"""
Engine única de banco de dados — sync e async.

Fonte única de verdade para a Engine SQLAlchemy. Nenhuma outra camada
deve chamar `create_engine`/`create_async_engine` — importar `engine`
(sync) ou `async_engine` (async, preparada para uso futuro) daqui.

Reconexão automática: `pool_pre_ping=True` testa cada conexão do pool
antes de entregá-la, descartando e reabrindo conexões mortas (ex.: após
um restart do PostgreSQL ou timeout de rede) de forma transparente.
"""

import time
from typing import Any

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.config.settings import settings
from app.utils.logger import get_logger

logger = get_logger("app.database")


def _async_database_url(sync_url: str) -> str:
    """Deriva a URL do driver assíncrono (asyncpg) a partir da URL sync (psycopg).

    Mantém `DATABASE_URL` como única fonte de configuração (Módulo 2.2) —
    não introduz uma segunda variável de ambiente só para o driver async.
    """
    if "+psycopg" in sync_url:
        return sync_url.replace("+psycopg", "+asyncpg")
    if "+asyncpg" in sync_url:
        return sync_url
    return sync_url.replace("postgresql://", "postgresql+asyncpg://", 1)


def _build_sync_engine() -> Engine:
    return create_engine(
        settings.database_url,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_recycle=settings.database_pool_recycle,
        pool_timeout=settings.database_pool_timeout,
        echo=settings.database_echo,
        pool_pre_ping=True,
    )


def _build_async_engine() -> AsyncEngine:
    return create_async_engine(
        _async_database_url(settings.database_url),
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_recycle=settings.database_pool_recycle,
        pool_timeout=settings.database_pool_timeout,
        echo=settings.database_echo,
        pool_pre_ping=True,
    )


engine: Engine = _build_sync_engine()
async_engine: AsyncEngine = _build_async_engine()


# ---------------------------------------------------------------------------
# Logging do ciclo de vida da conexão e tempo de execução de consultas.
# Nunca logamos parâmetros de query (podem conter dados sensíveis) — apenas
# metadados: evento, tempo decorrido, se aplicável.
# ---------------------------------------------------------------------------


@event.listens_for(engine, "connect")
def _on_connect(dbapi_connection: Any, connection_record: Any) -> None:
    logger.info("database_connection_opened")


@event.listens_for(engine, "checkin")
def _on_checkin(dbapi_connection: Any, connection_record: Any) -> None:
    logger.debug("database_connection_returned_to_pool")


@event.listens_for(engine, "close")
def _on_close(dbapi_connection: Any, connection_record: Any) -> None:
    logger.info("database_connection_closed")


@event.listens_for(engine, "before_cursor_execute")
def _before_cursor_execute(
    conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, executemany: bool
) -> None:
    context._pia_os_query_start_time = time.perf_counter()


@event.listens_for(engine, "after_cursor_execute")
def _after_cursor_execute(
    conn: Any, cursor: Any, statement: str, parameters: Any, context: Any, executemany: bool
) -> None:
    start = getattr(context, "_pia_os_query_start_time", None)
    if start is None:
        return
    elapsed_ms = (time.perf_counter() - start) * 1000
    # Loga apenas duração e tipo de statement (primeira palavra), nunca os
    # parâmetros nem o SQL completo, que podem conter dados sensíveis.
    statement_kind = statement.strip().split(maxsplit=1)[0].upper() if statement.strip() else ""
    if elapsed_ms > 500:
        logger.warning(
            "database_slow_query",
            extra={"statement_kind": statement_kind, "duration_ms": round(elapsed_ms, 2)},
        )
    else:
        logger.debug(
            "database_query_executed",
            extra={"statement_kind": statement_kind, "duration_ms": round(elapsed_ms, 2)},
        )


@event.listens_for(engine, "handle_error")
def _on_handle_error(exception_context: Any) -> None:
    logger.error(
        "database_error",
        extra={"error_type": type(exception_context.original_exception).__name__},
    )
