"""
`MemoryDomainManager` — fachada de organização do patrimônio (E4.1).

Existe porque acrescenta invariantes acima do repositório, e não como
camada decorativa: é aqui que fica registrada, num único lugar, a
promessa central do módulo —

    ORGANIZATION CHANGED
    PATRIMONY DID NOT

O que este manager deliberadamente **não** faz:

- não decide quem pode ver, criar ou classificar (Governance é E4.3);
- não constrói nem consome contexto (Context é E4.2);
- não compõe vista admissível (Retrieval é E4.6);
- não avalia acessibilidade nem transiciona estado (E4.7);
- não infere persistência (E4.4) nem relevância;
- não calcula score de espécie alguma.
"""

import uuid

from app.memory.models.memory_domain import MemoryDomain
from app.memory.models.memory_domain_membership import MemoryDomainMembership
from app.memory.repositories.memory_domain_membership_repository import (
    MemoryDomainMembershipRepository,
)
from app.memory.repositories.memory_domain_repository import MemoryDomainRepository


class MemoryDomainManager:
    """Operações estruturais de domínio e pertencimento.

    Recebe COIDs como `uuid.UUID`, nunca instâncias de
    `CognitiveObject`: E4.1 referencia patrimônio, não o manipula.
    """

    def __init__(
        self,
        domain_repository: MemoryDomainRepository,
        membership_repository: MemoryDomainMembershipRepository,
    ) -> None:
        self._domains = domain_repository
        self._memberships = membership_repository

    def create_domain(self, *, name: str) -> MemoryDomain:
        """Cria um domínio.

        Não cria contexto implícito (E4.1 §14), não cria
        `CognitiveObject` representando o domínio (§6), não atribui
        owner nem policy.
        """
        return self._domains.add_domain(name=name)

    def get_domain(self, domain_id: uuid.UUID) -> MemoryDomain | None:
        """Domínio por id, ou `None`. Ausência não é exceção."""
        return self._domains.get_by_id(domain_id)

    def list_domains(self) -> list[MemoryDomain]:
        """Domínios em ordem determinística canônica."""
        return self._domains.list_domains()

    def add_object(self, *, domain_id: uuid.UUID, coid: uuid.UUID) -> MemoryDomainMembership:
        """Classifica um COID em um domínio.

        A operação é puramente organizacional. O mesmo COID pode ser
        classificado em quantos domínios se queira, e continua sendo um
        único `CognitiveObject` com um único COID — a classificação
        nunca duplica patrimônio:

            DOMAIN CLASSIFICATION MUST NOT COLLAPSE COGNITIVE IDENTITY
        """
        return self._memberships.add_membership(domain_id=domain_id, coid=coid)

    def contains(self, *, domain_id: uuid.UUID, coid: uuid.UUID) -> bool:
        """O COID pertence a este domínio?"""
        return self._memberships.contains(domain_id=domain_id, coid=coid)

    def list_members(self, domain_id: uuid.UUID) -> list[uuid.UUID]:
        """COIDs classificados no domínio, em ordem determinística.

        Devolve **identificadores**, não objetos: hidratá-los é
        trabalho da E3, que é a fonte da verdade sobre eles. Esta
        assinatura também é o que mantém a fronteira estrutural — o
        módulo nunca precisa importar `app.cognitive`.
        """
        return [m.coid for m in self._memberships.list_memberships_of_domain(domain_id)]

    def list_domains_for_object(self, coid: uuid.UUID) -> list[uuid.UUID]:
        """Domínios aos quais o COID pertence, em ordem determinística.

        Lista vazia é resultado válido e frequente: a maior parte do
        patrimônio pode legitimamente não estar classificada em
        domínio algum.
        """
        return [m.domain_id for m in self._memberships.list_memberships_of_object(coid)]
