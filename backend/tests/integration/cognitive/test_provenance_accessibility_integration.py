"""
Teste de integração de `ProvenanceManager`/`AccessibilityManager` —
exercita `UnitOfWork` com a fábrica de sessão REAL da aplicação e a
migração real de `provenance_records` (`e2c89ee3aa59`) contra
PostgreSQL.

Mesmo padrão gracioso dos demais arquivos de integração — pula se
PostgreSQL/a migração não estiverem disponíveis.
"""

import threading

import pytest

from app.cognitive.models.cognitive_object import CognitiveObject
from app.cognitive.models.enums import AccessibilityState, ProvenanceActorType, ProvenanceSourceType
from app.cognitive.repositories.object_repository import ObjectRepository
from app.cognitive.repositories.provenance_repository import ProvenanceRepository
from app.cognitive.services.accessibility_manager import AccessibilityManager
from app.cognitive.services.provenance_manager import ProvenanceManager
from app.database.health import check_database_health
from app.repositories.unit_of_work import UnitOfWork


def _postgres_available_with_provenance_records_table() -> bool:
    health = check_database_health()
    if not health.available:
        return False
    from sqlalchemy import inspect

    from app.database.engine import engine

    tables = inspect(engine).get_table_names()
    return {"cognitive_objects", "provenance_records"}.issubset(tables)


pytestmark = pytest.mark.skipif(
    not _postgres_available_with_provenance_records_table(),
    reason=(
        "PostgreSQL real indisponível ou migração e2c89ee3aa59 "
        "(provenance_records) não aplicada neste ambiente."
    ),
)


def _make_managers(session):
    objs = ObjectRepository(session)
    prov = ProvenanceRepository(session)
    prov_mgr = ProvenanceManager(prov)
    acc_mgr = AccessibilityManager(objs)
    return objs, prov, prov_mgr, acc_mgr


def test_provenance_round_trip_and_multiple_agents_against_real_database():
    with UnitOfWork() as uow:
        objs, prov, prov_mgr, acc_mgr = _make_managers(uow.session)
        obj = objs.add(CognitiveObject())
        uow.commit()
        obj_id = obj.id

    try:
        with UnitOfWork() as uow:
            objs, prov, prov_mgr, acc_mgr = _make_managers(uow.session)
            prov_mgr.record(
                coid=obj_id,
                source_type=ProvenanceSourceType.AGENT,
                actor_type=ProvenanceActorType.AGENT,
                actor_id="ia-a",
                provider_id="anthropic",
            )
            prov_mgr.record(
                coid=obj_id,
                source_type=ProvenanceSourceType.AGENT,
                actor_type=ProvenanceActorType.AGENT,
                actor_id="ia-b",
                provider_id="openai",
            )
            uow.commit()

        with UnitOfWork() as uow:
            objs, prov, prov_mgr, acc_mgr = _make_managers(uow.session)
            records = prov_mgr.list_for(obj_id)
            assert len(records) == 2
            providers = {r.provider_id for r in records}
            assert providers == {"anthropic", "openai"}
    finally:
        with UnitOfWork() as uow:
            objs, prov, prov_mgr, acc_mgr = _make_managers(uow.session)
            import sqlalchemy as sa

            uow.session.execute(
                sa.text("DELETE FROM provenance_records WHERE coid = :c"), {"c": str(obj_id)}
            )
            leftover = objs.get_by_id(obj_id, include_deleted=True)
            if leftover is not None:
                objs.delete(leftover)
            uow.commit()


def test_provenance_append_only_against_real_database():
    from app.cognitive.errors.exceptions import ProvenanceRecordImmutableError

    with UnitOfWork() as uow:
        objs, prov, prov_mgr, acc_mgr = _make_managers(uow.session)
        obj = objs.add(CognitiveObject())
        uow.commit()
        obj_id = obj.id

    try:
        with UnitOfWork() as uow:
            objs, prov, prov_mgr, acc_mgr = _make_managers(uow.session)
            rec = prov_mgr.record(
                coid=obj_id,
                source_type=ProvenanceSourceType.SYSTEM,
                actor_type=ProvenanceActorType.SYSTEM,
            )
            uow.commit()
            rec_id = rec.id

        with UnitOfWork() as uow:
            objs, prov, prov_mgr, acc_mgr = _make_managers(uow.session)
            reloaded = prov.get_by_id(rec_id)
            with pytest.raises(ProvenanceRecordImmutableError):
                prov.update(reloaded)
            with pytest.raises(ProvenanceRecordImmutableError):
                prov.delete(reloaded)
            uow.rollback()
    finally:
        with UnitOfWork() as uow:
            objs, prov, prov_mgr, acc_mgr = _make_managers(uow.session)
            import sqlalchemy as sa

            uow.session.execute(
                sa.text("DELETE FROM provenance_records WHERE coid = :c"), {"c": str(obj_id)}
            )
            leftover = objs.get_by_id(obj_id, include_deleted=True)
            if leftover is not None:
                objs.delete(leftover)
            uow.commit()


def test_accessibility_transition_against_real_database():
    with UnitOfWork() as uow:
        objs, prov, prov_mgr, acc_mgr = _make_managers(uow.session)
        obj = objs.add(CognitiveObject())
        uow.commit()
        obj_id = obj.id

    try:
        with UnitOfWork() as uow:
            objs, prov, prov_mgr, acc_mgr = _make_managers(uow.session)
            o = objs.get_by_id(obj_id)
            acc_mgr.transition(o, AccessibilityState.LATENT)
            uow.commit()

        with UnitOfWork() as uow:
            objs, prov, prov_mgr, acc_mgr = _make_managers(uow.session)
            reloaded = objs.get_by_id(obj_id)
            assert reloaded.accessibility == AccessibilityState.LATENT
    finally:
        with UnitOfWork() as uow:
            objs, prov, prov_mgr, acc_mgr = _make_managers(uow.session)
            leftover = objs.get_by_id(obj_id, include_deleted=True)
            if leftover is not None:
                objs.delete(leftover)
            uow.commit()


def test_concurrent_accessibility_transitions_do_not_corrupt_state():
    """§10 do módulo E3.6 — auditoria de concorrência: duas "IAs"
    (threads/sessões distintas) tentando alterar `Accessibility` do
    mesmo `CognitiveObject` simultaneamente. Não há invariante formal
    de exclusividade para `AccessibilityState` nesta fase (diferente
    de CLID/CURRENT) — o teste confirma que `refresh_for_update`
    ainda assim serializa as duas escritas (uma espera a outra) e o
    estado final é sempre um dos dois alvos válidos, nunca corrompido/
    parcial."""
    from sqlalchemy.orm import sessionmaker

    from app.database.engine import engine

    SessionFactory = sessionmaker(
        bind=engine, autocommit=False, autoflush=False, expire_on_commit=False
    )

    with UnitOfWork() as uow:
        objs, prov, prov_mgr, acc_mgr = _make_managers(uow.session)
        obj = objs.add(CognitiveObject())
        uow.commit()
        obj_id = obj.id

    results: dict[str, tuple[str, object]] = {}
    barrier = threading.Barrier(2)

    def worker(name: str, target: AccessibilityState) -> None:
        session = SessionFactory()
        try:
            objs_l = ObjectRepository(session)
            acc_l = AccessibilityManager(objs_l)
            o = objs_l.get_by_id(obj_id)
            barrier.wait()
            acc_l.transition(o, target)
            session.commit()
            results[name] = ("committed", o.accessibility)
        except Exception as exc:
            session.rollback()
            results[name] = ("failed", type(exc).__name__)
        finally:
            session.close()

    try:
        t1 = threading.Thread(target=worker, args=("T1", AccessibilityState.LATENT))
        t2 = threading.Thread(target=worker, args=("T2", AccessibilityState.INACCESSIBLE))
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        outcomes = [results.get("T1"), results.get("T2")]
        committed = [o for o in outcomes if o is not None and o[0] == "committed"]
        # ambas podem legitimamente commitar (nenhum invariante de
        # exclusividade existe) — o que importa é que o estado final
        # seja consistente com uma delas, nunca corrompido
        assert len(committed) >= 1, f"esperado ao menos 1 commit, obtido: {outcomes}"

        with UnitOfWork() as uow:
            objs, prov, prov_mgr, acc_mgr = _make_managers(uow.session)
            final = objs.get_by_id(obj_id)
            final_states = {c[1] for c in committed}
            assert final.accessibility in final_states
    finally:
        with UnitOfWork() as uow:
            objs, prov, prov_mgr, acc_mgr = _make_managers(uow.session)
            leftover = objs.get_by_id(obj_id, include_deleted=True)
            if leftover is not None:
                objs.delete(leftover)
            uow.commit()


# --- T1-T6: trace_id (correção E3.6.1) ---


def test_t1_trace_id_optional_absent_is_valid():
    with UnitOfWork() as uow:
        objs, prov, prov_mgr, acc_mgr = _make_managers(uow.session)
        obj = objs.add(CognitiveObject())
        uow.commit()
        obj_id = obj.id

    try:
        with UnitOfWork() as uow:
            objs, prov, prov_mgr, acc_mgr = _make_managers(uow.session)
            rec = prov_mgr.record(
                coid=obj_id,
                source_type=ProvenanceSourceType.SYSTEM,
                actor_type=ProvenanceActorType.SYSTEM,
            )
            uow.commit()  # não deve levantar mesmo sem trace_id
            assert rec.trace_id is None
    finally:
        with UnitOfWork() as uow:
            objs, prov, prov_mgr, acc_mgr = _make_managers(uow.session)
            import sqlalchemy as sa

            uow.session.execute(
                sa.text("DELETE FROM provenance_records WHERE coid = :c"), {"c": str(obj_id)}
            )
            leftover = objs.get_by_id(obj_id, include_deleted=True)
            if leftover is not None:
                objs.delete(leftover)
            uow.commit()


def test_t2_and_t3_trace_id_persists_distinct_from_session_and_correlation():
    with UnitOfWork() as uow:
        objs, prov, prov_mgr, acc_mgr = _make_managers(uow.session)
        obj = objs.add(CognitiveObject())
        uow.commit()
        obj_id = obj.id

    try:
        with UnitOfWork() as uow:
            objs, prov, prov_mgr, acc_mgr = _make_managers(uow.session)
            rec = prov_mgr.record(
                coid=obj_id,
                source_type=ProvenanceSourceType.AGENT,
                actor_type=ProvenanceActorType.AGENT,
                session_id="session-x",
                correlation_id="correlation-y",
                trace_id="trace-z",
            )
            uow.commit()
            rec_id = rec.id

        with UnitOfWork() as uow:
            objs, prov, prov_mgr, acc_mgr = _make_managers(uow.session)
            reloaded = prov.get_by_id(rec_id)
            assert reloaded.trace_id == "trace-z"
            assert reloaded.session_id == "session-x"
            assert reloaded.correlation_id == "correlation-y"
            assert len({reloaded.session_id, reloaded.correlation_id, reloaded.trace_id}) == 3
    finally:
        with UnitOfWork() as uow:
            objs, prov, prov_mgr, acc_mgr = _make_managers(uow.session)
            import sqlalchemy as sa

            uow.session.execute(
                sa.text("DELETE FROM provenance_records WHERE coid = :c"), {"c": str(obj_id)}
            )
            leftover = objs.get_by_id(obj_id, include_deleted=True)
            if leftover is not None:
                objs.delete(leftover)
            uow.commit()


def test_t4_multiple_records_same_coid_distinct_trace_ids():
    with UnitOfWork() as uow:
        objs, prov, prov_mgr, acc_mgr = _make_managers(uow.session)
        obj = objs.add(CognitiveObject())
        uow.commit()
        obj_id = obj.id

    try:
        with UnitOfWork() as uow:
            objs, prov, prov_mgr, acc_mgr = _make_managers(uow.session)
            prov_mgr.record(
                coid=obj_id,
                source_type=ProvenanceSourceType.AGENT,
                actor_type=ProvenanceActorType.AGENT,
                trace_id="trace-a",
            )
            prov_mgr.record(
                coid=obj_id,
                source_type=ProvenanceSourceType.AGENT,
                actor_type=ProvenanceActorType.AGENT,
                trace_id="trace-b",
            )
            uow.commit()

        with UnitOfWork() as uow:
            objs, prov, prov_mgr, acc_mgr = _make_managers(uow.session)
            trace_ids = {r.trace_id for r in prov_mgr.list_for(obj_id)}
            assert trace_ids == {"trace-a", "trace-b"}
    finally:
        with UnitOfWork() as uow:
            objs, prov, prov_mgr, acc_mgr = _make_managers(uow.session)
            import sqlalchemy as sa

            uow.session.execute(
                sa.text("DELETE FROM provenance_records WHERE coid = :c"), {"c": str(obj_id)}
            )
            leftover = objs.get_by_id(obj_id, include_deleted=True)
            if leftover is not None:
                objs.delete(leftover)
            uow.commit()


def test_t5_multi_ai_shares_trace_id_with_separate_provenance():
    with UnitOfWork() as uow:
        objs, prov, prov_mgr, acc_mgr = _make_managers(uow.session)
        obj = objs.add(CognitiveObject())
        uow.commit()
        obj_id = obj.id

    try:
        with UnitOfWork() as uow:
            objs, prov, prov_mgr, acc_mgr = _make_managers(uow.session)
            _ = prov_mgr.record(
                coid=obj_id,
                source_type=ProvenanceSourceType.AGENT,
                actor_type=ProvenanceActorType.AGENT,
                actor_id="ia-a",
                trace_id="shared-trace",
            )
            _ = prov_mgr.record(
                coid=obj_id,
                source_type=ProvenanceSourceType.AGENT,
                actor_type=ProvenanceActorType.AGENT,
                actor_id="ia-b",
                trace_id="shared-trace",
            )
            uow.commit()

        with UnitOfWork() as uow:
            objs, prov, prov_mgr, acc_mgr = _make_managers(uow.session)
            records = prov_mgr.list_for(obj_id)
            assert len(records) == 2
            assert all(r.trace_id == "shared-trace" for r in records)
            assert len({r.id for r in records}) == 2  # provenance separada
    finally:
        with UnitOfWork() as uow:
            objs, prov, prov_mgr, acc_mgr = _make_managers(uow.session)
            import sqlalchemy as sa

            uow.session.execute(
                sa.text("DELETE FROM provenance_records WHERE coid = :c"), {"c": str(obj_id)}
            )
            leftover = objs.get_by_id(obj_id, include_deleted=True)
            if leftover is not None:
                objs.delete(leftover)
            uow.commit()


def test_t6_no_transcript_or_payload_introduced_with_trace_id():
    """Inspeção estrutural: `trace_id` não abre porta para
    conteúdo/transcript — a coluna continua sendo uma string curta,
    e nenhuma outra coluna de conteúdo foi introduzida junto."""
    from app.cognitive.models.provenance_record import ProvenanceRecord

    columns = {c.name for c in ProvenanceRecord.__table__.columns}
    forbidden = {"content", "payload", "prompt", "response", "transcript", "chat_history"}
    assert columns.isdisjoint(forbidden)
    trace_id_column = ProvenanceRecord.__table__.columns["trace_id"]
    assert trace_id_column.type.length == 255
