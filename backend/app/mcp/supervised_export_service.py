"""
`SupervisedAutomaticHandoffExportService` — exportação por MCP.

```text
MCP_DISPATCH != MANUAL_HANDOFF
SUPERVISED_EXPORT != MANUAL_EXPORT
```

Irmão do `ManualHandoffExportService`, **não** um decorador dele.
Delegar ao manual traria junto três coisas que descrevem um despacho que
não aconteceu:

```text
ensure_manual_profile   -> perfil de conexao MANUAL
manual_attribution(...) -> atribuicao MANUAL no recibo de execucao
self._transport.export  -> transporte MANUAL externo
```

O recibo de execução é a resposta à pergunta "quem executou isto". Gravar
`manual_attribution` para um despacho que uma IA pediu por MCP não é
imprecisão de rótulo: é a auditoria afirmando que houve operador humano
no ponto onde não houve.

```text
MANUAL_ATTRIBUTION_FOR_AUTOMATIC_DISPATCH = FABRICATED_OPERATOR
```

## O que é reusado

Só o neutro: `OrchestrationRepository` para locks e transições,
`HandoffService.build_envelope_content` e `seal_step_for_export` — o
produtor único de Attempt e recibo de selamento continua sendo ele.

`SEAL_STEP_SEMANTICS = FROZEN_AT_E7_1` permanece intacto: nenhuma
asserção do fluxo manual muda, porque nenhuma linha dele é tocada.

## Onde o G3 entra

Este serviço é invocado **dentro** do callback de
`CommandReceiptService.export_handoff_once`, ou seja, depois do claim e
na mesma transação. O G3 roda aqui, antes de qualquer selo:

```text
claim -> [ G3 -> seal_step_for_export -> transicoes ] -> commit
```

G3 bloqueado levanta daqui. A exceção atravessa `_executar_uma_vez`, o
claim é revertido e a `command_key` **não** é consumida — o pedido pode
ser reapresentado quando a proteção permitir.

```text
BLOCKED_G3 -> ROLLBACK_CLAIM · KEY_STAYS_FREE · ZERO_ATTEMPT
```

Consumir a chave num bloqueio transformaria uma recusa temporária em
recusa permanente para aquela intenção.

## Sem transporte externo

O envelope é **devolvido** ao chamador MCP, não empurrado por um
transporte. Quem pediu já está do outro lado da conexão: o despacho é a
própria resposta.

```text
RESPONSE_IS_THE_DISPATCH · NO_SECOND_CHANNEL
```
"""

import uuid
from dataclasses import dataclass
from typing import Any, Protocol

from app.orchestration.models.enums import HandoffMode, StepState
from app.orchestration.protection.vocabulary import GatePosition, ProtectionOutcome


class HandoffBlockedError(Exception):
    """Proteção humana bloqueou dentro do callback. Reverte tudo."""

    def __init__(self, *, gate_position: GatePosition, fingerprint: str) -> None:
        super().__init__(f"handoff bloqueado em {gate_position.value}")
        self.gate_position = gate_position
        self.fingerprint = fingerprint


@dataclass(frozen=True)
class SupervisedExportOutcome:
    """O que a exportação supervisionada produz.

    Sem instância ORM, sem envelope bruto persistido, sem prompt.
    """

    attempt_id: uuid.UUID
    attempt_number: int
    receipt_id: uuid.UUID
    content_sha256: str
    step_state: StepState
    handoff_mode: HandoffMode

    def __post_init__(self) -> None:
        if self.handoff_mode is not HandoffMode.SUPERVISED_AUTOMATIC_HANDOFF:
            raise ValueError("exportação por MCP registra apenas supervised_automatic_handoff")


class ProtecaoPort(Protocol):
    """Composição da E7.4-1. O gate não é reimplementado aqui."""

    def aplicar(self, **kwargs: Any) -> Any: ...


class SupervisedAutomaticHandoffExportService:
    """Exporta uma etapa sob supervisão automática, dentro do claim."""

    def __init__(
        self,
        repository: Any,
        handoff_service: Any,
        *,
        protecao: ProtecaoPort,
        operacao: Any,
        objetivo_por_step: Any,
        connection_receipts: Any | None = None,
    ) -> None:
        self._repository = repository
        self._handoff_service = handoff_service
        self._protecao = protecao
        self._operacao = operacao
        self._objetivo = objetivo_por_step
        self._connection_receipts = connection_receipts

    def export_step(
        self,
        *,
        attempt_id: uuid.UUID,
        control_principal_ref: str,
        schedule_id: uuid.UUID,
        step_id: uuid.UUID,
        sealer_ref: str,
        authorization: Any | None = None,
    ) -> SupervisedExportOutcome:
        """Assinatura compatível com o `ExportServicePort` neutro.

        `authorization` existe para satisfazer o Protocol e é ignorada: a
        autorização deste caminho é o G3, aplicado aqui dentro.
        """
        del authorization

        etapa = self._repository.lock_step(
            control_principal_ref=control_principal_ref,
            schedule_id=schedule_id,
            step_id=step_id,
        )
        if etapa is None:
            raise LookupError("etapa inexistente neste Schedule sob este principal")

        # G3 ANTES do selo. Depois dele existiria Attempt de um despacho
        # que a proteção recusou.
        decisao = self._protecao.aplicar(
            objective=self._objetivo(schedule_id=schedule_id, step_id=step_id),
            gate_position=GatePosition.G3,
            principal_ref=control_principal_ref,
            operation=self._operacao,
            schedule_id=schedule_id,
            step_id=step_id,
            attempt_id=attempt_id,
        )
        if decisao.outcome is not ProtectionOutcome.ALLOWED:
            raise HandoffBlockedError(
                gate_position=GatePosition.G3,
                fingerprint=decisao.decision_fingerprint,
            )

        selado = self._handoff_service.seal_step_for_export(
            attempt_id=attempt_id,
            control_principal_ref=control_principal_ref,
            schedule_id=schedule_id,
            step_id=step_id,
            sealer_ref=sealer_ref,
        )

        # Transições na MESMA transação, e o estado confirmado é
        # AWAITING_RETURN: DISPATCHED é um instante, não um lugar onde o
        # sistema descansa. Mesma disciplina do manual, sem reusar o
        # manual.
        self._repository.set_step_state(
            control_principal_ref=control_principal_ref,
            schedule_id=schedule_id,
            step_id=step_id,
            state=StepState.AWAITING_RETURN,
        )

        return SupervisedExportOutcome(
            attempt_id=selado.attempt_id,
            attempt_number=selado.attempt_number,
            receipt_id=selado.receipt_id,
            content_sha256=selado.content_sha256,
            step_state=StepState.AWAITING_RETURN,
            handoff_mode=HandoffMode.SUPERVISED_AUTOMATIC_HANDOFF,
        )
