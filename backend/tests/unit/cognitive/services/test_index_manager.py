"""
Testes unitários de `E3.7`/`LIB-07` — Index Manager.

Cobrem os invariantes COUT do módulo sobre SQLite em memória (mesma
infraestrutura de `tests/unit/cognitive/`). O que depende do
PostgreSQL real — uso efetivo dos índices pelo planner, ciclo de
migração, destruição/recriação de índice — vive em
`tests/integration/cognitive/test_index_integration.py`.
"""

import uuid
from datetime import UTC, datetime

import pytest

from app.cognitive.models.cognitive_object import CognitiveObject
from app.cognitive.models.enums import (
    AccessibilityState,
    LineageRelation,
    ProvenanceActorType,
    ProvenanceSourceType,
    RelationshipType,
    RevisionStatus,
)
from app.cognitive.repositories.index_repository import IndexRepository
from app.cognitive.repositories.lineage_repository import LineageRepository
from app.cognitive.repositories.object_repository import ObjectRepository
from app.cognitive.repositories.provenance_repository import ProvenanceRepository
from app.cognitive.repositories.relationship_repository import RelationshipRepository
from app.cognitive.services.index_manager import IndexManager
from app.cognitive.services.provenance_manager import ProvenanceManager


@pytest.fixture
def managers(cognitive_session):
    session = cognitive_session
    objects = ObjectRepository(session)
    index = IndexManager(objects, IndexRepository(session))
    return session, objects, index


def _add(objects, session, **kwargs) -> CognitiveObject:
    obj = objects.add(CognitiveObject(**kwargs))
    session.flush()
    return obj


def test_i1_deterministic_location_by_structural_identity(managers):
    """I1 — localização determinística por identidade estrutural."""
    session, objects, index = managers
    obj = _add(objects, session)

    located = index.by_coid(obj.id)

    assert located is not None
    assert located.id == obj.id
    assert index.by_coid(uuid.uuid4()) is None


def test_i2_clid_with_multiple_revisions_is_fully_located(managers):
    """I2 — um CLID com várias revisões devolve todas, ordenadas."""
    session, objects, index = managers
    clid = uuid.uuid4()
    a = _add(objects, session, clid=clid, revision_status=RevisionStatus.SUPERSEDED)
    b = _add(objects, session, clid=clid, revision_status=RevisionStatus.CURRENT)
    _add(objects, session, clid=uuid.uuid4())

    found = index.by_clid(clid)

    # Ordem canônica é `created_at ASC, id ASC`; no SQLite os dois
    # objetos nascem com o mesmo `created_at`, então a comparação aqui
    # é de conjunto — a ordenação determinística tem teste próprio.
    assert {o.id for o in found} == {a.id, b.id}


def test_i3_current_and_superseded_are_both_indexable(managers):
    """I3 — `CURRENT` e `SUPERSEDED` permanecem localizáveis."""
    session, objects, index = managers
    current = _add(objects, session, clid=uuid.uuid4(), revision_status=RevisionStatus.CURRENT)
    superseded = _add(
        objects, session, clid=uuid.uuid4(), revision_status=RevisionStatus.SUPERSEDED
    )

    assert [o.id for o in index.by_revision_status(RevisionStatus.CURRENT)] == [current.id]
    assert [o.id for o in index.by_revision_status(RevisionStatus.SUPERSEDED)] == [superseded.id]


def test_i4_accessibility_is_not_existence(managers):
    """I4 — acessibilidade não equivale a existência: um objeto
    `CAUSALLY_EXTINCT` continua localizável, e não aparecer numa
    consulta filtrada por outro estado não o apaga."""
    session, objects, index = managers
    extinct = _add(objects, session, accessibility=AccessibilityState.CAUSALLY_EXTINCT)

    assert [o.id for o in index.by_accessibility(AccessibilityState.CAUSALLY_EXTINCT)] == [
        extinct.id
    ]
    assert index.by_accessibility(AccessibilityState.ACTIVE) == []
    # NOT RETURNED BY INDEX != DOES NOT EXIST
    assert index.by_coid(extinct.id) is not None


def test_i4b_accessibility_transition_does_not_destroy_patrimony(managers):
    """I4 (complemento) — mudar `AccessibilityState` move o objeto
    entre consultas, nunca o destrói."""
    session, objects, index = managers
    obj = _add(objects, session, accessibility=AccessibilityState.ACTIVE)

    obj.accessibility = AccessibilityState.INACCESSIBLE
    session.flush()

    assert index.by_accessibility(AccessibilityState.ACTIVE) == []
    assert [o.id for o in index.by_accessibility(AccessibilityState.INACCESSIBLE)] == [obj.id]
    assert index.by_coid(obj.id) is not None


def test_i5_lineage_stays_distinct_from_relationship(managers):
    """I5 — o índice não colapsa `LineageEdge` e `Relationship` num
    "edge" genérico: continuam em namespaces/repositórios distintos,
    com taxonomias disjuntas."""
    session, objects, _ = managers
    parent = _add(objects, session)
    child = _add(objects, session)

    lineage = LineageRepository(session)
    lineage.add_edge(
        parent_coid=parent.id, child_coid=child.id, relation_type=LineageRelation.DERIVED_FROM
    )
    relationships = RelationshipRepository(session)
    relationships.add_relationship(
        source_coid=parent.id,
        target_coid=child.id,
        relationship_type=RelationshipType.REFERENCES,
    )
    session.flush()

    assert {type(e).__name__ for e in lineage.list_children(parent.id)} == {"LineageEdge"}
    assert {type(r).__name__ for r in relationships.outgoing(parent.id)} == {"Relationship"}
    assert not set(LineageRelation) & set(RelationshipType)


def test_i6_retired_relationship_does_not_erase_history(managers):
    """I6 — retirar uma `Relationship` não apaga histórico: a linha
    continua persistida e recuperável."""
    session, objects, _ = managers
    a = _add(objects, session)
    b = _add(objects, session)
    relationships = RelationshipRepository(session)
    rel = relationships.add_relationship(
        source_coid=a.id, target_coid=b.id, relationship_type=RelationshipType.SUPPORTS
    )
    session.flush()

    relationships.retire(rel)
    session.flush()

    assert relationships.outgoing(a.id) == []
    assert [r.id for r in relationships.outgoing(a.id, include_retired=True)] == [rel.id]


def test_i7_trace_id_is_not_a_cognitive_identity(managers):
    """I7 — `trace_id` localiza, não identifica: dois objetos
    distintos podem compartilhá-lo, e ele não vira COID/CLID."""
    session, objects, index = managers
    first = _add(objects, session)
    second = _add(objects, session)
    provenance = ProvenanceManager(ProvenanceRepository(session))
    for obj in (first, second):
        provenance.record(
            coid=obj.id,
            source_type=ProvenanceSourceType.AGENT,
            actor_type=ProvenanceActorType.AGENT,
            trace_id="trace-compartilhado",
        )
    session.flush()

    found = index.by_trace_id("trace-compartilhado")

    assert {o.id for o in found} == {first.id, second.id}
    assert first.clid is None and second.clid is None
    assert first.id != second.id


def test_i7b_same_object_with_two_provenance_records_is_not_duplicated(managers):
    """I7 (complemento) — dois `ProvenanceRecord`s com o mesmo
    `trace_id` para o mesmo objeto devolvem o objeto uma única vez."""
    session, objects, index = managers
    obj = _add(objects, session)
    provenance = ProvenanceManager(ProvenanceRepository(session))
    for actor in (ProvenanceActorType.AGENT, ProvenanceActorType.HUMAN):
        provenance.record(
            coid=obj.id,
            source_type=ProvenanceSourceType.AGENT,
            actor_type=actor,
            trace_id="trace-duplo",
        )
    session.flush()

    assert [o.id for o in index.by_trace_id("trace-duplo")] == [obj.id]


@pytest.mark.parametrize("blank", ["", "   "])
def test_i7c_blank_trace_id_is_a_caller_error(managers, blank):
    """`trace_id` em branco é erro de chamada, não consulta vazia —
    `ValueError`, sem introduzir código `PIA-8xxx` novo."""
    _, _, index = managers

    with pytest.raises(ValueError, match="trace_id"):
        index.by_trace_id(blank)


def test_i8_index_does_not_create_cognitive_objects(managers):
    """I8 — consultar não cria objeto algum."""
    session, objects, index = managers
    _add(objects, session)
    before = len(objects.list())

    index.by_coid(uuid.uuid4())
    index.by_clid(uuid.uuid4())
    index.by_accessibility(AccessibilityState.LATENT)
    index.by_revision_status(RevisionStatus.CURRENT)
    index.by_trace_id("inexistente")

    assert len(objects.list()) == before


def test_i9_index_does_not_mutate_the_source(managers):
    """I9 — nenhuma consulta altera COID, CLID, accessibility ou
    revision_status da fonte."""
    session, objects, index = managers
    clid = uuid.uuid4()
    obj = _add(
        objects,
        session,
        clid=clid,
        accessibility=AccessibilityState.LATENT,
        revision_status=RevisionStatus.CURRENT,
    )
    before = (obj.id, obj.clid, obj.accessibility, obj.revision_status)

    index.by_coid(obj.id)
    index.by_clid(clid)
    index.by_accessibility(AccessibilityState.LATENT)
    index.by_revision_status(RevisionStatus.CURRENT)

    session.refresh(obj)
    assert (obj.id, obj.clid, obj.accessibility, obj.revision_status) == before


def test_i10_absence_from_a_query_does_not_erase_the_source(managers):
    """I10 — ausência numa consulta não apaga a fonte: após soft
    delete o objeto some das consultas padrão e continua recuperável
    com `include_deleted=True`."""
    session, objects, index = managers
    clid = uuid.uuid4()
    obj = _add(objects, session, clid=clid, accessibility=AccessibilityState.ACTIVE)

    objects.soft_delete(obj)
    session.flush()

    assert index.by_coid(obj.id) is None
    assert index.by_clid(clid) == []
    assert index.by_accessibility(AccessibilityState.ACTIVE) == []

    assert index.by_coid(obj.id, include_deleted=True) is not None
    assert [o.id for o in index.by_clid(clid, include_deleted=True)] == [obj.id]
    assert [
        o.id for o in index.by_accessibility(AccessibilityState.ACTIVE, include_deleted=True)
    ] == [obj.id]


def test_i10b_soft_deleted_objects_remain_reachable_by_revision_and_trace(managers):
    """I10 (complemento) — o mesmo vale para as demais dimensões."""
    session, objects, index = managers
    obj = _add(objects, session, clid=uuid.uuid4(), revision_status=RevisionStatus.CURRENT)
    ProvenanceManager(ProvenanceRepository(session)).record(
        coid=obj.id,
        source_type=ProvenanceSourceType.SYSTEM,
        actor_type=ProvenanceActorType.SYSTEM,
        trace_id="trace-soft-delete",
    )
    session.flush()
    objects.soft_delete(obj)
    session.flush()

    assert index.by_revision_status(RevisionStatus.CURRENT) == []
    assert index.by_trace_id("trace-soft-delete") == []
    assert [
        o.id for o in index.by_revision_status(RevisionStatus.CURRENT, include_deleted=True)
    ] == [obj.id]
    assert [o.id for o in index.by_trace_id("trace-soft-delete", include_deleted=True)] == [obj.id]


def test_i13_index_returns_entities_not_copies(managers):
    """I13 — nenhuma duplicação de patrimônio: o índice devolve a
    própria entidade persistida, não uma cópia materializada."""
    session, objects, index = managers
    clid = uuid.uuid4()
    obj = _add(objects, session, clid=clid)

    (located,) = index.by_clid(clid)

    assert located is obj


def test_limit_is_honoured_on_both_bounded_dimensions(managers):
    """`limit` corta o resultado sem alterar a ordenação
    determinística."""
    session, objects, index = managers
    created = [
        _add(objects, session, accessibility=AccessibilityState.ACTIVE, clid=uuid.uuid4())
        for _ in range(3)
    ]
    for obj in created:
        obj.revision_status = RevisionStatus.CURRENT
    session.flush()

    ordered = [o.id for o in index.by_accessibility(AccessibilityState.ACTIVE)]

    assert [o.id for o in index.by_accessibility(AccessibilityState.ACTIVE, limit=2)] == ordered[:2]
    assert [o.id for o in index.by_revision_status(RevisionStatus.CURRENT, limit=1)] == ordered[:1]


def test_ordering_is_deterministic_by_created_at_then_id(managers):
    """A ordenação canônica do projeto (`created_at ASC, id ASC`,
    E3.1.2) vale em todas as dimensões do índice — nunca ordem
    indefinida do banco."""
    session, objects, index = managers
    clid = uuid.uuid4()
    older = _add(objects, session, clid=clid)
    newer = _add(objects, session, clid=clid)
    older.created_at = datetime(2020, 1, 1, tzinfo=UTC)
    newer.created_at = datetime(2020, 1, 2, tzinfo=UTC)
    session.flush()

    assert [o.id for o in index.by_clid(clid)] == [older.id, newer.id]

    older.created_at, newer.created_at = newer.created_at, older.created_at
    session.flush()

    assert [o.id for o in index.by_clid(clid)] == [newer.id, older.id]
