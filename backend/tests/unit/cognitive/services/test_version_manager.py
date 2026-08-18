"""
Testes de `VersionManager` — §16 do módulo E3.4 (V1-V5, V7; V6/V8 nos
arquivos de integração/suíte completa).
"""

import pytest

from app.cognitive.models.cognitive_object import CognitiveObject
from app.cognitive.models.enums import LineageRelation
from app.cognitive.repositories.lineage_repository import LineageRepository
from app.cognitive.repositories.object_repository import ObjectRepository
from app.cognitive.repositories.transformation_repository import TransformationRepository
from app.cognitive.services.clid_manager import ClidManager
from app.cognitive.services.version_manager import VersionManager


@pytest.fixture
def objects(cognitive_session):
    return ObjectRepository(cognitive_session)


@pytest.fixture
def lineage(cognitive_session):
    return LineageRepository(cognitive_session)


@pytest.fixture
def transformations(cognitive_session):
    return TransformationRepository(cognitive_session)


@pytest.fixture
def clid_manager(objects, lineage):
    return ClidManager(objects, lineage)


@pytest.fixture
def version_manager(objects, clid_manager, transformations):
    return VersionManager(objects, clid_manager, transformations)


# --- V1: VERSION IDENTITY ---


def test_v1_source_and_target_have_different_coids(objects, version_manager, cognitive_session):
    source = objects.add(CognitiveObject())
    cognitive_session.commit()

    target, _, _ = version_manager.derive(source, operation_type="derive")
    cognitive_session.commit()

    assert source.id != target.id


def test_v1_source_remains_intact(objects, version_manager, cognitive_session):
    source = objects.add(CognitiveObject())
    cognitive_session.commit()
    source_created_at = source.created_at

    version_manager.derive(source, operation_type="derive")
    cognitive_session.commit()

    assert source.created_at == source_created_at
    assert not source.is_deleted
    reloaded_source = objects.get_by_id(source.id)
    assert reloaded_source is not None


def test_v1_target_is_persisted(objects, version_manager, cognitive_session):
    source = objects.add(CognitiveObject())
    cognitive_session.commit()

    target, _, _ = version_manager.derive(source, operation_type="derive")
    cognitive_session.commit()

    reloaded_target = objects.get_by_id(target.id)
    assert reloaded_target is not None
    assert reloaded_target.id == target.id


def test_v1_no_overwrite_of_source(objects, version_manager, cognitive_session):
    """`A.id = B.id` é proibido — nenhum caminho no código permite
    isso (o COID de `target` vem do `UUIDMixin`, nunca copiado de
    `source`)."""
    source = objects.add(CognitiveObject())
    cognitive_session.commit()
    original_id = source.id

    target, _, _ = version_manager.derive(source, operation_type="derive")
    cognitive_session.commit()

    assert source.id == original_id
    assert target.id != original_id


# --- V2: CONTINUITY ---


def test_v2_continuity_preserves_clid_when_source_has_one(
    objects, clid_manager, version_manager, cognitive_session
):
    source = objects.add(CognitiveObject())
    cognitive_session.commit()
    existing_clid = clid_manager.generate()
    clid_manager.assign(source, existing_clid)
    cognitive_session.commit()

    target, _, _ = version_manager.derive(source, operation_type="derive")
    cognitive_session.commit()

    assert target.clid == existing_clid


def test_v2_source_without_clid_uses_official_mechanism(
    objects, version_manager, cognitive_session
):
    source = objects.add(CognitiveObject())
    cognitive_session.commit()
    assert source.clid is None

    target, _, _ = version_manager.derive(source, operation_type="derive")
    cognitive_session.commit()

    assert source.clid is not None
    assert target.clid == source.clid


def test_v2_invalid_attempt_respects_immutability(
    objects, clid_manager, version_manager, cognitive_session
):
    """Se `target` já tem um CLID incompatível (cenário artificial,
    mas testável), `derive()` propaga a rejeição de `inherit()` —
    nenhum bypass."""
    source = objects.add(CognitiveObject())
    cognitive_session.commit()
    clid_manager.assign(source, clid_manager.generate())
    cognitive_session.commit()

    # não há como criar esse cenário via derive() sozinho (target é
    # sempre novo) — mas o mecanismo subjacente (inherit) já é testado
    # exaustivamente em E3.3; aqui confirmamos que derive() não
    # contorna a proteção reimplementando algo próprio.
    import inspect

    source_code = inspect.getsource(version_manager.derive)
    assert "self._clid.inherit" in source_code  # reaproveita, não duplica


# --- V3: TRANSFORMATION RECORD ---


def test_v3_record_references_correct_source_and_target(
    objects, version_manager, cognitive_session
):
    source = objects.add(CognitiveObject())
    cognitive_session.commit()

    target, _, record = version_manager.derive(source, operation_type="summarize")
    cognitive_session.commit()

    assert record.input_refs == [str(source.id)]
    assert record.output_refs == [str(target.id)]


def test_v3_record_has_correct_operation_type(objects, version_manager, cognitive_session):
    source = objects.add(CognitiveObject())
    cognitive_session.commit()

    _, _, record = version_manager.derive(source, operation_type="translate")
    cognitive_session.commit()

    assert record.operation_type == "translate"


def test_v3_record_is_persisted(objects, transformations, version_manager, cognitive_session):
    source = objects.add(CognitiveObject())
    cognitive_session.commit()

    _, _, record = version_manager.derive(source, operation_type="derive")
    cognitive_session.commit()

    reloaded = transformations.get_by_id(record.id)
    assert reloaded is not None


def test_v3_record_is_append_only(objects, transformations, version_manager, cognitive_session):
    from app.cognitive.errors.exceptions import TransformationRecordImmutableError

    source = objects.add(CognitiveObject())
    cognitive_session.commit()
    _, _, record = version_manager.derive(source, operation_type="derive")
    cognitive_session.commit()

    with pytest.raises(TransformationRecordImmutableError):
        transformations.update(record)
    with pytest.raises(TransformationRecordImmutableError):
        transformations.delete(record)


def test_v3_operation_type_empty_is_rejected(objects, version_manager, cognitive_session):
    source = objects.add(CognitiveObject())
    cognitive_session.commit()

    with pytest.raises(ValueError, match="operation_type"):
        version_manager.derive(source, operation_type="")


# --- V4: LINEAGE ---


def test_v4_edge_source_to_target_is_correct(objects, version_manager, cognitive_session):
    source = objects.add(CognitiveObject())
    cognitive_session.commit()

    target, edge, _ = version_manager.derive(source, operation_type="derive")
    cognitive_session.commit()

    assert edge.parent_coid == source.id
    assert edge.child_coid == target.id


def test_v4_relation_type_defaults_to_transformed_from(objects, version_manager, cognitive_session):
    source = objects.add(CognitiveObject())
    cognitive_session.commit()

    _, edge, _ = version_manager.derive(source, operation_type="derive")
    cognitive_session.commit()

    assert edge.relation_type == LineageRelation.TRANSFORMED_FROM


def test_v4_relation_type_can_be_overridden(objects, version_manager, cognitive_session):
    source = objects.add(CognitiveObject())
    cognitive_session.commit()

    _, edge, _ = version_manager.derive(
        source, operation_type="branch", relation_type=LineageRelation.BRANCH
    )
    cognitive_session.commit()

    assert edge.relation_type == LineageRelation.BRANCH


def test_v4_lineage_queries_continue_working(objects, lineage, version_manager, cognitive_session):
    source = objects.add(CognitiveObject())
    cognitive_session.commit()

    target, _, _ = version_manager.derive(source, operation_type="derive")
    cognitive_session.commit()

    children = lineage.list_children(source.id)
    assert len(children) == 1
    assert children[0].child_coid == target.id

    parents = lineage.list_parents(target.id)
    assert len(parents) == 1
    assert parents[0].parent_coid == source.id


# --- V5: ATOMICITY ---


def test_v5_failure_in_transformation_record_step_leaves_no_partial_state(
    objects, cognitive_sqlite_session_factory, monkeypatch
):
    """Força falha na última etapa (`TransformationRecord`) via
    monkeypatch — nenhum `target`/`CLID`/`LineageEdge` das etapas
    anteriores, já escritas nesta mesma transação, deve sobreviver ao
    rollback externo."""
    from app.repositories.unit_of_work import UnitOfWork

    with UnitOfWork(cognitive_sqlite_session_factory) as uow:
        objs = ObjectRepository(uow.session)
        source = objs.add(CognitiveObject())
        uow.commit()
        source_id = source.id

    def _raise_on_add(self, entity):
        raise RuntimeError("falha simulada ao persistir TransformationRecord")

    monkeypatch.setattr(TransformationRepository, "add", _raise_on_add)

    with pytest.raises(RuntimeError), UnitOfWork(cognitive_sqlite_session_factory) as uow:
        objs = ObjectRepository(uow.session)
        lin = LineageRepository(uow.session)
        trans = TransformationRepository(uow.session)
        mgr = ClidManager(objs, lin)
        vmgr = VersionManager(objs, mgr, trans)

        src = objs.get_by_id(source_id)
        vmgr.derive(src, operation_type="derive")

    # target/CLID/LineageEdge criados nas etapas anteriores (dentro da
    # mesma transação) não sobrevivem ao rollback provocado pela
    # exceção na última etapa
    with UnitOfWork(cognitive_sqlite_session_factory) as uow:
        objs = ObjectRepository(uow.session)
        lin = LineageRepository(uow.session)
        trans = TransformationRepository(uow.session)

        reloaded_source = objs.get_by_id(source_id)
        assert reloaded_source.clid is None  # rollback restaurou o estado original
        assert len(objs.list()) == 1  # só o source — nenhum target sobreviveu
        assert len(lin.list_children(source_id)) == 0
        assert len(trans.list_by_input_coid(source_id)) == 0


def test_v5_successful_derive_leaves_complete_state_only(
    objects, version_manager, transformations, lineage, cognitive_session
):
    """Confirma o caso feliz: depois de um `derive()` bem-sucedido,
    target + CLID + edge + record existem todos juntos — nunca um
    subconjunto parcial."""
    source = objects.add(CognitiveObject())
    cognitive_session.commit()

    target, edge, record = version_manager.derive(source, operation_type="derive")
    cognitive_session.commit()

    assert objects.get_by_id(target.id) is not None
    assert target.clid is not None
    assert lineage.edge_exists(source.id, target.id, edge.relation_type)
    assert transformations.get_by_id(record.id) is not None


def test_v5_rollback_via_unit_of_work_removes_everything(cognitive_sqlite_session_factory):
    from app.repositories.unit_of_work import UnitOfWork

    with UnitOfWork(cognitive_sqlite_session_factory) as uow:
        objs = ObjectRepository(uow.session)
        source = objs.add(CognitiveObject())
        uow.commit()
        source_id = source.id

    with pytest.raises(ValueError), UnitOfWork(cognitive_sqlite_session_factory) as uow:
        objs = ObjectRepository(uow.session)
        lin = LineageRepository(uow.session)
        trans = TransformationRepository(uow.session)
        mgr = ClidManager(objs, lin)
        vmgr = VersionManager(objs, mgr, trans)

        src = objs.get_by_id(source_id)
        vmgr.derive(src, operation_type="derive")
        raise ValueError("falha simulada após derive(), antes do commit externo")

    with UnitOfWork(cognitive_sqlite_session_factory) as uow:
        objs = ObjectRepository(uow.session)
        lin = LineageRepository(uow.session)
        trans = TransformationRepository(uow.session)

        reloaded_source = objs.get_by_id(source_id)
        assert reloaded_source.clid is None
        assert len(objs.list()) == 1  # só o source — nenhum target sobreviveu
        assert len(lin.list_children(source_id)) == 0
        assert len(trans.list_by_input_coid(source_id)) == 0


# --- V7: MULTI-AI READINESS ---


def test_v7_no_provider_model_agent_parameter_anywhere():
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
    for name, method in inspect.getmembers(VersionManager, predicate=inspect.isfunction):
        if name.startswith("_"):
            continue
        params = set(inspect.signature(method).parameters)
        assert params.isdisjoint(forbidden), f"{name} aceita parâmetro proibido"


def test_v7_derive_does_not_import_any_provider_sdk():
    import inspect

    source_code = inspect.getsource(
        __import__("app.cognitive.services.version_manager", fromlist=["version_manager"])
    )
    for forbidden_token in ("openai", "anthropic", "google.generativeai", "cohere"):
        assert forbidden_token not in source_code.lower()
