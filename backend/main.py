"""
Ponto de entrada da aplicação PIA-OS Backend.

Responsável apenas por montar a aplicação FastAPI (app factory):
configuração, middlewares, exception handlers e routers básicos.
Nenhuma regra de negócio é definida aqui.
"""

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware

from app.api.router import api_router, root_router
from app.config.settings import settings
from app.core.lifespan import lifespan
from app.core.security import configure_security_middleware
from app.docs.openapi import apply_metadata_extension, build_openapi_kwargs
from app.logging.middleware import LoggingMiddleware
from app.middleware.exception_handler import register_exception_handlers
from app.middleware.request_id import RequestIDMiddleware
from app.middleware.timing import TimingMiddleware
from app.security.cors import build_cors_kwargs


def create_app() -> FastAPI:
    # Toda a metadata OpenAPI (título, descrição, versão, licença,
    # contato, servidores, tags) vem de app.docs.openapi — Módulo 2.9.
    app = FastAPI(**build_openapi_kwargs(settings), lifespan=lifespan)
    apply_metadata_extension(app, settings)

    # Ordem importa (cada add_middleware seguinte fica mais externo,
    # executando primeiro na entrada da requisição):
    #   Logging (mais interno) -> Timing -> Security/RateLimit ->
    #   RequestID -> CORS (mais externo).
    # RequestID precisa vir depois de Security para que request_id já
    # esteja disponível quando uma violação de segurança for logada.
    # CORS precisa ser o mais externo (preflight + headers em toda
    # resposta, inclusive erros de camadas mais internas).
    app.add_middleware(LoggingMiddleware)
    app.add_middleware(TimingMiddleware)
    configure_security_middleware(app, settings)
    app.add_middleware(RequestIDMiddleware)
    app.add_middleware(CORSMiddleware, **build_cors_kwargs(settings))

    register_exception_handlers(app)

    # Nenhum endpoint é registrado diretamente aqui — tudo vem de
    # app.api.router (ver app/api/router.py e docs/API.md).
    app.include_router(root_router)
    app.include_router(api_router, prefix=settings.api_prefix)

    return app


app = create_app()
