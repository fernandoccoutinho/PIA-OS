"""
Filtros de logging.

Um `logging.Filter` no sentido da stdlib — anexado a um handler, roda
para cada `LogRecord` antes da formatação. `ContextFilter` é o mecanismo
que faz `request_id`/`correlation_id`/etc. aparecerem automaticamente em
todo log da aplicação, sem qualquer chamador precisar passar `extra=`.
"""

import logging
import time

from app.logging.context import LoggingContext


class ContextFilter(logging.Filter):
    """Injeta os campos de `LoggingContext` atual no record, se setados.

    Nunca sobrescreve um campo que o próprio chamador já tenha passado
    via `extra=` (ex.: um log que quer um `request_id` diferente do
    contexto ambiente, caso raro mas não impedido).
    """

    def filter(self, record: logging.LogRecord) -> bool:
        for key, value in LoggingContext.get().as_dict().items():
            if not hasattr(record, key):
                setattr(record, key, value)
        return True


class SensitiveDataFilter(logging.Filter):
    """Remove/mascara campos sensíveis de `record.__dict__` antes da
    formatação — nunca de `record.msg` (mensagens livres não são
    inspecionadas por conteúdo, apenas os campos estruturados/`extra=`
    conhecidos por nome, que é onde dados sensíveis tipicamente entram
    de forma previsível: `password`, `secret_key`, `token`, etc.).
    """

    DEFAULT_SENSITIVE_KEYS = frozenset(
        {
            "password",
            "secret_key",
            "token",
            "authorization",
            "api_key",
            "access_token",
            "refresh_token",
            "database_url",  # pode conter usuário:senha embutidos
        }
    )
    REDACTED_VALUE = "***REDACTED***"

    def __init__(self, sensitive_keys: frozenset[str] | None = None) -> None:
        super().__init__()
        self._sensitive_keys = sensitive_keys or self.DEFAULT_SENSITIVE_KEYS

    def filter(self, record: logging.LogRecord) -> bool:
        for key in self._sensitive_keys:
            if hasattr(record, key):
                setattr(record, key, self.REDACTED_VALUE)
        return True


class DuplicateFilter(logging.Filter):
    """Suprime mensagens idênticas repetidas dentro de uma janela de
    tempo curta (evita inundar o log com o mesmo erro repetido em loop).

    Compara `(logger_name, level, message)` — não é uma deduplicação
    semântica, apenas textual, e é intencionalmente simples (sem
    dependências externas, sem persistência entre processos).
    """

    def __init__(self, window_seconds: float = 1.0) -> None:
        super().__init__()
        self._window_seconds = window_seconds
        self._last_seen: dict[tuple[str, int, str], float] = {}

    def filter(self, record: logging.LogRecord) -> bool:
        key = (record.name, record.levelno, record.getMessage())
        now = time.monotonic()
        last = self._last_seen.get(key)
        self._last_seen[key] = now
        return last is None or (now - last) >= self._window_seconds


class MinLevelFilter(logging.Filter):
    """Filtro explícito de nível mínimo — complementar a `logger.setLevel()`
    da stdlib (que já faz isso), usado quando um handler específico
    precisa de um piso diferente do logger/root (ex.: um handler de
    arquivo que só quer WARNING+ mesmo com o logger em DEBUG)."""

    def __init__(self, min_level: int) -> None:
        super().__init__()
        self._min_level = min_level

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno >= self._min_level
