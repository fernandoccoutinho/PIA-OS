import pytest
from fastapi import FastAPI

from app.exceptions.registry import ExceptionRegistry, default_registry


async def _dummy_handler(request, exc):  # pragma: no cover - nunca chamado
    raise NotImplementedError


def test_register_and_apply():
    registry = ExceptionRegistry()
    registry.register(ValueError, _dummy_handler)
    app = FastAPI()
    registry.apply(app)
    assert ValueError in app.exception_handlers


def test_register_duplicate_raises():
    registry = ExceptionRegistry()
    registry.register(ValueError, _dummy_handler)
    with pytest.raises(ValueError, match="Já existe um handler"):
        registry.register(ValueError, _dummy_handler)


def test_registered_types_reflects_registrations():
    registry = ExceptionRegistry()
    registry.register(ValueError, _dummy_handler)
    registry.register(TypeError, _dummy_handler)
    assert set(registry.registered_types()) == {ValueError, TypeError}


def test_default_registry_covers_all_expected_exception_types():
    from fastapi.exceptions import RequestValidationError
    from sqlalchemy.exc import SQLAlchemyError
    from starlette.exceptions import HTTPException as StarletteHTTPException

    from app.exceptions.base import PIAOSException

    types = default_registry.registered_types()
    assert PIAOSException in types
    assert StarletteHTTPException in types
    assert RequestValidationError in types
    assert SQLAlchemyError in types
    assert Exception in types


def test_default_registry_applies_without_error():
    app = FastAPI()
    default_registry.apply(app)
    assert len(app.exception_handlers) >= 5
