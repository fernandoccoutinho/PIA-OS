"""
Testes da correção E3.6.1 — COUT Data Preservation Rule aplicada ao
downgrade de `provenance_records` (`PD1`-`PD5`).

Usa `app.database.migrations` (wrapper programático já existente sobre
o Alembic) para orquestrar `upgrade`/`downgrade` reais contra
PostgreSQL. Mesmo padrão gracioso dos demais arquivos de integração —
pula se PostgreSQL/a migração-guarda não estiverem disponíveis.
"""

import pytest
import sqlalchemy as sa

from app.cognitive.models.cognitive_object import CognitiveObject
from app.cognitive.models.enums import ProvenanceActorType, ProvenanceSourceType
from app.cognitive.repositories.object_repository import ObjectRepository
from app.cognitive.repositories.provenance_repository import ProvenanceRepository
from app.cognitive.services.provenance_manager import ProvenanceManager
from app.database import migrations
from app.database.health import check_database_health
from app.repositories.unit_of_work import UnitOfWork

_GUARD_REVISION = "0460b6556563"
_PRE_PROVENANCE_REVISION = "f11551e97026"


def _guard_migration_available() -> bool:
    health = check_database_health()
    if not health.available:
        return False
    from sqlalchemy import inspect

    from app.database.engine import engine

    tables = inspect(engine).get_table_names()
    if "provenance_records" not in tables:
        return False
    return migrations.head_revision() == _GUARD_REVISION


pytestmark = pytest.mark.skipif(
    not _guard_migration_available(),
    reason=(
        "PostgreSQL real indisponível ou migração-guarda 0460b6556563 "
        "(downgrade de provenance_records) não é a head neste ambiente."
    ),
)


def _make_managers(session):
    objs = ObjectRepository(session)
    prov = ProvenanceRepository(session)
    prov_mgr = ProvenanceManager(prov)
    return objs, prov, prov_mgr


def _provenance_table_columns() -> set[str]:
    from sqlalchemy import inspect

    from app.database.engine import engine

    insp = inspect(engine)
    return {c["name"] for c in insp.get_columns("provenance_records")}


@pytest.fixture(autouse=True)
def _ensure_head_before_and_after():
    migrations.upgrade("head")
    yield
    if migrations.current_revision() != migrations.head_revision():
        migrations.upgrade("head")


def test_pd1_empty_table_downgrade_succeeds():
    """PD1 — `provenance_records` vazia: o downgrade atravessa a
    migração-guarda e a migração de criação da tabela normalmente,
    até a revisão imediatamente anterior."""
    migrations.downgrade(_PRE_PROVENANCE_REVISION)
    assert migrations.current_revision() == _PRE_PROVENANCE_REVISION

    migrations.upgrade("head")
    assert migrations.current_revision() == _GUARD_REVISION


def test_pd2_pd3_pd4_nonempty_table_downgrade_is_blocked_without_data_loss():
    """PD2 (bloqueio), PD3 (zero perda de dados), PD4 (schema
    preservado) — em um único teste, mesmo padrão de
    `test_relationship_downgrade_safety.py` (E3.5.2a)."""
    with UnitOfWork() as uow:
        objs, prov, prov_mgr = _make_managers(uow.session)
        obj = objs.add(CognitiveObject())
        uow.commit()
        obj_id = obj.id

    try:
        with UnitOfWork() as uow:
            objs, prov, prov_mgr = _make_managers(uow.session)
            rec = prov_mgr.record(
                coid=obj_id,
                source_type=ProvenanceSourceType.AGENT,
                actor_type=ProvenanceActorType.AGENT,
                trace_id="pd2-trace",
            )
            uow.commit()
            rec_id = rec.id

        with pytest.raises(Exception) as exc_info:
            migrations.downgrade(_PRE_PROVENANCE_REVISION)
        assert "PROVENANCE_DOWNGRADE_SEMANTICALLY_BLOCKED" in str(exc_info.value)

        assert migrations.current_revision() == _GUARD_REVISION

        with UnitOfWork() as uow:
            objs, prov, prov_mgr = _make_managers(uow.session)
            reloaded = prov.get_by_id(rec_id)
            assert reloaded is not None
            assert reloaded.coid == obj_id
            assert reloaded.trace_id == "pd2-trace"
            assert reloaded.source_type == ProvenanceSourceType.AGENT
            assert reloaded.actor_type == ProvenanceActorType.AGENT

        columns = _provenance_table_columns()
        assert "trace_id" in columns
        assert "coid" in columns
    finally:
        with UnitOfWork() as uow:
            objs, prov, prov_mgr = _make_managers(uow.session)
            uow.session.execute(
                sa.text("DELETE FROM provenance_records WHERE coid = :c"), {"c": str(obj_id)}
            )
            leftover = objs.get_by_id(obj_id, include_deleted=True)
            if leftover is not None:
                objs.delete(leftover)
            uow.commit()


def test_pd5_full_round_trip_compatible_with_empty_table():
    """PD5 — com tabela vazia: `upgrade → downgrade completo → upgrade
    completo` funciona de ponta a ponta, atravessando também a guarda
    de `Relationship` (E3.5.2) mais adiante na cadeia — confirma que
    as duas guardas não se confundem (§13 do prompt corretivo)."""
    migrations.downgrade("2826ce7fa4dc")
    assert migrations.current_revision() == "2826ce7fa4dc"

    migrations.upgrade("head")
    assert migrations.current_revision() == _GUARD_REVISION
