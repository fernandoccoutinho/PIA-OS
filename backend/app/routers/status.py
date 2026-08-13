"""
Status — readiness detalhada.

Verifica aplicação, banco, ORM e configuração (o que a especificação do
Módulo 2.5 pedia para `/health`) — ver justificativa em
`app/routers/health.py` e `docs/API.md` para por que essas checagens
vivem aqui, não em `/health`.
"""

import time

from fastapi import APIRouter

from app.api.module_registry import REGISTERED_MODULE_NAMES
from app.config.config import ConfigurationError, validate_environment
from app.config.constants import API_VERSION
from app.config.settings import settings
from app.database.health import check_database_health, check_orm_health
from app.docs.responses import response_500
from app.docs.tags import TAG_STATUS
from app.schemas.health import ComponentStatus, StatusResponse

router = APIRouter(tags=[TAG_STATUS.name])

_START_TIME = time.monotonic()


def _check_config() -> ComponentStatus:
    try:
        validate_environment(settings)
        return ComponentStatus(name="config", healthy=True)
    except ConfigurationError as exc:
        return ComponentStatus(name="config", healthy=False, detail=str(exc))


@router.get(
    "/status",
    response_model=StatusResponse,
    summary="Readiness detalhada",
    description=(
        "Verifica aplicação, banco de dados, sessão ORM e configuração. "
        "`status` é 'degraded' se qualquer componente falhar. Indicado para "
        "readiness probes e dashboards operacionais — mais custoso que "
        "`/health`, não recomendado como liveness probe de alta frequência."
    ),
    responses=response_500(),
)
def status() -> StatusResponse:
    """Verificação de prontidão (readiness): aplicação, banco, ORM e config."""
    db_health = check_database_health()
    orm_healthy = check_orm_health()
    config_status = _check_config()

    components = [
        ComponentStatus(name="application", healthy=True),
        ComponentStatus(
            name="database",
            healthy=db_health.available,
            detail=None if db_health.available else "Banco de dados inacessível.",
        ),
        ComponentStatus(
            name="orm",
            healthy=orm_healthy,
            detail=None if orm_healthy else "Sessão ORM não conseguiu executar uma consulta.",
        ),
        config_status,
    ]
    overall_healthy = all(c.healthy for c in components)

    return StatusResponse(
        status="ok" if overall_healthy else "degraded",
        database_connected=db_health.available,
        database_response_time_ms=db_health.response_time_ms,
        environment=settings.environment,
        uptime_seconds=time.monotonic() - _START_TIME,
        api_version=API_VERSION,
        modules_loaded=len(REGISTERED_MODULE_NAMES),
        components=components,
    )
