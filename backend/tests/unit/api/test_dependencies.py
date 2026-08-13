import dataclasses

import pytest
from sqlalchemy.orm import Session
from starlette.requests import Request

from app.api.dependencies import (
    RequestContext,
    get_app_settings,
    get_current_user,
    get_db_session,
    get_request_context,
)
from app.config.settings import Settings, settings
from app.database.session import get_db


def test_get_db_session_is_the_same_dependency_as_database_session_get_db():
    # Reexport, não uma segunda implementação (ver docstring do módulo).
    assert get_db_session is get_db


def test_get_db_session_yields_a_sqlalchemy_session():
    gen = get_db_session()
    session = next(gen)
    try:
        assert isinstance(session, Session)
    finally:
        gen.close()


def test_get_app_settings_returns_the_singleton():
    assert get_app_settings() is settings
    assert isinstance(get_app_settings(), Settings)


def test_get_current_user_returns_none_placeholder():
    # Autenticação não implementada nesta etapa — comportamento esperado.
    assert get_current_user() is None


def test_get_request_context_extracts_request_id_path_and_method():
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/health",
        "headers": [],
        "state": {"request_id": "abc-123"},
    }
    request = Request(scope)
    request.state.request_id = "abc-123"

    context = get_request_context(request)
    assert isinstance(context, RequestContext)
    assert context.request_id == "abc-123"
    assert context.path == "/api/v1/health"
    assert context.method == "GET"


def test_get_request_context_defaults_optional_fields_to_none():
    scope = {"type": "http", "method": "GET", "path": "/", "headers": [], "state": {}}
    request = Request(scope)

    context = get_request_context(request)
    assert context.request_id is None
    assert context.correlation_id is None
    assert context.session_id is None
    assert context.trace_id is None
    assert context.user_id is None
    assert context.tenant is None
    assert context.provider is None


def test_request_context_is_immutable():
    context = RequestContext(request_id=None, path="/", method="GET")
    with pytest.raises(dataclasses.FrozenInstanceError):
        context.request_id = "changed"  # type: ignore[misc]
