"""
Dependency Injection centralizada.

Todo endpoint que precisar de sessão de banco, configuração, ou contexto
da requisição importa daqui — nunca instancia esses recursos diretamente
dentro de um handler de rota.
"""

from dataclasses import dataclass

from fastapi import Request

from app.config.settings import Settings, settings
from app.database.session import get_db as _get_db

# Reexportado com o nome que a spec do Módulo 2.5 pede — mesma dependency
# de sessão criada no Módulo 2.3 (`app.database.session.get_db`), não uma
# segunda implementação.
get_db_session = _get_db


def get_app_settings() -> Settings:
    """Dependency de configuração — permite override em testes via
    `app.dependency_overrides[get_app_settings] = lambda: outras_settings`."""
    return settings


@dataclass(frozen=True)
class RequestContext:
    """Contexto da requisição atual — estrutura pensada para observabilidade
    futura (rastreamento distribuído, integração com IA). A maioria dos
    campos é `None` nesta etapa: só `request_id` é preenchido de fato hoje
    (via `RequestIDMiddleware`); os demais existem para que módulos
    futuros não precisem alterar a assinatura desta dependency — apenas
    passar a populá-los.
    """

    request_id: str | None
    path: str
    method: str
    correlation_id: str | None = None
    session_id: str | None = None
    trace_id: str | None = None
    user_id: str | None = None
    tenant: str | None = None
    provider: str | None = None


def get_request_context(request: Request) -> RequestContext:
    return RequestContext(
        request_id=getattr(request.state, "request_id", None),
        path=request.url.path,
        method=request.method,
    )


def get_current_user() -> None:
    """Placeholder para autenticação futura — deliberadamente não
    implementado neste módulo (ver escopo do Módulo 2.5: sem login,
    autenticação ou usuários). Endpoints futuros que precisarem de um
    usuário autenticado dependem desta função; ela hoje sempre retorna
    `None`, e nenhum endpoint atual a utiliza.
    """
    return None
