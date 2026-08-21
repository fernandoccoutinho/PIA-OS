"""
Testes unitários de `E3.8`/`LIB-08` — Search Engine.

Cobrem `S1`-`S20` do módulo sobre SQLite em memória. O que depende do
PostgreSQL real — plano de consulta composta e o gate forte de
preservação de patrimônio com contagem de escritas — vive em
`tests/integration/cognitive/test_search_integration.py`.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.cognitive.errors.exceptions import SearchCriteriaError
from app.cognitive.models.cognitive_object import CognitiveObject
from app.cognitive.models.enums import (
    AccessibilityState,
    LineageRelation,
    ProvenanceActorType,
    ProvenanceSourceType,
    RelationshipType,
    RevisionStatus,
)
from app.cognitive.models.lineage_edge import LineageEdge
from app.cognitive.models.provenance_record import ProvenanceRecord
from app.cognitive.models.relationship import Relationship
from app.cognitive.models.transformation_record import TransformationRecord
from app.cognitive.repositories.lineage_repository import LineageRepository
from app.cognitive.repositories.object_repository import ObjectRepository
from app.cognitive.repositories.provenance_repository import ProvenanceRepository
from app.cognitive.repositories.relationship_repository import RelationshipRepository
from app.cognitive.repositories.search_repository import SearchRepository
from app.cognitive.schemas.search_criteria import SearchCriteria
from app.cognitive.services.provenance_manager import ProvenanceManager
from app.cognitive.services.search_engine import SearchEngine


@pytest.fixture
def engine_and_session(cognitive_session):
    session = cognitive_session
    return session, ObjectRepository(session), SearchEngine(SearchRepository(session))


def _add(objects, session, **kwargs) -> CognitiveObject:
    obj = objects.add(CognitiveObject(**kwargs))
    session.flush()
    return obj


def _counts(session) -> dict[str, int]:
    """Censo do patrimônio persistido — usado para provar que buscar
    não escreve."""
    return {
        model.__name__: session.query(model).count()
        for model in (
            CognitiveObject,
            LineageEdge,
            Relationship,
            TransformationRecord,
            ProvenanceRecord,
        )
    }


def test_s1_search_by_a_single_structural_criterion(engine_and_session):
    """S1 — busca por critério estrutural válido."""
    session, objects, search = engine_and_session
    clid = uuid.uuid4()
    target = _add(objects, session, clid=clid)
    _add(objects, session, clid=uuid.uuid4())

    found = search.search(SearchCriteria(clid=clid))

    assert [o.id for o in found] == [target.id]


def test_s2_and_composition_narrows_the_result(engine_and_session):
    """S2 — composição `AND`: cada critério adicional restringe, nunca
    amplia."""
    session, objects, search = engine_and_session
    clid = uuid.uuid4()
    current = _add(
        objects,
        session,
        clid=clid,
        accessibility=AccessibilityState.ACTIVE,
        revision_status=RevisionStatus.CURRENT,
    )
    _add(
        objects,
        session,
        clid=clid,
        accessibility=AccessibilityState.LATENT,
        revision_status=RevisionStatus.SUPERSEDED,
    )

    only_clid = search.search(SearchCriteria(clid=clid))
    conjunction = search.search(
        SearchCriteria(
            clid=clid,
            accessibility=AccessibilityState.ACTIVE,
            revision_status=RevisionStatus.CURRENT,
        )
    )

    assert len(only_clid) == 2
    assert [o.id for o in conjunction] == [current.id]


def test_s3_empty_result_is_valid_not_an_error(engine_and_session):
    """S3 — resultado vazio é resposta válida de consulta bem-formada,
    nunca exceção."""
    _, _, search = engine_and_session

    assert search.search(SearchCriteria(clid=uuid.uuid4())) == []
    assert search.count(SearchCriteria(trace_id="nunca-existiu")) == 0


def test_s4_search_miss_does_not_erase_the_source(engine_and_session):
    """S4 — `SEARCH MISS != NON-EXISTENCE`: o objeto que não satisfaz
    os critérios continua persistido, inalterado e recuperável por
    outra consulta."""
    session, objects, search = engine_and_session
    obj = _add(objects, session, accessibility=AccessibilityState.CAUSALLY_EXTINCT)

    assert search.search(SearchCriteria(accessibility=AccessibilityState.ACTIVE)) == []

    assert objects.get_by_id(obj.id) is not None
    assert [o.id for o in search.search(SearchCriteria(coid=obj.id))] == [obj.id]


def test_s5_s6_s7_search_does_not_modify_object_coid_or_clid(engine_and_session):
    """S5/S6/S7 — a consulta não altera o objeto, o COID nem o CLID."""
    session, objects, search = engine_and_session
    clid = uuid.uuid4()
    obj = _add(
        objects,
        session,
        clid=clid,
        accessibility=AccessibilityState.LATENT,
        revision_status=RevisionStatus.CURRENT,
    )
    before = (obj.id, obj.clid, obj.accessibility, obj.revision_status, obj.deleted_at)

    search.search(SearchCriteria(clid=clid))
    search.search(SearchCriteria(coid=obj.id))
    search.search(SearchCriteria(accessibility=AccessibilityState.LATENT))

    session.refresh(obj)
    assert (obj.id, obj.clid, obj.accessibility, obj.revision_status, obj.deleted_at) == before


def test_s8_s9_current_and_superseded_are_both_retrievable(engine_and_session):
    """S8/S9 — `CURRENT` e `SUPERSEDED` recuperáveis; sem filtro de
    revisão, o histórico **não** é silenciosamente apagado da
    resposta."""
    session, objects, search = engine_and_session
    clid = uuid.uuid4()
    current = _add(objects, session, clid=clid, revision_status=RevisionStatus.CURRENT)
    superseded = _add(objects, session, clid=clid, revision_status=RevisionStatus.SUPERSEDED)

    assert [
        o.id
        for o in search.search(SearchCriteria(clid=clid, revision_status=RevisionStatus.CURRENT))
    ] == [current.id]
    assert [
        o.id
        for o in search.search(SearchCriteria(clid=clid, revision_status=RevisionStatus.SUPERSEDED))
    ] == [superseded.id]
    assert {o.id for o in search.search(SearchCriteria(clid=clid))} == {current.id, superseded.id}


def test_s10_accessibility_separates_existence_from_exposure(engine_and_session):
    """S10 — `EXISTENCE != ACCESSIBILITY != LOCALIZABILITY`: sem
    filtro, todos os estados vêm; filtrar esconde da resposta e não
    apaga (`filtered_out != erased`)."""
    session, objects, search = engine_and_session
    clid = uuid.uuid4()
    active = _add(objects, session, clid=clid, accessibility=AccessibilityState.ACTIVE)
    extinct = _add(objects, session, clid=clid, accessibility=AccessibilityState.CAUSALLY_EXTINCT)

    unfiltered = {o.id for o in search.search(SearchCriteria(clid=clid))}
    filtered = {
        o.id
        for o in search.search(SearchCriteria(clid=clid, accessibility=AccessibilityState.ACTIVE))
    }

    assert unfiltered == {active.id, extinct.id}
    assert filtered == {active.id}
    assert objects.get_by_id(extinct.id) is not None


def test_s10b_soft_deleted_is_out_of_scope_by_default_but_not_deleted(engine_and_session):
    """S10 (complemento) — `inaccessible != deleted` e
    `no_result != never_existed`: soft delete tira do escopo padrão e
    `include_deleted=True` traz de volta."""
    session, objects, search = engine_and_session
    clid = uuid.uuid4()
    obj = _add(objects, session, clid=clid)
    objects.soft_delete(obj)
    session.flush()

    assert search.search(SearchCriteria(clid=clid)) == []
    assert [o.id for o in search.search(SearchCriteria(clid=clid, include_deleted=True))] == [
        obj.id
    ]


def test_s11_trace_id_is_a_dimension_not_an_identity(engine_and_session):
    """S11 — `trace_id` compõe como dimensão de busca e não vira
    identidade: dois objetos podem compartilhá-lo e ele não altera
    COID/CLID."""
    session, objects, search = engine_and_session
    first = _add(objects, session, clid=uuid.uuid4())
    second = _add(objects, session, clid=uuid.uuid4())
    provenance = ProvenanceManager(ProvenanceRepository(session))
    for obj in (first, second):
        provenance.record(
            coid=obj.id,
            source_type=ProvenanceSourceType.AGENT,
            actor_type=ProvenanceActorType.AGENT,
            trace_id="trace-s11",
        )
    session.flush()

    found = search.search(SearchCriteria(trace_id="trace-s11"))

    assert {o.id for o in found} == {first.id, second.id}
    assert first.clid != second.clid
    assert first.id != second.id


def test_s11b_trace_id_composes_with_other_dimensions_without_duplicates(engine_and_session):
    """S11 (complemento) — o mesmo objeto com dois `ProvenanceRecord`s
    do mesmo trace aparece uma vez só, e o trace compõe com `AND`."""
    session, objects, search = engine_and_session
    target = _add(objects, session, accessibility=AccessibilityState.ACTIVE)
    other = _add(objects, session, accessibility=AccessibilityState.LATENT)
    provenance = ProvenanceManager(ProvenanceRepository(session))
    for actor in (ProvenanceActorType.AGENT, ProvenanceActorType.HUMAN):
        provenance.record(
            coid=target.id,
            source_type=ProvenanceSourceType.AGENT,
            actor_type=actor,
            trace_id="trace-s11b",
        )
    provenance.record(
        coid=other.id,
        source_type=ProvenanceSourceType.AGENT,
        actor_type=ProvenanceActorType.AGENT,
        trace_id="trace-s11b",
    )
    session.flush()

    assert [
        o.id
        for o in search.search(
            SearchCriteria(trace_id="trace-s11b", accessibility=AccessibilityState.ACTIVE)
        )
    ] == [target.id]


def test_s12_lineage_and_relationship_are_not_flattened(engine_and_session):
    """S12 — `LINEAGE != RELATIONSHIP`: a busca não expõe uma dimensão
    genérica de "edge" que colapse as duas taxonomias."""
    session, objects, _ = engine_and_session
    parent = _add(objects, session)
    child = _add(objects, session)
    LineageRepository(session).add_edge(
        parent_coid=parent.id, child_coid=child.id, relation_type=LineageRelation.DERIVED_FROM
    )
    RelationshipRepository(session).add_relationship(
        source_coid=parent.id, target_coid=child.id, relationship_type=RelationshipType.REFERENCES
    )
    session.flush()

    dimensions = {f for f in SearchCriteria._FILTER_FIELDS}

    assert (
        not {"edge", "edge_type", "relation", "relationship_type", "lineage_relation"} & dimensions
    )
    assert not set(LineageRelation) & set(RelationshipType)


def test_s13_s14_s15_search_creates_no_domain_records(engine_and_session):
    """S13/S14/S15 — consultar não cria Provenance, Transformation,
    Relationship nem LineageEdge."""
    session, objects, search = engine_and_session
    obj = _add(objects, session, clid=uuid.uuid4(), accessibility=AccessibilityState.ACTIVE)
    ProvenanceManager(ProvenanceRepository(session)).record(
        coid=obj.id,
        source_type=ProvenanceSourceType.SYSTEM,
        actor_type=ProvenanceActorType.SYSTEM,
        trace_id="trace-s13",
    )
    session.flush()
    before = _counts(session)

    search.search(SearchCriteria(clid=obj.clid))
    search.search(SearchCriteria(trace_id="trace-s13"))
    search.search(SearchCriteria(accessibility=AccessibilityState.ACTIVE))
    search.count(SearchCriteria(coid=obj.id))
    session.flush()

    assert _counts(session) == before


def test_s16_ordering_is_deterministic_not_ranking(engine_and_session):
    """S16 — ordenação determinística por `created_at ASC, id ASC`.
    Isto é *ordering*, não *relevance ranking*: nenhum score existe."""
    session, objects, search = engine_and_session
    clid = uuid.uuid4()
    older = _add(objects, session, clid=clid)
    newer = _add(objects, session, clid=clid)
    older.created_at = datetime(2020, 1, 1, tzinfo=UTC)
    newer.created_at = datetime(2020, 1, 2, tzinfo=UTC)
    session.flush()

    assert [o.id for o in search.search(SearchCriteria(clid=clid))] == [older.id, newer.id]

    older.created_at, newer.created_at = newer.created_at, older.created_at
    session.flush()

    assert [o.id for o in search.search(SearchCriteria(clid=clid))] == [newer.id, older.id]


def test_s17_pagination_is_stable_and_partitions_the_result(engine_and_session):
    """S17 — paginação offset/limit sobre ordenação total: páginas não
    se sobrepõem, não perdem objeto e sua união é o resultado
    completo."""
    session, objects, search = engine_and_session
    clid = uuid.uuid4()
    base = datetime(2021, 1, 1, tzinfo=UTC)
    for i in range(5):
        obj = _add(objects, session, clid=clid)
        obj.created_at = base + timedelta(seconds=i)
    session.flush()

    criteria = SearchCriteria(clid=clid)
    full = [o.id for o in search.search(criteria)]
    page1 = [o.id for o in search.search(criteria, limit=2)]
    page2 = [o.id for o in search.search(criteria, limit=2, offset=2)]
    page3 = [o.id for o in search.search(criteria, limit=2, offset=4)]

    assert len(full) == 5 == search.count(criteria)
    assert page1 + page2 + page3 == full
    assert not set(page1) & set(page2)


def test_s18_invalid_criteria_fail_in_a_typed_way(engine_and_session):
    """S18 — critérios inválidos falham com `SearchCriteriaError`
    (`PIA-8019`), antes de qualquer acesso ao banco."""
    _, _, search = engine_and_session

    with pytest.raises(SearchCriteriaError) as no_dimension:
        SearchCriteria()
    assert no_dimension.value.error_code.code == "PIA-8019"

    with pytest.raises(SearchCriteriaError):
        SearchCriteria(trace_id="   ")

    with pytest.raises(SearchCriteriaError):
        SearchCriteria(
            created_from=datetime(2024, 1, 2, tzinfo=UTC),
            created_until=datetime(2024, 1, 1, tzinfo=UTC),
        )

    with pytest.raises(SearchCriteriaError):
        search.search(SearchCriteria(clid=uuid.uuid4()), limit=-1)

    with pytest.raises(SearchCriteriaError):
        search.search(SearchCriteria(clid=uuid.uuid4()), offset=-1)


def test_s18b_include_deleted_alone_is_not_a_criterion(engine_and_session):
    """S18 (complemento) — `include_deleted` é modificador de escopo,
    não critério: sozinho, produziria varredura completa e é
    rejeitado."""
    with pytest.raises(SearchCriteriaError, match="nenhuma dimensão"):
        SearchCriteria(include_deleted=True)


def test_s19_s20_no_search_result_or_query_is_persisted(engine_and_session):
    """S19/S20 — nenhuma persistência de resultado nem de consulta: o
    retorno é a própria entidade persistida, e nenhuma tabela de
    histórico/consulta existe."""
    session, objects, search = engine_and_session
    clid = uuid.uuid4()
    obj = _add(objects, session, clid=clid)

    (found,) = search.search(SearchCriteria(clid=clid))

    assert found is obj
    tables = set(CognitiveObject.metadata.tables)
    assert not {t for t in tables if "search" in t or "query" in t}


def test_created_at_window_composes_as_a_closed_interval(engine_and_session):
    """A janela temporal é inclusiva nos dois extremos e compõe por
    `AND` com as demais dimensões."""
    session, objects, search = engine_and_session
    clid = uuid.uuid4()
    base = datetime(2022, 6, 1, tzinfo=UTC)
    made = []
    for i in range(3):
        obj = _add(objects, session, clid=clid)
        obj.created_at = base + timedelta(days=i)
        made.append(obj)
    session.flush()

    found = search.search(
        SearchCriteria(clid=clid, created_from=base, created_until=base + timedelta(days=1))
    )

    assert [o.id for o in found] == [made[0].id, made[1].id]


def test_active_dimensions_reports_only_informed_criteria(engine_and_session):
    """`active_dimensions()` reporta o que foi informado, sem expor
    valores — usado em documentação e diagnóstico."""
    criteria = SearchCriteria(clid=uuid.uuid4(), accessibility=AccessibilityState.ACTIVE)

    assert criteria.active_dimensions() == ("clid", "accessibility")
