"""
Integração da E4.5 — Consolidation Manager, contra PostgreSQL real.

Cobre as 30 exigências do §18. A prova decisiva é a **composição real**:

    ConsolidationManager(
        transformation_port=MultiInputTransformationManager(...),
        persistence_manager=PersistenceManager(...),
    )

sem adapter, com o objeto real da E3.4.2 satisfazendo a porta apenas
por sua forma. Este arquivo importa os dois lados — permitido pelo §5,
que veda o import cruzado no **código de produção** de `app/memory`,
não no arranjo de teste que monta a composição.

Não substitui por SQLite: atomicidade sob rollback, FK real,
`timestamptz` e concorrência entre conexões só existem no banco de
produção.
"""

import dataclasses
import threading
import uuid

import pytest
import sqlalchemy as sa

from app.cognitive.models.cognitive_object import CognitiveObject
from app.cognitive.models.enums import CausalEventType, LineageRelation, TransformationKind
from app.cognitive.repositories.causal_history_repository import CausalHistoryRepository
from app.cognitive.repositories.lineage_repository import LineageRepository
from app.cognitive.repositories.object_repository import ObjectRepository
from app.cognitive.repositories.transformation_repository import TransformationRepository
from app.cognitive.services.causal_history_manager import CausalHistoryManager
from app.cognitive.services.clid_manager import ClidManager
from app.cognitive.services.multi_input_transformation_manager import (
    MultiInputTransformationManager,
)
from app.database.health import check_database_health
from app.memory.errors.exceptions import ConsolidationVerificationError
from app.memory.ports import (
    MultiInputTransformationPort,
)
from app.memory.repositories.continuity_evidence_repository import ContinuityEvidenceRepository
from app.memory.schemas.persistence import PersistenceEvidenceKind, PersistenceOutcome
from app.memory.services.consolidation_manager import ConsolidationManager
from app.memory.services.persistence_manager import PersistenceManager
from app.repositories.unit_of_work import UnitOfWork


def _postgres_pronto() -> bool:
    if not check_database_health().available:
        return False
    from sqlalchemy import inspect

    from app.database.engine import engine

    tabelas = inspect(engine).get_table_names()
    return {
        "cognitive_objects",
        "lineage_edges",
        "transformation_records",
        "causal_histories",
        "causal_history_events",
    }.issubset(tabelas)


pytestmark = pytest.mark.skipif(
    not _postgres_pronto(),
    reason="PostgreSQL real indisponível ou migrações cognitivas não aplicadas.",
)


def _compor(session) -> tuple[ConsolidationManager, MultiInputTransformationManager]:
    """Composição real, sobre a MESMA `Session`.

    A partilha da sessão não é detalhe de conveniência: sem ela o
    `PersistenceManager` não enxergaria as escritas ainda não
    commitadas, e a verificação de pós-condição viraria uma consulta a
    um estado anterior à própria consolidação — isto é, uma prova vazia.
    """
    objetos = ObjectRepository(session)
    linhagem = LineageRepository(session)
    transformacoes = TransformationRepository(session)
    historias = CausalHistoryRepository(session)
    porta = MultiInputTransformationManager(
        objetos,
        ClidManager(objetos, linhagem),
        linhagem,
        transformacoes,
        CausalHistoryManager(historias),
        historias,
    )
    persistencia = PersistenceManager(ContinuityEvidenceRepository(session))
    return ConsolidationManager(porta, persistencia), porta


def _criar_fontes(quantidade: int, *, clid: uuid.UUID | None = None) -> list[uuid.UUID]:
    with UnitOfWork() as uow:
        objetos = ObjectRepository(uow.session)
        criados = []
        for _ in range(quantidade):
            objeto = objetos.add(CognitiveObject())
            if clid is not None:
                objeto.clid = clid
                objetos.update(objeto)
            criados.append(objeto)
        uow.commit()
        return [o.id for o in criados]


def _contar(tabela: str) -> int:
    with UnitOfWork() as uow:
        return uow.session.execute(sa.text(f"SELECT count(*) FROM {tabela}")).scalar_one()


def _censo(coids: list[uuid.UUID]) -> list[tuple]:
    with UnitOfWork() as uow:
        return [
            tuple(linha)
            for linha in uow.session.execute(
                sa.text(
                    "SELECT id, clid, accessibility, revision_status, deleted_at "
                    "FROM cognitive_objects WHERE id = ANY(:c ::uuid[]) ORDER BY id"
                ),
                {"c": [str(c) for c in coids]},
            ).all()
        ]


def _limpar(coids: list[uuid.UUID]) -> None:
    if not coids:
        return
    alvos = [str(c) for c in coids]
    with UnitOfWork() as uow:
        s = uow.session
        s.execute(
            sa.text(
                "DELETE FROM causal_history_events WHERE history_id IN "
                "(SELECT id FROM causal_histories WHERE subject_coid = ANY(:c ::uuid[]))"
            ),
            {"c": alvos},
        )
        s.execute(
            sa.text("DELETE FROM causal_histories WHERE subject_coid = ANY(:c ::uuid[])"),
            {"c": alvos},
        )
        s.execute(
            sa.text(
                "DELETE FROM lineage_edges WHERE parent_coid = ANY(:c ::uuid[]) "
                "OR child_coid = ANY(:c ::uuid[])"
            ),
            {"c": alvos},
        )
        s.execute(
            sa.text(
                "DELETE FROM transformation_records WHERE input_refs::text LIKE ANY("
                "SELECT '%' || x || '%' FROM unnest(:c ::text[]) AS x)"
            ),
            {"c": alvos},
        )
        s.execute(
            sa.text("DELETE FROM provenance_records WHERE coid = ANY(:c ::uuid[])"),
            {"c": alvos},
        )
        s.execute(
            sa.text("DELETE FROM cognitive_objects WHERE id = ANY(:c ::uuid[])"), {"c": alvos}
        )
        uow.commit()


# --- 1. Composição real -----------------------------------------------


def test_ci1_real_composition_without_adapter():
    """A prova decisiva do §5: o manager real da E3.4.2 é injetado
    diretamente, satisfazendo a porta apenas pela forma."""
    with UnitOfWork() as uow:
        manager, porta = _compor(uow.session)
        assert isinstance(porta, MultiInputTransformationManager)
        assert isinstance(porta, MultiInputTransformationPort)
        assert isinstance(manager, ConsolidationManager)


def test_ci1b_the_real_receipt_satisfies_the_receipt_port():
    fontes = _criar_fontes(2)
    criados = list(fontes)
    try:
        with UnitOfWork() as uow:
            manager, _ = _compor(uow.session)
            resultado = manager.consolidate(source_coids=fontes, declared_losses=["x"])
            uow.commit()
            criados.append(resultado.target_coid)
        assert isinstance(resultado.target_coid, uuid.UUID)
    finally:
        _limpar(criados)


# --- 2/3. Caminho feliz -----------------------------------------------


@pytest.mark.parametrize("quantidade", [2, 3])
def test_ci2_ci3_happy_path_with_common_clid(quantidade):
    clid = uuid.uuid4()
    fontes = _criar_fontes(quantidade, clid=clid)
    criados = list(fontes)
    try:
        with UnitOfWork() as uow:
            manager, _ = _compor(uow.session)
            resultado = manager.consolidate(
                source_coids=fontes,
                declared_losses=["variações de ramo"],
                declared_preservations=["tese central"],
            )
            uow.commit()
            criados.append(resultado.target_coid)

        assert resultado.target_clid == clid
        assert resultado.source_count == quantidade
        assert len(resultado.lineage_edge_ids) == quantidade
        assert (
            resultado.persistence_assessment.outcome
            is PersistenceOutcome.RECORDED_CONTINUITY_EVIDENCE
        )
    finally:
        _limpar(criados)


# --- 4/5. CLID divergente ou ausente ----------------------------------


def test_ci4_distinct_clids_produce_a_target_without_clid():
    a = _criar_fontes(1, clid=uuid.uuid4())[0]
    b = _criar_fontes(1, clid=uuid.uuid4())[0]
    criados = [a, b]
    try:
        with UnitOfWork() as uow:
            manager, _ = _compor(uow.session)
            resultado = manager.consolidate(source_coids=[a, b], declared_losses=["x"])
            uow.commit()
            criados.append(resultado.target_coid)
        assert resultado.target_clid is None
        assert resultado.persistence_assessment.clid is None
    finally:
        _limpar(criados)


def test_ci5_source_without_clid_produces_a_target_without_clid():
    a = _criar_fontes(1, clid=uuid.uuid4())[0]
    b = _criar_fontes(1)[0]
    criados = [a, b]
    try:
        with UnitOfWork() as uow:
            manager, _ = _compor(uow.session)
            resultado = manager.consolidate(source_coids=[a, b], declared_losses=["x"])
            uow.commit()
            criados.append(resultado.target_coid)
        assert resultado.target_clid is None
        with UnitOfWork() as uow:
            assert ObjectRepository(uow.session).get_by_id(b).clid is None
    finally:
        _limpar(criados)


# --- 6. Fonte soft-deleted --------------------------------------------


def test_ci6_soft_deleted_source_stays_soft_deleted():
    """`SOFT_DELETED != NEVER EXISTED`; a E4.5 não recupera nada."""
    fontes = _criar_fontes(2)
    criados = list(fontes)
    try:
        with UnitOfWork() as uow:
            objetos = ObjectRepository(uow.session)
            objetos.soft_delete(objetos.get_by_id(fontes[1]))
            uow.commit()
        with UnitOfWork() as uow:
            apagada_em = (
                ObjectRepository(uow.session).get_by_id(fontes[1], include_deleted=True).deleted_at
            )
        assert apagada_em is not None

        with UnitOfWork() as uow:
            manager, _ = _compor(uow.session)
            resultado = manager.consolidate(source_coids=fontes, declared_losses=["x"])
            uow.commit()
            criados.append(resultado.target_coid)

        with UnitOfWork() as uow:
            objetos = ObjectRepository(uow.session)
            assert objetos.get_by_id(fontes[1]) is None
            assert objetos.get_by_id(fontes[1], include_deleted=True).deleted_at == apagada_em
        assert resultado.persistence_assessment.subject_deleted is False
    finally:
        _limpar(criados)


# --- 7 a 12. Cardinalidade e conteúdo do que foi escrito --------------


def test_ci7_to_ci12_exact_written_state():
    clid = uuid.uuid4()
    fontes = _criar_fontes(3, clid=clid)
    criados = list(fontes)
    perdas = ["  nuance do ramo A  ", "exemplos numéricos"]
    try:
        with UnitOfWork() as uow:
            manager, _ = _compor(uow.session)
            resultado = manager.consolidate(source_coids=fontes, declared_losses=perdas)
            uow.commit()
            criados.append(resultado.target_coid)

        with UnitOfWork() as uow:
            s = uow.session
            # 7 — exatamente um target
            assert (
                s.execute(
                    sa.text("SELECT count(*) FROM cognitive_objects WHERE id = :t"),
                    {"t": str(resultado.target_coid)},
                ).scalar_one()
                == 1
            )
            # 8 — exatamente N edges MERGE
            assert (
                s.execute(
                    sa.text(
                        "SELECT count(*) FROM lineage_edges WHERE child_coid = :t "
                        "AND relation_type = 'merge'"
                    ),
                    {"t": str(resultado.target_coid)},
                ).scalar_one()
                == 3
            )
            # 9 — exatamente um TransformationRecord
            assert (
                s.execute(
                    sa.text(
                        "SELECT count(*) FROM transformation_records "
                        "WHERE output_refs::text LIKE :t"
                    ),
                    {"t": f"%{resultado.target_coid}%"},
                ).scalar_one()
                == 1
            )
            registro = TransformationRepository(s).get_by_id(resultado.transformation_id)
            # 10 — DERIVATION, nunca REVISION
            assert registro.transformation_kind is TransformationKind.DERIVATION
            # 11 — input_refs canônicos
            assert registro.input_refs == [str(c) for c in sorted(fontes)]
            assert registro.output_refs == [str(resultado.target_coid)]
            # operation_type estável
            assert registro.operation_type == "consolidate"
            # 12 — perdas persistidas exatamente, sem normalização
            assert registro.declared_losses == perdas
    finally:
        _limpar(criados)


# --- 13/14/15. Causalidade e ator -------------------------------------


def test_ci13_root_causal_event():
    fontes = _criar_fontes(2)
    criados = list(fontes)
    try:
        with UnitOfWork() as uow:
            manager, _ = _compor(uow.session)
            resultado = manager.consolidate(source_coids=fontes, declared_losses=["x"])
            uow.commit()
            criados.append(resultado.target_coid)

        # Leitura DENTRO da sessão: instâncias ORM saem detached quando a
        # UnitOfWork fecha, e tocar um atributo depois disso dispara
        # DetachedInstanceError.
        with UnitOfWork() as uow:
            eventos = CausalHistoryManager(CausalHistoryRepository(uow.session)).events_for(
                resultado.target_coid
            )
            assert len(eventos) == 1
            assert eventos[0].predecessor_event_id is None
            assert eventos[0].event_type is CausalEventType.TRANSFORMED
            assert eventos[0].payload_ref == str(resultado.transformation_id)
    finally:
        _limpar(criados)


def test_ci14_multiple_explicit_predecessors():
    fontes = _criar_fontes(2)
    criados = list(fontes)
    try:
        with UnitOfWork() as uow:
            causal = CausalHistoryManager(CausalHistoryRepository(uow.session))
            ev_a = causal.record(subject_coid=fontes[0], event_type=CausalEventType.CREATED)
            ev_b = causal.record(subject_coid=fontes[1], event_type=CausalEventType.CREATED)
            uow.commit()
            predecessores = [ev_a.id, ev_b.id]

        with UnitOfWork() as uow:
            manager, _ = _compor(uow.session)
            resultado = manager.consolidate(
                source_coids=fontes,
                declared_losses=["x"],
                predecessor_event_ids=predecessores,
            )
            uow.commit()
            criados.append(resultado.target_coid)

        assert len(resultado.causal_event_ids) == 2
        assert set(resultado.predecessor_event_ids) == set(predecessores)
    finally:
        _limpar(criados)


def test_ci15_actor_ref_preserved_in_transformation_and_causality():
    from app.cognitive.models.enums import ProvenanceActorType, ProvenanceSourceType
    from app.cognitive.models.provenance_record import ProvenanceRecord
    from app.cognitive.repositories.provenance_repository import ProvenanceRepository

    fontes = _criar_fontes(2, clid=uuid.uuid4())
    criados = list(fontes)
    try:
        with UnitOfWork() as uow:
            ator = ProvenanceRepository(uow.session).add(
                ProvenanceRecord(
                    coid=fontes[0],
                    source_type=ProvenanceSourceType.HUMAN,
                    actor_type=ProvenanceActorType.HUMAN,
                )
            )
            uow.commit()
            ator_id = ator.id

        with UnitOfWork() as uow:
            manager, _ = _compor(uow.session)
            resultado = manager.consolidate(
                source_coids=fontes, declared_losses=["x"], actor_ref=ator_id
            )
            uow.commit()
            criados.append(resultado.target_coid)

        with UnitOfWork() as uow:
            na_transformacao = uow.session.execute(
                sa.text("SELECT actor_ref FROM transformation_records WHERE id = :t"),
                {"t": str(resultado.transformation_id)},
            ).scalar_one()
            causais = [
                linha[0]
                for linha in uow.session.execute(
                    sa.text(
                        "SELECT e.actor_ref FROM causal_history_events e "
                        "JOIN causal_histories h ON h.id = e.history_id "
                        "WHERE h.subject_coid = :t"
                    ),
                    {"t": str(resultado.target_coid)},
                ).all()
            ]
        assert na_transformacao == ator_id
        assert set(causais) == {ator_id}
    finally:
        _limpar(criados)


# --- 16 a 19. Verificação pela E4.4 -----------------------------------


def test_ci16_to_ci19_assessment_matches_the_receipt_exactly():
    clid = uuid.uuid4()
    fontes = _criar_fontes(3, clid=clid)
    criados = list(fontes)
    try:
        with UnitOfWork() as uow:
            manager, _ = _compor(uow.session)
            resultado = manager.consolidate(source_coids=fontes, declared_losses=["x"])
            uow.commit()
            criados.append(resultado.target_coid)

        avaliacao = resultado.persistence_assessment
        # 16
        assert avaliacao.outcome is PersistenceOutcome.RECORDED_CONTINUITY_EVIDENCE
        assert avaliacao.coid == resultado.target_coid

        # 17 — correspondência exata fonte ↔ edge ↔ evidência
        linhagem = avaliacao.evidence_of(PersistenceEvidenceKind.LINEAGE_PARENT)
        assert len(linhagem) == 3
        assert {e.related_coid for e in linhagem} == set(fontes)
        assert {e.reference for e in linhagem} == {str(e) for e in resultado.lineage_edge_ids}
        por_referencia = {e.reference: e.related_coid for e in linhagem}
        for fonte, edge in zip(resultado.source_coids, resultado.lineage_edge_ids, strict=True):
            assert por_referencia[str(edge)] == fonte
            assert resultado.lineage_edge_for(fonte) == edge

        # 18
        saidas = avaliacao.evidence_of(PersistenceEvidenceKind.TRANSFORMATION_OUTPUT)
        assert len(saidas) == 1
        assert saidas[0].reference == str(resultado.transformation_id)

        # 19
        causais = avaliacao.evidence_of(PersistenceEvidenceKind.CAUSAL_EVENT)
        assert {e.reference for e in causais} == {str(e) for e in resultado.causal_event_ids}
    finally:
        _limpar(criados)


# --- 20. Fontes intocadas ---------------------------------------------


def test_ci20_source_census_is_identical_before_and_after():
    clid = uuid.uuid4()
    fontes = _criar_fontes(3, clid=clid)
    criados = list(fontes)
    try:
        antes = _censo(fontes)
        with UnitOfWork() as uow:
            manager, _ = _compor(uow.session)
            resultado = manager.consolidate(source_coids=fontes, declared_losses=["x"])
            uow.commit()
            criados.append(resultado.target_coid)
        assert _censo(fontes) == antes
    finally:
        _limpar(criados)


# --- 21/22/23. Rollback -----------------------------------------------


def test_ci21_rollback_by_omission_leaves_nothing():
    fontes = _criar_fontes(2)
    try:
        objetos_antes = _contar("cognitive_objects")
        edges_antes = _contar("lineage_edges")
        with UnitOfWork() as uow:
            manager, _ = _compor(uow.session)
            resultado = manager.consolidate(source_coids=fontes, declared_losses=["x"])
            # sem uow.commit()
        assert _contar("cognitive_objects") == objetos_antes
        assert _contar("lineage_edges") == edges_antes
        with UnitOfWork() as uow:
            assert (
                ObjectRepository(uow.session).get_by_id(resultado.target_coid, include_deleted=True)
                is None
            )
    finally:
        _limpar(fontes)


def test_ci22_rollback_when_verification_fails(monkeypatch):
    """Verificação falha → nada sobrevive, e nada é reparado.

    A falha é injetada no `PersistenceManager`, que passa a devolver um
    assessment internamente válido mas divergente do recibo — o cenário
    que `PIA-8032` existe para cobrir.
    """
    from app.memory.schemas.persistence import PersistenceAssessment

    clid = uuid.uuid4()
    fontes = _criar_fontes(3, clid=clid)
    try:
        antes = _censo(fontes)
        objetos_antes = _contar("cognitive_objects")
        edges_antes = _contar("lineage_edges")
        registros_antes = _contar("transformation_records")
        eventos_antes = _contar("causal_history_events")
        historias_antes = _contar("causal_histories")

        def _divergente(self, coid):  # noqa: ANN001
            return PersistenceAssessment(
                coid=coid, outcome=PersistenceOutcome.NO_RECORDED_CONTINUITY_EVIDENCE
            )

        monkeypatch.setattr(PersistenceManager, "assess", _divergente)

        with pytest.raises(ConsolidationVerificationError) as exc, UnitOfWork() as uow:
            manager, _ = _compor(uow.session)
            manager.consolidate(source_coids=fontes, declared_losses=["x"])
            uow.commit()
        assert exc.value.code == "PIA-8032"
        monkeypatch.undo()

        assert _contar("cognitive_objects") == objetos_antes, "alvo órfão sobreviveu"
        assert _contar("lineage_edges") == edges_antes, "linhagem parcial sobreviveu"
        assert _contar("transformation_records") == registros_antes
        assert _contar("causal_history_events") == eventos_antes
        assert _contar("causal_histories") == historias_antes

        depois = _censo(fontes)
        assert depois == antes, "fonte foi mutada"
        assert [linha[1] for linha in depois] == [linha[1] for linha in antes]
    finally:
        _limpar(fontes)


def test_ci23_rollback_when_assess_raises(monkeypatch):
    fontes = _criar_fontes(2, clid=uuid.uuid4())
    try:
        antes = _censo(fontes)
        objetos_antes = _contar("cognitive_objects")
        edges_antes = _contar("lineage_edges")
        registros_antes = _contar("transformation_records")

        chamadas = {"n": 0}

        def _falhar(self, coid):  # noqa: ANN001
            chamadas["n"] += 1
            raise RuntimeError("falha injetada em assess")

        monkeypatch.setattr(PersistenceManager, "assess", _falhar)

        with pytest.raises(RuntimeError, match="falha injetada"), UnitOfWork() as uow:
            manager, _ = _compor(uow.session)
            manager.consolidate(source_coids=fontes, declared_losses=["x"])
            uow.commit()
        monkeypatch.undo()

        assert chamadas["n"] > 0, "assess nunca foi alcançado — prova vazia"
        assert _contar("cognitive_objects") == objetos_antes
        assert _contar("lineage_edges") == edges_antes
        assert _contar("transformation_records") == registros_antes
        assert _censo(fontes) == antes
    finally:
        _limpar(fontes)


# --- 24/25. Concorrência ----------------------------------------------


def test_ci24_ci25_two_concurrent_consolidations_produce_distinct_targets():
    """`REPEATED CONSOLIDATION != SAME EVENT` — nenhuma deduplicação por
    conjunto de fontes, nenhum reaproveitamento silencioso de target."""
    fontes = _criar_fontes(2, clid=uuid.uuid4())
    criados = list(fontes)
    resultados: list[uuid.UUID] = []
    erros: list[BaseException] = []
    barreira = threading.Barrier(2, timeout=30)

    def _consolidar() -> None:
        try:
            with UnitOfWork() as uow:
                manager, _ = _compor(uow.session)
                barreira.wait()
                resultado = manager.consolidate(source_coids=fontes, declared_losses=["x"])
                uow.commit()
                resultados.append(resultado.target_coid)
        except BaseException as exc:  # noqa: BLE001
            erros.append(exc)

    threads = [threading.Thread(target=_consolidar) for _ in range(2)]
    try:
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=60)

        assert erros == [], f"consolidação concorrente falhou: {erros}"
        assert len(resultados) == 2
        assert resultados[0] != resultados[1]
        criados.extend(resultados)

        with UnitOfWork() as uow:
            linhagem = LineageRepository(uow.session)
            for alvo in resultados:
                arestas = linhagem.list_parents(alvo)
                assert len(arestas) == 2
                assert {a.relation_type for a in arestas} == {LineageRelation.MERGE}
        for coid in fontes:
            with UnitOfWork() as uow:
                assert ObjectRepository(uow.session).get_by_id(coid).deleted_at is None
    finally:
        _limpar(criados)


# --- 26 a 30. Guardas de regressão ------------------------------------


def test_ci26_no_schema_orm_drift():
    """E4.5 não cria tabela, coluna nem enum persistido.

    Recorte de ruído de harness pelo mesmo critério de `IX5` (E3.7),
    `CHI8` (E3.9) e da E3.4.2: modelos declarados apenas por fixtures de
    teste também se registram no `Base` real durante a coleta.
    """
    import app.cognitive.models  # noqa: F401
    import app.memory.models  # noqa: F401
    import app.orchestration.models  # noqa: F401
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from app.database.base import Base
    from app.database.engine import engine

    with engine.connect() as conexao:
        diferencas = compare_metadata(MigrationContext.configure(conexao), Base.metadata)
    reais = [d for d in diferencas if "test_" not in str(d)]
    assert reais == [], f"schema/ORM drift: {reais}"


def test_ci27_migration_head_is_unchanged_and_single():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    heads = ScriptDirectory.from_config(Config("alembic.ini")).get_heads()
    # Atualizado pela E4.7: a migração `7b2e4c9a15df` cria
    # `accessibility_policies`, entidade persistente autorizada pelo
    # §14 do prompt canônico. O head continua ÚNICO — o que este
    # guarda protege é a ausência de branching, não a imobilidade.
    # Atualizado pela E4.9.5: a migração `9d4f1a7c2be8` cria
    # `erasure_records`, primeira fatia de runtime da E4.9. O head
    # continua ÚNICO — o que este guarda protege é a ausência de
    # branching, não a imobilidade.
    # Atualizado pela E4.9.6: a migração `c8a3f5017e94` cria
    # `retention_policies`, segunda fatia de runtime da E4.9. O head
    # continua ÚNICO — o que este guarda protege é a ausência de
    # branching, não a imobilidade.
    # E4.9.9.d: head atualizado para `d5b31f7a08c4` (governance_rule_id
    # textual). A guarda continua medindo head ÚNICO.
    # ATUALIZADO PELA E4.11: a cabeça passou a ser `e7c25a91f4b3`
    # (validated_experiences). A guarda continua medindo head ÚNICO —
    # só o alvo do único mudou.
    assert tuple(heads) == ("a91d3f7c26be",), f"migration head mudou: {heads}"


def test_ci28_no_new_e4_model_or_table_was_introduced():
    """`NEW PERSISTENT ENTITY = NO` — a E4.5 não acrescenta model ORM."""
    import app.memory.models as memory_models
    from app.database.base import Base

    tabelas_memoria = {
        mapper.local_table.name
        for mapper in Base.registry.mappers
        if mapper.class_.__module__.startswith("app.memory")
    }
    # `accessibility_policies` entra pela E4.7 — ver nota acima.
    # Atualizado pela E4.9.5: `erasure_records` entra como primeira
    # fatia de runtime da E4.9, autorizada pelo prompt canônico. O
    # guarda continua exigindo o conjunto EXATO: nada além do
    # declarado foi introduzido.
    # Atualizado pela E4.9.6: `retention_policies` entra como segunda
    # fatia de runtime da E4.9, autorizada pelo prompt canônico. O
    # guarda continua exigindo o conjunto EXATO.
    assert tabelas_memoria == {
        "memory_domains",
        "memory_domain_memberships",
        "governance_policies",
        "accessibility_policies",
        "erasure_records",
        "retention_policies",
        # E4.9.9.a — três tabelas de aprovação persistente, autorizadas.
        "approval_records",
        "approval_record_targets",
        "approval_record_governance_items",
        # E4.11 — UMA tabela de registro append-only, autorizada. O
        # conjunto continua EXATO: a guarda mede que nada ALÉM do
        # declarado entrou, e é isso que ela sempre protegeu.
        "validated_experiences",
    }, tabelas_memoria
    assert not hasattr(memory_models, "ConsolidationRecord")


def test_ci29_g17_and_md6_boundaries_are_preserved():
    """Nenhum import de `app.cognitive` no código de produção da E4 —
    a fronteira que a porta existe para preservar."""
    import pathlib
    import re

    padrao = re.compile(r"^\s*(from|import)\s+app\.cognitive", re.MULTILINE)
    raiz = pathlib.Path(__file__).resolve().parents[3] / "app"
    ofensores = [
        str(caminho)
        for caminho in raiz.rglob("*.py")
        if "cognitive" not in caminho.parts and padrao.search(caminho.read_text(encoding="utf-8"))
    ]
    assert ofensores == []


@pytest.mark.parametrize(
    "primeiro_import",
    [
        "app.memory.ports.consolidation",
        "app.memory.schemas.consolidation",
        "app.memory.services.consolidation_manager",
    ],
)
def test_ci30_public_imports_work_in_any_order_in_a_clean_interpreter(primeiro_import):
    import subprocess
    import sys

    resultado = subprocess.run(
        [sys.executable, "-c", f"import {primeiro_import}; print('ok')"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert resultado.returncode == 0, resultado.stderr
    assert "ok" in resultado.stdout


def test_ci30b_traceability_s1_can_be_reconstructed_from_its_sources():
    """`S1 ← {M1, M2, M3}` reconstruível pelo patrimônio, sem entidade
    nova — o objetivo inteiro do módulo."""
    fontes = _criar_fontes(3, clid=uuid.uuid4())
    criados = list(fontes)
    try:
        with UnitOfWork() as uow:
            manager, _ = _compor(uow.session)
            resultado = manager.consolidate(source_coids=fontes, declared_losses=["x"])
            uow.commit()
            criados.append(resultado.target_coid)

        with UnitOfWork() as uow:
            por_linhagem = {
                aresta.parent_coid
                for aresta in LineageRepository(uow.session).list_parents(resultado.target_coid)
                if aresta.relation_type is LineageRelation.MERGE
            }
            registro = TransformationRepository(uow.session).get_by_id(resultado.transformation_id)
            por_registro = {uuid.UUID(ref) for ref in registro.input_refs}
        assert por_linhagem == set(fontes)
        assert por_registro == set(fontes)
    finally:
        _limpar(criados)


# ======================================================================
# E4.5.1 — endurecimento da verificação pós-escrita
# ======================================================================


def test_ci451_real_writer_persists_merge_qualifier_on_every_edge():
    """§7.26 — o writer oficial grava `"merge"` minúsculo.

    Confirma contra o banco o token que a verificação passou a exigir.
    Se a E3 algum dia mudar a serialização, é este teste que quebra —
    e é onde a mudança precisa ser discutida.
    """
    from app.memory.schemas.consolidation import LINEAGE_MERGE_QUALIFIER

    fontes = _criar_fontes(3, clid=uuid.uuid4())
    criados = list(fontes)
    try:
        with UnitOfWork() as uow:
            manager, _ = _compor(uow.session)
            resultado = manager.consolidate(source_coids=fontes, declared_losses=["x"])
            uow.commit()
            criados.append(resultado.target_coid)

        with UnitOfWork() as uow:
            gravados = [
                linha[0]
                for linha in uow.session.execute(
                    sa.text("SELECT relation_type FROM lineage_edges WHERE child_coid = :t"),
                    {"t": str(resultado.target_coid)},
                ).all()
            ]
        assert len(gravados) == 3
        assert set(gravados) == {LINEAGE_MERGE_QUALIFIER}

        linhagem = resultado.persistence_assessment.evidence_of(
            PersistenceEvidenceKind.LINEAGE_PARENT
        )
        assert {e.qualifier for e in linhagem} == {LINEAGE_MERGE_QUALIFIER}
    finally:
        _limpar(criados)


def test_ci451_real_writer_persists_transformed_qualifier_on_every_event():
    """§7.27 — o writer oficial grava `"TRANSFORMED"` maiúsculo.

    A capitalização difere da linhagem porque `event_type` não usa
    `values_callable` — assimetria conhecida, preservada e agora
    verificada dos dois lados.
    """
    from app.memory.schemas.consolidation import CAUSAL_TRANSFORMED_QUALIFIER

    fontes = _criar_fontes(2)
    criados = list(fontes)
    try:
        with UnitOfWork() as uow:
            manager, _ = _compor(uow.session)
            resultado = manager.consolidate(source_coids=fontes, declared_losses=["x"])
            uow.commit()
            criados.append(resultado.target_coid)

        with UnitOfWork() as uow:
            gravados = [
                linha[0]
                for linha in uow.session.execute(
                    sa.text(
                        "SELECT e.event_type FROM causal_history_events e "
                        "JOIN causal_histories h ON h.id = e.history_id "
                        "WHERE h.subject_coid = :t"
                    ),
                    {"t": str(resultado.target_coid)},
                ).all()
            ]
        assert gravados == [CAUSAL_TRANSFORMED_QUALIFIER]

        causais = resultado.persistence_assessment.evidence_of(PersistenceEvidenceKind.CAUSAL_EVENT)
        assert {e.qualifier for e in causais} == {CAUSAL_TRANSFORMED_QUALIFIER}
    finally:
        _limpar(criados)


def test_ci451_real_consolidation_remains_valid_after_hardening():
    """§7.28 — o endurecimento não recusa a consolidação legítima.

    Verificação de fim a fim: se a exigência de qualifier estivesse
    errada, é aqui que apareceria.
    """
    clid = uuid.uuid4()
    fontes = _criar_fontes(3, clid=clid)
    criados = list(fontes)
    try:
        with UnitOfWork() as uow:
            manager, _ = _compor(uow.session)
            resultado = manager.consolidate(
                source_coids=fontes,
                declared_losses=["variações de ramo"],
                declared_preservations=["tese central"],
            )
            uow.commit()
            criados.append(resultado.target_coid)

        assert resultado.target_clid == clid
        assert resultado.source_count == 3
        assert (
            resultado.persistence_assessment.outcome
            is PersistenceOutcome.RECORDED_CONTINUITY_EVIDENCE
        )
        with UnitOfWork() as uow:
            registro = TransformationRepository(uow.session).get_by_id(resultado.transformation_id)
            assert registro.transformation_kind is TransformationKind.DERIVATION
    finally:
        _limpar(criados)


@pytest.mark.parametrize("divergencia", ["lineage_qualifier", "causal_qualifier"])
def test_ci451_injected_divergence_after_write_raises_pia_8032_and_rolls_back(
    monkeypatch, divergencia
):
    """§7.29 a §7.31 — divergência injetada **depois** da escrita.

    A injeção troca só o qualifier do assessment, mantendo tudo o mais
    coerente: é o cenário exato dos defeitos A e B, e o que a E4.5
    aceitava em silêncio.
    """
    import dataclasses

    from app.memory.schemas.persistence import PersistenceAssessment

    fontes = _criar_fontes(3, clid=uuid.uuid4())
    try:
        antes = _censo(fontes)
        objetos_antes = _contar("cognitive_objects")
        edges_antes = _contar("lineage_edges")
        registros_antes = _contar("transformation_records")
        eventos_antes = _contar("causal_history_events")
        historias_antes = _contar("causal_histories")

        alvo_kind = (
            PersistenceEvidenceKind.LINEAGE_PARENT
            if divergencia == "lineage_qualifier"
            else PersistenceEvidenceKind.CAUSAL_EVENT
        )
        token_falso = "branch" if divergencia == "lineage_qualifier" else "COMPARED"
        original = PersistenceManager.assess
        chamadas = {"n": 0}

        def _adulterado(self, coid):  # noqa: ANN001
            chamadas["n"] += 1
            avaliacao: PersistenceAssessment = original(self, coid)
            adulterada = tuple(
                dataclasses.replace(e, qualifier=token_falso) if e.kind is alvo_kind else e
                for e in avaliacao.evidence
            )
            return dataclasses.replace(avaliacao, evidence=adulterada)

        monkeypatch.setattr(PersistenceManager, "assess", _adulterado)

        with pytest.raises(ConsolidationVerificationError) as exc, UnitOfWork() as uow:
            manager, _ = _compor(uow.session)
            manager.consolidate(source_coids=fontes, declared_losses=["x"])
            uow.commit()
        assert exc.value.code == "PIA-8032"
        monkeypatch.undo()

        assert chamadas["n"] > 0, "assess nunca foi alcançado — prova vazia"

        # §7.30 — rollback integral
        assert _contar("cognitive_objects") == objetos_antes, "alvo órfão sobreviveu"
        assert _contar("lineage_edges") == edges_antes, "linhagem parcial sobreviveu"
        assert _contar("transformation_records") == registros_antes
        assert _contar("causal_history_events") == eventos_antes
        assert _contar("causal_histories") == historias_antes

        # §7.31 — nenhuma fonte alterada
        depois = _censo(fontes)
        assert depois == antes, "fonte foi mutada"
        assert [linha[1] for linha in depois] == [linha[1] for linha in antes]
    finally:
        _limpar(fontes)


def test_ci451_no_value_error_escapes_the_canonical_path_against_the_real_database():
    """O chamador recebe `PIA-8032`, nunca o `ValueError` do value
    object — mesmo com a divergência vindo do banco real."""
    import dataclasses

    fontes = _criar_fontes(2)
    try:
        original = PersistenceManager.assess

        def _adulterado(self, coid):  # noqa: ANN001
            avaliacao = original(self, coid)
            adulterada = tuple(
                (
                    dataclasses.replace(e, qualifier="branch")
                    if e.kind is PersistenceEvidenceKind.LINEAGE_PARENT
                    else e
                )
                for e in avaliacao.evidence
            )
            return dataclasses.replace(avaliacao, evidence=adulterada)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(PersistenceManager, "assess", _adulterado)
            with UnitOfWork() as uow:
                manager, _ = _compor(uow.session)
                try:
                    manager.consolidate(source_coids=fontes, declared_losses=["x"])
                except ConsolidationVerificationError:
                    pass
                except ValueError as exc:  # pragma: no cover - falha do contrato
                    pytest.fail(f"ValueError cru escapou do caminho canônico: {exc}")
                else:  # pragma: no cover - falha do contrato
                    pytest.fail("divergência de qualifier não foi detectada")
    finally:
        _limpar(fontes)


# ======================================================================
# E4.5.2 — fidelidade pedido ↔ recibo, contra o writer real
# ======================================================================


class _PortaAdulterada:
    """Delega ao writer **real** e adultera só um campo do recibo.

    A adulteração ocorre **depois** de `derive_many()` executar, então o
    patrimônio foi de fato gravado — é isso que torna os testes de
    rollback abaixo provas de desfazimento de escrita real, e não de
    falha anterior à operação.
    """

    def __init__(self, real, *, fontes=None, predecessores=None) -> None:
        self._real = real
        self._fontes = fontes
        self._predecessores = predecessores
        self.chamadas = 0

    def derive_many(self, **kwargs):
        self.chamadas += 1
        recibo = self._real.derive_many(**kwargs)
        substituicoes = {}
        if self._fontes is not None:
            substituicoes["source_coids"] = self._fontes
        if self._predecessores is not None:
            substituicoes["predecessor_event_ids"] = self._predecessores
        return dataclasses.replace(recibo, **substituicoes)


def test_ci452_result_sources_are_exactly_the_canonicalized_request():
    """§10.16 — o writer oficial ecoa a canonicalização do pedido."""
    fontes = _criar_fontes(3, clid=uuid.uuid4())
    criados = list(fontes)
    try:
        with UnitOfWork() as uow:
            manager, _ = _compor(uow.session)
            resultado = manager.consolidate(
                source_coids=[fontes[2], fontes[0], fontes[1]], declared_losses=["x"]
            )
            uow.commit()
            criados.append(resultado.target_coid)
        assert resultado.source_coids == tuple(sorted(fontes))
    finally:
        _limpar(criados)


def test_ci452_result_predecessors_are_exactly_the_requested_tuple():
    """§10.17 e §10.18 — ordem preservada e cada predecessor ligado ao
    seu evento causal."""
    fontes = _criar_fontes(2)
    criados = list(fontes)
    try:
        with UnitOfWork() as uow:
            causal = CausalHistoryManager(CausalHistoryRepository(uow.session))
            ev_a = causal.record(subject_coid=fontes[0], event_type=CausalEventType.CREATED)
            ev_b = causal.record(subject_coid=fontes[1], event_type=CausalEventType.CREATED)
            uow.commit()
            pedidos = [ev_a.id, ev_b.id]

        with UnitOfWork() as uow:
            manager, _ = _compor(uow.session)
            resultado = manager.consolidate(
                source_coids=fontes, declared_losses=["x"], predecessor_event_ids=pedidos
            )
            uow.commit()
            criados.append(resultado.target_coid)

        # Canônico dos dois lados: a E4.5 canonicaliza o pedido por UUID
        # e o writer da E3 faz o mesmo. Assertar `tuple(pedidos)` na
        # ordem em que este teste os listou passaria só quando essa
        # ordem coincidisse com a canônica — metade das execuções, por
        # sorte.
        assert resultado.predecessor_event_ids == tuple(sorted(pedidos))

        with UnitOfWork() as uow:
            gravados = {
                linha[0]
                for linha in uow.session.execute(
                    sa.text(
                        "SELECT e.predecessor_event_id FROM causal_history_events e "
                        "JOIN causal_histories h ON h.id = e.history_id "
                        "WHERE h.subject_coid = :t"
                    ),
                    {"t": str(resultado.target_coid)},
                ).all()
            }
        assert gravados == set(pedidos)
    finally:
        _limpar(criados)


def test_ci452_consolidation_without_predecessors_still_yields_a_root_event():
    """§10.19 — o caminho fiel sem predecessores continua intacto."""
    fontes = _criar_fontes(2)
    criados = list(fontes)
    try:
        with UnitOfWork() as uow:
            manager, _ = _compor(uow.session)
            resultado = manager.consolidate(source_coids=fontes, declared_losses=["x"])
            uow.commit()
            criados.append(resultado.target_coid)

        assert resultado.predecessor_event_ids == ()
        assert len(resultado.causal_event_ids) == 1
        with UnitOfWork() as uow:
            eventos = CausalHistoryManager(CausalHistoryRepository(uow.session)).events_for(
                resultado.target_coid
            )
            assert len(eventos) == 1
            assert eventos[0].predecessor_event_id is None
    finally:
        _limpar(criados)


@pytest.mark.parametrize("campo", ["source_coids", "predecessor_event_ids"])
def test_ci452_tampered_receipt_raises_pia_8032_and_rolls_back_real_writes(campo):
    """§10.20 a §10.25 — o writer real escreve, o recibo é adulterado, e
    o rollback desfaz tudo.

    Também prova que `PersistenceManager.assess()` **não** é chamado:
    a divergência de fidelidade já está demonstrada antes disso.
    """
    fontes = _criar_fontes(3, clid=uuid.uuid4())
    historico = _criar_fontes(1)[0]
    try:
        with UnitOfWork() as uow:
            causal = CausalHistoryManager(CausalHistoryRepository(uow.session))
            ev_fonte = causal.record(subject_coid=fontes[0], event_type=CausalEventType.CREATED)
            ev_estranho = causal.record(subject_coid=historico, event_type=CausalEventType.CREATED)
            uow.commit()
            pedido_predecessor, intruso = ev_fonte.id, ev_estranho.id

        # As fontes-isca são criadas ANTES do censo: elas são objetos
        # commitados legitimamente, e contá-las depois faria o censo
        # acusar "alvo órfão" para linhas que o rollback nunca deveria
        # remover.
        iscas = tuple(sorted(_criar_fontes(3))) if campo == "source_coids" else ()

        antes = _censo(fontes)
        objetos_antes = _contar("cognitive_objects")
        edges_antes = _contar("lineage_edges")
        registros_antes = _contar("transformation_records")
        eventos_antes = _contar("causal_history_events")
        historias_antes = _contar("causal_histories")

        if campo == "source_coids":
            # Mesma CARDINALIDADE das fontes pedidas: o recibo da E3 é um
            # dataclass com invariantes próprios, e `dataclasses.replace`
            # os reexecuta — trocar 3 fontes por 2 seria recusado pelo
            # próprio recibo, provando outra coisa. Aqui a adulteração
            # precisa produzir um recibo **estruturalmente válido** e
            # apenas infiel, que é o defeito sob teste.
            adulteracao = {"fontes": iscas}
            predecessores_pedidos: list[uuid.UUID] = []
        else:
            adulteracao = {"predecessores": (intruso,)}
            predecessores_pedidos = [pedido_predecessor]

        avaliacoes = {"n": 0}
        original_assess = PersistenceManager.assess

        def _contando(self, coid):  # noqa: ANN001
            avaliacoes["n"] += 1
            return original_assess(self, coid)

        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(PersistenceManager, "assess", _contando)
            with pytest.raises(ConsolidationVerificationError) as exc, UnitOfWork() as uow:
                _, porta_real = _compor(uow.session)
                porta = _PortaAdulterada(porta_real, **adulteracao)
                manager = ConsolidationManager(
                    porta, PersistenceManager(ContinuityEvidenceRepository(uow.session))
                )
                manager.consolidate(
                    source_coids=fontes,
                    declared_losses=["x"],
                    predecessor_event_ids=predecessores_pedidos,
                )
                uow.commit()

        assert exc.value.code == "PIA-8032"
        assert porta.chamadas == 1, "o writer real precisa ter executado"
        # §10.25 — divergência já demonstrada não consulta o alvo
        assert avaliacoes["n"] == 0

        # §10.22 — rollback integral das escritas reais
        assert _contar("cognitive_objects") == objetos_antes, "alvo órfão sobreviveu"
        assert _contar("lineage_edges") == edges_antes, "linhagem parcial sobreviveu"
        assert _contar("transformation_records") == registros_antes
        assert _contar("causal_history_events") == eventos_antes
        assert _contar("causal_histories") == historias_antes

        # §10.23 e §10.24 — fontes e predecessor histórico intactos
        assert _censo(fontes) == antes
        with UnitOfWork() as uow:
            sobrevive = uow.session.execute(
                sa.text("SELECT count(*) FROM causal_history_events WHERE id = :e"),
                {"e": str(pedido_predecessor)},
            ).scalar_one()
        assert sobrevive == 1
    finally:
        _limpar([*fontes, historico, *iscas])


def test_ci452_untampered_real_writer_is_still_accepted():
    """§10.26 — o endurecimento não recusa a consolidação legítima."""
    clid = uuid.uuid4()
    fontes = _criar_fontes(2, clid=clid)
    criados = list(fontes)
    try:
        with UnitOfWork() as uow:
            manager, porta_real = _compor(uow.session)
            porta = _PortaAdulterada(porta_real)  # sem adulteração
            manager = ConsolidationManager(
                porta, PersistenceManager(ContinuityEvidenceRepository(uow.session))
            )
            resultado = manager.consolidate(source_coids=fontes, declared_losses=["x"])
            uow.commit()
            criados.append(resultado.target_coid)

        assert resultado.source_coids == tuple(sorted(fontes))
        assert resultado.target_clid == clid
        assert (
            resultado.persistence_assessment.outcome
            is PersistenceOutcome.RECORDED_CONTINUITY_EVIDENCE
        )
    finally:
        _limpar(criados)
