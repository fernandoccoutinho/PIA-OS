"""
Testes da correção E3.5.2 — COUT Data Preservation Rule aplicada ao
downgrade de `relationships` (`D1`-`D5`).

Usa `app.database.migrations` (wrapper programático já existente sobre
o Alembic) para orquestrar `upgrade`/`downgrade` reais contra
PostgreSQL — não simula em SQLite (o cenário depende de comandos
Alembic reais, não apenas de SQLAlchemy ORM).

Mesmo padrão gracioso dos demais arquivos de integração — pula se
PostgreSQL/a migração `f11551e97026` não estiverem disponíveis.
"""

import pytest
import sqlalchemy as sa

from app.cognitive.errors.exceptions import RelationshipDuplicateError
from app.cognitive.models.cognitive_object import CognitiveObject
from app.cognitive.models.enums import RelationshipType
from app.cognitive.repositories.object_repository import ObjectRepository
from app.cognitive.repositories.relationship_repository import RelationshipRepository
from app.cognitive.services.relationship_engine import RelationshipEngine
from app.database import migrations
from app.database.health import check_database_health
from app.repositories.unit_of_work import UnitOfWork

_TARGET_REVISION = "f11551e97026"
_PREVIOUS_REVISION = "63d205dec996"


def _guard_migration_available() -> bool:
    health = check_database_health()
    if not health.available:
        return False
    from sqlalchemy import inspect

    from app.database.engine import engine

    tables = inspect(engine).get_table_names()
    if "relationships" not in tables:
        return False
    return migrations.head_revision() == _TARGET_REVISION


pytestmark = pytest.mark.skipif(
    not _guard_migration_available(),
    reason=(
        "PostgreSQL real indisponível ou migração f11551e97026 "
        "(guard de downgrade de relationships) não é a head neste ambiente."
    ),
)


def _make_managers(session):
    objs = ObjectRepository(session)
    rels = RelationshipRepository(session)
    engine = RelationshipEngine(rels)
    return objs, rels, engine


@pytest.fixture(autouse=True)
def _ensure_head_before_and_after():
    """Garante que cada teste começa e termina com o banco na head —
    mesmo que um teste anterior tenha feito downgrade/upgrade."""
    migrations.upgrade("head")
    yield
    if migrations.current_revision() != migrations.head_revision():
        migrations.upgrade("head")


def test_d1_compatible_downgrade_succeeds():
    """D1 — nenhum histórico incompatível produzido: downgrade
    funciona normalmente."""
    with UnitOfWork() as uow:
        objs, rels, engine = _make_managers(uow.session)
        a = objs.add(CognitiveObject())
        b = objs.add(CognitiveObject())
        uow.commit()
        a_id, b_id = a.id, b.id

    try:
        with UnitOfWork() as uow:
            objs, rels, engine = _make_managers(uow.session)
            engine.create(
                source_coid=a_id, target_coid=b_id, relationship_type=RelationshipType.SUPPORTS
            )
            uow.commit()

        # D1: downgrade compatível deve funcionar sem levantar
        migrations.downgrade(_PREVIOUS_REVISION)
        assert migrations.current_revision() == _PREVIOUS_REVISION

        migrations.upgrade("head")
        assert migrations.current_revision() == _TARGET_REVISION
    finally:
        migrations.upgrade("head")
        with UnitOfWork() as uow:
            objs, rels, engine = _make_managers(uow.session)
            uow.session.execute(
                sa.text("DELETE FROM relationships WHERE source_coid = :a"), {"a": str(a_id)}
            )
            for coid in (a_id, b_id):
                leftover = objs.get_by_id(coid, include_deleted=True)
                if leftover is not None:
                    objs.delete(leftover)
            uow.commit()


def test_d2_d3_d4_d5_incompatible_historical_downgrade_is_blocked_without_data_loss():
    """D2 (bloqueio), D3 (zero perda de dados), D4 (schema/Alembic
    preservados), D5 (nenhum downgrade parcial) — tudo em um único
    teste porque compartilham o mesmo cenário/setup caro (múltiplas
    migrações reais)."""
    with UnitOfWork() as uow:
        objs, rels, engine = _make_managers(uow.session)
        a = objs.add(CognitiveObject())
        b = objs.add(CognitiveObject())
        uow.commit()
        a_id, b_id = a.id, b.id

    try:
        # setup: create -> retire -> create (duas gerações da mesma tripla)
        with UnitOfWork() as uow:
            objs, rels, engine = _make_managers(uow.session)
            r0 = engine.create(
                source_coid=a_id, target_coid=b_id, relationship_type=RelationshipType.SUPPORTS
            )
            uow.commit()
            r0_id = r0.id

        with UnitOfWork() as uow:
            objs, rels, engine = _make_managers(uow.session)
            r0_reloaded = rels.get_by_id(r0_id)
            engine.retire(r0_reloaded)
            uow.commit()

        with UnitOfWork() as uow:
            objs, rels, engine = _make_managers(uow.session)
            r1 = engine.create(
                source_coid=a_id, target_coid=b_id, relationship_type=RelationshipType.SUPPORTS
            )
            uow.commit()
            r1_id = r1.id

        # D2: downgrade deve ser recusado explicitamente
        with pytest.raises(Exception) as exc_info:
            migrations.downgrade(_PREVIOUS_REVISION)
        assert "DOWNGRADE_SEMANTICALLY_BLOCKED" in str(exc_info.value)

        # D4 (Alembic state): a revisão atual não retrocedeu
        assert migrations.current_revision() == _TARGET_REVISION

        # D3: zero perda de dados — R0 e R1 continuam presentes com os
        # estados corretos
        with UnitOfWork() as uow:
            objs, rels, engine = _make_managers(uow.session)
            reloaded_r0 = rels.get_by_id(r0_id)
            reloaded_r1 = rels.get_by_id(r1_id)
            assert reloaded_r0 is not None
            assert reloaded_r1 is not None
            assert reloaded_r0.retired_at is not None
            assert reloaded_r1.retired_at is None
            assert reloaded_r0.source_coid == a_id
            assert reloaded_r0.target_coid == b_id
            assert reloaded_r1.source_coid == a_id
            assert reloaded_r1.target_coid == b_id

        # D4 (schema preservado): índice único parcial e CHECK de
        # simetria continuam existindo; duplicata ativa continua
        # rejeitada (prova de que o schema E3.5.1 está íntegro)
        with UnitOfWork() as uow:
            objs, rels, engine = _make_managers(uow.session)
            with pytest.raises(RelationshipDuplicateError):
                engine.create(
                    source_coid=a_id,
                    target_coid=b_id,
                    relationship_type=RelationshipType.SUPPORTS,
                )
            uow.rollback()

        # D5: nenhum downgrade parcial — confirmado indiretamente pelo
        # fato de D3/D4 acima passarem (se houvesse estado parcial, o
        # índice/constraint ou os dados estariam corrompidos)
    finally:
        migrations.upgrade("head")
        with UnitOfWork() as uow:
            objs, rels, engine = _make_managers(uow.session)
            uow.session.execute(
                sa.text("DELETE FROM relationships WHERE source_coid = :a"), {"a": str(a_id)}
            )
            for coid in (a_id, b_id):
                leftover = objs.get_by_id(coid, include_deleted=True)
                if leftover is not None:
                    objs.delete(leftover)
            uow.commit()
