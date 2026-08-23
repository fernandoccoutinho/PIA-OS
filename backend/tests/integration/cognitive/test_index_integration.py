"""
Testes de integração de `E3.7`/`LIB-07` contra PostgreSQL real.

Cobrem exatamente o que SQLite não consegue provar:

- que os índices criados por `b7c41d0e92a5` são de fato **escolhidos
  pelo planner** em dataset com estatísticas reais (§21 — gate
  estrutural, não product-scale);
- que a migração é genuinamente reversível: `DROPPING AN INDEX !=
  DROPPING COGNITIVE HISTORY` (§23/§24);
- o gate COUT de destruição/recriação de índice (§29): destruir apenas
  o índice não toca no patrimônio, e recriá-lo devolve resultados
  equivalentes.

Este arquivo executa Alembic in-process e portanto depende do
mecanismo de isolamento de logging de `E3.6.1d` — a fixture autouse de
`conftest.py` deste diretório cobre isso automaticamente; nada de
logging é reconfigurado aqui.
"""

import uuid

import pytest
import sqlalchemy as sa

from app.cognitive.models.cognitive_object import CognitiveObject
from app.cognitive.models.enums import (
    AccessibilityState,
    ProvenanceActorType,
    ProvenanceSourceType,
    RevisionStatus,
)
from app.cognitive.repositories.index_repository import IndexRepository
from app.cognitive.repositories.object_repository import ObjectRepository
from app.cognitive.repositories.provenance_repository import ProvenanceRepository
from app.cognitive.services.index_manager import IndexManager
from app.cognitive.services.provenance_manager import ProvenanceManager
from app.database import migrations
from app.database.engine import engine
from app.database.health import check_database_health
from app.repositories.unit_of_work import UnitOfWork

_E3_7_REVISION = "b7c41d0e92a5"
_PRE_E3_7_REVISION = "0460b6556563"

_E3_7_INDEXES = {
    "cognitive_objects": {
        "ix_cognitive_objects_clid",
        "ix_cognitive_objects_accessibility_created_at_id",
        "ix_cognitive_objects_revision_status_created_at_id",
    },
    "provenance_records": {"ix_provenance_records_trace_id"},
}

#: Volume suficiente para o planner preferir índice a seq scan. Não é
#: benchmark de produto — é o mínimo que torna a escolha significativa.
_DATASET_SIZE = 3000


def _available() -> bool:
    if not check_database_health().available:
        return False
    from alembic.script import ScriptDirectory
    from app.database import migrations as _m

    script = ScriptDirectory.from_config(_m.get_alembic_config())
    try:
        return script.get_revision(_E3_7_REVISION) is not None
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _available(),
    reason=(
        "PostgreSQL real indisponível ou migração b7c41d0e92a5 "
        "(índices estruturais de E3.7) ausente da cadeia."
    ),
)


def _index_names(table: str) -> set[str]:
    return {idx["name"] for idx in sa.inspect(engine).get_indexes(table)}


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
        conn.execute(
            sa.text(
                "TRUNCATE provenance_records, relationships, lineage_edges, "
                "transformation_records, cognitive_objects CASCADE"
            )
        )


def _seed(size: int = _DATASET_SIZE) -> tuple[uuid.UUID, str]:
    """Popula o banco com `size` objetos e devolve um CLID e um
    `trace_id` que existem em exatamente um objeto cada — ou seja,
    altamente seletivos, que é a condição em que o índice importa."""
    target_clid = uuid.uuid4()
    target_trace = f"trace-alvo-{uuid.uuid4()}"
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO cognitive_objects "
                "(id, clid, accessibility, revision_status, created_at, updated_at) "
                "SELECT gen_random_uuid(), gen_random_uuid(), 'active', 'superseded', "
                "now() - (g || ' seconds')::interval, now() "
                "FROM generate_series(1, :n) AS g"
            ),
            {"n": size},
        )
        target_id = conn.execute(
            sa.text(
                "INSERT INTO cognitive_objects "
                "(id, clid, accessibility, revision_status, created_at, updated_at) "
                "VALUES (gen_random_uuid(), :clid, 'latent', 'current', now(), now()) "
                "RETURNING id"
            ),
            {"clid": target_clid},
        ).scalar_one()
        conn.execute(
            sa.text(
                "INSERT INTO provenance_records "
                "(id, coid, source_type, actor_type, trace_id, evidence_refs, "
                " created_at, updated_at) "
                "SELECT gen_random_uuid(), o.id, 'agent', 'agent', "
                "'trace-' || gen_random_uuid(), '[]'::json, now(), now() "
                "FROM cognitive_objects o"
            )
        )
        conn.execute(
            sa.text(
                "INSERT INTO provenance_records "
                "(id, coid, source_type, actor_type, trace_id, evidence_refs, "
                " created_at, updated_at) "
                "VALUES (gen_random_uuid(), :coid, 'agent', 'agent', :trace, "
                "'[]'::json, now(), now())"
            ),
            {"coid": target_id, "trace": target_trace},
        )
        conn.execute(sa.text("ANALYZE cognitive_objects"))
        conn.execute(sa.text("ANALYZE provenance_records"))
    return target_clid, target_trace


def _plan(sql: str, params: dict) -> str:
    with engine.connect() as conn:
        rows = conn.execute(sa.text(f"EXPLAIN ANALYZE {sql}"), params).all()
    return "\n".join(row[0] for row in rows)


def test_ix1_planner_uses_the_new_indexes():
    """IX1 (§21) — evidência de que os índices criados são realmente
    usados pelo planner, em dataset com estatísticas reais. Gate
    estrutural: o que se prova é que a estrutura é utilizável, não uma
    métrica de produto."""
    target_clid, target_trace = _seed()

    clid_plan = _plan(
        "SELECT * FROM cognitive_objects WHERE clid = :clid AND deleted_at IS NULL",
        {"clid": str(target_clid)},
    )
    assert "ix_cognitive_objects_clid" in clid_plan, clid_plan

    trace_plan = _plan(
        "SELECT * FROM provenance_records WHERE trace_id = :trace", {"trace": target_trace}
    )
    assert "ix_provenance_records_trace_id" in trace_plan, trace_plan

    ordered_plan = _plan(
        "SELECT * FROM cognitive_objects WHERE accessibility = 'latent' "
        "ORDER BY created_at ASC, id ASC LIMIT 10",
        {},
    )
    assert "ix_cognitive_objects_accessibility_created_at_id" in ordered_plan, ordered_plan

    # `revision_status`: o índice de E3.7 é o único caminho para
    # `SUPERSEDED` — e é escolhido.
    superseded_plan = _plan(
        "SELECT * FROM cognitive_objects WHERE revision_status = 'superseded' "
        "ORDER BY created_at ASC, id ASC LIMIT 10",
        {},
    )
    assert "ix_cognitive_objects_revision_status_created_at_id" in superseded_plan, superseded_plan

    # Já para `CURRENT`, o planner prefere o índice único parcial de
    # E3.4.1 (`uq_cognitive_objects_one_current_per_clid`, restrito a
    # `revision_status = 'current'` e portanto muito menor). Isso é
    # comportamento correto e está asseverado de propósito: o índice
    # de E3.7 acrescenta um caminho onde não havia nenhum, sem
    # competir com o que já existia.
    current_plan = _plan(
        "SELECT * FROM cognitive_objects WHERE revision_status = 'current' "
        "ORDER BY created_at ASC, id ASC LIMIT 10",
        {},
    )
    assert "uq_cognitive_objects_one_current_per_clid" in current_plan, current_plan
    assert "Seq Scan" not in current_plan, current_plan


def test_ix2_index_manager_returns_the_same_rows_against_postgres():
    """IX2 — as primitivas devolvem, contra PostgreSQL real, exatamente
    as linhas persistidas (round-trip do serviço, não só do SQL cru)."""
    target_clid, target_trace = _seed(size=200)

    with UnitOfWork() as uow:
        index = IndexManager(ObjectRepository(uow.session), IndexRepository(uow.session))

        by_clid = index.by_clid(target_clid)
        assert len(by_clid) == 1
        located = by_clid[0]
        assert located.accessibility == AccessibilityState.LATENT
        assert located.revision_status == RevisionStatus.CURRENT

        assert [o.id for o in index.by_trace_id(target_trace)] == [located.id]
        assert index.by_coid(located.id) is not None
        assert [o.id for o in index.by_accessibility(AccessibilityState.LATENT)] == [located.id]
        assert [o.id for o in index.by_revision_status(RevisionStatus.CURRENT)] == [located.id]


def test_ix3_index_destruction_preserves_patrimony_and_rebuild_restores_access():
    """IX3 (§29) — gate COUT de destruição/reconstrução, na variante
    de índices nativos:

    1. criar patrimônio; 2. índices presentes; 3. destruir SOMENTE os
    índices (downgrade da migração de E3.7); 4. patrimônio intacto e
    ainda consultável; 5. recriar (upgrade); 6. índices de volta e
    resultados equivalentes.
    """
    target_clid, target_trace = _seed(size=500)

    with UnitOfWork() as uow:
        index = IndexManager(ObjectRepository(uow.session), IndexRepository(uow.session))
        before_ids = [o.id for o in index.by_clid(target_clid)]
        before_trace = [o.id for o in index.by_trace_id(target_trace)]
    with engine.connect() as conn:
        before_count = conn.execute(sa.text("SELECT count(*) FROM cognitive_objects")).scalar_one()

    for table, expected in _E3_7_INDEXES.items():
        assert expected <= _index_names(table)

    migrations.downgrade(_PRE_E3_7_REVISION)
    assert migrations.current_revision() == _PRE_E3_7_REVISION

    # 3/4 — só os índices sumiram; o patrimônio continua inteiro e as
    # mesmas consultas continuam corretas (mais lentas, não erradas).
    for table, expected in _E3_7_INDEXES.items():
        assert not (expected & _index_names(table))
    with engine.connect() as conn:
        assert (
            conn.execute(sa.text("SELECT count(*) FROM cognitive_objects")).scalar_one()
            == before_count
        )
    with UnitOfWork() as uow:
        index = IndexManager(ObjectRepository(uow.session), IndexRepository(uow.session))
        assert [o.id for o in index.by_clid(target_clid)] == before_ids
        assert [o.id for o in index.by_trace_id(target_trace)] == before_trace

    migrations.upgrade("head")
    assert migrations.current_revision() == migrations.head_revision()

    for table, expected in _E3_7_INDEXES.items():
        assert expected <= _index_names(table)
    with engine.connect() as conn:
        assert (
            conn.execute(sa.text("SELECT count(*) FROM cognitive_objects")).scalar_one()
            == before_count
        )
    with UnitOfWork() as uow:
        index = IndexManager(ObjectRepository(uow.session), IndexRepository(uow.session))
        assert [o.id for o in index.by_clid(target_clid)] == before_ids
        assert [o.id for o in index.by_trace_id(target_trace)] == before_trace


def test_ix4_migration_cycle_is_idempotent_and_lossless():
    """IX4 (§14/§23) — `upgrade → downgrade → upgrade` completo é
    determinístico e idempotente: o conjunto de índices ao final é
    idêntico ao inicial, sem guarda de downgrade, porque nenhuma
    distinção cognitiva pode ser perdida por remover índice."""
    _seed(size=100)
    before = {table: _index_names(table) for table in _E3_7_INDEXES}

    migrations.downgrade(_PRE_E3_7_REVISION)
    migrations.upgrade("head")
    first_cycle = {table: _index_names(table) for table in _E3_7_INDEXES}

    migrations.downgrade(_PRE_E3_7_REVISION)
    migrations.upgrade("head")
    second_cycle = {table: _index_names(table) for table in _E3_7_INDEXES}

    assert first_cycle == before
    assert second_cycle == before


def test_ix5_metadata_matches_the_database_after_e3_7():
    """IX5 — `Base.metadata` e o banco continuam sincronizados depois
    de E3.7. Sem isto, um `alembic revision --autogenerate` futuro
    emitiria `DROP INDEX` para os índices deste módulo — foi por isso
    que eles foram declarados também em `__table_args__`, e não apenas
    na migração."""
    import app.cognitive.models  # noqa: F401
    import app.orchestration.models  # noqa: F401
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from app.database.base import Base

    with engine.connect() as conn:
        diffs = compare_metadata(MigrationContext.configure(conn), Base.metadata)

    index_diffs = [d for d in diffs if "index" in str(d).lower()]
    assert index_diffs == [], index_diffs


def test_ix6_no_new_table_and_no_transcript_storage():
    """IX6 (§16/§27) — E3.7 não criou tabela nova nem coluna capaz de
    guardar transcript/payload: o conjunto de tabelas é o mesmo de
    E3.6, e nenhuma coluna de texto livre foi acrescentada."""
    tables = set(sa.inspect(engine).get_table_names())

    assert "cognitive_indexes" not in tables
    assert tables >= {
        "cognitive_objects",
        "lineage_edges",
        "transformation_records",
        "relationships",
        "provenance_records",
    }
    assert not {t for t in tables if "index" in t}

    columns = {c["name"] for c in sa.inspect(engine).get_columns("cognitive_objects")}
    assert columns == {
        "id",
        "clid",
        "accessibility",
        "revision_status",
        "created_at",
        "updated_at",
        "deleted_at",
    }


def test_ix7_provenance_write_is_visible_to_the_index_in_the_same_transaction():
    """IX7 (§15) — consistência transacional: o índice estrutural é
    consistente assim que a transação da fonte commita. Não há
    pipeline assíncrono, fila ou worker — nada a sincronizar depois."""
    with UnitOfWork() as uow:
        obj = ObjectRepository(uow.session).add(CognitiveObject())
        uow.commit()
        coid = obj.id

    trace = f"trace-tx-{uuid.uuid4()}"
    with UnitOfWork() as uow:
        ProvenanceManager(ProvenanceRepository(uow.session)).record(
            coid=coid,
            source_type=ProvenanceSourceType.HUMAN,
            actor_type=ProvenanceActorType.HUMAN,
            trace_id=trace,
        )
        uow.commit()

    with UnitOfWork() as uow:
        index = IndexManager(ObjectRepository(uow.session), IndexRepository(uow.session))
        assert [o.id for o in index.by_trace_id(trace)] == [coid]
