"""
Montagem do sistema de logging a partir da configuração central (2.2).

`configure_logging()` é a única função que deve tocar no logger raiz
(`logging.getLogger()`, sem nome) — chamada uma única vez, no startup
(`app.core.logging.setup_logging`). Todo o resto do sistema só lê
(`get_logger`), nunca reconfigura.
"""

import logging

from app.config.settings import Settings
from app.logging.filters import ContextFilter, SensitiveDataFilter
from app.logging.formatters import JsonFormatter, TextFormatter
from app.logging.handlers import build_console_handler, build_file_handler, build_syslog_handler


def _build_formatter(log_format: str) -> logging.Formatter:
    return JsonFormatter() if log_format == "json" else TextFormatter()


def configure_logging(settings: Settings) -> None:
    """Configura o logger raiz: nível, handlers (console/file/syslog
    conforme `settings.log_destination`) e filtros (contexto + dados
    sensíveis, sempre ativos em todo handler)."""
    root = logging.getLogger()
    root.setLevel(settings.log_level)
    root.handlers.clear()

    formatter = _build_formatter(settings.log_format)
    destinations = settings.log_destinations

    handlers: list[logging.Handler] = []
    if "console" in destinations:
        handlers.append(build_console_handler(formatter))
    if "file" in destinations and settings.log_file_path:
        handlers.append(
            build_file_handler(
                formatter,
                file_path=settings.log_file_path,
                max_bytes=settings.log_rotation_max_bytes,
                backup_count=settings.log_rotation_backup_count,
            )
        )
    if "syslog" in destinations:
        syslog_handler = build_syslog_handler(formatter)
        if syslog_handler is not None:
            handlers.append(syslog_handler)

    if not handlers:
        # Nunca deixa a aplicação sem nenhum handler — cairia em
        # `logging.lastResort` (stderr, sem formatação estruturada).
        handlers.append(build_console_handler(formatter))

    context_filter = ContextFilter()
    sensitive_filter = SensitiveDataFilter()
    # Anexados a cada handler (não ao logger raiz): um filtro de Logger só
    # roda quando o log é emitido pelo próprio logger ao qual está
    # anexado — loggers filhos que apenas propagam (o caso normal, já que
    # o código sempre usa loggers nomeados) não disparam o filtro do
    # ancestral. Um filtro de Handler, por outro lado, roda sempre que
    # aquele handler processa um record, não importa a origem.
    for handler in handlers:
        handler.addFilter(context_filter)
        handler.addFilter(sensitive_filter)
        root.addHandler(handler)
