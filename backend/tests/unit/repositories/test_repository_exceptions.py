import pytest

from app.repositories.base_repository import BaseRepository
from app.repositories.exceptions import (
    EntityNotFoundError,
    PersistenceError,
    RepositoryError,
    TransactionError,
)
from app.repositories.unit_of_work import UnitOfWork
from tests.fixtures.database import SampleModel


def test_exception_hierarchy():
    assert issubclass(EntityNotFoundError, RepositoryError)
    assert issubclass(PersistenceError, RepositoryError)
    assert issubclass(TransactionError, RepositoryError)


def test_entity_not_found_error_message_includes_model_and_id():
    error = EntityNotFoundError("SampleModel", 42)
    assert "SampleModel" in str(error)
    assert "42" in str(error)


def test_get_by_id_or_raise_raises_entity_not_found(sqlite_session):
    repo = BaseRepository(sqlite_session, SampleModel)
    with pytest.raises(EntityNotFoundError):
        repo.get_by_id_or_raise(9999)


def test_get_by_id_or_raise_returns_entity_when_found(sqlite_session):
    repo = BaseRepository(sqlite_session, SampleModel)
    created = repo.add(SampleModel(name="found"))
    sqlite_session.commit()

    fetched = repo.get_by_id_or_raise(created.id)
    assert fetched.name == "found"


def test_add_wraps_integrity_violation_in_persistence_error(sqlite_session_factory):
    """NOT NULL violado no flush deve virar PersistenceError, não a exceção
    crua do driver."""
    session = sqlite_session_factory()
    try:
        repo = BaseRepository(session, SampleModel)
        with pytest.raises(PersistenceError):
            repo.add(SampleModel(name=None))  # type: ignore[arg-type]
    finally:
        session.close()


def test_unit_of_work_wraps_commit_failure_in_transaction_error(sqlite_session_factory):
    """Simula uma falha no commit em si (não no flush) via mock, para isolar
    especificamente o comportamento de `UnitOfWork.commit()` — uma violação
    de constraint já é capturada antes disso, em `BaseRepository.add()`."""
    from unittest.mock import patch

    from sqlalchemy.exc import SQLAlchemyError

    with UnitOfWork(sqlite_session_factory) as uow:
        repo = BaseRepository(uow.session, SampleModel)
        repo.add(SampleModel(name="valid"))
        with (
            patch.object(uow.session, "commit", side_effect=SQLAlchemyError("boom")),
            pytest.raises(TransactionError),
        ):
            uow.commit()
