"""
`ExecutionObservation` — observação sem enforcement fictício (`E7.3`).

```text
D10 = OBSERVED_ONLY
BUDGET_ENFORCEMENT = NOT_IMPLEMENTED
NO_SILENT_PROVIDER_SWITCH
SELF_DECLARED != VERIFIED_IDENTITY
```

Append-only, com **um produtor real**: quando duas tentativas da mesma
etapa declaram provedores diferentes, a importação grava a troca. Não há
campo genérico de custo ou valor — criar um sem produtor seria vocabulário
prometendo medição que ninguém faz.

Nenhum campo aceita prompt, resposta, transcrição ou contexto. O que fica
são identificadores declarados e referências tipadas; a guarda estática
mede os nomes de coluna.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
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
from app.orchestration.models.enums import ObservationKind
from app.orchestration.schemas.envelope import MAX_REF_LENGTH


class ExecutionObservation(BaseModel):
    """Registro imutável de uma troca declarada de provedor."""

    __tablename__ = "execution_observations"

    __table_args__ = (
        ForeignKeyConstraint(
            ["step_id", "schedule_id"],
            ["schedule_steps.id", "schedule_steps.schedule_id"],
            name="fk_execution_observations_step_within_schedule",
        ),
        ForeignKeyConstraint(
            ["previous_attempt_id", "step_id", "schedule_id"],
            ["handoff_attempts.id", "handoff_attempts.step_id", "handoff_attempts.schedule_id"],
            name="fk_execution_observations_previous_attempt",
        ),
        ForeignKeyConstraint(
            ["current_attempt_id", "step_id", "schedule_id"],
            ["handoff_attempts.id", "handoff_attempts.step_id", "handoff_attempts.schedule_id"],
            name="fk_execution_observations_current_attempt",
        ),
        CheckConstraint("self_declared", name="ck_execution_observations_self_declared_true"),
        CheckConstraint(
            "previous_attempt_id <> current_attempt_id",
            name="ck_execution_observations_distinct_attempts",
        ),
        CheckConstraint(
            "previous_declared_provider_id IS DISTINCT FROM current_declared_provider_id",
            name="ck_execution_observations_provider_actually_changed",
        ),
        CheckConstraint(
            "observation_kind IN ('declared_provider_switch')",
            name="ck_execution_observations_kind_vocabulary",
        ),
        Index("ix_execution_observations_step", "step_id"),
    )
    """As duas FKs compostas provam que **ambas** as tentativas pertencem à
    mesma etapa do mesmo Schedule.

    Uma observação que comparasse tentativas de trabalhos diferentes
    afirmaria uma troca de provedor que nunca ocorreu naquela etapa. E o
    `CHECK` de provedor distinto impede gravar "troca" quando nada trocou:
    um registro de mudança sem mudança é ruído que a auditoria futura vai
    tratar como sinal.
    """

    schedule_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("schedules.id", name="fk_execution_observations_schedule"), nullable=False
    )
    step_id: Mapped[uuid.UUID] = mapped_column(Uuid(), nullable=False)

    observation_kind: Mapped[ObservationKind] = mapped_column(
        SAEnum(
            ObservationKind,
            name="orchestration_observation_kind",
            native_enum=False,
            length=40,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )

    previous_attempt_id: Mapped[uuid.UUID] = mapped_column(Uuid(), nullable=False)
    current_attempt_id: Mapped[uuid.UUID] = mapped_column(Uuid(), nullable=False)

    previous_declared_provider_id: Mapped[str | None] = mapped_column(
        String(MAX_REF_LENGTH), nullable=True
    )
    current_declared_provider_id: Mapped[str | None] = mapped_column(
        String(MAX_REF_LENGTH), nullable=True
    )
    """Alegações, não identidade verificada. `NULL` é uma alegação válida:
    o cliente pode não declarar provedor, e omitir depois de ter declarado
    **é** uma troca."""

    self_declared: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
