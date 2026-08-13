"""
Testes de `ProvenanceRepository`/`ProvenanceManager` — §19 do módulo
E3.6 (P1-P13) e §20 (MIA1-MIA5).
"""

import pytest

from app.cognitive.errors.exceptions import ProvenanceRecordImmutableError
from app.cognitive.models.cognitive_object import CognitiveObject
from app.cognitive.models.enums import ProvenanceActorType, ProvenanceSourceType
from app.cognitive.models.provenance_record import ProvenanceRecord
from app.cognitive.repositories.object_repository import ObjectRepository
from app.cognitive.repositories.provenance_repository import ProvenanceRepository
from app.cognitive.services.provenance_manager import ProvenanceManager


@pytest.fixture
def objects(cognitive_session):
    return ObjectRepository(cognitive_session)


@pytest.fixture
def provenance(cognitive_session):
    return ProvenanceRepository(cognitive_session)


@pytest.fixture
def manager(provenance):
    return ProvenanceManager(provenance)


# --- P1-P13 ---


def test_p1_records_provenance_for_a_cognitive_object(objects, manager, cognitive_session):
    obj = objects.add(CognitiveObject())
    cognitive_session.commit()

    rec = manager.record(
        coid=obj.id, source_type=ProvenanceSourceType.HUMAN, actor_type=ProvenanceActorType.HUMAN
    )
    cognitive_session.commit()
    assert rec.id is not None


def test_p2_multiple_provenances_for_same_coid(objects, manager, cognitive_session):
    obj = objects.add(CognitiveObject())
    cognitive_session.commit()

    manager.record(
        coid=obj.id, source_type=ProvenanceSourceType.AGENT, actor_type=ProvenanceActorType.AGENT
    )
    manager.record(
        coid=obj.id, source_type=ProvenanceSourceType.AGENT, actor_type=ProvenanceActorType.AGENT
    )
    cognitive_session.commit()

    assert len(manager.list_for(obj.id)) == 2


def test_p3_different_agents_coexist(objects, manager, cognitive_session):
    obj = objects.add(CognitiveObject())
    cognitive_session.commit()

    manager.record(
        coid=obj.id,
        source_type=ProvenanceSourceType.AGENT,
        actor_type=ProvenanceActorType.AGENT,
        actor_id="agent-1",
    )
    manager.record(
        coid=obj.id,
        source_type=ProvenanceSourceType.AGENT,
        actor_type=ProvenanceActorType.AGENT,
        actor_id="agent-2",
    )
    cognitive_session.commit()

    actor_ids = {r.actor_id for r in manager.list_for(obj.id)}
    assert actor_ids == {"agent-1", "agent-2"}


def test_p4_different_providers_coexist(objects, manager, cognitive_session):
    obj = objects.add(CognitiveObject())
    cognitive_session.commit()

    manager.record(
        coid=obj.id,
        source_type=ProvenanceSourceType.AGENT,
        actor_type=ProvenanceActorType.AGENT,
        provider_id="anthropic",
    )
    manager.record(
        coid=obj.id,
        source_type=ProvenanceSourceType.AGENT,
        actor_type=ProvenanceActorType.AGENT,
        provider_id="openai",
    )
    cognitive_session.commit()

    providers = {r.provider_id for r in manager.list_for(obj.id)}
    assert providers == {"anthropic", "openai"}


def test_p5_distinct_execution_identity(objects, manager, cognitive_session):
    obj = objects.add(CognitiveObject())
    cognitive_session.commit()

    r1 = manager.record(
        coid=obj.id,
        source_type=ProvenanceSourceType.AGENT,
        actor_type=ProvenanceActorType.AGENT,
        agent_instance_id="exec-1",
    )
    r2 = manager.record(
        coid=obj.id,
        source_type=ProvenanceSourceType.AGENT,
        actor_type=ProvenanceActorType.AGENT,
        agent_instance_id="exec-2",
    )
    cognitive_session.commit()

    assert r1.provenance_id != r2.provenance_id
    assert r1.agent_instance_id != r2.agent_instance_id


def test_p6_parent_agent_output_ref_represents_sequence(objects, manager, cognitive_session):
    obj = objects.add(CognitiveObject())
    cognitive_session.commit()

    first = manager.record(
        coid=obj.id,
        source_type=ProvenanceSourceType.AGENT,
        actor_type=ProvenanceActorType.AGENT,
        agent_instance_id="exec-1",
        agent_sequence=1,
    )
    second = manager.record(
        coid=obj.id,
        source_type=ProvenanceSourceType.AGENT,
        actor_type=ProvenanceActorType.AGENT,
        agent_instance_id="exec-2",
        agent_sequence=2,
        parent_agent_output_ref=first.agent_instance_id,
    )
    cognitive_session.commit()

    assert second.parent_agent_output_ref == first.agent_instance_id
    assert second.agent_sequence == first.agent_sequence + 1


def test_p7_append_only_confirmed_via_repository_contract(objects, provenance, cognitive_session):
    obj = objects.add(CognitiveObject())
    cognitive_session.commit()

    rec = provenance.add(
        ProvenanceRecord(
            coid=obj.id,
            source_type=ProvenanceSourceType.SYSTEM,
            actor_type=ProvenanceActorType.SYSTEM,
        )
    )
    cognitive_session.commit()

    with pytest.raises(ProvenanceRecordImmutableError):
        provenance.update(rec)


def test_p8_physical_delete_rejected(objects, provenance, cognitive_session):
    obj = objects.add(CognitiveObject())
    cognitive_session.commit()

    rec = provenance.add(
        ProvenanceRecord(
            coid=obj.id,
            source_type=ProvenanceSourceType.SYSTEM,
            actor_type=ProvenanceActorType.SYSTEM,
        )
    )
    cognitive_session.commit()

    with pytest.raises(ProvenanceRecordImmutableError) as exc_info:
        provenance.delete(rec)
    assert exc_info.value.code == "PIA-8017"


def test_p9_destructive_update_rejected(objects, provenance, cognitive_session):
    obj = objects.add(CognitiveObject())
    cognitive_session.commit()

    rec = provenance.add(
        ProvenanceRecord(
            coid=obj.id,
            source_type=ProvenanceSourceType.SYSTEM,
            actor_type=ProvenanceActorType.SYSTEM,
        )
    )
    cognitive_session.commit()

    with pytest.raises(ProvenanceRecordImmutableError) as exc_info:
        provenance.update(rec)
    assert exc_info.value.code == "PIA-8017"


def test_p10_no_full_payload_or_chat_stored(manager):
    """Inspeção da assinatura pública: nenhum parâmetro de
    conteúdo/payload/chat existe em `ProvenanceManager.record()`."""
    import inspect

    params = set(inspect.signature(manager.record).parameters)
    forbidden = {"content", "payload", "prompt", "response", "transcript", "chat_history"}
    assert params.isdisjoint(forbidden)


def test_p11_no_provider_sdk_required(objects, manager, cognitive_session):
    """`provider_id` é uma string livre — nenhum SDK precisa ser
    importado para popular esse campo."""
    obj = objects.add(CognitiveObject())
    cognitive_session.commit()

    rec = manager.record(
        coid=obj.id,
        source_type=ProvenanceSourceType.AGENT,
        actor_type=ProvenanceActorType.AGENT,
        provider_id="qualquer-string-livre",
    )
    cognitive_session.commit()
    assert rec.provider_id == "qualquer-string-livre"


def test_p12_correlation_session_trace_preserved_when_provided(objects, manager, cognitive_session):
    obj = objects.add(CognitiveObject())
    cognitive_session.commit()

    rec = manager.record(
        coid=obj.id,
        source_type=ProvenanceSourceType.AGENT,
        actor_type=ProvenanceActorType.AGENT,
        session_id="session-123",
        correlation_id="corr-456",
    )
    cognitive_session.commit()

    assert rec.session_id == "session-123"
    assert rec.correlation_id == "corr-456"


def test_p13_absent_optional_fields_remain_valid(objects, manager, cognitive_session):
    obj = objects.add(CognitiveObject())
    cognitive_session.commit()

    rec = manager.record(
        coid=obj.id, source_type=ProvenanceSourceType.HUMAN, actor_type=ProvenanceActorType.HUMAN
    )
    cognitive_session.commit()
    assert rec.id is not None


# --- Non-commit ---


def test_manager_does_not_commit(objects, manager, cognitive_session):
    obj = objects.add(CognitiveObject())
    cognitive_session.commit()

    manager.record(
        coid=obj.id, source_type=ProvenanceSourceType.SYSTEM, actor_type=ProvenanceActorType.SYSTEM
    )
    cognitive_session.rollback()

    assert manager.list_for(obj.id) == []


# --- MIA1-MIA5 ---


def test_mia1_competitive_two_independent_contributions(objects, manager, cognitive_session):
    obj = objects.add(CognitiveObject())
    cognitive_session.commit()

    r_a = manager.record(
        coid=obj.id,
        source_type=ProvenanceSourceType.AGENT,
        actor_type=ProvenanceActorType.AGENT,
        actor_id="ia-a",
        orchestration_run_id="run-1",
    )
    r_b = manager.record(
        coid=obj.id,
        source_type=ProvenanceSourceType.AGENT,
        actor_type=ProvenanceActorType.AGENT,
        actor_id="ia-b",
        orchestration_run_id="run-1",
    )
    cognitive_session.commit()

    assert len(manager.list_for(obj.id)) == 2
    assert r_a.provenance_id != r_b.provenance_id


def test_mia2_complementary_generator_and_critic_roles_preserved(
    objects, manager, cognitive_session
):
    obj = objects.add(CognitiveObject())
    cognitive_session.commit()

    manager.record(
        coid=obj.id,
        source_type=ProvenanceSourceType.AGENT,
        actor_type=ProvenanceActorType.AGENT,
        agent_role="generator",
    )
    manager.record(
        coid=obj.id,
        source_type=ProvenanceSourceType.AGENT,
        actor_type=ProvenanceActorType.AGENT,
        agent_role="critic",
    )
    cognitive_session.commit()

    roles = {r.agent_role for r in manager.list_for(obj.id)}
    assert roles == {"generator", "critic"}


def test_mia3_sequential_a_b_a_ordering_reconstructible(objects, manager, cognitive_session):
    obj = objects.add(CognitiveObject())
    cognitive_session.commit()

    manager.record(
        coid=obj.id,
        source_type=ProvenanceSourceType.AGENT,
        actor_type=ProvenanceActorType.AGENT,
        agent_instance_id="step-1",
        agent_sequence=1,
    )
    manager.record(
        coid=obj.id,
        source_type=ProvenanceSourceType.AGENT,
        actor_type=ProvenanceActorType.AGENT,
        agent_instance_id="step-2",
        agent_sequence=2,
        parent_agent_output_ref="step-1",
    )
    manager.record(
        coid=obj.id,
        source_type=ProvenanceSourceType.AGENT,
        actor_type=ProvenanceActorType.AGENT,
        agent_instance_id="step-3",
        agent_sequence=3,
        parent_agent_output_ref="step-2",
    )
    cognitive_session.commit()

    records = sorted(manager.list_for(obj.id), key=lambda r: r.agent_sequence)
    assert [r.agent_instance_id for r in records] == ["step-1", "step-2", "step-3"]


def test_mia4_no_contribution_overwrites_another(objects, manager, cognitive_session):
    obj = objects.add(CognitiveObject())
    cognitive_session.commit()

    r1 = manager.record(
        coid=obj.id, source_type=ProvenanceSourceType.AGENT, actor_type=ProvenanceActorType.AGENT
    )
    cognitive_session.commit()
    r1_created_at = r1.created_at

    manager.record(
        coid=obj.id, source_type=ProvenanceSourceType.AGENT, actor_type=ProvenanceActorType.AGENT
    )
    cognitive_session.commit()

    assert r1.created_at == r1_created_at
    assert len(manager.list_for(obj.id)) == 2


def test_mia5_no_execution_requires_full_transcript_storage():
    import inspect

    import app.cognitive.services.provenance_manager as provenance_manager_module

    source_code = inspect.getsource(provenance_manager_module)
    for forbidden_token in ("openai", "anthropic", "google.generativeai", "cohere"):
        assert forbidden_token not in source_code.lower()
