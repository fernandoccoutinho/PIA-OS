"""Testes de `ProvenanceRecord` — validação estrutural mínima."""

import uuid

import pytest
from sqlalchemy.exc import IntegrityError

from app.cognitive.models.cognitive_object import CognitiveObject
from app.cognitive.models.enums import ProvenanceActorType, ProvenanceSourceType
from app.cognitive.models.provenance_record import ProvenanceRecord


def test_creates_with_required_fields(cognitive_session):
    obj = CognitiveObject()
    cognitive_session.add(obj)
    cognitive_session.commit()

    rec = ProvenanceRecord(
        coid=obj.id,
        source_type=ProvenanceSourceType.AGENT,
        actor_type=ProvenanceActorType.AGENT,
    )
    cognitive_session.add(rec)
    cognitive_session.commit()
    cognitive_session.refresh(rec)

    assert rec.id is not None
    assert rec.provenance_id == rec.id
    assert rec.coid == obj.id
    assert rec.source_type == ProvenanceSourceType.AGENT
    assert rec.actor_type == ProvenanceActorType.AGENT
    assert rec.created_at is not None


def test_optional_fields_default_correctly(cognitive_session):
    obj = CognitiveObject()
    cognitive_session.add(obj)
    cognitive_session.commit()

    rec = ProvenanceRecord(
        coid=obj.id,
        source_type=ProvenanceSourceType.HUMAN,
        actor_type=ProvenanceActorType.HUMAN,
    )
    cognitive_session.add(rec)
    cognitive_session.commit()
    cognitive_session.refresh(rec)

    assert rec.source_ref is None
    assert rec.actor_id is None
    assert rec.provider_id is None
    assert rec.model_id is None
    assert rec.session_id is None
    assert rec.correlation_id is None
    assert rec.evidence_refs == []
    assert rec.orchestration_run_id is None
    assert rec.agent_role is None
    assert rec.agent_instance_id is None
    assert rec.agent_sequence is None
    assert rec.parent_agent_output_ref is None


def test_all_source_types_and_actor_types_accepted(cognitive_session):
    obj = CognitiveObject()
    cognitive_session.add(obj)
    cognitive_session.commit()

    for source_type in ProvenanceSourceType:
        for actor_type in ProvenanceActorType:
            rec = ProvenanceRecord(coid=obj.id, source_type=source_type, actor_type=actor_type)
            cognitive_session.add(rec)
    cognitive_session.commit()

    expected = len(list(ProvenanceSourceType)) * len(list(ProvenanceActorType))
    assert cognitive_session.query(ProvenanceRecord).count() == expected


def test_provider_and_model_are_never_required_even_for_agent(cognitive_session):
    """§ obrigatória do módulo E3.0/E3.6: `provider_id`/`model_id`
    nunca são obrigatórios, mesmo quando `actor_type == AGENT`."""
    obj = CognitiveObject()
    cognitive_session.add(obj)
    cognitive_session.commit()

    rec = ProvenanceRecord(
        coid=obj.id, source_type=ProvenanceSourceType.AGENT, actor_type=ProvenanceActorType.AGENT
    )
    cognitive_session.add(rec)
    cognitive_session.commit()  # não deve levantar
    cognitive_session.refresh(rec)
    assert rec.provider_id is None
    assert rec.model_id is None


def test_multiple_records_for_same_coid_are_allowed(cognitive_session):
    obj = CognitiveObject()
    cognitive_session.add(obj)
    cognitive_session.commit()

    for i in range(5):
        rec = ProvenanceRecord(
            coid=obj.id,
            source_type=ProvenanceSourceType.AGENT,
            actor_type=ProvenanceActorType.AGENT,
            actor_id=f"agent-{i}",
        )
        cognitive_session.add(rec)
    cognitive_session.commit()  # não deve levantar — sem UniqueConstraint em coid

    assert cognitive_session.query(ProvenanceRecord).count() == 5


def test_foreign_key_violation_rejects_nonexistent_coid(cognitive_session):
    rec = ProvenanceRecord(
        coid=uuid.uuid4(),
        source_type=ProvenanceSourceType.SYSTEM,
        actor_type=ProvenanceActorType.SYSTEM,
    )
    cognitive_session.add(rec)
    with pytest.raises(IntegrityError):
        cognitive_session.commit()
    cognitive_session.rollback()


def test_evidence_refs_persist_as_list(cognitive_session):
    obj = CognitiveObject()
    cognitive_session.add(obj)
    cognitive_session.commit()

    rec = ProvenanceRecord(
        coid=obj.id,
        source_type=ProvenanceSourceType.IMPORT,
        actor_type=ProvenanceActorType.SYSTEM,
        evidence_refs=["ref-1", "ref-2"],
    )
    cognitive_session.add(rec)
    cognitive_session.commit()
    cognitive_session.refresh(rec)

    assert rec.evidence_refs == ["ref-1", "ref-2"]


def test_no_content_column_exists():
    """Inspeção estrutural: nenhuma coluna de conteúdo/transcript
    integral existe (§4/§10 do módulo E3.6 — PROVENANCE != TRANSCRIPT)."""
    columns = {c.name for c in ProvenanceRecord.__table__.columns}
    forbidden = {
        "content",
        "payload",
        "prompt",
        "response",
        "transcript",
        "chat_history",
        "message",
        "conversation",
        "token_usage",
    }
    assert columns.isdisjoint(forbidden)
