"""
Validação de hosts confiáveis.

Implementada como checagem manual dentro do `SecurityMiddleware`
(`app/security/middleware.py`), não via
`starlette.middleware.trustedhost.TrustedHostMiddleware`: o middleware
nativo do Starlette responde diretamente com uma `PlainTextResponse`,
sem passar pelos handlers globais de exceção (Módulo 2.7) nem pelo
Logger Central (Módulo 2.6) — o que violaria a exigência explícita do
Módulo 2.8 de que toda violação seja registrada.
"""

from starlette.requests import Request

from app.config.settings import Settings


def is_trusted_host(request: Request, settings: Settings) -> bool:
    """`"*"` (padrão de desenvolvimento) aceita qualquer host. Em
    produção, `settings.trusted_hosts` deve ser uma lista explícita."""
    allowed = settings.trusted_hosts_list
    if "*" in allowed:
        return True
    host = (request.headers.get("host") or "").split(":")[0].strip().lower()
    return host in {h.lower() for h in allowed}
