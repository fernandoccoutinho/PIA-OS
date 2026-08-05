from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.database.session import async_session_scope, get_async_db, get_db


def test_get_db_rolls_back_on_exception():
    class _Boom(Exception):
        pass

    with patch("app.database.session.SessionLocal") as mock_factory:
        mock_session = mock_factory.return_value
        gen = get_db()
        next(gen)  # entra no generator, obtém a sessão
        with pytest.raises(_Boom):
            gen.throw(_Boom("falha simulada"))
        mock_session.rollback.assert_called_once()
        mock_session.close.assert_called_once()


def test_get_db_closes_session_on_normal_completion():
    with patch("app.database.session.SessionLocal") as mock_factory:
        mock_session = mock_factory.return_value
        gen = get_db()
        next(gen)
        gen.close()
        mock_session.close.assert_called_once()


async def test_get_async_db_yields_session_and_closes_normally():
    mock_session = AsyncMock()
    mock_factory = MagicMock()
    mock_factory.return_value.__aenter__.return_value = mock_session
    mock_factory.return_value.__aexit__.return_value = None

    with patch("app.database.session.AsyncSessionLocal", mock_factory):
        agen = get_async_db()
        db = await agen.__anext__()
        assert db is mock_session
        with pytest.raises(StopAsyncIteration):
            await agen.__anext__()


async def test_get_async_db_rolls_back_on_exception():
    class _Boom(Exception):
        pass

    mock_session = AsyncMock()
    mock_factory = MagicMock()
    mock_factory.return_value.__aenter__.return_value = mock_session
    mock_factory.return_value.__aexit__.return_value = None

    with patch("app.database.session.AsyncSessionLocal", mock_factory):
        agen = get_async_db()
        await agen.__anext__()
        with pytest.raises(_Boom):
            await agen.athrow(_Boom("falha simulada"))
        mock_session.rollback.assert_awaited_once()


async def test_async_session_scope_commits_on_success():
    mock_session = AsyncMock()
    with patch("app.database.session.AsyncSessionLocal", return_value=mock_session):
        async with async_session_scope() as db:
            assert db is mock_session
        mock_session.commit.assert_awaited_once()
        mock_session.rollback.assert_not_awaited()
        mock_session.close.assert_awaited_once()


async def test_async_session_scope_rolls_back_on_exception():
    class _Boom(Exception):
        pass

    mock_session = AsyncMock()
    with patch("app.database.session.AsyncSessionLocal", return_value=mock_session):
        with pytest.raises(_Boom):
            async with async_session_scope():
                raise _Boom("falha simulada")
        mock_session.rollback.assert_awaited_once()
        mock_session.commit.assert_not_awaited()
        mock_session.close.assert_awaited_once()
