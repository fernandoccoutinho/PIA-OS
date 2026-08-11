"""
Mocks reutilizáveis — construtores de `Mock`/`AsyncMock` comuns à suíte.

Não substitui `unittest.mock` diretamente nos testes onde um mock simples
de uma linha já resolve — apenas centraliza os casos que se repetem
entre módulos (sessão async, engine com falha de conexão).
"""

from unittest.mock import AsyncMock, MagicMock


def make_async_session_mock() -> AsyncMock:
    """`AsyncMock` com a interface mínima de uma `AsyncSession` do
    SQLAlchemy (`commit`, `rollback`, `close`, `execute` — todos awaitable)."""
    return AsyncMock()


def make_failing_engine_mock(exception: Exception) -> MagicMock:
    """Engine cujo `.connect()` lança `exception` — para simular banco
    indisponível sem precisar de um PostgreSQL real (usado desde o
    Módulo 2.3 em `test_database_health.py`, formalizado aqui)."""
    mock_engine = MagicMock()
    mock_engine.connect.side_effect = exception
    return mock_engine


def make_session_factory_mock() -> MagicMock:
    """Factory de sessão (`sessionmaker`) mockada — `factory()` sempre
    retorna o mesmo objeto mock, como uma sessão real de fábrica faria
    por chamada (mas aqui, sempre a mesma instância, para inspeção)."""
    mock_factory = MagicMock()
    return mock_factory
