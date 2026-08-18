"""
Testes de `ClidManager` — §35-§39 do módulo E3.3 (CL1-CL8, INH1-INH6,
Multi-IA-ready).
"""

import uuid

import pytest

from app.cognitive.errors.exceptions import (
    ClidInvalidError,
    CognitiveObjectClidAlreadySetError,
)
from app.cognitive.models.cognitive_object import CognitiveObject
from app.cognitive.repositories.lineage_repository import LineageRepository
from app.cognitive.repositories.object_repository import ObjectRepository
from app.cognitive.services.clid_manager import (
    ClidManager,
    ImportedClidStatus,
    ImportedClidValidation,
)


@pytest.fixture
def objects(cognitive_session):
    return ObjectRepository(cognitive_session)


@pytest.fixture
def lineage(cognitive_session):
    return LineageRepository(cognitive_session)


@pytest.fixture
def manager(objects, lineage):
    return ClidManager(objects, lineage)


# --- CL1-CL8 ---


def test_cl1_generate_produces_a_valid_clid(manager):
    clid = manager.generate()
    assert isinstance(clid, uuid.UUID)


def test_cl2_generated_clids_are_distinct(manager):
    generated = {manager.generate() for _ in range(50)}
    assert len(generated) == 50


def test_cl3_null_to_clid_permitted(objects, manager, cognitive_session):
    obj = objects.add(CognitiveObject())
    cognitive_session.commit()
    assert obj.clid is None

    clid = manager.generate()
    manager.assign(obj, clid)
    cognitive_session.commit()
    assert obj.clid == clid


def test_cl4_clid_a_to_clid_a_is_idempotent(objects, manager, cognitive_session):
    obj = objects.add(CognitiveObject())
    cognitive_session.commit()
    clid = manager.generate()
    manager.assign(obj, clid)
    cognitive_session.commit()

    manager.assign(obj, clid)  # não deve levantar
    cognitive_session.commit()
    assert obj.clid == clid


def test_cl5_clid_a_to_clid_b_rejected(objects, manager, cognitive_session):
    obj = objects.add(CognitiveObject())
    cognitive_session.commit()
    manager.assign(obj, manager.generate())
    cognitive_session.commit()

    with pytest.raises(CognitiveObjectClidAlreadySetError) as exc_info:
        manager.assign(obj, manager.generate())
    assert exc_info.value.code == "PIA-8002"


def test_cl6_clid_a_to_null_rejected(objects, manager, cognitive_session):
    obj = objects.add(CognitiveObject())
    cognitive_session.commit()
    manager.assign(obj, manager.generate())
    cognitive_session.commit()

    with pytest.raises(CognitiveObjectClidAlreadySetError):
        obj.clid = None


def test_cl7_coid_unchanged_when_assigning_clid(objects, manager, cognitive_session):
    obj = objects.add(CognitiveObject())
    cognitive_session.commit()
    original_coid = obj.id

    manager.assign(obj, manager.generate())
    cognitive_session.commit()
    assert obj.id == original_coid


def test_cl8_same_content_does_not_force_same_clid(objects, manager, cognitive_session):
    """Sem campo de conteúdo nesta fase — "mesmo conteúdo" aqui
    significa dois objetos criados de forma independente, idênticos em
    todos os campos, que não recebem o mesmo CLID automaticamente."""
    a = objects.add(CognitiveObject())
    b = objects.add(CognitiveObject())
    cognitive_session.commit()

    assert a.clid is None
    assert b.clid is None  # nenhuma inferência automática de CLID compartilhado


def test_assert_assignable_does_not_mutate_entity(objects, manager, cognitive_session):
    """`assert_assignable` é puramente de leitura — nunca muta a
    entidade, mesmo quando levantaria erro se fosse uma atribuição
    real."""
    obj = objects.add(CognitiveObject())
    cognitive_session.commit()
    manager.assign(obj, manager.generate())
    cognitive_session.commit()
    original_clid = obj.clid

    with pytest.raises(CognitiveObjectClidAlreadySetError):
        manager.assert_assignable(obj, uuid.uuid4())

    assert obj.clid == original_clid  # não mudou


def test_assert_assignable_does_not_raise_for_first_assignment(objects, manager):
    obj = objects.add(CognitiveObject())
    manager.assert_assignable(obj, uuid.uuid4())  # não deve levantar


def test_assert_assignable_does_not_raise_for_idempotent_value(objects, manager, cognitive_session):
    obj = objects.add(CognitiveObject())
    cognitive_session.commit()
    clid = manager.generate()
    manager.assign(obj, clid)
    cognitive_session.commit()

    manager.assert_assignable(obj, clid)  # não deve levantar


# --- validate() ---


def test_validate_accepts_uuid_and_str(manager):
    clid = uuid.uuid4()
    assert manager.validate(clid) == clid
    assert manager.validate(str(clid)) == clid


def test_validate_rejects_invalid_value(manager):
    with pytest.raises(ClidInvalidError) as exc_info:
        manager.validate("not-a-uuid")
    assert exc_info.value.code == "PIA-8005"


def test_validate_rejects_non_str_non_uuid_type(manager):
    with pytest.raises(ClidInvalidError):
        manager.validate(12345)
    with pytest.raises(ClidInvalidError):
        manager.validate(None)


# --- INH1-INH6 ---


def test_inh1_parent_with_clid_propagates_to_child(objects, manager, cognitive_session):
    parent = objects.add(CognitiveObject())
    child = objects.add(CognitiveObject())
    cognitive_session.commit()
    parent_clid = manager.generate()
    manager.assign(parent, parent_clid)
    cognitive_session.commit()

    manager.inherit(parent, child)
    cognitive_session.commit()
    assert child.clid == parent_clid


def test_inh1_parent_without_clid_generates_new_one_for_both(objects, manager, cognitive_session):
    parent = objects.add(CognitiveObject())
    child = objects.add(CognitiveObject())
    cognitive_session.commit()
    assert parent.clid is None

    manager.inherit(parent, child)
    cognitive_session.commit()

    assert parent.clid is not None
    assert child.clid == parent.clid


def test_inh2_coids_remain_distinct(objects, manager, cognitive_session):
    parent = objects.add(CognitiveObject())
    child = objects.add(CognitiveObject())
    cognitive_session.commit()

    manager.inherit(parent, child)
    cognitive_session.commit()
    assert parent.id != child.id


def test_inh3_parent_without_clid_policy_is_frozen(objects, manager, cognitive_session):
    """Política congelada (§11 do módulo E3.3): parent sem CLID recebe
    um novo CLID gerado, que é então propagado ao child — não um erro,
    não uma continuidade "vazia"."""
    parent = objects.add(CognitiveObject())
    child = objects.add(CognitiveObject())
    cognitive_session.commit()

    edge = manager.inherit(parent, child)
    cognitive_session.commit()

    assert parent.clid is not None
    assert edge.relation_type is not None


def test_inh4_child_with_incompatible_clid_is_rejected(objects, manager, cognitive_session):
    parent = objects.add(CognitiveObject())
    child = objects.add(CognitiveObject())
    cognitive_session.commit()
    manager.assign(parent, manager.generate())
    manager.assign(child, manager.generate())  # CLID diferente, já setado
    cognitive_session.commit()

    with pytest.raises(CognitiveObjectClidAlreadySetError):
        manager.inherit(parent, child)


def test_inh5_and_inh6_failure_leaves_no_partial_state(cognitive_sqlite_session_factory):
    """INH5 (sem estado parcial) + INH6 (rollback restaura estado
    anterior), via `UnitOfWork` real."""
    from app.repositories.unit_of_work import UnitOfWork

    with UnitOfWork(cognitive_sqlite_session_factory) as uow:
        objs = ObjectRepository(uow.session)
        parent = objs.add(CognitiveObject())
        child = objs.add(CognitiveObject())
        uow.commit()
        parent_id, child_id = parent.id, child.id

    with UnitOfWork(cognitive_sqlite_session_factory) as uow:
        objs = ObjectRepository(uow.session)
        c = objs.get_by_id(child_id)
        c.clid = uuid.uuid4()  # CLID incompatível pré-existente
        objs.update(c)
        uow.commit()

    with (
        pytest.raises(CognitiveObjectClidAlreadySetError),
        UnitOfWork(cognitive_sqlite_session_factory) as uow,
    ):
        objs = ObjectRepository(uow.session)
        lin = LineageRepository(uow.session)
        mgr = ClidManager(objs, lin)
        p = objs.get_by_id(parent_id)
        c = objs.get_by_id(child_id)
        mgr.inherit(p, c)

    with UnitOfWork(cognitive_sqlite_session_factory) as uow:
        objs = ObjectRepository(uow.session)
        p_reloaded = objs.get_by_id(parent_id)
        assert p_reloaded.clid is None  # INH6: rollback restaurou estado anterior


# --- Multi-IA-ready (MIA1-MIA5) ---


def test_mia1_a_and_b_coexist_with_distinct_coids(objects, cognitive_session):
    a = objects.add(CognitiveObject())
    b = objects.add(CognitiveObject())
    cognitive_session.commit()
    assert a.id != b.id


def test_mia2_a_and_b_can_share_clid_explicitly(objects, manager, cognitive_session):
    """COMPLEMENTARY: IA-A gera A, IA-B critica e produz B — A e B
    podem compartilhar CLID por operação explícita (`inherit`), nunca
    automaticamente."""
    a = objects.add(CognitiveObject())
    b = objects.add(CognitiveObject())
    cognitive_session.commit()
    assert a.clid is None and b.clid is None  # nada automático — nenhum CLID atribuído sozinho

    manager.inherit(a, b)
    cognitive_session.commit()
    assert a.clid == b.clid  # só depois de operação explícita


def test_mia3_chain_a_b_c_can_share_one_clid(objects, manager, cognitive_session):
    """SEQUENTIAL: A produz -> B revisa -> C corrige, todos
    compartilhando CLID, sem sobrescrever objetos anteriores."""
    a = objects.add(CognitiveObject())
    b = objects.add(CognitiveObject())
    c = objects.add(CognitiveObject())
    cognitive_session.commit()

    manager.inherit(a, b)
    manager.inherit(b, c)
    cognitive_session.commit()

    assert a.clid == b.clid == c.clid
    assert a.id != b.id != c.id != a.id


def test_mia4_no_provider_or_model_parameter_anywhere():
    import inspect

    forbidden = {"provider", "provider_id", "model", "model_id", "agent", "agent_id"}
    for name, method in inspect.getmembers(ClidManager, predicate=inspect.isfunction):
        if name.startswith("_"):
            continue
        params = set(inspect.signature(method).parameters)
        assert params.isdisjoint(forbidden), f"{name} aceita parâmetro proibido"


def test_mia5_no_previous_object_is_overwritten(objects, manager, cognitive_session):
    a = objects.add(CognitiveObject())
    b = objects.add(CognitiveObject())
    cognitive_session.commit()
    a_created_at = a.created_at

    manager.inherit(a, b)
    cognitive_session.commit()

    assert a.created_at == a_created_at  # 'a' não foi tocado além do clid
    assert objects.get_by_id(a.id) is not None  # 'a' continua existindo, não substituído


# --- Import (§22) ---


def test_import_valid_when_entity_has_no_clid(objects, manager, cognitive_session):
    obj = objects.add(CognitiveObject())
    cognitive_session.commit()

    result = manager.validate_imported_clid(obj, str(uuid.uuid4()))
    assert result.status == ImportedClidStatus.VALID
    assert isinstance(result, ImportedClidValidation)


def test_import_invalid_format(objects, manager, cognitive_session):
    obj = objects.add(CognitiveObject())
    cognitive_session.commit()

    result = manager.validate_imported_clid(obj, "not-a-uuid")
    assert result.status == ImportedClidStatus.INVALID
    assert result.clid is None


def test_import_incompatible_with_existing_clid(objects, manager, cognitive_session):
    obj = objects.add(CognitiveObject())
    cognitive_session.commit()
    manager.assign(obj, manager.generate())
    cognitive_session.commit()

    result = manager.validate_imported_clid(obj, str(uuid.uuid4()))
    assert result.status == ImportedClidStatus.INCOMPATIBLE


def test_import_valid_when_matches_existing_clid(objects, manager, cognitive_session):
    """Reimportar o mesmo CLID que o objeto já tem é VALID (idempotente),
    não INCOMPATIBLE."""
    obj = objects.add(CognitiveObject())
    cognitive_session.commit()
    existing_clid = manager.generate()
    manager.assign(obj, existing_clid)
    cognitive_session.commit()

    result = manager.validate_imported_clid(obj, str(existing_clid))
    assert result.status == ImportedClidStatus.VALID


def test_import_no_silent_auto_remap(objects, manager, cognitive_session):
    obj = objects.add(CognitiveObject())
    cognitive_session.commit()
    manager.assign(obj, manager.generate())
    cognitive_session.commit()
    original_clid = obj.clid

    manager.validate_imported_clid(obj, str(uuid.uuid4()))

    assert obj.clid == original_clid  # nunca alterado por esta chamada
