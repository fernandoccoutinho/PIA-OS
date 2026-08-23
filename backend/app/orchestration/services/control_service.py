"""
`ControlService` — Stop Conditions, cancelamento cooperativo e conclusão.

```text
D9 = COOPERATIVE
NO_HARD_CANCEL | NO_WORKER | NO_TIMEOUT
LOCK_ORDER = Schedule -> Step(s) -> Attempt(s)
CANCELLED | STOPPED | PAUSED -> ZERO TRANSPORT
```

Não há cancelamento forte porque não há processo em execução para
interromper: o despacho é manual. O que se cancela é a **autorização da
próxima chamada**, e é por isso que o efeito aparece no ponto de
despacho, não num sinal enviado a alguém.

`PAUSED` é retomável por ato explícito. `STOPPED` e `CANCELLED` são
terminais.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from app.orchestration.errors.exceptions import (
    OrchestrationContractViolationError,
    OrchestrationLifecycleViolationError,
    OrchestrationScopeViolationError,
)
from app.orchestration.models.enums import (
    E7_3_IMPLEMENTED_SCHEDULE_TRANSITIONS,
    AttemptState,
    ControlEventKind,
    ControlReasonCode,
    ScheduleState,
    StepState,
    StopConditionCategory,
)
from app.orchestration.repositories.orchestration_repository import OrchestrationRepository


@dataclass(frozen=True)
class ControlEventView:
    event_id: uuid.UUID
    schedule_id: uuid.UUID
    step_id: uuid.UUID | None
    event_kind: ControlEventKind
    reason_code: ControlReasonCode
    stop_condition_category: StopConditionCategory | None
    declared_by_principal_ref: str
    occurred_at: datetime


@dataclass(frozen=True)
class ControlOutcome:
    schedule_id: uuid.UUID
    schedule_state: ScheduleState
    event: ControlEventView
    cancelled_steps: int
    closed_attempts: int


def _vista(evento: object) -> ControlEventView:
    return ControlEventView(
        event_id=evento.id,  # type: ignore[attr-defined]
        schedule_id=evento.schedule_id,  # type: ignore[attr-defined]
        step_id=evento.step_id,  # type: ignore[attr-defined]
        event_kind=evento.event_kind,  # type: ignore[attr-defined]
        reason_code=evento.reason_code,  # type: ignore[attr-defined]
        stop_condition_category=evento.stop_condition_category,  # type: ignore[attr-defined]
        declared_by_principal_ref=evento.declared_by_principal_ref,  # type: ignore[attr-defined]
        occurred_at=evento.occurred_at,  # type: ignore[attr-defined]
    )


_ACAO_DESTINO: dict[str, ScheduleState] = {
    "pause": ScheduleState.PAUSED,
    "resume": ScheduleState.ACTIVE,
    "stop": ScheduleState.STOPPED,
    "cancel": ScheduleState.CANCELLED,
}
_ACAO_EVENTO: dict[str, ControlEventKind] = {
    "pause": ControlEventKind.PAUSED,
    "resume": ControlEventKind.RESUMED,
    "stop": ControlEventKind.STOPPED,
    "cancel": ControlEventKind.CANCELLED,
}


class ControlService:
    """Produtor único de eventos de controle e das transições de ciclo."""

    def __init__(self, repository: OrchestrationRepository) -> None:
        self._repository = repository

    def apply(
        self,
        *,
        control_principal_ref: str,
        schedule_id: uuid.UUID,
        action: str,
        event_id: uuid.UUID,
        stop_condition_category: StopConditionCategory | None = None,
    ) -> ControlOutcome:
        """Aplica `pause | resume | stop | cancel` sob a ordem de locks."""
        if action not in _ACAO_DESTINO:
            raise OrchestrationContractViolationError(
                message=f"ação de controle desconhecida: {action!r}"
            )
        agenda = self._repository.lock_schedule(
            control_principal_ref=control_principal_ref, schedule_id=schedule_id
        )
        if agenda is None:
            raise OrchestrationScopeViolationError(
                message="Schedule inexistente sob este principal de controle",
                detail={"schedule_id": str(schedule_id)},
            )
        destino = _ACAO_DESTINO[action]
        if (agenda.state, destino) not in E7_3_IMPLEMENTED_SCHEDULE_TRANSITIONS:
            raise OrchestrationLifecycleViolationError(
                message=f"transição {agenda.state.value} -> {destino.value} não é executável",
                detail={"current_state": agenda.state.value},
            )
        if action == "stop":
            if stop_condition_category is None:
                raise OrchestrationContractViolationError(
                    message="parar exige categoria de Stop Condition"
                )
            motivo = ControlReasonCode.STOP_CONDITION_DECLARED
        else:
            if stop_condition_category is not None:
                raise OrchestrationContractViolationError(
                    message="categoria de Stop Condition só se aplica a stop"
                )
            motivo = ControlReasonCode.OPERATOR_REQUESTED

        canceladas = 0
        fechadas = 0
        if action == "cancel":
            canceladas, fechadas = self._cancelar_conteudo(
                control_principal_ref=control_principal_ref, schedule_id=schedule_id
            )

        self._repository.set_schedule_state(
            control_principal_ref=control_principal_ref,
            schedule_id=schedule_id,
            state=destino,
        )
        evento = self._repository.create_control_event(
            event_id=event_id,
            control_principal_ref=control_principal_ref,
            schedule_id=schedule_id,
            step_id=None,
            event_kind=_ACAO_EVENTO[action],
            reason_code=motivo,
            stop_condition_category=stop_condition_category,
            declared_by_principal_ref=control_principal_ref,
            occurred_at=self._repository.database_now(),
        )
        return ControlOutcome(
            schedule_id=schedule_id,
            schedule_state=destino,
            event=_vista(evento),
            cancelled_steps=canceladas,
            closed_attempts=fechadas,
        )

    def _cancelar_conteudo(
        self, *, control_principal_ref: str, schedule_id: uuid.UUID
    ) -> tuple[int, int]:
        """Cancela etapas pendentes e fecha tentativas abertas, em ordem.

        Etapas `RETURNED` são **preservadas**: já entregaram, e apagar o
        que foi concluído junto com o que foi cancelado destruiria a
        distinção entre trabalho feito e trabalho abortado.
        """
        canceladas = 0
        for etapa in self._repository.list_steps(
            control_principal_ref=control_principal_ref, schedule_id=schedule_id
        ):
            if etapa.state in (StepState.PENDING, StepState.AWAITING_RETURN):
                self._repository.set_step_state(
                    control_principal_ref=control_principal_ref,
                    schedule_id=schedule_id,
                    step_id=etapa.id,
                    state=StepState.CANCELLED,
                )
                canceladas += 1
        fechadas = 0
        for tentativa in self._repository.list_open_attempts_of_schedule(
            control_principal_ref=control_principal_ref, schedule_id=schedule_id
        ):
            self._repository.set_attempt_state(
                control_principal_ref=control_principal_ref,
                schedule_id=schedule_id,
                attempt_id=tentativa.id,
                state=AttemptState.CLOSED_CANCELLED,
            )
            fechadas += 1
        return canceladas, fechadas

    def register_pause(
        self,
        *,
        control_principal_ref: str,
        schedule_id: uuid.UUID,
        step_id: uuid.UUID,
        reason_code: ControlReasonCode,
    ) -> ControlEventView | None:
        """Pausa provocada por gate bloqueado, sem duplicar evento.

        ```text
        REPEAT_WHILE_PAUSED -> NO_SECOND_EVENT
        ```

        Repetir a chamada enquanto o Schedule já está `PAUSED` pelo mesmo
        motivo não grava de novo: um evento por ocorrência, não por
        tentativa de leitura.
        """
        agenda = self._repository.lock_schedule(
            control_principal_ref=control_principal_ref, schedule_id=schedule_id
        )
        if agenda is None:  # pragma: no cover - chamador já resolveu o escopo
            raise OrchestrationScopeViolationError(
                message="Schedule inexistente sob este principal de controle",
                detail={"schedule_id": str(schedule_id)},
            )
        if agenda.state is ScheduleState.PAUSED:
            if self._repository.count_open_pause_events(
                control_principal_ref=control_principal_ref,
                schedule_id=schedule_id,
                reason_code=reason_code,
            ):
                return None
        elif agenda.state is ScheduleState.ACTIVE:
            self._repository.set_schedule_state(
                control_principal_ref=control_principal_ref,
                schedule_id=schedule_id,
                state=ScheduleState.PAUSED,
            )
        else:  # pragma: no cover - terminal recusa antes de chegar aqui
            return None
        evento = self._repository.create_control_event(
            event_id=uuid.uuid4(),
            control_principal_ref=control_principal_ref,
            schedule_id=schedule_id,
            step_id=step_id,
            event_kind=ControlEventKind.PAUSED,
            reason_code=reason_code,
            stop_condition_category=None,
            declared_by_principal_ref=control_principal_ref,
            occurred_at=self._repository.database_now(),
        )
        return _vista(evento)

    def complete_if_all_returned(
        self, *, control_principal_ref: str, schedule_id: uuid.UUID
    ) -> ControlEventView | None:
        """`ACTIVE -> COMPLETED` quando **todas** as etapas retornaram.

        ```text
        VALIDATED_FINAL_RESULT -> COMPLETED, NO AUTOEXPORT
        ```

        Chamado na mesma transação do import validado. Um retorno
        rejeitado não completa, e nenhum texto de IA — "aprovado,
        prossiga" inclusive — dispara isto: a condição é o estado das
        etapas, não o conteúdo devolvido.
        """
        agenda = self._repository.lock_schedule(
            control_principal_ref=control_principal_ref, schedule_id=schedule_id
        )
        if agenda is None or agenda.state is not ScheduleState.ACTIVE:
            return None
        if not self._repository.all_steps_returned(
            control_principal_ref=control_principal_ref, schedule_id=schedule_id
        ):
            return None
        self._repository.set_schedule_state(
            control_principal_ref=control_principal_ref,
            schedule_id=schedule_id,
            state=ScheduleState.COMPLETED,
        )
        evento = self._repository.create_control_event(
            event_id=uuid.uuid4(),
            control_principal_ref=control_principal_ref,
            schedule_id=schedule_id,
            step_id=None,
            event_kind=ControlEventKind.COMPLETED,
            reason_code=ControlReasonCode.ALL_STEPS_RETURNED,
            stop_condition_category=None,
            declared_by_principal_ref=control_principal_ref,
            occurred_at=self._repository.database_now(),
        )
        return _vista(evento)

    def list_events(
        self, *, control_principal_ref: str, schedule_id: uuid.UUID
    ) -> tuple[ControlEventView, ...]:
        return tuple(
            _vista(e)
            for e in self._repository.list_control_events(
                control_principal_ref=control_principal_ref, schedule_id=schedule_id
            )
        )
