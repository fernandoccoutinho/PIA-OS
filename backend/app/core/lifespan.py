"""
Ciclo de vida da aplicação (startup / shutdown).

Nenhuma regra de negócio é executada aqui — apenas inicialização
de infraestrutura (logging, validação de configuração, verificação
de conectividade com o banco).
"""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config.config import ConfigurationError, validate_environment
from app.config.settings import settings
from app.core.logging import setup_logging
from app.database.session import check_database_connection
from app.logging import events, get_logger

logger = get_logger("app.lifespan")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    setup_logging(settings)
    events.log_event(
        logger,
        events.APPLICATION_STARTED,
        app_name=settings.app_name,
        environment=settings.environment,
    )

    try:
        validate_environment(settings)
    except ConfigurationError as exc:
        logger.error("startup_aborted_invalid_configuration", extra={"detail": str(exc)})
        raise

    db_ok = check_database_connection()
    logger.info("database_connection_check", extra={"connected": db_ok})

    logger.info("startup_complete")

    yield

    events.log_event(logger, events.APPLICATION_STOPPED)
