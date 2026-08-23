"""
`HandoffAttempt` — uma tentativa de repasse.

```text
SAME_CONTENT_SHA256 MAY_HAVE MULTIPLE_ATTEMPTS
RETRY -> NEW_COMMAND_KEY -> NEW_ATTEMPT
```

A tentativa é o que separa identidade de **conteúdo** de identidade de
**execução**. Duas tentativas do mesmo conteúdo são dois fatos: o mesmo
`content_sha256` aparece nas duas, e cada uma tem o seu recibo.

A tabela **não** é append-only, e a diferença em relação a `seal_receipts`
é deliberada: o estado da tentativa fecha quando um retorno chega (E7.2),
enquanto o recibo descreve um ato instantâneo que já terminou.
"""

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base_model import BaseModel
from app.orchestration.models.enums import AttemptState
from app.orchestration.schemas.envelope import MAX_ENVELOPE_VERSION_LENGTH

SHA256_HEX_LENGTH = 64


class HandoffAttempt(BaseModel):
    """Tentativa aberta pelo `HandoffService` no ato do selamento."""

    __tablename__ = "handoff_attempts"

    __table_args__ = (
        UniqueConstraint("step_id", "attempt_number", name="uq_handoff_attempts_step_number"),
        CheckConstraint("attempt_number >= 1", name="ck_handoff_attempts_number_positive"),
        CheckConstraint(
            f"length(content_sha256) = {SHA256_HEX_LENGTH}",
            name="ck_handoff_attempts_content_sha256_length",
        ),
        CheckConstraint(
            "length(btrim(envelope_version)) > 0",
            name="ck_handoff_attempts_envelope_version_not_blank",
        ),
        Index("ix_handoff_attempts_schedule", "schedule_id"),
        Index("ix_handoff_attempts_content_sha256", "content_sha256"),
    )
    """`(step_id, attempt_number)` único é o que dá ordem legível às
    tentativas; o índice por `content_sha256` é o que torna barato
    responder "quantas tentativas houve deste conteúdo".

    O formato hexadecimal do hash é verificado por regex na migration —
    `~` é PostgreSQL, e o metadata precisa criar tabela em qualquer
    dialeto. Aqui fica o comprimento, que é portátil.
    """

    schedule_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("schedules.id", name="fk_handoff_attempts_schedule"), nullable=False
    )
    """Redundante com `step.schedule_id`, e de propósito: toda consulta é
    escopada por `schedule_id` (§17), e depender do join para aplicar o
    escopo deixaria a garantia à mercê de quem escrever a próxima query.
    """

    step_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("schedule_steps.id", name="fk_handoff_attempts_step"), nullable=False
    )

    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)

    envelope_version: Mapped[str] = mapped_column(
        String(MAX_ENVELOPE_VERSION_LENGTH), nullable=False
    )
    """Versão do contrato que produziu este hash — insumo, não carimbo."""

    content_sha256: Mapped[str] = mapped_column(String(SHA256_HEX_LENGTH), nullable=False)

    state: Mapped[AttemptState] = mapped_column(
        SAEnum(
            AttemptState,
            name="orchestration_attempt_state",
            native_enum=False,
            length=24,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=AttemptState.OPEN,
    )
