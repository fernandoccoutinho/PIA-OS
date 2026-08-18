"""
Testes de `AccessibilityManager` — §21 do módulo E3.6 (A1-A10).
"""

import pytest

from app.cognitive.errors.exceptions import AccessibilityInvalidTransitionError
from app.cognitive.models.cognitive_object import CognitiveObject
from app.cognitive.models.enums import (
    AccessibilityState,
    LineageRelation,
    ProvenanceActorType,
    ProvenanceSourceType,
    RevisionStatus,
)
from app.cognitive.repositories.lineage_repository import LineageRepository
from app.cognitive.repositories.object_repository import ObjectRepository
from app.cognitive.repositories.provenance_repository import ProvenanceRepository
from app.cognitive.services.accessibility_manager import AccessibilityManager
from app.cognitive.services.clid_manager import ClidManager
from app.cognitive.services.provenance_manager import ProvenanceManager


@pytest.fixture
def objects(cognitive_session):
    return ObjectRepository(cognitive_session)


@pytest.fixture
def lineage(cognitive_session):
    return LineageRepository(cognitive_session)


@pytest.fixture
def manager(objects):
    return AccessibilityManager(objects)


# --- A1-A10 ---


def test_a1_read_current_state(objects, manager, cognitive_session):
    obj = objects.add(CognitiveObject())
    cognitive_session.commit()
    assert manager.get_state(obj) == AccessibilityState.ACTIVE


def test_a2_valid_transition(objects, manager, cognitive_session):
    obj = objects.add(CognitiveObject())
    cognitive_session.commit()

    manager.transition(obj, AccessibilityState.LATENT)
    cognitive_session.commit()
    assert obj.accessibility == AccessibilityState.LATENT


def test_a3_invalid_transition_rejected(objects, manager, cognitive_session):
    """Único caso restrito nesta fase: `CAUSALLY_EXTINCT` sem
    `reason` (a matriz completa de autoridade é `E4`, não antecipada
    aqui — ver docstring de `AccessibilityManager`)."""
    obj = objects.add(CognitiveObject())
    cognitive_session.commit()

    with pytest.raises(AccessibilityInvalidTransitionError) as exc_info:
        manager.transition(obj, AccessibilityState.CAUSALLY_EXTINCT)
    assert exc_info.value.code == "PIA-8018"


def test_a4_idempotent_transition_is_valid(objects, manager, cognitive_session):
    obj = objects.add(CognitiveObject())
    cognitive_session.commit()

    manager.transition(obj, AccessibilityState.ACTIVE)
    cognitive_session.commit()
    assert obj.accessibility == AccessibilityState.ACTIVE


def test_a4_idempotent_transition_to_causally_extinct_does_not_require_reason(
    objects, manager, cognitive_session
):
    """Idempotência tem precedência sobre a exigência de `reason` —
    se já está em `CAUSALLY_EXTINCT`, reafirmar o mesmo estado não
    exige justificativa nova."""
    obj = objects.add(CognitiveObject())
    cognitive_session.commit()
    manager.transition(obj, AccessibilityState.CAUSALLY_EXTINCT, reason="motivo original")
    cognitive_session.commit()

    manager.transition(obj, AccessibilityState.CAUSALLY_EXTINCT)
    assert obj.accessibility == AccessibilityState.CAUSALLY_EXTINCT


def test_a5_object_historically_preserved_after_becoming_inaccessible(
    objects, manager, cognitive_session
):
    obj = objects.add(CognitiveObject())
    cognitive_session.commit()
    obj_id = obj.id

    manager.transition(obj, AccessibilityState.INACCESSIBLE)
    cognitive_session.commit()

    reloaded = objects.get_by_id(obj_id)
    assert reloaded is not None
    assert reloaded.accessibility == AccessibilityState.INACCESSIBLE


def test_a6_revision_status_not_altered(objects, manager, cognitive_session):
    obj = objects.add(CognitiveObject())
    cognitive_session.commit()
    obj.revision_status = RevisionStatus.CURRENT
    cognitive_session.commit()

    manager.transition(obj, AccessibilityState.LATENT)
    cognitive_session.commit()

    assert obj.revision_status == RevisionStatus.CURRENT


def test_a7_clid_not_altered(objects, lineage, manager, cognitive_session):
    obj = objects.add(CognitiveObject())
    cognitive_session.commit()
    clid_mgr = ClidManager(objects, lineage)
    clid_mgr.assign(obj, clid_mgr.generate())
    cognitive_session.commit()
    original_clid = obj.clid

    manager.transition(obj, AccessibilityState.LATENT)
    cognitive_session.commit()

    assert obj.clid == original_clid


def test_a8_coid_not_altered(objects, manager, cognitive_session):
    obj = objects.add(CognitiveObject())
    cognitive_session.commit()
    original_id = obj.id

    manager.transition(obj, AccessibilityState.LATENT)
    cognitive_session.commit()

    assert obj.id == original_id


def test_a9_lineage_not_altered(objects, lineage, manager, cognitive_session):
    a = objects.add(CognitiveObject())
    b = objects.add(CognitiveObject())
    cognitive_session.commit()
    lineage.add_edge(parent_coid=a.id, child_coid=b.id, relation_type=LineageRelation.DERIVED_FROM)
    cognitive_session.commit()

    manager.transition(a, AccessibilityState.LATENT)
    cognitive_session.commit()

    assert len(lineage.list_children(a.id)) == 1


def test_a10_previous_provenance_not_altered(objects, manager, cognitive_session):
    obj = objects.add(CognitiveObject())
    cognitive_session.commit()

    prov_repo = ProvenanceRepository(cognitive_session)
    prov_mgr = ProvenanceManager(prov_repo)
    rec = prov_mgr.record(
        coid=obj.id, source_type=ProvenanceSourceType.AGENT, actor_type=ProvenanceActorType.AGENT
    )
    cognitive_session.commit()
    rec_created_at = rec.created_at

    manager.transition(obj, AccessibilityState.LATENT)
    cognitive_session.commit()

    assert rec.created_at == rec_created_at
    assert prov_mgr.list_for(obj.id)[0].id == rec.id


# --- assert_accessible / não commit ---


def test_assert_accessible_passes_for_active(objects, manager, cognitive_session):
    obj = objects.add(CognitiveObject())
    cognitive_session.commit()
    manager.assert_accessible(obj)


def test_assert_accessible_passes_for_latent(objects, manager, cognitive_session):
    obj = objects.add(CognitiveObject())
    cognitive_session.commit()
    manager.transition(obj, AccessibilityState.LATENT)
    cognitive_session.commit()
    manager.assert_accessible(obj)


def test_assert_accessible_rejects_inaccessible(objects, manager, cognitive_session):
    obj = objects.add(CognitiveObject())
    cognitive_session.commit()
    manager.transition(obj, AccessibilityState.INACCESSIBLE)
    cognitive_session.commit()
    with pytest.raises(ValueError):
        manager.assert_accessible(obj)


def test_manager_does_not_commit(objects, manager, cognitive_session):
    obj = objects.add(CognitiveObject())
    cognitive_session.commit()

    manager.transition(obj, AccessibilityState.LATENT)
    cognitive_session.rollback()

    reloaded = objects.get_by_id(obj.id)
    assert reloaded.accessibility == AccessibilityState.ACTIVE
