"""
`DeterministicTestTransport` — dublê de porta para provas de serviço.

```text
TEST_ADAPTER_NOT_REGISTERED_IN_PRODUCTION_ROUTER = TRUE
```

Vive em `app/` e não em `tests/` porque implementa um Protocol de `app/` e
precisa acompanhar a porta quando ela mudar; um dublê no diretório de
testes se desatualiza em silêncio e passa a provar a si mesmo.

A guarda estática mede que o router de produção **não** o importa. Ele
não faz I/O: devolve fixtures configuradas na construção.
"""

import uuid

from app.orchestration.ports.transport import ExportedHandoff, RawReturn


class DeterministicTestTransport:
    """Porta com retornos pré-configurados por tentativa."""

    mode = "manual_handoff"

    def __init__(self, retornos: dict[uuid.UUID, RawReturn] | None = None) -> None:
        self._retornos: dict[uuid.UUID, RawReturn] = dict(retornos or {})
        self.exportados: list[ExportedHandoff] = []

    def configurar(self, *, attempt_id: uuid.UUID, retorno: RawReturn) -> None:
        self._retornos[attempt_id] = retorno

    def export(self, handoff: ExportedHandoff) -> ExportedHandoff:
        self.exportados.append(handoff)
        return handoff

    def receive(self, *, attempt_id: uuid.UUID) -> RawReturn:
        if attempt_id not in self._retornos:
            raise KeyError(f"nenhum retorno configurado para {attempt_id}")
        return self._retornos[attempt_id]
