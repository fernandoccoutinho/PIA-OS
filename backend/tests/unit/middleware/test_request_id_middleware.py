from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config.constants import REQUEST_ID_HEADER
from app.middleware.request_id import RequestIDMiddleware


def _build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)

    @app.get("/x")
    def _x():
        return {"ok": True}

    return app


client = TestClient(_build_app())


def test_generates_a_request_id_when_none_provided():
    response = client.get("/x")
    assert REQUEST_ID_HEADER in response.headers
    assert response.headers[REQUEST_ID_HEADER]  # não vazio


def test_preserves_an_incoming_request_id():
    response = client.get("/x", headers={REQUEST_ID_HEADER: "meu-id-customizado"})
    assert response.headers[REQUEST_ID_HEADER] == "meu-id-customizado"


def test_request_id_is_unique_per_request():
    first = client.get("/x").headers[REQUEST_ID_HEADER]
    second = client.get("/x").headers[REQUEST_ID_HEADER]
    assert first != second
