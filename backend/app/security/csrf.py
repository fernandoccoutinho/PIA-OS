"""
Proteção CSRF — estrutura apenas, conforme o escopo do Módulo 2.8.

CSRF é uma preocupação de autenticação baseada em cookies — este backend
ainda não tem nenhuma (Módulo 2.5 não implementa login/sessão). Nada
aqui é ativado ou conectado ao `main.py`; existe para que um módulo
futuro de autenticação por cookie/sessão não precise desenhar isso do
zero.
"""

from dataclasses import dataclass

from starlette.requests import Request


@dataclass(frozen=True)
class CSRFPolicy:
    enabled: bool = False
    cookie_name: str = "pia_csrf_token"
    header_name: str = "X-CSRF-Token"
    safe_methods: frozenset[str] = frozenset({"GET", "HEAD", "OPTIONS"})


DEFAULT_CSRF_POLICY = CSRFPolicy()


def requires_csrf_check(request: Request, policy: CSRFPolicy = DEFAULT_CSRF_POLICY) -> bool:
    """Se uma requisição precisaria de validação CSRF, segundo a política.

    Sempre `False` enquanto `policy.enabled` for `False` (padrão) — não
    há autenticação por cookie para proteger ainda. A lógica de
    comparação do token (cookie vs. header) é responsabilidade de um
    módulo futuro; esta função só decide *se* a checagem se aplicaria.
    """
    if not policy.enabled:
        return False
    return request.method.upper() not in policy.safe_methods
