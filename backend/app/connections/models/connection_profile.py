"""
`ConnectionProfile` — a conexão configurada de um principal.

```text
PROFILE_DESCREVE_CONFIGURAÇÃO != RECIBO_DESCREVE_EXECUÇÃO
ENUM_OR_REGISTRY != AVAILABLE
MANUAL_PROFILE = ONE_PER_PRINCIPAL, endpoint_ref = NULL, state = AVAILABLE
```

O perfil manual é **real**, não um marcador: é a conexão que de fato
existe e funciona desde a Chain113. `endpoint_ref` nulo é a verdade —
quem transporta é a pessoa, e não há endereço a guardar.

## O que esta tabela nunca guarda

```text
segredo · token · senha · cookie · sessão · resposta de provedor · conteúdo bruto
```

`credential_ref` é referência **opaca** a uma custódia que ainda não
existe (o cofre é etapa própria). Guardar a credencial aqui seria
improvisar o cofre dentro do kernel.
"""

import uuid

import sqlalchemy as sa
from sqlalchemy import CheckConstraint, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.connections.models.enums import ConnectionMethod, ConnectionState
from app.models.base_model import BaseModel

MAX_REF_LENGTH = 255
"""Mesmo teto de `app/orchestration/schemas/envelope.py`, e pela mesma razão."""

MAX_ENDPOINT_REF_LENGTH = 512
"""Referência opaca ao endpoint. Não é URL validada nem alvo de requisição.

Nada nesta entrega abre conexão de rede: o campo existe para distinguir
duas conexões do mesmo método, e é isso.
"""

_TERMINAL_SQL = "('revoked', 'unsupported')"


class ConnectionProfile(BaseModel):
    """Trinca `(principal, método, endpoint)` com estado próprio."""

    __tablename__ = "connection_profiles"

    __table_args__ = (
        UniqueConstraint(
            "id",
            "control_principal_ref",
            name="uq_connection_profiles_id_principal",
        ),
        CheckConstraint(
            "length(btrim(control_principal_ref)) > 0",
            name="ck_connection_profiles_principal_not_blank",
        ),
        CheckConstraint(
            "NOT (method = 'manual_handoff' AND endpoint_ref IS NOT NULL)",
            name="ck_connection_profiles_manual_has_no_endpoint",
        ),
        CheckConstraint(
            "state <> 'available' OR method = 'manual_handoff'",
            name="ck_connection_profiles_available_method",
        ),
        CheckConstraint(
            "method IN ('manual_handoff', 'provider_native_mcp_inbound', "
            "'direct_provider_api', 'provider_native_agent_bridge', "
            "'enterprise_gateway_or_broker', 'local_model_adapter', "
            "'browser_assisted_handoff', 'watched_inbox_outbox')",
            name="ck_connection_profiles_method_vocabulary",
        ),
        CheckConstraint(
            "state IN ('declared', 'preflight_required', 'implemented_pending_audit', "
            "'available', 'degraded', 'revoked', 'unsupported')",
            name="ck_connection_profiles_state_vocabulary",
        ),
        Index(
            "ix_connection_profiles_manual_singleton",
            "control_principal_ref",
            unique=True,
            postgresql_where=sa.text(f"method = 'manual_handoff' AND state NOT IN {_TERMINAL_SQL}"),
        ),
        Index(
            "ix_connection_profiles_non_terminal_triple",
            "control_principal_ref",
            "method",
            "endpoint_ref",
            unique=True,
            postgresql_where=sa.text(f"state NOT IN {_TERMINAL_SQL}"),
        ),
        Index("ix_connection_profiles_principal", "control_principal_ref"),
    )
    """Três garantias distintas, e nenhuma substitui a outra.

    ## `uq_connection_profiles_id_principal`

    AMPLIAÇÃO DECLARADA. Redundante em cardinalidade (`id` já é chave
    primária) e **obrigatória em referência**: é o alvo da chave
    estrangeira composta de `connection_execution_receipts`.

    ```text
    TWO_VALID_REFERENCES != ONE_COHERENT_REFERENCE
    ```

    Mesmo precedente de `uq_handoff_attempts_id_step_schedule` (E7.3) e
    de `uq_schedule_steps_id_schedule` (Chain111).

    ## `ix_connection_profiles_manual_singleton`

    Um perfil manual **não terminal** por principal. Parcial em duas
    dimensões: só o método manual, e só fora dos terminais. A trinca
    geral não cobre este caso porque `endpoint_ref` é `NULL` no manual, e
    `NULL` não colide com `NULL` num índice único — sem este segundo
    índice, dois perfis manuais entrariam pelo SQL bruto.

    ```text
    NULL_NÃO_COLIDE_COM_NULL
    ```

    ## `ck_connection_profiles_available_method`

    ```text
    ENUM_OR_REGISTRY != AVAILABLE
    ```

    O banco recusa `AVAILABLE` para qualquer método que não seja o
    manual. A regra existe em Python (`AVAILABLE_CONNECTION_METHODS`) e
    aqui, porque quem chega por SQL bruto não passa pelo serviço.
    """

    control_principal_ref: Mapped[str] = mapped_column(String(MAX_REF_LENGTH), nullable=False)
    """Referência opaca ao principal técnico. Nunca vem do corpo da requisição.

    ```text
    control_principal_ref = str(principal.id)
    OPAQUE_ID != SECRET_ID
    ```
    """

    method: Mapped[ConnectionMethod] = mapped_column(
        SAEnum(
            ConnectionMethod,
            name="connection_method",
            native_enum=False,
            length=40,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )

    endpoint_ref: Mapped[str | None] = mapped_column(String(MAX_ENDPOINT_REF_LENGTH), nullable=True)
    """`NULL` no manual, e isso é a verdade — não uma lacuna."""

    access_provider_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("connection_access_providers.id", name="fk_connection_profiles_access_provider"),
        nullable=True,
    )
    """Operador do endpoint. `NULL` no manual: não há operador algum."""

    state: Mapped[ConnectionState] = mapped_column(
        SAEnum(
            ConnectionState,
            name="connection_state",
            native_enum=False,
            length=32,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )

    credential_ref: Mapped[str | None] = mapped_column(String(MAX_REF_LENGTH), nullable=True)
    """Referência **opaca** a uma custódia externa que ainda não existe.

    ```text
    TOKEN_PASSTHROUGH = FORBIDDEN
    PROVIDER_CREDENTIAL NOT IN {perfil, envelope, prompt, log}
    ```
    """

    display_name: Mapped[str | None] = mapped_column(String(MAX_REF_LENGTH), nullable=True)
    """Nome amigável para a projeção da E8.

    ```text
    O nome bonito é da tela. O recibo continua guardando a atribuição exata.
    ```
    """
