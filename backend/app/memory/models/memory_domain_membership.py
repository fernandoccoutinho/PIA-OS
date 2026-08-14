"""
`MemoryDomainMembership` — associação N:N entre domínio e COID (E4.1).

A tabela mais importante deste módulo, e a que mais facilmente daria
errado: bastaria copiar um único atributo do `CognitiveObject` para
criar uma segunda fonte da verdade sobre o patrimônio. Ela não copia
nada. Guarda **duas referências e nada mais**.

```
COID → {D1, D2, ..., Dn}
one COID remains one CognitiveObject
```

Adicionar, remover ou reclassificar membership **não pode** alterar
`CognitiveObject.id`, `.clid`, `.accessibility`, `.revision_status`,
nem proveniência, linhagem ou história causal. E4.1 organiza; E4.1 não
reinterpreta patrimônio.
"""

import uuid

from sqlalchemy import ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base_model import BaseModel


class MemoryDomainMembership(BaseModel):
    """Pertencimento de um COID a um `MemoryDomain`.

    Cardinalidade **many-to-many**: um domínio classifica muitos
    COIDs, e um COID pertence a zero, um ou vários domínios. Zero é
    válido e não é estado degenerado —

        ZERO DOMAIN MEMBERSHIP != NONEXISTENCE

    exigir domínio faria da segmentação uma condição de existir, o que
    contradiz a Matriz A do `E4_MEMORY_SEMANTICS.md`.
    """

    __tablename__ = "memory_domain_memberships"

    domain_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("memory_domains.id"), nullable=False, index=True
    )
    """Domínio ao qual o COID pertence.

    FK **sem** `ON DELETE CASCADE`, seguindo a política já estabelecida
    em `LineageEdge` e `Relationship` (E3.3/E3.5). Aqui a razão é ainda
    mais forte: cascade a partir de estado organizacional é o caminho
    mais curto para apagar patrimônio por conveniência de schema.

        DOMAIN DELETE MUST NOT CASCADE TO COGNITIVE PATRIMONY

    De todo modo `DOMAIN_DELETION` está `DEFERRED` (E4.1 §4/Q14) —
    nenhum caminho de código remove domínio nesta entrega.
    """

    coid: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cognitive_objects.id"), nullable=False, index=True
    )
    """COID do `CognitiveObject` classificado.

    Referência declarada por **nome de tabela**, resolvida no
    `MetaData` compartilhado. Isso não é detalhe de estilo: é o que
    permite a este pacote não importar `app.cognitive` em nenhuma
    linha, mantendo a fronteira E3/E4 estrutural em vez de documental
    (E4.1 §2.1). A integridade referencial é real e vem do banco.

    Nenhum atributo do objeto é copiado para cá. Nome, CLID,
    `accessibility`, `revision_status`, proveniência, relações e
    história causal permanecem exclusivamente na E3, que continua
    sendo a única fonte da verdade sobre eles.
    """

    __table_args__ = (
        UniqueConstraint("domain_id", "coid", name="uq_memory_domain_memberships_domain_coid"),
    )
    """`(domain_id, coid)` é a **identidade estrutural** da associação:
    o mesmo objeto não pertence duas vezes ao mesmo domínio.

    A constraint vive no banco (autoridade final), e o repositório
    traduz a violação para `MemoryDomainMembershipDuplicateError`
    (`PIA-8024`) — mesma disciplina de defesa em profundidade de
    E3.3/E3.4/E3.5: o domínio dá a mensagem boa, o banco dá a
    garantia.

    O `id` próprio herdado de `BaseModel` é identidade de *registro*,
    seguindo a convenção do projeto; a unicidade *lógica* é o par.

    **Sem coluna de lifecycle** (`left_at`/`retired_at`), e a omissão é
    deliberada. O `E4_PRIMITIVE_OWNERSHIP.md` §5 recomendava lifecycle
    por analogia a `Relationship.retired_at`, mas a analogia se rompe
    num ponto: `retired_at` existe na E3 porque existe um `retire()`
    que o escreve. Aqui a remoção de membership está `DEFERRED` até
    E4.3 definir autoridade — e uma coluna que nenhum código escreve
    não preserva história, apenas promete preservação que o módulo não
    entrega. O lifecycle entra junto com o escritor que lhe dá
    sentido.
    """
