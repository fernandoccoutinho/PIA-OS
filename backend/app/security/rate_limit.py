"""
Infraestrutura de rate limiting.

Interface (`RateLimiter` Protocol) + implementação em memória — sem
Redis nesta etapa, conforme o escopo do Módulo 2.8. Desabilitado por
padrão (`settings.rate_limit_enabled = False`); quando um backend
distribuído (Redis) for adicionado em um módulo futuro, basta uma nova
classe que implemente o mesmo Protocol — nenhum código consumidor muda.

`InMemoryRateLimiter` só é adequado para uma única instância do
processo — não compartilha estado entre réplicas. Isso é aceitável
apenas porque a funcionalidade está desligada por padrão; ativá-la em
um deployment com múltiplas réplicas sem um backend compartilhado
subestimaria a taxa real agregada (documentado em `docs/SECURITY.md`).
"""

import time
from collections.abc import Awaitable, Callable
from typing import Any, Protocol, runtime_checkable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.config.settings import settings
from app.core.error_codes import PIA_1008_TOO_MANY_REQUESTS
from app.exceptions.api import TooManyRequestsException
from app.exceptions.handlers import piaos_exception_handler
from app.logging import events
from app.logging.logger import get_logger

logger = get_logger("app.security")


@runtime_checkable
class RateLimiter(Protocol):
    def is_allowed(self, key: str) -> bool: ...


class InMemoryRateLimiter:
    """Janela deslizante simples, por chave (tipicamente IP do cliente),
    guardada em memória do processo."""

    def __init__(self, max_requests: int, window_seconds: int) -> None:
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._hits: dict[str, list[float]] = {}

    def is_allowed(self, key: str) -> bool:
        now = time.monotonic()
        window_start = now - self._window_seconds
        hits = self._hits.setdefault(key, [])
        while hits and hits[0] < window_start:
            hits.pop(0)
        if len(hits) >= self._max_requests:
            return False
        hits.append(now)
        return True


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Só é registrada em `main.py` se `settings.rate_limit_enabled` —
    por padrão a aplicação não tem rate limiting ativo."""

    def __init__(self, app: Any, limiter: RateLimiter | None = None) -> None:
        super().__init__(app)
        self._limiter = limiter or InMemoryRateLimiter(
            max_requests=settings.rate_limit_requests,
            window_seconds=settings.rate_limit_window_seconds,
        )

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        client_ip = request.client.host if request.client else "unknown"
        if not self._limiter.is_allowed(client_ip):
            events.log_event(
                logger,
                events.SECURITY_VIOLATION,
                level=30,  # logging.WARNING
                violation_type="rate_limit_exceeded",
                ip=client_ip,
                route=request.url.path,
                method=request.method,
                error_code=PIA_1008_TOO_MANY_REQUESTS.code,
            )
            # Ver nota em app/security/middleware.py: exceções de
            # middleware não passam pelos handlers registrados via
            # add_exception_handler — chamamos o handler diretamente.
            return await piaos_exception_handler(
                request, TooManyRequestsException(detail="Limite de requisições excedido.")
            )
        return await call_next(request)
