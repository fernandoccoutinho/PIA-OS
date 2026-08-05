"""
Middleware de logging de requisições.

Substitui `app.middleware.logging_middleware` (Módulo 2.1) — mesma
responsabilidade (logar início/fim de requisição), mas agora integrado
ao `LoggingContext`: `request_id` fica disponível para *qualquer* log
emitido durante o processamento da requisição (inclusive em camadas
profundas — repositório, ORM), não apenas nas duas linhas de log que
este middleware escreve.

Depende de rodar *depois* de `RequestIDMiddleware` na pilha (ver ordem
de `add_middleware` em `main.py`) — precisa que `request.state.request_id`
já exista.
"""

import time
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.logging import events, logging_context
from app.logging.logger import get_logger

logger = get_logger("app.request")


class LoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = getattr(request.state, "request_id", None)
        correlation_id = request.headers.get("X-Correlation-ID")

        with logging_context(request_id=request_id, correlation_id=correlation_id):
            events.log_event(
                logger,
                events.REQUEST_RECEIVED,
                method=request.method,
                path=request.url.path,
            )

            start = time.perf_counter()
            response = await call_next(request)
            duration_ms = (time.perf_counter() - start) * 1000

            events.log_event(
                logger,
                events.REQUEST_COMPLETED,
                method=request.method,
                path=request.url.path,
                status_code=response.status_code,
                duration_ms=round(duration_ms, 2),
            )

        return response
