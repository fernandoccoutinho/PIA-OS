"""
Prova **estática** de que os colaboradores reais satisfazem as portas da
E4.8 e que a composição tipada é possível ponta a ponta.

Sem asserção de runtime relevante: o valor deste arquivo é ser
verificado pelo mypy.

```text
RUNTIME_CHECKABLE != STATIC SIGNATURE COMPATIBILITY
STATIC ASSIGNMENT != TYPED END-TO-END COMPOSITION
```

As duas lições vêm da E4.7.1 e da E4.7.2: `isinstance` num `Protocol`
`runtime_checkable` confere apenas **nomes de membros**, e atribuir não
é chamar. Por isso este arquivo faz as duas coisas — atribui e depois
**chama** `retrieve_isolated` com os tipos reais.

Sem `Any`, `cast` ou `type: ignore`, que anulariam a prova.
"""

import uuid
from datetime import datetime

from app.cognitive.schemas.search_criteria import SearchCriteria
from app.memory.models.memory_domain_membership import MemoryDomainMembership
from app.memory.ports.isolation import (
    ContextValidationPort,
    DomainMembershipPort,
    GovernanceResolutionPort,
    IsolatedRetrievalPort,
)
from app.memory.repositories.memory_domain_membership_repository import (
    MemoryDomainMembershipRepository,
)
from app.memory.schemas.isolation import MemoryIsolationResult
from app.memory.schemas.memory_context import MemoryContext
from app.memory.services.context_manager import ContextManager
from app.memory.services.governance_manager import GovernanceManager
from app.memory.services.memory_isolation_manager import MemoryIsolationManager
from app.memory.services.platform_safety_boundary import CapabilityDescriptor
from app.memory.services.retrieval_manager import MemoryRetrievalManager


def prova_de_atribuicao_estatica(
    retrieval: MemoryRetrievalManager[SearchCriteria],
    governanca: GovernanceManager,
    contexto: ContextManager,
    memberships: MemoryDomainMembershipRepository,
) -> None:
    """As quatro portas, satisfeitas por atribuição verificada."""
    a: IsolatedRetrievalPort[SearchCriteria] = retrieval
    b: GovernanceResolutionPort = governanca
    c: ContextValidationPort = contexto
    d: DomainMembershipPort[MemoryDomainMembership] = memberships
    _ = (a, b, c, d)


def prova_de_composicao_e_chamada_tipada(
    retrieval: MemoryRetrievalManager[SearchCriteria],
    governanca: GovernanceManager,
    contexto: ContextManager,
    memberships: MemoryDomainMembershipRepository,
    dominio: uuid.UUID,
    descritor: CapabilityDescriptor,
    criteria: SearchCriteria,
    momento: datetime,
) -> MemoryIsolationResult:
    """A composição real, tipada, com chamada usando os tipos reais."""
    manager: MemoryIsolationManager[SearchCriteria] = MemoryIsolationManager(
        retrieval, governanca, contexto, memberships
    )
    return manager.retrieve_isolated(
        context=MemoryContext(domain_ids=(dominio,)),
        descriptor=descritor,
        criteria=criteria,
        policy_key="g",
        moment=momento,
        limit=50,
        offset=0,
    )


def test_static_isolation_ports_module_is_type_checked() -> None:
    """Marcador de runtime: a prova real é o mypy sobre este arquivo."""
    assert prova_de_atribuicao_estatica.__doc__
    assert prova_de_composicao_e_chamada_tipada.__doc__
