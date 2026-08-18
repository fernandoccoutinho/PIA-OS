"""
Testes dos dois débitos fechados pela correção E3.5.1 — unicidade
compatível com soft-retire (C1, U1-U4) e garantia estrutural de
simetria de `RELATED_TO` (C2, S1-S2).
"""

import pytest
from sqlalchemy.exc import IntegrityError

from app.cognitive.errors.exceptions import RelationshipDuplicateError
from app.cognitive.models.cognitive_object import CognitiveObject
from app.cognitive.models.enums import RelationshipType
from app.cognitive.models.relationship import Relationship
from app.cognitive.repositories.object_repository import ObjectRepository
from app.cognitive.repositories.relationship_repository import RelationshipRepository


@pytest.fixture
def objects(cognitive_session):
    return ObjectRepository(cognitive_session)


@pytest.fixture
def relationships(cognitive_session):
    return RelationshipRepository(cognitive_session)


# --- C1 / U1-U4: unicidade compatível com soft-retire ---


def test_u1_active_duplicate_is_rejected(objects, relationships, cognitive_session):
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


def test_u2_retired_relation_allows_redeclaration(objects, relationships, cognitive_session):
    """O ciclo aprovado no lifecycle: `create` -> `retire` -> `create`
    novamente com os mesmos endpoints/tipo é permitido."""
    a = objects.add(CognitiveObject())
    b = objects.add(CognitiveObject())
    cognitive_session.commit()

    old = relationships.add_relationship(
        source_coid=a.id, target_coid=b.id, relationship_type=RelationshipType.SUPPORTS
    )
    cognitive_session.commit()

    relationships.retire(old)
    cognitive_session.commit()

    new = relationships.add_relationship(
        source_coid=a.id, target_coid=b.id, relationship_type=RelationshipType.SUPPORTS
    )
    cognitive_session.commit()  # não deve levantar

    assert new.id != old.id
    assert new.retired_at is None


def test_u3_retired_history_remains_recoverable(objects, relationships, cognitive_session):
    a = objects.add(CognitiveObject())
    b = objects.add(CognitiveObject())
    cognitive_session.commit()

    old = relationships.add_relationship(
        source_coid=a.id, target_coid=b.id, relationship_type=RelationshipType.SUPPORTS
    )
    cognitive_session.commit()
    old_id = old.id

    relationships.retire(old)
    cognitive_session.commit()

    relationships.add_relationship(
        source_coid=a.id, target_coid=b.id, relationship_type=RelationshipType.SUPPORTS
    )
    cognitive_session.commit()

    reloaded_old = relationships.get_by_id(old_id)
    assert reloaded_old is not None
    assert reloaded_old.retired_at is not None
    assert reloaded_old.source_coid == a.id
    assert reloaded_old.target_coid == b.id

    # aparece via include_retired, mas não na navegação padrão
    assert old_id not in {r.id for r in relationships.outgoing(a.id)}
    assert old_id in {r.id for r in relationships.outgoing(a.id, include_retired=True)}


def test_u_only_one_active_relationship_exists_after_retire_and_recreate(
    objects, relationships, cognitive_session
):
    a = objects.add(CognitiveObject())
    b = objects.add(CognitiveObject())
    cognitive_session.commit()

    old = relationships.add_relationship(
        source_coid=a.id, target_coid=b.id, relationship_type=RelationshipType.SUPPORTS
    )
    cognitive_session.commit()
    relationships.retire(old)
    cognitive_session.commit()
    relationships.add_relationship(
        source_coid=a.id, target_coid=b.id, relationship_type=RelationshipType.SUPPORTS
    )
    cognitive_session.commit()

    all_including_retired = relationships.outgoing(a.id, include_retired=True)
    active = [r for r in all_including_retired if r.retired_at is None]
    assert len(all_including_retired) == 2
    assert len(active) == 1


# --- C2 / S1-S2: garantia estrutural de simetria ---


def test_s1_canonical_path_rejects_reverse_duplicate(objects, relationships, cognitive_session):
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


def test_s2_direct_bypass_of_repository_is_rejected_by_database(objects, cognitive_session):
    """Contornando `RelationshipRepository` inteiramente (construção
    direta do modelo, sem a normalização de ordem) — o banco rejeita
    a forma não-canônica via `CheckConstraint`, confirmando que a
    garantia é `DB_LEVEL`, não apenas do caminho canônico do
    repositório."""
    a = objects.add(CognitiveObject())
    b = objects.add(CognitiveObject())
    cognitive_session.commit()

    lo, hi = (a.id, b.id) if str(a.id) < str(b.id) else (b.id, a.id)

    canonical = Relationship(
        source_coid=lo, target_coid=hi, relationship_type=RelationshipType.RELATED_TO
    )
    cognitive_session.add(canonical)
    cognitive_session.commit()

    non_canonical = Relationship(
        source_coid=hi, target_coid=lo, relationship_type=RelationshipType.RELATED_TO
    )
    cognitive_session.add(non_canonical)
    with pytest.raises(IntegrityError):
        cognitive_session.commit()
    cognitive_session.rollback()


def test_s2_bypass_of_non_symmetric_type_does_not_trigger_canonical_check(
    objects, cognitive_session
):
    """O `CheckConstraint` de ordem canônica só se aplica a
    `RELATED_TO` — tipos direcionados não são afetados, mesmo com
    `source_coid > target_coid`."""
    a = objects.add(CognitiveObject())
    b = objects.add(CognitiveObject())
    cognitive_session.commit()

    hi, lo = (a.id, b.id) if str(a.id) > str(b.id) else (b.id, a.id)

    rel = Relationship(source_coid=hi, target_coid=lo, relationship_type=RelationshipType.SUPPORTS)
    cognitive_session.add(rel)
    cognitive_session.commit()  # não deve levantar — SUPPORTS é direcionado

    assert rel.source_coid == hi
    assert rel.target_coid == lo
