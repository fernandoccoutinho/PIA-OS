"""Testes de `LineageEdge` — validação estrutural mínima do modelo."""

import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.cognitive.models.cognitive_object import CognitiveObject
from app.cognitive.models.enums import LineageRelation
from app.cognitive.models.lineage_edge import LineageEdge


def test_creates_with_all_required_fields(cognitive_session):
    parent = CognitiveObject()
    child = CognitiveObject()
    cognitive_session.add_all([parent, child])
    cognitive_session.commit()

    edge = LineageEdge(
        parent_coid=parent.id, child_coid=child.id, relation_type=LineageRelation.DERIVED_FROM
    )
    cognitive_session.add(edge)
    cognitive_session.commit()
    cognitive_session.refresh(edge)

    assert edge.id is not None
    assert edge.parent_coid == parent.id
    assert edge.child_coid == child.id
    assert edge.relation_type == LineageRelation.DERIVED_FROM
    assert edge.created_at is not None


def test_relation_type_accepts_all_six_documented_values(cognitive_session):
    """Taxonomia completa de `LineageRelation` já congelada no Domain
    Model Draft — todos os 6 valores devem ser aceitos pela coluna."""
    parent = CognitiveObject()
    children = [CognitiveObject() for _ in LineageRelation]
    cognitive_session.add_all([parent, *children])
    cognitive_session.commit()

    for relation, child in zip(LineageRelation, children, strict=True):
        edge = LineageEdge(parent_coid=parent.id, child_coid=child.id, relation_type=relation)
        cognitive_session.add(edge)
    cognitive_session.commit()

    assert cognitive_session.query(LineageEdge).count() == len(LineageRelation)


def test_self_link_rejected_by_check_constraint(cognitive_session):
    """Defesa em profundidade a nível de banco — o guard de domínio
    (`LineageRepository.add_edge`) é a primeira linha de defesa; este
    teste confirma que a `CHECK` constraint também protege, no caso de
    manipulação direta do modelo que ignore o repositório."""
    obj = CognitiveObject()
    cognitive_session.add(obj)
    cognitive_session.commit()

    edge = LineageEdge(
        parent_coid=obj.id, child_coid=obj.id, relation_type=LineageRelation.DERIVED_FROM
    )
    cognitive_session.add(edge)
    with pytest.raises(IntegrityError):
        cognitive_session.commit()
    cognitive_session.rollback()


def test_duplicate_triple_rejected_by_unique_constraint(cognitive_session):
    parent = CognitiveObject()
    child = CognitiveObject()
    cognitive_session.add_all([parent, child])
    cognitive_session.commit()

    edge1 = LineageEdge(
        parent_coid=parent.id, child_coid=child.id, relation_type=LineageRelation.DERIVED_FROM
    )
    cognitive_session.add(edge1)
    cognitive_session.commit()

    edge2 = LineageEdge(
        parent_coid=parent.id, child_coid=child.id, relation_type=LineageRelation.DERIVED_FROM
    )
    cognitive_session.add(edge2)
    with pytest.raises(IntegrityError):
        cognitive_session.commit()
    cognitive_session.rollback()


def test_different_relation_type_between_same_pair_is_allowed(cognitive_session):
    """A unique constraint é sobre a tripla completa — uma relação
    *diferente* entre os mesmos dois objetos continua permitida."""
    parent = CognitiveObject()
    child = CognitiveObject()
    cognitive_session.add_all([parent, child])
    cognitive_session.commit()

    e1 = LineageEdge(
        parent_coid=parent.id, child_coid=child.id, relation_type=LineageRelation.DERIVED_FROM
    )
    e2 = LineageEdge(
        parent_coid=parent.id, child_coid=child.id, relation_type=LineageRelation.BRANCH
    )
    cognitive_session.add_all([e1, e2])
    cognitive_session.commit()  # não deve levantar

    assert cognitive_session.query(LineageEdge).count() == 2


def test_foreign_key_violation_rejects_nonexistent_endpoint(cognitive_session):
    child = CognitiveObject()
    cognitive_session.add(child)
    cognitive_session.commit()

    ghost = LineageEdge(
        parent_coid=uuid.uuid4(), child_coid=child.id, relation_type=LineageRelation.BRANCH
    )
    cognitive_session.add(ghost)
    with pytest.raises(IntegrityError):
        cognitive_session.commit()
    cognitive_session.rollback()
