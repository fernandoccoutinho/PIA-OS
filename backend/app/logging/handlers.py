"""
Fábricas de handlers de log.

A escolha de quais handlers ativar vem inteiramente de
`settings.log_destination` (Módulo 2.2) — nenhum código de aplicação
decide isso hardcoded; ver `app/logging/config.py`.
"""

import logging
import logging.handlers
import sys
from pathlib import Path

# Logger stdlib puro (não o Logger Central) — usado apenas para avisar
# sobre falhas na própria montagem do sistema de logging, antes dele
# estar pronto. Usar o Logger Central aqui criaria uma dependência
# circular (handlers.py é montado pelo próprio Logger Central).
_bootstrap_logger = logging.getLogger("app.logging.handlers")


def build_console_handler(formatter: logging.Formatter) -> logging.StreamHandler:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    return handler


def build_file_handler(
    formatter: logging.Formatter,
    *,
    file_path: str,
    max_bytes: int,
    backup_count: int,
) -> logging.handlers.RotatingFileHandler:
    """Handler de arquivo com rotação por tamanho — rotação de fato
    implementada (não apenas estrutura), via `RotatingFileHandler` da
    stdlib, que já resolve isso sem dependências externas.
    """
    path = Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(
        filename=str(path),
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    handler.setFormatter(formatter)
    return handler


def build_syslog_handler(formatter: logging.Formatter) -> logging.Handler | None:
    """Handler de Syslog — estrutura apenas, conforme o escopo do Módulo 2.6.

    Tenta construir um `SysLogHandler` real (a stdlib já oferece um), mas
    isso é experimental nesta etapa: nenhum teste verifica entrega real a
    um daemon syslog (nenhum está disponível no ambiente de
    desenvolvimento/CI), e nenhuma configuração de host/porta do syslog
    foi adicionada ao Módulo 2.2 além do nome do destino. Retorna `None`
    (em vez de lançar) se a construção falhar, para nunca impedir a
    aplicação de iniciar por causa de um destino experimental.
    """
    try:
        handler = logging.handlers.SysLogHandler(address="/dev/log")
        handler.setFormatter(formatter)
        return handler
    except Exception:
        _bootstrap_logger.warning(
            "syslog_handler_unavailable — SysLogHandler não pôde ser construído neste ambiente."
        )
        return None
