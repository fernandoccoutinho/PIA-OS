"""
`ConnectionExecutionReceipt` — por onde uma execução concreta passou.

```text
PROFILE_DESCREVE_CONFIGURAÇÃO != RECIBO_DESCREVE_EXECUÇÃO
```

Um perfil muda de estado, é revogado, é substituído — e a execução de
ontem precisa continuar dizendo por onde passou. Por isso os seis campos
operacionais são **copiados no ato**, nunca derivados por join na
leitura: derivá-los faria um perfil alterado hoje reescrever a história
de uma execução antiga.

## Vínculo bilateral

```text
FK COMPOSTA (attempt_id, step_id, schedule_id)     -> handoff_attempts
FK COMPOSTA (connection_id, control_principal_ref) -> connection_profiles
UNIQUE (attempt_id)
CHECK  (model_attestation_level = 'attested') = (observed_model IS NOT NULL)
TWO_VALID_REFERENCES != ONE_COHERENT_REFERENCE
```

Uma FK **simples** para o perfil permitiria, por SQL bruto, ligar a
Attempt do principal A à conexão do principal B: cada referência seria
válida sozinha, e nenhuma provaria que as duas pertencem ao mesmo dono.
É exatamente o defeito que a Chain111 corrigiu em `handoff_attempts` e a
Chain112 corrigiu no binding de Schedule.

```text
COERÊNCIA SOBREVIVE FORA DOS SERVIÇOS
```

Append-only por trigger, no molde de `seal_receipts`: o recibo descreve
um ato instantâneo já terminado.
"""

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    String,
    UniqueConstraint,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.connections.models.catalog import MAX_RELEASE_ID_LENGTH, MAX_SLUG_LENGTH
from app.connections.models.connection_profile import MAX_REF_LENGTH
from app.connections.models.enums import ConnectionMethod, ModelAttestationLevel
from app.models.base_model import BaseModel


class ConnectionExecutionReceipt(BaseModel):
    """Um recibo por Attempt. Imutável."""

    __tablename__ = "connection_execution_receipts"

    __table_args__ = (
        UniqueConstraint("attempt_id", name="uq_connection_execution_receipts_attempt"),
        ForeignKeyConstraint(
            ["attempt_id", "step_id", "schedule_id"],
            [
                "handoff_attempts.id",
                "handoff_attempts.step_id",
                "handoff_attempts.schedule_id",
            ],
            name="fk_connection_execution_receipts_attempt",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["connection_id", "control_principal_ref", "connection_method"],
            [
                "connection_profiles.id",
                "connection_profiles.control_principal_ref",
                "connection_profiles.method",
            ],
            name="fk_connection_execution_receipts_connection_within_principal",
        ),
        CheckConstraint(
            "(model_attestation_level = 'attested') = (observed_model IS NOT NULL)",
            name="ck_connection_execution_receipts_attestation_bicondicional",
        ),
        CheckConstraint(
            "connection_method <> 'manual_handoff' OR ("
            "access_provider IS NULL AND requested_model IS NULL "
            "AND observed_model IS NULL AND model_attestation_level = 'unknown')",
            name="ck_connection_execution_receipts_manual_truth",
        ),
        CheckConstraint(
            "length(btrim(control_principal_ref)) > 0",
            name="ck_connection_execution_receipts_principal_not_blank",
        ),
        CheckConstraint(
            "connection_method IN ('manual_handoff', 'provider_native_mcp_inbound', "
            "'direct_provider_api', 'provider_native_agent_bridge', "
            "'enterprise_gateway_or_broker', 'local_model_adapter', "
            "'browser_assisted_handoff', 'watched_inbox_outbox')",
            name="ck_connection_execution_receipts_method_vocabulary",
        ),
        CheckConstraint(
            "model_attestation_level IN ('attested', 'self_declared', 'unknown')",
            name="ck_connection_execution_receipts_attestation_vocabulary",
        ),
        Index("ix_connection_execution_receipts_connection", "connection_id"),
        Index("ix_connection_execution_receipts_schedule", "schedule_id"),
    )
    """A FK da Attempt é `DEFERRABLE INITIALLY DEFERRED` pela mesma razão
    de `fk_service_delegations_consumed_attempt`: o recibo é escrito na
    mesma transação da Attempt e do `SealReceipt`, e uma FK imediata
    obrigaria a ordem de escrita a virar contrato implícito. Diferida, o
    commit só passa se a Attempt correspondente tiver sido criada.

    ```text
    1 Attempt = 1 ConnectionExecutionReceipt
    ```

    A bicondicional da atestação é o que impede `attested` de significar
    "achamos que foi": atestar exige ter observado.

    ## Corretivo R1 — rota, e não só dono

    ```text
    COHERENT_OWNER != COHERENT_ROUTE
    RECEIPT_METHOD == PROFILE_METHOD
    ```

    A FK passou a ser **ternária**: `connection_method` entra nela, e o
    alvo é `uq_connection_profiles_id_principal_method`. Sem isso, o
    recibo declarava livremente uma rota que o perfil não oferece — e o
    recibo é a única evidência da rota realmente usada.

    ## Corretivo R1 — a verdade do manual, imposta pelo banco

    ```text
    manual_handoff  =>  access_provider IS NULL
                        requested_model IS NULL
                        observed_model  IS NULL
                        atestação       = unknown
    ```

    A autoridade R3 fixa esses quatro valores para o manual, e antes
    apenas o value object recusava o operador. Por SQL bruto entrava um
    repasse manual com modelo fabricado e atestação `attested` — a
    atribuição inteira inventada, com a bicondicional satisfeita.
    """

    control_principal_ref: Mapped[str] = mapped_column(String(MAX_REF_LENGTH), nullable=False)
    """**Copiado**, nunca derivado por join na leitura.

    É ele que fecha o segundo vínculo; derivá-lo faria a coerência
    depender da consulta em vez do schema.
    """

    schedule_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(), nullable=False)
    step_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(), nullable=False)
    attempt_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(), nullable=False)
    connection_id: Mapped[uuid.UUID] = mapped_column(sa.Uuid(), nullable=False)

    connection_method: Mapped[ConnectionMethod] = mapped_column(
        SAEnum(
            ConnectionMethod,
            name="connection_method",
            native_enum=False,
            length=40,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    """Valor do enum **no momento da execução**, copiado.

    Se o perfil mudar de método amanhã, este recibo continua dizendo por
    onde a execução de hoje passou.
    """

    access_provider: Mapped[str | None] = mapped_column(String(MAX_SLUG_LENGTH), nullable=True)
    """Slug do operador, copiado. `NULL` no manual: não há operador."""

    requested_model: Mapped[str | None] = mapped_column(
        String(MAX_RELEASE_ID_LENGTH), nullable=True
    )
    """`NULL` quando não há modelo a solicitar — o caso do manual."""

    observed_model: Mapped[str | None] = mapped_column(String(MAX_RELEASE_ID_LENGTH), nullable=True)
    """Atestado pelo provedor. `NULL` quando a rota é opaca.

    ```text
    REQUESTED_MODEL != OBSERVED_MODEL
    GATEWAY_OPACO -> NULL, jamais um palpite
    ```
    """

    model_attestation_level: Mapped[ModelAttestationLevel] = mapped_column(
        SAEnum(
            ModelAttestationLevel,
            name="connection_model_attestation_level",
            native_enum=False,
            length=24,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )

    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    """Instante lido do relógio do PostgreSQL — precedente de `seal_receipts`."""
