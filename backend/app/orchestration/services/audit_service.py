"""
`AuditService` — parecer separado, jamais escrita no artefato (`E7.3`).

```text
AUDITOR_WRITE_ON_AUDITED_ARTIFACT = FORBIDDEN
AUDITOR_OUTPUT = SEPARATE_APPEND_ONLY_OPINION
AI_SELF_PASS_FINAL = FORBIDDEN
```

A única escrita que este serviço conhece é `create_audit_opinion`. Ele
não tem acesso a nenhum caminho que altere `HandoffResult`,
`HandoffAttribution`, Schedule, Step, Attempt ou recibo — e o mutante
`M-a` existe para matar qualquer versão em que passe a ter.

Parecer negativo **preserva** o resultado. `dissent` não apaga, não marca
e não reabre; pareceres independentes coexistem, porque divergência entre
auditores é informação, não conflito a resolver por sobrescrita.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from app.orchestration.errors.exceptions import (
    OrchestrationContractViolationError,
    OrchestrationScopeViolationError,
)
from app.orchestration.models.audit_opinion import (
    assert_opinion_matrix,
    canonical_audit_reason_codes,
)
from app.orchestration.models.enums import AuditOpinionKind
from app.orchestration.repositories.orchestration_repository import OrchestrationRepository


@dataclass(frozen=True)
class AuditOpinionView:
    opinion_id: uuid.UUID
    handoff_result_id: uuid.UUID
    opinion: AuditOpinionKind
    reason_codes: tuple[str, ...]
    auditor_execution_ref: str
    issued_by_principal_ref: str
    issued_at: datetime


class AuditService:
    """Registra parecer sobre um `HandoffResult`. Nada além disso."""

    def __init__(self, repository: OrchestrationRepository) -> None:
        self._repository = repository

    def issue(
        self,
        *,
        control_principal_ref: str,
        schedule_id: uuid.UUID,
        attempt_id: uuid.UUID,
        opinion: AuditOpinionKind,
        reason_codes: tuple[str, ...],
        auditor_execution_ref: str,
    ) -> AuditOpinionView:
        """Emite parecer. A matriz opinião×motivo é imposta antes do banco."""
        if not auditor_execution_ref.strip():
            raise OrchestrationContractViolationError(
                message="auditor_execution_ref não pode ser vazio"
            )
        # A matriz é invariante de contrato: violá-la é 422 do cliente, não
        # 500 do servidor. `ValueError` cru vazaria como erro interno.
        try:
            codigos = canonical_audit_reason_codes(reason_codes)
            assert_opinion_matrix(opinion, codigos)
        except ValueError as erro:
            raise OrchestrationContractViolationError(message=str(erro)) from erro

        resultado = self._repository.get_result_for_audit(
            control_principal_ref=control_principal_ref,
            schedule_id=schedule_id,
            attempt_id=attempt_id,
        )
        if resultado is None:
            raise OrchestrationScopeViolationError(
                message="resultado inexistente nesta tentativa sob este principal",
                detail={"schedule_id": str(schedule_id), "attempt_id": str(attempt_id)},
            )
        parecer = self._repository.create_audit_opinion(
            control_principal_ref=control_principal_ref,
            schedule_id=schedule_id,
            handoff_result_id=resultado.id,
            opinion=opinion,
            reason_codes=codigos,
            auditor_execution_ref=auditor_execution_ref,
            issued_by_principal_ref=control_principal_ref,
            issued_at=self._repository.database_now(),
        )
        return AuditOpinionView(
            opinion_id=parecer.id,
            handoff_result_id=parecer.handoff_result_id,
            opinion=parecer.opinion,
            reason_codes=tuple(parecer.reason_codes),
            auditor_execution_ref=parecer.auditor_execution_ref,
            issued_by_principal_ref=parecer.issued_by_principal_ref,
            issued_at=parecer.issued_at,
        )

    def list_for_schedule(
        self, *, control_principal_ref: str, schedule_id: uuid.UUID
    ) -> tuple[AuditOpinionView, ...]:
        return tuple(
            AuditOpinionView(
                opinion_id=p.id,
                handoff_result_id=p.handoff_result_id,
                opinion=p.opinion,
                reason_codes=tuple(p.reason_codes),
                auditor_execution_ref=p.auditor_execution_ref,
                issued_by_principal_ref=p.issued_by_principal_ref,
                issued_at=p.issued_at,
            )
            for p in self._repository.list_audit_opinions(
                control_principal_ref=control_principal_ref, schedule_id=schedule_id
            )
        )
