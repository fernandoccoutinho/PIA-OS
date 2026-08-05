from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config.constants import RESPONSE_TIME_HEADER
from app.middleware.timing import TimingMiddleware


def _build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(TimingMiddleware)

    @app.get("/x")
    def _x():
        return {"ok": True}

    return app


client = TestClient(_build_app())


def test_response_includes_timing_header():
    response = client.get("/x")
    assert RESPONSE_TIME_HEADER in response.headers


def test_timing_header_is_a_non_negative_number():
    response = client.get("/x")
    elapsed = float(response.headers[RESPONSE_TIME_HEADER])
    assert elapsed >= 0


def test_timing_header_has_two_decimal_places():
    response = client.get("/x")
    value = response.headers[RESPONSE_TIME_HEADER]
    assert len(value.split(".")[-1]) == 2
