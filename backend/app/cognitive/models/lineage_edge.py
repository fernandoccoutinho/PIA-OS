"""
LineageEdge — fundação de linhagem entre `CognitiveObject`s distintos
(`E3.3` / `LIB-03`).

Contrato: `E3_DOMAIN_MODEL_DRAFT.md`, seção "8. LineageEdge". Campos
concretizados para esta implementação: `from_ref`/`to_ref` (tipados
`COID | distinction_id` no Draft) tornam-se `parent_coid`/`child_coid`
(`UUID`, FK para `cognitive_objects.id`) — `CognitiveDistinction`
está `DEFERRED` desde E3.1, então COID é o único referente real hoje;
isso concretiza o contrato, não o contradiz. `transformation_ref`
permanece nulo/estrutural (nenhuma FK para uma tabela que não existe
ainda — `TransformationRecord` é `E3.4`).

Armazenamento **direcionado único**: uma linha por relação real
(`parent_coid`, `child_coid` já codificam a direção) — não um par
simétrico de edges. Ver `E3_3_LIB03_CLID_LINEAGE.md` para a
justificativa completa dessa decisão, delegada ao módulo E3.3 pelo
próprio Domain Model Draft.
"""

import uuid

from sqlalchemy import CheckConstraint, ForeignKey, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.cognitive.models.enums import LineageRelation
from app.models.base_model import BaseModel


class LineageEdge(BaseModel):
    """Relação direcionada `parent_coid → child_coid` entre dois
    `CognitiveObject`s distintos.

    Não representa mutação interna do mesmo objeto — uma nova
    versão/derivação cognitiva é sempre um novo `CognitiveObject`
    (§27 do módulo E3.3); `LineageEdge` apenas registra que dois
    objetos já existentes estão historicamente ligados.

    Append-only por construção: nenhum método de atualização/remoção
    é exposto por `LineageRepository` — não há requisito documentado
    para editar ou apagar uma edge já registrada.
    """

    __tablename__ = "lineage_edges"

    parent_coid: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cognitive_objects.id"), nullable=False, index=True
    )
    """COID do objeto de origem da relação. FK para `cognitive_objects.id`
    sem `ON DELETE CASCADE` — `CognitiveObject` usa soft delete
    (nunca é fisicamente removido em fluxo normal), então cascade
    automático não tem base documental (§32 do módulo E3.3)."""

    child_coid: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cognitive_objects.id"), nullable=False, index=True
    )
    """COID do objeto de destino da relação. Mesma política de FK que
    `parent_coid`."""

    relation_type: Mapped[LineageRelation] = mapped_column(
        SAEnum(
            LineageRelation,
            name="lineage_relation",
            native_enum=False,
            length=32,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
    """Ver `app.cognitive.models.enums.LineageRelation` — taxonomia
    completa já congelada no Domain Model Draft, usada sem alteração."""

    __table_args__ = (
        CheckConstraint("parent_coid != child_coid", name="ck_lineage_edges_no_self_link"),
        UniqueConstraint(
            "parent_coid",
            "child_coid",
            "relation_type",
            name="uq_lineage_edges_parent_child_relation",
        ),
    )
    """`CheckConstraint`: defesa em profundidade contra self-link — o
    guard de domínio (`LineageRepository.add_edge`) já rejeita antes
    de chegar ao banco; a constraint cobre o caso de manipulação
    direta que ignore o repositório.

    `UniqueConstraint`: a mesma tripla (parent, child, tipo de
    relação) não pode ser registrada duas vezes (§17 do módulo E3.3)
    — uma relação *diferente* entre os mesmos dois objetos (ex.:
    `BRANCH` e depois `DERIVED_FROM`) continua permitida."""
