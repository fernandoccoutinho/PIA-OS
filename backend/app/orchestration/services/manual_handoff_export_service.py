"""
`ManualHandoffExportService` — produtor único de `ExportedHandoff` (`E7.2`).

```text
SEALED != DISPATCHED
EXPORT = SEAL + TRANSPORT + TRANSITIONS
```

A E7.1 selava e parava: a etapa continuava `PENDING` porque nada havia
atravessado fronteira alguma. A E7.2 traz o transporte manual, e por isso
`DISPATCHED` e `AWAITING_RETURN` finalmente têm produtor.

O `seal_step` da E7.1 **não** foi rebatizado. Ele continua significando o
que significava; este serviço o compõe e acrescenta o que é seu. Mudar o
sentido do método antigo faria toda a evidência da E7.1 passar a descrever
outra coisa.

```text
LOCK_ORDER = Schedule -> Step(s) -> Attempt
ONE_OPEN_ATTEMPT_PER_STEP = TRUE
REJECTED_RESULT BLOCKS ADVANCE
```
"""

import uuid
from dataclasses import dataclass

from app.orchestration.errors.exceptions import (
    OrchestrationLifecycleViolationError,
    OrchestrationScopeViolationError,
)
from app.orchestration.models.enums import (
    EXECUTABLE_HANDOFF_MODES,
    AttemptState,
    ScheduleState,
    StepState,
)
from app.orchestration.ports.transport import ExportedHandoff, HandoffTransportPort
from app.orchestration.repositories.orchestration_repository import OrchestrationRepository
from app.orchestration.schemas.envelope import ENVELOPE_VERSION, EnvelopeContent
from app.orchestration.services.handoff_service import HandoffService


@dataclass(frozen=True)
class ExportOutcome:
    """O que uma exportação produz. Congelado e sem instância ORM."""

    exported: ExportedHandoff
    step_state: StepState
    attempt_state: AttemptState


class ManualHandoffExportService:
    """Sela, abre tentativa, transporta manualmente e move a etapa."""

    def __init__(
        self,
        repository: OrchestrationRepository,
        handoff_service: HandoffService,
        transport: HandoffTransportPort,
    ) -> None:
        self._repository = repository
        self._handoff_service = handoff_service
        self._transport = transport

    def export_step(
        self,
        *,
        attempt_id: uuid.UUID,
        control_principal_ref: str,
        schedule_id: uuid.UUID,
        step_id: uuid.UUID,
        sealer_ref: str,
    ) -> ExportOutcome:
        """Exporta uma etapa, na ordem de locks e sob todas as pré-condições.

        As duas transições ocorrem na mesma transação e o estado confirmado
        ao cliente é `AWAITING_RETURN`: `DISPATCHED` é um instante, não um
        lugar onde o sistema descansa. Persistir a parada intermediária
        criaria um estado que ninguém consegue observar e do qual ninguém
        sabe sair.
        """
        agenda = self._repository.lock_schedule(
            control_principal_ref=control_principal_ref, schedule_id=schedule_id
        )
        if agenda is None:
            raise OrchestrationScopeViolationError(
                message="Schedule inexistente sob este principal de controle",
                detail={"schedule_id": str(schedule_id)},
            )
        if agenda.state is not ScheduleState.ACTIVE:
            raise OrchestrationLifecycleViolationError(
                message=f"exportação exige Schedule ACTIVE; estado atual {agenda.state.value}",
                detail={"current_state": agenda.state.value},
            )
        if agenda.execution_mode not in EXECUTABLE_HANDOFF_MODES:
            raise OrchestrationLifecycleViolationError(
                message=f"modo {agenda.execution_mode.value!r} não é executável nesta entrega",
                detail={"execution_mode": agenda.execution_mode.value},
            )

        etapa = self._repository.lock_step(
            control_principal_ref=control_principal_ref,
            schedule_id=schedule_id,
            step_id=step_id,
        )
        if etapa is None:
            raise OrchestrationScopeViolationError(
                message="etapa inexistente neste Schedule sob este principal",
                detail={"schedule_id": str(schedule_id), "step_id": str(step_id)},
            )

        pendentes = self._repository.list_unreturned_predecessors(
            control_principal_ref=control_principal_ref,
            schedule_id=schedule_id,
            position=etapa.position,
        )
        if pendentes:
            raise OrchestrationLifecycleViolationError(
                message=(
                    "exportação exige todas as posições anteriores RETURNED; "
                    f"pendentes: {pendentes}"
                ),
                detail={"position": etapa.position, "unreturned_positions": pendentes},
            )

        aberta = self._repository.get_open_attempt(
            control_principal_ref=control_principal_ref,
            schedule_id=schedule_id,
            step_id=step_id,
        )
        if aberta is not None:
            raise OrchestrationLifecycleViolationError(
                message="já existe tentativa OPEN nesta etapa; importe ou rejeite antes",
                detail={"open_attempt_id": str(aberta.id)},
            )

        if etapa.state not in (StepState.PENDING, StepState.AWAITING_RETURN):
            # `PENDING` é o primeiro export; `AWAITING_RETURN` é o retry
            # legítimo depois de uma rejeição. Nenhum outro estado admite
            # exportação, e listar os dois explicitamente evita que um
            # estado futuro entre por omissão.
            raise OrchestrationLifecycleViolationError(
                message=f"exportação não admite etapa em {etapa.state.value}",
                detail={"current_state": etapa.state.value},
            )
        primeira_exportacao = etapa.state is StepState.PENDING

        selado = self._handoff_service.seal_step_for_export(
            attempt_id=attempt_id,
            control_principal_ref=control_principal_ref,
            schedule_id=schedule_id,
            step_id=step_id,
            sealer_ref=sealer_ref,
        )

        envelope = EnvelopeContent(
            envelope_version=ENVELOPE_VERSION,
            schedule_id=schedule_id,
            step_id=step_id,
            role=etapa.role,
            instruction_ref=etapa.instruction_ref,
            context_refs=tuple(etapa.context_refs),
            expected_output_contract=etapa.expected_output_contract,
            constraints=tuple(etapa.constraints),
        )
        repasse = ExportedHandoff(
            schedule_id=schedule_id,
            step_id=step_id,
            attempt_id=selado.attempt_id,
            attempt_number=selado.attempt_number,
            receipt_id=selado.receipt_id,
            content_sha256=selado.content_sha256,
            sealed_at=selado.sealed_at,
            envelope=envelope,
        )
        entregue = self._transport.export(repasse)

        if primeira_exportacao:
            self._repository.set_step_state(
                control_principal_ref=control_principal_ref,
                schedule_id=schedule_id,
                step_id=step_id,
                state=StepState.DISPATCHED,
            )
        self._repository.set_step_state(
            control_principal_ref=control_principal_ref,
            schedule_id=schedule_id,
            step_id=step_id,
            state=StepState.AWAITING_RETURN,
        )
        return ExportOutcome(
            exported=entregue,
            step_state=StepState.AWAITING_RETURN,
            attempt_state=AttemptState.OPEN,
        )
