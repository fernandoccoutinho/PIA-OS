"""
Health check — liveness.

Deliberadamente não verifica banco, ORM ou configuração: liveness deve
refletir apenas se o processo está no ar. A especificação do Módulo 2.5
pede essas verificações em `/health`, mas isso reproduziria o mesmo
antipadrão já identificado e corrigido no Módulo 2.3 (um orquestrador
reiniciaria a aplicação por uma instabilidade momentânea do banco). As
verificações de app/banco/ORM/configuração ficam em `/status`
(`app/routers/status.py`), que é readiness — ver `docs/DATABASE.md` e
`docs/API.md`.
"""

from fastapi import APIRouter

from app.docs.responses import response_500
from app.docs.tags import TAG_HEALTH
from app.schemas.health import HealthResponse

router = APIRouter(tags=[TAG_HEALTH.name])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Liveness do processo",
    description=(
        "Verificação simples de vivacidade — responde 'ok' se o processo está "
        "no ar, sem consultar banco, ORM ou configuração (isso fica em "
        "`/status`). Indicado para liveness probes de alta frequência."
    ),
    responses=response_500(),
)
def health() -> HealthResponse:
    """Verificação simples de vivacidade — o processo está no ar."""
    return HealthResponse(status="ok")
