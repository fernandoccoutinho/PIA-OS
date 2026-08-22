"""
Roteador central.

Nenhum endpoint é registrado diretamente em `main.py` — tudo passa por
aqui. `root_router` é montado na raiz da aplicação (`GET /` não leva o
prefixo de API); `api_router` agrega os demais e é montado sob
`settings.api_prefix` (`/api/v1`).
"""

from fastapi import APIRouter

from app.api.module_registry import REGISTERED_MODULE_NAMES
from app.routers import health, metrics, predictive_evaluations, root, status, version

root_router = APIRouter()
root_router.include_router(root.router)

_API_ROUTERS = [
    health.router,
    status.router,
    version.router,
    metrics.router,
    predictive_evaluations.router,
]
assert len(_API_ROUTERS) == len(REGISTERED_MODULE_NAMES), (
    "api/router.py e api/module_registry.py estão dessincronizados — "
    "atualize os dois ao adicionar ou remover um módulo."
)

api_router = APIRouter()
for _router in _API_ROUTERS:
    api_router.include_router(_router)

MODULES_LOADED = len(_API_ROUTERS)
