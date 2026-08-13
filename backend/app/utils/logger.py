"""
Compatibilidade com as Entregas 2.1-2.5.

A implementação canônica do Logger Central agora vive em `app.logging`
(Módulo 2.6) — `get_logger` aqui é um reexport direto, não uma segunda
fábrica. `JsonFormatter`/`configure_logging` permanecem definidos por
segurança de compatibilidade (nenhum código os chama mais — a montagem
oficial do sistema de logging passou a ser
`app.core.logging.setup_logging()`), mas seguem funcionais caso algo
externo dependa deles.
"""

import logging
import sys
from datetime import UTC, datetime
from typing import Any

from app.logging.logger import get_logger  # noqa: F401 — reexport, não duplicação

__all__ = ["JsonFormatter", "configure_logging", "get_logger"]


class JsonFormatter(logging.Formatter):
    """Formata cada registro de log como uma linha JSON.

    Mantido por compatibilidade — a versão canônica e mais completa é
    `app.logging.formatters.JsonFormatter` (inclui `module`/`function`).
    """

    def format(self, record: logging.LogRecord) -> str:
        import json

        payload: dict[str, Any] = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        base_record = logging.LogRecord("", 0, "", 0, "", (), None)
        extra_keys = set(record.__dict__) - set(base_record.__dict__)
        for key in extra_keys:
            payload[key] = getattr(record, key)

        return json.dumps(payload, ensure_ascii=False)


def configure_logging(level: str = "INFO", json_format: bool = True) -> None:
    """Configura o logger raiz — assinatura antiga, mantida por
    compatibilidade. Não é mais chamada pelo bootstrap da aplicação
    (ver `app.core.logging.setup_logging`, que usa
    `app.logging.config.configure_logging(settings)` — mais completa:
    handlers múltiplos, filtros de contexto e dados sensíveis).
    """
    root = logging.getLogger()
    root.setLevel(level)
    root.handlers.clear()

    handler = logging.StreamHandler(sys.stdout)
    if json_format:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)-8s | %(name)s | %(message)s")
        )
    root.addHandler(handler)
