import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config.settings import settings
from app.exceptions.handlers import register_exception_handlers


def _build_test_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    def _boom():
        raise RuntimeError("falha simulada")

    return app


client = TestClient(_build_test_app(), raise_server_exceptions=False)


def test_stack_trace_is_logged_when_debug_is_true(caplog, monkeypatch):
    monkeypatch.setattr(settings, "debug", True)
    with caplog.at_level(logging.ERROR, logger="app.exceptions"):
        client.get("/boom")
    record = next(r for r in caplog.records if hasattr(r, "error_code"))
    assert record.exc_info is not None


def test_stack_trace_is_not_logged_when_debug_is_false(caplog, monkeypatch):
    monkeypatch.setattr(settings, "debug", False)
    with caplog.at_level(logging.ERROR, logger="app.exceptions"):
        client.get("/boom")
    record = next(r for r in caplog.records if hasattr(r, "error_code"))
    assert record.exc_info is None


def test_response_body_omits_stack_trace_regardless_of_debug(monkeypatch):
    monkeypatch.setattr(settings, "debug", True)
    response = client.get("/boom")
    assert "Traceback" not in response.text
    assert "falha simulada" not in response.text
