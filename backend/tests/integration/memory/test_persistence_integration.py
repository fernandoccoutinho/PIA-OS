"""
E4.4 — testes de integração contra PostgreSQL real.

Cobrem os requisitos que só o patrimônio real demonstra: evidências
efetivamente registradas, ausência de escrita, censo canônico
inalterado e independência de contexto, domínio, policy e
acessibilidade.
"""

import re
import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy import event

from app.cognitive.models.cognitive_object import CognitiveObject
from app.cognitive.models.enums import (
    AccessibilityState,
    CausalEventType,
    LineageRelation,
    ProvenanceActorType,
    ProvenanceSourceType,
    TransformationKind,
)
from app.cognitive.models.transformation_record import TransformationRecord
from app.cognitive.repositories.causal_history_repository import CausalHistoryRepository
from app.cognitive.repositories.lineage_repository import LineageRepository
from app.cognitive.repositories.object_repository import ObjectRepository
from app.cognitive.repositories.provenance_repository import ProvenanceRepository
from app.cognitive.schemas.synchronization import SECTION_BY_TABLE
from app.cognitive.services.accessibility_manager import AccessibilityManager
from app.cognitive.services.causal_history_manager import CausalHistoryManager
from app.cognitive.services.provenance_manager import ProvenanceManager
from app.database import migrations
from app.database.engine import engine
from app.database.health import check_database_health
from app.memory.models.governance_enums import CognitiveOperation, GovernanceEffect
from app.memory.repositories.continuity_evidence_repository import (
    ContinuityEvidenceRepository,
)
from app.memory.repositories.governance_policy_repository import GovernancePolicyRepository
from app.memory.repositories.memory_domain_membership_repository import (
    MemoryDomainMembershipRepository,
)
from app.memory.repositories.memory_domain_repository import MemoryDomainRepository
from app.memory.schemas.governance import GovernanceRule
from app.memory.schemas.persistence import PersistenceEvidenceKind, PersistenceOutcome
from app.memory.services.governance_manager import GovernanceManager
from app.memory.services.persistence_manager import PersistenceManager
from app.repositories.unit_of_work import UnitOfWork

_E4_TABLES = (
    # `accessibility_policies` entra pela E4.7 — nova entidade persistente
    # autorizada pelo §14 do prompt canônico daquele módulo. O guarda do
    # `pi13` continua exigindo o conjunto EXATO de tabelas: o que ele
    # protege é a ausência de tabela NÃO declarada, não a imobilidade do
    # schema entre módulos.
    #
    # Atualizado pela E4.9.5: `erasure_records` entra pelo mesmo
    # critério — primeira fatia de runtime da E4.9, autorizada pelo
    # prompt canônico. As três tabelas proibidas por `pi13`
    # (`persistence_records`, `persistence_assessments`,
    # `memory_items`) continuam ausentes.
    "accessibility_policies",
    "erasure_records",
    "governance_policies",
    "memory_domain_memberships",
    "memory_domains",
)
_COGNITIVE_TABLES = (
    "causal_history_events",
    "causal_histories",
    "provenance_records",
    "relationships",
    "lineage_edges",
    "transformation_records",
    "cognitive_objects",
)


def _available() -> bool:
    return check_database_health().available


pytestmark = pytest.mark.skipif(
    not _available(),
    reason="PostgreSQL real indisponível — E4.4 avalia evidências sobre patrimônio real.",
)


@pytest.fixture(autouse=True)
def _clean():
    migrations.upgrade("head")
    _truncate()
    yield
    _truncate()


def _truncate() -> None:
    with engine.begin() as conn:
        conn.execute(sa.text(f"TRUNCATE {', '.join(_E4_TABLES + _COGNITIVE_TABLES)} CASCADE"))


def _census(tables: tuple[str, ...]) -> dict[str, list[tuple[Any, ...]]]:
    snapshot: dict[str, list[tuple[Any, ...]]] = {}
    with engine.connect() as conn:
        for table in tables:
            columns = sorted(sa.inspect(engine).get_columns(table), key=lambda c: c["name"])
            names = ", ".join(f'"{c["name"]}"' for c in columns)
            rows = conn.execute(sa.text(f"SELECT {names} FROM {table} ORDER BY id")).fetchall()
            snapshot[table] = [tuple(row) for row in rows]
    return snapshot


def _manager(session) -> PersistenceManager:
    return PersistenceManager(ContinuityEvidenceRepository(session))


# ======================================================================
# Requisitos 1–8 — evidências reais
# ======================================================================


def test_pi1_unknown_coid_is_distinct_from_object_without_evidence():
    """Requisito 1: `SUBJECT_NOT_FOUND` != `NO_RECORDED_...`.

    Um COID inexistente sugere erro de referência; um objeto recém-criado
    sem continuidade registrada é fato legítimo. Providências opostas.
    """
    with UnitOfWork() as uow:
        nu = ObjectRepository(uow.session).add(CognitiveObject())
        uow.commit()
        coid_nu = nu.id

    with UnitOfWork() as uow:
        manager = _manager(uow.session)
        ausente = manager.assess(uuid.uuid4())
        vazio = manager.assess(coid_nu)

    assert ausente.outcome is PersistenceOutcome.SUBJECT_NOT_FOUND
    assert vazio.outcome is PersistenceOutcome.NO_RECORDED_CONTINUITY_EVIDENCE
    assert ausente.outcome is not vazio.outcome
    assert ausente.evidence == () and vazio.evidence == ()
    assert ausente.clid is None


def test_pi2_object_without_any_continuity_reports_honestly():
    """Requisito 2: nenhuma evidência é inventada para preencher o vazio.

    ```
    MISSING EVIDENCE != AUTHORIZATION TO FABRICATE HISTORY
    ```
    """
    with UnitOfWork() as uow:
        objeto = ObjectRepository(uow.session).add(CognitiveObject())
        uow.commit()
        coid = objeto.id

    with UnitOfWork() as uow:
        resultado = _manager(uow.session).assess(coid)

    assert resultado.outcome is PersistenceOutcome.NO_RECORDED_CONTINUITY_EVIDENCE
    assert resultado.evidence == ()
    assert resultado.clid is None
    assert resultado.has_recorded_continuity is False


def test_pi3_clid_appears_as_evidence_without_becoming_a_score():
    """Requisito 3: CLID registrado é evidência — e nada além disso."""
    clid = uuid.uuid4()
    with UnitOfWork() as uow:
        objeto = ObjectRepository(uow.session).add(CognitiveObject(clid=clid))
        uow.commit()
        coid = objeto.id

    with UnitOfWork() as uow:
        resultado = _manager(uow.session).assess(coid)

    assert resultado.outcome is PersistenceOutcome.RECORDED_CONTINUITY_EVIDENCE
    assert resultado.clid == clid
    evidencias = resultado.evidence_of(PersistenceEvidenceKind.CLID)
    assert len(evidencias) == 1
    assert evidencias[0].reference == str(clid)
    assert not hasattr(evidencias[0], "score")


def test_pi4_lineage_preserves_direction():
    """Requisito 4: entrada e saída de linhagem com direção correta."""
    with UnitOfWork() as uow:
        objects = ObjectRepository(uow.session)
        lineage = LineageRepository(uow.session)
        pai = objects.add(CognitiveObject())
        meio = objects.add(CognitiveObject())
        filho = objects.add(CognitiveObject())
        uow.session.flush()
        lineage.add_edge(
            parent_coid=pai.id, child_coid=meio.id, relation_type=LineageRelation.BRANCH
        )
        lineage.add_edge(
            parent_coid=meio.id, child_coid=filho.id, relation_type=LineageRelation.DERIVED_FROM
        )
        uow.commit()
        refs = {"pai": pai.id, "meio": meio.id, "filho": filho.id}

    with UnitOfWork() as uow:
        resultado = _manager(uow.session).assess(refs["meio"])

    de_onde_veio = resultado.evidence_of(PersistenceEvidenceKind.LINEAGE_PARENT)
    o_que_derivou = resultado.evidence_of(PersistenceEvidenceKind.LINEAGE_CHILD)

    assert len(de_onde_veio) == 1
    assert de_onde_veio[0].related_coid == refs["pai"]
    assert de_onde_veio[0].qualifier == "branch"
    assert len(o_que_derivou) == 1
    assert o_que_derivou[0].related_coid == refs["filho"]
    assert o_que_derivou[0].qualifier == "derived_from"


def test_pi5_multiple_branches_remain_multiple():
    """Requisito 5: nada escolhe um ramo como "o verdadeiro".

    ```
    EQUIVALENCE != DESTRUCTIVE COLLAPSE
    DIVERGENCE  != INVALIDITY
    ```
    """
    with UnitOfWork() as uow:
        objects = ObjectRepository(uow.session)
        lineage = LineageRepository(uow.session)
        origem = objects.add(CognitiveObject())
        ramos = [objects.add(CognitiveObject()) for _ in range(4)]
        uow.session.flush()
        for ramo in ramos:
            lineage.add_edge(
                parent_coid=origem.id, child_coid=ramo.id, relation_type=LineageRelation.BRANCH
            )
        uow.commit()
        coid, ids_ramos = origem.id, {r.id for r in ramos}

    with UnitOfWork() as uow:
        resultado = _manager(uow.session).assess(coid)

    filhos = resultado.evidence_of(PersistenceEvidenceKind.LINEAGE_CHILD)
    assert len(filhos) == 4
    assert {e.related_coid for e in filhos} == ids_ramos


def test_pi6_transformation_input_and_output_remain_distinct():
    """Requisito 6: citação como entrada != citação como saída."""
    with UnitOfWork() as uow:
        objects = ObjectRepository(uow.session)
        a = objects.add(CognitiveObject())
        b = objects.add(CognitiveObject())
        uow.session.flush()
        uow.session.add(
            TransformationRecord(
                operation_type="derivar",
                transformation_kind=TransformationKind.DERIVATION,
                input_refs=[str(a.id)],
                output_refs=[str(b.id)],
            )
        )
        uow.commit()
        coid_a, coid_b = a.id, b.id

    with UnitOfWork() as uow:
        manager = _manager(uow.session)
        de_a = manager.assess(coid_a)
        de_b = manager.assess(coid_b)

    assert len(de_a.evidence_of(PersistenceEvidenceKind.TRANSFORMATION_INPUT)) == 1
    assert de_a.evidence_of(PersistenceEvidenceKind.TRANSFORMATION_OUTPUT) == ()
    assert len(de_b.evidence_of(PersistenceEvidenceKind.TRANSFORMATION_OUTPUT)) == 1
    assert de_b.evidence_of(PersistenceEvidenceKind.TRANSFORMATION_INPUT) == ()


def test_pi7_causal_events_appear_by_reference():
    """Requisito 7: eventos aparecem por referência, nunca como ORM."""
    with UnitOfWork() as uow:
        objects = ObjectRepository(uow.session)
        causal = CausalHistoryManager(CausalHistoryRepository(uow.session))
        objeto = objects.add(CognitiveObject())
        uow.session.flush()
        raiz = causal.record(subject_coid=objeto.id, event_type=CausalEventType.CREATED)
        causal.record(subject_coid=objeto.id, event_type=CausalEventType.ACCESSED, predecessor=raiz)
        uow.commit()
        coid = objeto.id

    with UnitOfWork() as uow:
        resultado = _manager(uow.session).assess(coid)

    eventos = resultado.evidence_of(PersistenceEvidenceKind.CAUSAL_EVENT)
    assert len(eventos) == 2
    # O `qualifier` carrega o valor **como a E3 o persistiu**, sem
    # normalização. E a E3 é inconsistente entre tabelas: `event_type`
    # (E3.9) declara `SAEnum(...)` sem `values_callable` e grava o NOME
    # do membro ("CREATED"), enquanto `relation_type` (E3.3) usa
    # `values_callable` e grava o `.value` ("branch") — ver `pi17`.
    #
    # E4.4 reporta o que está gravado. Normalizar aqui inventaria uma
    # convenção que o banco não tem e esconderia um fato da E3.
    assert {e.qualifier for e in eventos} == {"CREATED", "ACCESSED"}
    for evidencia in eventos:
        assert isinstance(evidencia.reference, str)
        assert not hasattr(evidencia, "_sa_instance_state")


def test_pi8_absent_causal_history_creates_no_history():
    """Requisito 8: ler nunca cria. Zero eventos antes e depois."""
    with UnitOfWork() as uow:
        objeto = ObjectRepository(uow.session).add(CognitiveObject(clid=uuid.uuid4()))
        uow.commit()
        coid = objeto.id

    with engine.connect() as conn:
        antes = conn.execute(sa.text("SELECT COUNT(*) FROM causal_history_events")).scalar_one()
        historias_antes = conn.execute(
            sa.text("SELECT COUNT(*) FROM causal_histories")
        ).scalar_one()

    with UnitOfWork() as uow:
        resultado = _manager(uow.session).assess(coid)

    assert resultado.evidence_of(PersistenceEvidenceKind.CAUSAL_EVENT) == ()
    with engine.connect() as conn:
        assert (
            conn.execute(sa.text("SELECT COUNT(*) FROM causal_history_events")).scalar_one()
            == antes
        )
        assert (
            conn.execute(sa.text("SELECT COUNT(*) FROM causal_histories")).scalar_one()
            == historias_antes
        )


# ======================================================================
# Requisitos 13–14 — read-only comprovado
# ======================================================================


def test_pi9_assessment_emits_no_writes_and_leaves_the_census_intact():
    """Requisitos 13 e 14: `DATABASE_WRITES_DURING_ASSESSMENT = 0`.

    Listener de cursor contando escritas mais censo das dez tabelas —
    a prova é o SQL efetivamente emitido, não a intenção do código.
    Mesma técnica de `SX3` (E3.8), `IA2` (E3.10) e `DB1` (E4.2).
    """
    refs = _seed_rich_patrimony()
    todas = _COGNITIVE_TABLES + _E4_TABLES
    censo_antes = _census(todas)

    escritas = {"n": 0}
    padrao = re.compile(r"^\s*(INSERT|UPDATE|DELETE|TRUNCATE)\b", re.IGNORECASE)

    def _listen(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        if padrao.match(statement):
            escritas["n"] += 1

    event.listen(engine, "before_cursor_execute", _listen)
    try:
        with UnitOfWork() as uow:
            manager = _manager(uow.session)
            for coid in (refs["o1"], refs["o2"], refs["o3"], uuid.uuid4()):
                manager.assess(coid)
    finally:
        event.remove(engine, "before_cursor_execute", _listen)

    assert escritas["n"] == 0, "DATABASE_WRITES_DURING_ASSESSMENT deve ser 0"
    assert _census(todas) == censo_antes


def _seed_rich_patrimony() -> dict[str, uuid.UUID]:
    """Patrimônio com as quatro fontes de continuidade povoadas."""
    with UnitOfWork() as uow:
        objects = ObjectRepository(uow.session)
        lineage = LineageRepository(uow.session)
        causal = CausalHistoryManager(CausalHistoryRepository(uow.session))
        prov = ProvenanceManager(ProvenanceRepository(uow.session))

        clid = uuid.uuid4()
        o1 = objects.add(CognitiveObject(clid=clid))
        o2 = objects.add(CognitiveObject(clid=clid))
        o3 = objects.add(CognitiveObject())
        uow.session.flush()

        prov.record(
            coid=o1.id,
            source_type=ProvenanceSourceType.HUMAN,
            actor_type=ProvenanceActorType.HUMAN,
            trace_id="e44",
        )
        lineage.add_edge(parent_coid=o1.id, child_coid=o2.id, relation_type=LineageRelation.BRANCH)
        uow.session.add(
            TransformationRecord(
                operation_type="derivar",
                transformation_kind=TransformationKind.DERIVATION,
                input_refs=[str(o1.id)],
                output_refs=[str(o2.id)],
            )
        )
        causal.record(subject_coid=o1.id, event_type=CausalEventType.CREATED)
        uow.commit()
        return {"o1": o1.id, "o2": o2.id, "o3": o3.id, "clid": clid}


# ======================================================================
# Requisitos 15–18 — independência
# ======================================================================


def test_pi10_context_domain_policy_and_accessibility_do_not_change_the_assessment():
    """Requisitos 15–18 num único cenário.

    ```
    CONTEXT CHANGES VIEW
    CONTEXT DOES NOT CHANGE PERSISTENCE

    GOVERNANCE MUST NOT REWRITE PERSISTENCE
    ```

    Domínio, membership, policy e `AccessibilityState` mudam entre as
    duas avaliações; o resultado não pode se mexer. E o contexto sequer
    entra: `assess()` só recebe um COID.
    """
    refs = _seed_rich_patrimony()

    with UnitOfWork() as uow:
        antes = _manager(uow.session).assess(refs["o2"])

    # Muda tudo o que não é continuidade.
    with UnitOfWork() as uow:
        dominio = MemoryDomainRepository(uow.session).add_domain(name="D1")
        uow.session.flush()
        MemoryDomainMembershipRepository(uow.session).add_membership(
            domain_id=dominio.id, coid=refs["o2"]
        )
        GovernanceManager(GovernancePolicyRepository(uow.session)).publish_version(
            policy_key="p",
            rules=(
                GovernanceRule(
                    rule_id="nega-tudo",
                    effect=GovernanceEffect.DENY,
                    operations=frozenset({CognitiveOperation.READ}),
                ),
            ),
        )
        objects = ObjectRepository(uow.session)
        alvo = objects.get_by_id(refs["o2"])
        AccessibilityManager(objects).transition(alvo, AccessibilityState.INACCESSIBLE)
        uow.commit()

    with UnitOfWork() as uow:
        depois = _manager(uow.session).assess(refs["o2"])

    assert depois == antes, "persistência não pode variar com contexto/domínio/policy/acesso"
    assert depois.outcome is PersistenceOutcome.RECORDED_CONTINUITY_EVIDENCE


def test_pi11_causally_extinct_is_not_read_as_continuity_created_or_destroyed():
    """Requisito 18: mudar `AccessibilityState` não cria nem destrói
    continuidade.

    ```
    DISTINCTION EXTINCTION != HISTORICAL ERASURE
    ```
    """
    refs = _seed_rich_patrimony()
    with UnitOfWork() as uow:
        antes = _manager(uow.session).assess(refs["o1"])

    with UnitOfWork() as uow:
        objects = ObjectRepository(uow.session)
        alvo = objects.get_by_id(refs["o1"])
        AccessibilityManager(objects).transition(
            alvo, AccessibilityState.CAUSALLY_EXTINCT, reason="broken glass"
        )
        uow.commit()

    with UnitOfWork() as uow:
        depois = _manager(uow.session).assess(refs["o1"])

    assert depois == antes
    assert depois.evidence == antes.evidence
    assert depois.outcome is PersistenceOutcome.RECORDED_CONTINUITY_EVIDENCE


def test_pi12_assessment_is_deterministic_across_repeated_reads():
    """Requisito 9 no banco real: leituras repetidas, resultado idêntico."""
    refs = _seed_rich_patrimony()
    with UnitOfWork() as uow:
        manager = _manager(uow.session)
        primeira = manager.assess(refs["o1"])
        segunda = manager.assess(refs["o1"])
    with UnitOfWork() as uow:
        terceira = _manager(uow.session).assess(refs["o1"])

    assert primeira == segunda == terceira
    assert hash(primeira) == hash(terceira)


# ======================================================================
# Requisitos 20–22 — fronteiras estruturais
# ======================================================================


def test_pi13_no_new_table_and_no_new_migration():
    """Requisito 20: E4.4 não criou tabela nem migração.

    Lido do schema real, não do modelo.
    """
    tabelas = set(sa.inspect(engine).get_table_names())
    esperadas = set(_COGNITIVE_TABLES) | set(_E4_TABLES) | {"alembic_version"}
    assert tabelas == esperadas, f"tabela inesperada: {tabelas - esperadas}"
    for proibida in ("persistence_records", "persistence_assessments", "memory_items"):
        assert proibida not in tabelas


def test_pi14_e3_sync_envelope_still_has_exactly_seven_sections():
    """Requisito 22."""
    assert set(SECTION_BY_TABLE) == set(_COGNITIVE_TABLES)
    assert len(SECTION_BY_TABLE) == 7


def test_pi15_soft_deleted_object_is_still_assessed():
    """**Corrigido em E4.4.1.** Soft delete não é inexistência.

    A versão anterior deste teste codificava o defeito: afirmava que um
    objeto com exclusão lógica é `SUBJECT_NOT_FOUND`, justificando com
    a "política de leitura da E3.1.1". A justificativa estava errada —
    a E3.1.1 filtra por padrão nas **listagens** e oferece
    `include_deleted=True` precisamente para **consumidores de
    auditoria**, que é o que um avaliador de continuidade é.

    ```
    SOFT_DELETED != NEVER EXISTED
    SOFT_DELETED != SUBJECT_NOT_FOUND
    SOFT_DELETED != HISTORICAL ERASURE
    ```
    """
    with UnitOfWork() as uow:
        objeto = ObjectRepository(uow.session).add(CognitiveObject(clid=uuid.uuid4()))
        uow.commit()
        coid = objeto.id

    with UnitOfWork() as uow:
        assert (
            _manager(uow.session).assess(coid).outcome
            is PersistenceOutcome.RECORDED_CONTINUITY_EVIDENCE
        )

    with engine.begin() as conn:
        conn.execute(
            sa.text("UPDATE cognitive_objects SET deleted_at = now() WHERE id = :c"),
            {"c": coid},
        )

    with UnitOfWork() as uow:
        resultado = _manager(uow.session).assess(coid)
    assert resultado.outcome is PersistenceOutcome.RECORDED_CONTINUITY_EVIDENCE
    assert resultado.subject_deleted is True
    assert resultado.evidence != ()
    assert resultado.clid is not None


def test_pi16_provenance_alone_is_not_continuity():
    """Proveniência não é reclassificada como continuidade.

    Um objeto com proveniência registrada e mais nada continua sem
    evidência de continuidade — proveniência responde "de onde veio",
    não "atravessou o quê".
    """
    with UnitOfWork() as uow:
        objeto = ObjectRepository(uow.session).add(CognitiveObject())
        uow.session.flush()
        ProvenanceManager(ProvenanceRepository(uow.session)).record(
            coid=objeto.id,
            source_type=ProvenanceSourceType.HUMAN,
            actor_type=ProvenanceActorType.HUMAN,
            trace_id="so-proveniencia",
        )
        uow.commit()
        coid = objeto.id

    with engine.connect() as conn:
        assert (
            conn.execute(
                sa.text("SELECT COUNT(*) FROM provenance_records WHERE coid = :c"), {"c": coid}
            ).scalar_one()
            == 1
        )

    with UnitOfWork() as uow:
        resultado = _manager(uow.session).assess(coid)

    assert resultado.outcome is PersistenceOutcome.NO_RECORDED_CONTINUITY_EVIDENCE
    assert resultado.evidence == ()


def test_pi17_e3_persists_enums_with_two_different_conventions():
    """**Observação sobre a E3, reproduzida e não corrigida.**

    `lineage_edges.relation_type` (E3.3) declara `values_callable` e
    grava o `.value` do membro; `causal_history_events.event_type`
    (E3.9) não declara, e grava o **nome**. Duas convenções para o
    mesmo problema, no mesmo patrimônio.

    Não é defeito que bloqueie a E4.4 — o valor é estável dos dois
    lados, e este módulo o reporta como está. Mas é uma armadilha para
    qualquer consumidor futuro que assuma uma convenção só, e por isso
    fica registrada em teste em vez de virar conhecimento tácito.

    **Não corrigida aqui**: alterar `app/cognitive/` acionaria a Stop
    Condition 2 e 13 deste módulo. O lugar de revisá-la é um corretivo
    da E3.
    """
    with UnitOfWork() as uow:
        objects = ObjectRepository(uow.session)
        lineage = LineageRepository(uow.session)
        causal = CausalHistoryManager(CausalHistoryRepository(uow.session))
        a = objects.add(CognitiveObject())
        b = objects.add(CognitiveObject())
        uow.session.flush()
        lineage.add_edge(parent_coid=a.id, child_coid=b.id, relation_type=LineageRelation.BRANCH)
        causal.record(subject_coid=a.id, event_type=CausalEventType.CREATED)
        uow.commit()

    with engine.connect() as conn:
        relacao = conn.execute(
            sa.text("SELECT DISTINCT relation_type FROM lineage_edges")
        ).scalar_one()
        evento = conn.execute(
            sa.text("SELECT DISTINCT event_type FROM causal_history_events")
        ).scalar_one()

    assert relacao == LineageRelation.BRANCH.value == "branch", "E3.3 grava o .value"
    assert evento == CausalEventType.CREATED.name == "CREATED", "E3.9 grava o NOME"
    assert (
        relacao.islower() and evento.isupper()
    ), "as duas convenções coexistem no mesmo patrimônio — armadilha registrada"


# ======================================================================
# E4.4.1 — soft delete não é inexistência
# ======================================================================


def _soft_delete(coid: uuid.UUID) -> None:
    """Marca exclusão lógica por SQL direto.

    Deliberadamente **não** altera `deleted_at` por nenhum caminho de
    domínio: o corretivo proíbe recuperar objeto apagado ou mexer em
    `deleted_at` como funcionalidade. Aqui é apenas montagem de
    cenário.
    """
    with engine.begin() as conn:
        conn.execute(
            sa.text("UPDATE cognitive_objects SET deleted_at = now() WHERE id = :c"),
            {"c": coid},
        )


def test_pi18_unknown_coid_is_still_subject_not_found():
    """(1) `SUBJECT_NOT_FOUND` continua significando "não há linha".

    A correção alarga o que é avaliado; não pode alargar o que é
    encontrado.
    """
    with UnitOfWork() as uow:
        resultado = _manager(uow.session).assess(uuid.uuid4())
    assert resultado.outcome is PersistenceOutcome.SUBJECT_NOT_FOUND
    assert resultado.subject_deleted is False
    assert resultado.evidence == ()


def test_pi19_soft_deleted_object_keeps_every_kind_of_evidence():
    """(2)–(6) num único cenário, com as quatro fontes povoadas.

    CLID, linhagem (pai **e** filho), transformação (entrada **e**
    saída) e história causal continuam visíveis depois da exclusão
    lógica — e o resultado é idêntico ao de antes, exceto pelo
    descritor.
    """
    with UnitOfWork() as uow:
        objects = ObjectRepository(uow.session)
        lineage = LineageRepository(uow.session)
        causal = CausalHistoryManager(CausalHistoryRepository(uow.session))

        clid = uuid.uuid4()
        pai = objects.add(CognitiveObject())
        alvo = objects.add(CognitiveObject(clid=clid))
        filho = objects.add(CognitiveObject())
        uow.session.flush()
        lineage.add_edge(
            parent_coid=pai.id, child_coid=alvo.id, relation_type=LineageRelation.BRANCH
        )
        lineage.add_edge(
            parent_coid=alvo.id, child_coid=filho.id, relation_type=LineageRelation.DERIVED_FROM
        )
        uow.session.add(
            TransformationRecord(
                operation_type="entrada",
                transformation_kind=TransformationKind.DERIVATION,
                input_refs=[str(alvo.id)],
                output_refs=[],
            )
        )
        uow.session.add(
            TransformationRecord(
                operation_type="saida",
                transformation_kind=TransformationKind.DERIVATION,
                input_refs=[],
                output_refs=[str(alvo.id)],
            )
        )
        causal.record(subject_coid=alvo.id, event_type=CausalEventType.CREATED)
        uow.commit()
        coid = alvo.id

    with UnitOfWork() as uow:
        antes = _manager(uow.session).assess(coid)

    _soft_delete(coid)

    with UnitOfWork() as uow:
        depois = _manager(uow.session).assess(coid)

    assert depois.outcome is PersistenceOutcome.RECORDED_CONTINUITY_EVIDENCE
    assert depois.subject_deleted is True
    assert antes.subject_deleted is False

    # (3) CLID mantido
    assert depois.clid == clid
    assert len(depois.evidence_of(PersistenceEvidenceKind.CLID)) == 1
    # (4) linhagem, nas duas direções
    assert len(depois.evidence_of(PersistenceEvidenceKind.LINEAGE_PARENT)) == 1
    assert len(depois.evidence_of(PersistenceEvidenceKind.LINEAGE_CHILD)) == 1
    # (5) transformação, nas duas direções
    assert len(depois.evidence_of(PersistenceEvidenceKind.TRANSFORMATION_INPUT)) == 1
    assert len(depois.evidence_of(PersistenceEvidenceKind.TRANSFORMATION_OUTPUT)) == 1
    # (6) história causal
    assert len(depois.evidence_of(PersistenceEvidenceKind.CAUSAL_EVENT)) == 1

    # Só o descritor mudou — a continuidade registrada é a mesma.
    assert depois.evidence == antes.evidence


def test_pi20_soft_deleted_without_continuity_is_still_not_subject_not_found():
    """Objeto soft-deleted **sem** evidência continua distinguível de
    inexistente — os três resultados seguem separados."""
    with UnitOfWork() as uow:
        objeto = ObjectRepository(uow.session).add(CognitiveObject())
        uow.commit()
        coid = objeto.id
    _soft_delete(coid)

    with UnitOfWork() as uow:
        resultado = _manager(uow.session).assess(coid)

    assert resultado.outcome is PersistenceOutcome.NO_RECORDED_CONTINUITY_EVIDENCE
    assert resultado.subject_deleted is True
    assert resultado.outcome is not PersistenceOutcome.SUBJECT_NOT_FOUND


def test_pi21_assessing_a_soft_deleted_object_writes_nothing():
    """(21) A avaliação continua read-only — inclusive no caminho novo.

    Em particular, nada "recupera" o objeto: `deleted_at` fica como
    está.
    """
    with UnitOfWork() as uow:
        objeto = ObjectRepository(uow.session).add(CognitiveObject(clid=uuid.uuid4()))
        uow.commit()
        coid = objeto.id
    _soft_delete(coid)

    todas = _COGNITIVE_TABLES + _E4_TABLES
    censo_antes = _census(todas)

    escritas = {"n": 0}
    padrao = re.compile(r"^\s*(INSERT|UPDATE|DELETE|TRUNCATE)\b", re.IGNORECASE)

    def _listen(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        if padrao.match(statement):
            escritas["n"] += 1

    event.listen(engine, "before_cursor_execute", _listen)
    try:
        with UnitOfWork() as uow:
            _manager(uow.session).assess(coid)
    finally:
        event.remove(engine, "before_cursor_execute", _listen)

    assert escritas["n"] == 0
    assert _census(todas) == censo_antes
    with engine.connect() as conn:
        ainda_apagado = conn.execute(
            sa.text("SELECT deleted_at IS NOT NULL FROM cognitive_objects WHERE id = :c"),
            {"c": coid},
        ).scalar_one()
    assert ainda_apagado is True, "a avaliação não pode recuperar objeto apagado"


def test_pi22_assessments_from_the_manager_remain_valid_under_the_new_invariants():
    """(20) Tudo que `assess()` produz continua construtível.

    Se algum caminho do manager montasse um assessment incoerente com
    os invariantes novos, `__post_init__` o recusaria aqui.
    """
    refs = _seed_rich_patrimony()
    _soft_delete(refs["o2"])

    with UnitOfWork() as uow:
        manager = _manager(uow.session)
        resultados = [
            manager.assess(refs["o1"]),
            manager.assess(refs["o2"]),
            manager.assess(refs["o3"]),
            manager.assess(uuid.uuid4()),
        ]

    for resultado in resultados:
        assert isinstance(hash(resultado), int)
        clids = resultado.evidence_of(PersistenceEvidenceKind.CLID)
        assert len(clids) == (1 if resultado.clid is not None else 0)
        if resultado.clid is not None:
            assert clids[0].reference == str(resultado.clid)
        for evidencia in resultado.evidence:
            assert uuid.UUID(evidencia.reference)
