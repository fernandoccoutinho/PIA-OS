"""
Testes da própria infraestrutura de testes (factories, helpers, fixtures)
— garante que o que outros testes vão reutilizar funciona de verdade,
não só existe.
"""

import pytest

from app.exceptions import NotFoundException
from app.exceptions.handlers import piaos_exception_handler
from tests.factories.models import make_sample_model, make_sample_models
from tests.helpers.assertions import assert_error_envelope, assert_valid_component_status
from tests.helpers.mocks import make_async_session_mock, make_failing_engine_mock


def test_make_sample_model_generates_unique_names():
    a = make_sample_model()
    b = make_sample_model()
    assert a.name != b.name


def test_make_sample_model_accepts_overrides():
    entity = make_sample_model(name="específico")
    assert entity.name == "específico"


def test_make_sample_models_generates_the_requested_count():
    entities = make_sample_models(5)
    assert len(entities) == 5
    assert len({e.name for e in entities}) == 5  # todos únicos


async def test_make_async_session_mock_supports_awaited_calls():
    mock = make_async_session_mock()
    await mock.commit()
    await mock.rollback()
    mock.commit.assert_awaited_once()
    mock.rollback.assert_awaited_once()


def test_make_failing_engine_mock_raises_on_connect():
    mock_engine = make_failing_engine_mock(ConnectionError("simulado"))
    with pytest.raises(ConnectionError):
        mock_engine.connect()


async def test_assert_error_envelope_against_a_real_handler_response():
    import json

    from starlette.requests import Request

    scope = {"type": "http", "method": "GET", "path": "/x", "headers": [], "state": {}}
    request = Request(scope)
    response = await piaos_exception_handler(request, NotFoundException(detail="id=1"))

    body = json.loads(response.body)
    assert_error_envelope(body, status_code=404, code="PIA-1002")


def test_assert_valid_component_status_accepts_well_formed_component():
    assert_valid_component_status({"name": "database", "healthy": True, "detail": None})


def test_assert_valid_component_status_rejects_malformed_component():
    with pytest.raises(AssertionError):
        assert_valid_component_status({"name": "database"})  # falta 'healthy'


def test_test_settings_fixture(test_settings):
    assert test_settings.environment.value == "testing"
    assert test_settings.debug is True


def test_production_settings_fixture(production_settings):
    assert production_settings.environment.value == "production"
    assert production_settings.debug is False


def test_fake_user_payload_fixture(fake_user_payload):
    assert "id" in fake_user_payload
    assert "email" in fake_user_payload


def test_client_fixture_triggers_lifespan(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200


def test_client_no_lifespan_fixture_still_works(client_no_lifespan):
    response = client_no_lifespan.get("/api/v1/health")
    assert response.status_code == 200
