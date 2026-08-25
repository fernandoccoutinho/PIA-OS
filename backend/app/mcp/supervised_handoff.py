"""
`SupervisedAutomaticHandoffService` — despacho MCP, irmão do manual.

```text
MCP_DISPATCH != MANUAL_HANDOFF
```

Este serviço é **irmão**, não substituto: o caminho manual permanece
intocado, com todas as suas asserções. Nenhuma linha do manual foi
alterada, e nenhum núcleo neutro foi extraído — extrair só é permitido se
todas as provas existentes passarem sem mudança de asserção, e a extração
não era necessária para esta entrega.

## Por que nunca `MANUAL_HANDOFF`

`MANUAL_HANDOFF` afirma que um humano olhou e despachou. Registrar
despacho automático sob esse rótulo destruiria a única distinção que
permite auditar depois quem decidiu o quê.

```text
AUTOMATIC_LOGGED_AS_MANUAL = FABRICATED_HUMAN_REVIEW
```

`SUPERVISED_AUTOMATIC_HANDOFF` já existe no enum e já está **fora** de
`EXECUTABLE_HANDOFF_MODES` — o modo não se auto-executa.

## Ordem dos gates

```text
G2 ANTES de entregar o envelope
G3 ANTES de materializar/despachar
BLOCKED -> pausa duravel · ZERO resposta de handoff
```

O bloqueio não devolve envelope vazio nem erro parcial: devolve recusa, e
a pausa é durável. Um envelope entregue junto com um bloqueio seria a
capacidade vazando pelo mesmo ato que a negou.

## Idempotência

`command_key + request_sha256` juntos. A chave sozinha identifica a
intenção; o hash identifica **o que** foi pedido. Mesma chave com pedido
diferente é conflito, não substituição silenciosa.

```text
KEY_WITHOUT_REQUEST_HASH = SILENT_OVERWRITE_OF_A_DIFFERENT_REQUEST
```
"""

import uuid
from dataclasses import dataclass
from typing import Any, Protocol

from app.orchestration.models.enums import HandoffMode
from app.orchestration.protection.vocabulary import GatePosition, ProtectionOutcome


class HandoffBlockedError(Exception):
    """Proteção humana bloqueou. Zero efeito, zero envelope."""

    def __init__(self, *, gate_position: GatePosition, fingerprint: str) -> None:
        super().__init__(f"handoff bloqueado em {gate_position.value}")
        self.gate_position = gate_position
        self.fingerprint = fingerprint


class HandoffConflictError(Exception):
    """Mesma `command_key`, `request_sha256` diferente."""


@dataclass(frozen=True)
class SupervisedHandoffResult:
    """O que sai. Sem envelope bruto, sem prompt, sem contexto."""

    attempt_id: uuid.UUID
    handoff_mode: HandoffMode
    replayed: bool

    def __post_init__(self) -> None:
        if self.handoff_mode is not HandoffMode.SUPERVISED_AUTOMATIC_HANDOFF:
            raise ValueError(
                "despacho MCP registra apenas supervised_automatic_handoff — "
                "marcá-lo como manual fabricaria revisão humana que não houve"
            )


class ProtecaoPort(Protocol):
    """A composição da E7.4-1. O gate não é reimplementado aqui."""

    def aplicar(self, **kwargs: Any) -> Any: ...


class SupervisedAutomaticHandoffService:
    """Despacho supervisionado sob os gates da proteção humana."""

    def __init__(
        self,
        *,
        protecao: ProtecaoPort,
        recibos: Any,
        objetivo_por_step: Any,
        operacao: Any,
    ) -> None:
        self._protecao = protecao
        self._recibos = recibos
        self._objetivo = objetivo_por_step
        self._operacao = operacao

    def exportar(
        self,
        *,
        control_principal_ref: str,
        schedule_id: uuid.UUID,
        step_id: uuid.UUID,
        command_key: str,
        request_sha256: str,
    ) -> SupervisedHandoffResult:
        """G2, envelope, G3, materialização — nesta ordem, sem atalho."""
        if not command_key.strip():
            raise ValueError("command_key é obrigatório")
        if len(request_sha256) != 64:
            raise ValueError("request_sha256 deve ser sha256 hexadecimal")

        objetivo = self._objetivo(schedule_id=schedule_id, step_id=step_id)

        g2 = self._protecao.aplicar(
            objective=objetivo,
            gate_position=GatePosition.G2,
            principal_ref=control_principal_ref,
            operation=self._operacao,
            schedule_id=schedule_id,
            step_id=step_id,
        )
        if g2.outcome is not ProtectionOutcome.ALLOWED:
            raise HandoffBlockedError(
                gate_position=GatePosition.G2, fingerprint=g2.decision_fingerprint
            )

        tentativa = self._recibos.prealocar_tentativa(
            control_principal_ref=control_principal_ref,
            schedule_id=schedule_id,
            step_id=step_id,
            command_key=command_key,
            request_sha256=request_sha256,
        )
        if tentativa.conflito:
            raise HandoffConflictError(
                "command_key já usada com request_sha256 diferente — "
                "substituir silenciosamente apagaria um pedido distinto"
            )
        if tentativa.replayed:
            # Replay devolve o MESMO resultado sem reexecutar o gate de
            # materialização: reexecutar produziria segunda Attempt para a
            # mesma intenção, que é o que a idempotência existe para impedir.
            return SupervisedHandoffResult(
                attempt_id=tentativa.attempt_id,
                handoff_mode=HandoffMode.SUPERVISED_AUTOMATIC_HANDOFF,
                replayed=True,
            )

        g3 = self._protecao.aplicar(
            objective=objetivo,
            gate_position=GatePosition.G3,
            principal_ref=control_principal_ref,
            operation=self._operacao,
            schedule_id=schedule_id,
            step_id=step_id,
            attempt_id=tentativa.attempt_id,
        )
        if g3.outcome is not ProtectionOutcome.ALLOWED:
            raise HandoffBlockedError(
                gate_position=GatePosition.G3, fingerprint=g3.decision_fingerprint
            )

        self._recibos.materializar(
            control_principal_ref=control_principal_ref,
            attempt_id=tentativa.attempt_id,
            handoff_mode=HandoffMode.SUPERVISED_AUTOMATIC_HANDOFF,
        )
        return SupervisedHandoffResult(
            attempt_id=tentativa.attempt_id,
            handoff_mode=HandoffMode.SUPERVISED_AUTOMATIC_HANDOFF,
            replayed=False,
        )
