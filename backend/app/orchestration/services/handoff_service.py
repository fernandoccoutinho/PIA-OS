"""
`HandoffService` — produtor único de `ENVELOPE_CONTENT`, `Attempt` e
`SealReceipt` (MAI §21).

```text
SAME_CONTENT + MULTIPLE_ATTEMPTS -> mesmo hash, recibos distintos
CONTENT_CHANGED -> hash distinto
SEALED_AT_IN_CONTENT_HASH = FALSE
SEALED != DISPATCHED
```

O `control_principal_ref` atravessa **todas** as chamadas ao
repositório, inclusive as de escrita. A verificação que este serviço faz
antes é recusa antecipada, com mensagem melhor; a **garantia** vive no
repositório e na chave estrangeira composta do banco, que continuam
valendo se alguém chamar o repositório direto.

```text
EARLY_REFUSAL != THE_GUARANTEE
```

O `schedule_id` também atravessa: o repositório precisa do Schedule que
o chamador **declarou**, não do que a tentativa deixa derivar.

```text
OWNER_BINDING != SCHEDULE_BINDING
```

Selar é montar o conteúdo congelado da etapa, calcular seu hash, abrir uma
tentativa e registrar o recibo daquele ato. Não há transporte: o envelope
não atravessa fronteira nenhuma nesta entrega, e por isso a etapa
permanece `PENDING`.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from app.orchestration.errors.exceptions import (
    OrchestrationLifecycleViolationError,
    OrchestrationScopeViolationError,
)
from app.orchestration.models.enums import EXECUTABLE_HANDOFF_MODES, ScheduleState, StepState
from app.orchestration.repositories.orchestration_repository import OrchestrationRepository
from app.orchestration.schemas.envelope import ENVELOPE_VERSION, EnvelopeContent


@dataclass(frozen=True)
class SealOutcome:
    """O que um selamento produz: um conteúdo, uma tentativa, um recibo."""

    attempt_id: uuid.UUID
    attempt_number: int
    content_sha256: str
    envelope_version: str
    receipt_id: uuid.UUID
    sealed_at: datetime
    sealer_ref: str

    def __post_init__(self) -> None:
        if self.attempt_number < 1:
            raise ValueError("attempt_number começa em 1")
        if len(self.content_sha256) != 64:
            raise ValueError("content_sha256 deve ter 64 caracteres hexadecimais")


class HandoffService:
    """Sela etapas. Nenhum outro serviço abre tentativa ou emite recibo."""

    def __init__(self, repository: OrchestrationRepository) -> None:
        self._repository = repository

    def build_envelope_content(
        self, *, control_principal_ref: str, schedule_id: uuid.UUID, step_id: uuid.UUID
    ) -> EnvelopeContent:
        """Monta os oito campos congelados a partir da etapa persistida.

        Nada aqui lê relógio, ambiente ou identidade de tentativa: o
        conteúdo precisa ser reproduzível a partir da etapa, e só dela.
        """
        agenda = self._repository.get_schedule(
            control_principal_ref=control_principal_ref, schedule_id=schedule_id
        )
        if agenda is None:
            raise OrchestrationScopeViolationError(
                message="Schedule inexistente sob este principal de controle",
                detail={"schedule_id": str(schedule_id)},
            )
        etapa = self._repository.get_step(
            control_principal_ref=control_principal_ref,
            schedule_id=schedule_id,
            step_id=step_id,
        )
        if etapa is None:
            raise OrchestrationScopeViolationError(
                message="etapa inexistente neste Schedule sob este principal",
                detail={"schedule_id": str(schedule_id), "step_id": str(step_id)},
            )
        return EnvelopeContent(
            envelope_version=ENVELOPE_VERSION,
            schedule_id=schedule_id,
            step_id=step_id,
            role=etapa.role,
            instruction_ref=etapa.instruction_ref,
            context_refs=tuple(etapa.context_refs),
            expected_output_contract=etapa.expected_output_contract,
            constraints=tuple(etapa.constraints),
        )

    def seal_step(
        self,
        *,
        attempt_id: uuid.UUID,
        control_principal_ref: str,
        schedule_id: uuid.UUID,
        step_id: uuid.UUID,
        sealer_ref: str,
    ) -> SealOutcome:
        """Sela uma etapa e devolve o recibo daquele ato.

        Exige Schedule `ACTIVE` e etapa `PENDING`. Selar um trabalho ainda
        em rascunho registraria um repasse de composição não confirmada.
        """
        agenda = self._repository.get_schedule(
            control_principal_ref=control_principal_ref, schedule_id=schedule_id
        )
        if agenda is None:
            raise OrchestrationScopeViolationError(
                message="Schedule inexistente sob este principal de controle",
                detail={"schedule_id": str(schedule_id)},
            )
        if agenda.state is not ScheduleState.ACTIVE:
            raise OrchestrationLifecycleViolationError(
                message=f"selamento exige Schedule ACTIVE; estado atual {agenda.state.value}",
                detail={"current_state": agenda.state.value},
            )
        if agenda.execution_mode not in EXECUTABLE_HANDOFF_MODES:
            raise OrchestrationLifecycleViolationError(
                message=f"modo {agenda.execution_mode.value!r} não é executável nesta entrega",
                detail={"execution_mode": agenda.execution_mode.value},
            )
        etapa = self._repository.get_step(
            control_principal_ref=control_principal_ref,
            schedule_id=schedule_id,
            step_id=step_id,
        )
        if etapa is None:
            raise OrchestrationScopeViolationError(
                message="etapa inexistente neste Schedule sob este principal",
                detail={"schedule_id": str(schedule_id), "step_id": str(step_id)},
            )
        if etapa.state is not StepState.PENDING:
            raise OrchestrationLifecycleViolationError(
                message=f"selamento exige etapa PENDING; estado atual {etapa.state.value}",
                detail={"current_state": etapa.state.value},
            )
        if not sealer_ref.strip():
            raise OrchestrationLifecycleViolationError(message="sealer_ref não pode ser vazio")

        conteudo = EnvelopeContent(
            envelope_version=ENVELOPE_VERSION,
            schedule_id=schedule_id,
            step_id=step_id,
            role=etapa.role,
            instruction_ref=etapa.instruction_ref,
            context_refs=tuple(etapa.context_refs),
            expected_output_contract=etapa.expected_output_contract,
            constraints=tuple(etapa.constraints),
        )
        content_sha256 = conteudo.content_sha256()

        numero = self._repository.next_attempt_number(
            control_principal_ref=control_principal_ref,
            schedule_id=schedule_id,
            step_id=step_id,
        )
        tentativa = self._repository.create_attempt(
            control_principal_ref=control_principal_ref,
            attempt_id=attempt_id,
            schedule_id=schedule_id,
            step_id=step_id,
            attempt_number=numero,
            envelope_version=conteudo.envelope_version,
            content_sha256=content_sha256,
        )
        sealed_at = self._repository.database_now()
        recibo = self._repository.create_seal_receipt(
            control_principal_ref=control_principal_ref,
            schedule_id=schedule_id,
            attempt_id=tentativa.id,
            content_sha256=content_sha256,
            sealed_at=sealed_at,
            sealer_ref=sealer_ref,
        )
        return SealOutcome(
            attempt_id=tentativa.id,
            attempt_number=tentativa.attempt_number,
            content_sha256=content_sha256,
            envelope_version=conteudo.envelope_version,
            receipt_id=recibo.id,
            sealed_at=recibo.sealed_at,
            sealer_ref=recibo.sealer_ref,
        )
