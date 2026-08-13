"""
Testes de integração de `E3.8`/`LIB-08` contra PostgreSQL real.

Dois objetivos que SQLite não consegue cumprir:

- **§22/§31** — confirmar que a consulta composta é resolvida pelo
  banco sobre os índices de `E3.7`, sem scan patológico quando existe
  alternativa indexada. Seguindo a lição de `E3.7`: *testar a
  propriedade, não o plano preferido pelo implementador* — o que se
  assevera é que o planner usa **algum** caminho indexado, não um
  índice específico escolhido a dedo.
- **§29** — o gate COUT forte: patrimônio idêntico antes e depois de
  uma bateria de buscas, com contagem direta de escritas de domínio
  emitidas ao banco.

Executa Alembic in-process apenas na fixture de head; o isolamento de
logging de `E3.6.1d` vem da fixture autouse de `conftest.py` deste
diretório.
"""

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy import event

from app.cognitive.models.enums import AccessibilityState, RevisionStatus
from app.cognitive.repositories.search_repository import SearchRepository
from app.cognitive.schemas.search_criteria import SearchCriteria
from app.cognitive.services.search_engine import SearchEngine
from app.database import migrations
from app.database.engine import engine
from app.database.health import check_database_health
from app.repositories.unit_of_work import UnitOfWork

_DATASET_SIZE = 3000

_COGNITIVE_TABLES = (
    "provenance_records",
    "relationships",
    "lineage_edges",
    "transformation_records",
    "cognitive_objects",
)


def _available() -> bool:
    return check_database_health().available


pytestmark = pytest.mark.skipif(
    not _available(), reason="PostgreSQL real indisponível — E3.8 exige banco real."
)


@pytest.fixture(autouse=True)
def _head_and_clean_slate():
    migrations.upgrade("head")
    _truncate()
    yield
    _truncate()


def _truncate() -> None:
    with engine.begin() as conn:
        conn.execute(sa.text(f"TRUNCATE {', '.join(_COGNITIVE_TABLES)} CASCADE"))


def _seed(size: int = _DATASET_SIZE) -> tuple[uuid.UUID, str]:
    """Patrimônio com CLID e trace_id altamente seletivos — a condição
    em que o caminho indexado importa."""
    target_clid = uuid.uuid4()
    target_trace = f"trace-{uuid.uuid4()}"
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
                "VALUES (gen_random_uuid(), :coid, 'agent', 'agent', :trace, "
                "'[]'::json, now(), now())"
            ),
            {"coid": target_id, "trace": target_trace},
        )
        for table in ("cognitive_objects", "provenance_records"):
            conn.execute(sa.text(f"ANALYZE {table}"))
    return target_clid, target_trace


def _explain(criteria: SearchCriteria) -> str:
    with UnitOfWork() as uow:
        stmt = SearchRepository(uow.session)._build(criteria)
        compiled = stmt.compile(engine, compile_kwargs={"literal_binds": True})
    with engine.connect() as conn:
        rows = conn.execute(sa.text(f"EXPLAIN ANALYZE {compiled}")).all()
    return "\n".join(row[0] for row in rows)


def _patrimony_snapshot() -> dict[str, list[tuple]]:
    """Censo completo e ordenado do patrimônio — todas as linhas de
    todas as tabelas cognitivas."""
    snapshot: dict[str, list[tuple]] = {}
    with engine.connect() as conn:
        for table in _COGNITIVE_TABLES:
            rows = conn.execute(sa.text(f"SELECT * FROM {table} ORDER BY id")).all()
            snapshot[table] = [tuple(row) for row in rows]
    return snapshot


def test_sx1_composed_query_uses_an_indexed_path():
    """SX1 (§22/§31) — a conjunção é resolvida pelo banco por caminho
    indexado, sem varredura sequencial da tabela de objetos quando há
    alternativa indexada. Assevera a **propriedade**, não qual índice
    o planner deve preferir."""
    target_clid, target_trace = _seed()

    plan = _explain(
        SearchCriteria(
            clid=target_clid,
            accessibility=AccessibilityState.LATENT,
            revision_status=RevisionStatus.CURRENT,
        )
    )

    assert "Index" in plan, plan
    assert "Seq Scan on cognitive_objects" not in plan, plan

    trace_plan = _explain(SearchCriteria(trace_id=target_trace))
    assert "Index" in trace_plan, trace_plan
    assert "Seq Scan on provenance_records" not in trace_plan, trace_plan


def test_sx2_composed_search_returns_the_persisted_rows():
    """SX2 — round-trip do serviço contra o banco real: a conjunção
    devolve exatamente o objeto persistido que a satisfaz."""
    target_clid, target_trace = _seed(size=200)

    with UnitOfWork() as uow:
        search = SearchEngine(SearchRepository(uow.session))

        conjunction = search.search(
            SearchCriteria(
                clid=target_clid,
                accessibility=AccessibilityState.LATENT,
                revision_status=RevisionStatus.CURRENT,
            )
        )
        assert len(conjunction) == 1
        located = conjunction[0]

        assert [o.id for o in search.search(SearchCriteria(trace_id=target_trace))] == [located.id]
        assert search.count(SearchCriteria(revision_status=RevisionStatus.SUPERSEDED)) == 200
        # Conjunção contraditória: bem-formada, resultado vazio, sem erro.
        assert (
            search.search(
                SearchCriteria(clid=target_clid, accessibility=AccessibilityState.INACCESSIBLE)
            )
            == []
        )


def test_sx3_patrimony_is_bit_for_bit_identical_after_searching():
    """SX3 (§29) — gate COUT forte: `P_after == P_before`.

    Executa uma bateria de buscas sobre patrimônio heterogêneo e
    compara o censo completo de todas as tabelas cognitivas, linha a
    linha, além de contar as escritas de domínio emitidas ao banco
    durante as consultas.
    """
    target_clid, target_trace = _seed(size=500)
    before = _patrimony_snapshot()

    writes: list[str] = []

    @event.listens_for(engine, "before_cursor_execute")
    def _record_writes(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        head = statement.lstrip().split(None, 1)[0].upper() if statement.strip() else ""
        if head in {"INSERT", "UPDATE", "DELETE", "TRUNCATE"}:
            writes.append(head)

    try:
        with UnitOfWork() as uow:
            search = SearchEngine(SearchRepository(uow.session))
            search.search(SearchCriteria(clid=target_clid))
            search.search(SearchCriteria(trace_id=target_trace))
            search.search(SearchCriteria(accessibility=AccessibilityState.ACTIVE), limit=10)
            search.search(SearchCriteria(revision_status=RevisionStatus.SUPERSEDED), limit=5)
            search.search(SearchCriteria(coid=uuid.uuid4()))
            search.search(SearchCriteria(clid=uuid.uuid4(), include_deleted=True))
            search.count(SearchCriteria(accessibility=AccessibilityState.ACTIVE))
    finally:
        event.remove(engine, "before_cursor_execute", _record_writes)

    assert writes == [], writes
    assert _patrimony_snapshot() == before


def test_sx4_search_does_not_depend_on_its_own_state():
    """SX4 (§30) — `PATRIMONY DOES NOT DEPEND ON SEARCH`: nenhuma
    tabela de busca, cache ou histórico de consulta foi criada; o
    conjunto de tabelas é o mesmo de `E3.7`."""
    tables = set(sa.inspect(engine).get_table_names())

    assert not {t for t in tables if "search" in t or "quer" in t or "cache" in t}
    assert tables >= set(_COGNITIVE_TABLES)


def test_sx5_pagination_is_stable_across_repeated_queries():
    """SX5 — paginação estável contra o banco real: repetir a mesma
    página devolve a mesma fatia, e as páginas particionam o total."""
    _seed(size=50)

    criteria = SearchCriteria(revision_status=RevisionStatus.SUPERSEDED)
    with UnitOfWork() as uow:
        search = SearchEngine(SearchRepository(uow.session))
        total = search.count(criteria)
        first = [o.id for o in search.search(criteria, limit=20)]
        first_again = [o.id for o in search.search(criteria, limit=20)]
        second = [o.id for o in search.search(criteria, limit=20, offset=20)]
        third = [o.id for o in search.search(criteria, limit=20, offset=40)]

    assert total == 50
    assert first == first_again
    assert len(set(first + second + third)) == 50
