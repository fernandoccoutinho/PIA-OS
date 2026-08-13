"""
Testes de `RelationshipRepository` — §32-§36 do módulo E3.5
(CR1-CR8, TY1-TY6, NV1-NV7, LS1-LS6).
"""

import uuid

import pytest

from app.cognitive.errors.exceptions import (
    RelationshipDuplicateError,
    RelationshipEndpointNotFoundError,
    RelationshipImmutableError,
    RelationshipSelfLinkError,
)
from app.cognitive.models.cognitive_object import CognitiveObject
from app.cognitive.models.enums import LineageRelation, RelationshipType
from app.cognitive.repositories.lineage_repository import LineageRepository
from app.cognitive.repositories.object_repository import ObjectRepository
from app.cognitive.repositories.relationship_repository import RelationshipRepository


@pytest.fixture
def objects(cognitive_session):
    return ObjectRepository(cognitive_session)


@pytest.fixture
def relationships(cognitive_session):
    return RelationshipRepository(cognitive_session)


@pytest.fixture
def lineage(cognitive_session):
    return LineageRepository(cognitive_session)


# --- CR1-CR8: criação ---


def test_cr1_valid_relationship_is_created(objects, relationships, cognitive_session):
    a = objects.add(CognitiveObject())
    b = objects.add(CognitiveObject())
    cognitive_session.commit()

    rel = relationships.add_relationship(
        source_coid=a.id, target_coid=b.id, relationship_type=RelationshipType.SUPPORTS
    )
    cognitive_session.commit()
    assert rel.id is not None


def test_cr2_and_cr3_nonexistent_endpoint_is_rejected(objects, relationships, cognitive_session):
    existing = objects.add(CognitiveObject())
    cognitive_session.commit()

    with pytest.raises(RelationshipEndpointNotFoundError) as exc_info:
        relationships.add_relationship(
            source_coid=uuid.uuid4(),
            target_coid=existing.id,
            relationship_type=RelationshipType.REFERENCES,
        )
    assert exc_info.value.code == "PIA-8015"
    cognitive_session.rollback()

    with pytest.raises(RelationshipEndpointNotFoundError):
        relationships.add_relationship(
            source_coid=existing.id,
            target_coid=uuid.uuid4(),
            relationship_type=RelationshipType.REFERENCES,
        )
    cognitive_session.rollback()


def test_cr4_invalid_type_is_rejected_by_python_enum(objects, relationships, cognitive_session):
    """`RelationshipType` é um `StrEnum` — passar um valor fora da
    taxonomia levanta `ValueError`/`AttributeError` no nível do
    Python antes mesmo de chegar ao repositório (nenhum bypass)."""
    with pytest.raises((ValueError, AttributeError)):
        RelationshipType("not_a_real_type")


def test_cr5_duplicate_directed_relationship_is_rejected(objects, relationships, cognitive_session):
    a = objects.add(CognitiveObject())
    b = objects.add(CognitiveObject())
    cognitive_session.commit()

    relationships.add_relationship(
        source_coid=a.id, target_coid=b.id, relationship_type=RelationshipType.SUPPORTS
    )
    cognitive_session.commit()

    with pytest.raises(RelationshipDuplicateError) as exc_info:
        relationships.add_relationship(
            source_coid=a.id, target_coid=b.id, relationship_type=RelationshipType.SUPPORTS
        )
    assert exc_info.value.code == "PIA-8014"
    cognitive_session.rollback()


def test_cr5_duplicate_symmetric_relationship_rejected_regardless_of_order(
    objects, relationships, cognitive_session
):
    a = objects.add(CognitiveObject())
    b = objects.add(CognitiveObject())
    cognitive_session.commit()

    relationships.add_relationship(
        source_coid=a.id, target_coid=b.id, relationship_type=RelationshipType.RELATED_TO
    )
    cognitive_session.commit()

    with pytest.raises(RelationshipDuplicateError):
        relationships.add_relationship(
            source_coid=b.id, target_coid=a.id, relationship_type=RelationshipType.RELATED_TO
        )
    cognitive_session.rollback()


def test_cr6_self_relation_follows_defined_policy(objects, relationships, cognitive_session):
    a = objects.add(CognitiveObject())
    cognitive_session.commit()

    for rel_type in RelationshipType:
        with pytest.raises(RelationshipSelfLinkError) as exc_info:
            relationships.add_relationship(
                source_coid=a.id, target_coid=a.id, relationship_type=rel_type
            )
        assert exc_info.value.code == "PIA-8013"


def test_cr7_rollback_does_not_leave_partial_relationship(
    objects, relationships, cognitive_session
):
    a = objects.add(CognitiveObject())
    cognitive_session.commit()

    with pytest.raises(RelationshipSelfLinkError):
        relationships.add_relationship(
            source_coid=a.id, target_coid=a.id, relationship_type=RelationshipType.SUPPORTS
        )

    assert len(relationships.outgoing(a.id)) == 0


def test_cr8_commit_remains_caller_responsibility(objects, relationships, cognitive_session):
    a = objects.add(CognitiveObject())
    b = objects.add(CognitiveObject())
    cognitive_session.commit()

    relationships.add_relationship(
        source_coid=a.id, target_coid=b.id, relationship_type=RelationshipType.SUPPORTS
    )
    # sem commit explícito ainda — a linha existe na sessão (flush),
    # mas nada garante persistência além dela até o caller commitar
    cognitive_session.rollback()

    assert len(relationships.outgoing(a.id)) == 0  # rollback desfez, confirma que não commitou


# --- TY1-TY6: tipos ---


def test_ty1_types_have_explicit_semantics():
    """Cada tipo tem `is_symmetric` bem definido — semântica explícita,
    não implícita."""
    for rel_type in RelationshipType:
        assert isinstance(rel_type.is_symmetric, bool)


def test_ty2_directed_type_does_not_create_inverse_automatically(
    objects, relationships, cognitive_session
):
    a = objects.add(CognitiveObject())
    b = objects.add(CognitiveObject())
    cognitive_session.commit()

    relationships.add_relationship(
        source_coid=a.id, target_coid=b.id, relationship_type=RelationshipType.REFERENCES
    )
    cognitive_session.commit()

    assert relationships.relationship_exists(a.id, b.id, RelationshipType.REFERENCES) is True
    assert relationships.relationship_exists(b.id, a.id, RelationshipType.REFERENCES) is False


def test_ty3_symmetric_type_respects_ab_ba_equivalence(objects, relationships, cognitive_session):
    a = objects.add(CognitiveObject())
    b = objects.add(CognitiveObject())
    cognitive_session.commit()

    relationships.add_relationship(
        source_coid=a.id, target_coid=b.id, relationship_type=RelationshipType.RELATED_TO
    )
    cognitive_session.commit()

    assert relationships.relationship_exists(a.id, b.id, RelationshipType.RELATED_TO) is True
    assert relationships.relationship_exists(b.id, a.id, RelationshipType.RELATED_TO) is True


def test_ty4_relationship_type_does_not_overlap_lineage_relation():
    relationship_values = {t.value for t in RelationshipType}
    lineage_values = {t.value for t in LineageRelation}
    assert relationship_values.isdisjoint(lineage_values)


def test_ty5_no_type_implies_score_or_ranking():
    """Nenhum campo de score/ranking existe no modelo — inspeção
    estrutural das colunas reais."""
    from app.cognitive.models.relationship import Relationship as _Relationship

    columns = {c.name for c in _Relationship.__table__.columns}
    forbidden = {
        "score",
        "ranking",
        "relationship_score",
        "cout_score",
        "importance_score",
        "truth_score",
        "confidence_score",
        "relevance_score",
    }
    assert columns.isdisjoint(forbidden)


def test_ty6_contradictory_relationships_coexist(objects, relationships, cognitive_session):
    a = objects.add(CognitiveObject())
    x = objects.add(CognitiveObject())
    b = objects.add(CognitiveObject())
    cognitive_session.commit()

    relationships.add_relationship(
        source_coid=a.id, target_coid=x.id, relationship_type=RelationshipType.SUPPORTS
    )
    relationships.add_relationship(
        source_coid=b.id, target_coid=x.id, relationship_type=RelationshipType.CONTRADICTS
    )
    cognitive_session.commit()  # não deve levantar

    assert len(relationships.incoming(x.id)) == 2


# --- NV1-NV7: navegação ---


def test_nv1_outgoing_returns_correct_relationships(objects, relationships, cognitive_session):
    a = objects.add(CognitiveObject())
    b = objects.add(CognitiveObject())
    c = objects.add(CognitiveObject())
    cognitive_session.commit()
    relationships.add_relationship(
        source_coid=a.id, target_coid=b.id, relationship_type=RelationshipType.SUPPORTS
    )
    relationships.add_relationship(
        source_coid=a.id, target_coid=c.id, relationship_type=RelationshipType.REFERENCES
    )
    cognitive_session.commit()

    out = relationships.outgoing(a.id)
    assert {r.target_coid for r in out} == {b.id, c.id}


def test_nv2_incoming_returns_correct_relationships(objects, relationships, cognitive_session):
    a = objects.add(CognitiveObject())
    b = objects.add(CognitiveObject())
    c = objects.add(CognitiveObject())
    cognitive_session.commit()
    relationships.add_relationship(
        source_coid=a.id, target_coid=c.id, relationship_type=RelationshipType.SUPPORTS
    )
    relationships.add_relationship(
        source_coid=b.id, target_coid=c.id, relationship_type=RelationshipType.CONTRADICTS
    )
    cognitive_session.commit()

    inc = relationships.incoming(c.id)
    assert {r.source_coid for r in inc} == {a.id, b.id}


def test_nv3_filter_by_relationship_type_works(objects, relationships, cognitive_session):
    a = objects.add(CognitiveObject())
    b = objects.add(CognitiveObject())
    c = objects.add(CognitiveObject())
    cognitive_session.commit()
    relationships.add_relationship(
        source_coid=a.id, target_coid=b.id, relationship_type=RelationshipType.SUPPORTS
    )
    relationships.add_relationship(
        source_coid=a.id, target_coid=c.id, relationship_type=RelationshipType.CONTRADICTS
    )
    cognitive_session.commit()

    only_supports = relationships.outgoing(a.id, relationship_type=RelationshipType.SUPPORTS)
    assert [r.target_coid for r in only_supports] == [b.id]


def test_nv4_object_without_relationships_returns_empty_collection(objects, cognitive_session):
    isolated = objects.add(CognitiveObject())
    cognitive_session.commit()

    rels = RelationshipRepository(cognitive_session)
    assert rels.outgoing(isolated.id) == []
    assert rels.incoming(isolated.id) == []
    assert rels.neighbors(isolated.id) == []


def test_nv5_navigation_excludes_retired_relationships_by_default(
    objects, relationships, cognitive_session
):
    a = objects.add(CognitiveObject())
    b = objects.add(CognitiveObject())
    cognitive_session.commit()
    rel = relationships.add_relationship(
        source_coid=a.id, target_coid=b.id, relationship_type=RelationshipType.SUPPORTS
    )
    cognitive_session.commit()

    relationships.retire(rel)
    cognitive_session.commit()

    assert relationships.outgoing(a.id) == []
    assert relationships.outgoing(a.id, include_retired=True) != []


def test_nv6_ordering_is_deterministic(objects, relationships, cognitive_session):
    a = objects.add(CognitiveObject())
    targets = [objects.add(CognitiveObject()) for _ in range(6)]
    cognitive_session.commit()
    for t in targets:
        relationships.add_relationship(
            source_coid=a.id, target_coid=t.id, relationship_type=RelationshipType.RELATED_TO
        )
    cognitive_session.commit()

    run_1 = [r.id for r in relationships.outgoing(a.id)]
    run_2 = [r.id for r in relationships.outgoing(a.id)]
    assert run_1 == run_2


def test_nv7_no_infinite_traversal(objects, relationships, cognitive_session):
    """`neighbors()` é one-hop — mesmo com um ciclo estrutural
    (A->B, B->A, tipos diferentes), a chamada retorna e termina."""
    a = objects.add(CognitiveObject())
    b = objects.add(CognitiveObject())
    cognitive_session.commit()
    relationships.add_relationship(
        source_coid=a.id, target_coid=b.id, relationship_type=RelationshipType.SUPPORTS
    )
    relationships.add_relationship(
        source_coid=b.id, target_coid=a.id, relationship_type=RelationshipType.CONTRADICTS
    )
    cognitive_session.commit()

    result = relationships.neighbors(a.id)  # não deve travar/loopar
    assert len(result) == 2


# --- LS1-LS6: separação de Lineage ---


def test_ls1_creating_relationship_does_not_create_lineage_edge(
    objects, relationships, lineage, cognitive_session
):
    a = objects.add(CognitiveObject())
    b = objects.add(CognitiveObject())
    cognitive_session.commit()

    relationships.add_relationship(
        source_coid=a.id, target_coid=b.id, relationship_type=RelationshipType.SUPPORTS
    )
    cognitive_session.commit()

    assert lineage.list_children(a.id) == []


def test_ls2_creating_lineage_edge_does_not_create_relationship(
    objects, relationships, lineage, cognitive_session
):
    a = objects.add(CognitiveObject())
    b = objects.add(CognitiveObject())
    cognitive_session.commit()

    lineage.add_edge(parent_coid=a.id, child_coid=b.id, relation_type=LineageRelation.DERIVED_FROM)
    cognitive_session.commit()

    assert relationships.outgoing(a.id) == []


def test_ls3_and_ls4_relationship_does_not_alter_clid_or_coid(
    objects, relationships, cognitive_session
):
    a = objects.add(CognitiveObject())
    b = objects.add(CognitiveObject())
    cognitive_session.commit()
    original_a_id, original_a_clid = a.id, a.clid
    original_b_id, original_b_clid = b.id, b.clid

    relationships.add_relationship(
        source_coid=a.id, target_coid=b.id, relationship_type=RelationshipType.SUPPORTS
    )
    cognitive_session.commit()

    assert a.id == original_a_id
    assert b.id == original_b_id
    assert a.clid == original_a_clid
    assert b.clid == original_b_clid


def test_ls5_relationship_does_not_alter_revision_status(objects, relationships, cognitive_session):
    from app.cognitive.models.enums import RevisionStatus

    a = objects.add(CognitiveObject())
    b = objects.add(CognitiveObject())
    cognitive_session.commit()
    a.revision_status = RevisionStatus.CURRENT
    cognitive_session.commit()

    relationships.add_relationship(
        source_coid=a.id, target_coid=b.id, relationship_type=RelationshipType.SUPPORTS
    )
    cognitive_session.commit()

    assert a.revision_status == RevisionStatus.CURRENT
    assert b.revision_status is None


def test_ls6_relationship_does_not_create_transformation_record(
    objects, relationships, cognitive_session
):
    from app.cognitive.repositories.transformation_repository import TransformationRepository

    a = objects.add(CognitiveObject())
    b = objects.add(CognitiveObject())
    cognitive_session.commit()

    relationships.add_relationship(
        source_coid=a.id, target_coid=b.id, relationship_type=RelationshipType.SUPPORTS
    )
    cognitive_session.commit()

    trans = TransformationRepository(cognitive_session)
    assert trans.list_by_input_coid(a.id) == []
    assert trans.list_by_output_coid(b.id) == []


# --- Append-only / lifecycle ---


def test_update_is_rejected(objects, relationships, cognitive_session):
    a = objects.add(CognitiveObject())
    b = objects.add(CognitiveObject())
    cognitive_session.commit()
    rel = relationships.add_relationship(
        source_coid=a.id, target_coid=b.id, relationship_type=RelationshipType.SUPPORTS
    )
    cognitive_session.commit()

    with pytest.raises(RelationshipImmutableError) as exc_info:
        relationships.update(rel)
    assert exc_info.value.code == "PIA-8016"


def test_delete_is_rejected(objects, relationships, cognitive_session):
    a = objects.add(CognitiveObject())
    b = objects.add(CognitiveObject())
    cognitive_session.commit()
    rel = relationships.add_relationship(
        source_coid=a.id, target_coid=b.id, relationship_type=RelationshipType.SUPPORTS
    )
    cognitive_session.commit()

    with pytest.raises(RelationshipImmutableError) as exc_info:
        relationships.delete(rel)
    assert exc_info.value.code == "PIA-8016"


def test_retire_is_idempotent(objects, relationships, cognitive_session):
    a = objects.add(CognitiveObject())
    b = objects.add(CognitiveObject())
    cognitive_session.commit()
    rel = relationships.add_relationship(
        source_coid=a.id, target_coid=b.id, relationship_type=RelationshipType.SUPPORTS
    )
    cognitive_session.commit()

    first = relationships.retire(rel)
    cognitive_session.commit()
    second = relationships.retire(first)
    cognitive_session.commit()

    assert first.retired_at == second.retired_at


def test_retire_preserves_the_row_and_all_other_fields(objects, relationships, cognitive_session):
    a = objects.add(CognitiveObject())
    b = objects.add(CognitiveObject())
    cognitive_session.commit()
    rel = relationships.add_relationship(
        source_coid=a.id, target_coid=b.id, relationship_type=RelationshipType.SUPPORTS
    )
    cognitive_session.commit()
    rel_id = rel.id
    source, target, rel_type = rel.source_coid, rel.target_coid, rel.relationship_type

    relationships.retire(rel)
    cognitive_session.commit()

    reloaded = cognitive_session.get(type(rel), rel_id)
    assert reloaded is not None
    assert reloaded.source_coid == source
    assert reloaded.target_coid == target
    assert reloaded.relationship_type == rel_type
    assert reloaded.retired_at is not None


# --- Classificação de violação (sinal estruturado, isolado) ---


class _FakeDriverError:
    def __init__(self, *, sqlstate: str | None = None, sqlite_errorname: str | None = None):
        if sqlstate is not None:
            self.sqlstate = sqlstate
        if sqlite_errorname is not None:
            self.sqlite_errorname = sqlite_errorname


def _build_persistence_error(orig: object | None):
    from app.repositories.exceptions import PersistenceError

    cause = Exception()
    if orig is not None:
        cause.orig = orig  # type: ignore[attr-defined]
    try:
        raise PersistenceError("falha simulada") from cause
    except PersistenceError as exc:
        return exc


def test_classify_postgres_unique_violation():
    from app.cognitive.repositories.relationship_repository import (
        _classify_relationship_integrity_violation,
    )

    exc = _build_persistence_error(_FakeDriverError(sqlstate="23505"))
    assert _classify_relationship_integrity_violation(exc) == "unique"


def test_classify_postgres_foreign_key_violation():
    from app.cognitive.repositories.relationship_repository import (
        _classify_relationship_integrity_violation,
    )

    exc = _build_persistence_error(_FakeDriverError(sqlstate="23503"))
    assert _classify_relationship_integrity_violation(exc) == "foreign_key"


def test_classify_unrelated_sqlstate_returns_none():
    from app.cognitive.repositories.relationship_repository import (
        _classify_relationship_integrity_violation,
    )

    exc = _build_persistence_error(_FakeDriverError(sqlstate="23502"))
    assert _classify_relationship_integrity_violation(exc) is None


def test_classify_orig_none_returns_none():
    from app.cognitive.repositories.relationship_repository import (
        _classify_relationship_integrity_violation,
    )

    exc = _build_persistence_error(None)
    assert _classify_relationship_integrity_violation(exc) is None


def test_add_relationship_reraises_unrelated_persistence_error(monkeypatch, relationships):
    """Um `PersistenceError` cuja causa não é unicidade nem FK
    continua propagando sem reinterpretação (mesmo princípio de
    E3.2.1/E3.3)."""
    import uuid as _uuid

    from app.repositories.base_repository import BaseRepository
    from app.repositories.exceptions import PersistenceError

    fake_cause = Exception()
    fake_cause.orig = _FakeDriverError(sqlstate="23502")  # not_null, não coberto

    def _raise_unrelated(self, entity):
        raise PersistenceError("falha simulada não relacionada") from fake_cause

    monkeypatch.setattr(BaseRepository, "add", _raise_unrelated)

    with pytest.raises(PersistenceError) as exc_info:
        relationships.add_relationship(
            source_coid=_uuid.uuid4(),
            target_coid=_uuid.uuid4(),
            relationship_type=RelationshipType.SUPPORTS,
        )
    assert not isinstance(exc_info.value, RelationshipDuplicateError)
    assert not isinstance(exc_info.value, RelationshipEndpointNotFoundError)


def test_incoming_filters_by_type_and_include_retired(objects, relationships, cognitive_session):
    a = objects.add(CognitiveObject())
    b = objects.add(CognitiveObject())
    c = objects.add(CognitiveObject())
    cognitive_session.commit()
    rel = relationships.add_relationship(
        source_coid=a.id, target_coid=c.id, relationship_type=RelationshipType.SUPPORTS
    )
    relationships.add_relationship(
        source_coid=b.id, target_coid=c.id, relationship_type=RelationshipType.CONTRADICTS
    )
    cognitive_session.commit()

    only_supports = relationships.incoming(c.id, relationship_type=RelationshipType.SUPPORTS)
    assert [r.source_coid for r in only_supports] == [a.id]

    relationships.retire(rel)
    cognitive_session.commit()
    assert relationships.incoming(c.id, relationship_type=RelationshipType.SUPPORTS) == []
    assert (
        len(
            relationships.incoming(
                c.id, relationship_type=RelationshipType.SUPPORTS, include_retired=True
            )
        )
        == 1
    )
