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


#: Campos de `RequestValidationError.errors()` seguros para publicar.
#:
#: ```text
#: RAW_OUTPUT_IN_RESPONSE = FORBIDDEN
#: RAW_OUTPUT_IN_APPLICATION_LOG = FORBIDDEN
#: ```
#:
#: `input` e `ctx` carregam o VALOR que o cliente enviou. Num endpoint que
#: recebe retorno de IA, esse valor é justamente o conteúdo bruto que o
#: programa promete não persistir nem registrar — e um payload malformado
#: o devolveria no corpo do 422 e o gravaria no log, derrotando a
#: promessa por um detalhe de formatação do framework.
#:
#: Lista de PERMITIDOS, não de proibidos: um campo novo do Pydantic entra
#: como oculto por omissão, e não como vazamento por omissão.
CAMPOS_DE_VALIDACAO_PUBLICAVEIS: frozenset[str] = frozenset({"type", "loc", "msg"})


def _validacao_sem_conteudo(erros: object) -> list[dict[str, object]]:
    """Recorta cada erro aos campos seguros, preservando o diagnóstico.

    `loc` continua dizendo QUAL campo falhou e `msg` POR QUE; some apenas
    o valor enviado. O cliente conserta a requisição sem que o servidor
    ecoe o que recebeu.
    """
    saneados: list[dict[str, object]] = []
    if not isinstance(erros, list):  # pragma: no cover - contrato do FastAPI
        return saneados
    for erro in erros:
        if not isinstance(erro, dict):  # pragma: no cover - contrato do FastAPI
            continue
        seguro: dict[str, object] = {}
        for chave in ("type", "loc", "msg"):
            if chave in erro:
                valor = erro[chave]
                seguro[chave] = list(valor) if isinstance(valor, tuple) else valor
        saneados.append(seguro)
    return saneados


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """Validação automática de request (Pydantic, via FastAPI), **sem eco**.

    O log usa uma mensagem derivada dos campos seguros em vez de
    `str(exc)`: a representação padrão da exceção contém a lista completa
    de erros, `input` incluído. `exc_info` também fica de fora — o
    traceback do Pydantic carrega o valor recebido.

    ```text
    DIAGNOSTIC_LOCATION != DIAGNOSTIC_VALUE
    ```
    """
    error_code = PIA_2001_VALIDATION_ERROR
    seguros = _validacao_sem_conteudo(exc.errors())
    _log_validacao(request, seguros, error_code=error_code)
    return _build_response(
        error_code=error_code,
        message=error_code.default_message,
        detail=seguros,
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        request=request,
    )


def _log_validacao(
    request: Request, seguros: list[dict[str, object]], *, error_code: ErrorCode
) -> None:
    """Registra a falha de validação sem `str(exc)` e sem `exc_info`."""
    request_id = getattr(request.state, "request_id", None)
    context = LoggingContext.get()
    localizacoes: list[str] = []
    for erro in seguros:
        local = erro.get("loc")
        if isinstance(local, list):
            localizacoes.append(".".join(str(parte) for parte in local))
    events.log_event(
        logger,
        events.INTERNAL_ERROR,
        level=logging.ERROR,
        exc_info=None,
        exception_type="RequestValidationError",
        exception_message=(
            f"{len(seguros)} erro(s) de validação em: {', '.join(localizacoes) or '(desconhecido)'}"
        ),
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
