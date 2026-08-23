"""
`GateAuthorizationPort` — porta de autorização humana (`E7.3`).

```text
SERVICE_DELEGATION != HUMAN_APPROVAL
TECHNICAL_PRINCIPAL != HUMAN_IDENTITY
HUMAN_GATE_IN_PRODUCTION = DENY_ALL_UNTIL_E8
```

Porta, não capacidade. A E7.3 define o **contrato** de autorização
humana e nada mais: identidade, MFA, step-up e aprovação são E8.

A composição de produção nega sempre. Isso não é limitação a contornar —
é o comportamento correto enquanto não existe autoridade humana no
sistema. Um principal técnico satisfazendo a porta seria exatamente a
confusão que o programa proíbe, e o mutante `M-g2` existe para matar
qualquer versão em que isso passe.
"""

import uuid
from dataclasses import dataclass
from typing import Protocol

from app.orchestration.models.enums import GateReasonCode


@dataclass(frozen=True)
class GateDecision:
    """Veredito da porta. `reason_code` é enum, nunca string livre.

    String livre num código de recusa vira o lugar onde alguém escreve
    explicação — e explicação num campo comparado por igualdade deixa de
    ser comparável.
    """

    granted: bool
    reason_code: GateReasonCode

    def __post_init__(self) -> None:
        if self.granted and self.reason_code is not GateReasonCode.AUTHORIZED:
            raise ValueError("decisão concedida exige reason_code AUTHORIZED")
        if not self.granted and self.reason_code is GateReasonCode.AUTHORIZED:
            raise ValueError("decisão negada não pode alegar AUTHORIZED")


class GateAuthorizationPort(Protocol):
    """Autoriza — ou não — o componente humano de um gate."""

    def authorize(
        self,
        *,
        gate_scope: str,
        schedule_id: uuid.UUID,
        step_id: uuid.UUID,
        content_sha256: str,
    ) -> GateDecision:
        """Decide sobre este conteúdo exato, desta etapa, deste trabalho."""
        ...
