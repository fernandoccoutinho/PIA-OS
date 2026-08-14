"""
E4.2 — testes de integração contra PostgreSQL real.

Cobrem CT8, CT9, CT13–CT17, COUT1–COUT4 e DB1 do §39 do prompt
canônico.

O gate central é `COUT1`: contextos diferentes sobre o mesmo
patrimônio, exigindo

    ΔContext  != 0
    ΔPatrimony = 0

e o gate `DB1` prova, por listener de cursor, que todo o módulo é
estritamente read-only.
"""

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
)
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
from app.memory.errors.exceptions import ContextUnknownDomainReferenceError
from app.memory.repositories.memory_domain_membership_repository import (
    MemoryDomainMembershipRepository,
)
from app.memory.repositories.memory_domain_repository import MemoryDomainRepository
from app.memory.services.context_manager import ContextManager
from app.repositories.unit_of_work import UnitOfWork

_MEMORY_TABLES = ("memory_domain_memberships", "memory_domains")
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
    reason="PostgreSQL real indisponível — E4.2 valida ausência de escrita no banco real.",
)


@pytest.fixture(autouse=True)
def _clean():
    migrations.upgrade("head")
    _truncate()
    yield
    _truncate()


def _truncate() -> None:
    with engine.begin() as conn:
        conn.execute(sa.text(f"TRUNCATE {', '.join(_MEMORY_TABLES + _COGNITIVE_TABLES)} CASCADE"))


def _census(tables: tuple[str, ...]) -> dict[str, list[tuple[Any, ...]]]:
    """Censo linha a linha, coluna a coluna, em ordem determinística."""
    snapshot: dict[str, list[tuple[Any, ...]]] = {}
    with engine.connect() as conn:
        for table in tables:
            columns = sorted(sa.inspect(engine).get_columns(table), key=lambda c: c["name"])
            names = ", ".join(f'"{c["name"]}"' for c in columns)
            rows = conn.execute(sa.text(f"SELECT {names} FROM {table} ORDER BY id")).fetchall()
            snapshot[table] = [tuple(row) for row in rows]
    return snapshot


def _seed() -> dict[str, uuid.UUID]:
    """Patrimônio com linhagem, proveniência, história causal e os
    quatro estados de acessibilidade, mais dois domínios povoados."""
    with UnitOfWork() as uow:
        objects = ObjectRepository(uow.session)
        prov = ProvenanceManager(ProvenanceRepository(uow.session))
        causal = CausalHistoryManager(CausalHistoryRepository(uow.session))
        lineage = LineageRepository(uow.session)
        accessibility = AccessibilityManager(objects)
        domains = MemoryDomainRepository(uow.session)
        memberships = MemoryDomainMembershipRepository(uow.session)

        clid = uuid.uuid4()
        o1 = objects.add(CognitiveObject(clid=clid))
        o2 = objects.add(CognitiveObject(clid=clid))
        o3 = objects.add(CognitiveObject())
        uow.session.flush()

        p = prov.record(
            coid=o1.id,
            source_type=ProvenanceSourceType.HUMAN,
            actor_type=ProvenanceActorType.HUMAN,
            trace_id="e42",
        )
        uow.session.flush()
        lineage.add_edge(parent_coid=o1.id, child_coid=o2.id, relation_type=LineageRelation.BRANCH)
        raiz = causal.record(subject_coid=o1.id, event_type=CausalEventType.CREATED, actor_ref=p.id)
        causal.record(subject_coid=o2.id, event_type=CausalEventType.TRANSFORMED, predecessor=raiz)
        accessibility.transition(o2, AccessibilityState.INACCESSIBLE)
        accessibility.transition(
            o3, AccessibilityState.CAUSALLY_EXTINCT, reason="cenário Broken Glass"
        )

        d1 = domains.add_domain(name="D1")
        d2 = domains.add_domain(name="D2")
        uow.session.flush()
        memberships.add_membership(domain_id=d1.id, coid=o1.id)
        memberships.add_membership(domain_id=d2.id, coid=o3.id)
        uow.commit()

        return {"o1": o1.id, "o2": o2.id, "o3": o3.id, "d1": d1.id, "d2": d2.id, "clid": clid}


# ======================================================================
# CT8 / CT9 — validação de referências de domínio
# ======================================================================


def test_ct8_valid_domain_reference_passes_validation():
    """CT8 — domínios existentes validam, e nada é copiado.

    A validação confirma a **existência** da referência; o contexto
    continua carregando apenas ids. `MemoryDomain` segue sendo fonte
    da verdade sobre si mesmo.
    """
    refs = _seed()
    with UnitOfWork() as uow:
        manager = ContextManager(MemoryDomainRepository(uow.session))
        contexto = manager.build_validated(domain_ids=[refs["d1"], refs["d2"]])

    assert contexto.domain_ids == tuple(sorted({refs["d1"], refs["d2"]}, key=str))
    # Nenhum dado do domínio foi copiado para dentro do contexto.
    assert not hasattr(contexto, "name")
    assert not hasattr(contexto, "domains")


def test_ct9_unknown_domain_reference_reports_the_whole_set():
    """CT9 — referência desconhecida vira erro estruturado.

    Reporta **todos** os ids desconhecidos de uma vez: reportar um por
    vez forçaria N tentativas para descobrir N referências ruins.

    E a distinção diagnóstica é preservada:

        missing domain != cognitive patrimony missing
    """
    refs = _seed()
    ausente_a, ausente_b = uuid.uuid4(), uuid.uuid4()

    with UnitOfWork() as uow:
        manager = ContextManager(MemoryDomainRepository(uow.session))
        with pytest.raises(ContextUnknownDomainReferenceError) as exc:
            manager.build_validated(domain_ids=[refs["d1"], ausente_a, ausente_b])

    assert exc.value.error_code.code == "PIA-8026"
    assert set(exc.value.unknown_domain_ids) == {ausente_a, ausente_b}
    assert refs["d1"] not in exc.value.unknown_domain_ids

    # O patrimônio cognitivo continua íntegro: domínio ausente não diz
    # nada sobre objetos.
    with engine.connect() as conn:
        assert conn.execute(sa.text("SELECT COUNT(*) FROM cognitive_objects")).scalar_one() == 3


# ======================================================================
# DB1 / CT13 / CT14 — zero escritas
# ======================================================================


def test_db1_context_operations_emit_zero_writes():
    """DB1 + CT13 + CT14 — o módulo inteiro é read-only.

    Listener em `before_cursor_execute` contando
    `INSERT/UPDATE/DELETE/TRUNCATE`, mais censo completo das tabelas
    cognitivas **e** de memória. Mesma técnica de `SX3` (E3.8) e
    `IA2` (E3.10): a prova de "read-only" é o SQL efetivamente
    emitido, não a intenção do código.
    """
    refs = _seed()
    todas = _COGNITIVE_TABLES + _MEMORY_TABLES
    censo_antes = _census(todas)

    escritas = {"n": 0}
    import re

    padrao = re.compile(r"^\s*(INSERT|UPDATE|DELETE|TRUNCATE)\b", re.IGNORECASE)

    def _listen(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        if padrao.match(statement):
            escritas["n"] += 1

    event.listen(engine, "before_cursor_execute", _listen)
    try:
        with UnitOfWork() as uow:
            manager = ContextManager(MemoryDomainRepository(uow.session))
            c1 = manager.build_validated(domain_ids=[refs["d1"]], session_id="s1")
            c2 = manager.build_validated(domain_ids=[refs["d2"]], actor_ref="ana")
            manager.validate(c1)
            manager.derive(c1, purpose="derivado")
            manager.build(domain_ids=[refs["d1"], refs["d2"]], purpose="p")
            manager.equivalent(c1, c2)
    finally:
        event.remove(engine, "before_cursor_execute", _listen)

    assert escritas["n"] == 0, "CONTEXT_DOMAIN_WRITE_COUNT deve ser 0"
    assert _census(todas) == censo_antes


# ======================================================================
# CT15–CT17 — contexto não altera membership, acessibilidade nem história
# ======================================================================


def test_ct15_context_does_not_alter_membership():
    """CT15 — `domain in context != object added to domain`."""
    refs = _seed()
    censo_antes = _census(_MEMORY_TABLES)

    with UnitOfWork() as uow:
        manager = ContextManager(MemoryDomainRepository(uow.session))
        manager.build_validated(domain_ids=[refs["d1"], refs["d2"]], actor_ref="ana")

    assert _census(_MEMORY_TABLES) == censo_antes

    with UnitOfWork() as uow:
        memberships = MemoryDomainMembershipRepository(uow.session)
        # Declarar D2 num contexto não colocou o1 em D2.
        assert not memberships.contains(domain_id=refs["d2"], coid=refs["o1"])
        assert memberships.contains(domain_id=refs["d1"], coid=refs["o1"])


def test_ct16_context_does_not_mutate_accessibility():
    """CT16 — `CONTEXT DOES NOT MODIFY ACCESSIBILITY`.

    Contextos são construídos referenciando domínios que contêm
    objetos em estados variados; nenhum estado se move.
    """
    refs = _seed()

    with UnitOfWork() as uow:
        objects = ObjectRepository(uow.session)
        antes = {
            coid: objects.get_by_id(coid).accessibility  # type: ignore[union-attr]
            for coid in (refs["o1"], refs["o2"], refs["o3"])
        }

    with UnitOfWork() as uow:
        manager = ContextManager(MemoryDomainRepository(uow.session))
        contexto = manager.build_validated(domain_ids=[refs["d1"], refs["d2"]], purpose="p")
        manager.derive(contexto, session_id="s2")

    with UnitOfWork() as uow:
        objects = ObjectRepository(uow.session)
        depois = {
            coid: objects.get_by_id(coid).accessibility  # type: ignore[union-attr]
            for coid in (refs["o1"], refs["o2"], refs["o3"])
        }

    assert depois == antes
    assert depois[refs["o2"]] is AccessibilityState.INACCESSIBLE
    assert depois[refs["o3"]] is AccessibilityState.CAUSALLY_EXTINCT


def test_ct17_context_creates_no_provenance_and_no_causal_history():
    """CT17 — perspectiva não é origem nem evento causal.

    Olhar para algo não é um fato sobre esse algo. Criar proveniência
    ou evento causal ao construir contexto falsificaria a história do
    patrimônio com algo que nunca ocorreu.
    """
    refs = _seed()
    with engine.connect() as conn:
        prov_antes = conn.execute(sa.text("SELECT COUNT(*) FROM provenance_records")).scalar_one()
        ev_antes = conn.execute(sa.text("SELECT COUNT(*) FROM causal_history_events")).scalar_one()

    with UnitOfWork() as uow:
        manager = ContextManager(MemoryDomainRepository(uow.session))
        manager.build_validated(
            domain_ids=[refs["d1"]], actor_ref="ana", session_id="s1", purpose="revisão"
        )

    with engine.connect() as conn:
        assert (
            conn.execute(sa.text("SELECT COUNT(*) FROM provenance_records")).scalar_one()
            == prov_antes
        )
        assert (
            conn.execute(sa.text("SELECT COUNT(*) FROM causal_history_events")).scalar_one()
            == ev_antes
        )


# ======================================================================
# COUT — gates fortes
# ======================================================================


def test_cout1_context_delta_without_patrimony_delta():
    """COUT1 — **o gate central da E4.2**.

    ```
    ΔContext  != 0
    ΔPatrimony = 0
    ```

    Dois contextos distintos sobre o mesmo patrimônio fixo; censo das
    sete tabelas cognitivas **e** das duas de memória idêntico byte a
    byte antes e depois.
    """
    refs = _seed()
    todas = _COGNITIVE_TABLES + _MEMORY_TABLES
    censo_antes = _census(todas)

    with UnitOfWork() as uow:
        manager = ContextManager(MemoryDomainRepository(uow.session))
        c1 = manager.build_validated(domain_ids=[refs["d1"]], purpose="operacional")
        c2 = manager.build_validated(domain_ids=[refs["d2"]], purpose="arquivístico")

    assert c1 != c2, "ΔContext != 0"
    assert c1.domain_ids != c2.domain_ids
    assert _census(todas) == censo_antes, "ΔPatrimony deve ser 0"


def test_cout2_different_contexts_preserve_coid_and_clid():
    """COUT2 — identidade e continuidade atravessam qualquer contexto.

    Perspectiva não toca COID nem CLID: são propriedades do
    patrimônio, e patrimônio não depende de contexto.
    """
    refs = _seed()

    with UnitOfWork() as uow:
        manager = ContextManager(MemoryDomainRepository(uow.session))
        for domains in ([refs["d1"]], [refs["d2"]], [refs["d1"], refs["d2"]], []):
            manager.build_validated(domain_ids=domains)

    with UnitOfWork() as uow:
        objects = ObjectRepository(uow.session)
        o1 = objects.get_by_id(refs["o1"])
        o2 = objects.get_by_id(refs["o2"])
        assert o1 is not None and o2 is not None
        assert o1.id == refs["o1"] and o2.id == refs["o2"]
        assert o1.clid == o2.clid == refs["clid"]


def test_cout3_causally_extinct_remains_extinct_under_any_context():
    """COUT3 — Broken Glass sobrevive à mudança de perspectiva.

    Um objeto `CAUSALLY_EXTINCT` continua extinto sob qualquer
    contexto — inclusive um que declare o domínio ao qual ele
    pertence. Contexto muda a vista; não ressuscita distinção.
    """
    refs = _seed()

    with UnitOfWork() as uow:
        manager = ContextManager(MemoryDomainRepository(uow.session))
        manager.build_validated(domain_ids=[refs["d2"]], purpose="arquivo")
        manager.build_validated(domain_ids=[], actor_ref="ana")

    with UnitOfWork() as uow:
        o3 = ObjectRepository(uow.session).get_by_id(refs["o3"])
        assert o3 is not None
        assert o3.accessibility is AccessibilityState.CAUSALLY_EXTINCT


def test_cout4_context_fabricates_no_history():
    """COUT4 — nenhuma história é inventada.

    Nem para domínio desconhecido, nem para contexto vazio, nem para
    contexto com ator e propósito. `MISSING EVIDENCE != AUTHORIZATION
    TO FABRICATE` continua valendo na camada de perspectiva.
    """
    refs = _seed()
    censo_antes = _census(_COGNITIVE_TABLES)

    with UnitOfWork() as uow:
        manager = ContextManager(MemoryDomainRepository(uow.session))
        manager.build_validated(domain_ids=[])
        manager.build_validated(actor_ref="ana", purpose="p", session_id="s")
        with pytest.raises(ContextUnknownDomainReferenceError):
            manager.build_validated(domain_ids=[uuid.uuid4()])

    assert _census(_COGNITIVE_TABLES) == censo_antes

    # E o objeto que existia continua existindo, com sua história.
    with UnitOfWork() as uow:
        eventos = CausalHistoryManager(CausalHistoryRepository(uow.session)).events_for(refs["o1"])
    assert len(eventos) == 1


def test_cout5_memory_context_never_entered_the_sync_envelope():
    """`MEMORY_CONTEXT_SYNC = NONE`.

    Contexto é TRANSIENT por contrato (matriz F da E4.0): não é
    persistido, logo não há o que sincronizar. O envelope da E3
    continua com as sete seções congeladas.
    """
    assert set(SECTION_BY_TABLE) == set(_COGNITIVE_TABLES)
    for tabela in ("memory_contexts", "context_definitions"):
        assert tabela not in SECTION_BY_TABLE
        assert tabela not in sa.inspect(engine).get_table_names(), (
            f"{tabela} não deve existir — MemoryContext é TRANSIENT e "
            "ContextDefinition está DEFERRED"
        )
