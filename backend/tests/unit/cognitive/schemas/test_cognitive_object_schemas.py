"""Testes dos schemas Pydantic de CognitiveObject — §23."""

import uuid

import pytest
from pydantic import ValidationError

from app.cognitive.models.enums import AccessibilityState
from app.cognitive.schemas.cognitive_object import (
    CognitiveObjectCreate,
    CognitiveObjectRead,
    CognitiveObjectUpdate,
)


def test_create_schema_accepts_no_fields():
    payload = CognitiveObjectCreate()
    assert payload.clid is None


def test_create_schema_accepts_optional_clid():
    clid = uuid.uuid4()
    payload = CognitiveObjectCreate(clid=clid)
    assert payload.clid == clid


def test_create_schema_does_not_accept_accessibility():
    """`accessibility` não é campo de `CognitiveObjectCreate` — todo
    objeto novo nasce ACTIVE, sem política de estado inicial
    alternativa (§6 do CognitiveObjectCreate)."""
    assert "accessibility" not in CognitiveObjectCreate.model_fields


def test_update_schema_requires_clid():
    with pytest.raises(ValidationError):
        CognitiveObjectUpdate()


def test_update_schema_does_not_accept_id():
    """Update NÃO deve permitir alteração silenciosa de identidade —
    `id`/`coid` não é sequer um campo aceito (§23)."""
    assert "id" not in CognitiveObjectUpdate.model_fields
    assert "coid" not in CognitiveObjectUpdate.model_fields


def test_update_schema_does_not_accept_accessibility():
    assert "accessibility" not in CognitiveObjectUpdate.model_fields


def test_read_schema_has_expected_fields():
    expected = {
        "id",
        "clid",
        "accessibility",
        "created_at",
        "updated_at",
        "deleted_at",
        "is_deleted",
    }
    assert set(CognitiveObjectRead.model_fields) == expected


def test_read_schema_accepts_enum_member_directly():
    read = CognitiveObjectRead(
        id=uuid.uuid4(),
        clid=None,
        accessibility=AccessibilityState.ACTIVE,
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
        deleted_at=None,
        is_deleted=False,
    )
    assert read.accessibility == AccessibilityState.ACTIVE
