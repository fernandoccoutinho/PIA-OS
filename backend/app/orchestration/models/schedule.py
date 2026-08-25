"""
`Schedule` — o trabalho governado (`E7.1`).

```text
SCHEDULE_CONTROL_BINDING = TECHNICAL_PRINCIPAL_REF
API_READ_WRITE_WITHOUT_CONTROL_BINDING = FORBIDDEN
SAME_SCOPE != SAME_WORK_OWNERSHIP
```

Todo Schedule nasce vinculado a um `control_principal_ref` (addendum §1).
O vínculo não é metadado de auditoria: é a chave de escopo de **toda**
leitura e mutação, imposta no repositório, e não numa camada acima que
alguém possa contornar chamando o repositório direto.
"""

from sqlalchemy import CheckConstraint, Index, String, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base_model import BaseModel
from app.orchestration.models.enums import HandoffMode, ScheduleState
from app.orchestration.schemas.envelope import MAX_REF_LENGTH, MAX_TITLE_LENGTH


class Schedule(BaseModel):
    """Composição de trabalho: título, modo de execução, estado e dono técnico."""

    __tablename__ = "schedules"

    __table_args__ = (
        CheckConstraint(
            "length(btrim(title)) > 0",
            name="ck_schedules_title_not_blank",
        ),
        CheckConstraint(
            "length(btrim(control_principal_ref)) > 0",
            name="ck_schedules_control_principal_not_blank",
        ),
        Index("ix_schedules_control_principal_ref", "control_principal_ref"),
        UniqueConstraint("id", "control_principal_ref", name="uq_schedules_id_principal"),
    )
    """Dois `CHECK`, um índice e o alvo composto de referência.

    O índice existe porque **toda** consulta filtra por
    `control_principal_ref`: sem ele, o escopo obrigatório seria um scan.
    Não há `UNIQUE` sobre título — dois trabalhos podem se chamar igual, e
    fundi-los apagaria a distinção entre eles.

    ## E7.4-1 B1a — `uq_schedules_id_principal`

    AMPLIAÇÃO DECLARADA, corretiva. Redundante em cardinalidade (`id` já é
    a chave primária) e obrigatória em referência: é o alvo da FK composta
    que o evento de proteção humana usa para provar, no banco, que o
    Schedule citado pertence àquele principal.

    ```text
    TWO_VALID_REFERENCES != ONE_COHERENT_REFERENCE
    ```

    Mesmo precedente de `uq_schedule_steps_id_schedule` (Chain111) e de
    `uq_handoff_attempts_id_step_schedule` (E7.3). Declarada aqui **e** na
    migration porque a guarda de drift compara o metadata com o schema
    real.
    """

    title: Mapped[str] = mapped_column(String(MAX_TITLE_LENGTH), nullable=False)

    state: Mapped[ScheduleState] = mapped_column(
        SAEnum(
            ScheduleState,
            name="orchestration_schedule_state",
            native_enum=False,
            length=16,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=ScheduleState.DRAFT,
    )
    """Ciclo de vida congelado no MAI §6, gravado pelo `.value`."""

    execution_mode: Mapped[HandoffMode] = mapped_column(
        SAEnum(
            HandoffMode,
            name="orchestration_handoff_mode",
            native_enum=False,
            length=40,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    """Eixo independente da composição (§4).

    O vocabulário é o do MAI inteiro; o escritor só aceita
    `MANUAL_HANDOFF` (`EXECUTABLE_HANDOFF_MODES`). Trocar de modo amanhã
    não reescreve a composição — é exatamente o que a separação dos eixos
    compra.
    """

    control_principal_ref: Mapped[str] = mapped_column(String(MAX_REF_LENGTH), nullable=False)
    """Referência **opaca** ao principal técnico (addendum §1).

    ```text
    REFERENCE != FOREIGN_KEY
    TECHNICAL_PRINCIPAL != HUMAN_IDENTITY
    ```

    Sem FK para `programmatic_service_principals` de propósito: o addendum
    diz "opaca", e uma FK acoplaria a E7 à tabela da E6.2, impedindo
    registrar trabalho cujo principal já foi revogado e removido. Custo
    declarado: não há integridade referencial ao principal.
    """
