import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config.settings import Settings
from app.exceptions.handlers import register_exception_handlers
from app.security.middleware import SecurityMiddleware
from app.security.rate_limit import InMemoryRateLimiter, RateLimitMiddleware


def _build_app(settings: Settings) -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)
    app.add_middleware(SecurityMiddleware, settings=settings)

    @app.get("/ping")
    def _ping():
        return {"pong": True}

    @app.post("/echo")
    def _echo():
        return {"ok": True}

    return app


def test_security_headers_are_applied_to_every_response():
    client = TestClient(_build_app(Settings()))
    response = client.get("/ping")
    assert response.status_code == 200
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"


def test_trusted_host_violation_returns_standard_error_envelope():
    settings = Settings(trusted_hosts="api.pia-os.com")
    client = TestClient(_build_app(settings), raise_server_exceptions=False)
    response = client.get("/ping", headers={"Host": "evil.com"})
    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "PIA-1009"


def test_untrusted_host_is_logged_as_security_violation(caplog):
    settings = Settings(trusted_hosts="api.pia-os.com")
    client = TestClient(_build_app(settings), raise_server_exceptions=False)
    with caplog.at_level(logging.WARNING, logger="app.security"):
        client.get("/ping", headers={"Host": "evil.com"})
    record = next(r for r in caplog.records if getattr(r, "event", None) == "security_violation")
    assert record.violation_type == "untrusted_host"
    assert record.ip is not None
    assert record.route == "/ping"
    assert record.method == "GET"


def test_wildcard_trusted_hosts_allows_any_host():
    client = TestClient(_build_app(Settings(trusted_hosts="*")))
    response = client.get("/ping", headers={"Host": "anything.example.com"})
    assert response.status_code == 200


def test_oversized_payload_is_rejected():
    settings = Settings(max_request_size_bytes=10)
    client = TestClient(_build_app(settings), raise_server_exceptions=False)
    response = client.post(
        "/echo",
        content=b"x" * 1000,
        headers={"Content-Type": "application/json", "Content-Length": "1000"},
    )
    assert response.status_code == 413
    assert response.json()["error"]["code"] == "PIA-1006"


def test_unsupported_content_type_is_rejected():
    settings = Settings(allowed_content_types="application/json")
    client = TestClient(_build_app(settings), raise_server_exceptions=False)
    response = client.post("/echo", content=b"<x/>", headers={"Content-Type": "text/xml"})
    assert response.status_code == 415
    assert response.json()["error"]["code"] == "PIA-1007"


def test_allowed_content_type_passes_through():
    settings = Settings(allowed_content_types="application/json")
    client = TestClient(_build_app(settings))
    response = client.post("/echo", json={"a": 1})
    assert response.status_code == 200


def test_rate_limit_middleware_blocks_after_limit():
    app = FastAPI()
    register_exception_handlers(app)
    limiter = InMemoryRateLimiter(max_requests=2, window_seconds=60)
    app.add_middleware(RateLimitMiddleware, limiter=limiter)

    @app.get("/x")
    def _x():
        return {"ok": True}

    client = TestClient(app, raise_server_exceptions=False)
    assert client.get("/x").status_code == 200
    assert client.get("/x").status_code == 200
    response = client.get("/x")
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "PIA-1008"


def test_rate_limit_disabled_by_default_in_real_app():
    from main import app as real_app

    assert Settings().rate_limit_enabled is False
    middleware_classes = [m.cls.__name__ for m in real_app.user_middleware]
    assert "RateLimitMiddleware" not in middleware_classes
