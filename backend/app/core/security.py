"""
Bootstrap de segurança do PIA-OS — ponto de composição, não biblioteca.

Mesma relação que `app.core.logging` tem com `app.logging` (Módulo 2.6):
`app/security/` é infraestrutura genérica; este módulo é a "cola"
específica do PIA-OS que decide quais middlewares registrar — chamado
em `main.py::create_app()`.
"""

from fastapi import FastAPI

from app.config.settings import Settings
from app.security.middleware import SecurityMiddleware
from app.security.rate_limit import RateLimitMiddleware


def configure_security_middleware(app: FastAPI, settings: Settings) -> None:
    """Registra `SecurityMiddleware` e, se habilitado, `RateLimitMiddleware`.

    Não registra CORS aqui — ver `app.security.cors.build_cors_kwargs`,
    usado diretamente em `main.py`, porque o `CORSMiddleware` precisa
    ficar mais externo que `RequestIDMiddleware` (adicionado depois
    desta chamada) para responder a preflight o mais cedo possível e
    anexar cabeçalhos CORS a toda resposta, inclusive erros gerados por
    camadas mais internas. Ver ordem completa documentada em `main.py`.
    """
    app.add_middleware(SecurityMiddleware, settings=settings)
    if settings.rate_limit_enabled:
        app.add_middleware(RateLimitMiddleware)
