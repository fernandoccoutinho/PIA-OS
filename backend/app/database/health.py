"""
Health check dedicado do banco de dados.

Separado do health check genérico da aplicação (`app/routers/health.py`)
de propósito: a disponibilidade do banco é uma preocupação de
*readiness*, não de *liveness* — ver nota em `docs/DATABASE.md` sobre por
que este check é exposto em `/api/v1/status`, não em `/api/v1/health`.
"""

import time
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session as OrmSession

from app.database.engine import engine
from app.utils.logger import get_logger

logger = get_logger("app.database")


@dataclass(frozen=True)
class DatabaseHealth:
    available: bool
    response_time_ms: float | None
    status: str  # "healthy" | "unavailable"


def check_database_health() -> DatabaseHealth:
    """Executa um `SELECT 1` e mede o tempo de resposta do banco.

    Nunca lança exceção — falhas de conexão resultam em `available=False`,
    permitindo que o chamador (endpoint de readiness) responda com um
    status HTTP apropriado em vez de derrubar a requisição.
    """
    start = time.perf_counter()
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
        elapsed_ms = (time.perf_counter() - start) * 1000
        return DatabaseHealth(
            available=True, response_time_ms=round(elapsed_ms, 2), status="healthy"
        )
    except Exception as exc:
        logger.error("database_health_check_failed", extra={"error_type": type(exc).__name__})
        return DatabaseHealth(available=False, response_time_ms=None, status="unavailable")


def check_database_connection() -> bool:
    """Compatibilidade com as Entregas 2.1/2.2 — verificação booleana simples."""
    return check_database_health().available


def get_database_version() -> str | None:
    """Retorna a string de versão do servidor PostgreSQL (`SELECT version()`).

    None se o banco estiver inacessível — nunca lança exceção, mesma
    política de `check_database_health` (usado por `/version`, que não
    deve derrubar a requisição por o banco estar fora do ar).
    """
    try:
        with engine.connect() as connection:
            return connection.execute(text("SELECT version()")).scalar()
    except Exception as exc:
        logger.error("database_version_check_failed", extra={"error_type": type(exc).__name__})
        return None


def check_orm_health() -> bool:
    """Verifica que uma `Session` do ORM consegue abrir e executar uma
    consulta — não apenas que a conexão bruta (`engine.connect()`) funciona.

    Usa `sqlalchemy.orm.Session` diretamente (não `SessionLocal` de
    `app.database.session`) para evitar um import circular: `session.py`
    já importa deste módulo (`check_database_connection`).
    """
    try:
        with OrmSession(engine) as session:
            session.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.error("orm_health_check_failed", extra={"error_type": type(exc).__name__})
        return False
