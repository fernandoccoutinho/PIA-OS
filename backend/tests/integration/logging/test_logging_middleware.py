import logging

from fastapi.testclient import TestClient

from app.logging.context import LoggingContext
from app.logging.filters import ContextFilter
from main import app

client = TestClient(app)


def _with_context_filter(caplog):
    """`caplog` usa seu próprio handler, separado dos handlers reais da
    aplicação — os filtros de contexto são anexados por handler (ver
    `app/logging/config.py`), então o handler do caplog só recebe
    request_id/correlation_id se o filtro for anexado a ele também."""
    caplog.handler.addFilter(ContextFilter())


def test_request_generates_received_and_completed_log_events(caplog):
    with caplog.at_level(logging.INFO, logger="app.request"):
        response = client.get("/api/v1/health")
    assert response.status_code == 200

    events_logged = [r.event for r in caplog.records if hasattr(r, "event")]
    assert "request_received" in events_logged
    assert "request_completed" in events_logged


def test_request_completed_event_carries_status_code_and_duration(caplog):
    with caplog.at_level(logging.INFO, logger="app.request"):
        client.get("/api/v1/health")

    completed = next(r for r in caplog.records if getattr(r, "event", None) == "request_completed")
    assert completed.status_code == 200
    assert completed.duration_ms >= 0
    assert completed.method == "GET"
    assert completed.path == "/api/v1/health"


def test_request_id_is_consistent_across_received_and_completed_events(caplog):
    _with_context_filter(caplog)
    with caplog.at_level(logging.INFO, logger="app.request"):
        response = client.get("/api/v1/health")

    header_request_id = response.headers["X-Request-ID"]
    request_records = [r for r in caplog.records if hasattr(r, "event")]
    for record in request_records:
        assert record.request_id == header_request_id


def test_correlation_id_header_is_propagated_to_log_context(caplog):
    _with_context_filter(caplog)
    with caplog.at_level(logging.INFO, logger="app.request"):
        client.get("/api/v1/health", headers={"X-Correlation-ID": "corr-xyz"})

    received = next(r for r in caplog.records if getattr(r, "event", None) == "request_received")
    assert received.correlation_id == "corr-xyz"


def test_context_is_cleared_after_request_completes():
    client.get("/api/v1/health")
    # O middleware usa `logging_context` como context manager — ao sair,
    # o contexto não deve mais vazar para chamadas fora do ciclo de request.
    assert LoggingContext.get().request_id is None
