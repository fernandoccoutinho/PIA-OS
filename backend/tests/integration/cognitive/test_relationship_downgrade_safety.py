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

# Nomenclatura explícita (correção E3.5.2a) — `_PREVIOUS_REVISION`
# ocultava qual fronteira arquitetural cada constante representa.
_GUARD_REVISION = "f11551e97026"  # migração-guarda (E3.5.2)
_E3_5_1_REVISION = "63d205dec996"  # active uniqueness + symmetric guarantee (E3.5.1)
_PRE_E3_5_1_REVISION = "2826ce7fa4dc"  # schema original de Relationship (E3.5), antes de E3.5.1


def _guard_migration_available() -> bool:
    health = check_database_health()
    if not health.available:
        return False
    from sqlalchemy import inspect

    from app.database.engine import engine

    tables = inspect(engine).get_table_names()
    if "relationships" not in tables:
        return False
    return migrations.head_revision() == _GUARD_REVISION


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


def _relationships_indexes_and_constraints() -> dict[str, set[str]]:
    """Introspecção real do PostgreSQL — nomes de índices e de
    constraints CHECK/UNIQUE atualmente presentes em `relationships`.
    Usado para confirmar estruturalmente qual schema está em vigor,
    não apenas a revisão que o Alembic *diz* estar aplicada."""
    from sqlalchemy import inspect

    from app.database.engine import engine

    insp = inspect(engine)
    index_names = {ix["name"] for ix in insp.get_indexes("relationships")}
    unique_constraint_names = {
        uc["name"] for uc in insp.get_unique_constraints("relationships") if uc["name"]
    }
    check_constraint_names = {
        cc["name"] for cc in insp.get_check_constraints("relationships") if cc["name"]
    }
    return {
        "indexes": index_names,
        "unique_constraints": unique_constraint_names,
        "checks": check_constraint_names,
    }


@pytest.fixture(autouse=True)
def _ensure_head_before_and_after():
    """Garante que cada teste começa e termina com o banco na head —
    mesmo que um teste anterior tenha feito downgrade/upgrade."""
    migrations.upgrade("head")
    yield
    if migrations.current_revision() != migrations.head_revision():
        migrations.upgrade("head")


def test_d1_compatible_downgrade_succeeds():
    """D1 — `FULL_COMPATIBLE_DOWNGRADE`: nenhum histórico incompatível
    produzido. Prova o downgrade **completo** do estado compatível até
    `2826ce7fa4dc` (o schema imediatamente anterior a E3.5.1) — não
    apenas até `63d205dec996` (correção E3.5.2a: a versão anterior
    deste teste executava só `f11551e97026 -> 63d205dec996`, o
    downgrade da migração-guarda, sem nunca exercitar de fato o
    downgrade de `63d205dec996`).

    Confirma estruturalmente, via introspecção real do PostgreSQL
    (não apenas `alembic current`):

    - o índice único parcial de E3.5.1
      (`uq_relationships_active_source_target_type`) deixou de existir;
    - o `CheckConstraint` de canonicalização de E3.5.1
      (`ck_relationships_symmetric_canonical_order`) deixou de existir;
    - a `UniqueConstraint` incondicional anterior
      (`uq_relationships_source_target_type`) voltou a existir;
    - os dados compatíveis continuam presentes e íntegros.

    Depois, `upgrade("head")` e confirma que o schema E3.5.1/E3.5.2
    volta corretamente (mesma introspecção, resultado invertido).
    """
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

        # downgrade completo, atravessando f11551e97026 -> 63d205dec996
        # -> 2826ce7fa4dc (não apenas o primeiro passo)
        migrations.downgrade(_PRE_E3_5_1_REVISION)

        # A: Alembic realmente chegou a 2826ce7fa4dc
        assert migrations.current_revision() == _PRE_E3_5_1_REVISION

        schema_after_downgrade = _relationships_indexes_and_constraints()
        # B: índice parcial de E3.5.1 não está mais presente
        assert "uq_relationships_active_source_target_type" not in schema_after_downgrade["indexes"]
        # C: CHECK de canonicalização de E3.5.1 não está mais presente
        assert "ck_relationships_symmetric_canonical_order" not in schema_after_downgrade["checks"]
        # D: constraint de unicidade anterior está novamente presente
        assert "uq_relationships_source_target_type" in schema_after_downgrade["unique_constraints"]

        # E/F: os dados compatíveis existentes continuam presentes,
        # sem alteração indevida — consulta SQL direta, já que o ORM
        # de app.cognitive foi mapeado contra o schema atual (head),
        # não contra o schema antigo agora restaurado
        from app.database.engine import engine as db_engine

        with db_engine.connect() as conn:
            row = conn.execute(
                sa.text(
                    "SELECT source_coid, target_coid, relationship_type, retired_at "
                    "FROM relationships WHERE source_coid = :a"
                ),
                {"a": str(a_id)},
            ).fetchone()
            assert row is not None
            assert str(row[0]) == str(a_id)
            assert str(row[1]) == str(b_id)
            assert row[2] == "supports"
            assert row[3] is None

        # volta para a head e confirma que o schema E3.5.1/E3.5.2
        # retorna corretamente
        migrations.upgrade("head")
        assert migrations.current_revision() == _GUARD_REVISION

        schema_after_upgrade = _relationships_indexes_and_constraints()
        assert "uq_relationships_active_source_target_type" in schema_after_upgrade["indexes"]
        assert "ck_relationships_symmetric_canonical_order" in schema_after_upgrade["checks"]
        assert (
            "uq_relationships_source_target_type" not in schema_after_upgrade["unique_constraints"]
        )

        # dados preservados também depois do upgrade de volta
        with UnitOfWork() as uow:
            objs, rels, engine = _make_managers(uow.session)
            reloaded = rels.outgoing(a_id)
            assert len(reloaded) == 1
            assert reloaded[0].target_coid == b_id
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
    migrações reais). Comportamento inalterado pela correção E3.5.2a
    — apenas a nomenclatura das constantes foi atualizada."""
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
            migrations.downgrade(_PRE_E3_5_1_REVISION)
        assert "DOWNGRADE_SEMANTICALLY_BLOCKED" in str(exc_info.value)

        # D4 (Alembic state): a revisão atual não retrocedeu
        assert migrations.current_revision() == _GUARD_REVISION

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

        # D4 (schema preservado, introspecção estrutural direta)
        schema_after_block = _relationships_indexes_and_constraints()
        assert "uq_relationships_active_source_target_type" in schema_after_block["indexes"]
        assert "ck_relationships_symmetric_canonical_order" in schema_after_block["checks"]

        # D5: nenhum downgrade parcial — confirmado tanto pela
        # integridade estrutural acima quanto pelos dados em D3
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
