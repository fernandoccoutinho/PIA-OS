"""Versões: backend, API, banco de dados e plataforma PIA-OS."""

from fastapi import APIRouter

from app.config.constants import API_VERSION, PIA_OS_VERSION
from app.config.settings import settings
from app.database.health import get_database_version
from app.docs.responses import response_500
from app.docs.tags import TAG_VERSION
from app.schemas.health import VersionResponse

router = APIRouter(tags=[TAG_VERSION.name])


@router.get(
    "/version",
    response_model=VersionResponse,
    summary="Versões da plataforma",
    description=(
        "Retorna a versão do backend (componente), da API REST, do servidor "
        "PostgreSQL (null se inacessível) e da plataforma PIA-OS como um todo."
    ),
    responses=response_500(),
)
def version() -> VersionResponse:
    """Retorna versão do backend, da API, do banco (se acessível) e do PIA-OS."""
    return VersionResponse(
        app_name=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
        api_version=API_VERSION,
        pia_os_version=PIA_OS_VERSION,
        database_version=get_database_version(),
    )
