"""
Biblioteca de eventos padronizados.

Nomes de evento fixos (em vez de mensagens livres) tornam os logs
pesquisáveis/agregáveis de forma consistente entre módulos — qualquer
consumidor futuro (dashboard, alerta) pode filtrar por `event=...` sem
depender do texto exato de uma mensagem.
"""

import logging
from typing import Any

# --- Ciclo de vida da aplicação ---
APPLICATION_STARTED = "application_started"
APPLICATION_STOPPED = "application_stopped"
CONFIGURATION_LOADED = "configuration_loaded"

# --- Requisições HTTP ---
REQUEST_RECEIVED = "request_received"
REQUEST_COMPLETED = "request_completed"

# --- Erros ---
INTERNAL_ERROR = "internal_error"
UNHANDLED_EXCEPTION = "unhandled_exception"

# --- Infraestrutura ---
DATABASE_UNAVAILABLE = "database_unavailable"
DATABASE_RECONNECTED = "database_reconnected"

# --- Segurança ---
SECURITY_VIOLATION = "security_violation"


def log_event(
    logger: logging.Logger,
    event: str,
    *,
    level: int = logging.INFO,
    exc_info: BaseException | bool | None = None,
    **fields: Any,
) -> None:
    """Registra um evento padronizado — `event` vira parte do payload
    estruturado (campo `event`), não apenas o texto da mensagem, para
    permanecer pesquisável mesmo se a mensagem textual mudar.

        log_event(logger, REQUEST_COMPLETED, status_code=200, duration_ms=12.3)

    `exc_info` é repassado como parâmetro nativo do `logging` (nunca
    dentro de `extra=`) — colocá-lo em `extra` faria o próprio `logging`
    lançar `KeyError` (`exc_info` já é um atributo reservado de todo
    `LogRecord`).
    """
    logger.log(level, event, exc_info=exc_info, extra={"event": event, **fields})
