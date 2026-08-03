"""Ponto de entrada da aplicação FastAPI.

Usa o padrão *application factory* (``create_app``) para facilitar testes e
futuras configurações por ambiente.
"""

from fastapi import FastAPI

from pia_os import __version__
from pia_os.api import health
from pia_os.config import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    """Cria e configura a instância do FastAPI."""
    settings = settings or get_settings()

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        debug=settings.debug,
    )

    app.include_router(health.router)

    @app.get("/", tags=["root"])
    def root() -> dict[str, str]:
        """Endpoint raiz — identifica o serviço."""
        return {"service": settings.app_name, "version": __version__}

    return app


app = create_app()
