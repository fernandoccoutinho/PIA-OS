"""
Testes de integração de `E3.9`/`LIB-09` contra PostgreSQL real.

Cobrem o que SQLite não prova:

- constraints reais do banco (`CheckConstraint` de auto-predecessor,
  FK de predecessor/ator, unicidade de história por sujeito);
- ciclo de migração `upgrade → downgrade → upgrade` com tabela vazia;
- **guarda de downgrade** com história registrada — o downgrade é
  recusado antes de qualquer alteração estrutural, e nenhum dado é
  perdido (`HISTORICAL PRESERVATION > DOWNGRADE CONVENIENCE`);
- gate forte de leitura: navegar a história emite zero escritas e não
  altera o patrimônio de origem;
- concorrência real de append.

Executa Alembic in-process; o isolamento de logging de `E3.6.1d` vem
da fixture autouse de `conftest.py` deste diretório.
"""

import threading
import uuid
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from sqlalchemy import event
from sqlalchemy.exc import IntegrityError

from app.cognitive.models.cognitive_object import CognitiveObject
from app.cognitive.models.enums import CausalEventType
from app.cognitive.repositories.causal_history_repository import CausalHistoryRepository
from app.cognitive.repositories.object_repository import ObjectRepository
from app.cognitive.services.causal_history_manager import CausalHistoryManager
from app.database import migrations
from app.database.engine import engine
from app.database.health import check_database_health
from app.database.session import SessionLocal
from app.repositories.unit_of_work import UnitOfWork

_E3_9_REVISION = "c9a3f61b74d2"
_PRE_E3_9_REVISION = "b7c41d0e92a5"

_ALL_TABLES = (
    "causal_history_events",
    "causal_histories",
    "provenance_records",
    "relationships",
    "lineage_edges",
    "transformation_records",
    "cognitive_objects",
)


def _available() -> bool:
    if not check_database_health().available:
        return False
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(migrations.get_alembic_config())
    try:
        return script.get_revision(_E3_9_REVISION) is not None
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _available(),
    reason="PostgreSQL real indisponível ou migração c9a3f61b74d2 (E3.9) ausente da cadeia.",
)


@pytest.fixture(autouse=True)
def _head_and_clean_slate():
    migrations.upgrade("head")
    _truncate()
    yield
    if migrations.current_revision() != migrations.head_revision():
        migrations.upgrade("head")
    _truncate()


def _truncate() -> None:
    with engine.begin() as conn:
        conn.execute(sa.text(f"TRUNCATE {', '.join(_ALL_TABLES)} CASCADE"))


def _new_subject() -> uuid.UUID:
    with UnitOfWork() as uow:
        obj = ObjectRepository(uow.session).add(CognitiveObject())
        uow.commit()
        return obj.id


def _census() -> dict[str, list[tuple]]:
    census: dict[str, list[tuple]] = {}
    with engine.connect() as conn:
        for table in _ALL_TABLES:
            rows = conn.execute(sa.text(f"SELECT * FROM {table} ORDER BY id")).all()
            census[table] = [tuple(row) for row in rows]
    return census


def test_chi1_round_trip_against_real_postgres():
    """CHI1 — história e eventos persistem e voltam íntegros, com
    `occurred_at` distinto de `created_at`."""
    subject = _new_subject()
    long_ago = datetime(1999, 7, 20, tzinfo=UTC)

    with UnitOfWork() as uow:
        manager = CausalHistoryManager(CausalHistoryRepository(uow.session))
        root = manager.record(
            subject_coid=subject,
            event_type=CausalEventType.CREATED,
            payload_ref="ref://origem",
            occurred_at=long_ago,
        )
        manager.record(
            subject_coid=subject, event_type=CausalEventType.TRANSFORMED, predecessor=root
        )
        uow.commit()
        root_id = root.id

    with UnitOfWork() as uow:
        manager = CausalHistoryManager(CausalHistoryRepository(uow.session))
        events = manager.events_for(subject)
        assert len(events) == 2
        first = next(e for e in events if e.id == root_id)
        assert first.occurred_at == long_ago
        assert first.created_at > first.occurred_at
        assert first.payload_ref == "ref://origem"
        assert [e.id for e in manager.roots(subject)] == [root_id]


def test_chi2_database_constraints_are_the_final_authority():
    """CHI2 — as garantias estruturais existem no banco, não só no
    domínio: auto-predecessor rejeitado pelo CHECK, predecessor
    inexistente rejeitado pela FK, e um sujeito não pode ter duas
    histórias."""
    subject = _new_subject()

    with UnitOfWork() as uow:
        manager = CausalHistoryManager(CausalHistoryRepository(uow.session))
        history = manager.ensure_history(subject)
        uow.commit()
        history_id = history.id

    # (a) auto-predecessor — CheckConstraint
    forced_id = uuid.uuid4()
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO causal_history_events "
                "(id, history_id, event_type, predecessor_event_id, created_at, updated_at) "
                "VALUES (:id, :h, 'transformed', :id, now(), now())"
            ),
            {"id": forced_id, "h": history_id},
        )

    # (b) predecessor inexistente — ForeignKey
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO causal_history_events "
                "(id, history_id, event_type, predecessor_event_id, created_at, updated_at) "
                "VALUES (gen_random_uuid(), :h, 'transformed', gen_random_uuid(), "
                "now(), now())"
            ),
            {"h": history_id},
        )

    # (c) duas histórias para o mesmo sujeito — índice único
    with pytest.raises(IntegrityError), engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO causal_histories (id, subject_coid, created_at, updated_at) "
                "VALUES (gen_random_uuid(), :s, now(), now())"
            ),
            {"s": subject},
        )


def test_chi3_concurrent_appends_all_survive():
    """CHI3 (§42) — o invariante real de concorrência aqui é *nenhuma
    perda*: append-only não tem last-write-wins a proteger, e dois
    appends simultâneos devem ambos sobreviver.

    Duas threads, duas sessões/conexões independentes, barreira para
    forçar simultaneidade real.
    """
    subject = _new_subject()
    with UnitOfWork() as uow:
        CausalHistoryManager(CausalHistoryRepository(uow.session)).ensure_history(subject)
        uow.commit()

    barrier = threading.Barrier(2)
    errors: list[Exception] = []

    def worker(label: str) -> None:
        try:
            session = SessionLocal()
            try:
                manager = CausalHistoryManager(CausalHistoryRepository(session))
                barrier.wait(timeout=10)
                manager.record(
                    subject_coid=subject,
                    event_type=CausalEventType.ACCESSED,
                    payload_ref=f"ref://{label}",
                )
                session.commit()
            finally:
                session.close()
        except Exception as exc:  # pragma: no cover - só em falha real
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(name,)) for name in ("t1", "t2")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert errors == []
    with UnitOfWork() as uow:
        manager = CausalHistoryManager(CausalHistoryRepository(uow.session))
        payloads = {e.payload_ref for e in manager.events_for(subject)}
    assert payloads == {"ref://t1", "ref://t2"}


def test_chi4_reading_history_emits_zero_writes():
    """CHI4 (§38) — navegar a história não escreve nada, e nem a
    história nem o patrimônio de origem mudam."""
    subject = _new_subject()
    with UnitOfWork() as uow:
        manager = CausalHistoryManager(CausalHistoryRepository(uow.session))
        root = manager.record(subject_coid=subject, event_type=CausalEventType.CREATED)
        manager.record(subject_coid=subject, event_type=CausalEventType.ACCESSED, predecessor=root)
        uow.commit()
        root_id = root.id

    before = _census()
    writes: list[str] = []

    @event.listens_for(engine, "before_cursor_execute")
    def _record_writes(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        head = statement.lstrip().split(None, 1)[0].upper() if statement.strip() else ""
        if head in {"INSERT", "UPDATE", "DELETE", "TRUNCATE"}:
            writes.append(head)

    try:
        with UnitOfWork() as uow:
            manager = CausalHistoryManager(CausalHistoryRepository(uow.session))
            manager.history_for(subject)
            manager.events_for(subject)
            manager.roots(subject)
            stored_root = CausalHistoryRepository(uow.session).get_event(root_id)
            assert stored_root is not None
            manager.successors(stored_root)
            manager.predecessors(stored_root)
            manager.history_for(uuid.uuid4())
            manager.events_for(uuid.uuid4())
    finally:
        event.remove(engine, "before_cursor_execute", _record_writes)

    assert writes == [], writes
    assert _census() == before


def test_chi5_appending_does_not_mutate_previous_events():
    """CHI5 (§39) — anexar um evento novo deixa os anteriores
    byte-idênticos no banco."""
    subject = _new_subject()
    with UnitOfWork() as uow:
        manager = CausalHistoryManager(CausalHistoryRepository(uow.session))
        manager.record(subject_coid=subject, event_type=CausalEventType.CREATED)
        uow.commit()

    with engine.connect() as conn:
        before = [
            tuple(row)
            for row in conn.execute(
                sa.text("SELECT * FROM causal_history_events ORDER BY id")
            ).all()
        ]

    with UnitOfWork() as uow:
        manager = CausalHistoryManager(CausalHistoryRepository(uow.session))
        manager.record(subject_coid=subject, event_type=CausalEventType.TRANSFORMED)
        uow.commit()

    with engine.connect() as conn:
        after = [
            tuple(row)
            for row in conn.execute(
                sa.text("SELECT * FROM causal_history_events ORDER BY id")
            ).all()
        ]

    assert len(after) == 2
    for row in before:
        assert row in after


def test_chi6_empty_tables_allow_downgrade():
    """CHI6 (§43) — sem história registrada, o downgrade é seguro e
    permitido; o ciclo completo volta à head."""
    actual_head = migrations.head_revision()

    migrations.downgrade(_PRE_E3_9_REVISION)
    assert migrations.current_revision() == _PRE_E3_9_REVISION
    tables = set(sa.inspect(engine).get_table_names())
    assert not {"causal_histories", "causal_history_events"} & tables

    migrations.upgrade("head")
    assert migrations.current_revision() == actual_head
    tables = set(sa.inspect(engine).get_table_names())
    assert {"causal_histories", "causal_history_events"} <= tables


def test_chi7_downgrade_with_recorded_history_is_blocked_without_data_loss():
    """CHI7 (§43) — com história registrada, o downgrade é recusado
    **antes** de qualquer alteração estrutural, e nada é perdido.

    O registro histórico é ele próprio um rastro preservado
    (`COUT-CH-9`): apagá-lo por conveniência de schema destruiria a
    evidência que o módulo existe para guardar.
    """
    subject = _new_subject()
    with UnitOfWork() as uow:
        manager = CausalHistoryManager(CausalHistoryRepository(uow.session))
        manager.record(
            subject_coid=subject,
            event_type=CausalEventType.CREATED,
            payload_ref="ref://preservar",
        )
        uow.commit()

    actual_head = migrations.head_revision()
    before = _census()

    with pytest.raises(Exception) as exc_info:
        migrations.downgrade(_PRE_E3_9_REVISION)
    assert "CAUSAL_HISTORY_DOWNGRADE_SEMANTICALLY_BLOCKED" in str(exc_info.value)

    assert migrations.current_revision() == actual_head
    tables = set(sa.inspect(engine).get_table_names())
    assert {"causal_histories", "causal_history_events"} <= tables
    assert _census() == before

    with UnitOfWork() as uow:
        manager = CausalHistoryManager(CausalHistoryRepository(uow.session))
        payloads = [e.payload_ref for e in manager.events_for(subject)]
    assert payloads == ["ref://preservar"]


def test_chi8_metadata_matches_the_database_after_e3_9():
    """CHI8 — `Base.metadata` e o banco continuam sincronizados nas
    tabelas de história; sem isso um `autogenerate` futuro proporia
    mudanças fantasma nelas.

    O escopo é restrito às duas tabelas de `E3.9` de propósito:
    modelos declarados apenas por fixtures de teste
    (`test_base_model_concrete_entity`, `test_mixin_fixture_entity`)
    também se registram no `Base` real durante a coleta e apareceriam
    como `add_table` — ruído de harness, não divergência de schema.
    Mesmo recorte que `IX5` (`E3.7`) já usava.
    """
    import app.cognitive.models  # noqa: F401
    import app.orchestration.models  # noqa: F401
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from app.database.base import Base

    with engine.connect() as conn:
        diffs = compare_metadata(MigrationContext.configure(conn), Base.metadata)

    causal_diffs = [d for d in diffs if "causal_histor" in str(d)]
    assert causal_diffs == [], causal_diffs


def test_chi9_no_transcript_columns_were_introduced():
    """CHI9 (§30) — inspeção do schema real: as tabelas de história
    guardam referências e identificadores, nunca conteúdo."""
    inspector = sa.inspect(engine)

    history_columns = {c["name"] for c in inspector.get_columns("causal_histories")}
    event_columns = {c["name"] for c in inspector.get_columns("causal_history_events")}

    assert history_columns == {"id", "subject_coid", "created_at", "updated_at"}
    assert event_columns == {
        "id",
        "history_id",
        "event_type",
        "actor_ref",
        "payload_ref",
        "predecessor_event_id",
        "occurred_at",
        "created_at",
        "updated_at",
    }
    assert not {c for c in event_columns if "transcript" in c or "content" in c or "prompt" in c}


def test_chi10_cross_history_predecessor_persists_against_postgres():
    """CHI10 (`E3.9.1`) — o elo causal entre histórias de sujeitos
    diferentes persiste no banco real e não funde nada.

    A FK de `predecessor_event_id` é global de propósito: transmissão
    causal atravessa sujeitos (`history boundary != causal boundary`),
    e exigir `child.history_id == predecessor.history_id` obrigaria a
    fundir as duas histórias — apagando a distinção entre os dois
    sujeitos.
    """
    source = _new_subject()
    receiver = _new_subject()

    with UnitOfWork() as uow:
        manager = CausalHistoryManager(CausalHistoryRepository(uow.session))
        emitted = manager.record(
            subject_coid=source, event_type=CausalEventType.CREATED, payload_ref="ref://emitido"
        )
        received = manager.record(
            subject_coid=receiver,
            event_type=CausalEventType.ACCESSED,
            predecessor=emitted,
            payload_ref="ref://recebido",
        )
        uow.commit()
        emitted_id, received_id = emitted.id, received.id

    with engine.connect() as conn:
        rows = dict(
            conn.execute(
                sa.text(
                    "SELECT e.id, h.subject_coid FROM causal_history_events e "
                    "JOIN causal_histories h ON h.id = e.history_id"
                )
            ).all()
        )
        link = conn.execute(
            sa.text("SELECT predecessor_event_id FROM causal_history_events WHERE id = :i"),
            {"i": received_id},
        ).scalar_one()

    assert link == emitted_id
    assert rows[emitted_id] == source
    assert rows[received_id] == receiver
    assert rows[emitted_id] != rows[received_id]

    with UnitOfWork() as uow:
        manager = CausalHistoryManager(CausalHistoryRepository(uow.session))
        assert [e.id for e in manager.events_for(source)] == [emitted_id]
        assert [e.id for e in manager.events_for(receiver)] == [received_id]
        stored = CausalHistoryRepository(uow.session).get_event(emitted_id)
        assert stored is not None
        assert [e.id for e in manager.successors(stored)] == [received_id]
