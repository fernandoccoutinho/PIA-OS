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

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, text
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
    primeiro) — ver `RelationshipRepository.add_relationship` — **e
    também garantida estruturalmente no banco** (correção E3.5.1,
    débito C2): `ck_relationships_symmetric_canonical_order` rejeita
    qualquer linha `RELATED_TO` onde `source_coid >= target_coid`,
    independentemente do caminho de escrita — um bypass direto do
    repositório (ORM/SQL cru) não consegue armazenar `(A,B,RELATED_TO)`
    e `(B,A,RELATED_TO)` simultaneamente, porque a forma não-canônica
    é sempre rejeitada antes mesmo de chegar à checagem de unicidade.
    `SYMMETRIC_UNIQUENESS = DB_LEVEL` (não apenas por convenção do
    caminho canônico do repositório).

    Append-only: `RelationshipRepository.update()`/`.delete()` sempre
    rejeitam (mesma disciplina de `LineageEdge`/`TransformationRecord`).
    "Remoção" lógica é `retired_at` (soft-retire) — a relação
    permanece um fato histórico auditável, nunca apagada (§12 do
    módulo E3.5: "alterar/remover uma relação não deve apagar um fato
    histórico").

    Unicidade (correção E3.5.1, débito C1): vale apenas para relações
    **vigentes** (`retired_at IS NULL`) — índice único parcial, não
    `UniqueConstraint` incondicional. Isso permite exatamente o ciclo
    de vida aprovado ("retirar a antiga, criar uma nova"):
    `create(A,B,SUPPORTS)` → `retire(old)` → `create(A,B,SUPPORTS)`
    novamente é permitido; a linha antiga continua na tabela,
    auditável, apenas fora do escopo da constraint de unicidade.
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
        CheckConstraint(
            "relationship_type != 'related_to' OR source_coid < target_coid",
            name="ck_relationships_symmetric_canonical_order",
        ),
        Index(
            "uq_relationships_active_source_target_type",
            "source_coid",
            "target_coid",
            "relationship_type",
            unique=True,
            postgresql_where=text("retired_at IS NULL"),
            sqlite_where=text("retired_at IS NULL"),
        ),
    )
    """`CheckConstraint` (self-link): defesa em profundidade — o guard
    de domínio (`RelationshipEngine.create`) já rejeita antes de
    chegar ao banco.

    `CheckConstraint` (`ck_relationships_symmetric_canonical_order`,
    novo em E3.5.1): garante estruturalmente que uma linha `RELATED_TO`
    só pode existir na forma canônica (`source_coid < target_coid`) —
    fecha o débito C2: a garantia de simetria deixa de depender
    exclusivamente da normalização feita pelo repositório.

    `Index` único parcial (`uq_relationships_active_source_target_type`,
    substituiu a `UniqueConstraint` incondicional original em E3.5.1,
    débito C1): a mesma tripla `(source_coid, target_coid,
    relationship_type)` não pode ser registrada duas vezes **entre
    relações vigentes** (`retired_at IS NULL`) — uma relação retirada
    não bloqueia a criação de uma nova vigente com os mesmos
    endpoints/tipo. Suportado nativamente por PostgreSQL
    (`postgresql_where`) e SQLite (`sqlite_where`, usado nos testes
    unitários).
    """
