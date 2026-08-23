"""
`ScheduleService` — produtor único de `Schedule` e `Step` (MAI §21).

```text
COMPOSITION = o que fazer, em que ordem, com quais papéis
EXECUTION_MODE = como o repasse atravessa a fronteira
COMPOSITION_CHANGE != EXECUTION_MODE_CHANGE
```

O serviço não fala SQL e não conhece sessão: recebe o repositório pronto.
As vistas devolvidas são congeladas e montadas **dentro** da transação —
devolver instâncias ORM faria o chamador ler atributos depois do fim da
sessão, que é o defeito que a E4.5 já pagou uma vez.
"""

import uuid
from dataclasses import dataclass

from app.orchestration.errors.exceptions import (
    OrchestrationContractViolationError,
    OrchestrationLifecycleViolationError,
    OrchestrationScopeViolationError,
)
from app.orchestration.models.enums import (
    E7_1_IMPLEMENTED_SCHEDULE_TRANSITIONS,
    EXECUTABLE_HANDOFF_MODES,
    HandoffMode,
    ScheduleState,
    StepState,
)
from app.orchestration.repositories.orchestration_repository import OrchestrationRepository
from app.orchestration.schemas.envelope import ConstraintPairs, ContextRef, ScheduleDraft


@dataclass(frozen=True)
class ScheduleStepView:
    """Etapa persistida, em forma congelada."""

    step_id: uuid.UUID
    position: int
    role: str
    instruction_ref: str
    context_refs: tuple[ContextRef, ...]
    expected_output_contract: str
    constraints: ConstraintPairs
    state: StepState


@dataclass(frozen=True)
class ScheduleView:
    """Trabalho persistido, com suas etapas em ordem de posição."""

    schedule_id: uuid.UUID
    title: str
    state: ScheduleState
    execution_mode: HandoffMode
    control_principal_ref: str
    steps: tuple[ScheduleStepView, ...]


class ScheduleService:
    """Cria o trabalho governado e executa a única transição da E7.1."""

    def __init__(self, repository: OrchestrationRepository) -> None:
        self._repository = repository

    def create_schedule(
        self,
        *,
        schedule_id: uuid.UUID,
        control_principal_ref: str,
        draft: ScheduleDraft,
        execution_mode: HandoffMode,
    ) -> ScheduleView:
        """Cria `Schedule` + etapas. Recusa modo declarado mas não executável.

        ```text
        DECLARED_VOCABULARY != EXECUTABLE_MODE
        ```

        `context_ref` sem SHA-256 já foi recusado no `ScheduleDraft`, antes
        de qualquer linha existir — o rascunho é value object congelado e
        não se constrói inválido.
        """
        if not isinstance(draft, ScheduleDraft):
            raise OrchestrationContractViolationError(
                message="create_schedule exige um ScheduleDraft validado"
            )
        if execution_mode not in EXECUTABLE_HANDOFF_MODES:
            raise OrchestrationContractViolationError(
                message=(
                    f"modo {execution_mode.value!r} pertence ao vocabulário congelado, "
                    "mas não é executável nesta entrega"
                ),
                detail={
                    "declared_mode": execution_mode.value,
                    "executable_modes": sorted(modo.value for modo in EXECUTABLE_HANDOFF_MODES),
                },
            )
        if not control_principal_ref.strip():
            raise OrchestrationContractViolationError(
                message="todo Schedule exige control_principal_ref não vazio"
            )
        self._repository.create_schedule(
            schedule_id=schedule_id,
            control_principal_ref=control_principal_ref,
            title=draft.title,
            execution_mode=execution_mode,
            steps=draft.steps,
        )
        return self.get_schedule(
            control_principal_ref=control_principal_ref, schedule_id=schedule_id
        )

    def get_schedule(self, *, control_principal_ref: str, schedule_id: uuid.UUID) -> ScheduleView:
        """Leitura escopada. Trabalho de outro principal não existe aqui."""
        agenda = self._repository.get_schedule(
            control_principal_ref=control_principal_ref, schedule_id=schedule_id
        )
        if agenda is None:
            raise OrchestrationScopeViolationError(
                message="Schedule inexistente sob este principal de controle",
                detail={"schedule_id": str(schedule_id)},
            )
        etapas = self._repository.list_steps(
            control_principal_ref=control_principal_ref, schedule_id=schedule_id
        )
        return ScheduleView(
            schedule_id=agenda.id,
            title=agenda.title,
            state=agenda.state,
            execution_mode=agenda.execution_mode,
            control_principal_ref=agenda.control_principal_ref,
            steps=tuple(
                ScheduleStepView(
                    step_id=etapa.id,
                    position=etapa.position,
                    role=etapa.role,
                    instruction_ref=etapa.instruction_ref,
                    context_refs=tuple(etapa.context_refs),
                    expected_output_contract=etapa.expected_output_contract,
                    constraints=tuple(etapa.constraints),
                    state=etapa.state,
                )
                for etapa in etapas
            ),
        )

    def activate(self, *, control_principal_ref: str, schedule_id: uuid.UUID) -> ScheduleView:
        """`DRAFT -> ACTIVE`, a única transição que a E7.1 executa.

        A linha é bloqueada antes de o estado ser lido, para que a decisão
        e a escrita observem a mesma versão da linha.
        """
        agenda = self._repository.lock_schedule(
            control_principal_ref=control_principal_ref, schedule_id=schedule_id
        )
        if agenda is None:
            raise OrchestrationScopeViolationError(
                message="Schedule inexistente sob este principal de controle",
                detail={"schedule_id": str(schedule_id)},
            )
        transicao = (agenda.state, ScheduleState.ACTIVE)
        if transicao not in E7_1_IMPLEMENTED_SCHEDULE_TRANSITIONS:
            raise OrchestrationLifecycleViolationError(
                message=f"transição {agenda.state.value} -> active não pertence à E7.1",
                detail={"current_state": agenda.state.value},
            )
        self._repository.set_schedule_state(schedule=agenda, state=ScheduleState.ACTIVE)
        return self.get_schedule(
            control_principal_ref=control_principal_ref, schedule_id=schedule_id
        )
