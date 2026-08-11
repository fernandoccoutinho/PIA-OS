"""
Transações aninhadas (savepoints).

Não introduz uma API nova — `Session.begin_nested()` já é suporte nativo
do SQLAlchemy 2.x, disponível hoje através de `uow.session` sem qualquer
mudança de código. Estes testes documentam e comprovam que o padrão
funciona sobre a infraestrutura atual (UnitOfWork + BaseRepository), para
que um módulo futuro que precise de savepoints não precise descobrir isso
por tentativa e erro.
"""

from app.repositories.base_repository import BaseRepository
from app.repositories.unit_of_work import UnitOfWork
from tests.fixtures.database import SampleModel


def test_savepoint_rollback_does_not_affect_outer_transaction(sqlite_session_factory):
    with UnitOfWork(sqlite_session_factory) as uow:
        uow.repository(SampleModel).add(SampleModel(name="outer"))

        savepoint = uow.session.begin_nested()
        uow.repository(SampleModel).add(SampleModel(name="inner-will-rollback"))
        savepoint.rollback()

        uow.commit()

    with UnitOfWork(sqlite_session_factory) as uow:
        names = {e.name for e in uow.repository(SampleModel).list()}
    assert "outer" in names
    assert "inner-will-rollback" not in names


def test_savepoint_commit_persists_alongside_outer_transaction(sqlite_session_factory):
    with UnitOfWork(sqlite_session_factory) as uow:
        uow.repository(SampleModel).add(SampleModel(name="outer-2"))

        savepoint = uow.session.begin_nested()
        uow.repository(SampleModel).add(SampleModel(name="inner-will-persist"))
        savepoint.commit()

        uow.commit()

    with UnitOfWork(sqlite_session_factory) as uow:
        names = {e.name for e in uow.repository(SampleModel).list()}
    assert {"outer-2", "inner-will-persist"}.issubset(names)


def test_savepoint_via_context_manager(sqlite_session_factory):
    """`begin_nested()` também funciona como context manager — rollback
    automático se uma exceção ocorrer dentro do bloco aninhado."""
    with UnitOfWork(sqlite_session_factory) as uow:
        repo = BaseRepository(uow.session, SampleModel)
        repo.add(SampleModel(name="outer-3"))

        try:
            with uow.session.begin_nested():
                repo.add(SampleModel(name="inner-context-manager"))
                raise RuntimeError("falha simulada dentro do savepoint")
        except RuntimeError:
            pass  # savepoint já reverteu sozinho ao sair do `with` com exceção

        uow.commit()

    with UnitOfWork(sqlite_session_factory) as uow:
        names = {e.name for e in uow.repository(SampleModel).list()}
    assert "outer-3" in names
    assert "inner-context-manager" not in names
