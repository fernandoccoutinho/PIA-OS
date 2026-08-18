"""Testes de `revision_status` em `CognitiveObject` — correção E3.4.0."""

import pytest

from app.cognitive.errors.exceptions import RevisionStatusInvalidTransitionError
from app.cognitive.models.cognitive_object import CognitiveObject
from app.cognitive.models.enums import AccessibilityState, RevisionStatus


def test_revision_status_defaults_to_none(cognitive_session):
    obj = CognitiveObject()
    cognitive_session.add(obj)
    cognitive_session.commit()
    assert obj.revision_status is None


def test_none_to_current_permitted(cognitive_session):
    obj = CognitiveObject()
    cognitive_session.add(obj)
    cognitive_session.commit()

    obj.revision_status = RevisionStatus.CURRENT
    cognitive_session.commit()
    assert obj.revision_status == RevisionStatus.CURRENT


def test_none_to_superseded_permitted_as_implicit_chain_entry(cognitive_session):
    """`None -> SUPERSEDED` direto representa uma "Rev.0" que nunca foi
    formalmente marcada `CURRENT` antes de ser superada (§4 do prompt
    corretivo E3.4.0)."""
    obj = CognitiveObject()
    cognitive_session.add(obj)
    cognitive_session.commit()

    obj.revision_status = RevisionStatus.SUPERSEDED
    cognitive_session.commit()
    assert obj.revision_status == RevisionStatus.SUPERSEDED


def test_current_to_superseded_permitted(cognitive_session):
    obj = CognitiveObject()
    cognitive_session.add(obj)
    obj.revision_status = RevisionStatus.CURRENT
    cognitive_session.commit()

    obj.revision_status = RevisionStatus.SUPERSEDED
    cognitive_session.commit()
    assert obj.revision_status == RevisionStatus.SUPERSEDED


def test_superseded_to_current_rejected(cognitive_session):
    obj = CognitiveObject()
    cognitive_session.add(obj)
    obj.revision_status = RevisionStatus.SUPERSEDED
    cognitive_session.commit()

    with pytest.raises(RevisionStatusInvalidTransitionError) as exc_info:
        obj.revision_status = RevisionStatus.CURRENT
    assert exc_info.value.code == "PIA-8011"


def test_superseded_to_none_rejected(cognitive_session):
    obj = CognitiveObject()
    cognitive_session.add(obj)
    obj.revision_status = RevisionStatus.SUPERSEDED
    cognitive_session.commit()

    with pytest.raises(RevisionStatusInvalidTransitionError):
        obj.revision_status = None


def test_current_to_none_rejected(cognitive_session):
    obj = CognitiveObject()
    cognitive_session.add(obj)
    obj.revision_status = RevisionStatus.CURRENT
    cognitive_session.commit()

    with pytest.raises(RevisionStatusInvalidTransitionError):
        obj.revision_status = None


def test_same_value_reassignment_is_idempotent(cognitive_session):
    obj = CognitiveObject()
    cognitive_session.add(obj)
    obj.revision_status = RevisionStatus.CURRENT
    cognitive_session.commit()

    obj.revision_status = RevisionStatus.CURRENT  # não deve levantar
    cognitive_session.commit()
    assert obj.revision_status == RevisionStatus.CURRENT

    obj.revision_status = RevisionStatus.SUPERSEDED
    cognitive_session.commit()
    obj.revision_status = RevisionStatus.SUPERSEDED  # idempotente também
    assert obj.revision_status == RevisionStatus.SUPERSEDED


def test_revision_status_independent_of_accessibility(cognitive_session):
    """§7 do prompt corretivo: uma revisão SUPERSEDED pode continuar
    ACTIVE — os dois campos não se misturam."""
    obj = CognitiveObject()
    cognitive_session.add(obj)
    obj.revision_status = RevisionStatus.SUPERSEDED
    cognitive_session.commit()
    cognitive_session.refresh(obj)

    assert obj.revision_status == RevisionStatus.SUPERSEDED
    assert obj.accessibility == AccessibilityState.ACTIVE  # default, nunca tocado
