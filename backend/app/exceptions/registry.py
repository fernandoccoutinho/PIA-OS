"""
Registry de Exceções.

Responsável por: registrar handlers, evitar duplicações (registrar o
mesmo tipo de exceção duas vezes é um erro de programação, não um caso
válido — levanta `ValueError` cedo, em vez de deixar o segundo registro
silenciosamente sobrescrever o primeiro), e facilitar extensões futuras
(um módulo novo só precisa chamar `default_registry.register(...)`, sem
tocar em `main.py` ou em `handlers.py`).
"""

from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

Handler = Callable[[Request, Exception], Awaitable[JSONResponse]]


class ExceptionRegistry:
    """Coleção de pares (tipo de exceção -> handler), aplicada a uma
    instância do FastAPI de uma vez (`apply`)."""

    def __init__(self) -> None:
        self._handlers: dict[type[Exception], Handler] = {}

    def register(self, exc_type: type[Exception], handler: Handler) -> None:
        if exc_type in self._handlers:
            raise ValueError(
                f"Já existe um handler registrado para {exc_type.__name__} — "
                "evite registro duplicado (substitua a entrada existente "
                "explicitamente se essa for realmente a intenção)."
            )
        self._handlers[exc_type] = handler

    def apply(self, app: FastAPI) -> None:
        for exc_type, handler in self._handlers.items():
            app.add_exception_handler(exc_type, handler)

    def registered_types(self) -> tuple[type[Exception], ...]:
        return tuple(self._handlers.keys())


def _build_default_registry() -> ExceptionRegistry:
    from fastapi.exceptions import RequestValidationError
    from sqlalchemy.exc import SQLAlchemyError
    from starlette.exceptions import HTTPException as StarletteHTTPException

    from app.exceptions.base import PIAOSException
    from app.exceptions.handlers import (
        http_exception_handler,
        piaos_exception_handler,
        sqlalchemy_exception_handler,
        unhandled_exception_handler,
        validation_exception_handler,
    )

    registry = ExceptionRegistry()
    # Ordem de registro não importa para o FastAPI (ele escolhe pelo tipo
    # mais específico em tempo de exceção), mas a ordem aqui reflete a
    # hierarquia: mais específico (PIAOSException) primeiro, catch-all
    # (Exception) por último.
    registry.register(PIAOSException, piaos_exception_handler)
    registry.register(StarletteHTTPException, http_exception_handler)
    registry.register(RequestValidationError, validation_exception_handler)
    registry.register(SQLAlchemyError, sqlalchemy_exception_handler)
    registry.register(Exception, unhandled_exception_handler)
    return registry


default_registry = _build_default_registry()
