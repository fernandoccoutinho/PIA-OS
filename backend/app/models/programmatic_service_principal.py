"""
Principal técnico programático e bucket de cota (E6.2).

```text
SERVICE_PRINCIPAL != HUMAN_USER
SECRET_DIGEST_ONLY = TRUE
QUOTA_KEY = principal + operation + window
```

Duas entidades, um propósito: tornar `POST /api/v1/predictive-evaluations`
utilizável por um cliente programático sem abrir uma janela insegura.

`ProgrammaticServicePrincipal` **nunca** guarda o segredo. Guarda apenas o
digest HMAC-SHA-256 hexadecimal canônico, calculado com separação de
domínio sobre a `SECRET_KEY` central. Recuperar a credencial a partir da
linha é impossível por construção — o provisionamento a exibe uma única
vez e a esquece.

`ProgrammaticQuotaBucket` é contagem por janela, não histórico: a fonte de
verdade da cota é o PostgreSQL compartilhado entre réplicas, nunca a
memória de um processo.
"""

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine.interfaces import Dialect
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, TypeDecorator, TypeEngine

from app.models.base_model import BaseModel

# Vocabulário fechado de escopo técnico da E6.2. Ampliar exige contrato
# novo — a constante existe para que "adicionar um escopo" seja uma
# alteração visível, não um efeito colateral de configuração.
SCOPE_PREDICTIVE_EVALUATE = "predictive:evaluate"
PROGRAMMATIC_SCOPES: frozenset[str] = frozenset({SCOPE_PREDICTIVE_EVALUATE})

# Operação sob cota. Uma só nesta etapa; a coluna existe para que a
# segunda operação não exija migration de chave.
OPERATION_PREDICTIVE_EVALUATE = "predictive_evaluate"


class CanonicalScopeArray(TypeDecorator[Any]):
    """`JSONB` no PostgreSQL, `JSON` genérico nos demais.

    Mesmo precedente de `RetentionPolicyRules` (E4.9.6): o tipo físico no
    banco não muda, só a representação em memória. Um `with_variant`
    inline resolveria o dialeto, mas não passa no mypy estrito deste
    repositório sem um `type: ignore` novo.
    """

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())  # type: ignore[no-untyped-call]
        return dialect.type_descriptor(JSON())


def canonical_scopes(scopes: object) -> tuple[str, ...]:
    """Ordena, remove duplicatas e valida contra o vocabulário fechado.

    Canonicalizar na escrita e não na leitura é deliberado: duas linhas com
    o mesmo conjunto de escopos têm a mesma representação persistida, então
    comparar escopo nunca depende da ordem em que alguém digitou.

    ```text
    UNKNOWN_SCOPE = REJECTED_AT_WRITE_TIME
    ```
    """
    if isinstance(scopes, str) or not hasattr(scopes, "__iter__"):
        raise ValueError("scopes deve ser uma coleção de strings, não uma string solta")
    itens = list(scopes)
    for item in itens:
        if not isinstance(item, str):
            raise ValueError(f"escopo deve ser string, recebido {type(item).__name__}")
        if item not in PROGRAMMATIC_SCOPES:
            raise ValueError(f"escopo fora do vocabulário fechado da E6.2: {item!r}")
    if not itens:
        raise ValueError("um principal técnico sem escopo não conseguiria fazer nada")
    return tuple(sorted(set(itens)))


def normalize_persisted_scopes(scopes: object) -> tuple[str, ...]:
    """Leitura tolerante: ordena e deduplica, mas NÃO rejeita.

    A validação do vocabulário fechado pertence à escrita. Na leitura,
    rejeitar transformaria uma linha estranha em `500` — e um erro de
    servidor é uma resposta pior do que negar acesso. Escopo desconhecido
    simplesmente não concede nada.

    ```text
    UNKNOWN_PERSISTED_SCOPE = GRANTS_NOTHING
    READ_PATH_NEVER_RAISES = TRUE
    ```
    """
    if scopes is None or isinstance(scopes, str) or not hasattr(scopes, "__iter__"):
        return ()
    return tuple(sorted({item for item in scopes if isinstance(item, str)}))


class ProgrammaticServicePrincipal(BaseModel):
    """Identidade de SERVIÇO. Não é usuário humano e não concede aprovação.

    ```text
    ACTIVE = revoked_at IS NULL AND (expires_at IS NULL OR expires_at > now)
    SERVICE_SCOPE != PIAP_APPROVAL
    ```
    """

    __tablename__ = "programmatic_service_principals"

    key_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    secret_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    scopes: Mapped[list[str]] = mapped_column(CanonicalScopeArray, nullable=False)
    quota_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    quota_window_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    description: Mapped[str | None] = mapped_column(String(200), nullable=True, default=None)
    expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    __table_args__ = (
        CheckConstraint("quota_limit > 0", name="ck_programmatic_principal_quota_limit_positive"),
        CheckConstraint(
            "quota_window_seconds > 0",
            name="ck_programmatic_principal_quota_window_positive",
        ),
        CheckConstraint(
            "char_length(secret_digest) = 64",
            name="ck_programmatic_principal_digest_length",
        ),
        CheckConstraint("char_length(key_id) >= 8", name="ck_programmatic_principal_key_id_length"),
        Index("ix_programmatic_service_principals_key_id", "key_id", unique=True),
    )

    def is_active_at(self, moment: datetime) -> bool:
        """Revogado ou expirado é indistinguível de inexistente na resposta.

        A distinção existe aqui, no domínio, porque operar exige saber por
        que a credencial não vale. Ela **não** atravessa a fronteira HTTP.
        """
        if self.revoked_at is not None:
            return False
        return self.expires_at is None or self.expires_at > moment


class ProgrammaticQuotaBucket(BaseModel):
    """Contagem atômica por `(principal, operação, janela)` no PostgreSQL.

    Não existe fallback em memória: se o banco não responde, a chamada é
    recusada. Um contador em memória por réplica não é uma cota — é uma
    cota multiplicada pelo número de réplicas.
    """

    __tablename__ = "programmatic_quota_buckets"

    principal_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("programmatic_service_principals.id", ondelete="CASCADE"), nullable=False
    )
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    window_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))

    __table_args__ = (
        UniqueConstraint(
            "principal_id",
            "operation",
            "window_start",
            name="uq_programmatic_quota_bucket_window",
        ),
        CheckConstraint("used >= 0", name="ck_programmatic_quota_bucket_used_non_negative"),
    )
