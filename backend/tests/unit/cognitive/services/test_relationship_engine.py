"""
Testes de `RelationshipEngine` — §37 do módulo E3.5 (MIA1-MIA5) e
cobertura das operações do serviço (create/retire/navigation).
"""

import pytest

from app.cognitive.errors.exceptions import RelationshipSelfLinkError
from app.cognitive.models.cognitive_object import CognitiveObject
from app.cognitive.models.enums import RelationshipType
from app.cognitive.repositories.object_repository import ObjectRepository
from app.cognitive.repositories.relationship_repository import RelationshipRepository
from app.cognitive.services.relationship_engine import RelationshipEngine


@pytest.fixture
def objects(cognitive_session):
    return ObjectRepository(cognitive_session)


@pytest.fixture
def relationships(cognitive_session):
    return RelationshipRepository(cognitive_session)


@pytest.fixture
def engine(relationships):
    return RelationshipEngine(relationships)


def test_create_delegates_to_repository(objects, engine, cognitive_session):
    a = objects.add(CognitiveObject())
    b = objects.add(CognitiveObject())
    cognitive_session.commit()

    rel = engine.create(
        source_coid=a.id, target_coid=b.id, relationship_type=RelationshipType.SUPPORTS
    )
    cognitive_session.commit()
    assert rel.id is not None


def test_create_rejects_self_relation(objects, engine, cognitive_session):
    a = objects.add(CognitiveObject())
    cognitive_session.commit()

    with pytest.raises(RelationshipSelfLinkError):
        engine.create(
            source_coid=a.id, target_coid=a.id, relationship_type=RelationshipType.SUPPORTS
        )


def test_retire_delegates_to_repository(objects, engine, cognitive_session):
    a = objects.add(CognitiveObject())
    b = objects.add(CognitiveObject())
    cognitive_session.commit()
    rel = engine.create(
        source_coid=a.id, target_coid=b.id, relationship_type=RelationshipType.SUPPORTS
    )
    cognitive_session.commit()

    retired = engine.retire(rel)
    cognitive_session.commit()
    assert retired.retired_at is not None


def test_outgoing_incoming_neighbors_by_type(objects, engine, cognitive_session):
    a = objects.add(CognitiveObject())
    b = objects.add(CognitiveObject())
    c = objects.add(CognitiveObject())
    cognitive_session.commit()

    engine.create(source_coid=a.id, target_coid=b.id, relationship_type=RelationshipType.SUPPORTS)
    engine.create(
        source_coid=c.id, target_coid=a.id, relationship_type=RelationshipType.CONTRADICTS
    )
    cognitive_session.commit()

    assert len(engine.outgoing(a.id)) == 1
    assert len(engine.incoming(a.id)) == 1
    assert len(engine.neighbors(a.id)) == 2
    assert len(engine.by_type(RelationshipType.SUPPORTS)) == 1


def test_engine_does_not_commit(objects, engine, cognitive_session):
    """`create()`/`retire()` não commitam — confirmado por rollback
    desfazendo o efeito (§17 do módulo E3.5)."""
    a = objects.add(CognitiveObject())
    b = objects.add(CognitiveObject())
    cognitive_session.commit()

    engine.create(source_coid=a.id, target_coid=b.id, relationship_type=RelationshipType.SUPPORTS)
    cognitive_session.rollback()

    assert engine.outgoing(a.id) == []


# --- MIA1-MIA5: Multi-IA readiness ---


def test_mia1_multiple_relationships_coexist_without_single_provider(
    objects, engine, cognitive_session
):
    a = objects.add(CognitiveObject())
    b = objects.add(CognitiveObject())
    c = objects.add(CognitiveObject())
    cognitive_session.commit()

    engine.create(source_coid=a.id, target_coid=b.id, relationship_type=RelationshipType.SUPPORTS)
    engine.create(source_coid=a.id, target_coid=c.id, relationship_type=RelationshipType.REFERENCES)
    cognitive_session.commit()

    assert len(engine.outgoing(a.id)) == 2


def test_mia2_contradictory_relationships_coexist_via_engine(objects, engine, cognitive_session):
    a = objects.add(CognitiveObject())
    x = objects.add(CognitiveObject())
    b = objects.add(CognitiveObject())
    cognitive_session.commit()

    engine.create(source_coid=a.id, target_coid=x.id, relationship_type=RelationshipType.SUPPORTS)
    engine.create(
        source_coid=b.id, target_coid=x.id, relationship_type=RelationshipType.CONTRADICTS
    )
    cognitive_session.commit()  # não deve levantar

    assert len(engine.incoming(x.id)) == 2


def test_mia3_no_public_signature_requires_provider_model_agent():
    import inspect

    forbidden = {
        "provider",
        "provider_id",
        "model",
        "model_id",
        "agent",
        "agent_id",
        "openai",
        "claude",
        "gemini",
    }
    for name, method in inspect.getmembers(RelationshipEngine, predicate=inspect.isfunction):
        if name.startswith("_"):
            continue
        params = set(inspect.signature(method).parameters)
        assert params.isdisjoint(forbidden), f"{name} aceita parâmetro proibido"


def test_mia4_no_ai_sdk_imported():
    import inspect

    import app.cognitive.services.relationship_engine as relationship_engine_module

    source_code = inspect.getsource(relationship_engine_module)
    for forbidden_token in ("openai", "anthropic", "google.generativeai", "cohere"):
        assert forbidden_token not in source_code.lower()


def test_mia5_engine_does_not_arbitrate_conflicts(objects, engine, cognitive_session):
    """Nenhum método de `RelationshipEngine` resolve/arbitra
    conflitos — inspeção da API pública: apenas
    create/retire/outgoing/incoming/neighbors/by_type existem."""
    import inspect

    public_methods = {
        name
        for name, _ in inspect.getmembers(RelationshipEngine, predicate=inspect.isfunction)
        if not name.startswith("_")
    }
    assert public_methods == {"create", "retire", "outgoing", "incoming", "neighbors", "by_type"}
