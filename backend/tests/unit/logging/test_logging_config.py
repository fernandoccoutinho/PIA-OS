import logging

from app.config.settings import Settings
from app.logging.config import configure_logging
from app.logging.filters import ContextFilter, SensitiveDataFilter
from app.logging.formatters import JsonFormatter, TextFormatter


def teardown_function() -> None:
    # Evita que a configuração de um teste vaze para os seguintes.
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.WARNING)


def test_configure_logging_sets_root_level():
    settings = Settings(log_level="DEBUG", log_destination="console")
    configure_logging(settings)
    assert logging.getLogger().level == logging.DEBUG


def test_configure_logging_json_format_uses_json_formatter():
    settings = Settings(log_format="json", log_destination="console")
    configure_logging(settings)
    handler = logging.getLogger().handlers[0]
    assert isinstance(handler.formatter, JsonFormatter)


def test_configure_logging_text_format_uses_text_formatter():
    settings = Settings(log_format="text", log_destination="console")
    configure_logging(settings)
    handler = logging.getLogger().handlers[0]
    assert isinstance(handler.formatter, TextFormatter)


def test_configure_logging_attaches_context_and_sensitive_filters():
    settings = Settings(log_destination="console")
    configure_logging(settings)
    handler = logging.getLogger().handlers[0]
    filter_types = {type(f) for f in handler.filters}
    assert ContextFilter in filter_types
    assert SensitiveDataFilter in filter_types


def test_configure_logging_with_file_destination_adds_file_handler(tmp_path):
    import logging.handlers

    log_file = tmp_path / "app.log"
    settings = Settings(log_destination="console,file", log_file_path=str(log_file))
    configure_logging(settings)
    handler_types = {type(h) for h in logging.getLogger().handlers}
    assert logging.handlers.RotatingFileHandler in handler_types


def test_configure_logging_file_destination_without_path_is_skipped():
    import logging.handlers

    settings = Settings(log_destination="file", log_file_path=None)
    configure_logging(settings)
    handler_types = {type(h) for h in logging.getLogger().handlers}
    # Sem file_path, "file" é ignorado — mas nunca fica sem handler algum.
    assert logging.handlers.RotatingFileHandler not in handler_types
    assert len(logging.getLogger().handlers) >= 1


def test_configure_logging_is_idempotent_and_clears_previous_handlers():
    settings = Settings(log_destination="console")
    configure_logging(settings)
    configure_logging(settings)
    assert len(logging.getLogger().handlers) == 1
