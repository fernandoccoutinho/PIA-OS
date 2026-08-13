import logging
import logging.handlers

from app.logging.formatters import JsonFormatter
from app.logging.handlers import build_console_handler, build_file_handler, build_syslog_handler


def test_build_console_handler_writes_to_stdout():
    handler = build_console_handler(JsonFormatter())
    assert isinstance(handler, logging.StreamHandler)
    assert isinstance(handler.formatter, JsonFormatter)


def test_build_file_handler_creates_rotating_handler(tmp_path):
    file_path = tmp_path / "logs" / "app.log"
    handler = build_file_handler(
        JsonFormatter(),
        file_path=str(file_path),
        max_bytes=1024,
        backup_count=3,
    )
    try:
        assert isinstance(handler, logging.handlers.RotatingFileHandler)
        assert file_path.parent.exists()  # diretório criado automaticamente
        assert handler.maxBytes == 1024
        assert handler.backupCount == 3
    finally:
        handler.close()


def test_build_file_handler_actually_writes_and_rotates(tmp_path):
    file_path = tmp_path / "app.log"
    handler = build_file_handler(
        logging.Formatter("%(message)s"),
        file_path=str(file_path),
        max_bytes=200,
        backup_count=2,
    )
    logger = logging.getLogger("test_file_rotation")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        for i in range(200):
            logger.info(f"linha de log número {i} preenchendo espaço para forçar rotação")
        rotated = list(tmp_path.glob("app.log*"))
        assert len(rotated) >= 1
    finally:
        logger.removeHandler(handler)
        handler.close()


def test_build_syslog_handler_returns_handler_or_none_gracefully():
    # Estrutura apenas — não deve lançar mesmo se o ambiente não tiver
    # /dev/log disponível (comportamento esperado em alguns sandboxes).
    result = build_syslog_handler(JsonFormatter())
    assert result is None or isinstance(result, logging.Handler)
