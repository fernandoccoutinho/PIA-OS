"""
Relationship — relação semântica explícita entre `CognitiveObject`s
distintos (`E3.5` / `LIB-05`).

Distinção obrigatória (§3 do módulo E3.5): `Relationship` responde
"como estes objetos estão relacionados?" (`A SUPPORTS B`,
`A CONTRADICTS B`); `LineageEdge` (E3.3) responde "de qual objeto este
objeto veio?" (`A DERIVED_FROM B`). Taxonomias disjuntas — nenhum
`RelationshipType` se sobrepõe a `LineageRelation`, nenhuma
`LineageEdge` é criada automaticamente por uma `Relationship`, e
vice-versa.

Endpoints: **COID**, não CLID (decisão registrada no
`E3_5_LIB05_RELATIONSHIP_ENGINE.md`, seção "Endpoint Identity") — uma
relação semântica declarada é sobre objetos específicos, não sobre a
continuidade inteira de um patrimônio. Mesmo padrão de
`LineageEdge.parent_coid`/`child_coid`.

COUT-PIA: uma `Relationship` declara exatamente o que seu tipo diz —
nunca implica causalidade, equivalência, identidade, superioridade,
verdade, confiança, importância, qualidade, relevância, substituição,
persistência ou acessibilidade (§4 do módulo). Nenhum campo de
score/ranking existe aqui, nem pode existir.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.cognitive.models.enums import RelationshipType
from app.models.base_model import BaseModel


class Relationship(BaseModel):
    """Relação semântica declarada `source_coid -> target_coid`.

    Direcionalidade por tipo (`RelationshipType.is_symmetric`): para
    tipos direcionados, a ordem dos endpoints é significativa e
    preservada como declarada. Para o único tipo simétrico
    (`RELATED_TO`), a ordem é normalizada na escrita (menor UUID
    primeiro) — ver `RelationshipRepository.add_relationship` — para
    que `(A,B)` e `(B,A)` colidam na mesma constraint de unicidade, em
    vez de duplicar o mesmo fato sob duas linhas diferentes.

    Append-only: `RelationshipRepository.update()`/`.delete()` sempre
    rejeitam (mesma disciplina de `LineageEdge`/`TransformationRecord`).
    "Remoção" lógica é `retired_at` (soft-retire) — a relação
    permanece um fato histórico auditável, nunca apagada (§12 do
    módulo E3.5: "alterar/remover uma relação não deve apagar um fato
    histórico").
    """

    __tablename__ = "relationships"

    source_coid: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cognitive_objects.id"), nullable=False, index=True
    )
    """COID de origem da relação. FK para `cognitive_objects.id` sem
    `ON DELETE CASCADE` — mesma política de `LineageEdge` (soft delete
    de `CognitiveObject` nunca remove a linha física)."""

    target_coid: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cognitive_objects.id"), nullable=False, index=True
    )
    """COID de destino da relação. Mesma política de FK que `source_coid`."""

    relationship_type: Mapped[RelationshipType] = mapped_column(
        SAEnum(
            RelationshipType,
            name="relationship_type",
            native_enum=False,
            length=16,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    """Ver `app.cognitive.models.enums.RelationshipType` — taxonomia
    mínima justificável, disjunta de `LineageRelation`."""

    retired_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    """Soft-retire — `None` enquanto a relação está vigente. Setado
    (nunca revertido) quando a relação é "removida" logicamente; a
    linha nunca é apagada fisicamente (§9, §17 do prompt corretivo de
    E3.4 aplicado aqui por analogia: `SUPERSEDED != DELETED` — aqui,
    `retired != deleted`)."""

    __table_args__ = (
        CheckConstraint("source_coid != target_coid", name="ck_relationships_no_self_link"),
        UniqueConstraint(
            "source_coid",
            "target_coid",
            "relationship_type",
            name="uq_relationships_source_target_type",
        ),
    )
    """`CheckConstraint`: defesa em profundidade contra self-relation —
    o guard de domínio (`RelationshipEngine.create`) já rejeita antes
    de chegar ao banco. `UniqueConstraint`: a mesma tripla
    `(source_coid, target_coid, relationship_type)` não pode ser
    registrada duas vezes — para o tipo simétrico `RELATED_TO`, a
    normalização de ordem na escrita faz esta mesma constraint também
    cobrir `(B,A)` como duplicata de `(A,B)`."""
