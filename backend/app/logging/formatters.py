"""
Formatadores de log — JSON estruturado (produção) e texto legível (dev).

Ambos incluem os campos padronizados de log estruturado quando presentes
no record (timestamp, nível, request_id, correlation_id, session_id,
módulo, função, mensagem, duração, ambiente) — campos ausentes não
aparecem no JSON (não como `null`) nem no texto.
"""

import json
import logging
from datetime import UTC, datetime
from typing import Any

# Chaves padrão de um LogRecord "vazio" — usadas para descobrir quais
# atributos extras (`extra=` do chamador, ou injetados por ContextFilter)
# um record específico carrega, sem hardcodar a lista.
_BASE_RECORD_KEYS = frozenset(logging.LogRecord("", 0, "", 0, "", (), None).__dict__)

# Nomes dos campos estruturados oficiais (Módulo 2.6) — usados para
# ordenar/priorizar a saída em texto; no JSON, todos os campos extras
# são incluídos independentemente de estarem nesta lista.
_STRUCTURED_FIELD_ORDER = (
    "request_id",
    "correlation_id",
    "session_id",
    "trace_id",
    "duration_ms",
    "environment",
)


class JsonFormatter(logging.Formatter):
    """Formata cada registro de log como uma linha JSON."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "module": record.module,
            "function": record.funcName,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        extra_keys = set(record.__dict__) - _BASE_RECORD_KEYS
        for key in extra_keys:
            payload[key] = getattr(record, key)

        return json.dumps(payload, ensure_ascii=False, default=str)


class TextFormatter(logging.Formatter):
    """Formata cada registro como uma linha legível para desenvolvimento
    local — inclui os campos estruturados conhecidos entre colchetes,
    na ordem definida em `_STRUCTURED_FIELD_ORDER`, seguidos de quaisquer
    outros campos extras."""

    def format(self, record: logging.LogRecord) -> str:
        base = (
            f"{self.formatTime(record, '%Y-%m-%d %H:%M:%S')} | "
            f"{record.levelname:<8} | {record.name} | {record.getMessage()}"
        )

        extra_keys = set(record.__dict__) - _BASE_RECORD_KEYS
        ordered_parts = []
        for key in _STRUCTURED_FIELD_ORDER:
            if key in extra_keys:
                ordered_parts.append(f"{key}={getattr(record, key)}")
                extra_keys.discard(key)
        for key in sorted(extra_keys):
            ordered_parts.append(f"{key}={getattr(record, key)}")

        if ordered_parts:
            base += " [" + " ".join(ordered_parts) + "]"

        if record.exc_info:
            base += "\n" + self.formatException(record.exc_info)

        return base
