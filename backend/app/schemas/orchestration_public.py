"""
DTOs públicos da orquestração (`E7.2`).

```text
PUBLIC_DTO != ORM_MODEL
INPUT_NEVER_CARRIES = principal, papel, autoridade, proveniência, credencial
RESPONSE_NEVER_ECHOES = conteúdo bruto, control_principal_ref, segredo
```

Os DTOs de entrada omitem deliberadamente tudo o que o servidor deriva.
Um campo aceito é um campo que alguém pode mentir: `control_principal_ref`
e `sealer_ref` vêm de `str(principal.id)`, `role` vem da etapa, e
`provenance_record_ref` não existe na entrada porque a E7 não a escreve.

Os DTOs de saída nunca ecoam `content`. O retorno de uma IA entra para ser
medido e sai; o que a API devolve é hash, tamanho, media type e códigos.
"""

import uuid
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.orchestration.models.enums import (
    AttemptState,
    AuditOpinionKind,
    AuditReasonCode,
    ControlEventKind,
    ControlReasonCode,
    DelegationState,
    HandoffMode,
    HandoffResultStatus,
    ObservationKind,
    ScheduleState,
    StepState,
    StopConditionCategory,
)
from app.orchestration.schemas.output_contract import (
    OUTPUT_JSON_OBJECT_V1,
    OUTPUT_NON_EMPTY_TEXT_V1,
)

_CONTRATOS = (OUTPUT_NON_EMPTY_TEXT_V1, OUTPUT_JSON_OBJECT_V1)

MAX_COMMAND_KEY = 255
MAX_TITLE = 200
MAX_ROLE = 64
MAX_REF = 255
MAX_URI = 1024


class _Congelado(BaseModel):
    """Base imutável e sem campos extras.

    `extra="forbid"` é a diferença entre ignorar um campo desconhecido e
    recusá-lo: ignorar faria um cliente que tenta enviar
    `control_principal_ref` receber 201 e acreditar que funcionou.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")


# --- entrada ---------------------------------------------------------------


class ContextRefInput(_Congelado):
    uri: str = Field(min_length=1, max_length=MAX_URI)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    bytes: int = Field(ge=0)


class StepInput(_Congelado):
    role: str = Field(min_length=1, max_length=MAX_ROLE)
    instruction_ref: str = Field(min_length=1, max_length=MAX_REF)
    expected_output_contract: str = Field(description="Um dos dois contratos fechados da E7.2.")
    context_refs: tuple[ContextRefInput, ...] = ()
    constraints: dict[str, str] = Field(default_factory=dict)

    def contrato_suportado(self) -> bool:
        return self.expected_output_contract in _CONTRATOS


class CreateScheduleRequest(_Congelado):
    """Cria e **ativa** atomicamente.

    Não existe rota de ativação: um Schedule `DRAFT` acessível por API
    seria um recurso público que não entrega valor e que precisaria de um
    segundo passo para virar útil.
    """

    command_key: str = Field(min_length=1, max_length=MAX_COMMAND_KEY)
    title: str = Field(min_length=1, max_length=MAX_TITLE)
    execution_mode: HandoffMode = HandoffMode.MANUAL_HANDOFF
    steps: tuple[StepInput, ...] = Field(min_length=1)


class ExportHandoffRequest(_Congelado):
    """Só a chave. `sealer_ref` é derivado do principal autenticado."""

    command_key: str = Field(min_length=1, max_length=MAX_COMMAND_KEY)


class ReturnOutputInput(_Congelado):
    media_type: str = Field(min_length=1, max_length=64)
    content: str = Field(description="Conteúdo transitório. Não é persistido nem reexibido.")
    declared_output_ref: str | None = Field(default=None, max_length=MAX_URI)


class ReturnAttributionInput(_Congelado):
    """Alegação sobre a IA. `role` não entra: é derivado da etapa."""

    declared_instance_id: str = Field(min_length=1, max_length=MAX_REF)
    declared_provider_id: str | None = Field(default=None, max_length=MAX_REF)
    declared_model_id: str | None = Field(default=None, max_length=MAX_REF)


class ImportReturnRequest(_Congelado):
    command_key: str = Field(min_length=1, max_length=MAX_COMMAND_KEY)
    attempt_id: uuid.UUID
    output: ReturnOutputInput
    attribution: ReturnAttributionInput


# --- saída -----------------------------------------------------------------


class ContextRefView(_Congelado):
    uri: str
    sha256: str
    bytes: int


class StepView(_Congelado):
    step_id: uuid.UUID
    position: int
    role: str
    instruction_ref: str
    expected_output_contract: str
    context_refs: tuple[ContextRefView, ...]
    constraints: dict[str, str]
    state: StepState


class ScheduleView(_Congelado):
    """Sem `control_principal_ref`: quem pergunta já é o dono."""

    schedule_id: uuid.UUID
    title: str
    state: ScheduleState
    execution_mode: HandoffMode
    steps: tuple[StepView, ...]


class EnvelopeView(_Congelado):
    """Os oito campos congelados do MAI §3 — só referências, nada inline."""

    envelope_version: str
    schedule_id: uuid.UUID
    step_id: uuid.UUID
    role: str
    instruction_ref: str
    context_refs: tuple[ContextRefView, ...]
    expected_output_contract: str
    constraints: dict[str, str]


class ExportHandoffResponse(_Congelado):
    schedule_id: uuid.UUID
    step_id: uuid.UUID
    attempt_id: uuid.UUID
    attempt_number: int
    receipt_id: uuid.UUID
    content_sha256: str
    sealed_at: datetime
    replayed: bool
    step_state: StepState
    attempt_state: AttemptState
    envelope: EnvelopeView


class AttributionView(_Congelado):
    declared_provider_id: str | None
    declared_model_id: str | None
    declared_instance_id: str
    role: str
    declared_at: datetime
    self_declared: bool
    provenance_record_ref: uuid.UUID | None = None


class ResultView(_Congelado):
    """Veredito. Nunca traz `content`."""

    status: HandoffResultStatus
    expected_output_contract: str
    output_media_type: str
    output_sha256: str
    output_bytes: int
    declared_output_ref: str | None
    validation_codes: tuple[str, ...]


class ImportReturnResponse(_Congelado):
    schedule_id: uuid.UUID
    step_id: uuid.UUID
    attempt_id: uuid.UUID
    replayed: bool
    step_state: StepState
    attempt_state: AttemptState
    result: ResultView
    attribution: AttributionView


class AttemptView(_Congelado):
    attempt_id: uuid.UUID
    step_id: uuid.UUID
    attempt_number: int
    envelope_version: str
    content_sha256: str
    state: AttemptState
    created_at: datetime
    result: ResultView | None = None
    attribution: AttributionView | None = None


class AttemptListResponse(_Congelado):
    schedule_id: uuid.UUID
    attempts: tuple[AttemptView, ...]


# --- E7.3: governança ------------------------------------------------------


class GrantDelegationRequest(_Congelado):
    """Só chave e validade. Hash, escopo e concedente são derivados.

    ```text
    SERVER_DERIVES_WHAT_THE_CLIENT_COULD_LIE_ABOUT
    ```
    """

    command_key: str = Field(min_length=1, max_length=MAX_COMMAND_KEY)
    valid_until: datetime


class RevokeDelegationRequest(_Congelado):
    command_key: str = Field(min_length=1, max_length=MAX_COMMAND_KEY)


class ControlEventRequest(_Congelado):
    """`pause | resume | stop | cancel`; categoria fechada só em `stop`."""

    command_key: str = Field(min_length=1, max_length=MAX_COMMAND_KEY)
    action: Literal["pause", "resume", "stop", "cancel"]
    stop_condition_category: StopConditionCategory | None = None


class AuditOpinionRequest(_Congelado):
    """`PASS_FINAL` não é representável: o tipo não admite o valor."""

    command_key: str = Field(min_length=1, max_length=MAX_COMMAND_KEY)
    opinion: AuditOpinionKind
    reason_codes: tuple[AuditReasonCode, ...] = Field(min_length=1)
    auditor_execution_ref: str = Field(min_length=1, max_length=MAX_REF)


class DelegationView(_Congelado):
    delegation_id: uuid.UUID
    step_id: uuid.UUID
    content_sha256: str
    scope: str
    state: DelegationState
    valid_until: datetime
    consumed_at: datetime | None = None
    consumed_by_attempt_id: uuid.UUID | None = None


class ControlEventView(_Congelado):
    event_id: uuid.UUID
    step_id: uuid.UUID | None
    event_kind: ControlEventKind
    reason_code: ControlReasonCode
    stop_condition_category: StopConditionCategory | None
    occurred_at: datetime


class ControlEventResponse(_Congelado):
    schedule_id: uuid.UUID
    schedule_state: ScheduleState
    replayed: bool
    cancelled_steps: int
    closed_attempts: int
    event: ControlEventView


class ObservationView(_Congelado):
    observation_id: uuid.UUID
    step_id: uuid.UUID
    observation_kind: ObservationKind
    previous_attempt_id: uuid.UUID
    current_attempt_id: uuid.UUID
    previous_declared_provider_id: str | None
    current_declared_provider_id: str | None
    self_declared: bool
    observed_at: datetime


class AuditOpinionView(_Congelado):
    opinion_id: uuid.UUID
    handoff_result_id: uuid.UUID
    opinion: AuditOpinionKind
    reason_codes: tuple[str, ...]
    auditor_execution_ref: str
    issued_at: datetime


class GrantDelegationResponse(_Congelado):
    replayed: bool
    delegation: DelegationView


class AuditOpinionResponse(_Congelado):
    replayed: bool
    opinion: AuditOpinionView


class GovernanceView(_Congelado):
    """Nunca conteúdo bruto, credencial ou principal de controle."""

    schedule_id: uuid.UUID
    schedule_state: ScheduleState
    delegations: tuple[DelegationView, ...]
    control_events: tuple[ControlEventView, ...]
    observations: tuple[ObservationView, ...]
    audit_opinions: tuple[AuditOpinionView, ...]
