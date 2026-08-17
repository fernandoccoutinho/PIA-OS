"""
Portas estruturais do isolamento cognitivo (`E4.8`).

A produção de `app/memory` nunca importa `app.cognitive` — fronteira
verificada por `G17` (E3.12) e `MD6` (E4.1). Precedente: E4.5, E4.6 e
E4.7.

Aqui a fronteira é outra: a E4.8 é **composição sobre módulos da própria
E4**, e as portas existem para que ela dependa de forma, não de classe
concreta.

```text
IsolatedRetrievalPort     a operação pública da E4.6, com criteria opaco
DomainMembershipPort      leitura de memberships, com view tipada mínima
GovernanceResolutionPort  resolução de autoridade, sem duplicar o motor
ContextValidationPort     confirmação da perspectiva, sem substituí-la
```

Nenhuma delas reimplementa o que envolve: a E4.8 **pergunta** e
**verifica**, nunca refaz.

    ISOLATION DOES NOT GRANT AUTHORITY
    ISOLATION DOES NOT CREATE EXISTENCE

## Sem `Any`, sem reflexão

Os retornos que dependem de ordem são `Sequence`, não `Iterable`
arbitrário — a lição que a E4.6.2 pagou ao aceitar generator e ver a
ordem divergir. Nenhum objeto ORM atravessa o resultado público: a
`MembershipView` expõe só as duas identidades de que o isolamento
precisa.
"""

import uuid
from collections.abc import Iterable, Sequence
from datetime import datetime
from typing import Protocol, TypeVar, runtime_checkable

from app.memory.schemas.governance import GovernanceResolution
from app.memory.schemas.memory_context import MemoryContext
from app.memory.schemas.retrieval import MemoryRetrievalResult
from app.memory.services.platform_safety_boundary import CapabilityDescriptor

CriteriaT_contra = TypeVar("CriteriaT_contra", contravariant=True)
"""Critérios de busca, **opacos** para a E4.8.

Contravariante porque a porta apenas os **consome**: a E4.8 recebe o
objeto do chamador e o repassa por identidade, sem inspecionar,
normalizar ou reconstruir. Os critérios continuam sendo da E3.8, como
já eram na E4.6.

    CRITERIA TRAVEL BY IDENTITY, NOT BY INSPECTION
"""

MembershipT_co = TypeVar("MembershipT_co", covariant=True)
"""Membership devolvida pelo repositório, opaca na porta.

Covariante porque a porta apenas a **produz**. Genérica pelo mesmo
motivo registrado na E4.7.1: os modelos declaram campos como
`Mapped[...]`, e um `Protocol` que prometesse `coid: uuid.UUID` não
seria satisfeito por atribuição estática — o mypy compara a anotação
declarada, não o que o descritor devolve em runtime.

A E4.8 estreita o objeto com `isinstance` contra `MembershipView`, que
**tipa** o valor para o mypy e torna a leitura dos campos verificada
estaticamente, sem `getattr`.
"""


@runtime_checkable
class MembershipView(Protocol):
    """Forma mínima de uma `MemoryDomainMembership`.

    Só as duas identidades que o isolamento precisa. `created_at`, `id`
    e qualquer outro campo não são da conta da E4.8 — e um objeto ORM
    completo nunca atravessa o resultado público.

        MEMBERSHIP != EXISTENCE
        MEMBERSHIP != AUTHORIZATION
    """

    @property
    def domain_id(self) -> uuid.UUID:
        """Domínio ao qual a associação pertence."""

    @property
    def coid(self) -> uuid.UUID:
        """Objeto cognitivo associado."""


@runtime_checkable
class ContextValidationPort(Protocol):
    """Confirma que a perspectiva declarada é utilizável.

    Satisfeita estruturalmente por `ContextManager` (E4.2).

        VALIDATION CONFIRMS
        ISOLATION DOES NOT REWRITE USER CONTEXT
    """

    def validate(self, context: MemoryContext) -> MemoryContext:
        """Devolve a perspectiva confirmada."""
        ...  # pragma: no cover - corpo de stub de Protocol, nunca executado

    def derive(
        self,
        context: MemoryContext,
        *,
        domain_ids: Iterable[uuid.UUID] | None = None,
        session_id: str | None = None,
        actor_ref: str | None = None,
        purpose: str | None = None,
    ) -> MemoryContext:
        """Deriva uma perspectiva preservando o que não foi alterado.

        A E4.8 a usa para montar os **singletons** com que pergunta à
        governança sobre cada domínio — preservando `session_id`,
        `actor_ref` e `purpose` exatamente.

        `domain_ids` reproduz a assinatura real (`Iterable[uuid.UUID] |
        None`) em vez de um `object` mais largo: parâmetro é posição
        **contravariante**, então alargá-lo faria a porta exigir do
        objeto real mais do que ele aceita — e a satisfação estática
        falharia. Foi o que o mypy apontou ao verificar esta porta.
        """
        ...  # pragma: no cover - corpo de stub de Protocol, nunca executado


@runtime_checkable
class GovernanceResolutionPort(Protocol):
    """Resolve autoridade pelo caminho canônico da E4.3.

    Satisfeita estruturalmente por `GovernanceManager`.

    A E4.8 **não** duplica `GovernanceRule.matches()`, não reinterpreta
    regras e não consulta o repositório de policy para "confirmar" uma
    resolução. Ela pergunta uma vez por domínio e verifica o vínculo com
    a função compartilhada da E4.3.4.

        GOVERNANCE DECIDES AUTHORITY
        ISOLATION APPLIES UNDER GOVERNANCE AUTHORITY
    """

    def resolve(
        self,
        *,
        descriptor: CapabilityDescriptor,
        context: MemoryContext,
        policy_key: str | None = None,
        moment: datetime | None = None,
    ) -> GovernanceResolution:
        """Resolução de autoridade para esta operação e perspectiva."""
        ...  # pragma: no cover - corpo de stub de Protocol, nunca executado


@runtime_checkable
class DomainMembershipPort(Protocol[MembershipT_co]):
    """Lê as associações de um domínio.

    Satisfeita estruturalmente por `MemoryDomainMembershipRepository`
    (E4.1).

    `Sequence`, não `Iterable`: o snapshot precisa ser materializado e
    reordenável de forma determinística. Aceitar um generator faria a
    E4.8 consumir a coleção uma vez e depois compará-la vazia — a
    mesma classe de defeito que a E4.6.2 fechou.
    """

    def list_memberships_of_domain(self, domain_id: uuid.UUID) -> Sequence[MembershipT_co]:
        """Associações declaradas para este domínio."""
        ...  # pragma: no cover - corpo de stub de Protocol, nunca executado


@runtime_checkable
class IsolatedRetrievalPort(Protocol[CriteriaT_contra]):
    """A operação pública da E4.6, consumida sem ser reimplementada.

    Satisfeita estruturalmente por `MemoryRetrievalManager`.

    A assinatura reproduz `retrieve()` exatamente, inclusive `limit` e
    `offset`, porque a E4.8 **repassa** a paginação solicitada em uma
    única chamada. Estreitar a assinatura faria a porta mentir sobre o
    que o objeto real aceita; recompor a paginação quebraria ordem
    global, `has_more` e desduplicação.

        ISOLATION COMPOSES RETRIEVAL
        ISOLATION DOES NOT REIMPLEMENT RETRIEVAL
        ISOLATION NEVER CALLS SEARCH DIRECTLY
    """

    def retrieve(
        self,
        *,
        context: MemoryContext,
        descriptor: CapabilityDescriptor,
        criteria: CriteriaT_contra,
        policy_key: str | None = None,
        moment: datetime | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> MemoryRetrievalResult:
        """Vista admissível para esta perspectiva."""
        ...  # pragma: no cover - corpo de stub de Protocol, nunca executado
