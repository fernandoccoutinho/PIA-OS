"""Endpoint raiz — cartão de visitas da plataforma."""

from datetime import UTC, datetime

from fastapi import APIRouter

from app.config.settings import settings
from app.docs.responses import response_500
from app.docs.tags import TAG_SYSTEM
from app.schemas.health import RootResponse

router = APIRouter(tags=[TAG_SYSTEM.name])


@router.get(
    "/",
    response_model=RootResponse,
    summary="Informações da plataforma",
    description=(
        "Retorna nome, versão, ambiente, timestamp atual e onde encontrar "
        "a documentação interativa (Swagger/ReDoc). Ponto de entrada da API."
    ),
    responses=response_500(),
)
def root() -> RootResponse:
    """Informações básicas da plataforma — nome, versão, ambiente,
    timestamp e onde encontrar a documentação."""
    return RootResponse(
        name=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        timestamp=datetime.now(UTC).isoformat(),
        docs_url=settings.docs_url,
        redoc_url=settings.redoc_url,
    )
