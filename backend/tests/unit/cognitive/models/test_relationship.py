"""Testes de `Relationship` — validação estrutural mínima."""

import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.cognitive.models.cognitive_object import CognitiveObject
from app.cognitive.models.enums import RelationshipType
from app.cognitive.models.relationship import Relationship


def test_creates_with_required_fields(cognitive_session):
    a = CognitiveObject()
    b = CognitiveObject()
    cognitive_session.add_all([a, b])
    cognitive_session.commit()

    rel = Relationship(
        source_coid=a.id, target_coid=b.id, relationship_type=RelationshipType.SUPPORTS
    )
    cognitive_session.add(rel)
    cognitive_session.commit()
    cognitive_session.refresh(rel)

    assert rel.id is not None
    assert rel.source_coid == a.id
    assert rel.target_coid == b.id
    assert rel.relationship_type == RelationshipType.SUPPORTS
    assert rel.retired_at is None
    assert rel.created_at is not None


def test_relationship_type_accepts_all_five_documented_values(cognitive_session):
    a = CognitiveObject()
    targets = [CognitiveObject() for _ in RelationshipType]
    cognitive_session.add_all([a, *targets])
    cognitive_session.commit()

    for rel_type, target in zip(RelationshipType, targets, strict=True):
        # RELATED_TO exige ordem canônica (source_coid < target_coid)
        # desde a correção E3.5.1 (CheckConstraint estrutural) — demais
        # tipos são direcionados e aceitam qualquer ordem.
        source, dest = (
            (a.id, target.id)
            if not rel_type.is_symmetric or str(a.id) < str(target.id)
            else (target.id, a.id)
        )
        rel = Relationship(source_coid=source, target_coid=dest, relationship_type=rel_type)
        cognitive_session.add(rel)
    cognitive_session.commit()

    assert cognitive_session.query(Relationship).count() == len(RelationshipType)


def test_self_link_rejected_by_check_constraint(cognitive_session):
    obj = CognitiveObject()
    cognitive_session.add(obj)
    cognitive_session.commit()

    rel = Relationship(
        source_coid=obj.id, target_coid=obj.id, relationship_type=RelationshipType.SUPPORTS
    )
    cognitive_session.add(rel)
    with pytest.raises(IntegrityError):
        cognitive_session.commit()
    cognitive_session.rollback()


def test_duplicate_triple_rejected_by_unique_constraint(cognitive_session):
    a = CognitiveObject()
    b = CognitiveObject()
    cognitive_session.add_all([a, b])
    cognitive_session.commit()

    r1 = Relationship(
        source_coid=a.id, target_coid=b.id, relationship_type=RelationshipType.SUPPORTS
    )
    cognitive_session.add(r1)
    cognitive_session.commit()

    r2 = Relationship(
        source_coid=a.id, target_coid=b.id, relationship_type=RelationshipType.SUPPORTS
    )
    cognitive_session.add(r2)
    with pytest.raises(IntegrityError):
        cognitive_session.commit()
    cognitive_session.rollback()


def test_different_relationship_type_between_same_pair_is_allowed(cognitive_session):
    a = CognitiveObject()
    b = CognitiveObject()
    cognitive_session.add_all([a, b])
    cognitive_session.commit()

    r1 = Relationship(
        source_coid=a.id, target_coid=b.id, relationship_type=RelationshipType.SUPPORTS
    )
    r2 = Relationship(
        source_coid=a.id, target_coid=b.id, relationship_type=RelationshipType.REFERENCES
    )
    cognitive_session.add_all([r1, r2])
    cognitive_session.commit()

    assert cognitive_session.query(Relationship).count() == 2


def test_foreign_key_violation_rejects_nonexistent_endpoint(cognitive_session):
    target = CognitiveObject()
    cognitive_session.add(target)
    cognitive_session.commit()

    ghost = Relationship(
        source_coid=uuid.uuid4(), target_coid=target.id, relationship_type=RelationshipType.SUPPORTS
    )
    cognitive_session.add(ghost)
    with pytest.raises(IntegrityError):
        cognitive_session.commit()
    cognitive_session.rollback()


def test_only_related_to_is_symmetric():
    assert RelationshipType.RELATED_TO.is_symmetric is True
    for rel_type in RelationshipType:
        if rel_type is RelationshipType.RELATED_TO:
            continue
        assert rel_type.is_symmetric is False
