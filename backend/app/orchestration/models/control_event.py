"""
`OrchestrationControlEvent` — evidência imutável de controle (`E7.3`).

```text
D9 = COOPERATIVE
NO_HARD_CANCEL | NO_WORKER | NO_TIMEOUT
```

Append-only. Pausa, retomada, parada, cancelamento e conclusão deixam
aqui o seu registro, com vocabulário fechado e **sem texto livre** —
texto livre num registro de controle vira o lugar onde alguém escreve o
que não coube em nenhum campo, inclusive conteúdo bruto.

Separado de `ExecutionObservation` de propósito: observação é
`OBSERVED_ONLY`; evento de controle é evidência de *enforcement*. Fundir
os dois faria um registro sem consequência e um com consequência morarem
no mesmo lugar, e a leitura futura não saberia distinguir.

**Não contém `attempt_id`.** O fechamento das tentativas no cancelamento
é consequência consultável — as Attempts ficam `CLOSED_CANCELLED` e podem
ser lidas — e não uma segunda lista gravada dentro do evento, que
poderia divergir da primeira.
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

from app.models.base_model import BaseModel
from app.orchestration.models.enums import (
    ControlEventKind,
    ControlReasonCode,
    StopConditionCategory,
)
from app.orchestration.schemas.envelope import MAX_REF_LENGTH


class OrchestrationControlEvent(BaseModel):
    """Um ato de controle, registrado para sempre."""

    __tablename__ = "orchestration_control_events"

    __table_args__ = (
        ForeignKeyConstraint(
            ["step_id", "schedule_id"],
            ["schedule_steps.id", "schedule_steps.schedule_id"],
            name="fk_control_events_step_within_schedule",
        ),
        CheckConstraint(
            "(reason_code = 'stop_condition_declared') = (stop_condition_category IS NOT NULL)",
            name="ck_control_events_stop_category_matrix",
        ),
        CheckConstraint(
            "length(btrim(declared_by_principal_ref)) > 0",
            name="ck_control_events_principal_not_blank",
        ),
        Index("ix_control_events_schedule", "schedule_id"),
    )
    """A matriz categoria×motivo é imposta por `CHECK`, nos dois sentidos.

    Categoria presente sem `stop_condition_declared` seria uma
    justificativa sem pergunta; `stop_condition_declared` sem categoria
    seria uma Stop Condition que ninguém consegue classificar depois.
    """

    schedule_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("schedules.id", name="fk_control_events_schedule"), nullable=False
    )
    step_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(), nullable=True)
    """Quando presente, a FK composta prova que a etapa é deste Schedule."""

    event_kind: Mapped[ControlEventKind] = mapped_column(
        SAEnum(
            ControlEventKind,
            name="orchestration_control_event_kind",
            native_enum=False,
            length=16,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    reason_code: Mapped[ControlReasonCode] = mapped_column(
        SAEnum(
            ControlReasonCode,
            name="orchestration_control_reason_code",
            native_enum=False,
            length=40,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    stop_condition_category: Mapped[StopConditionCategory | None] = mapped_column(
        SAEnum(
            StopConditionCategory,
            name="orchestration_stop_condition_category",
            native_enum=False,
            length=40,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=True,
    )
    declared_by_principal_ref: Mapped[str] = mapped_column(String(MAX_REF_LENGTH), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
