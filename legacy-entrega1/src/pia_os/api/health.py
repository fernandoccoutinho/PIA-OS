"""Endpoints de verificação de saúde (health checks).

Servem para o Docker/CI e para monitoramento saberem se a aplicação
está de pé. Não dependem de banco de dados nesta fase.
"""

from fastapi import APIRouter
from pydantic import BaseModel

from pia_os import __version__

router = APIRouter(tags=["health"])


class HealthStatus(BaseModel):
    """Resposta do health check."""

    status: str
    service: str
    version: str


@router.get("/health", response_model=HealthStatus)
def health() -> HealthStatus:
    """Retorna o estado atual do serviço."""
    return HealthStatus(status="ok", service="pia-os", version=__version__)
