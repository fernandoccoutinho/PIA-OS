"""
Handlers globais de exceção — Sistema Global de Tratamento de Erros.

Fluxo: Erro -> Exceção específica -> Handler Global -> Logger -> Resposta
padronizada. Nenhuma exceção deve escapar diretamente para o usuário —
todo handler aqui produz um `ErrorResponse` (`app/schemas/error.py`) e
loga o evento via o Logger Central (Módulo 2.6) antes de responder.

Evolução do Módulo 2.5 (`app.middleware.exception_handler`) — mesmas
rotas de exceção cobertas (`PIAOSException`/`APIException`,
`StarletteHTTPException`, `RequestValidationError`, `Exception` genérica)
mais o handler novo para `SQLAlchemyError`.
"""

import logging

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config.settings import settings
from app.core.error_codes import (
    PIA_0002_INTERNAL_ERROR,
    PIA_2001_VALIDATION_ERROR,
    PIA_3001_DATABASE_ERROR,
    ErrorCode,
    error_code_for_http_status,
)
from app.exceptions.base import PIAOSException
from app.logging import events
from app.logging.context import LoggingContext
from app.logging.logger import get_logger
from app.schemas.error import ErrorDetail, ErrorResponse

logger = get_logger("app.exceptions")


def _details_dict(detail: object) -> dict[str, object]:
    """Normaliza `detail` (qualquer forma) para o campo `details` (dict)
    do envelope novo — sem descartar `detail` original, que continua
    presente por compatibilidade com o Módulo 2.5."""
    if detail is None:
        return {}
    if isinstance(detail, dict):
        return detail
    return {"value": detail}


def _build_response(
    *,
    error_code: ErrorCode,
    message: str,
    detail: object,
    status_code: int,
    request: Request,
) -> JSONResponse:
    request_id = getattr(request.state, "request_id", None)
    context = LoggingContext.get()
    error_detail = ErrorDetail(
        message=message,
        detail=detail,
        status_code=status_code,
        request_id=request_id,
        path=request.url.path,
        code=error_code.code,
        category=error_code.category.value,
        severity=error_code.severity.value,
        correlation_id=context.correlation_id,
        trace_id=context.trace_id,
        details=_details_dict(detail),
    )
    return JSONResponse(
        status_code=status_code,
        content=ErrorResponse(error=error_detail).model_dump(),
    )


def _log_exception(request: Request, exc: Exception, *, event: str, error_code: ErrorCode) -> None:
    request_id = getattr(request.state, "request_id", None)
    context = LoggingContext.get()
    events.log_event(
        logger,
        event,
        level=logging.ERROR,
        exc_info=exc if settings.debug else None,
        exception_type=type(exc).__name__,
        exception_message=str(exc),
        error_code=error_code.code,
        category=error_code.category.value,
        severity=error_code.severity.value,
        request_id=request_id,
        correlation_id=context.correlation_id,
        trace_id=context.trace_id,
        user_id=context.user_id,
        route=request.url.path,
        method=request.method,
    )


async def piaos_exception_handler(request: Request, exc: PIAOSException) -> JSONResponse:
    """Handler para toda a hierarquia `PIAOSException` — API, validação,
    configuração, banco, infraestrutura, externo, autenticação."""
    _log_exception(request, exc, event=events.INTERNAL_ERROR, error_code=exc.error_code)
    return _build_response(
        error_code=exc.error_code,
        message=exc.message,
        detail=exc.detail,
        status_code=exc.status_code,
        request=request,
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """HTTPException crua do Starlette/FastAPI (ex.: 404 de rota
    inexistente, 405 de método não suportado) — nunca uma
    `PIAOSException`, então o código de erro é inferido do status."""
    error_code = error_code_for_http_status(exc.status_code)
    _log_exception(request, exc, event=events.INTERNAL_ERROR, error_code=error_code)
    return _build_response(
        error_code=error_code,
        message=error_code.default_message,
        detail=exc.detail,
        status_code=exc.status_code,
        request=request,
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Validação automática de request (Pydantic, via FastAPI)."""
    error_code = PIA_2001_VALIDATION_ERROR
    _log_exception(request, exc, event=events.INTERNAL_ERROR, error_code=error_code)
    return _build_response(
        error_code=error_code,
        message=error_code.default_message,
        detail=exc.errors(),
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        request=request,
    )


async def sqlalchemy_exception_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    """`SQLAlchemyError` cru que escapou sem ter sido capturado/traduzido
    pela camada de repositório (ver `app/exceptions/database.py`) —
    nunca expõe a mensagem do driver/SQL ao cliente, apenas loga."""
    error_code = PIA_3001_DATABASE_ERROR
    _log_exception(request, exc, event=events.DATABASE_UNAVAILABLE, error_code=error_code)
    return _build_response(
        error_code=error_code,
        message=error_code.default_message,
        detail="Ocorreu um erro ao acessar o banco de dados.",
        status_code=error_code.http_status,
        request=request,
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Última linha de defesa — qualquer exceção não coberta pelos
    handlers acima. Nunca deixa uma exceção crua chegar ao cliente."""
    error_code = PIA_0002_INTERNAL_ERROR
    _log_exception(request, exc, event=events.UNHANDLED_EXCEPTION, error_code=error_code)
    return _build_response(
        error_code=error_code,
        message=error_code.default_message,
        detail="Ocorreu um erro interno inesperado.",
        status_code=error_code.http_status,
        request=request,
    )


def register_exception_handlers(app: FastAPI) -> None:
    """Registra todos os handlers globais — delega ao Registry
    (`app/exceptions/registry.py`), que evita duplicação de registro."""
    from app.exceptions.registry import default_registry

    default_registry.apply(app)
