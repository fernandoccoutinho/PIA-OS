"""Testes dos endpoints de saúde e raiz."""

from fastapi.testclient import TestClient

from pia_os import __version__


def test_health_ok(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "status": "ok",
        "service": "pia-os",
        "version": __version__,
    }


def test_root(client: TestClient) -> None:
    response = client.get("/")

    assert response.status_code == 200
    body = response.json()
    assert body["service"] == "PIA-OS"
    assert body["version"] == __version__
