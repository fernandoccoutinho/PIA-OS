"""
`DenyAllHumanGate` — a única implementação produtiva da porta (`E7.3`).

```text
HUMAN_GATE_IN_PRODUCTION = DENY_ALL_UNTIL_E8
TECHNICAL_PRINCIPAL_SATISFIES_HUMAN_GATE = FALSE
```

Nega sempre, e a razão é sempre a mesma: não existe autoridade humana
neste sistema até a E8. Um Schedule que declara
`pia.gate.required = service_delegation_and_human` **não despacha** nesta
entrega — e isso é o resultado correto, não um bug a contornar.

Nenhum dublê concedente vive em `app/`. Um adaptador permissivo aqui
seria um bypass reutilizável em produção, bastando trocar uma linha de
composição. O dublê que concede existe apenas em `tests/`, e a guarda
estática mede que ele não é importado por nada em `app/`.
"""

import uuid

from app.orchestration.models.enums import GateReasonCode
from app.orchestration.ports.gate import GateDecision


class DenyAllHumanGate:
    """Porta humana indisponível — recusa tipada, sem exceção."""

    def authorize(
        self,
        *,
        gate_scope: str,
        schedule_id: uuid.UUID,
        step_id: uuid.UUID,
        content_sha256: str,
    ) -> GateDecision:
        """Recusa, sem consultar nada e sem efeito colateral.

        Devolve decisão em vez de levantar: uma recusa esperada não é
        erro, e transformá-la em exceção faria o chamador tratar o
        comportamento normal como falha.
        """
        del gate_scope, schedule_id, step_id, content_sha256
        return GateDecision(granted=False, reason_code=GateReasonCode.HUMAN_AUTHORITY_UNAVAILABLE)
