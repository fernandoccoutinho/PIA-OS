import pytest

from app.repositories.base_repository import BaseRepository
from app.repositories.unit_of_work import UnitOfWork
from tests.fixtures.database import SampleModel


def test_commit_persists_changes(sqlite_session_factory):
    with UnitOfWork(sqlite_session_factory) as uow:
        repo = BaseRepository(uow.session, SampleModel)
        repo.create(SampleModel(name="committed"))
        uow.commit()

    with UnitOfWork(sqlite_session_factory) as uow:
        repo = BaseRepository(uow.session, SampleModel)
        names = {e.name for e in repo.list()}
    assert "committed" in names


def test_missing_explicit_commit_rolls_back(sqlite_session_factory):
    with UnitOfWork(sqlite_session_factory) as uow:
        repo = BaseRepository(uow.session, SampleModel)
        repo.create(SampleModel(name="never-committed"))
        # commit() deliberadamente não chamado

    with UnitOfWork(sqlite_session_factory) as uow:
        repo = BaseRepository(uow.session, SampleModel)
        names = {e.name for e in repo.list()}
    assert "never-committed" not in names


def test_exception_inside_block_rolls_back(sqlite_session_factory):
    with pytest.raises(ValueError), UnitOfWork(sqlite_session_factory) as uow:
        repo = BaseRepository(uow.session, SampleModel)
        repo.create(SampleModel(name="doomed"))
        raise ValueError("falha simulada")

    with UnitOfWork(sqlite_session_factory) as uow:
        repo = BaseRepository(uow.session, SampleModel)
        names = {e.name for e in repo.list()}
    assert "doomed" not in names


def test_explicit_rollback(sqlite_session_factory):
    with UnitOfWork(sqlite_session_factory) as uow:
        repo = BaseRepository(uow.session, SampleModel)
        repo.create(SampleModel(name="explicitly-rolled-back"))
        uow.rollback()

    with UnitOfWork(sqlite_session_factory) as uow:
        repo = BaseRepository(uow.session, SampleModel)
        names = {e.name for e in repo.list()}
    assert "explicitly-rolled-back" not in names


def test_session_accessor_raises_outside_context_manager():
    uow = UnitOfWork()
    with pytest.raises(RuntimeError):
        _ = uow.session


def test_multiple_repositories_share_one_transaction(sqlite_session_factory):
    """Duas operações via repositórios diferentes commitam/revertem juntas."""
    with UnitOfWork(sqlite_session_factory) as uow:
        repo = BaseRepository(uow.session, SampleModel)
        repo.create(SampleModel(name="first"))
        repo.create(SampleModel(name="second"))
        uow.commit()

    with UnitOfWork(sqlite_session_factory) as uow:
        repo = BaseRepository(uow.session, SampleModel)
        names = {e.name for e in repo.list()}
    assert {"first", "second"}.issubset(names)
