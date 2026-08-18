"""
Fault injection completo de `derive()`/`revise()` — correção E3.4.1,
§9 do prompt corretivo (A1-A7). Complementa o teste já existente de
falha em `TransformationRecord`
(`test_v5_failure_in_transformation_record_step_leaves_no_partial_state`,
em `test_version_manager.py`).
"""

import pytest

from app.cognitive.models.cognitive_object import CognitiveObject
from app.cognitive.models.enums import RevisionStatus
from app.cognitive.repositories.lineage_repository import LineageRepository
from app.cognitive.repositories.object_repository import ObjectRepository
from app.cognitive.repositories.transformation_repository import TransformationRepository
from app.cognitive.services.clid_manager import ClidManager
from app.cognitive.services.version_manager import VersionManager
from app.repositories.unit_of_work import UnitOfWork


def _setup_source(session_factory, *, current: bool = False):
    with UnitOfWork(session_factory) as uow:
        objs = ObjectRepository(uow.session)
        source = objs.add(CognitiveObject())
        if current:
            source.revision_status = RevisionStatus.CURRENT
            objs.update(source)
        uow.commit()
        return source.id


def _assert_no_orphan_state(session_factory, source_id):
    """Nenhum estado parcial sobrevive: `source` recuperável, nenhum
    `target` órfão, nenhuma lineage/transformação associada."""
    with UnitOfWork(session_factory) as uow:
        objs = ObjectRepository(uow.session)
        lin = LineageRepository(uow.session)
        trans = TransformationRepository(uow.session)

        reloaded_source = objs.get_by_id(source_id)
        assert reloaded_source is not None
        assert len(objs.list()) == 1
        assert len(lin.list_children(source_id)) == 0
        assert len(trans.list_by_input_coid(source_id)) == 0


# --- A1: falha na criação/persistência do target ---


def test_a1_target_creation_failure_rolls_back_completely(
    cognitive_sqlite_session_factory, monkeypatch
):
    from app.repositories.base_repository import BaseRepository

    source_id = _setup_source(cognitive_sqlite_session_factory)

    def _raise_on_add(self, entity):
        if isinstance(entity, CognitiveObject):
            raise RuntimeError("falha simulada ao criar target")
        return BaseRepository.add(self, entity)

    monkeypatch.setattr(BaseRepository, "add", _raise_on_add)

    with pytest.raises(RuntimeError), UnitOfWork(cognitive_sqlite_session_factory) as uow:
        objs = ObjectRepository(uow.session)
        lin = LineageRepository(uow.session)
        trans = TransformationRepository(uow.session)
        mgr = ClidManager(objs, lin)
        vmgr = VersionManager(objs, mgr, trans)
        src = objs.get_by_id(source_id)
        vmgr.derive(src, operation_type="summarize")

    _assert_no_orphan_state(cognitive_sqlite_session_factory, source_id)


# --- A2: falha durante resolução/propagação de CLID ---


def test_a2_clid_propagation_failure_rolls_back_completely(
    cognitive_sqlite_session_factory, monkeypatch
):
    from app.cognitive.services.clid_manager import ClidManager as _ClidManagerCls

    source_id = _setup_source(cognitive_sqlite_session_factory)

    def _raise_on_inherit(self, parent, child, **kwargs):
        raise RuntimeError("falha simulada durante inherit()/CLID")

    monkeypatch.setattr(_ClidManagerCls, "inherit", _raise_on_inherit)

    with pytest.raises(RuntimeError), UnitOfWork(cognitive_sqlite_session_factory) as uow:
        objs = ObjectRepository(uow.session)
        lin = LineageRepository(uow.session)
        trans = TransformationRepository(uow.session)
        mgr = ClidManager(objs, lin)
        vmgr = VersionManager(objs, mgr, trans)
        src = objs.get_by_id(source_id)
        vmgr.derive(src, operation_type="summarize")

    _assert_no_orphan_state(cognitive_sqlite_session_factory, source_id)


# --- A3: falha durante criação/persistência de LineageEdge ---


def test_a3_lineage_creation_failure_rolls_back_completely(
    cognitive_sqlite_session_factory, monkeypatch
):
    from app.cognitive.repositories.lineage_repository import (
        LineageRepository as _LineageRepositoryCls,
    )

    source_id = _setup_source(cognitive_sqlite_session_factory)

    def _raise_on_add_edge(self, **kwargs):
        raise RuntimeError("falha simulada ao criar LineageEdge")

    monkeypatch.setattr(_LineageRepositoryCls, "add_edge", _raise_on_add_edge)

    with pytest.raises(RuntimeError), UnitOfWork(cognitive_sqlite_session_factory) as uow:
        objs = ObjectRepository(uow.session)
        lin = LineageRepository(uow.session)
        trans = TransformationRepository(uow.session)
        mgr = ClidManager(objs, lin)
        vmgr = VersionManager(objs, mgr, trans)
        src = objs.get_by_id(source_id)
        vmgr.derive(src, operation_type="summarize")

    _assert_no_orphan_state(cognitive_sqlite_session_factory, source_id)

    with UnitOfWork(cognitive_sqlite_session_factory) as uow:
        objs = ObjectRepository(uow.session)
        reloaded_source = objs.get_by_id(source_id)
        assert reloaded_source.clid is None  # CLID também não deve ter sido propagado


# --- A4: falha durante transição de revision_status em revise() ---


def test_a4_revision_status_transition_failure_rolls_back_completely(
    cognitive_sqlite_session_factory, monkeypatch
):
    """Força a falha exatamente no ponto identificado e corrigido
    durante o desenvolvimento de E3.4.1: a `update()` dentro de
    `revise()` que seta `target.revision_status = CURRENT`.

    Identifica a chamada certa por critério semântico
    (`entity.revision_status == CURRENT`), não por posição/contagem —
    mesmo princípio já usado em
    `test_unrelated_persistence_error_during_current_update_is_not_reclassified`
    (`test_current_uniqueness.py`): `inherit()` também chama `update()`
    internamente para propagar CLID, e `revise()` chama `update()`
    duas vezes mais (`source→SUPERSEDED`, `target→CURRENT`) — a
    posição numérica de qual chamada é "a certa" não é estável entre
    cenários (ex.: varia conforme `source.clid` já estar setado ou
    não). O critério semântico é robusto independentemente de quantas
    chamadas internas a `update()` ocorram antes.
    """
    from app.repositories.base_repository import BaseRepository

    source_id = _setup_source(cognitive_sqlite_session_factory, current=True)

    original_update = BaseRepository.update

    def _raise_when_setting_current(self, entity):
        if getattr(entity, "revision_status", None) == RevisionStatus.CURRENT:
            raise RuntimeError("falha simulada na transição de revision_status")
        return original_update(self, entity)

    monkeypatch.setattr(BaseRepository, "update", _raise_when_setting_current)

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
        assert reloaded_source.revision_status == RevisionStatus.CURRENT
        assert len(objs.list()) == 1


# --- A5: falha na criação de TransformationRecord (revise, revalidação) ---


def test_a5_transformation_record_failure_in_revise_rolls_back_completely(
    cognitive_sqlite_session_factory, monkeypatch
):
    source_id = _setup_source(cognitive_sqlite_session_factory, current=True)

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
        vmgr.revise(src, operation_type="revise")

    with UnitOfWork(cognitive_sqlite_session_factory) as uow:
        objs = ObjectRepository(uow.session)
        reloaded_source = objs.get_by_id(source_id)
        assert reloaded_source.revision_status == RevisionStatus.CURRENT
        assert len(objs.list()) == 1


# --- A6: revise() bem-sucedido deixa estado coerente completo ---


def test_a6_successful_revise_leaves_complete_coherent_state(cognitive_sqlite_session_factory):
    source_id = _setup_source(cognitive_sqlite_session_factory, current=True)

    with UnitOfWork(cognitive_sqlite_session_factory) as uow:
        objs = ObjectRepository(uow.session)
        lin = LineageRepository(uow.session)
        trans = TransformationRepository(uow.session)
        mgr = ClidManager(objs, lin)
        vmgr = VersionManager(objs, mgr, trans)
        src = objs.get_by_id(source_id)
        target, edge, record = vmgr.revise(src, operation_type="revise")
        uow.commit()
        target_id, record_id = target.id, record.id
        relation_type = edge.relation_type

    with UnitOfWork(cognitive_sqlite_session_factory) as uow:
        objs = ObjectRepository(uow.session)
        lin = LineageRepository(uow.session)
        trans = TransformationRepository(uow.session)

        reloaded_source = objs.get_by_id(source_id)
        reloaded_target = objs.get_by_id(target_id)
        assert reloaded_source.revision_status == RevisionStatus.SUPERSEDED
        assert reloaded_target.revision_status == RevisionStatus.CURRENT
        assert reloaded_target.clid == reloaded_source.clid
        assert lin.edge_exists(source_id, target_id, relation_type)
        assert trans.get_by_id(record_id) is not None


# --- A7: derive() bem-sucedido deixa estado coerente completo ---


def test_a7_successful_derive_leaves_complete_coherent_state(cognitive_sqlite_session_factory):
    source_id = _setup_source(cognitive_sqlite_session_factory)

    with UnitOfWork(cognitive_sqlite_session_factory) as uow:
        objs = ObjectRepository(uow.session)
        lin = LineageRepository(uow.session)
        trans = TransformationRepository(uow.session)
        mgr = ClidManager(objs, lin)
        vmgr = VersionManager(objs, mgr, trans)
        src = objs.get_by_id(source_id)
        target, edge, record = vmgr.derive(src, operation_type="summarize")
        uow.commit()
        target_id, record_id = target.id, record.id
        relation_type = edge.relation_type

    with UnitOfWork(cognitive_sqlite_session_factory) as uow:
        objs = ObjectRepository(uow.session)
        lin = LineageRepository(uow.session)
        trans = TransformationRepository(uow.session)

        reloaded_source = objs.get_by_id(source_id)
        reloaded_target = objs.get_by_id(target_id)
        assert reloaded_source.revision_status is None
        assert reloaded_target.revision_status is None
        assert reloaded_target.clid == reloaded_source.clid
        assert lin.edge_exists(source_id, target_id, relation_type)
        assert trans.get_by_id(record_id) is not None
