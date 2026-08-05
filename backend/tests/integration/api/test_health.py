from fastapi.testclient import TestClient

from app.config.settings import settings
from main import app

client = TestClient(app)


def test_health_returns_ok():
    response = client.get(f"{settings.api_prefix}/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_version_returns_expected_fields():
    response = client.get(f"{settings.api_prefix}/version")
    assert response.status_code == 200
    body = response.json()
    assert body["app_name"] == settings.app_name
    assert body["version"] == settings.app_version
    assert body["environment"] == settings.environment
    assert body["api_version"] == "v1"
    assert body["pia_os_version"]
    assert "database_version" in body  # None se o banco estiver inacessível


def test_status_returns_database_flag():
    response = client.get(f"{settings.api_prefix}/status")
    assert response.status_code == 200
    body = response.json()
    assert "database_connected" in body
    assert body["status"] in {"ok", "degraded"}


def test_status_returns_detailed_fields():
    response = client.get(f"{settings.api_prefix}/status")
    body = response.json()
    assert body["uptime_seconds"] >= 0
    assert body["api_version"] == "v1"
    assert body["modules_loaded"] > 0
    assert isinstance(body["components"], list)
    component_names = {c["name"] for c in body["components"]}
    assert {"application", "database", "orm", "config"}.issubset(component_names)


def test_metrics_returns_uptime():
    response = client.get(f"{settings.api_prefix}/metrics")
    assert response.status_code == 200
    body = response.json()
    assert body["uptime_seconds"] >= 0


def test_response_has_request_id_header():
    response = client.get(f"{settings.api_prefix}/health")
    assert "X-Request-ID" in response.headers


def test_response_has_timing_header():
    response = client.get(f"{settings.api_prefix}/health")
    assert "X-Response-Time-Ms" in response.headers


def test_unknown_route_returns_standard_error_envelope():
    response = client.get("/rota-inexistente")
    assert response.status_code == 404
    body = response.json()
    assert "error" in body
    assert body["error"]["status_code"] == 404
