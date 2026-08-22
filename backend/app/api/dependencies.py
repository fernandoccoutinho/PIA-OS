"""
Dependency Injection centralizada.

Todo endpoint que precisar de sessão de banco, configuração, ou contexto
da requisição importa daqui — nunca instancia esses recursos diretamente
dentro de um handler de rota.
"""

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config.settings import Settings, settings
from app.database.session import get_db as _get_db
from app.exceptions.api import TooManyRequestsException
from app.exceptions.database import DatabaseUnavailableException
from app.models.programmatic_service_principal import (
    OPERATION_PREDICTIVE_EVALUATE,
    SCOPE_PREDICTIVE_EVALUATE,
)
from app.repositories.programmatic_access_repository import ProgrammaticAccessRepository
from app.security.programmatic_access import (
    ProgrammaticPrincipal,
    authenticate_programmatic_principal,
    require_scope,
)

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


QUOTA_EXCEEDED_DETAIL = "cota do principal técnico esgotada para esta janela"
QUOTA_AUTHORITY_UNAVAILABLE_DETAIL = (
    "autoridade de cota indisponível; a chamada foi recusada sem avaliar"
)

programmatic_bearer_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="PIAServiceBearer",
    bearerFormat="pia_<key_id>.<secret>",
    description=(
        "Credencial de SERVIÇO da E6.2. Não representa usuário humano e nunca "
        "concede, substitui ou amplia aprovação PIAP."
    ),
)
"""Esquema Bearer publicado no OpenAPI.

`auto_error=False` é obrigatório: com o erro automático do FastAPI, a
ausência do header produziria um `403` do próprio framework, distinto do
`401` de credencial inválida — e essa diferença é exatamente o oráculo de
enumeração que a decisão proíbe. Com `False`, o verificador recebe `None`
e devolve a mesma recusa pública de qualquer outra falha.

```text
FRAMEWORK_AUTO_ERROR = ORACLE
MISSING == MALFORMED == UNKNOWN == WRONG == REVOKED == EXPIRED -> 401
```
"""

SessionDep = Annotated[Session, Depends(get_db_session)]
BearerCredentials = Annotated[
    HTTPAuthorizationCredentials | None, Security(programmatic_bearer_scheme)
]


def get_programmatic_principal(
    credentials: BearerCredentials,
    session: SessionDep,
) -> ProgrammaticPrincipal:
    """Autentica o principal TÉCNICO. Separada de `get_current_user`.

    Duas dependencies distintas de propósito: `get_current_user` é o
    placeholder da identidade HUMANA (login, MFA, aprovação — E8). Uma
    credencial de serviço não é um usuário, e fundi-las faria o escopo
    técnico parecer autoridade de aprovação.

    O `HTTPBearer` já separou esquema e token; o verificador recebe o
    header reconstruído para manter uma única gramática de credencial, em
    vez de dois analisadores que podem divergir.

    ```text
    SERVICE_PRINCIPAL != HUMAN_USER
    SERVICE_SCOPE != PIAP_APPROVAL
    ```
    """
    header = f"{credentials.scheme} {credentials.credentials}" if credentials is not None else None
    return authenticate_programmatic_principal(header, ProgrammaticAccessRepository(session))


PrincipalDep = Annotated[ProgrammaticPrincipal, Depends(get_programmatic_principal)]


def require_predictive_evaluate_access(
    principal: PrincipalDep,
    session: SessionDep,
) -> ProgrammaticPrincipal:
    """Autenticação -> escopo -> cota, nesta ordem, antes de qualquer ciência.

    A ordem é a garantia: um principal sem escopo recebe 403 sem consumir
    cota, e nenhum caminho chega à E5 sem passar pelos três.

    ```text
    AUTH -> SCOPE -> QUOTA -> SCIENCE
    QUOTA_BEFORE_SCIENCE = TRUE
    IN_MEMORY_FALLBACK = NONE
    ```
    """
    require_scope(principal, SCOPE_PREDICTIVE_EVALUATE)
    repositorio = ProgrammaticAccessRepository(session)
    try:
        liberado = repositorio.consume_quota(
            principal_id=principal.id,
            operation=OPERATION_PREDICTIVE_EVALUATE,
            quota_limit=principal.quota_limit,
            quota_window_seconds=principal.quota_window_seconds,
        )
    except Exception as exc:
        # Fail closed, mas SEM mentir sobre a causa. Publicar 429 aqui
        # afirmaria que o cliente estourou a cota e o orientaria a esperar
        # a janela virar — quando o que houve foi indisponibilidade da
        # autoridade de cota, cuja recuperação não depende dele.
        #
        # QUOTA_EXCEEDED != QUOTA_AUTHORITY_UNAVAILABLE
        session.rollback()
        raise DatabaseUnavailableException(detail=QUOTA_AUTHORITY_UNAVAILABLE_DETAIL) from exc
    session.commit()
    if not liberado:
        # Único caminho legítimo para 429: o incremento condicional
        # atômico recusou porque o teto foi atingido de fato.
        raise TooManyRequestsException(detail=QUOTA_EXCEEDED_DETAIL)
    return principal
