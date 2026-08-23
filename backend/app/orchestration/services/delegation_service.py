"""
`DelegationService` — produtor único de `ServiceDelegation` (`E7.3`).

```text
SERVICE_DELEGATION != HUMAN_APPROVAL
BOUND_BY = schedule_id + step_id + content_sha256 + scope + valid_until
CONSUMPTION = SINGLE_USE + ATOMIC + HASH_BOUND
EXPIRY_SWEEPER = NOT_IMPLEMENTED
```

O cliente envia apenas `command_key` e `valid_until`. Tudo o mais é
derivado: principal do token, Schedule e Step do path, `scope` fixo e o
`content_sha256` corrente do envelope. Aceitar hash, escopo ou concedente
do corpo permitiria conceder autorização para um conteúdo que não é o que
será despachado.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from app.orchestration.errors.exceptions import (
    OrchestrationContractViolationError,
    OrchestrationLifecycleViolationError,
    OrchestrationScopeViolationError,
)
from app.orchestration.models.enums import DelegationState
from app.orchestration.repositories.orchestration_repository import OrchestrationRepository
from app.orchestration.schemas.envelope import GATE_SCOPE_DISPATCH, gate_requirement
from app.orchestration.services.handoff_service import HandoffService


@dataclass(frozen=True)
class DelegationView:
    """Vista congelada. Nenhuma instância ORM atravessa a sessão."""

    delegation_id: uuid.UUID
    schedule_id: uuid.UUID
    step_id: uuid.UUID
    content_sha256: str
    scope: str
    state: DelegationState
    valid_until: datetime
    granted_by_principal_ref: str
    consumed_at: datetime | None
    consumed_by_attempt_id: uuid.UUID | None


def _vista(delegacao: object) -> DelegationView:
    return DelegationView(
        delegation_id=delegacao.id,  # type: ignore[attr-defined]
        schedule_id=delegacao.schedule_id,  # type: ignore[attr-defined]
        step_id=delegacao.step_id,  # type: ignore[attr-defined]
        content_sha256=delegacao.content_sha256,  # type: ignore[attr-defined]
        scope=delegacao.scope,  # type: ignore[attr-defined]
        state=delegacao.state,  # type: ignore[attr-defined]
        valid_until=delegacao.valid_until,  # type: ignore[attr-defined]
        granted_by_principal_ref=delegacao.granted_by_principal_ref,  # type: ignore[attr-defined]
        consumed_at=delegacao.consumed_at,  # type: ignore[attr-defined]
        consumed_by_attempt_id=delegacao.consumed_by_attempt_id,  # type: ignore[attr-defined]
    )


class DelegationService:
    """Concede, revoga e consome autorização técnica de despacho."""

    def __init__(
        self, repository: OrchestrationRepository, handoff_service: HandoffService
    ) -> None:
        self._repository = repository
        self._handoff_service = handoff_service

    def grant(
        self,
        *,
        control_principal_ref: str,
        schedule_id: uuid.UUID,
        step_id: uuid.UUID,
        valid_until: datetime,
        delegation_id: uuid.UUID,
    ) -> DelegationView:
        """Concede delegação para o conteúdo **corrente** da etapa.

        A etapa precisa declarar gate técnico: conceder autorização a uma
        etapa sem gate criaria uma linha que nenhum caminho consome, e um
        registro de autorização que nada autoriza é ruído que a auditoria
        futura vai ler como sinal.
        """
        agenda = self._repository.lock_schedule(
            control_principal_ref=control_principal_ref, schedule_id=schedule_id
        )
        if agenda is None:
            raise OrchestrationScopeViolationError(
                message="Schedule inexistente sob este principal de controle",
                detail={"schedule_id": str(schedule_id)},
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
        exigencia = gate_requirement(tuple(etapa.constraints))
        if exigencia is None:
            raise OrchestrationContractViolationError(
                message="etapa sem gate declarado não admite delegação",
                detail={"step_id": str(step_id)},
            )
        agora = self._repository.database_now()
        if valid_until <= agora:
            raise OrchestrationContractViolationError(
                message="valid_until precisa ser futuro em relação ao relógio do banco"
            )

        # Expiração síncrona antes de qualquer decisão: sem isto o índice
        # parcial aprisionaria a Step com uma delegação vencida.
        self._repository.expire_stale_delegations(
            control_principal_ref=control_principal_ref,
            schedule_id=schedule_id,
            step_id=step_id,
        )
        conteudo = self._handoff_service.build_envelope_content(
            control_principal_ref=control_principal_ref,
            schedule_id=schedule_id,
            step_id=step_id,
        )
        # Binding novo substitui o anterior: a ACTIVE de hash antigo passa a
        # REVOKED antes do insert, e não fica competindo pelo índice.
        self._repository.revoke_active_delegations(
            control_principal_ref=control_principal_ref,
            schedule_id=schedule_id,
            step_id=step_id,
            scope=GATE_SCOPE_DISPATCH,
        )
        delegacao = self._repository.create_delegation(
            control_principal_ref=control_principal_ref,
            delegation_id=delegation_id,
            schedule_id=schedule_id,
            step_id=step_id,
            content_sha256=conteudo.content_sha256(),
            scope=GATE_SCOPE_DISPATCH,
            granted_by_principal_ref=control_principal_ref,
            valid_until=valid_until,
        )
        return _vista(delegacao)

    def revoke(
        self,
        *,
        control_principal_ref: str,
        schedule_id: uuid.UUID,
        delegation_id: uuid.UUID,
    ) -> DelegationView:
        """Revoga uma delegação `ACTIVE`. Terminal não regride."""
        delegacao = self._repository.get_delegation(
            control_principal_ref=control_principal_ref,
            schedule_id=schedule_id,
            delegation_id=delegation_id,
        )
        if delegacao is None:
            raise OrchestrationScopeViolationError(
                message="delegação inexistente neste Schedule sob este principal",
                detail={"schedule_id": str(schedule_id), "delegation_id": str(delegation_id)},
            )
        if delegacao.state is not DelegationState.ACTIVE:
            raise OrchestrationLifecycleViolationError(
                message=f"delegação já está em estado terminal {delegacao.state.value}",
                detail={"current_state": delegacao.state.value},
            )
        self._repository.revoke_active_delegations(
            control_principal_ref=control_principal_ref,
            schedule_id=schedule_id,
            step_id=delegacao.step_id,
            scope=delegacao.scope,
        )
        atual = self._repository.get_delegation(
            control_principal_ref=control_principal_ref,
            schedule_id=schedule_id,
            delegation_id=delegation_id,
        )
        if atual is None:  # pragma: no cover - a linha não é deletável
            raise RuntimeError("delegação desapareceu dentro da transação")
        return _vista(atual)

    def list_for_schedule(
        self, *, control_principal_ref: str, schedule_id: uuid.UUID
    ) -> tuple[DelegationView, ...]:
        return tuple(
            _vista(d)
            for d in self._repository.list_delegations(
                control_principal_ref=control_principal_ref, schedule_id=schedule_id
            )
        )
