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

import sqlalchemy as sa
from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
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
        ForeignKeyConstraint(
            ["step_id", "schedule_id"],
            ["schedule_steps.id", "schedule_steps.schedule_id"],
            name="fk_handoff_attempts_step_within_schedule",
        ),
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
        UniqueConstraint(
            "id", "step_id", "schedule_id", name="uq_handoff_attempts_id_step_schedule"
        ),
        Index(
            "ix_handoff_attempts_single_open",
            "step_id",
            unique=True,
            postgresql_where=sa.text("state = 'open'"),
        ),
    )
    """`(step_id, attempt_number)` único é o que dá ordem legível às
    tentativas; o índice por `content_sha256` é o que torna barato
    responder "quantas tentativas houve deste conteúdo".

    O formato hexadecimal do hash é verificado por regex na migration —
    `~` é PostgreSQL, e o metadata precisa criar tabela em qualquer
    dialeto. Aqui fica o comprimento, que é portátil.

    ## E7.2 — `ix_handoff_attempts_single_open`

    Índice **parcial** único: no máximo uma tentativa `OPEN` por etapa.

    ```text
    APPLICATION_CHECK != DATABASE_GUARANTEE
    ```

    O serviço também verifica sob `FOR UPDATE`, e as duas coisas não são
    redundantes: o lock serializa quem passa pelo serviço, o índice recusa
    quem chegar por SQL bruto ou por um caminho que ainda não existe.

    Parcial, e não total, porque tentativas fechadas se acumulam por
    design — o histórico de retries é o produto, não lixo.

    ## E7.3 — `uq_handoff_attempts_id_step_schedule`

    AMPLIAÇÃO DECLARADA. Redundante em cardinalidade (`id` já é a chave
    primária) e obrigatória em referência: é o alvo das chaves
    estrangeiras compostas que `service_delegations` e
    `execution_observations` usam para provar, no banco, que a tentativa
    citada pertence àquela etapa daquele Schedule.

    ```text
    TWO_VALID_REFERENCES != ONE_COHERENT_REFERENCE
    ```

    Mesmo precedente de `uq_schedule_steps_id_schedule` (Chain111).

    Declarado aqui **e** na migration porque a guarda de drift compara o
    metadata com o schema real; declarar só na migration faria o índice
    parecer deriva a cada execução do gate.
    """

    schedule_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("schedules.id", name="fk_handoff_attempts_schedule"), nullable=False
    )
    """Redundante com `step.schedule_id`, e de propósito: toda consulta é
    escopada por `schedule_id` (§17), e depender do join para aplicar o
    escopo deixaria a garantia à mercê de quem escrever a próxima query.

    ```text
    TWO_VALID_REFERENCES != ONE_COHERENT_REFERENCE
    ```

    Corretivo R1: a redundância só é segura se as duas referências forem
    **coerentes**. A chave estrangeira composta
    `fk_handoff_attempts_step_within_schedule` recusa no banco a
    combinação `Schedule A + Step B`, que a Chain110 aceitava porque cada
    FK era válida isoladamente.
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
