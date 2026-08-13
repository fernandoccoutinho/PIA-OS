"""
Testes da correção E3.6.1 — COUT Data Preservation Rule aplicada ao
downgrade de `provenance_records` (`PD1`-`PD5`).

Usa `app.database.migrations` (wrapper programático já existente sobre
o Alembic) para orquestrar `upgrade`/`downgrade` reais contra
PostgreSQL. Mesmo padrão gracioso dos demais arquivos de integração —
pula se PostgreSQL/a migração-guarda não estiverem disponíveis.

**Correção E3.6.1a (débito C1)**: a versão anterior deste arquivo
exigia `migrations.head_revision() == "0460b6556563"` para não
pular — exatamente o mesmo problema já identificado e corrigido em
`test_relationship_downgrade_safety.py` na própria correção E3.6.1,
mas que não havia sido replicado aqui. Corrigido seguindo o mesmo
princípio: os testes começam na head ATUAL (seja ela qual for),
fazem downgrade controlado até a revisão necessária, e restauram a
head atual no fim — nunca exigem que `0460b6556563` seja a head
global. A condição de skip verifica apenas que a migração existe na
cadeia (via `ScriptDirectory.get_revision()`), não que é a head.
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

# Revisões específicas da cadeia sendo exercitadas, não a head global
# (correção E3.6.1a — mesmo princípio de nomenclatura já aplicado em
# `test_relationship_downgrade_safety.py`).
_PROVENANCE_GUARD_REVISION = "0460b6556563"  # migração-guarda de Provenance (E3.6.1)
_PRE_PROVENANCE_REVISION = "f11551e97026"  # schema imediatamente anterior a Provenance


def _revision_exists(revision_id: str) -> bool:
    """Confirma que `revision_id` existe na cadeia de migrações (não
    que é a head) — mesmo helper local já usado em
    `test_relationship_downgrade_safety.py`; replicado aqui em vez de
    movido para produção (§2 do prompt corretivo E3.6.1a: "não mover
    helper para produção, não criar utilitário global apenas para
    esta correção")."""
    from alembic.script import ScriptDirectory

    config = migrations.get_alembic_config()
    script = ScriptDirectory.from_config(config)
    try:
        return script.get_revision(revision_id) is not None
    except Exception:
        return False


def _guard_migration_available() -> bool:
    health = check_database_health()
    if not health.available:
        return False
    from sqlalchemy import inspect

    from app.database.engine import engine

    tables = inspect(engine).get_table_names()
    if "provenance_records" not in tables:
        return False
    return _revision_exists(_PROVENANCE_GUARD_REVISION)


pytestmark = pytest.mark.skipif(
    not _guard_migration_available(),
    reason=(
        "PostgreSQL real indisponível, tabela 'provenance_records' "
        "ausente, ou migração 0460b6556563 (guard de downgrade de "
        "provenance_records) não existe na cadeia deste ambiente."
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
    """Garante que cada teste começa e termina com o banco na head
    ATUAL (seja ela qual for — nunca hardcoded)."""
    migrations.upgrade("head")
    yield
    if migrations.current_revision() != migrations.head_revision():
        migrations.upgrade("head")


def test_pd1_empty_table_downgrade_succeeds():
    """PD1 — `provenance_records` vazia: o downgrade atravessa a
    migração-guarda e a migração de criação da tabela normalmente,
    até a revisão imediatamente anterior. Depois, `upgrade("head")` e
    confirma que a head alcançada é a head REAL do ambiente, não um
    valor hardcoded."""
    actual_head = migrations.head_revision()

    migrations.downgrade(_PRE_PROVENANCE_REVISION)
    assert migrations.current_revision() == _PRE_PROVENANCE_REVISION

    migrations.upgrade("head")
    assert migrations.current_revision() == actual_head


def test_pd2_pd3_pd4_nonempty_table_downgrade_is_blocked_without_data_loss():
    """PD2 (bloqueio), PD3 (zero perda de dados), PD4 (schema
    preservado) — em um único teste, mesmo padrão de
    `test_relationship_downgrade_safety.py` (E3.5.2a). Correção
    E3.6.1a: a comparação "não retrocedeu" usa `migrations.head_revision()`
    dinâmico, não mais uma constante hardcoded."""
    with UnitOfWork() as uow:
        objs, prov, prov_mgr = _make_managers(uow.session)
        obj = objs.add(CognitiveObject())
        uow.commit()
        obj_id = obj.id

    try:
        actual_head = migrations.head_revision()

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

        assert migrations.current_revision() == actual_head

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
    as duas guardas não se confundem. Correção E3.6.1a: comparação
    final usa a head real, não hardcoded."""
    actual_head = migrations.head_revision()

    migrations.downgrade("2826ce7fa4dc")
    assert migrations.current_revision() == "2826ce7fa4dc"

    migrations.upgrade("head")
    assert migrations.current_revision() == actual_head


def test_provenance_guard_still_reachable_from_current_head():
    """Confirma explicitamente que a guarda de `Provenance` (E3.6.1)
    continua alcançável a partir da head atual, mesmo depois de
    módulos posteriores estenderem a cadeia — mesmo espírito de
    `test_m4_relationship_guard_still_reachable_from_current_head`
    em `test_relationship_downgrade_safety.py`."""
    assert _revision_exists(_PROVENANCE_GUARD_REVISION)
    assert _revision_exists(_PRE_PROVENANCE_REVISION)
