"""
Testes de `CoidManager` — §24-§29 do módulo E3.2 (G1-G6, V1-V5,
I1-I5, C1-C5, IMP1-IMP5, Multi-IA-readiness).
"""

import uuid

import pytest

from app.cognitive.errors.exceptions import (
    CognitiveObjectIdentityImmutableError,
    CoidCollisionError,
    CoidInvalidError,
)
from app.cognitive.models.cognitive_object import CognitiveObject
from app.cognitive.repositories.object_repository import ObjectRepository
from app.cognitive.services.coid_manager import (
    CoidManager,
    ImportedCoidStatus,
    ImportedCoidValidation,
)


@pytest.fixture
def repo(cognitive_session):
    return ObjectRepository(cognitive_session)


@pytest.fixture
def manager(repo):
    return CoidManager(repo)


# --- G1-G6: GERAÇÃO ---


def test_g1_generate_produces_a_valid_coid(manager):
    coid = manager.generate()
    assert isinstance(coid, uuid.UUID)


def test_g2_multiple_generations_produce_distinct_ids(manager):
    generated = {manager.generate() for _ in range(50)}
    assert len(generated) == 50


def test_g3_generated_format_is_accepted_by_validator(manager):
    coid = manager.generate()
    assert manager.validate(coid) == coid
    assert manager.validate(str(coid)) == coid


def test_g4_coid_does_not_depend_on_payload(manager):
    """`generate()` não recebe nenhum argumento de conteúdo — não há
    como um payload influenciar o COID gerado."""
    import inspect

    sig = inspect.signature(manager.generate)
    assert len(sig.parameters) == 0


def test_g5_coid_does_not_depend_on_provider_model_or_session(manager):
    """Idem — `generate()` não aceita provider/model/session_id."""
    import inspect

    sig = inspect.signature(manager.generate)
    assert "provider" not in sig.parameters
    assert "model" not in sig.parameters
    assert "session_id" not in sig.parameters


def test_g6_two_objects_with_identical_content_receive_distinct_coids(repo, cognitive_session):
    """`CognitiveObject` não tem campo de conteúdo nesta fase — "conteúdo
    idêntico" aqui significa dois objetos criados sem nenhum
    diferencial de payload, que ainda assim recebem COIDs distintos."""
    a = repo.add(CognitiveObject())
    b = repo.add(CognitiveObject())
    cognitive_session.commit()
    assert a.id != b.id


def test_assert_unique_raises_directly_on_real_collision(repo, cognitive_session, manager):
    existing = repo.add(CognitiveObject())
    cognitive_session.commit()

    with pytest.raises(CoidCollisionError) as exc_info:
        manager.assert_unique(existing.id)
    assert exc_info.value.code == "PIA-8004"
    assert exc_info.value.coid == existing.id


def test_generate_unique_returns_a_fresh_unique_coid(manager):
    coid = manager.generate_unique()
    assert isinstance(coid, uuid.UUID)
    manager.assert_unique(coid)  # não levanta — confirma que está livre


def test_generate_unique_retries_on_collision_then_succeeds(monkeypatch, manager):
    """Simula colisão nas duas primeiras tentativas, sucesso na terceira."""
    fixed_colliding = uuid.uuid4()
    fresh = uuid.uuid4()
    sequence = iter([fixed_colliding, fixed_colliding, fresh])
    monkeypatch.setattr(manager, "generate", lambda: next(sequence))

    calls = {"count": 0}
    original_assert_unique = manager.assert_unique

    def _assert_unique_side_effect(coid):
        calls["count"] += 1
        if coid == fixed_colliding:
            raise CoidCollisionError(coid)
        return original_assert_unique(coid)

    monkeypatch.setattr(manager, "assert_unique", _assert_unique_side_effect)

    result = manager.generate_unique(max_attempts=5)
    assert result == fresh
    assert calls["count"] == 3


def test_generate_unique_raises_after_exhausting_attempts(monkeypatch, manager):
    always_colliding = uuid.uuid4()
    monkeypatch.setattr(manager, "generate", lambda: always_colliding)
    monkeypatch.setattr(
        manager,
        "assert_unique",
        lambda coid: (_ for _ in ()).throw(CoidCollisionError(coid)),
    )
    with pytest.raises(CoidCollisionError):
        manager.generate_unique(max_attempts=3)


# --- V1-V5: VALIDAÇÃO ---


def test_v1_valid_coid_accepted(manager):
    coid = uuid.uuid4()
    assert manager.validate(coid) == coid
    assert manager.validate(str(coid)) == coid


def test_v2_invalid_value_rejected(manager):
    with pytest.raises(CoidInvalidError) as exc_info:
        manager.validate("not-a-uuid")
    assert exc_info.value.code == "PIA-8003"


def test_v3_invalid_type_rejected(manager):
    with pytest.raises(CoidInvalidError):
        manager.validate(12345)
    with pytest.raises(CoidInvalidError):
        manager.validate(None)
    with pytest.raises(CoidInvalidError):
        manager.validate(["not", "a", "uuid"])


def test_v4_null_rejected_when_identity_is_required(manager):
    """`validate(None)` é rejeitado — identidade nunca pode ser nula
    quando exigida (consistente com a imutabilidade COID_A -> NULL)."""
    with pytest.raises(CoidInvalidError):
        manager.validate(None)


def test_v5_validation_normalization_is_idempotent(manager):
    """`validate()` já normaliza (str -> UUID) — aplicar duas vezes
    produz o mesmo resultado (idempotente). Nenhum `normalize()`
    separado existe (§25 do módulo E3.2: desnecessário)."""
    coid = uuid.uuid4()
    once = manager.validate(str(coid))
    twice = manager.validate(once)
    assert once == twice == coid
    assert not hasattr(manager, "normalize")


# --- I1-I5: IMUTABILIDADE (consolidação do contrato formal) ---


def test_i1_persisted_coid_cannot_change(repo, cognitive_session):
    obj = repo.add(CognitiveObject())
    cognitive_session.commit()
    original_id = obj.id

    obj.id = uuid.uuid4()
    with pytest.raises(CognitiveObjectIdentityImmutableError):
        cognitive_session.commit()
    cognitive_session.rollback()
    cognitive_session.refresh(obj)
    assert obj.id == original_id


def test_i2_persisted_coid_cannot_become_null(repo, cognitive_session):
    obj = repo.add(CognitiveObject())
    cognitive_session.commit()

    obj.id = None
    with pytest.raises(CognitiveObjectIdentityImmutableError):
        cognitive_session.commit()
    cognitive_session.rollback()


def test_i3_update_schema_does_not_expose_coid():
    from app.cognitive.schemas.cognitive_object import CognitiveObjectUpdate

    assert "id" not in CognitiveObjectUpdate.model_fields
    assert "coid" not in CognitiveObjectUpdate.model_fields


def test_i4_repository_update_does_not_bypass_immutability(repo, cognitive_session):
    obj = repo.add(CognitiveObject())
    cognitive_session.commit()
    original_id = obj.id

    obj.id = uuid.uuid4()
    with pytest.raises(CognitiveObjectIdentityImmutableError):
        repo.update(obj)
    cognitive_session.rollback()
    cognitive_session.refresh(obj)
    assert obj.id == original_id


def test_i5_rollback_preserves_original_identity(repo, cognitive_session):
    obj = repo.add(CognitiveObject())
    cognitive_session.commit()
    original_id = obj.id

    obj.id = uuid.uuid4()
    with pytest.raises(CognitiveObjectIdentityImmutableError):
        cognitive_session.commit()
    cognitive_session.rollback()

    reloaded = repo.get_by_id(original_id)
    assert reloaded is not None
    assert reloaded.id == original_id


# --- C1-C5: COLISÃO ---


def test_c1_explicit_attempt_to_persist_existing_coid(repo, cognitive_session, manager):
    existing = repo.add(CognitiveObject())
    cognitive_session.commit()

    duplicate = CognitiveObject()
    duplicate.id = existing.id
    with pytest.raises(CoidCollisionError):
        repo.add(duplicate)
    cognitive_session.rollback()


def test_c2_collision_error_is_mapped_to_domain_error(repo, cognitive_session):
    existing = repo.add(CognitiveObject())
    cognitive_session.commit()

    duplicate = CognitiveObject()
    duplicate.id = existing.id
    with pytest.raises(CoidCollisionError) as exc_info:
        repo.add(duplicate)
    cognitive_session.rollback()

    assert exc_info.value.code == "PIA-8004"
    # a causa original do SQLAlchemy não escapa como o tipo de exceção
    # visto pela camada de domínio — está encadeada via __cause__, não
    # é o tipo levantado.
    from app.repositories.exceptions import PersistenceError

    assert not isinstance(exc_info.value, PersistenceError)


def test_c3_existing_object_is_not_overwritten(repo, cognitive_session):
    existing = repo.add(CognitiveObject())
    cognitive_session.commit()
    original_created_at = existing.created_at

    duplicate = CognitiveObject()
    duplicate.id = existing.id
    with pytest.raises(CoidCollisionError):
        repo.add(duplicate)
    cognitive_session.rollback()

    reloaded = repo.get_by_id(existing.id)
    assert reloaded is not None
    assert reloaded.created_at == original_created_at


def test_c4_existing_payload_is_not_altered(repo, cognitive_session):
    """Sem campo de conteúdo nesta fase — a verificação equivalente é
    que `clid`/`accessibility` do objeto existente permanecem
    inalterados após a tentativa de colisão."""
    existing = repo.add(CognitiveObject())
    cognitive_session.commit()
    existing.clid = uuid.uuid4()
    cognitive_session.commit()
    original_clid = existing.clid

    duplicate = CognitiveObject()
    duplicate.id = existing.id
    with pytest.raises(CoidCollisionError):
        repo.add(duplicate)
    cognitive_session.rollback()

    reloaded = repo.get_by_id(existing.id)
    assert reloaded.clid == original_clid


def test_c5_transaction_fails_and_rolls_back_correctly(cognitive_sqlite_session_factory):
    from app.repositories.unit_of_work import UnitOfWork

    with UnitOfWork(cognitive_sqlite_session_factory) as uow:
        repo_uow = ObjectRepository(uow.session)
        existing = repo_uow.add(CognitiveObject())
        uow.commit()
        existing_id = existing.id

    with pytest.raises(CoidCollisionError), UnitOfWork(cognitive_sqlite_session_factory) as uow:
        repo_uow = ObjectRepository(uow.session)
        duplicate = CognitiveObject()
        duplicate.id = existing_id
        repo_uow.add(duplicate)

    # sessão/transação seguinte não vê nenhum efeito da tentativa falha
    with UnitOfWork(cognitive_sqlite_session_factory) as uow:
        repo_uow = ObjectRepository(uow.session)
        assert len(repo_uow.list()) == 1


# --- IMP1-IMP5: IMPORT ---


def test_imp1_imported_coid_valid_and_nonexistent(manager):
    result = manager.validate_imported_coid(str(uuid.uuid4()))
    assert result.status == ImportedCoidStatus.VALID
    assert result.coid is not None


def test_imp2_imported_coid_invalid(manager):
    result = manager.validate_imported_coid("not-a-uuid")
    assert result.status == ImportedCoidStatus.INVALID
    assert result.coid is None


def test_imp3_imported_coid_already_existing(repo, cognitive_session, manager):
    existing = repo.add(CognitiveObject())
    cognitive_session.commit()

    result = manager.validate_imported_coid(str(existing.id))
    assert result.status == ImportedCoidStatus.COLLISION
    assert result.coid == existing.id


def test_imp4_no_silent_auto_remap(repo, cognitive_session, manager):
    """Um COID importado colidente nunca é silenciosamente trocado por
    outro — o resultado apenas classifica; nenhuma escrita acontece."""
    existing = repo.add(CognitiveObject())
    cognitive_session.commit()
    count_before = len(repo.list())

    result = manager.validate_imported_coid(str(existing.id))

    assert result.status == ImportedCoidStatus.COLLISION
    assert result.coid == existing.id  # nunca outro valor
    assert len(repo.list()) == count_before  # nenhum objeto criado/alterado


def test_imp5_collision_result_is_explicitly_identifiable(manager, repo, cognitive_session):
    """Os três resultados são estruturalmente distinguíveis via
    `ImportedCoidValidation.status`, não por inspeção ad-hoc de
    exceções ou heurística."""
    existing = repo.add(CognitiveObject())
    cognitive_session.commit()

    valid = manager.validate_imported_coid(str(uuid.uuid4()))
    invalid = manager.validate_imported_coid("xxx")
    collision = manager.validate_imported_coid(str(existing.id))

    statuses = {valid.status, invalid.status, collision.status}
    assert statuses == {
        ImportedCoidStatus.VALID,
        ImportedCoidStatus.INVALID,
        ImportedCoidStatus.COLLISION,
    }
    assert isinstance(valid, ImportedCoidValidation)


# --- MULTI-IA-READY ---


def test_multi_ai_two_independent_origins_receive_distinct_coids(repo, cognitive_session):
    """Simula (sem SDK real) duas origens independentes — mesmo
    'conteúdo' (nenhum, nesta fase) — recebendo COIDs distintos."""
    agent_a_output = repo.add(CognitiveObject())
    agent_b_output = repo.add(CognitiveObject())
    cognitive_session.commit()

    assert agent_a_output.id != agent_b_output.id


def test_coid_manager_has_no_agent_or_provider_parameter_anywhere():
    """Nenhum método público de `CoidManager` aceita provider/model/
    agent — neutralidade Multi-IA estrutural (§15 do módulo E3.2)."""
    import inspect

    forbidden = {"provider", "provider_id", "model", "model_id", "agent", "agent_id"}
    for name, method in inspect.getmembers(CoidManager, predicate=inspect.isfunction):
        if name.startswith("_"):
            continue
        params = set(inspect.signature(method).parameters)
        assert params.isdisjoint(forbidden), f"{name} aceita parâmetro proibido"
