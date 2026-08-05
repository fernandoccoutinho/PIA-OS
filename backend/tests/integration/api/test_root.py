from datetime import datetime

from fastapi.testclient import TestClient

from app.config.settings import settings
from main import app

client = TestClient(app)


def test_root_returns_platform_info():
    response = client.get("/")
    assert response.status_code == 200
    body = response.json()
    assert body["name"] == settings.app_name
    assert body["version"] == settings.app_version
    assert body["environment"] == settings.environment
    assert "timestamp" in body
    assert body["docs_url"] == settings.docs_url
    assert body["redoc_url"] == settings.redoc_url


def test_root_is_not_under_the_api_prefix():
    response = client.get(f"{settings.api_prefix}/")
    assert response.status_code == 404


def test_root_timestamp_is_iso_format():
    response = client.get("/")
    timestamp = response.json()["timestamp"]
    datetime.fromisoformat(timestamp)  # não lança se for ISO 8601 válido
