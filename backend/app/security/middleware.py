"""
Security Middleware.

Responsável por: validar hosts confiáveis, validar a requisição (tamanho,
Content-Type), aplicar cabeçalhos de segurança à resposta, e integrar
toda violação com o Logger Central (Módulo 2.6).

Violações são levantadas como exceções da hierarquia `PIAOSException`
(Módulo 2.7) — nunca uma resposta manual — para que o mesmo pipeline de
tratamento de erros e a mesma resposta padronizada cubram também erros
de segurança.
"""

from collections.abc import Awaitable, Callable
from typing import Any

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.config.settings import Settings
from app.config.settings import settings as default_settings
from app.exceptions.api import (
    PayloadTooLargeException,
    UnsupportedMediaTypeException,
    UntrustedHostException,
)
from app.exceptions.base import PIAOSException
from app.exceptions.handlers import piaos_exception_handler
from app.logging import events
from app.logging.logger import get_logger
from app.security.headers import build_security_headers
from app.security.request_validation import validate_request
from app.security.trusted_hosts import is_trusted_host

logger = get_logger("app.security")

# Mapa código de erro -> classe de exceção correspondente, para traduzir
# o resultado de `validate_request` (que retorna dados, não levanta) em
# uma exceção da hierarquia oficial.
_VIOLATION_EXCEPTIONS = {
    "payload_too_large": PayloadTooLargeException,
    "unsupported_media_type": UnsupportedMediaTypeException,
}


class SecurityMiddleware(BaseHTTPMiddleware):
    def __init__(self, app: Any, settings: Settings | None = None) -> None:
        super().__init__(app)
        self._settings = settings or default_settings

    def _log_violation(self, request: Request, violation_type: str, error_code: str) -> None:
        events.log_event(
            logger,
            events.SECURITY_VIOLATION,
            level=30,  # logging.WARNING
            violation_type=violation_type,
            ip=request.client.host if request.client else None,
            route=request.url.path,
            method=request.method,
            error_code=error_code,
            request_id=getattr(request.state, "request_id", None),
        )

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        try:
            if not is_trusted_host(request, self._settings):
                self._log_violation(request, "untrusted_host", "PIA-1009")
                raise UntrustedHostException(detail=request.headers.get("host"))

            violation = validate_request(request, self._settings)
            if violation is not None:
                self._log_violation(request, violation.reason, violation.error_code.code)
                exception_type = _VIOLATION_EXCEPTIONS[violation.reason]
                raise exception_type()
        except PIAOSException as exc:
            # Exceções levantadas dentro de um BaseHTTPMiddleware NÃO
            # passam pelos handlers registrados via
            # `app.add_exception_handler` (limitação conhecida do
            # Starlette/FastAPI — só o catch-all genérico enxerga
            # exceções de middleware). Chamamos o handler diretamente
            # para reaproveitar a mesma resposta padronizada e o mesmo
            # logging do Módulo 2.7, em vez de duplicar essa lógica aqui.
            return await piaos_exception_handler(request, exc)

        response = await call_next(request)
        for name, value in build_security_headers(self._settings).items():
            response.headers[name] = value
        return response
