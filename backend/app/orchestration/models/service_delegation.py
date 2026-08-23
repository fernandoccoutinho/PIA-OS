"""
`ServiceDelegation` — autorização técnica de despacho (`E7.3`).

```text
SERVICE_DELEGATION != HUMAN_APPROVAL
BOUND_BY = schedule_id + step_id + content_sha256 + scope + valid_until
CONSUMPTION = SINGLE_USE
CONTENT_HASH_CHANGED -> INVALID
TERMINAL -> ANY_OTHER_STATE = FORBIDDEN
```

O vínculo ao `content_sha256` é o que torna `CONTENT_HASH_CHANGED -> INVALID`
**estrutural** em vez de verificado: a delegação simplesmente não casa com
o novo hash, e não há caminho em que alguém precise lembrar de conferir.

Esta é a única tabela da E7.3 que **não** é append-only, e a razão é a
mesma que separou `handoff_attempts` de `seal_receipts` na E7.1: a
delegação tem ciclo de vida, enquanto evento, observação e parecer
descrevem atos instantâneos já terminados. Um trigger de UPDATE aqui
impediria o próprio consumo.

Não ser append-only não é ser descartável. `DELETE` e `TRUNCATE` são
recusados, o vínculo é imutável e só as transições monotônicas passam —
tudo imposto por trigger, porque SQL bruto não passa pelo repositório.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Uuid,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import text as sa_text

from app.models.base_model import BaseModel
from app.orchestration.models.attempt import SHA256_HEX_LENGTH
from app.orchestration.models.enums import DelegationState
from app.orchestration.schemas.envelope import MAX_REF_LENGTH

MAX_SCOPE_LENGTH = 32


class ServiceDelegation(BaseModel):
    """Autorização de despacho, de uso único e ligada ao conteúdo."""

    __tablename__ = "service_delegations"

    __table_args__ = (
        ForeignKeyConstraint(
            ["step_id", "schedule_id"],
            ["schedule_steps.id", "schedule_steps.schedule_id"],
            name="fk_service_delegations_step_within_schedule",
        ),
        ForeignKeyConstraint(
            ["consumed_by_attempt_id", "step_id", "schedule_id"],
            [
                "handoff_attempts.id",
                "handoff_attempts.step_id",
                "handoff_attempts.schedule_id",
            ],
            name="fk_service_delegations_consumed_attempt",
            deferrable=True,
            initially="DEFERRED",
        ),
        CheckConstraint(
            f"length(content_sha256) = {SHA256_HEX_LENGTH}",
            name="ck_service_delegations_content_sha256_length",
        ),
        CheckConstraint(
            "length(btrim(granted_by_principal_ref)) > 0",
            name="ck_service_delegations_granted_by_not_blank",
        ),
        CheckConstraint(
            "(state = 'consumed') = (consumed_at IS NOT NULL)",
            name="ck_service_delegations_consumed_at_coherent",
        ),
        CheckConstraint(
            "(state = 'consumed') = (consumed_by_attempt_id IS NOT NULL)",
            name="ck_service_delegations_consumed_attempt_coherent",
        ),
        Index(
            "ix_service_delegations_single_active",
            "schedule_id",
            "step_id",
            "scope",
            unique=True,
            postgresql_where=sa_text("state = 'active'"),
        ),
        CheckConstraint(
            "state IN ('active', 'consumed', 'revoked', 'expired')",
            name="ck_service_delegations_state_vocabulary",
        ),
        CheckConstraint("scope IN ('dispatch')", name="ck_service_delegations_scope_vocabulary"),
        Index("ix_service_delegations_step", "step_id"),
    )
    """A FK do consumo é **composta e diferida**, e as duas coisas importam.

    Composta porque `(attempt_id, step_id, schedule_id)` precisa ser
    coerente: duas referências válidas isoladamente não provam que a
    tentativa consumida pertence àquela etapa daquele trabalho — a lição
    que exigiu a Chain111.

    `DEFERRABLE INITIALLY DEFERRED` porque o consumo é gravado **antes**
    de `seal_step_for_export()` criar a Attempt, na mesma transação. Uma
    FK imediata falharia no `UPDATE`; omiti-la repetiria o defeito de
    coerência. Diferida, o commit só passa se a Attempt correspondente
    tiver sido de fato criada.

    ```text
    ONE_ACTIVE_PER (schedule_id, step_id, scope)
    ```

    O índice parcial é por trinca, e não só por `step_id`: uma delegação
    vencida ou ligada a hash antigo precisa dar lugar a outra, e a
    unicidade por etapa sozinha aprisionaria a Step.
    """

    schedule_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("schedules.id", name="fk_service_delegations_schedule"), nullable=False
    )
    step_id: Mapped[uuid.UUID] = mapped_column(Uuid(), nullable=False)

    content_sha256: Mapped[str] = mapped_column(String(SHA256_HEX_LENGTH), nullable=False)
    """Hash do envelope no instante da concessão. **Imutável.**"""

    scope: Mapped[str] = mapped_column(String(MAX_SCOPE_LENGTH), nullable=False)
    """`dispatch`. Enum fechado, derivado pelo servidor, nunca do corpo."""

    granted_by_principal_ref: Mapped[str] = mapped_column(String(MAX_REF_LENGTH), nullable=False)
    """Principal técnico que concedeu. Derivado do token.

    ```text
    TECHNICAL_PRINCIPAL != HUMAN_IDENTITY
    ```
    """

    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    state: Mapped[DelegationState] = mapped_column(
        SAEnum(
            DelegationState,
            name="orchestration_delegation_state",
            native_enum=False,
            length=16,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=DelegationState.ACTIVE,
    )

    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    consumed_by_attempt_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(), nullable=True)
