"""
Teste de integração de `LineageRepository`/`ClidManager` — exercita
`UnitOfWork` com a fábrica de sessão REAL da aplicação e a migração
real de `lineage_edges` (`4f56e1a4936c`) contra PostgreSQL.

Mesmo padrão gracioso de `test_object_repository_integration.py`: pula
se PostgreSQL/a migração não estiverem disponíveis, em vez de falhar.
"""

import pytest

from app.cognitive.errors.exceptions import (
    LineageDuplicateEdgeError,
    LineageEndpointNotFoundError,
    LineageSelfLinkError,
)
from app.cognitive.models.cognitive_object import CognitiveObject
from app.cognitive.models.enums import LineageRelation
from app.cognitive.repositories.lineage_repository import LineageRepository
from app.cognitive.repositories.object_repository import ObjectRepository
from app.cognitive.services.clid_manager import ClidManager
from app.database.health import check_database_health
from app.repositories.unit_of_work import UnitOfWork


def _postgres_available_with_lineage_edges_table() -> bool:
    health = check_database_health()
    if not health.available:
        return False
    from sqlalchemy import inspect

    from app.database.engine import engine

    tables = inspect(engine).get_table_names()
    return "cognitive_objects" in tables and "lineage_edges" in tables


pytestmark = pytest.mark.skipif(
    not _postgres_available_with_lineage_edges_table(),
    reason=(
        "PostgreSQL real indisponível ou migração 4f56e1a4936c "
        "(lineage_edges) não aplicada neste ambiente."
    ),
)


def test_inherit_and_lineage_round_trip_against_real_database():
    """Valida, contra PostgreSQL real: migration, FK, compartilhamento
    de CLID via `inherit()`, e limpeza."""
    with UnitOfWork() as uow:
        objs = ObjectRepository(uow.session)
        lin = LineageRepository(uow.session)
        mgr = ClidManager(objs, lin)

        parent = objs.add(CognitiveObject())
        child = objs.add(CognitiveObject())
        uow.commit()
        parent_id, child_id = parent.id, child.id

    try:
        with UnitOfWork() as uow:
            objs = ObjectRepository(uow.session)
            lin = LineageRepository(uow.session)
            mgr = ClidManager(objs, lin)

            p = objs.get_by_id(parent_id)
            c = objs.get_by_id(child_id)
            edge = mgr.inherit(p, c)
            uow.commit()
            edge_id = edge.id

        with UnitOfWork() as uow:
            objs = ObjectRepository(uow.session)
            lin = LineageRepository(uow.session)

            p = objs.get_by_id(parent_id)
            c = objs.get_by_id(child_id)
            assert p.clid is not None
            assert c.clid == p.clid  # CLID compartilhado

            children = lin.list_children(parent_id)
            assert len(children) == 1
            assert children[0].id == edge_id
    finally:
        with UnitOfWork() as uow:
            objs = ObjectRepository(uow.session)
            # lineage_edges primeiro (FK), depois os objetos
            uow.session.execute(
                __import__("sqlalchemy").text(
                    "DELETE FROM lineage_edges WHERE parent_coid = :p OR child_coid = :c"
                ),
                {"p": str(parent_id), "c": str(child_id)},
            )
            for coid in (parent_id, child_id):
                leftover = objs.get_by_id(coid, include_deleted=True)
                if leftover is not None:
                    objs.delete(leftover)
            uow.commit()


def test_self_link_rejected_against_real_database():
    with UnitOfWork() as uow:
        objs = ObjectRepository(uow.session)
        obj = objs.add(CognitiveObject())
        uow.commit()
        obj_id = obj.id

    try:
        with UnitOfWork() as uow:
            lin = LineageRepository(uow.session)
            with pytest.raises(LineageSelfLinkError) as exc_info:
                lin.add_edge(
                    parent_coid=obj_id,
                    child_coid=obj_id,
                    relation_type=LineageRelation.DERIVED_FROM,
                )
            assert exc_info.value.code == "PIA-8006"
            uow.rollback()
    finally:
        with UnitOfWork() as uow:
            objs = ObjectRepository(uow.session)
            leftover = objs.get_by_id(obj_id, include_deleted=True)
            if leftover is not None:
                objs.delete(leftover)
            uow.commit()


def test_duplicate_edge_rejected_against_real_database():
    with UnitOfWork() as uow:
        objs = ObjectRepository(uow.session)
        a = objs.add(CognitiveObject())
        b = objs.add(CognitiveObject())
        uow.commit()
        a_id, b_id = a.id, b.id

    try:
        with UnitOfWork() as uow:
            lin = LineageRepository(uow.session)
            lin.add_edge(
                parent_coid=a_id, child_coid=b_id, relation_type=LineageRelation.DERIVED_FROM
            )
            uow.commit()

        with UnitOfWork() as uow:
            lin = LineageRepository(uow.session)
            with pytest.raises(LineageDuplicateEdgeError) as exc_info:
                lin.add_edge(
                    parent_coid=a_id, child_coid=b_id, relation_type=LineageRelation.DERIVED_FROM
                )
            assert exc_info.value.code == "PIA-8007"
            uow.rollback()
    finally:
        with UnitOfWork() as uow:
            objs = ObjectRepository(uow.session)
            uow.session.execute(
                __import__("sqlalchemy").text(
                    "DELETE FROM lineage_edges WHERE parent_coid = :p AND child_coid = :c"
                ),
                {"p": str(a_id), "c": str(b_id)},
            )
            for coid in (a_id, b_id):
                leftover = objs.get_by_id(coid, include_deleted=True)
                if leftover is not None:
                    objs.delete(leftover)
            uow.commit()


def test_foreign_key_violation_rejected_against_real_database():
    import uuid

    with UnitOfWork() as uow:
        objs = ObjectRepository(uow.session)
        child = objs.add(CognitiveObject())
        uow.commit()
        child_id = child.id

    try:
        with UnitOfWork() as uow:
            lin = LineageRepository(uow.session)
            with pytest.raises(LineageEndpointNotFoundError) as exc_info:
                lin.add_edge(
                    parent_coid=uuid.uuid4(),
                    child_coid=child_id,
                    relation_type=LineageRelation.BRANCH,
                )
            assert exc_info.value.code == "PIA-8008"
            uow.rollback()
    finally:
        with UnitOfWork() as uow:
            objs = ObjectRepository(uow.session)
            leftover = objs.get_by_id(child_id, include_deleted=True)
            if leftover is not None:
                objs.delete(leftover)
            uow.commit()


def test_clid_immutability_against_real_database():
    import uuid

    with UnitOfWork() as uow:
        objs = ObjectRepository(uow.session)
        obj = objs.add(CognitiveObject())
        uow.commit()
        obj_id = obj.id

    try:
        with UnitOfWork() as uow:
            objs = ObjectRepository(uow.session)
            lin = LineageRepository(uow.session)
            mgr = ClidManager(objs, lin)
            o = objs.get_by_id(obj_id)
            mgr.assign(o, mgr.generate())
            uow.commit()

        from app.cognitive.errors.exceptions import CognitiveObjectClidAlreadySetError

        with UnitOfWork() as uow:
            objs = ObjectRepository(uow.session)
            o = objs.get_by_id(obj_id)
            with pytest.raises(CognitiveObjectClidAlreadySetError):
                o.clid = uuid.uuid4()
            uow.rollback()
    finally:
        with UnitOfWork() as uow:
            objs = ObjectRepository(uow.session)
            leftover = objs.get_by_id(obj_id, include_deleted=True)
            if leftover is not None:
                objs.delete(leftover)
            uow.commit()
