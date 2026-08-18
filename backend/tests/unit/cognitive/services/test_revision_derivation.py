"""
Testes de `VersionManager.derive()`/`.revise()` — §22-§25 do prompt
corretivo E3.4.0 (D1-D7, R1-R9, W1-W4). Complementa
`test_version_manager.py` (V1-V7, do módulo E3.4 original — ainda
válidos e passando, ver arquivo irmão).
"""

import pytest

from app.cognitive.errors.exceptions import RevisionStatusInvalidTransitionError
from app.cognitive.models.cognitive_object import CognitiveObject
from app.cognitive.models.enums import RevisionStatus, TransformationKind
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


# --- D1-D7: DERIVATION ---


def test_d1_derive_creates_new_coid(objects, version_manager, cognitive_session):
    source = objects.add(CognitiveObject())
    cognitive_session.commit()

    target, _, _ = version_manager.derive(source, operation_type="summarize")
    cognitive_session.commit()

    assert target.id != source.id


def test_d2_source_remains_intact(objects, version_manager, cognitive_session):
    source = objects.add(CognitiveObject())
    cognitive_session.commit()
    original_created_at = source.created_at

    version_manager.derive(source, operation_type="summarize")
    cognitive_session.commit()

    assert source.created_at == original_created_at
    assert not source.is_deleted


def test_d3_source_does_not_become_superseded_automatically(
    objects, version_manager, cognitive_session
):
    source = objects.add(CognitiveObject())
    cognitive_session.commit()
    assert source.revision_status is None

    version_manager.derive(source, operation_type="summarize")
    cognitive_session.commit()

    assert source.revision_status is None  # nunca tocado por derive()


def test_d3_derive_does_not_supersede_a_current_source(objects, version_manager, cognitive_session):
    """Mesmo quando `source` já é `CURRENT` (parte de uma cadeia de
    revisão controlada), `derive()` não o altera — uma derivação
    (ex.: um resumo) não é uma nova revisão."""
    source = objects.add(CognitiveObject())
    cognitive_session.commit()
    source.revision_status = RevisionStatus.CURRENT
    cognitive_session.commit()

    version_manager.derive(source, operation_type="summarize")
    cognitive_session.commit()

    assert source.revision_status == RevisionStatus.CURRENT


def test_d4_lineage_is_registered(objects, lineage, version_manager, cognitive_session):
    source = objects.add(CognitiveObject())
    cognitive_session.commit()

    target, edge, _ = version_manager.derive(source, operation_type="summarize")
    cognitive_session.commit()

    assert lineage.edge_exists(source.id, target.id, edge.relation_type)


def test_d5_transformation_record_is_registered_as_derivation(
    objects, version_manager, cognitive_session
):
    source = objects.add(CognitiveObject())
    cognitive_session.commit()

    _, _, record = version_manager.derive(source, operation_type="summarize")
    cognitive_session.commit()

    assert record.transformation_kind == TransformationKind.DERIVATION


def test_d6_clid_semantics_followed(objects, version_manager, cognitive_session):
    source = objects.add(CognitiveObject())
    cognitive_session.commit()

    target, _, _ = version_manager.derive(source, operation_type="summarize")
    cognitive_session.commit()

    assert target.clid == source.clid
    assert target.clid is not None


def test_d7_two_derivations_can_coexist(objects, version_manager, cognitive_session):
    """`A` derivando `B` e `C` simultaneamente — branch natural, sem
    exigir CURRENT/SUPERSEDED entre elas (§14 do prompt corretivo)."""
    source = objects.add(CognitiveObject())
    cognitive_session.commit()

    b, _, _ = version_manager.derive(source, operation_type="summarize")
    c, _, _ = version_manager.derive(source, operation_type="translate")
    cognitive_session.commit()

    assert b.id != c.id
    assert b.clid == c.clid == source.clid
    assert b.revision_status is None
    assert c.revision_status is None


# --- R1-R9: REVISION ---


def test_r1_revise_creates_new_coid(objects, version_manager, cognitive_session):
    source = objects.add(CognitiveObject())
    cognitive_session.commit()

    target, _, _ = version_manager.revise(source, operation_type="revise")
    cognitive_session.commit()

    assert target.id != source.id


def test_r2_same_clid_continuity(objects, version_manager, cognitive_session):
    source = objects.add(CognitiveObject())
    cognitive_session.commit()

    target, _, _ = version_manager.revise(source, operation_type="revise")
    cognitive_session.commit()

    assert target.clid == source.clid
    assert target.clid is not None


def test_r3_target_becomes_current(objects, version_manager, cognitive_session):
    source = objects.add(CognitiveObject())
    cognitive_session.commit()

    target, _, _ = version_manager.revise(source, operation_type="revise")
    cognitive_session.commit()

    assert target.revision_status == RevisionStatus.CURRENT


def test_r4_previously_current_source_becomes_superseded(
    objects, version_manager, cognitive_session
):
    source = objects.add(CognitiveObject())
    cognitive_session.commit()
    source.revision_status = RevisionStatus.CURRENT
    cognitive_session.commit()

    version_manager.revise(source, operation_type="revise")
    cognitive_session.commit()

    assert source.revision_status == RevisionStatus.SUPERSEDED


def test_r5_source_remains_recoverable(objects, version_manager, cognitive_session):
    source = objects.add(CognitiveObject())
    cognitive_session.commit()
    source_id = source.id

    version_manager.revise(source, operation_type="revise")
    cognitive_session.commit()

    reloaded = objects.get_by_id(source_id)
    assert reloaded is not None
    assert reloaded.revision_status == RevisionStatus.SUPERSEDED  # não DELETED


def test_r6_lineage_is_correct(objects, lineage, version_manager, cognitive_session):
    source = objects.add(CognitiveObject())
    cognitive_session.commit()

    target, edge, _ = version_manager.revise(source, operation_type="revise")
    cognitive_session.commit()

    assert edge.parent_coid == source.id
    assert edge.child_coid == target.id


def test_r7_transformation_record_is_correct(objects, version_manager, cognitive_session):
    source = objects.add(CognitiveObject())
    cognitive_session.commit()

    target, _, record = version_manager.revise(source, operation_type="revise")
    cognitive_session.commit()

    assert record.transformation_kind == TransformationKind.REVISION
    assert record.input_refs == [str(source.id)]
    assert record.output_refs == [str(target.id)]


def test_r8_rollback_restores_previous_current_if_operation_fails(
    objects, cognitive_sqlite_session_factory
):
    """Força falha na última etapa (`TransformationRecord`) — o
    `CURRENT` anterior deve ser restaurado após rollback (nenhum
    estado parcial com `target` `CURRENT` e `source` `SUPERSEDED` sem
    o registro correspondente)."""
    from app.repositories.unit_of_work import UnitOfWork

    with UnitOfWork(cognitive_sqlite_session_factory) as uow:
        objs = ObjectRepository(uow.session)
        source = objs.add(CognitiveObject())
        source.revision_status = RevisionStatus.CURRENT
        objs.update(source)
        uow.commit()
        source_id = source.id

    import pytest as _pytest

    def _raise_on_add(self, entity):
        raise RuntimeError("falha simulada ao persistir TransformationRecord")

    with _pytest.MonkeyPatch.context() as mp:
        mp.setattr(TransformationRepository, "add", _raise_on_add)

        with pytest.raises(RuntimeError), UnitOfWork(cognitive_sqlite_session_factory) as uow:
            objs = ObjectRepository(uow.session)
            lin = LineageRepository(uow.session)
            trans = TransformationRepository(uow.session)
            mgr = ClidManager(objs, lin)
            vmgr = VersionManager(objs, mgr, trans)

            src = objs.get_by_id(source_id)
            vmgr.revise(src, operation_type="revise")

    with UnitOfWork(cognitive_sqlite_session_factory) as uow:
        objs = ObjectRepository(uow.session)
        reloaded_source = objs.get_by_id(source_id)
        assert reloaded_source.revision_status == RevisionStatus.CURRENT  # restaurado
        assert len(objs.list()) == 1  # nenhum target sobreviveu


def test_r9_at_most_one_current_after_operation(objects, version_manager, cognitive_session):
    source = objects.add(CognitiveObject())
    cognitive_session.commit()

    rev1, _, _ = version_manager.revise(source, operation_type="revise")
    cognitive_session.commit()
    rev2, _, _ = version_manager.revise(rev1, operation_type="revise")
    cognitive_session.commit()

    all_objects = objects.list()
    currents = [o for o in all_objects if o.revision_status == RevisionStatus.CURRENT]
    assert len(currents) == 1
    assert currents[0].id == rev2.id


def test_revise_on_already_superseded_source_is_rejected(
    objects, version_manager, cognitive_session
):
    source = objects.add(CognitiveObject())
    cognitive_session.commit()

    rev1, _, _ = version_manager.revise(source, operation_type="revise")
    cognitive_session.commit()

    with pytest.raises(RevisionStatusInvalidTransitionError) as exc_info:
        version_manager.revise(source, operation_type="revise again")
    assert exc_info.value.code == "PIA-8011"


def test_revise_operation_type_empty_is_rejected(objects, version_manager, cognitive_session):
    source = objects.add(CognitiveObject())
    cognitive_session.commit()

    with pytest.raises(ValueError, match="operation_type"):
        version_manager.revise(source, operation_type="")


# --- W1-W4: WORKSPACE / CONTROLLED ASSET ---


def test_w1_version_manager_does_not_auto_promote_anything(objects, cognitive_session):
    """Criar um `CognitiveObject` simples (workspace/transitório) não
    o torna, sozinho, parte de uma cadeia controlada — `revision_status`
    permanece `None` até uma chamada explícita a `revise()`."""
    obj = objects.add(CognitiveObject())
    cognitive_session.commit()
    assert obj.revision_status is None


def test_w2_derive_and_revise_require_explicit_call(objects, version_manager, cognitive_session):
    """Nenhum objeto se torna `CURRENT`/`SUPERSEDED` "sozinho" — só
    chamando `revise()` explicitamente."""
    source = objects.add(CognitiveObject())
    cognitive_session.commit()
    assert source.revision_status is None

    # derive() não estabelece revision_status
    target_derive, _, _ = version_manager.derive(source, operation_type="summarize")
    cognitive_session.commit()
    assert target_derive.revision_status is None

    # só revise() explicitamente estabelece
    target_revise, _, _ = version_manager.revise(source, operation_type="revise")
    cognitive_session.commit()
    assert target_revise.revision_status == RevisionStatus.CURRENT


def test_w3_no_conversation_or_provider_data_persisted_by_this_module():
    """Nenhum campo de `CognitiveObject`/`TransformationRecord` guarda
    conteúdo de conversa ou dados de provider — verificado por
    inspeção das colunas reais."""
    cognitive_object_columns = {c.name for c in CognitiveObject.__table__.columns}
    from app.cognitive.models.transformation_record import TransformationRecord

    transformation_columns = {c.name for c in TransformationRecord.__table__.columns}

    forbidden = {"conversation", "chat_history", "provider", "model", "prompt", "message"}
    assert cognitive_object_columns.isdisjoint(forbidden)
    assert transformation_columns.isdisjoint(forbidden)


def test_w4_no_ai_sdk_import_anywhere_in_version_manager():
    import inspect

    import app.cognitive.services.version_manager as version_manager_module

    source_code = inspect.getsource(version_manager_module)
    for forbidden_token in ("openai", "anthropic", "google.generativeai", "cohere"):
        assert forbidden_token not in source_code.lower()
