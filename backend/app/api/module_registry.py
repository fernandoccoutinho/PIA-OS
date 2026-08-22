"""
Lista canônica dos módulos de API registrados.

Módulo separado (não dentro de `api/router.py`) para que `routers/status.py`
possa importar apenas os *nomes* sem precisar importar os objetos
`APIRouter` de verdade — o que geraria import circular, já que
`api/router.py` importa `app.routers.status`.
"""

REGISTERED_MODULE_NAMES: tuple[str, ...] = (
    "health",
    "status",
    "version",
    "metrics",
    "predictive_evaluations",
)
