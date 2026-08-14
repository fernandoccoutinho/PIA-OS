"""
Testes de `MultiInputTransformationManager` (E3.4.2).

Cobrem as exigências 14–45 do §12.2 do prompt canônico. Usam a sessão
SQLite em memória do `conftest.py` deste diretório — que registra as
tabelas cognitivas **reais** no `Base` real, não um schema paralelo.

Garantias que dependem de lock de linha e de concorrência real vivem em
`tests/integration/cognitive/test_multi_input_transformation_integration.py`,
contra PostgreSQL: SQLite não tem lock de linha, e afirmar aqui o que
só o PostgreSQL prova seria overclaim.
"""

import ast
import pathlib
import re
import subprocess
import sys
import uuid
from datetime import UTC, datetime

import pytest

from app.cognitive.errors.exceptions import (
    CausalPredecessorNotFoundError,
    CausalPredecessorSubjectMismatchError,
    MultiInputSourceNotFoundError,
)
from app.cognitive.models.cognitive_object import CognitiveObject
from app.cognitive.models.enums import (
    AccessibilityState,
    CausalEventType,
    LineageRelation,
    RevisionStatus,
    TransformationKind,
)
from app.cognitive.repositories.causal_history_repository import CausalHistoryRepository
from app.cognitive.repositories.lineage_repository import LineageRepository
from app.cognitive.repositories.object_repository import ObjectRepository
from app.cognitive.repositories.transformation_repository import TransformationRepository
from app.cognitive.services.causal_history_manager import CausalHistoryManager
from app.cognitive.services.clid_manager import ClidManager
from app.cognitive.services.multi_input_transformation_manager import (
    MultiInputTransformationManager,
)


@pytest.fixture
def kit(cognitive_session):
    objetos = ObjectRepository(cognitive_session)
    linhagem = LineageRepository(cognitive_session)
    transformacoes = TransformationRepository(cognitive_session)
    historias = CausalHistoryRepository(cognitive_session)
    clid = ClidManager(objetos, linhagem)
    causal = CausalHistoryManager(historias)
    manager = MultiInputTransformationManager(
        objetos, clid, linhagem, transformacoes, causal, historias
    )
    return manager, objetos, linhagem, transformacoes, historias, causal, clid


def _provenance(cognitive_session, coid: uuid.UUID) -> uuid.UUID:
    """Cria um `ProvenanceRecord` mínimo e devolve seu id.

    Necessário porque `causal_history_events.actor_ref` é FK para
    `provenance_records.id`: um UUID arbitrário como `actor_ref` é
    corretamente recusado pelo banco.
    """
    from app.cognitive.models.enums import ProvenanceActorType, ProvenanceSourceType
    from app.cognitive.models.provenance_record import ProvenanceRecord
    from app.cognitive.repositories.provenance_repository import ProvenanceRepository

    registro = ProvenanceRepository(cognitive_session).add(
        ProvenanceRecord(
            coid=coid,
            source_type=ProvenanceSourceType.HUMAN,
            actor_type=ProvenanceActorType.HUMAN,
        )
    )
    return registro.id


def _fonte(objetos: ObjectRepository, *, clid: uuid.UUID | None = None) -> CognitiveObject:
    objeto = objetos.add(CognitiveObject())
    if clid is not None:
        objeto.clid = clid
        objetos.update(objeto)
    return objeto


# --- 14/15. CLID comum ------------------------------------------------


def test_e342_two_sources_sharing_a_clid_propagate_it_to_the_target(kit):
    manager, objetos, *_ = kit
    clid = uuid.uuid4()
    a, b = _fonte(objetos, clid=clid), _fonte(objetos, clid=clid)

    recibo = manager.derive_many(
        source_coids=[a.id, b.id],
        operation_type="consolidar",
        declared_losses=["variações de ramo"],
    )

    assert recibo.target_clid == clid
    assert objetos.get_by_id(recibo.target_coid).clid == clid


def test_e342_three_sources_sharing_a_clid_propagate_it(kit):
    manager, objetos, *_ = kit
    clid = uuid.uuid4()
    fontes = [_fonte(objetos, clid=clid) for _ in range(3)]

    recibo = manager.derive_many(
        source_coids=[f.id for f in fontes],
        operation_type="consolidar",
        declared_losses=["detalhe por ramo"],
    )

    assert recibo.target_clid == clid
    assert len(recibo.source_coids) == 3
    assert len(recibo.lineage_edge_ids) == 3


# --- 16/17/18. CLID divergente ou ausente ----------------------------


def test_e342_sources_with_different_clids_produce_a_target_without_clid(kit):
    """`MIXED HISTORIES != SINGLE CONTINUITY` — o alvo não recebe um
    CLID inventado nem o da primeira fonte."""
    manager, objetos, *_ = kit
    a, b = _fonte(objetos, clid=uuid.uuid4()), _fonte(objetos, clid=uuid.uuid4())

    recibo = manager.derive_many(
        source_coids=[a.id, b.id],
        operation_type="consolidar",
        declared_losses=["continuidades distintas não fundidas"],
    )

    assert recibo.target_clid is None
    assert objetos.get_by_id(recibo.target_coid).clid is None


def test_e342_one_source_without_clid_produces_a_target_without_clid(kit):
    manager, objetos, *_ = kit
    clid = uuid.uuid4()
    a, b = _fonte(objetos, clid=clid), _fonte(objetos)

    recibo = manager.derive_many(
        source_coids=[a.id, b.id],
        operation_type="consolidar",
        declared_losses=["fonte sem continuidade registrada"],
    )

    assert recibo.target_clid is None


def test_e342_all_sources_without_clid_produce_a_target_without_clid(kit):
    manager, objetos, *_ = kit
    a, b = _fonte(objetos), _fonte(objetos)

    recibo = manager.derive_many(
        source_coids=[a.id, b.id],
        operation_type="consolidar",
        declared_losses=["nenhuma continuidade prévia"],
    )

    assert recibo.target_clid is None


def test_e342_sources_without_clid_do_not_receive_one(kit):
    """`SOURCE CLID GENERATION = FORBIDDEN` — a razão de não usar
    `ClidManager.inherit()`, que geraria e gravaria CLID na fonte."""
    manager, objetos, *_ = kit
    a, b = _fonte(objetos), _fonte(objetos)

    manager.derive_many(
        source_coids=[a.id, b.id],
        operation_type="consolidar",
        declared_losses=["x"],
    )

    assert objetos.get_by_id(a.id).clid is None
    assert objetos.get_by_id(b.id).clid is None


# --- 19. Fonte soft-deleted ------------------------------------------


def test_e342_soft_deleted_source_is_a_legitimate_source(kit):
    """`SOFT_DELETED != NEVER EXISTED` — a fonte é referenciada, entra
    em `input_refs` e continua endpoint de linhagem."""
    manager, objetos, linhagem, transformacoes, *_ = kit
    a, b = _fonte(objetos), _fonte(objetos)
    objetos.soft_delete(b)
    apagada_em = objetos.get_by_id(b.id, include_deleted=True).deleted_at
    assert apagada_em is not None

    recibo = manager.derive_many(
        source_coids=[a.id, b.id],
        operation_type="consolidar",
        declared_losses=["x"],
    )

    registro = transformacoes.get_by_id(recibo.transformation_id)
    assert str(b.id) in registro.input_refs
    assert linhagem.edge_exists(b.id, recibo.target_coid, LineageRelation.MERGE)
    # não recuperada, e `deleted_at` intocado
    assert objetos.get_by_id(b.id) is None
    assert objetos.get_by_id(b.id, include_deleted=True).deleted_at == apagada_em


# --- 20. Ordem canônica -----------------------------------------------


def test_e342_input_refs_are_canonical_regardless_of_input_order(kit):
    """`(M1,M2,M3)` e `(M3,M1,M2)` são o mesmo pedido — ordem de
    digitação não é informação semântica."""
    manager, objetos, _lin, transformacoes, *_ = kit
    fontes = [_fonte(objetos) for _ in range(3)]
    ids = [f.id for f in fontes]

    r1 = manager.derive_many(source_coids=ids, operation_type="c1", declared_losses=["x"])
    r2 = manager.derive_many(
        source_coids=[ids[2], ids[0], ids[1]], operation_type="c2", declared_losses=["x"]
    )

    esperado = [str(c) for c in sorted(ids)]
    assert transformacoes.get_by_id(r1.transformation_id).input_refs == esperado
    assert transformacoes.get_by_id(r2.transformation_id).input_refs == esperado
    assert r1.source_coids == r2.source_coids == tuple(sorted(ids))


# --- 21/22/23/24. Cardinalidade e existência de fontes ---------------


def test_e342_zero_sources_is_rejected(kit):
    manager, *_ = kit
    with pytest.raises(ValueError, match="ao menos duas fontes"):
        manager.derive_many(source_coids=[], operation_type="c", declared_losses=["x"])


def test_e342_single_source_is_rejected(kit):
    manager, objetos, *_ = kit
    a = _fonte(objetos)
    with pytest.raises(ValueError, match="VersionManager.derive"):
        manager.derive_many(source_coids=[a.id], operation_type="c", declared_losses=["x"])


def test_e342_duplicate_source_is_rejected_not_deduplicated(kit):
    manager, objetos, *_ = kit
    a = _fonte(objetos)
    with pytest.raises(ValueError, match="duplicados"):
        manager.derive_many(source_coids=[a.id, a.id], operation_type="c", declared_losses=["x"])


def test_e342_missing_source_raises_with_the_full_set(kit):
    manager, objetos, *_ = kit
    a = _fonte(objetos)
    ausente_1, ausente_2 = uuid.uuid4(), uuid.uuid4()

    with pytest.raises(MultiInputSourceNotFoundError) as exc:
        manager.derive_many(
            source_coids=[a.id, ausente_1, ausente_2],
            operation_type="c",
            declared_losses=["x"],
        )

    assert exc.value.code == "PIA-8029"
    assert set(exc.value.missing_coids) == {ausente_1, ausente_2}


# --- 25/26/27/28. Validação de argumentos ----------------------------


@pytest.mark.parametrize("valor", ["", "   "])
def test_e342_blank_operation_type_is_rejected(kit, valor):
    manager, objetos, *_ = kit
    a, b = _fonte(objetos), _fonte(objetos)
    with pytest.raises(ValueError, match="operation_type"):
        manager.derive_many(source_coids=[a.id, b.id], operation_type=valor, declared_losses=["x"])


def test_e342_operation_type_longer_than_the_column_is_rejected(kit):
    """Preflight, não erro de banco no meio de uma operação já
    parcialmente aplicada."""
    manager, objetos, *_ = kit
    a, b = _fonte(objetos), _fonte(objetos)
    with pytest.raises(ValueError, match="capacidade real da coluna"):
        manager.derive_many(
            source_coids=[a.id, b.id], operation_type="x" * 65, declared_losses=["x"]
        )


def test_e342_empty_declared_losses_is_rejected(kit):
    manager, objetos, *_ = kit
    a, b = _fonte(objetos), _fonte(objetos)
    with pytest.raises(ValueError, match="MANDATORY"):
        manager.derive_many(source_coids=[a.id, b.id], operation_type="c", declared_losses=[])


@pytest.mark.parametrize("perda", ["", "   ", "\t\n"])
def test_e342_blank_declared_loss_is_rejected(kit, perda):
    manager, objetos, *_ = kit
    a, b = _fonte(objetos), _fonte(objetos)
    with pytest.raises(ValueError, match="declaração vazia"):
        manager.derive_many(source_coids=[a.id, b.id], operation_type="c", declared_losses=[perda])


def test_e342_string_as_declared_losses_is_rejected(kit):
    """`str` é iterável — aceitá-lo transformaria a declaração numa
    coleção de caracteres."""
    manager, objetos, *_ = kit
    a, b = _fonte(objetos), _fonte(objetos)
    with pytest.raises(TypeError, match="coleção de strings"):
        manager.derive_many(
            source_coids=[a.id, b.id], operation_type="c", declared_losses="perdeu contexto"
        )


@pytest.mark.parametrize("invalido", [123, None, [1, 2]])
def test_e342_invalid_declared_losses_types_are_rejected(kit, invalido):
    manager, objetos, *_ = kit
    a, b = _fonte(objetos), _fonte(objetos)
    with pytest.raises(TypeError):
        manager.derive_many(source_coids=[a.id, b.id], operation_type="c", declared_losses=invalido)


def test_e342_invalid_source_coid_types_are_rejected(kit):
    manager, objetos, *_ = kit
    a = _fonte(objetos)
    with pytest.raises(TypeError, match="apenas uuid.UUID"):
        manager.derive_many(
            source_coids=[a.id, "nao-e-uuid"], operation_type="c", declared_losses=["x"]
        )


@pytest.mark.parametrize(
    ("campo", "valor"),
    [("actor_ref", "nao-e-uuid"), ("policy_ref", 123), ("occurred_at", "ontem")],
)
def test_e342_invalid_optional_types_are_rejected(kit, campo, valor):
    manager, objetos, *_ = kit
    a, b = _fonte(objetos), _fonte(objetos)
    with pytest.raises(TypeError, match=campo):
        manager.derive_many(
            source_coids=[a.id, b.id],
            operation_type="c",
            declared_losses=["x"],
            **{campo: valor},
        )


def test_e342_blank_policy_ref_is_rejected(kit):
    manager, objetos, *_ = kit
    a, b = _fonte(objetos), _fonte(objetos)
    with pytest.raises(ValueError, match="policy_ref"):
        manager.derive_many(
            source_coids=[a.id, b.id],
            operation_type="c",
            declared_losses=["x"],
            policy_ref="   ",
        )


# --- 29/30/31. Linhagem e registro -----------------------------------


def test_e342_exactly_one_merge_edge_per_source(kit):
    manager, objetos, linhagem, *_ = kit
    fontes = [_fonte(objetos) for _ in range(3)]

    recibo = manager.derive_many(
        source_coids=[f.id for f in fontes], operation_type="c", declared_losses=["x"]
    )

    arestas = linhagem.list_parents(recibo.target_coid)
    assert len(arestas) == 3
    assert {a.relation_type for a in arestas} == {LineageRelation.MERGE}
    assert {a.parent_coid for a in arestas} == {f.id for f in fontes}
    assert len(recibo.lineage_edge_ids) == 3


def test_e342_exactly_one_transformation_record(kit):
    """Contraste deliberado com o cenário G1 da E3.12, que produzia
    dois registros incoerentes para uma única operação."""
    manager, objetos, _lin, transformacoes, *_ = kit
    a, b = _fonte(objetos), _fonte(objetos)

    recibo = manager.derive_many(
        source_coids=[a.id, b.id], operation_type="c", declared_losses=["x"]
    )

    por_a = transformacoes.list_by_input_coid(a.id)
    por_b = transformacoes.list_by_input_coid(b.id)
    assert len(por_a) == len(por_b) == 1
    assert por_a[0].id == por_b[0].id == recibo.transformation_id
    assert por_a[0].output_refs == [str(recibo.target_coid)]


def test_e342_transformation_kind_is_derivation_never_revision(kit):
    manager, objetos, _lin, transformacoes, *_ = kit
    a, b = _fonte(objetos), _fonte(objetos)

    recibo = manager.derive_many(
        source_coids=[a.id, b.id], operation_type="c", declared_losses=["x"]
    )

    registro = transformacoes.get_by_id(recibo.transformation_id)
    assert registro.transformation_kind is TransformationKind.DERIVATION
    assert registro.transformation_kind is not TransformationKind.REVISION


def test_e342_declarations_are_preserved_exactly_as_given(kit):
    manager, objetos, _lin, transformacoes, *_ = kit
    a, b = _fonte(objetos), _fonte(objetos)
    perdas = ["nuance do ramo A", "exemplos numéricos"]
    preservacoes = ["tese central"]

    recibo = manager.derive_many(
        source_coids=[a.id, b.id],
        operation_type="c",
        declared_losses=perdas,
        declared_preservations=preservacoes,
    )

    registro = transformacoes.get_by_id(recibo.transformation_id)
    assert registro.declared_losses == perdas
    assert registro.declared_preservations == preservacoes


def test_e342_mutating_the_declaration_list_afterwards_does_not_change_the_record(kit):
    manager, objetos, _lin, transformacoes, *_ = kit
    a, b = _fonte(objetos), _fonte(objetos)
    perdas = ["original"]

    recibo = manager.derive_many(
        source_coids=[a.id, b.id], operation_type="c", declared_losses=perdas
    )
    perdas.append("acrescentada depois")

    assert transformacoes.get_by_id(recibo.transformation_id).declared_losses == ["original"]


# --- 32/33/34/35. Fontes intocadas -----------------------------------


def test_e342_no_source_becomes_superseded(kit):
    manager, objetos, *_ = kit
    a, b = _fonte(objetos), _fonte(objetos)
    assert a.revision_status is None

    recibo = manager.derive_many(
        source_coids=[a.id, b.id], operation_type="c", declared_losses=["x"]
    )

    assert objetos.get_by_id(a.id).revision_status is None
    assert objetos.get_by_id(b.id).revision_status is None
    assert objetos.get_by_id(recibo.target_coid).revision_status is None
    assert RevisionStatus.SUPERSEDED not in {
        objetos.get_by_id(a.id).revision_status,
        objetos.get_by_id(b.id).revision_status,
    }


def test_e342_no_source_clid_is_mutated(kit):
    manager, objetos, *_ = kit
    clid_a, clid_b = uuid.uuid4(), uuid.uuid4()
    a, b = _fonte(objetos, clid=clid_a), _fonte(objetos, clid=clid_b)

    manager.derive_many(source_coids=[a.id, b.id], operation_type="c", declared_losses=["x"])

    assert objetos.get_by_id(a.id).clid == clid_a
    assert objetos.get_by_id(b.id).clid == clid_b


def test_e342_no_source_accessibility_is_mutated(kit):
    manager, objetos, *_ = kit
    a, b = _fonte(objetos), _fonte(objetos)
    b.accessibility = AccessibilityState.INACCESSIBLE
    objetos.update(b)

    manager.derive_many(source_coids=[a.id, b.id], operation_type="c", declared_losses=["x"])

    assert objetos.get_by_id(a.id).accessibility is AccessibilityState.ACTIVE
    assert objetos.get_by_id(b.id).accessibility is AccessibilityState.INACCESSIBLE


def test_e342_no_source_deleted_at_is_mutated(kit):
    manager, objetos, *_ = kit
    a, b = _fonte(objetos), _fonte(objetos)

    manager.derive_many(source_coids=[a.id, b.id], operation_type="c", declared_losses=["x"])

    assert objetos.get_by_id(a.id).deleted_at is None
    assert objetos.get_by_id(b.id).deleted_at is None


def test_e342_target_is_a_new_coid_distinct_from_every_source(kit):
    manager, objetos, *_ = kit
    a, b = _fonte(objetos), _fonte(objetos)

    recibo = manager.derive_many(
        source_coids=[a.id, b.id], operation_type="c", declared_losses=["x"]
    )

    assert recibo.target_coid not in {a.id, b.id}
    assert objetos.get_by_id(recibo.target_coid) is not None


# --- 36/37/38/39/40/41/42. Causalidade -------------------------------


def test_e342_no_predecessor_produces_exactly_one_root_event(kit):
    """`MISSING PREDECESSOR != MISSING OPERATION` — a ocorrência da
    própria transformação é fato conhecido."""
    manager, objetos, _lin, _trans, _hist, causal, _clid = kit
    a, b = _fonte(objetos), _fonte(objetos)

    recibo = manager.derive_many(
        source_coids=[a.id, b.id], operation_type="c", declared_losses=["x"]
    )

    eventos = causal.events_for(recibo.target_coid)
    assert len(eventos) == 1
    assert eventos[0].predecessor_event_id is None
    assert eventos[0].event_type is CausalEventType.TRANSFORMED
    assert len(recibo.causal_event_ids) == 1
    assert recibo.predecessor_event_ids == ()


def test_e342_n_predecessors_produce_n_events(kit):
    manager, objetos, _lin, _trans, _hist, causal, _clid = kit
    a, b = _fonte(objetos), _fonte(objetos)
    ev_a = causal.record(subject_coid=a.id, event_type=CausalEventType.CREATED)
    ev_b = causal.record(subject_coid=b.id, event_type=CausalEventType.CREATED)

    recibo = manager.derive_many(
        source_coids=[a.id, b.id],
        operation_type="c",
        declared_losses=["x"],
        predecessor_event_ids=[ev_a.id, ev_b.id],
    )

    eventos = causal.events_for(recibo.target_coid)
    assert len(eventos) == 2
    assert {e.predecessor_event_id for e in eventos} == {ev_a.id, ev_b.id}
    assert set(recibo.predecessor_event_ids) == {ev_a.id, ev_b.id}


def test_e342_missing_predecessor_is_rejected(kit):
    manager, objetos, *_ = kit
    a, b = _fonte(objetos), _fonte(objetos)
    inexistente = uuid.uuid4()

    with pytest.raises(CausalPredecessorNotFoundError) as exc:
        manager.derive_many(
            source_coids=[a.id, b.id],
            operation_type="c",
            declared_losses=["x"],
            predecessor_event_ids=[inexistente],
        )

    assert exc.value.code == "PIA-8030"
    assert exc.value.missing_event_ids == (inexistente,)


def test_e342_predecessor_of_a_foreign_subject_is_rejected(kit):
    """Aceitá-lo ligaria a história do alvo a um objeto que não
    participou da transformação."""
    manager, objetos, _lin, _trans, _hist, causal, _clid = kit
    a, b, estranho = _fonte(objetos), _fonte(objetos), _fonte(objetos)
    ev_estranho = causal.record(subject_coid=estranho.id, event_type=CausalEventType.CREATED)

    with pytest.raises(CausalPredecessorSubjectMismatchError) as exc:
        manager.derive_many(
            source_coids=[a.id, b.id],
            operation_type="c",
            declared_losses=["x"],
            predecessor_event_ids=[ev_estranho.id],
        )

    assert exc.value.code == "PIA-8031"
    assert exc.value.subject_coid == estranho.id


def test_e342_duplicate_predecessor_is_rejected(kit):
    manager, objetos, _lin, _trans, _hist, causal, _clid = kit
    a, b = _fonte(objetos), _fonte(objetos)
    ev = causal.record(subject_coid=a.id, event_type=CausalEventType.CREATED)

    with pytest.raises(ValueError, match="repetições"):
        manager.derive_many(
            source_coids=[a.id, b.id],
            operation_type="c",
            declared_losses=["x"],
            predecessor_event_ids=[ev.id, ev.id],
        )


def test_e342_invalid_predecessor_types_are_rejected(kit):
    manager, objetos, *_ = kit
    a, b = _fonte(objetos), _fonte(objetos)
    with pytest.raises(TypeError, match="predecessor_event_ids"):
        manager.derive_many(
            source_coids=[a.id, b.id],
            operation_type="c",
            declared_losses=["x"],
            predecessor_event_ids=["nao-e-uuid"],
        )


def test_e342_payload_ref_points_to_the_transformation(kit):
    """Referência, nunca conteúdo: `CAUSAL_TRACE != TRANSCRIPT`."""
    manager, objetos, _lin, _trans, _hist, causal, _clid = kit
    a, b = _fonte(objetos), _fonte(objetos)

    recibo = manager.derive_many(
        source_coids=[a.id, b.id], operation_type="c", declared_losses=["x"]
    )

    eventos = causal.events_for(recibo.target_coid)
    assert eventos[0].payload_ref == str(recibo.transformation_id)


def test_e342_occurred_at_none_stays_none(kit):
    """Nunca preenchido com `created_at` — o sistema não afirma saber
    quando o fato ocorreu."""
    manager, objetos, _lin, _trans, _hist, causal, _clid = kit
    a, b = _fonte(objetos), _fonte(objetos)

    recibo = manager.derive_many(
        source_coids=[a.id, b.id], operation_type="c", declared_losses=["x"]
    )

    assert causal.events_for(recibo.target_coid)[0].occurred_at is None


def test_e342_occurred_at_is_preserved_when_given(kit):
    manager, objetos, _lin, _trans, _hist, causal, _clid = kit
    a, b = _fonte(objetos), _fonte(objetos)
    quando = datetime(2024, 3, 1, 12, 0, tzinfo=UTC)

    recibo = manager.derive_many(
        source_coids=[a.id, b.id],
        operation_type="c",
        declared_losses=["x"],
        occurred_at=quando,
    )

    gravado = causal.events_for(recibo.target_coid)[0].occurred_at
    # O dialeto SQLite dos testes unitários descarta `tzinfo` mesmo em
    # `DateTime(timezone=True)`; o instante atravessa intacto. A
    # asserção com fuso preservado pertence à integração contra
    # PostgreSQL, que é onde a coluna é de fato `timestamptz`.
    assert gravado.replace(tzinfo=UTC) == quando


def test_e342_actor_ref_and_policy_ref_are_recorded_when_given(kit, cognitive_session):
    """Ausência continua ausência; presença vem do chamador, nunca
    inferida."""
    manager, objetos, _lin, transformacoes, *_ = kit
    a, b = _fonte(objetos), _fonte(objetos)
    # `causal_history_events.actor_ref` é FK real para
    # `provenance_records.id` (E3.9), enquanto o campo homônimo de
    # `TransformationRecord` não tem FK. Um `actor_ref` informado
    # precisa portanto ser um `ProvenanceRecord` existente — e a
    # autoridade final é a FK do banco, não uma pré-checagem inventada
    # aqui, mesma disciplina de E3.3/E3.4.
    ator = _provenance(cognitive_session, a.id)

    recibo = manager.derive_many(
        source_coids=[a.id, b.id],
        operation_type="c",
        declared_losses=["x"],
        actor_ref=ator,
        policy_ref="policy://e3-4-2",
    )

    registro = transformacoes.get_by_id(recibo.transformation_id)
    assert registro.actor_ref == ator
    assert registro.policy_ref == "policy://e3-4-2"


def test_e342_absent_actor_and_policy_stay_absent(kit):
    manager, objetos, _lin, transformacoes, *_ = kit
    a, b = _fonte(objetos), _fonte(objetos)

    recibo = manager.derive_many(
        source_coids=[a.id, b.id], operation_type="c", declared_losses=["x"]
    )

    registro = transformacoes.get_by_id(recibo.transformation_id)
    assert registro.actor_ref is None
    assert registro.policy_ref is None


# --- 43/44. Transação -------------------------------------------------


def test_e342_manager_never_commits(kit, monkeypatch, cognitive_session):
    """A transação é do chamador. Um commit interno tornaria o rollback
    do chamador incapaz de desfazer a operação."""
    manager, objetos, *_ = kit
    a, b = _fonte(objetos), _fonte(objetos)
    chamadas = []
    monkeypatch.setattr(type(cognitive_session), "commit", lambda self: chamadas.append("commit"))

    manager.derive_many(source_coids=[a.id, b.id], operation_type="c", declared_losses=["x"])

    assert chamadas == []


def test_e342_preflight_failure_writes_nothing(kit, cognitive_session):
    """`DATABASE_WRITES = 0` em erro de preflight: nenhum alvo órfão,
    nenhuma edge, nenhum registro."""
    from sqlalchemy import event as sa_event

    manager, objetos, *_ = kit
    a = _fonte(objetos)
    cognitive_session.flush()

    escritas = []

    def _contar(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        if statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")):
            escritas.append(statement)

    engine = cognitive_session.get_bind()
    sa_event.listen(engine, "before_cursor_execute", _contar)
    try:
        with pytest.raises(MultiInputSourceNotFoundError):
            manager.derive_many(
                source_coids=[a.id, uuid.uuid4()],
                operation_type="c",
                declared_losses=["x"],
            )
        cognitive_session.flush()
    finally:
        sa_event.remove(engine, "before_cursor_execute", _contar)

    assert escritas == []


def test_e342_predecessor_validation_happens_before_any_write(kit, cognitive_session):
    from sqlalchemy import event as sa_event

    manager, objetos, *_ = kit
    a, b = _fonte(objetos), _fonte(objetos)
    cognitive_session.flush()

    escritas = []

    def _contar(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        if statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")):
            escritas.append(statement)

    engine = cognitive_session.get_bind()
    sa_event.listen(engine, "before_cursor_execute", _contar)
    try:
        with pytest.raises(CausalPredecessorNotFoundError):
            manager.derive_many(
                source_coids=[a.id, b.id],
                operation_type="c",
                declared_losses=["x"],
                predecessor_event_ids=[uuid.uuid4()],
            )
        cognitive_session.flush()
    finally:
        sa_event.remove(engine, "before_cursor_execute", _contar)

    assert escritas == []


# --- 45. Ordens de import em interpretadores limpos ------------------


@pytest.mark.parametrize(
    "primeiro_import",
    [
        "app.cognitive.schemas.multi_input_transformation",
        "app.cognitive.services.multi_input_transformation_manager",
        "app.cognitive.errors",
        "app.cognitive.models",
    ],
)
def test_e342_public_imports_work_in_any_order_in_a_clean_interpreter(primeiro_import):
    """Guarda contra ciclo de import — o sétimo defeito da E4.3.1, que
    só apareceu porque a suíte sempre importava outro módulo antes.
    Dentro do mesmo processo `sys.modules` esconderia o problema, então
    cada ordem roda num interpretador novo.
    """
    resultado = subprocess.run(
        [sys.executable, "-c", f"import {primeiro_import}; print('ok')"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert resultado.returncode == 0, resultado.stderr
    assert "ok" in resultado.stdout


# --- Fronteiras verificadas por ausência estrutural -------------------


def test_e342_manager_exposes_only_derive_many():
    """Superfície pública mínima: nada de score, rank, selecionar fonte
    vencedora, resolver divergência ou aprender."""
    publicos = {nome for nome in dir(MultiInputTransformationManager) if not nome.startswith("_")}
    assert publicos == {"derive_many"}


def test_e342_manager_source_has_no_forbidden_capabilities():
    """Testar ausência é o único modo honesto de provar uma fronteira:
    um teste de comportamento passaria igual se a capacidade proibida
    existisse mas não fosse chamada. Compara o **código executável**
    (AST sem docstrings), como em E4.3.1 — as docstrings citam
    nominalmente o que o módulo não faz.
    """
    import app.cognitive.services.multi_input_transformation_manager as modulo

    arvore = ast.parse(pathlib.Path(modulo.__file__).read_text(encoding="utf-8"))
    for no in ast.walk(arvore):
        if isinstance(no, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            corpo = no.body
            if (
                corpo
                and isinstance(corpo[0], ast.Expr)
                and isinstance(corpo[0].value, ast.Constant)
                and isinstance(corpo[0].value.value, str)
            ):
                no.body = corpo[1:] or [ast.Pass()]
    executavel = ast.unparse(arvore)

    for proibido in (
        "_score",
        "rank",
        "winner",
        "best_source",
        "resolve_divergence",
        "learn",
        "embedding",
        "provider",
        "transcript",
        "commit(",
        "REVISION",
    ):
        assert proibido not in executavel, f"capacidade proibida encontrada: {proibido}"


def test_e342_manager_does_not_import_app_memory():
    """A dependência aponta em uma direção só: `app/cognitive` é dona do
    patrimônio e não conhece a camada de memória."""
    import app.cognitive.schemas.multi_input_transformation as schema_mod
    import app.cognitive.services.multi_input_transformation_manager as manager_mod

    padrao = re.compile(r"^\s*(from|import)\s+app\.memory", re.MULTILINE)
    for modulo in (manager_mod, schema_mod):
        fonte = pathlib.Path(modulo.__file__).read_text(encoding="utf-8")
        assert padrao.search(fonte) is None


# --- Ramos de tipo descobertos pela exigência de 100% ------------------


@pytest.mark.parametrize("invalido", [123, None, uuid.uuid4()])
def test_e342_non_iterable_source_coids_is_rejected(kit, invalido):
    """`source_coids` não iterável — inclusive um único UUID solto, que
    é o engano mais provável de quem quer consolidar."""
    manager, *_ = kit
    with pytest.raises(TypeError, match="coleção de uuid.UUID"):
        manager.derive_many(source_coids=invalido, operation_type="c", declared_losses=["x"])


def test_e342_string_as_source_coids_is_rejected(kit):
    manager, *_ = kit
    with pytest.raises(TypeError, match="coleção de uuid.UUID"):
        manager.derive_many(source_coids="abc", operation_type="c", declared_losses=["x"])


@pytest.mark.parametrize("invalido", [123, None, ["c"]])
def test_e342_non_string_operation_type_is_rejected(kit, invalido):
    manager, objetos, *_ = kit
    a, b = _fonte(objetos), _fonte(objetos)
    with pytest.raises(TypeError, match="operation_type deve ser str"):
        manager.derive_many(
            source_coids=[a.id, b.id], operation_type=invalido, declared_losses=["x"]
        )


@pytest.mark.parametrize("invalido", [123, None, uuid.uuid4()])
def test_e342_non_iterable_predecessor_event_ids_is_rejected(kit, invalido):
    manager, objetos, *_ = kit
    a, b = _fonte(objetos), _fonte(objetos)
    with pytest.raises(TypeError, match="predecessor_event_ids deve ser uma coleção"):
        manager.derive_many(
            source_coids=[a.id, b.id],
            operation_type="c",
            declared_losses=["x"],
            predecessor_event_ids=invalido,
        )


def test_e342_string_as_predecessor_event_ids_is_rejected(kit):
    manager, objetos, *_ = kit
    a, b = _fonte(objetos), _fonte(objetos)
    with pytest.raises(TypeError, match="predecessor_event_ids deve ser uma coleção"):
        manager.derive_many(
            source_coids=[a.id, b.id],
            operation_type="c",
            declared_losses=["x"],
            predecessor_event_ids="abc",
        )
