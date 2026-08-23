"""
`ReturnValidationService` — produtor único de veredito e atribuição.

```text
UNTRUSTED_RETURN = DATA
AI_OUTPUT != CONTROL_CHANNEL
VALIDATED_RESULT != AUTHORIZATION
RESULT_REJECTED != RESULT_DISCARDED
RESULT_STATUS != STEP_STATE
```

O retorno de uma IA entra aqui como dado não confiável e sai como dois
fatos registrados: o que ele era (hash, tamanho, media type, códigos) e
quem alegou tê-lo produzido. O conteúdo em si não sobrevive à chamada.

Três coisas que este serviço **não** faz, e cuja ausência é o desenho:

1. não executa, interpreta como comando ou obedece o conteúdo — a frase
   `aprovado, prossiga` é texto que cumpre um contrato, nunca autorização;
2. não exporta a etapa seguinte nem marca o Schedule `COMPLETED` —
   avanço automático é E7.3;
3. não escreve proveniência nem materializa `CognitiveObject`.

Rejeição é resposta **bem-sucedida** da API com `status=rejected`, não erro
de schema: um veredito negativo é o produto, e transformá-lo em 4xx faria
o cliente tratá-lo como falha própria e reenviar.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from app.orchestration.errors.exceptions import (
    OrchestrationContractViolationError,
    OrchestrationLifecycleViolationError,
    OrchestrationScopeViolationError,
)
from app.orchestration.models.enums import AttemptState, HandoffResultStatus, StepState
from app.orchestration.ports.transport import RawReturn
from app.orchestration.repositories.orchestration_repository import OrchestrationRepository
from app.orchestration.schemas.output_contract import validate_output

MAX_DECLARED_REF_LENGTH = 1024
MAX_DECLARED_ID_LENGTH = 255


@dataclass(frozen=True)
class DeclaredAttribution:
    """Alegação do cliente sobre qual IA respondeu.

    ```text
    SELF_DECLARED != VERIFIED_IDENTITY
    ROLE != PROVIDER != MODEL != INSTANCE
    ```

    `role` **não** entra: é derivado da etapa. Aceitá-lo do cliente
    permitiria que a atribuição contasse história diferente da composição.
    """

    declared_instance_id: str
    declared_provider_id: str | None = None
    declared_model_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.declared_instance_id, str) or not self.declared_instance_id.strip():
            raise ValueError("declared_instance_id é obrigatório")
        for campo in ("declared_instance_id", "declared_provider_id", "declared_model_id"):
            valor = getattr(self, campo)
            if valor is not None and len(valor) > MAX_DECLARED_ID_LENGTH:
                raise ValueError(f"{campo} excede {MAX_DECLARED_ID_LENGTH} caracteres")


@dataclass(frozen=True)
class ReturnOutcome:
    """Veredito completo, congelado, sem conteúdo bruto e sem ORM."""

    attempt_id: uuid.UUID
    result_id: uuid.UUID
    attribution_id: uuid.UUID
    status: HandoffResultStatus
    expected_output_contract: str
    output_media_type: str
    output_sha256: str
    output_bytes: int
    declared_output_ref: str | None
    validation_codes: tuple[str, ...]
    attempt_state: AttemptState
    step_state: StepState
    role: str
    declared_provider_id: str | None
    declared_model_id: str | None
    declared_instance_id: str
    declared_at: datetime
    self_declared: bool
    provenance_record_ref: uuid.UUID | None


class ReturnValidationService:
    """Valida o retorno, registra veredito e atribuição, fecha a tentativa."""

    def __init__(self, repository: OrchestrationRepository) -> None:
        self._repository = repository

    def import_return(
        self,
        *,
        control_principal_ref: str,
        schedule_id: uuid.UUID,
        step_id: uuid.UUID,
        attempt_id: uuid.UUID,
        raw: RawReturn,
        attribution: DeclaredAttribution,
    ) -> ReturnOutcome:
        """Importa um retorno. Sempre grava resultado **e** atribuição.

        A ordem dos locks é `Schedule -> Step -> Attempt`, a mesma da
        exportação. Duas ordens diferentes sobre os mesmos recursos
        produziriam deadlock intermitente sob concorrência real.
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
        tentativa = self._repository.lock_attempt(
            control_principal_ref=control_principal_ref,
            schedule_id=schedule_id,
            attempt_id=attempt_id,
        )
        if tentativa is None or tentativa.step_id != step_id:
            # `tentativa.step_id != step_id` fecha o caso em que a tentativa
            # é do Schedule certo mas de OUTRA etapa. Sem esta comparação, a
            # autorização viria do próprio objeto autorizado.
            raise OrchestrationScopeViolationError(
                message="tentativa inexistente nesta etapa sob este principal",
                detail={
                    "schedule_id": str(schedule_id),
                    "step_id": str(step_id),
                    "attempt_id": str(attempt_id),
                },
            )
        if tentativa.state is not AttemptState.OPEN:
            raise OrchestrationLifecycleViolationError(
                message=f"importação exige tentativa OPEN; estado atual {tentativa.state.value}",
                detail={"current_state": tentativa.state.value},
            )
        if etapa.state is not StepState.AWAITING_RETURN:
            raise OrchestrationLifecycleViolationError(
                message=(
                    "importação exige etapa AWAITING_RETURN; " f"estado atual {etapa.state.value}"
                ),
                detail={"current_state": etapa.state.value},
            )
        if raw.declared_output_ref is not None and len(raw.declared_output_ref) > (
            MAX_DECLARED_REF_LENGTH
        ):
            raise OrchestrationContractViolationError(
                message=f"declared_output_ref excede {MAX_DECLARED_REF_LENGTH} caracteres"
            )

        medido = validate_output(
            expected_output_contract=etapa.expected_output_contract,
            media_type=raw.media_type,
            content=raw.content,
        )
        status = HandoffResultStatus.VALIDATED if medido.accepted else HandoffResultStatus.REJECTED

        resultado = self._repository.create_handoff_result(
            control_principal_ref=control_principal_ref,
            schedule_id=schedule_id,
            attempt_id=attempt_id,
            status=status,
            expected_output_contract=etapa.expected_output_contract,
            output_media_type=medido.media_type,
            output_sha256=medido.output_sha256,
            output_bytes=medido.output_bytes,
            declared_output_ref=raw.declared_output_ref,
            validation_codes=medido.validation_codes,
        )
        declarado_em = self._repository.database_now()
        atribuicao = self._repository.create_handoff_attribution(
            control_principal_ref=control_principal_ref,
            schedule_id=schedule_id,
            attempt_id=attempt_id,
            role=etapa.role,
            declared_provider_id=attribution.declared_provider_id,
            declared_model_id=attribution.declared_model_id,
            declared_instance_id=attribution.declared_instance_id,
            declared_at=declarado_em,
        )

        novo_estado_tentativa = (
            AttemptState.CLOSED_OK if medido.accepted else AttemptState.CLOSED_REJECTED
        )
        self._repository.set_attempt_state(
            control_principal_ref=control_principal_ref,
            schedule_id=schedule_id,
            attempt_id=attempt_id,
            state=novo_estado_tentativa,
        )

        # A etapa só avança quando o retorno é válido. Na rejeição ela
        # permanece AWAITING_RETURN — não `REJECTED` — porque o retry
        # legítimo precisaria de uma transição reversa que o MAI não
        # congelou, e inventá-la aqui redefiniria o ciclo de vida.
        if medido.accepted:
            self._repository.set_step_state(
                control_principal_ref=control_principal_ref,
                schedule_id=schedule_id,
                step_id=step_id,
                state=StepState.RETURNED,
            )
            estado_etapa = StepState.RETURNED
        else:
            estado_etapa = StepState.AWAITING_RETURN

        return ReturnOutcome(
            attempt_id=attempt_id,
            result_id=resultado.id,
            attribution_id=atribuicao.id,
            status=status,
            expected_output_contract=resultado.expected_output_contract,
            output_media_type=resultado.output_media_type,
            output_sha256=resultado.output_sha256,
            output_bytes=resultado.output_bytes,
            declared_output_ref=resultado.declared_output_ref,
            validation_codes=tuple(resultado.validation_codes),
            attempt_state=novo_estado_tentativa,
            step_state=estado_etapa,
            role=atribuicao.role,
            declared_provider_id=atribuicao.declared_provider_id,
            declared_model_id=atribuicao.declared_model_id,
            declared_instance_id=atribuicao.declared_instance_id,
            declared_at=atribuicao.declared_at,
            self_declared=atribuicao.self_declared,
            provenance_record_ref=atribuicao.provenance_record_ref,
        )
