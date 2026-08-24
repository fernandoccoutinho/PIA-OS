"""
`OrchestrationQueryService` — a fronteira **pública** de leitura da E7.

```text
ROUTER_PODE_LER_REPOSITORIO != MCP_PODE_LER_REPOSITORIO
NENHUMA INSTÂNCIA ORM CRUZA ESTA FRONTEIRA
```

## Por que este serviço existe

Medição da Chain117: `app/routers/orchestration.py` fazia **nove**
chamadas diretas ao repositório (linhas 444, 447, 452, 605, 608, 839,
845, 851 e 857) para montar `attempts.list` e `governance.read`. Isso é
aceitável enquanto o router é código de transporte do próprio PIA;
expor as mesmas leituras por MCP daria ao boundary um caminho que passa
**ao lado** dos serviços.

A E7.4-1 cria o serviço antes de qualquer tool existir, e não depois —
criar a fronteira junto com o primeiro consumidor externo é como se
descobre, tarde, que ela tinha um furo.

## O que o serviço nunca devolve

```text
conteúdo bruto · credencial · control_principal_ref · segredo
```

`control_principal_ref` é **argumento**, nunca campo de retorno: ele
entra para escopar a consulta e não sai para ninguém.

Todo retorno é dataclass congelada, com as colunas extraídas **dentro**
da sessão — lição reincidente do programa desde a E4.5.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from app.orchestration.models.enums import (
    AttemptState,
    AuditOpinionKind,
    ControlEventKind,
    ControlReasonCode,
    DelegationState,
    HandoffResultStatus,
    ObservationKind,
    ScheduleState,
    StepState,
)
from app.orchestration.repositories.orchestration_repository import OrchestrationRepository
from app.orchestration.schemas.envelope import ConstraintPairs, ContextRef
from app.orchestration.services.schedule_service import ScheduleService


@dataclass(frozen=True)
class ResultProjection:
    """Veredito sobre um retorno. Hash e tamanho, nunca o conteúdo.

    ```text
    RAW_OUTPUT_IN_DATABASE = FORBIDDEN
    ```
    """

    status: HandoffResultStatus
    expected_output_contract: str
    output_media_type: str
    output_sha256: str
    output_bytes: int
    declared_output_ref: str | None
    validation_codes: tuple[str, ...]


@dataclass(frozen=True)
class AttributionProjection:
    """O que a IA **declarou** sobre si. `self_declared` é o que ele é.

    ```text
    SELF_DECLARED != VERIFIED
    ```
    """

    declared_provider_id: str | None
    declared_model_id: str | None
    declared_instance_id: str | None
    role: str | None
    declared_at: datetime | None
    self_declared: bool
    provenance_record_ref: str | None


@dataclass(frozen=True)
class AttemptProjection:
    """Uma tentativa, com veredito e atribuição quando existirem."""

    attempt_id: uuid.UUID
    step_id: uuid.UUID
    attempt_number: int
    envelope_version: str
    content_sha256: str
    state: AttemptState
    created_at: datetime
    result: ResultProjection | None
    attribution: AttributionProjection | None


@dataclass(frozen=True)
class DelegationProjection:
    """Delegação técnica, com o vínculo de conteúdo visível."""

    delegation_id: uuid.UUID
    step_id: uuid.UUID
    content_sha256: str
    scope: str
    state: DelegationState
    valid_until: datetime
    consumed_at: datetime | None
    consumed_by_attempt_id: uuid.UUID | None


@dataclass(frozen=True)
class ControlEventProjection:
    """Evento de controle. Motivo tipado, sem texto livre."""

    event_id: uuid.UUID
    step_id: uuid.UUID | None
    event_kind: ControlEventKind
    reason_code: ControlReasonCode
    stop_condition_category: str | None
    occurred_at: datetime


@dataclass(frozen=True)
class ObservationProjection:
    """Observação de execução. `D10 = OBSERVED_ONLY`."""

    observation_id: uuid.UUID
    step_id: uuid.UUID
    observation_kind: ObservationKind
    previous_attempt_id: uuid.UUID
    current_attempt_id: uuid.UUID
    previous_declared_provider_id: str | None
    current_declared_provider_id: str | None
    self_declared: bool
    observed_at: datetime


@dataclass(frozen=True)
class AuditOpinionProjection:
    """Parecer de execução. `AI_SELF_PASS_FINAL = FORBIDDEN`."""

    opinion_id: uuid.UUID
    handoff_result_id: uuid.UUID
    opinion: AuditOpinionKind
    reason_codes: tuple[str, ...]
    auditor_execution_ref: str
    issued_at: datetime


@dataclass(frozen=True)
class GovernanceProjection:
    """Tudo que a governança de um Schedule expõe, de uma vez."""

    schedule_id: uuid.UUID
    schedule_state: ScheduleState
    delegations: tuple[DelegationProjection, ...]
    control_events: tuple[ControlEventProjection, ...]
    observations: tuple[ObservationProjection, ...]
    audit_opinions: tuple[AuditOpinionProjection, ...]


@dataclass(frozen=True)
class SealReceiptProjection:
    """O ato de selar. `SEALED_AT_IN_CONTENT_HASH = FALSE`."""

    receipt_id: uuid.UUID
    attempt_id: uuid.UUID
    content_sha256: str
    sealed_at: datetime


@dataclass(frozen=True)
class StepProjection:
    """Uma etapa: identidade, estado e as **referências** do envelope.

    ```text
    REFERÊNCIA COM HASH != CONTEÚDO BRUTO
    ```

    `instruction_ref` e `context_refs` são referências com hash e
    tamanho — nunca o texto. É a mesma disciplina que a E7.2 já impunha
    ao envelope, e é o que permite reconstruir a resposta de um replay a
    partir do que está persistido, sem guardar conteúdo.
    """

    step_id: uuid.UUID
    position: int
    role: str
    state: StepState
    instruction_ref: str
    context_refs: tuple[ContextRef, ...]
    expected_output_contract: str
    constraints: ConstraintPairs


class OrchestrationQueryService:
    """Leitura pública e escopada. Único caminho para consumidores externos."""

    def __init__(self, repository: OrchestrationRepository) -> None:
        self._repository = repository
        self._schedules = ScheduleService(repository)

    def list_attempts(
        self, *, control_principal_ref: str, schedule_id: uuid.UUID
    ) -> tuple[AttemptProjection, ...]:
        """Tentativas do Schedule, com veredito e atribuição.

        A leitura do Schedule vem **primeiro** e levanta escopo antes de
        listar qualquer coisa: sem ela, um `schedule_id` alheio devolveria
        lista vazia, e "vazio" e "não é seu" ficariam indistinguíveis.
        """
        self._schedules.get_schedule(
            control_principal_ref=control_principal_ref, schedule_id=schedule_id
        )
        projecoes: list[AttemptProjection] = []
        for tentativa in self._repository.list_attempts(
            control_principal_ref=control_principal_ref, schedule_id=schedule_id
        ):
            resultado = self._repository.get_handoff_result(
                control_principal_ref=control_principal_ref,
                schedule_id=schedule_id,
                attempt_id=tentativa.id,
            )
            atribuicao = self._repository.get_handoff_attribution(
                control_principal_ref=control_principal_ref,
                schedule_id=schedule_id,
                attempt_id=tentativa.id,
            )
            projecoes.append(
                AttemptProjection(
                    attempt_id=tentativa.id,
                    step_id=tentativa.step_id,
                    attempt_number=tentativa.attempt_number,
                    envelope_version=tentativa.envelope_version,
                    content_sha256=tentativa.content_sha256,
                    state=tentativa.state,
                    created_at=tentativa.created_at,
                    result=None if resultado is None else _projetar_resultado(resultado),
                    attribution=(None if atribuicao is None else _projetar_atribuicao(atribuicao)),
                )
            )
        return tuple(projecoes)

    def get_attempt_outcome(
        self,
        *,
        control_principal_ref: str,
        schedule_id: uuid.UUID,
        step_id: uuid.UUID,
        attempt_id: uuid.UUID,
    ) -> tuple[ResultProjection | None, AttributionProjection | None, StepProjection | None]:
        """Veredito, atribuição e etapa de uma tentativa, numa leitura só.

        Devolver os três juntos é o que evita o chamador remontá-los com
        três chamadas ao repositório — que é exatamente o bypass que este
        serviço existe para fechar.
        """
        resultado = self._repository.get_handoff_result(
            control_principal_ref=control_principal_ref,
            schedule_id=schedule_id,
            attempt_id=attempt_id,
        )
        atribuicao = self._repository.get_handoff_attribution(
            control_principal_ref=control_principal_ref,
            schedule_id=schedule_id,
            attempt_id=attempt_id,
        )
        etapa = self._repository.get_step(
            control_principal_ref=control_principal_ref,
            schedule_id=schedule_id,
            step_id=step_id,
        )
        return (
            None if resultado is None else _projetar_resultado(resultado),
            None if atribuicao is None else _projetar_atribuicao(atribuicao),
            None if etapa is None else _projetar_etapa(etapa),
        )

    def get_attempt(
        self, *, control_principal_ref: str, schedule_id: uuid.UUID, attempt_id: uuid.UUID
    ) -> AttemptProjection | None:
        """Uma tentativa, escopada pelas condições do chamador."""
        tentativa = self._repository.get_attempt(
            control_principal_ref=control_principal_ref,
            schedule_id=schedule_id,
            attempt_id=attempt_id,
        )
        if tentativa is None:
            return None
        return AttemptProjection(
            attempt_id=tentativa.id,
            step_id=tentativa.step_id,
            attempt_number=tentativa.attempt_number,
            envelope_version=tentativa.envelope_version,
            content_sha256=tentativa.content_sha256,
            state=tentativa.state,
            created_at=tentativa.created_at,
            result=None,
            attribution=None,
        )

    def get_export_replay_context(
        self,
        *,
        control_principal_ref: str,
        schedule_id: uuid.UUID,
        step_id: uuid.UUID,
        attempt_id: uuid.UUID,
    ) -> tuple[AttemptProjection | None, SealReceiptProjection | None, StepProjection | None]:
        """Tentativa, recibo de selamento e etapa — para reconstruir um replay.

        ```text
        REPLAY_RESPONSE = PERSISTED_TRUTH
        ```

        Os três numa leitura só, pela mesma razão de
        `get_attempt_outcome`: devolvê-los separadamente devolveria ao
        chamador o trabalho de remontá-los pelo repositório, que é o
        bypass que este serviço fecha.

        A coerência tentativa↔etapa **não** é verificada aqui: quem
        decide o que fazer com uma `command_key` reutilizada noutro path
        é o chamador, e embutir a decisão numa leitura faria um serviço
        de consulta emitir política.
        """
        tentativa = self._repository.get_attempt(
            control_principal_ref=control_principal_ref,
            schedule_id=schedule_id,
            attempt_id=attempt_id,
        )
        selo = self._repository.get_seal_receipt_by_attempt(
            control_principal_ref=control_principal_ref,
            schedule_id=schedule_id,
            attempt_id=attempt_id,
        )
        etapa = self._repository.get_step(
            control_principal_ref=control_principal_ref,
            schedule_id=schedule_id,
            step_id=step_id,
        )
        return (
            (
                None
                if tentativa is None
                else AttemptProjection(
                    attempt_id=tentativa.id,
                    step_id=tentativa.step_id,
                    attempt_number=tentativa.attempt_number,
                    envelope_version=tentativa.envelope_version,
                    content_sha256=tentativa.content_sha256,
                    state=tentativa.state,
                    created_at=tentativa.created_at,
                    result=None,
                    attribution=None,
                )
            ),
            None if selo is None else _projetar_selo(selo),
            None if etapa is None else _projetar_etapa(etapa),
        )

    def read_governance(
        self, *, control_principal_ref: str, schedule_id: uuid.UUID
    ) -> GovernanceProjection:
        """Delegações, eventos, observações e pareceres do Schedule."""
        agenda = self._schedules.get_schedule(
            control_principal_ref=control_principal_ref, schedule_id=schedule_id
        )
        return GovernanceProjection(
            schedule_id=schedule_id,
            schedule_state=agenda.state,
            delegations=tuple(
                _projetar_delegacao(d)
                for d in self._repository.list_delegations(
                    control_principal_ref=control_principal_ref, schedule_id=schedule_id
                )
            ),
            control_events=tuple(
                _projetar_evento(e)
                for e in self._repository.list_control_events(
                    control_principal_ref=control_principal_ref, schedule_id=schedule_id
                )
            ),
            observations=tuple(
                _projetar_observacao(o)
                for o in self._repository.list_execution_observations(
                    control_principal_ref=control_principal_ref, schedule_id=schedule_id
                )
            ),
            audit_opinions=tuple(
                _projetar_parecer(p)
                for p in self._repository.list_audit_opinions(
                    control_principal_ref=control_principal_ref, schedule_id=schedule_id
                )
            ),
        )


def _projetar_resultado(resultado: object) -> ResultProjection:
    return ResultProjection(
        status=resultado.status,  # type: ignore[attr-defined]
        expected_output_contract=resultado.expected_output_contract,  # type: ignore[attr-defined]
        output_media_type=resultado.output_media_type,  # type: ignore[attr-defined]
        output_sha256=resultado.output_sha256,  # type: ignore[attr-defined]
        output_bytes=resultado.output_bytes,  # type: ignore[attr-defined]
        declared_output_ref=resultado.declared_output_ref,  # type: ignore[attr-defined]
        validation_codes=tuple(resultado.validation_codes),  # type: ignore[attr-defined]
    )


def _projetar_atribuicao(atribuicao: object) -> AttributionProjection:
    return AttributionProjection(
        declared_provider_id=atribuicao.declared_provider_id,  # type: ignore[attr-defined]
        declared_model_id=atribuicao.declared_model_id,  # type: ignore[attr-defined]
        declared_instance_id=atribuicao.declared_instance_id,  # type: ignore[attr-defined]
        role=atribuicao.role,  # type: ignore[attr-defined]
        declared_at=atribuicao.declared_at,  # type: ignore[attr-defined]
        self_declared=atribuicao.self_declared,  # type: ignore[attr-defined]
        provenance_record_ref=atribuicao.provenance_record_ref,  # type: ignore[attr-defined]
    )


def _projetar_etapa(etapa: object) -> StepProjection:
    return StepProjection(
        step_id=etapa.id,  # type: ignore[attr-defined]
        position=etapa.position,  # type: ignore[attr-defined]
        role=etapa.role,  # type: ignore[attr-defined]
        state=etapa.state,  # type: ignore[attr-defined]
        instruction_ref=etapa.instruction_ref,  # type: ignore[attr-defined]
        context_refs=tuple(etapa.context_refs),  # type: ignore[attr-defined]
        expected_output_contract=etapa.expected_output_contract,  # type: ignore[attr-defined]
        constraints=etapa.constraints,  # type: ignore[attr-defined]
    )


def _projetar_selo(selo: object) -> SealReceiptProjection:
    return SealReceiptProjection(
        receipt_id=selo.id,  # type: ignore[attr-defined]
        attempt_id=selo.attempt_id,  # type: ignore[attr-defined]
        content_sha256=selo.content_sha256,  # type: ignore[attr-defined]
        sealed_at=selo.sealed_at,  # type: ignore[attr-defined]
    )


def _projetar_delegacao(delegacao: object) -> DelegationProjection:
    return DelegationProjection(
        delegation_id=delegacao.id,  # type: ignore[attr-defined]
        step_id=delegacao.step_id,  # type: ignore[attr-defined]
        content_sha256=delegacao.content_sha256,  # type: ignore[attr-defined]
        scope=delegacao.scope,  # type: ignore[attr-defined]
        state=delegacao.state,  # type: ignore[attr-defined]
        valid_until=delegacao.valid_until,  # type: ignore[attr-defined]
        consumed_at=delegacao.consumed_at,  # type: ignore[attr-defined]
        consumed_by_attempt_id=delegacao.consumed_by_attempt_id,  # type: ignore[attr-defined]
    )


def _projetar_evento(evento: object) -> ControlEventProjection:
    categoria = evento.stop_condition_category  # type: ignore[attr-defined]
    return ControlEventProjection(
        event_id=evento.id,  # type: ignore[attr-defined]
        step_id=evento.step_id,  # type: ignore[attr-defined]
        event_kind=evento.event_kind,  # type: ignore[attr-defined]
        reason_code=evento.reason_code,  # type: ignore[attr-defined]
        stop_condition_category=None if categoria is None else categoria.value,
        occurred_at=evento.occurred_at,  # type: ignore[attr-defined]
    )


def _projetar_observacao(observacao: object) -> ObservationProjection:
    return ObservationProjection(
        observation_id=observacao.id,  # type: ignore[attr-defined]
        step_id=observacao.step_id,  # type: ignore[attr-defined]
        observation_kind=observacao.observation_kind,  # type: ignore[attr-defined]
        previous_attempt_id=observacao.previous_attempt_id,  # type: ignore[attr-defined]
        current_attempt_id=observacao.current_attempt_id,  # type: ignore[attr-defined]
        previous_declared_provider_id=(
            observacao.previous_declared_provider_id  # type: ignore[attr-defined]
        ),
        current_declared_provider_id=(
            observacao.current_declared_provider_id  # type: ignore[attr-defined]
        ),
        self_declared=observacao.self_declared,  # type: ignore[attr-defined]
        observed_at=observacao.observed_at,  # type: ignore[attr-defined]
    )


def _projetar_parecer(parecer: object) -> AuditOpinionProjection:
    return AuditOpinionProjection(
        opinion_id=parecer.id,  # type: ignore[attr-defined]
        handoff_result_id=parecer.handoff_result_id,  # type: ignore[attr-defined]
        opinion=parecer.opinion,  # type: ignore[attr-defined]
        reason_codes=tuple(parecer.reason_codes),  # type: ignore[attr-defined]
        auditor_execution_ref=parecer.auditor_execution_ref,  # type: ignore[attr-defined]
        issued_at=parecer.issued_at,  # type: ignore[attr-defined]
    )
