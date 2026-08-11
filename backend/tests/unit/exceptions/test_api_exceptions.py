from fastapi import FastAPI, status
from fastapi.testclient import TestClient

from app.core.exceptions import (
    APIException,
    BadRequestException,
    InternalServerException,
    NotFoundException,
    ValidationException,
)
from app.exceptions.base import PIAOSException
from app.middleware.exception_handler import register_exception_handlers


def test_exception_hierarchy():
    """A partir do Módulo 2.7, a hierarquia oficial é:

        PIAOSException
        ├── APIException (+ BadRequestException, NotFoundException, InternalServerException)
        └── ValidationException  (irmã de APIException, não subclasse — ver docs/ERRORS.md)

    O comportamento HTTP observável (status, mensagem, envelope JSON) é
    idêntico ao do Módulo 2.5 — apenas a relação de herança em Python
    mudou, por decisão explícita da especificação do Módulo 2.7.
    """
    assert issubclass(BadRequestException, APIException)
    assert issubclass(NotFoundException, APIException)
    assert issubclass(InternalServerException, APIException)
    assert issubclass(APIException, PIAOSException)
    assert issubclass(ValidationException, PIAOSException)
    assert not issubclass(ValidationException, APIException)


def test_default_status_codes():
    assert BadRequestException().status_code == status.HTTP_400_BAD_REQUEST
    assert NotFoundException().status_code == status.HTTP_404_NOT_FOUND
    assert ValidationException().status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert InternalServerException().status_code == status.HTTP_500_INTERNAL_SERVER_ERROR


def test_custom_message_overrides_default():
    exc = NotFoundException(message="recurso_x_nao_encontrado")
    assert exc.message == "recurso_x_nao_encontrado"


def test_detail_is_preserved():
    exc = BadRequestException(detail={"field": "email"})
    assert exc.detail == {"field": "email"}


def _build_test_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom-not-found")
    def _boom_not_found():
        raise NotFoundException(detail="id=42")

    @app.get("/boom-bad-request")
    def _boom_bad_request():
        raise BadRequestException(message="parametro_invalido")

    return app


client = TestClient(_build_test_app())


def test_api_exception_is_translated_to_standard_envelope():
    response = client.get("/boom-not-found")
    assert response.status_code == 404
    body = response.json()
    assert body["error"]["message"] == "not_found"
    assert body["error"]["detail"] == "id=42"
    assert body["error"]["status_code"] == 404
    assert body["error"]["path"] == "/boom-not-found"


def test_api_exception_custom_message_reaches_the_envelope():
    response = client.get("/boom-bad-request")
    assert response.status_code == 400
    assert response.json()["error"]["message"] == "parametro_invalido"
