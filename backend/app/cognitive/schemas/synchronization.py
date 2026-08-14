"""
Formato de sincronização de patrimônio cognitivo (`E3.11`/`LIB-11`).

```text
SYNCHRONIZATION = TRANSMISSION OF COGNITIVE PATRIMONY
SYNCHRONIZATION != COPY CURRENT ROWS
TRANSMISSION != OVERWRITE
```

O pacote transporta **identidade e história**, não um retrato do estado
atual. Por isso todo identificador persistente viaja como está — COID,
CLID e os ids de cada registro — e o import é proibido de regenerar
qualquer um deles: depois de `EXPORT(A) → IMPORT(B)` o patrimônio em
`B` é *o mesmo* patrimônio, não "objetos equivalentes novos".

Determinismo e ausência de perda são requisitos, não desejos:

```text
deterministic serialization   UUID round-trip lossless
explicit format version       datetime round-trip lossless
NULL preservation             enum round-trip lossless
```

O envelope é versionado (`schema_version`) e provider-neutral: nada no
formato depende de OpenAI, Anthropic, Gemini, Cohere ou qualquer outro
— `provider_id`/`model_id` viajam como as strings opcionais que já
eram. Nenhum transcript, prompt ou payload é exportado, porque `E3` não
os armazena (`TRANSCRIPT_AUTO_STORAGE = NONE`), e referências externas
(`payload_ref`, `evidence_refs`, `source_ref`) viajam **como
referência** — o conteúdo apontado nunca é copiado
(`ARTIFACT_STORAGE = DEFERRED`).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, StrEnum
from typing import Any

import sqlalchemy as sa

#: Identificador do formato. Muda apenas se a semântica do envelope
#: mudar de forma incompatível.
SYNC_FORMAT = "pia-os.cognitive-sync"

#: Versão do schema do envelope. Um pacote de versão desconhecida é
#: rejeitado — nunca interpretado "na melhor das hipóteses".
SYNC_SCHEMA_VERSION = "1.0"

#: Seções do pacote, na ordem de dependência derivada das FKs reais
#: (`Base.metadata.sorted_tables`), não por intuição.
SECTION_BY_TABLE: dict[str, str] = {
    "cognitive_objects": "objects",
    "transformation_records": "transformations",
    "causal_histories": "causal_histories",
    "lineage_edges": "lineage",
    "provenance_records": "provenance",
    "relationships": "relationships",
    "causal_history_events": "causal_events",
}


class SyncStatus(StrEnum):
    """Resultado de um import.

    `CONFLICT` não é falha de execução: é resultado válido do contrato
    (`CONFLICT DETECTION != CONFLICT RESOLUTION`).
    """

    APPLIED = "applied"
    CONFLICT = "conflict"


@dataclass(frozen=True)
class SyncConflict:
    """Colisão de identidade: **mesmo identificador persistente, estado
    estrutural diferente**.

    Carrega as duas representações — a do pacote e a do destino — de
    modo que nenhum dos lados desapareça do diagnóstico. Nada aqui
    escolhe um vencedor: não há "mais novo vence", prioridade de
    provider, score ou timestamp.
    """

    section: str
    entity_id: uuid.UUID
    incoming: dict[str, Any]
    existing: dict[str, Any]

    @property
    def differing_fields(self) -> tuple[str, ...]:
        """Campos em que as duas representações divergem — evidência
        localizada, não apenas "há conflito"."""
        keys = set(self.incoming) | set(self.existing)
        return tuple(
            sorted(key for key in keys if self.incoming.get(key) != self.existing.get(key))
        )


@dataclass(frozen=True)
class SyncReport:
    """Resultado transitório de um import. Não persistido.

    `overwrite_count` existe para ser sempre zero e para que isso seja
    **verificável**: um import ou aplica registros novos, ou não aplica
    nada. Sobrescrever destino nunca é uma das opções.
    """

    conflicts: tuple[SyncConflict, ...] = ()
    applied: dict[str, int] = field(default_factory=dict)
    skipped: dict[str, int] = field(default_factory=dict)
    overwrite_count: int = 0

    @property
    def status(self) -> SyncStatus:
        return SyncStatus.CONFLICT if self.conflicts else SyncStatus.APPLIED

    @property
    def applied_count(self) -> int:
        return sum(self.applied.values())

    @property
    def skipped_count(self) -> int:
        """Registros já presentes e **idênticos** — idempotência, não
        conflito."""
        return sum(self.skipped.values())


# --- Codec ------------------------------------------------------------


def encode_value(value: object) -> Any:
    """Serializa um valor de coluna preservando a informação.

    `UUID` e `datetime` viram texto canônico; enums viram seu **valor**
    (não o nome); `None` continua `None`; JSON já é estrutura Python.
    """
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    return value


def decode_value(column: sa.Column[Any], value: Any) -> Any:
    """Inverte `encode_value` usando o **tipo real da coluna**.

    Decodificar pelo tipo, e não por heurística sobre o conteúdo, é o
    que torna o round-trip verificável: um UUID volta como `UUID`, um
    timestamp volta como `datetime` com fuso, e um enum volta como o
    membro correspondente ao valor persistido.
    """
    if value is None:
        return None
    column_type = column.type
    if isinstance(column_type, sa.Uuid):
        return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))
    if isinstance(column_type, sa.DateTime):
        return value if isinstance(value, datetime) else datetime.fromisoformat(str(value))
    if isinstance(column_type, sa.Enum) and column_type.enum_class is not None:
        return column_type.enum_class(value)
    return value


def encode_row(row: sa.Row[Any]) -> dict[str, Any]:
    return {key: encode_value(value) for key, value in row._mapping.items()}


def canonical_payload(package: dict[str, Any]) -> dict[str, Any]:
    """Conteúdo comparável de um pacote — tudo menos os campos
    puramente transportacionais.

    Só `exported_at` é excluído, e por um motivo verificável: é o
    instante em que o pacote foi gerado, não um fato do patrimônio.
    Dois exports do mesmo patrimônio em momentos diferentes devem ser
    canonicamente iguais; se qualquer outra coisa divergisse, seria
    perda de informação, não ruído de transporte.
    """
    return {key: value for key, value in package.items() if key != "exported_at"}
