"""
TransformationRecord — histórico append-only de transformações
explícitas entre `CognitiveObject`s (`E3.4` / `LIB-04`).

Contrato: `E3_DOMAIN_MODEL_DRAFT.md`, seção "6. TransformationRecord":

```text
TransformationRecord
  transformation_id: UUID
  operation_type: str
  input_refs: list[COID | distinction_id]
  output_refs: list[COID | distinction_id]
  actor_ref: ProvenanceRecord ref
  policy_ref: str?
  declared_preservations: list[str]
  declared_losses: list[str]
  timestamp: datetime
```

Concretizações desta implementação (documentadas, não contradições —
mesmo padrão já usado para `clid` em E3.1 e `transformation_ref` em
E3.3):

- `transformation_id` = `id` (herdado de `BaseModel`/`UUIDMixin`) —
  sem segundo mecanismo de identidade, mesmo padrão de `coid` em
  `CognitiveObject`.
- `timestamp` = `created_at` (herdado de `BaseModel`) — mesmo padrão.
- `actor_ref: ProvenanceRecord ref` é **obrigatório** no Draft, mas
  `ProvenanceRecord` não existe ainda (`E3.6`) — implementado como
  `UUID | None`, nulo até o módulo dono existir. Nenhuma FK para uma
  tabela inexistente.
- `operation_type` é documentado no Draft com "ex.: summarize |
  translate | ..." — uma lista de exemplos, não uma taxonomia fechada
  como `LineageRelation` — implementado como `str` livre (validado
  não-vazio na camada de serviço, `VersionManager`, não aqui).
- `input_refs`/`output_refs` são listas heterogêneas
  (`COID | distinction_id`) — armazenadas como `JSON` (lista de
  strings), não como FK: uma lista polimórfica não seria representável
  por uma FK simples, e `CognitiveDistinction` (o outro tipo possível)
  está `DEFERRED` desde E3.1.

Append-only: nenhum método de update/delete é exposto por
`TransformationRepository` (mesma disciplina de `LineageEdge`,
correção E3.3.1).
"""

import uuid

from sqlalchemy import JSON, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.cognitive.models.enums import TransformationKind
from app.models.base_model import BaseModel


class TransformationRecord(BaseModel):
    """Registro histórico de uma transformação explicitamente
    solicitada/estabelecida entre `CognitiveObject`s — não decide
    sozinho que uma relação causal existe (§21 do módulo E3.4)."""

    __tablename__ = "transformation_records"

    operation_type: Mapped[str] = mapped_column(String(64), nullable=False)
    """Natureza da transformação — vocabulário aberto (ex.: "summarize",
    "translate", "derive"), não uma taxonomia fechada."""

    transformation_kind: Mapped[TransformationKind] = mapped_column(
        SAEnum(
            TransformationKind,
            name="transformation_kind",
            native_enum=False,
            length=16,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    """Distingue `REVISION` de `DERIVATION` (correção E3.4.0) —
    obrigatório: toda transformação criada por `VersionManager` sabe
    explicitamente qual é. Ver `app.cognitive.models.enums.TransformationKind`."""

    input_refs: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    """COIDs (como string) dos `CognitiveObject`s de entrada."""

    output_refs: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    """COIDs (como string) dos `CognitiveObject`s de saída."""

    actor_ref: Mapped[uuid.UUID | None] = mapped_column(nullable=True, default=None)
    """Referência estrutural a um `ProvenanceRecord` futuro (E3.6) —
    nulo nesta fase, nenhuma FK para tabela inexistente."""

    policy_ref: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
    """Referência a uma política — nenhuma política implementada em
    E3 (mesma nota do Draft)."""

    declared_preservations: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    """Declarações do executor sobre o que a transformação preserva —
    não verificado automaticamente (ver docstring do módulo)."""

    declared_losses: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    """Declarações do executor sobre o que a transformação perde/
    descarta — idem, não verificado automaticamente."""

    @property
    def transformation_id(self) -> uuid.UUID:
        """Alias de leitura de `id` — mesmo padrão de `CognitiveObject.coid`."""
        return self.id
