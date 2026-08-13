"""
Testes de integração do ciclo de vida da aplicação.

A maioria dos testes de endpoint usa `TestClient(app)` sem `with`, o que
NÃO dispara os eventos de startup/shutdown do FastAPI — por isso
`app/core/lifespan.py` tinha cobertura baixa apesar de toda a suíte
passar. Estes testes usam `with TestClient(app) as client:` de propósito,
para exercitar o ciclo de vida real.

Usam `capsys` (não `caplog`): `setup_logging()` reconstrói os handlers do
logger raiz do zero (ver `docs/LOGGING.md`), o que remove o handler de
captura do `caplog` no meio do teste — mesma limitação já documentada no
Módulo 2.6. `capsys` captura a saída real (stdout), que é onde o handler
reconstruído efetivamente escreve.
"""

import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from app.config.config import ConfigurationError
from main import app


def _logged_events(capsys) -> list[dict]:
    captured = capsys.readouterr()
    lines = [line for line in captured.out.strip().split("\n") if line.strip()]
    return [json.loads(line) for line in lines]


def test_lifespan_startup_and_shutdown_complete_without_error(capsys):
    with TestClient(app) as client:
        response = client.get("/api/v1/health")
        assert response.status_code == 200

    payloads = _logged_events(capsys)
    events_logged = [p.get("event") for p in payloads]
    assert "application_started" in events_logged
    assert "application_stopped" in events_logged


def test_lifespan_logs_database_connection_check(capsys):
    with TestClient(app):
        pass
    payloads = _logged_events(capsys)
    messages = [p.get("message") for p in payloads]
    assert "database_connection_check" in messages
    assert "startup_complete" in messages


def test_lifespan_aborts_startup_on_invalid_configuration(capsys):
    with (
        patch("app.core.lifespan.validate_environment", side_effect=ConfigurationError("bad")),
        pytest.raises(ConfigurationError),
        TestClient(app),
    ):
        pass

    payloads = _logged_events(capsys)
    messages = [p.get("message") for p in payloads]
    assert "startup_aborted_invalid_configuration" in messages
