from unittest.mock import patch

from app.database.health import DatabaseHealth, check_database_connection, check_database_health
from app.database.session import session_scope


def test_check_database_health_returns_dataclass():
    result = check_database_health()
    assert isinstance(result, DatabaseHealth)
    assert result.status in {"healthy", "unavailable"}


def test_check_database_health_unavailable_when_connection_fails():
    with patch("app.database.health.engine") as mock_engine:
        mock_engine.connect.side_effect = ConnectionError("simulated failure")
        result = check_database_health()
    assert result.available is False
    assert result.status == "unavailable"
    assert result.response_time_ms is None


def test_check_database_connection_boolean_compat():
    # Compatibilidade com Entregas 2.1/2.2 — retorna bool, não o dataclass.
    assert isinstance(check_database_connection(), bool)


def test_session_scope_rolls_back_on_exception():
    class _Boom(Exception):
        pass

    with patch("app.database.session.SessionLocal") as mock_factory:
        mock_session = mock_factory.return_value
        try:
            with session_scope():
                raise _Boom("falha simulada")
        except _Boom:
            pass
        mock_session.rollback.assert_called_once()
        mock_session.commit.assert_not_called()
        mock_session.close.assert_called_once()


def test_session_scope_commits_on_success():
    with patch("app.database.session.SessionLocal") as mock_factory:
        mock_session = mock_factory.return_value
        with session_scope():
            pass
        mock_session.commit.assert_called_once()
        mock_session.rollback.assert_not_called()
        mock_session.close.assert_called_once()
