import json
import logging

from app.config.settings import Settings
from app.core.logging import setup_logging


def teardown_function() -> None:
    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(logging.WARNING)


def test_setup_logging_configures_the_root_logger():
    settings = Settings(log_level="DEBUG", log_destination="console")
    setup_logging(settings)
    assert logging.getLogger().level == logging.DEBUG
    assert len(logging.getLogger().handlers) >= 1


def test_setup_logging_emits_configuration_loaded_event(capsys):
    """`setup_logging` reconstrói os handlers do zero (via
    `configure_logging`), o que substitui qualquer handler de captura de
    teste (ex.: o do `caplog`) já anexado ao logger raiz antes da
    chamada. Por isso a asserção aqui é sobre a saída real (stdout),
    não sobre `caplog.records` — é o que de fato chega ao handler
    configurado."""
    settings = Settings(log_destination="console", log_format="json")
    setup_logging(settings)

    captured = capsys.readouterr()
    lines = [line for line in captured.out.strip().split("\n") if line.strip()]
    payloads = [json.loads(line) for line in lines]
    assert any(p.get("event") == "configuration_loaded" for p in payloads)


def test_setup_logging_uses_default_settings_when_not_provided():
    # Não deve lançar — usa `settings` do módulo central por padrão.
    setup_logging()
