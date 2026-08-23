"""
Porta de transporte de repasse (`E7.2`).

```text
PORT_KNOWS_NOTHING_ABOUT = FastAPI, SQLAlchemy, rede, credencial
D2 = MANUAL
D4 = PORT_ONLY
```

Objetos puros e congelados. Nenhum deles carrega credencial, token,
header, sessão ou cliente de rede — se carregassem, a porta deixaria de
ser fronteira e viraria um lugar por onde o segredo passa.

```text
PROVIDER_CREDENTIAL NOT IN {envelope, prompt, log, persistência comum}
```

`RawReturn` é **transitório** por construção: entra para ser medido e sai.
Nada aqui é persistido, e a ausência de qualquer método de serialização
para banco é deliberada.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.orchestration.schemas.envelope import EnvelopeContent


@dataclass(frozen=True)
class ExportedHandoff:
    """O que atravessa a fronteira num repasse manual.

    Contém o envelope exato que foi selado e os metadados do recibo — nunca
    instrução ou contexto embutido, apenas as referências já declaradas.
    """

    schedule_id: uuid.UUID
    step_id: uuid.UUID
    attempt_id: uuid.UUID
    attempt_number: int
    receipt_id: uuid.UUID
    content_sha256: str
    sealed_at: datetime
    envelope: EnvelopeContent

    def __post_init__(self) -> None:
        if self.attempt_number < 1:
            raise ValueError("attempt_number começa em 1")
        if self.envelope.content_sha256() != self.content_sha256:
            raise ValueError(
                "content_sha256 não corresponde ao envelope exportado; "
                "o repasse descreveria conteúdo diferente do selado"
            )


@dataclass(frozen=True)
class RawReturn:
    """Retorno cru de uma IA. **Não confiável e não persistido.**

    ```text
    AI_OUTPUT != CONTROL_CHANNEL
    RAW_RETURN -> TRANSIENT
    ```

    O `content` existe apenas durante a validação. Nenhuma tabela, log ou
    resposta de consulta o reexibe.
    """

    media_type: str
    content: str
    declared_output_ref: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.media_type, str) or not self.media_type.strip():
            raise ValueError("media_type é obrigatório")
        if not isinstance(self.content, str):
            raise ValueError("content deve ser str")

    def __repr__(self) -> str:
        """Repr sem o conteúdo — `repr` vaza para log e traceback.

        Um `dataclass` comum imprimiria a resposta inteira no primeiro
        `logger.exception`, e a proibição de conteúdo bruto em log seria
        derrotada por um detalhe de formatação.
        """
        return (
            f"RawReturn(media_type={self.media_type!r}, "
            f"content=<{len(self.content)} chars redacted>, "
            f"declared_output_ref={self.declared_output_ref!r})"
        )


class HandoffTransportPort(Protocol):
    """Exportar um repasse selado e receber o retorno correspondente.

    Duas operações, nenhuma delas assíncrona e nenhuma delas com efeito
    externo obrigatório: o adaptador manual satisfaz o Protocol sem tocar
    em rede, e é isso que torna a porta honesta na E7.2.
    """

    def export(self, handoff: ExportedHandoff) -> ExportedHandoff:
        """Entrega o repasse ao operador humano e devolve o que foi entregue."""
        ...

    def receive(self, *, attempt_id: uuid.UUID) -> RawReturn:
        """Obtém o retorno correspondente a uma tentativa."""
        ...
