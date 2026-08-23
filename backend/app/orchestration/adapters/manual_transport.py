"""
`ManualTransport` — `D2 = MANUAL`, e manual é literal.

```text
NO_NETWORK | NO_SDK | NO_CREDENTIAL | NO_QUEUE | NO_WORKER | NO_SUBPROCESS
```

O operador humano leva o envelope à IA e traz o retorno. O adaptador
apenas devolve o que já foi selado e aceita explicitamente o que o
cliente entregou.

`receive()` levanta: nesta entrega **não existe** canal por onde um
retorno chegue sozinho. O retorno chega pelo endpoint de importação, com
o conteúdo no corpo da requisição, e é o serviço que o valida. Um
adaptador que devolvesse algo aqui estaria inventando transporte.

```text
MANUAL_TRANSPORT_HAS_NO_INBOUND_CHANNEL = TRUE
```
"""

import uuid

from app.orchestration.ports.transport import ExportedHandoff, RawReturn


class ManualTransportInboundUnavailableError(RuntimeError):
    """Não há canal de entrada no transporte manual."""


class ManualTransport:
    """Transporte manual. Serializa o já selado; nada mais."""

    mode = "manual_handoff"

    def export(self, handoff: ExportedHandoff) -> ExportedHandoff:
        """Devolve o repasse tal como selado.

        Não abre arquivo, socket, subprocesso ou conexão. A ausência de
        efeito é o comportamento correto: quem transporta é a pessoa.
        """
        if not isinstance(handoff, ExportedHandoff):
            raise TypeError("export exige um ExportedHandoff congelado")
        return handoff

    def receive(self, *, attempt_id: uuid.UUID) -> RawReturn:
        raise ManualTransportInboundUnavailableError(
            "transporte manual não possui canal de entrada; o retorno chega "
            f"pelo endpoint de importação (attempt_id={attempt_id})"
        )
