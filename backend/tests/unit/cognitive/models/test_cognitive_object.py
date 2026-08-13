"""
Testes de `CognitiveObject` — §29 e §32 do módulo E3.1.
"""

import contextlib
import uuid
from datetime import datetime

import pytest

from app.cognitive.errors.exceptions import (
    CognitiveObjectClidAlreadySetError,
    CognitiveObjectIdentityImmutableError,
)
from app.cognitive.models.cognitive_object import CognitiveObject
from app.cognitive.models.enums import AccessibilityState

# --- criação válida / campos obrigatórios / defaults ---


def test_creates_with_defaults(cognitive_session):
    obj = CognitiveObject()
    cognitive_session.add(obj)
    cognitive_session.commit()
    cognitive_session.refresh(obj)

    assert obj.clid is None
    assert obj.accessibility == AccessibilityState.ACTIVE
    assert obj.is_deleted is False
    assert obj.deleted_at is None


def test_no_field_requires_a_value_at_construction(cognitive_session):
    """CognitiveObject() sem nenhum argumento é uma criação válida —
    nenhum campo de conteúdo/provider é obrigatório (§29, §33)."""
    obj = CognitiveObject()
    cognitive_session.add(obj)
    cognitive_session.commit()
    assert obj.id is not None


# --- UUID / PK ---


def test_id_is_a_uuid_generated_on_flush(cognitive_session):
    obj = CognitiveObject()
    assert obj.id is None
    cognitive_session.add(obj)
    cognitive_session.flush()
    assert isinstance(obj.id, uuid.UUID)


def test_coid_property_aliases_id(cognitive_session):
    obj = CognitiveObject()
    cognitive_session.add(obj)
    cognitive_session.flush()
    assert obj.coid == obj.id


# --- timestamps ---


def test_timestamps_are_set_by_the_database(cognitive_session):
    obj = CognitiveObject()
    cognitive_session.add(obj)
    cognitive_session.commit()
    cognitive_session.refresh(obj)

    assert isinstance(obj.created_at, datetime)
    assert isinstance(obj.updated_at, datetime)


# --- serialização (via schema Read) ---


def test_read_schema_serializes_from_orm_instance(cognitive_session):
    from app.cognitive.schemas.cognitive_object import CognitiveObjectRead

    obj = CognitiveObject()
    cognitive_session.add(obj)
    cognitive_session.commit()
    cognitive_session.refresh(obj)

    read = CognitiveObjectRead.model_validate(obj)
    assert read.id == obj.id
    assert read.accessibility == AccessibilityState.ACTIVE
    assert read.is_deleted is False


# --- TEST C5: identidade não pode ser silenciosamente reatribuída ---


def test_identity_mutation_is_rejected_after_persistence(cognitive_session):
    obj = CognitiveObject()
    cognitive_session.add(obj)
    cognitive_session.commit()
    cognitive_session.refresh(obj)

    original_id = obj.id
    obj.id = uuid.uuid4()

    with pytest.raises(CognitiveObjectIdentityImmutableError) as exc_info:
        cognitive_session.commit()
    cognitive_session.rollback()

    assert exc_info.value.code == "PIA-8001"
    cognitive_session.refresh(obj)
    assert obj.id == original_id


# --- clid: primeira atribuição permitida, sobrescrita rejeitada ---


# --- CLID: imutabilidade após primeira atribuição (correção E3.1.1) ---


def test_cl1_clid_can_be_set_once_from_none(cognitive_session):
    obj = CognitiveObject()
    cognitive_session.add(obj)
    cognitive_session.commit()

    new_clid = uuid.uuid4()
    obj.clid = new_clid
    cognitive_session.commit()
    cognitive_session.refresh(obj)
    assert obj.clid == new_clid


def test_cl2_clid_reassignment_to_same_value_is_idempotent(cognitive_session):
    obj = CognitiveObject()
    same_clid = uuid.uuid4()
    obj.clid = same_clid
    cognitive_session.add(obj)
    cognitive_session.commit()

    obj.clid = same_clid  # não deve levantar
    cognitive_session.commit()
    assert obj.clid == same_clid


def test_cl3_clid_overwrite_with_different_value_is_rejected(cognitive_session):
    obj = CognitiveObject()
    cognitive_session.add(obj)
    obj.clid = uuid.uuid4()
    cognitive_session.commit()

    with pytest.raises(CognitiveObjectClidAlreadySetError) as exc_info:
        obj.clid = uuid.uuid4()

    assert exc_info.value.code == "PIA-8002"


def test_cl4_clid_reset_to_none_is_rejected(cognitive_session):
    """Correção E3.1.1 (C2): o guard original não rejeitava
    `CLID_A -> None` — lacuna real, coberta explicitamente aqui."""
    obj = CognitiveObject()
    cognitive_session.add(obj)
    obj.clid = uuid.uuid4()
    cognitive_session.commit()

    with pytest.raises(CognitiveObjectClidAlreadySetError) as exc_info:
        obj.clid = None

    assert exc_info.value.code == "PIA-8002"


def test_cl5_update_via_repository_does_not_bypass_the_guard(cognitive_session):
    """A proteção vive no modelo (`@validates`), não no schema/
    repositório — tentar contornar via `repo.update()` também falha,
    porque a mutação do atributo já foi rejeitada antes mesmo do
    `update()` ser chamado."""
    from app.cognitive.repositories.object_repository import ObjectRepository

    repo = ObjectRepository(cognitive_session)
    obj = repo.add(CognitiveObject())
    obj.clid = uuid.uuid4()
    cognitive_session.commit()

    with pytest.raises(CognitiveObjectClidAlreadySetError):
        obj.clid = uuid.uuid4()
        repo.update(obj)


def test_cl6_reload_after_invalid_attempt_preserves_original_clid(cognitive_session):
    obj = CognitiveObject()
    cognitive_session.add(obj)
    original_clid = uuid.uuid4()
    obj.clid = original_clid
    cognitive_session.commit()

    with contextlib.suppress(CognitiveObjectClidAlreadySetError):
        obj.clid = uuid.uuid4()

    cognitive_session.refresh(obj)
    assert obj.clid == original_clid


def test_cl7_rollback_after_invalid_clid_attempt_leaves_consistent_state(cognitive_session):
    obj = CognitiveObject()
    cognitive_session.add(obj)
    original_clid = uuid.uuid4()
    obj.clid = original_clid
    cognitive_session.commit()

    with contextlib.suppress(CognitiveObjectClidAlreadySetError):
        obj.clid = uuid.uuid4()
    cognitive_session.rollback()

    # sessão continua utilizável após o rollback — nova operação funciona
    other = CognitiveObject()
    cognitive_session.add(other)
    cognitive_session.commit()
    assert other.id is not None


# --- TEST C1: mesmo "conteúdo" (aqui, nenhum) não implica mesmo objeto ---


def test_two_independently_created_objects_remain_distinct(cognitive_session):
    """Dois CognitiveObjects criados de forma independente, com os
    mesmos valores em todos os campos (accessibility=ACTIVE, clid=None),
    permanecem duas linhas distintas — nenhuma deduplicação automática
    por igualdade de estado (§20, TEST C1)."""
    a = CognitiveObject()
    b = CognitiveObject()
    cognitive_session.add_all([a, b])
    cognitive_session.commit()

    assert a.id != b.id
    assert cognitive_session.query(CognitiveObject).count() == 2


# --- TEST C2: provider/modelo não é obrigatório ---


def test_object_does_not_require_provider_or_model(cognitive_session):
    """CognitiveObject não possui nenhum campo provider/model_id
    obrigatório — essa informação pertence a ProvenanceRecord (E3.6),
    não a este objeto (§18, §33)."""
    obj = CognitiveObject()
    column_names = {c.name for c in CognitiveObject.__table__.columns}
    assert "provider_id" not in column_names
    assert "model_id" not in column_names
    cognitive_session.add(obj)
    cognitive_session.commit()  # não levanta por falta de provider/model


# --- TEST C3: nenhum campo cout_score obrigatório ou existente ---


def test_no_cout_score_field_exists():
    """Nenhum campo de score/ranking COUT existe em CognitiveObject —
    proibição explícita do EDR (§21, TEST C3)."""
    column_names = {c.name for c in CognitiveObject.__table__.columns}
    forbidden = {
        "cout_score",
        "global_admissibility_score",
        "universal_rank",
        "causal_rank",
        "best_object",
        "best_answer",
    }
    assert column_names.isdisjoint(forbidden)


# --- objeto pode existir sem provenance completo ---


def test_object_can_exist_without_any_provenance_reference(cognitive_session):
    """Nenhuma FK/coluna obrigatória para provenance existe em
    CognitiveObject nesta fase (ProvenanceRecord é E3.6) — o objeto é
    criável e persistível sozinho (§18, §29)."""
    obj = CognitiveObject()
    cognitive_session.add(obj)
    cognitive_session.commit()
    assert obj.id is not None
