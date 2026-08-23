"""
`CommandReceiptService` — produtor único de `CommandReceipt` e fronteira
de idempotência (MAI §15, addendum §2).

```text
COMMAND_IDEMPOTENCY_SCOPE = (technical_principal_ref, operation, command_key)
GLOBAL_COMMAND_KEY_ALONE = INSUFFICIENT
SAME_COMMAND_KEY -> SAME_RECEIPT, NO_DUPLICATE_EFFECT
RETRY -> NEW_COMMAND_KEY -> NEW_ATTEMPT
```

A ordem importa: a identidade do efeito é **gerada antes** da
reivindicação, e o efeito só é produzido quando o banco confirma que foi
esta chamada que inseriu a linha. Produzir primeiro e reivindicar depois
duplicaria o efeito toda vez que a chave já existisse.

```text
CLAIM_BEFORE_EFFECT = TRUE
EFFECT_BEFORE_CLAIM = DUPLICATE_ON_REPLAY
```

Não existe callback público aqui. Cada operação do vocabulário fechado
tem seu método, e o efeito é um método interno ligado a ele — um
executor genérico deixaria a fronteira de idempotência aceitar qualquer
efeito que alguém quisesse rotular como comando.
"""

import hashlib
import json
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING

from app.orchestration.errors.exceptions import (
    OrchestrationContractViolationError,
    OrchestrationLifecycleViolationError,
)
from app.orchestration.models.enums import CommandOperation, HandoffMode
from app.orchestration.ports.transport import RawReturn
from app.orchestration.repositories.orchestration_repository import OrchestrationRepository
from app.orchestration.schemas.envelope import MAX_REF_LENGTH, ScheduleDraft
from app.orchestration.services.handoff_service import HandoffService
from app.orchestration.services.manual_handoff_export_service import (
    ExportOutcome,
    ManualHandoffExportService,
)
from app.orchestration.services.return_validation_service import (
    DeclaredAttribution,
    ReturnOutcome,
    ReturnValidationService,
)
from app.orchestration.services.schedule_service import ScheduleService

if TYPE_CHECKING:  # pragma: no cover - só para tipos
    from datetime import datetime

    from app.orchestration.models.enums import AuditOpinionKind, StopConditionCategory
    from app.orchestration.services.audit_service import AuditOpinionView, AuditService
    from app.orchestration.services.control_service import ControlOutcome, ControlService
    from app.orchestration.services.delegation_service import DelegationService, DelegationView

MAX_COMMAND_KEY_LENGTH = 255


def _impressao_digital(payload: Mapping[str, object]) -> str:
    """SHA-256 do JSON canônico da requisição.

    ```text
    SAME_COMMAND_KEY + DIFFERENT_REQUEST = CONFLICT
    FINGERPRINT_STORES_HASH_NOT_CONTENT
    ```

    Ordenado, compacto e sem escape de não-ASCII, como o
    `ENVELOPE_CONTENT`: a ordem em que o cliente montou o corpo não é
    conteúdo. Do conteúdo bruto entra apenas o **hash** dos bytes UTF-8
    exatos — a impressão digital identifica a requisição sem guardá-la.

    ## Corretivo R2 (Chain115): `sealer_ref` entra em selar e exportar

    ```text
    WHO_SEALED_IS_PART_OF_WHAT_WAS_REQUESTED
    DERIVED_TODAY != DERIVED_FOREVER
    ```

    Hoje a API deriva `sealer_ref` de `str(principal.id)`, que já compõe a
    tripla de idempotência — então, **por esse caminho**, um selador
    diferente implica principal diferente e a colisão nem chega a existir.
    A digital não depende disso: `seal_handoff_once` e
    `export_handoff_once` recebem `sealer_ref` como parâmetro próprio, e
    um chamador de serviço pode passá-lo divergente.

    Deixar de fora um campo que muda o efeito, apoiado em como a única
    superfície atual o preenche, é fazer a corretude depender de uma
    coincidência entre camadas. Quem selou é parte do que foi pedido.
    """
    canonico = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


def _digest_de_conteudo(content: str) -> str:
    """SHA-256 dos bytes UTF-8 exatos, sem canonicalizar nem aparar."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CommandOutcome:
    """Recibo de comando + se ele foi recuperado em vez de produzido.

    `replayed` é informação, não desculpa: o chamador precisa saber que
    nada novo aconteceu, e esconder isso faria um reenvio parecer uma
    execução.
    """

    receipt_id: uuid.UUID
    technical_principal_ref: str
    operation: CommandOperation
    command_key: str
    outcome_ref: str
    replayed: bool


class CommandReceiptService:
    """Executa cada comando no máximo uma vez por tripla."""

    def __init__(
        self,
        repository: OrchestrationRepository,
        schedule_service: ScheduleService,
        handoff_service: HandoffService,
        export_service: ManualHandoffExportService | None = None,
        return_validation_service: ReturnValidationService | None = None,
        delegation_service: "DelegationService | None" = None,
        control_service: "ControlService | None" = None,
        audit_service: "AuditService | None" = None,
    ) -> None:
        self._delegation_service = delegation_service
        self._control_service = control_service
        self._audit_service = audit_service
        self._repository = repository
        self._schedule_service = schedule_service
        self._handoff_service = handoff_service
        self._export_service = export_service
        self._return_validation_service = return_validation_service

    def _exigir_export(self) -> ManualHandoffExportService:
        if self._export_service is None:
            raise OrchestrationContractViolationError(
                message="serviço de exportação não configurado nesta composição"
            )
        return self._export_service

    def _exigir_validacao(self) -> ReturnValidationService:
        if self._return_validation_service is None:
            raise OrchestrationContractViolationError(
                message="serviço de validação de retorno não configurado nesta composição"
            )
        return self._return_validation_service

    # --- comandos do vocabulário fechado -----------------------------------

    def create_schedule_once(
        self,
        *,
        technical_principal_ref: str,
        command_key: str,
        draft: ScheduleDraft,
        execution_mode: HandoffMode = HandoffMode.MANUAL_HANDOFF,
    ) -> CommandOutcome:
        """Cria o trabalho uma única vez por tripla.

        O `control_principal_ref` do Schedule é o principal técnico que
        emitiu o comando (addendum §1): quem cria é quem controla.
        """
        schedule_id = uuid.uuid4()
        impressao = _impressao_digital(
            {
                "operation": CommandOperation.CREATE_SCHEDULE.value,
                "title": draft.title,
                "execution_mode": execution_mode.value,
                "steps": [
                    {
                        "role": etapa.role,
                        "instruction_ref": etapa.instruction_ref,
                        "expected_output_contract": etapa.expected_output_contract,
                        "context_refs": [ref.as_content() for ref in etapa.context_refs],
                        "constraints": dict(etapa.constraints),
                    }
                    for etapa in draft.steps
                ],
            }
        )

        def efeito() -> None:
            self._schedule_service.create_schedule(
                schedule_id=schedule_id,
                control_principal_ref=technical_principal_ref,
                draft=draft,
                execution_mode=execution_mode,
            )

        return self._executar_uma_vez(
            technical_principal_ref=technical_principal_ref,
            operation=CommandOperation.CREATE_SCHEDULE,
            command_key=command_key,
            proposed_outcome_ref=str(schedule_id),
            request_sha256=impressao,
            efeito=efeito,
        )

    def seal_handoff_once(
        self,
        *,
        technical_principal_ref: str,
        command_key: str,
        schedule_id: uuid.UUID,
        step_id: uuid.UUID,
        sealer_ref: str,
    ) -> CommandOutcome:
        """Sela uma etapa uma única vez por tripla.

        Repetir a mesma chave devolve o mesmo recibo e **não** abre segunda
        tentativa. Retry legítimo usa chave nova e abre tentativa nova, com
        o mesmo `content_sha256`.
        """
        attempt_id = uuid.uuid4()

        def efeito() -> None:
            self._handoff_service.seal_step(
                attempt_id=attempt_id,
                control_principal_ref=technical_principal_ref,
                schedule_id=schedule_id,
                step_id=step_id,
                sealer_ref=sealer_ref,
            )

        return self._executar_uma_vez(
            technical_principal_ref=technical_principal_ref,
            operation=CommandOperation.SEAL_HANDOFF,
            command_key=command_key,
            proposed_outcome_ref=str(attempt_id),
            request_sha256=_impressao_digital(
                {
                    "operation": CommandOperation.SEAL_HANDOFF.value,
                    "schedule_id": str(schedule_id),
                    "step_id": str(step_id),
                    "sealer_ref": sealer_ref,
                }
            ),
            efeito=efeito,
        )

    # --- núcleo ------------------------------------------------------------

    def _executar_uma_vez(
        self,
        *,
        technical_principal_ref: str,
        operation: CommandOperation,
        command_key: str,
        proposed_outcome_ref: str,
        request_sha256: str,
        efeito: Callable[[], None],
    ) -> CommandOutcome:
        """Reivindica a tripla; só quem reivindicou produz o efeito.

        No replay, a impressão digital do recibo existente é comparada com
        a do pedido atual. Divergência é 409, e não a devolução silenciosa
        do recurso antigo:

        ```text
        SAME_COMMAND_KEY + DIFFERENT_REQUEST = CONFLICT
        ```
        """
        if not technical_principal_ref.strip():
            raise OrchestrationContractViolationError(
                message="technical_principal_ref não pode ser vazio"
            )
        if len(technical_principal_ref) > MAX_REF_LENGTH:
            raise OrchestrationContractViolationError(
                message=f"technical_principal_ref excede {MAX_REF_LENGTH} caracteres"
            )
        if not command_key.strip():
            raise OrchestrationContractViolationError(message="command_key não pode ser vazia")
        if len(command_key) > MAX_COMMAND_KEY_LENGTH:
            raise OrchestrationContractViolationError(
                message=f"command_key excede {MAX_COMMAND_KEY_LENGTH} caracteres"
            )

        recibo, reivindicado = self._repository.claim_command(
            technical_principal_ref=technical_principal_ref,
            operation=operation.value,
            command_key=command_key,
            proposed_outcome_ref=proposed_outcome_ref,
            request_sha256=request_sha256,
        )
        if not reivindicado and recibo.request_sha256 != request_sha256:
            # Recibo histórico (sem impressão) também cai aqui: sem saber
            # que requisição o originou, devolvê-lo seria afirmar uma
            # equivalência não verificada.
            raise OrchestrationLifecycleViolationError(
                message=(
                    "command_key já usada para uma requisição diferente; "
                    "use chave nova para um pedido novo"
                ),
                detail={"operation": operation.value},
            )
        if reivindicado:
            efeito()
        return CommandOutcome(
            receipt_id=recibo.id,
            technical_principal_ref=recibo.technical_principal_ref,
            operation=operation,
            command_key=recibo.command_key,
            outcome_ref=recibo.outcome_ref,
            replayed=not reivindicado,
        )

    # --- E7.2 -------------------------------------------------------------

    def export_handoff_once(
        self,
        *,
        technical_principal_ref: str,
        command_key: str,
        schedule_id: uuid.UUID,
        step_id: uuid.UUID,
        sealer_ref: str,
    ) -> tuple[CommandOutcome, ExportOutcome | None]:
        """Exporta uma etapa uma única vez por tripla.

        Operação **própria** (`EXPORT_HANDOFF`), distinta de `SEAL_HANDOFF`:
        transporte e transições são efeito maior que selamento, e reusar a
        chave da E7.1 faria um replay de selamento devolver um repasse que
        nunca ocorreu.

        ```text
        SEAL_HANDOFF != EXPORT_HANDOFF
        SAME_COMMAND_KEY != RETRY
        ```

        No replay o efeito não roda de novo — por isso o segundo elemento
        é `None`. O chamador reconstrói a resposta a partir do recibo, e
        nunca de uma exportação inventada.
        """
        attempt_id = uuid.uuid4()
        resultado: dict[str, ExportOutcome] = {}

        def efeito() -> None:
            resultado["saida"] = self._exigir_export().export_step(
                attempt_id=attempt_id,
                control_principal_ref=technical_principal_ref,
                schedule_id=schedule_id,
                step_id=step_id,
                sealer_ref=sealer_ref,
            )

        recibo = self._executar_uma_vez(
            technical_principal_ref=technical_principal_ref,
            operation=CommandOperation.EXPORT_HANDOFF,
            command_key=command_key,
            proposed_outcome_ref=str(attempt_id),
            request_sha256=_impressao_digital(
                {
                    "operation": CommandOperation.EXPORT_HANDOFF.value,
                    "schedule_id": str(schedule_id),
                    "step_id": str(step_id),
                    "sealer_ref": sealer_ref,
                }
            ),
            efeito=efeito,
        )
        return recibo, resultado.get("saida")

    def import_return_once(
        self,
        *,
        technical_principal_ref: str,
        command_key: str,
        schedule_id: uuid.UUID,
        step_id: uuid.UUID,
        attempt_id: uuid.UUID,
        raw: RawReturn,
        attribution: DeclaredAttribution,
    ) -> tuple[CommandOutcome, ReturnOutcome | None]:
        """Importa um retorno uma única vez por tripla.

        O `outcome_ref` é o próprio `attempt_id`, que aqui vem do chamador
        e não é gerado: o efeito recai sobre uma tentativa que já existe.
        É o que permite detectar reuso da mesma chave para tentativa
        diferente — o recibo recuperado apontaria para outra tentativa, e
        o chamador recusa em vez de devolver o recurso errado.
        """
        resultado: dict[str, ReturnOutcome] = {}

        def efeito() -> None:
            resultado["saida"] = self._exigir_validacao().import_return(
                control_principal_ref=technical_principal_ref,
                schedule_id=schedule_id,
                step_id=step_id,
                attempt_id=attempt_id,
                raw=raw,
                attribution=attribution,
            )

        recibo = self._executar_uma_vez(
            technical_principal_ref=technical_principal_ref,
            operation=CommandOperation.IMPORT_RETURN,
            command_key=command_key,
            proposed_outcome_ref=str(attempt_id),
            request_sha256=_impressao_digital(
                {
                    "operation": CommandOperation.IMPORT_RETURN.value,
                    "schedule_id": str(schedule_id),
                    "step_id": str(step_id),
                    "attempt_id": str(attempt_id),
                    "media_type": raw.media_type,
                    "content_sha256": _digest_de_conteudo(raw.content),
                    "declared_output_ref": raw.declared_output_ref,
                    "declared_provider_id": attribution.declared_provider_id,
                    "declared_model_id": attribution.declared_model_id,
                    "declared_instance_id": attribution.declared_instance_id,
                },
            ),
            efeito=efeito,
        )
        return recibo, resultado.get("saida")

    # --- E7.3 --------------------------------------------------------------

    def grant_delegation_once(
        self,
        *,
        technical_principal_ref: str,
        command_key: str,
        schedule_id: uuid.UUID,
        step_id: uuid.UUID,
        valid_until: "datetime",
    ) -> "tuple[CommandOutcome, DelegationView | None]":
        """Concede delegação uma única vez por tripla."""
        if self._delegation_service is None:
            raise OrchestrationContractViolationError(
                message="serviço de delegação não configurado nesta composição"
            )
        delegation_id = uuid.uuid4()
        saida: dict[str, object] = {}

        def efeito() -> None:
            saida["v"] = self._delegation_service.grant(  # type: ignore[union-attr]
                control_principal_ref=technical_principal_ref,
                schedule_id=schedule_id,
                step_id=step_id,
                valid_until=valid_until,
                delegation_id=delegation_id,
            )

        recibo = self._executar_uma_vez(
            technical_principal_ref=technical_principal_ref,
            operation=CommandOperation.GRANT_DELEGATION,
            command_key=command_key,
            proposed_outcome_ref=str(delegation_id),
            request_sha256=_impressao_digital(
                {
                    "operation": CommandOperation.GRANT_DELEGATION.value,
                    "schedule_id": str(schedule_id),
                    "step_id": str(step_id),
                    "valid_until": valid_until.isoformat(),
                }
            ),
            efeito=efeito,
        )
        return recibo, saida.get("v")  # type: ignore[return-value]

    def revoke_delegation_once(
        self,
        *,
        technical_principal_ref: str,
        command_key: str,
        schedule_id: uuid.UUID,
        step_id: uuid.UUID,
        delegation_id: uuid.UUID,
    ) -> "tuple[CommandOutcome, DelegationView | None]":
        if self._delegation_service is None:
            raise OrchestrationContractViolationError(
                message="serviço de delegação não configurado nesta composição"
            )
        saida: dict[str, object] = {}

        def efeito() -> None:
            saida["v"] = self._delegation_service.revoke(  # type: ignore[union-attr]
                control_principal_ref=technical_principal_ref,
                schedule_id=schedule_id,
                delegation_id=delegation_id,
            )

        recibo = self._executar_uma_vez(
            technical_principal_ref=technical_principal_ref,
            operation=CommandOperation.REVOKE_DELEGATION,
            command_key=command_key,
            proposed_outcome_ref=str(delegation_id),
            request_sha256=_impressao_digital(
                {
                    "operation": CommandOperation.REVOKE_DELEGATION.value,
                    "schedule_id": str(schedule_id),
                    "step_id": str(step_id),
                    "delegation_id": str(delegation_id),
                }
            ),
            efeito=efeito,
        )
        return recibo, saida.get("v")  # type: ignore[return-value]

    def control_schedule_once(
        self,
        *,
        technical_principal_ref: str,
        command_key: str,
        schedule_id: uuid.UUID,
        action: str,
        stop_condition_category: "StopConditionCategory | None",
    ) -> "tuple[CommandOutcome, ControlOutcome | None]":
        """Uma operação para as quatro ações; a ação entra na digital.

        ```text
        SAME_COMMAND_KEY + DIFFERENT_ACTION = CONFLICT
        ```
        """
        if self._control_service is None:
            raise OrchestrationContractViolationError(
                message="serviço de controle não configurado nesta composição"
            )
        saida: dict[str, object] = {}

        def efeito() -> None:
            saida["v"] = self._control_service.apply(  # type: ignore[union-attr]
                control_principal_ref=technical_principal_ref,
                schedule_id=schedule_id,
                action=action,
                stop_condition_category=stop_condition_category,
            )

        recibo = self._executar_uma_vez(
            technical_principal_ref=technical_principal_ref,
            operation=CommandOperation.CONTROL_SCHEDULE,
            command_key=command_key,
            proposed_outcome_ref=str(schedule_id),
            request_sha256=_impressao_digital(
                {
                    "operation": CommandOperation.CONTROL_SCHEDULE.value,
                    "schedule_id": str(schedule_id),
                    "action": action,
                    "stop_condition_category": (
                        stop_condition_category.value if stop_condition_category else None
                    ),
                }
            ),
            efeito=efeito,
        )
        return recibo, saida.get("v")  # type: ignore[return-value]

    def issue_audit_opinion_once(
        self,
        *,
        technical_principal_ref: str,
        command_key: str,
        schedule_id: uuid.UUID,
        attempt_id: uuid.UUID,
        opinion: "AuditOpinionKind",
        reason_codes: tuple[str, ...],
        auditor_execution_ref: str,
    ) -> "tuple[CommandOutcome, AuditOpinionView | None]":
        if self._audit_service is None:
            raise OrchestrationContractViolationError(
                message="serviço de auditoria não configurado nesta composição"
            )
        saida: dict[str, object] = {}

        def efeito() -> None:
            saida["v"] = self._audit_service.issue(  # type: ignore[union-attr]
                control_principal_ref=technical_principal_ref,
                schedule_id=schedule_id,
                attempt_id=attempt_id,
                opinion=opinion,
                reason_codes=reason_codes,
                auditor_execution_ref=auditor_execution_ref,
            )

        recibo = self._executar_uma_vez(
            technical_principal_ref=technical_principal_ref,
            operation=CommandOperation.ISSUE_AUDIT_OPINION,
            command_key=command_key,
            proposed_outcome_ref=str(attempt_id),
            request_sha256=_impressao_digital(
                {
                    "operation": CommandOperation.ISSUE_AUDIT_OPINION.value,
                    "schedule_id": str(schedule_id),
                    "attempt_id": str(attempt_id),
                    "opinion": opinion.value,
                    "reason_codes": sorted(reason_codes),
                    "auditor_execution_ref": auditor_execution_ref,
                }
            ),
            efeito=efeito,
        )
        return recibo, saida.get("v")  # type: ignore[return-value]
