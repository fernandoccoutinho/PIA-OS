import pytest

from app.repositories.base_repository import BaseRepository, Page
from app.repositories.unit_of_work import UnitOfWork
from tests.fixtures.database import SampleModel


def test_count_without_filters_returns_total(sqlite_session):
    repo = BaseRepository(sqlite_session, SampleModel)
    repo.add(SampleModel(name="a"))
    repo.add(SampleModel(name="b"))
    sqlite_session.commit()
    assert repo.count() == 2


def test_count_with_filter(sqlite_session):
    repo = BaseRepository(sqlite_session, SampleModel)
    repo.add(SampleModel(name="alpha"))
    repo.add(SampleModel(name="alpha"))
    repo.add(SampleModel(name="beta"))
    sqlite_session.commit()
    assert repo.count(name="alpha") == 2
    assert repo.count(name="beta") == 1
    assert repo.count(name="nao-existe") == 0


def test_exists_by_true_and_false(sqlite_session):
    repo = BaseRepository(sqlite_session, SampleModel)
    repo.add(SampleModel(name="unique-name"))
    sqlite_session.commit()
    assert repo.exists_by(name="unique-name") is True
    assert repo.exists_by(name="nao-existe") is False


def test_filters_reject_unknown_field(sqlite_session):
    repo = BaseRepository(sqlite_session, SampleModel)
    with pytest.raises(ValueError, match="não possui o campo"):
        repo.count(campo_inexistente="x")


def test_paginate_returns_correct_page_and_total(sqlite_session):
    repo = BaseRepository(sqlite_session, SampleModel)
    for i in range(25):
        repo.add(SampleModel(name=f"item-{i:02d}"))
    sqlite_session.commit()

    page1 = repo.paginate(page=1, page_size=10)
    assert isinstance(page1, Page)
    assert len(page1.items) == 10
    assert page1.total == 25
    assert page1.total_pages == 3
    assert page1.has_next is True

    page3 = repo.paginate(page=3, page_size=10)
    assert len(page3.items) == 5
    assert page3.has_next is False


def test_paginate_with_filter(sqlite_session):
    repo = BaseRepository(sqlite_session, SampleModel)
    repo.add(SampleModel(name="match"))
    repo.add(SampleModel(name="match"))
    repo.add(SampleModel(name="other"))
    sqlite_session.commit()

    page = repo.paginate(page=1, page_size=10, name="match")
    assert page.total == 2
    assert len(page.items) == 2


def test_paginate_rejects_invalid_page_or_page_size(sqlite_session):
    repo = BaseRepository(sqlite_session, SampleModel)
    with pytest.raises(ValueError):
        repo.paginate(page=0)
    with pytest.raises(ValueError):
        repo.paginate(page_size=0)


def test_unit_of_work_repository_shortcut_shares_session(sqlite_session_factory):
    with UnitOfWork(sqlite_session_factory) as uow:
        repo = uow.repository(SampleModel)
        assert isinstance(repo, BaseRepository)
        assert repo._session is uow.session


def test_unit_of_work_repository_multiple_models_same_transaction(sqlite_session_factory):
    """Duas chamadas a uow.repository() compartilham a mesma sessão —
    commit único persiste ambas, rollback reverte ambas (rollback em cascata)."""
    with UnitOfWork(sqlite_session_factory) as uow:
        uow.repository(SampleModel).add(SampleModel(name="cascade-a"))
        uow.repository(SampleModel).add(SampleModel(name="cascade-b"))
        uow.commit()

    with UnitOfWork(sqlite_session_factory) as uow:
        names = {e.name for e in uow.repository(SampleModel).list()}
    assert {"cascade-a", "cascade-b"}.issubset(names)


def test_cascading_rollback_when_second_operation_fails(sqlite_session_factory):
    """Se a segunda operação falhar antes do commit, a primeira (ainda não
    commitada) também é revertida — não fica um registro órfão."""
    with pytest.raises(ValueError), UnitOfWork(sqlite_session_factory) as uow:
        uow.repository(SampleModel).add(SampleModel(name="will-be-rolled-back"))
        raise ValueError("falha simulada antes do commit")

    with UnitOfWork(sqlite_session_factory) as uow:
        names = {e.name for e in uow.repository(SampleModel).list()}
    assert "will-be-rolled-back" not in names
