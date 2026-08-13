"""
Testes do shim de compatibilidade `app.utils.logger` (Módulos 2.1-2.5).

Não é mais o caminho recomendado (ver `app.logging`, Módulo 2.6), mas
precisa continuar funcional — testado aqui para não regredir em silêncio.
"""

import json
import logging

from app.logging.logger import get_logger as canonical_get_logger
from app.utils.logger import JsonFormatter, configure_logging, get_logger


def teardown_function() -> None:
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.WARNING)


def test_get_logger_is_a_reexport_of_the_canonical_factory():
    assert get_logger is canonical_get_logger


def test_json_formatter_produces_valid_json():
    record = logging.LogRecord("app.test", logging.INFO, __file__, 1, "hello", (), None)
    output = JsonFormatter().format(record)
    payload = json.loads(output)
    assert payload["message"] == "hello"
    assert payload["level"] == "INFO"
    assert payload["logger"] == "app.test"


def test_json_formatter_includes_extra_fields():
    record = logging.LogRecord("app.test", logging.INFO, __file__, 1, "hello", (), None)
    record.custom_field = "valor"
    payload = json.loads(JsonFormatter().format(record))
    assert payload["custom_field"] == "valor"


def test_json_formatter_includes_exception_info():
    try:
        raise ValueError("boom")
    except ValueError:
        import sys

        record = logging.LogRecord("app.test", logging.ERROR, __file__, 1, "erro", (), None)
        record.exc_info = sys.exc_info()
    payload = json.loads(JsonFormatter().format(record))
    assert "exception" in payload
    assert "boom" in payload["exception"]


def test_configure_logging_json_format_sets_json_formatter():
    configure_logging(level="INFO", json_format=True)
    handler = logging.getLogger().handlers[0]
    assert isinstance(handler.formatter, JsonFormatter)


def test_configure_logging_text_format_sets_text_formatter():
    configure_logging(level="DEBUG", json_format=False)
    root = logging.getLogger()
    assert root.level == logging.DEBUG
    handler = root.handlers[0]
    assert not isinstance(handler.formatter, JsonFormatter)


def test_configure_logging_clears_previous_handlers():
    configure_logging()
    configure_logging()
    assert len(logging.getLogger().handlers) == 1
