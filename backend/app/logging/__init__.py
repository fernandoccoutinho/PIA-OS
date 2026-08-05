"""
Sistema de Logs e Observabilidade do PIA-OS (Módulo 2.6).

Uso recomendado pelos demais módulos:

    from app.logging import get_logger
    logger = get_logger(__name__)

Para transportar contexto (request_id, correlation_id, ...):

    from app.logging import logging_context

Para eventos padronizados:

    from app.logging import events
    events.log_event(logger, events.REQUEST_COMPLETED, status_code=200)

A montagem do logger raiz (`configure_logging`) é feita uma única vez no
startup — ver `app.core.logging.setup_logging`, não chame
`app.logging.config.configure_logging` diretamente fora dali.
"""

from app.logging.context import ContextSnapshot, LoggingContext, logging_context
from app.logging.logger import get_logger

__all__ = [
    "ContextSnapshot",
    "LoggingContext",
    "get_logger",
    "logging_context",
]
