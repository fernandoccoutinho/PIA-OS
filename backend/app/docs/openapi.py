"""
Configuração centralizada do OpenAPI.

Toda a metadata que antes vivia hardcoded em `main.py::create_app()`
passa a vir daqui — um único lugar para título, descrição, versão,
licença, contato, servidores e termos de uso. `main.py` só chama
`build_openapi_kwargs(settings)` e passa o resultado para `FastAPI(...)`.
"""

from typing import Any

from fastapi import FastAPI

from app.config.settings import Settings
from app.docs.changelog import render_changelog_markdown
from app.docs.metadata import build_api_metadata
from app.docs.tags import build_openapi_tags_metadata


def _build_description(settings: Settings) -> str:
    base = (
        "Backend do PIA-OS (Persistent Intelligence Architecture Operating "
        "System). Esta etapa expõe apenas infraestrutura — nenhuma "
        "funcionalidade de domínio do PIA-OS está implementada ainda.\n\n"
        "Todo erro segue um envelope único e documentado — ver "
        "`docs/ERRORS.md` no repositório. Toda resposta inclui os headers "
        "`X-Request-ID` e `X-Response-Time-Ms`.\n\n"
        "---\n\n"
    )
    return base + render_changelog_markdown()


def build_servers(settings: Settings) -> list[dict[str, str]]:
    """Lista de servidores do OpenAPI — hoje só o servidor atual do
    ambiente ativo. Múltiplos servidores (dev/staging/prod simultâneos)
    ficam para quando houver URLs públicas reais de cada um."""
    return [
        {
            "url": "/",
            "description": f"Servidor atual ({settings.environment.value})",
        }
    ]


def build_openapi_kwargs(settings: Settings) -> dict[str, Any]:
    """Kwargs prontos para `FastAPI(**build_openapi_kwargs(settings))`."""
    return {
        "title": settings.app_name,
        "description": _build_description(settings),
        "version": settings.app_version,
        "docs_url": settings.docs_url,
        "redoc_url": settings.redoc_url,
        "openapi_url": settings.openapi_url,
        "openapi_tags": build_openapi_tags_metadata(),
        "servers": build_servers(settings),
        "terms_of_service": None,  # placeholder — sem termos de uso definitivos nesta etapa
        "contact": {
            "name": "Equipe PIA-OS",
            "email": "contato@example.com",  # placeholder — sem contato real definido ainda
        },
        "license_info": {
            "name": "Proprietary",  # placeholder — licença definitiva não definida nesta etapa
        },
    }


def apply_metadata_extension(app: FastAPI, settings: Settings) -> None:
    """Sobrescreve `app.openapi()` para injetar `info.x-metadata`
    (versão do backend, da API, do PIA-OS e timestamp de geração) no
    schema gerado — `x-*` é o mecanismo padrão da especificação OpenAPI
    para extensões, não uma estrutura inventada fora do padrão.

    O schema é cacheado por padrão pelo FastAPI (`app.openapi_schema`);
    respeitamos esse cache, exceto que recomputamos `x-metadata` a cada
    chamada, para que `generated_at` reflita o momento real da consulta,
    não o momento do primeiro request após o startup.
    """

    def custom_openapi() -> dict[str, Any]:
        if app.openapi_schema is None:
            app.openapi_schema = FastAPI.openapi(app)
        app.openapi_schema["info"]["x-metadata"] = dict(build_api_metadata(settings))
        return app.openapi_schema

    app.openapi = custom_openapi  # type: ignore[method-assign]
