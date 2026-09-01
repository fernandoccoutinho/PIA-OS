"""Provas PostgreSQL reais da persistência governada `E5.l`."""

import json
import uuid
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.database import migrations
from app.database.engine import engine
from app.database.health import check_database_health
from app.predictive_accessibility.errors.exceptions import (
    PredictiveReconfigurationEventIdentityMismatchError,
    PredictiveReconfigurationEventImmutableError,
)
from app.predictive_accessibility.reconfiguration import (
    PredictiveReconfigurationDecision,
    PredictiveReconfigurationEvent,
    PredictiveReconfigurationEventKind,
)
from app.predictive_accessibility.repositories.reconfiguration_repository import (
    PredictiveReconfigurationRepository,
)

pytestmark = pytest.mark.skipif(
    not check_database_health().available,
    reason="PostgreSQL real indisponível — E5.l exige constraints e triggers reais.",
)

_PARENT_REVISION = "e7c25a91f4b3"
_T0 = datetime(2026, 8, 21, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _fresh_e5l_table():
    migrations.upgrade("head")
    yield
    with engine.begin() as connection:
        connection.execute(sa.text("DROP TABLE predictive_reconfiguration_events CASCADE"))
        connection.execute(
            sa.text("DROP FUNCTION IF EXISTS reject_predictive_reconfiguration_mutation()")
        )
        connection.execute(
            sa.text(
                "DROP FUNCTION IF EXISTS " "predictive_string_array_is_canonical(jsonb, boolean)"
            )
        )
        connection.execute(
            sa.text("UPDATE alembic_version SET version_num = :revision"),
            {"revision": _PARENT_REVISION},
        )
    migrations.upgrade("head")


def _event(
    *,
    event_id: uuid.UUID | None = None,
    subject_key: str = "a" * 64,
    from_version: int = 0,
    active_candidate_ref: uuid.UUID | None = None,
) -> PredictiveReconfigurationEvent:
    candidate_ref = active_candidate_ref or uuid.uuid4()
    return PredictiveReconfigurationEvent(
        event_id=event_id or uuid.uuid4(),
        subject_key=subject_key,
        event_kind=PredictiveReconfigurationEventKind.PROMOTE,
        from_version=from_version,
        to_version=from_version + 1,
        active_candidate_ref=candidate_ref,
        candidate_payload_sha256="b" * 64,
        model_ref="model:v2",
        hypothesis_refs=("hypothesis:shift",),
        validation_ref="validation:blind:1",
        cost_ref="cost:1",
        responsible_ref="owner:1",
        rollback_plan_ref="rollback:1",
        approval_reference="APR-1",
        approval_version=from_version + 1,
        approval_scope=("predictive.promote",),
        approval_jurisdiction="br",
        approval_bound_kind="promotion_candidate",
        approval_bound_ref=candidate_ref,
        rollback_of_event_id=None,
        recorded_at=_T0,
    )


def test_e5l_replay_idempotente_e_identidade_divergente_no_postgresql() -> None:
    original = _event(event_id=uuid.UUID(int=201))
    values = {
        column.key: getattr(original, column.key)
        for column in PredictiveReconfigurationEvent.__table__.columns
    }
    with Session(engine) as session:
        repository = PredictiveReconfigurationRepository(session)
        first = repository.append(original)
        session.commit()
        assert first.decision is PredictiveReconfigurationDecision.PROMOTED
    with Session(engine) as session:
        replay = PredictiveReconfigurationRepository(session).append(
            PredictiveReconfigurationEvent(**values)
        )
        assert replay.decision is PredictiveReconfigurationDecision.REPLAYED

    values["model_ref"] = "model:divergent"
    with (
        Session(engine) as session,
        pytest.raises(PredictiveReconfigurationEventIdentityMismatchError),
    ):
        PredictiveReconfigurationRepository(session).append(
            PredictiveReconfigurationEvent(**values)
        )

    with Session(engine) as session:
        assert (
            session.execute(
                sa.text("SELECT count(*) FROM predictive_reconfiguration_events")
            ).scalar_one()
            == 1
        )


def test_e5l_duas_sessoes_convergem_sem_dupla_promocao() -> None:
    first = _event(event_id=uuid.UUID(int=211))
    second = _event(event_id=uuid.UUID(int=212))
    session_a = Session(engine)
    session_b = Session(engine)
    try:
        repo_a = PredictiveReconfigurationRepository(session_a)
        repo_b = PredictiveReconfigurationRepository(session_b)
        assert repo_a.current(first.subject_key) is None
        assert repo_b.current(second.subject_key) is None
        repo_a.append(first)
        session_a.commit()
        loser = repo_b.append(second)
        session_b.commit()
        assert loser.decision is PredictiveReconfigurationDecision.LOST_CONCURRENT_RACE
        assert loser.event is not None
        assert loser.event.event_id == first.event_id
    finally:
        session_a.close()
        session_b.close()


@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("subject_key", "z" * 64),
        ("hypothesis_refs", sa.text("'[]'::jsonb")),
        ("approval_scope", sa.text('\'["b","a"]\'::jsonb')),
        ("approval_bound_kind", "unbound"),
        ("approval_version", 0),
    ],
)
def test_e5l_sql_bruto_nao_contorna_invariantes(column: str, value: object) -> None:
    event = _event()
    values = {
        column_.key: getattr(event, column_.key)
        for column_ in PredictiveReconfigurationEvent.__table__.columns
    }
    values[column] = value
    columns = ", ".join(values)
    parameters: dict[str, object] = {}
    placeholders: list[str] = []
    for name, item in values.items():
        if isinstance(item, sa.sql.elements.TextClause):
            placeholders.append(item.text)
        elif name in {"hypothesis_refs", "approval_scope"}:
            placeholders.append(f"CAST(:{name} AS jsonb)")
            parameters[name] = json.dumps(item)
        else:
            placeholders.append(f":{name}")
            parameters[name] = item
    command = sa.text(
        f"INSERT INTO predictive_reconfiguration_events ({columns}) "
        f"VALUES ({', '.join(placeholders)})"
    )
    with pytest.raises(sa.exc.IntegrityError), engine.begin() as connection:
        connection.execute(command, parameters)


@pytest.mark.parametrize(
    "command",
    (
        "UPDATE predictive_reconfiguration_events SET model_ref='changed'",
        "DELETE FROM predictive_reconfiguration_events",
        "TRUNCATE predictive_reconfiguration_events",
    ),
)
def test_e5l_banco_recusa_update_delete_e_truncate(command: str) -> None:
    with Session(engine) as session:
        session.add(_event())
        session.commit()
    with pytest.raises(Exception, match="append-only"), engine.begin() as connection:
        connection.execute(sa.text(command))


def test_e5l_orm_recusa_mutacao_fora_do_repositorio() -> None:
    event = _event()
    with Session(engine) as session:
        session.add(event)
        session.commit()
        event.model_ref = "changed"
        with pytest.raises(PredictiveReconfigurationEventImmutableError):
            session.flush()


def test_e5l_migration_round_trip_vazio() -> None:
    migrations.downgrade(_PARENT_REVISION)
    assert migrations.current_revision() == _PARENT_REVISION
    with engine.connect() as connection:
        assert (
            connection.execute(
                sa.text("SELECT to_regclass('predictive_reconfiguration_events')")
            ).scalar_one()
            is None
        )
    migrations.upgrade("head")
    assert migrations.current_revision() == "f8a91c2d4e60"
    with engine.connect() as connection:
        assert (
            connection.execute(
                sa.text("SELECT to_regclass('predictive_reconfiguration_events')")
            ).scalar_one()
            == "predictive_reconfiguration_events"
        )


def test_e5l_downgrade_com_historico_recusa_antes_de_ddl() -> None:
    event = _event()
    with Session(engine) as session:
        session.add(event)
        session.commit()
    with pytest.raises(RuntimeError, match="downgrade recusado"):
        migrations.downgrade(_PARENT_REVISION)
    assert migrations.current_revision() == "f8a91c2d4e60"
    with engine.connect() as connection:
        assert (
            connection.execute(
                sa.text("SELECT count(*) FROM predictive_reconfiguration_events")
            ).scalar_one()
            == 1
        )
        assert (
            connection.execute(
                sa.text(
                    "SELECT count(*) FROM pg_trigger "
                    "WHERE tgname IN ('trg_predictive_reconfiguration_append_only', "
                    "'trg_predictive_reconfiguration_no_truncate')"
                )
            ).scalar_one()
            == 2
        )
