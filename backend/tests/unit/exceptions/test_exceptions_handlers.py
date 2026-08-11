import logging

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel
from sqlalchemy.exc import SQLAlchemyError

from app.exceptions import BadRequestException, NotFoundException
from app.exceptions.handlers import register_exception_handlers


class _Body(BaseModel):
    email: str


def _build_test_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom-not-found")
    def _boom_not_found():
        raise NotFoundException(detail="id=42")

    @app.get("/boom-bad-request")
    def _boom_bad_request():
        raise BadRequestException(message="parametro_invalido")

    @app.post("/needs-body")
    def _needs_body(body: _Body):
        return {"ok": True}

    @app.get("/boom-sqlalchemy")
    def _boom_sqlalchemy():
        raise SQLAlchemyError("conexão perdida com o banco")

    @app.get("/boom-generic")
    def _boom_generic():
        raise RuntimeError("algo inesperado")

    return app


client = TestClient(_build_test_app(), raise_server_exceptions=False)


def test_piaos_exception_envelope_has_all_new_fields():
    response = client.get("/boom-not-found")
    assert response.status_code == 404
    body = response.json()
    assert body["success"] is False
    error = body["error"]
    assert error["code"] == "PIA-1002"
    assert error["category"] == "api"
    assert error["severity"] == "warning"
    assert "timestamp" in error
    assert error["details"] == {"value": "id=42"}
    # compatibilidade com o Módulo 2.5
    assert error["message"] == "not_found"
    assert error["detail"] == "id=42"
    assert error["status_code"] == 404
    assert error["path"] == "/boom-not-found"


def test_bad_request_custom_message():
    response = client.get("/boom-bad-request")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "PIA-1001"
    assert response.json()["error"]["message"] == "parametro_invalido"


def test_request_validation_error_uses_validation_error_code():
    response = client.post("/needs-body", json={})
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "PIA-2001"
    assert error["category"] == "validation"
    assert isinstance(error["detail"], list)  # lista de erros do Pydantic


def test_sqlalchemy_error_never_leaks_driver_message():
    response = client.get("/boom-sqlalchemy")
    assert response.status_code == 500
    error = response.json()["error"]
    assert error["code"] == "PIA-3001"
    assert error["category"] == "database"
    assert "conexão perdida" not in error["message"]
    assert "conexão perdida" not in str(error["detail"])


def test_unhandled_exception_returns_generic_internal_error():
    response = client.get("/boom-generic")
    assert response.status_code == 500
    error = response.json()["error"]
    assert error["code"] == "PIA-0002"
    assert error["message"] == "internal_server_error"
    assert "RuntimeError" not in error["message"]


def test_every_error_response_logs_the_error_code(caplog):
    with caplog.at_level(logging.ERROR, logger="app.exceptions"):
        client.get("/boom-not-found")
    record = next(r for r in caplog.records if hasattr(r, "error_code"))
    assert record.error_code == "PIA-1002"
    assert record.category == "api"
    assert record.severity == "warning"


def test_stack_trace_never_appears_in_the_http_response_body():
    """Independente do ambiente (dev/prod), a resposta HTTP nunca inclui
    stack trace — isso só acontece no log, e só quando settings.debug."""
    response = client.get("/boom-generic")
    body_text = response.text
    assert "Traceback" not in body_text
    assert "RuntimeError" not in body_text
