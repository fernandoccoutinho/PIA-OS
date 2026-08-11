"""
Configuração de CORS — centralizada no Módulo 2.2.

Usa `starlette.middleware.cors.CORSMiddleware` diretamente (já parte do
FastAPI/Starlette, nenhuma dependência nova) em vez de reimplementar a
lógica de preflight (`OPTIONS`) — isso é propositalmente sutil (ordem de
headers, tratamento de credenciais, wildcard vs. origem específica) e
reimplementar aumentaria a superfície de erro sem benefício real. Este
módulo só traduz `Settings` para os kwargs que o `CORSMiddleware` espera.
"""

from app.config.settings import Settings


def build_cors_kwargs(settings: Settings) -> dict[str, object]:
    """Constrói os kwargs de `CORSMiddleware` a partir da configuração central.

    Nota de segurança: `allow_credentials=True` combinado com
    `allow_origins=["*"]` é proibido pela especificação CORS (o
    Starlette já recusa isso em runtime) — se `cors_allow_credentials`
    estiver ativo, `cors_allowed_origins` precisa ser uma lista explícita,
    nunca `*`.
    """
    return {
        "allow_origins": settings.cors_allowed_origins_list,
        "allow_methods": settings.cors_allowed_methods_list,
        "allow_headers": settings.cors_allowed_headers_list,
        "allow_credentials": settings.cors_allow_credentials,
    }
