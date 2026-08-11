"""
Cabeçalhos de segurança HTTP.

Aplicados a toda resposta pelo `SecurityMiddleware`
(`app/security/middleware.py`). Valores padrão são deliberadamente
restritivos — nenhum endpoint funcional foi criado ainda que precise de
uma exceção a eles.
"""

from app.config.settings import Settings

# Cabeçalhos estáticos — não dependem de configuração por ambiente.
_STATIC_HEADERS: dict[str, str] = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=(), payment=()",
    "Cross-Origin-Resource-Policy": "same-origin",
    "Cross-Origin-Opener-Policy": "same-origin",
}


def build_security_headers(settings: Settings) -> dict[str, str]:
    """Monta o conjunto de cabeçalhos de segurança para a resposta atual.

    `Content-Security-Policy` só é incluído se `settings.csp_policy`
    estiver definido — a especificação do Módulo 2.8 pede a estrutura
    pronta, sem uma política definitiva ainda (uma CSP mal calibrada
    quebra a aplicação de formas sutis; definir a política real é
    trabalho de um módulo futuro, quando os endpoints funcionais
    existirem e puderem ser testados contra ela).
    """
    headers = dict(_STATIC_HEADERS)
    if settings.csp_policy:
        headers["Content-Security-Policy"] = settings.csp_policy
    return headers
