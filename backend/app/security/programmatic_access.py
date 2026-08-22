"""
Verificador Bearer fail-closed do principal técnico (E6.2).

```text
MISSING == MALFORMED == UNKNOWN == WRONG == REVOKED == EXPIRED -> 401 PIA-7001
VERIFIER_UNAVAILABLE -> DENY, NEVER ANONYMOUS
SERVICE_CREDENTIAL != PIAP_APPROVAL
```

Seis condições de falha, uma resposta pública. Diferenciá-las diria a um
atacante qual `key_id` existe, e transformaria a resposta de erro num
oráculo de enumeração. A distinção existe nos logs estruturais apenas
como categoria, nunca com o token.

O segredo não é armazenado em lugar algum: o banco guarda o digest
HMAC-SHA-256 com separação de domínio, e a comparação usa
`hmac.compare_digest`. Comparar com `==` vazaria o prefixo correto pelo
tempo de execução.
"""

import hashlib
import hmac
import secrets
import uuid
from dataclasses import dataclass
from datetime import datetime

from app.exceptions.api import AuthenticationException, InsufficientScopeException
from app.models.programmatic_service_principal import (
    ProgrammaticServicePrincipal,
    normalize_persisted_scopes,
)
from app.repositories.programmatic_access_repository import ProgrammaticAccessRepository
from app.security.secrets import SecretsManager, secrets_manager

# Rótulo de domínio fixo. Sem ele, o mesmo `SECRET_KEY` produziria digests
# intercambiáveis entre finalidades diferentes: um digest calculado para
# outro propósito passaria a valer como credencial aqui.
DOMAIN_LABEL = "pia-os/e6.2/programmatic-service-principal/v1"

TOKEN_PREFIX = "pia_"
BEARER_PREFIX = "Bearer "
MIN_SECRET_BYTES = 32
KEY_ID_BYTES = 18

# Detalhe público único. Qualquer variação por condição seria um oráculo.
PUBLIC_AUTH_DETAIL = "credencial de serviço ausente ou inválida"
PUBLIC_SCOPE_DETAIL = "principal técnico sem o escopo exigido para esta operação"


@dataclass(frozen=True)
class ProgrammaticPrincipal:
    """Projeção imutável do principal autenticado, sem material secreto.

    Não carrega `secret_digest` de propósito: o que atravessa a aplicação
    depois da autenticação não precisa do digest, e o que não circula não
    vaza.
    """

    id: uuid.UUID
    key_id: str
    scopes: tuple[str, ...]
    quota_limit: int
    quota_window_seconds: int

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes


def generate_key_id() -> str:
    """Identificador público opaco — sem tenant, e-mail ou identidade humana."""
    return secrets.token_urlsafe(KEY_ID_BYTES).replace(".", "-")


def generate_secret() -> str:
    """Segredo de alta entropia, exibido uma única vez no provisionamento."""
    return secrets.token_urlsafe(MIN_SECRET_BYTES)


def compute_secret_digest(
    key_id: str, secret: str, *, manager: SecretsManager | None = None
) -> str:
    """HMAC-SHA-256 hexadecimal canônico, com `key_id` dentro da mensagem.

    Incluir o `key_id` impede que um segredo válido para uma credencial
    seja reaproveitado em outra: o digest é ligado ao par, não ao segredo.
    """
    gerente = manager or secrets_manager
    mensagem = f"{DOMAIN_LABEL}:{key_id}:{secret}".encode()
    return hmac.new(gerente.get_secret_key().encode("utf-8"), mensagem, hashlib.sha256).hexdigest()


def parse_bearer_credential(header_value: str | None) -> tuple[str, str]:
    """`Authorization: Bearer pia_<key_id>.<secret>` -> `(key_id, secret)`.

    Levanta a MESMA exceção pública de qualquer outra falha. O formato
    inválido não é mais informativo para o cliente legítimo do que a
    credencial errada.
    """
    if not header_value or not header_value.startswith(BEARER_PREFIX):
        raise AuthenticationException(detail=PUBLIC_AUTH_DETAIL)
    token = header_value[len(BEARER_PREFIX) :].strip()
    if not token.startswith(TOKEN_PREFIX):
        raise AuthenticationException(detail=PUBLIC_AUTH_DETAIL)
    corpo = token[len(TOKEN_PREFIX) :]
    key_id, separador, secret = corpo.partition(".")
    if not separador or not key_id or not secret:
        raise AuthenticationException(detail=PUBLIC_AUTH_DETAIL)
    return key_id, secret


def _to_principal(linha: ProgrammaticServicePrincipal) -> ProgrammaticPrincipal:
    return ProgrammaticPrincipal(
        id=linha.id,
        key_id=linha.key_id,
        scopes=normalize_persisted_scopes(linha.scopes),
        quota_limit=linha.quota_limit,
        quota_window_seconds=linha.quota_window_seconds,
    )


def authenticate_programmatic_principal(
    header_value: str | None,
    repository: ProgrammaticAccessRepository,
    *,
    manager: SecretsManager | None = None,
) -> ProgrammaticPrincipal:
    """Autentica ou recusa. Nunca devolve principal anônimo.

    Falha do repositório (banco fora, verificador indisponível) é traduzida
    para a mesma recusa: `IDP_UNAVAILABLE = BLOCK, NEVER DEGRADE`.
    """
    key_id, secret = parse_bearer_credential(header_value)
    try:
        linha = repository.get_by_key_id(key_id)
        agora: datetime | None = repository.database_now() if linha is not None else None
    except AuthenticationException:
        raise
    except Exception as exc:  # verificador indisponível -> recusa, não liberação
        raise AuthenticationException(detail=PUBLIC_AUTH_DETAIL) from exc
    if linha is None or agora is None:
        # Calcula um digest descartável mesmo sem linha: o tempo de resposta
        # de `key_id` inexistente fica parecido com o de segredo errado.
        compute_secret_digest(key_id, secret, manager=manager)
        raise AuthenticationException(detail=PUBLIC_AUTH_DETAIL)
    esperado = compute_secret_digest(key_id, secret, manager=manager)
    if not hmac.compare_digest(esperado, linha.secret_digest):
        raise AuthenticationException(detail=PUBLIC_AUTH_DETAIL)
    if not linha.is_active_at(agora):
        raise AuthenticationException(detail=PUBLIC_AUTH_DETAIL)
    return _to_principal(linha)


def require_scope(principal: ProgrammaticPrincipal, scope: str) -> None:
    """403/PIA-7002 antes de qualquer ciência e antes de consumir cota.

    ```text
    AUTHENTICATED != AUTHORIZED
    ```
    """
    if not principal.has_scope(scope):
        raise InsufficientScopeException(detail=PUBLIC_SCOPE_DETAIL)
