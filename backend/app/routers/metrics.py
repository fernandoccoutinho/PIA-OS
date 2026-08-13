"""
Métricas mínimas de processo — herdado do Módulo 2.1.

Não faz parte da lista de endpoints exigidos pelo Módulo 2.5 (root,
health, status, version), mas preservado por compatibilidade — nenhuma
API existente é removida.
"""

import time

from fastapi import APIRouter

from app.config.settings import settings
from app.docs.responses import response_500
from app.docs.tags import TAG_METRICS
from app.schemas.health import MetricsResponse

router = APIRouter(tags=[TAG_METRICS.name])

_START_TIME = time.monotonic()


@router.get(
    "/metrics",
    response_model=MetricsResponse,
    summary="Métricas de processo",
    description="Uptime do processo, em segundos, e ambiente ativo. Sem métricas de negócio.",
    responses=response_500(),
)
def metrics() -> MetricsResponse:
    """Métricas mínimas de processo (uptime). Sem coleta de métricas de negócio."""
    return MetricsResponse(
        uptime_seconds=time.monotonic() - _START_TIME,
        environment=settings.environment,
    )
