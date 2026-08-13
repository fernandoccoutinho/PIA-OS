"""
Testes de `LineageRepository` — §37-§38 do módulo E3.3 (LIN1-LIN10,
CY1 self-only).
"""

import uuid

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


@pytest.fixture
def objects(cognitive_session):
    return ObjectRepository(cognitive_session)


@pytest.fixture
def lineage(cognitive_session):
    return LineageRepository(cognitive_session)


# --- LIN1-LIN10 ---


def test_lin1_edge_can_be_created(objects, lineage, cognitive_session):
    a = objects.add(CognitiveObject())
    b = objects.add(CognitiveObject())
    cognitive_session.commit()

    edge = lineage.add_edge(
        parent_coid=a.id, child_coid=b.id, relation_type=LineageRelation.DERIVED_FROM
    )
    cognitive_session.commit()
    assert edge.id is not None


def test_lin2_parent_and_child_must_exist(lineage, objects, cognitive_session):
    existing = objects.add(CognitiveObject())
    cognitive_session.commit()

    with pytest.raises(LineageEndpointNotFoundError) as exc_info:
        lineage.add_edge(
            parent_coid=uuid.uuid4(), child_coid=existing.id, relation_type=LineageRelation.BRANCH
        )
    assert exc_info.value.code == "PIA-8008"
    cognitive_session.rollback()


def test_lin3_self_link_rejected(objects, lineage, cognitive_session):
    a = objects.add(CognitiveObject())
    cognitive_session.commit()

    with pytest.raises(LineageSelfLinkError) as exc_info:
        lineage.add_edge(
            parent_coid=a.id, child_coid=a.id, relation_type=LineageRelation.DERIVED_FROM
        )
    assert exc_info.value.code == "PIA-8006"


def test_lin3_self_link_rejected_before_any_write(objects, lineage, cognitive_session):
    """A rejeição acontece no domínio, antes de tentar persistir —
    nenhuma linha é adicionada à sessão."""
    a = objects.add(CognitiveObject())
    cognitive_session.commit()

    with pytest.raises(LineageSelfLinkError):
        lineage.add_edge(
            parent_coid=a.id, child_coid=a.id, relation_type=LineageRelation.DERIVED_FROM
        )

    assert len(lineage.list_children(a.id)) == 0


def test_lin4_duplicate_edge_is_rejected(objects, lineage, cognitive_session):
    a = objects.add(CognitiveObject())
    b = objects.add(CognitiveObject())
    cognitive_session.commit()

    lineage.add_edge(parent_coid=a.id, child_coid=b.id, relation_type=LineageRelation.DERIVED_FROM)
    cognitive_session.commit()

    with pytest.raises(LineageDuplicateEdgeError) as exc_info:
        lineage.add_edge(
            parent_coid=a.id, child_coid=b.id, relation_type=LineageRelation.DERIVED_FROM
        )
    assert exc_info.value.code == "PIA-8007"
    cognitive_session.rollback()


def test_lin5_direction_is_preserved(objects, lineage, cognitive_session):
    a = objects.add(CognitiveObject())
    b = objects.add(CognitiveObject())
    cognitive_session.commit()

    edge = lineage.add_edge(
        parent_coid=a.id, child_coid=b.id, relation_type=LineageRelation.DERIVED_FROM
    )
    cognitive_session.commit()

    assert edge.parent_coid == a.id
    assert edge.child_coid == b.id
    # a consulta "inversa" não retorna a mesma edge como se fosse b->a
    assert len(lineage.list_children(b.id)) == 0
    assert len(lineage.list_parents(a.id)) == 0


def test_lin6_list_children_works(objects, lineage, cognitive_session):
    a = objects.add(CognitiveObject())
    b = objects.add(CognitiveObject())
    c = objects.add(CognitiveObject())
    cognitive_session.commit()
    lineage.add_edge(parent_coid=a.id, child_coid=b.id, relation_type=LineageRelation.DERIVED_FROM)
    lineage.add_edge(parent_coid=a.id, child_coid=c.id, relation_type=LineageRelation.BRANCH)
    cognitive_session.commit()

    children = lineage.list_children(a.id)
    assert {e.child_coid for e in children} == {b.id, c.id}


def test_lin6_list_children_filters_by_relation_type(objects, lineage, cognitive_session):
    a = objects.add(CognitiveObject())
    b = objects.add(CognitiveObject())
    c = objects.add(CognitiveObject())
    cognitive_session.commit()
    lineage.add_edge(parent_coid=a.id, child_coid=b.id, relation_type=LineageRelation.DERIVED_FROM)
    lineage.add_edge(parent_coid=a.id, child_coid=c.id, relation_type=LineageRelation.BRANCH)
    cognitive_session.commit()

    only_derived = lineage.list_children(a.id, relation_type=LineageRelation.DERIVED_FROM)
    assert [e.child_coid for e in only_derived] == [b.id]


def test_lin7_list_parents_works(objects, lineage, cognitive_session):
    a = objects.add(CognitiveObject())
    b = objects.add(CognitiveObject())
    c = objects.add(CognitiveObject())
    cognitive_session.commit()
    lineage.add_edge(parent_coid=a.id, child_coid=c.id, relation_type=LineageRelation.DERIVED_FROM)
    lineage.add_edge(parent_coid=b.id, child_coid=c.id, relation_type=LineageRelation.MERGE)
    cognitive_session.commit()

    parents = lineage.list_parents(c.id)
    assert {e.parent_coid for e in parents} == {a.id, b.id}


def test_lin8_soft_deleted_objects_do_not_destroy_lineage(objects, lineage, cognitive_session):
    a = objects.add(CognitiveObject())
    b = objects.add(CognitiveObject())
    cognitive_session.commit()
    edge = lineage.add_edge(
        parent_coid=a.id, child_coid=b.id, relation_type=LineageRelation.DERIVED_FROM
    )
    cognitive_session.commit()

    objects.soft_delete(a)
    cognitive_session.commit()

    # a lineage continua auditável mesmo com o parent soft-deleted
    children = lineage.list_children(a.id)
    assert len(children) == 1
    assert children[0].id == edge.id


def test_lin9_ordering_is_deterministic(objects, lineage, cognitive_session):
    a = objects.add(CognitiveObject())
    children = [objects.add(CognitiveObject()) for _ in range(6)]
    cognitive_session.commit()
    for child in children:
        lineage.add_edge(
            parent_coid=a.id, child_coid=child.id, relation_type=LineageRelation.DERIVED_FROM
        )
    cognitive_session.commit()

    run_1 = [e.id for e in lineage.list_children(a.id)]
    run_2 = [e.id for e in lineage.list_children(a.id)]
    assert run_1 == run_2


def test_lin10_rollback_of_creation_works(objects, cognitive_sqlite_session_factory):
    from app.repositories.unit_of_work import UnitOfWork

    with UnitOfWork(cognitive_sqlite_session_factory) as uow:
        objs = ObjectRepository(uow.session)
        a = objs.add(CognitiveObject())
        b = objs.add(CognitiveObject())
        uow.commit()
        a_id, b_id = a.id, b.id

    with pytest.raises(ValueError), UnitOfWork(cognitive_sqlite_session_factory) as uow:
        lin = LineageRepository(uow.session)
        lin.add_edge(parent_coid=a_id, child_coid=b_id, relation_type=LineageRelation.DERIVED_FROM)
        raise ValueError("falha simulada após criar a edge, antes do commit")

    with UnitOfWork(cognitive_sqlite_session_factory) as uow:
        lin = LineageRepository(uow.session)
        assert len(lin.list_children(a_id)) == 0


def test_edge_exists_checks_the_exact_triple(objects, lineage, cognitive_session):
    a = objects.add(CognitiveObject())
    b = objects.add(CognitiveObject())
    cognitive_session.commit()
    lineage.add_edge(parent_coid=a.id, child_coid=b.id, relation_type=LineageRelation.DERIVED_FROM)
    cognitive_session.commit()

    assert lineage.edge_exists(a.id, b.id, LineageRelation.DERIVED_FROM) is True
    assert lineage.edge_exists(a.id, b.id, LineageRelation.BRANCH) is False
    assert lineage.edge_exists(b.id, a.id, LineageRelation.DERIVED_FROM) is False


def test_list_parents_filters_by_relation_type(objects, lineage, cognitive_session):
    a = objects.add(CognitiveObject())
    b = objects.add(CognitiveObject())
    c = objects.add(CognitiveObject())
    cognitive_session.commit()
    lineage.add_edge(parent_coid=a.id, child_coid=c.id, relation_type=LineageRelation.DERIVED_FROM)
    lineage.add_edge(parent_coid=b.id, child_coid=c.id, relation_type=LineageRelation.MERGE)
    cognitive_session.commit()

    only_merge = lineage.list_parents(c.id, relation_type=LineageRelation.MERGE)
    assert [e.parent_coid for e in only_merge] == [b.id]


# --- Classificação de violação de integridade — sinal estruturado ---


class _FakeDriverError:
    def __init__(self, *, sqlstate: str | None = None, sqlite_errorname: str | None = None):
        if sqlstate is not None:
            self.sqlstate = sqlstate
        if sqlite_errorname is not None:
            self.sqlite_errorname = sqlite_errorname


def _build_persistence_error(orig: object | None):
    from app.repositories.exceptions import PersistenceError

    cause = Exception()
    if orig is not None:
        cause.orig = orig  # type: ignore[attr-defined]
    try:
        raise PersistenceError("falha simulada") from cause
    except PersistenceError as exc:
        return exc


def test_classify_postgres_unique_violation():
    from app.cognitive.repositories.lineage_repository import (
        _classify_lineage_integrity_violation,
    )

    exc = _build_persistence_error(_FakeDriverError(sqlstate="23505"))
    assert _classify_lineage_integrity_violation(exc) == "unique"


def test_classify_postgres_foreign_key_violation():
    from app.cognitive.repositories.lineage_repository import (
        _classify_lineage_integrity_violation,
    )

    exc = _build_persistence_error(_FakeDriverError(sqlstate="23503"))
    assert _classify_lineage_integrity_violation(exc) == "foreign_key"


def test_classify_postgres_unrelated_sqlstate_returns_none():
    from app.cognitive.repositories.lineage_repository import (
        _classify_lineage_integrity_violation,
    )

    exc = _build_persistence_error(_FakeDriverError(sqlstate="23502"))  # not_null
    assert _classify_lineage_integrity_violation(exc) is None


def test_classify_orig_none_returns_none():
    from app.cognitive.repositories.lineage_repository import (
        _classify_lineage_integrity_violation,
    )

    exc = _build_persistence_error(None)
    assert _classify_lineage_integrity_violation(exc) is None


def test_add_edge_reraises_unrelated_persistence_error(monkeypatch, lineage):
    """Um `PersistenceError` cuja causa não é unicidade nem FK
    continua propagando sem reinterpretação (mesmo princípio da
    correção E3.2.1 para COID)."""
    from app.repositories.base_repository import BaseRepository
    from app.repositories.exceptions import PersistenceError

    fake_cause = Exception()
    fake_cause.orig = _FakeDriverError(sqlstate="23502")  # not_null, não coberto

    def _raise_unrelated(self, entity):
        raise PersistenceError("falha simulada não relacionada") from fake_cause

    monkeypatch.setattr(BaseRepository, "add", _raise_unrelated)

    with pytest.raises(PersistenceError) as exc_info:
        lineage.add_edge(
            parent_coid=uuid.uuid4(), child_coid=uuid.uuid4(), relation_type=LineageRelation.BRANCH
        )
    from app.cognitive.errors.exceptions import (
        LineageDuplicateEdgeError,
        LineageEndpointNotFoundError,
    )

    assert not isinstance(exc_info.value, LineageDuplicateEdgeError)
    assert not isinstance(exc_info.value, LineageEndpointNotFoundError)


# --- CY1: proteção de ciclo (CYCLE_PROTECTION = SELF_ONLY) ---


def test_cy1_self_link_is_the_only_cycle_protection_enforced(objects, lineage, cognitive_session):
    """`CYCLE_PROTECTION = SELF_ONLY` (documentado e justificado em
    `E3_3_LIB03_CLID_LINEAGE.md`) — A->A é rejeitado; um ciclo indireto
    A->B->A NÃO é bloqueado nesta fase (débito explícito, candidato a
    E3.10 Integrity Manager)."""
    a = objects.add(CognitiveObject())
    b = objects.add(CognitiveObject())
    cognitive_session.commit()

    lineage.add_edge(parent_coid=a.id, child_coid=b.id, relation_type=LineageRelation.DERIVED_FROM)
    cognitive_session.commit()

    # ciclo indireto B->A NÃO é bloqueado — confirma a classificação
    # SELF_ONLY documentada (não é um "deveria falhar e não falhou",
    # é o comportamento deliberadamente definido nesta fase)
    reverse_edge = lineage.add_edge(
        parent_coid=b.id, child_coid=a.id, relation_type=LineageRelation.DERIVED_FROM
    )
    cognitive_session.commit()
    assert reverse_edge.id is not None
