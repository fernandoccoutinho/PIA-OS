"""
`MemoryDomainRepository` — acesso a `MemoryDomain` (E4.1).

Fino de propósito. `BaseRepository` já entrega `add`, `get_by_id` e
`list`; este repositório existe para dar nome de domínio às operações e
para garantir a ordenação determinística canônica do projeto
(`created_at ASC, id ASC`, desde E3.1.2).

Operações **deliberadamente ausentes**: `delete_domain`,
`rename_domain`, `retire_domain`. Todas estão `DEFERRED` até E4.3
definir autoridade — e nenhuma operação destrutiva é criada só para
completar um CRUD (E4.1 §19). Um domínio, uma vez criado, é criado.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.memory.models.memory_domain import MemoryDomain
from app.repositories.base_repository import BaseRepository


class MemoryDomainRepository(BaseRepository[MemoryDomain]):
    """Persistência de `MemoryDomain`.

    Não conhece `CognitiveObject` e não pode conhecê-lo: este pacote
    não importa `app.cognitive` (E4.1 §2.1).
    """

    def __init__(self, session: Session) -> None:
        super().__init__(session, MemoryDomain)

    def add_domain(self, *, name: str) -> MemoryDomain:
        """Cria um `MemoryDomain`.

        `name` é atributo, não identidade: nenhuma unicidade é imposta
        e dois domínios homônimos são dois domínios distintos
        (`same name != same domain`). O `id` é gerado por `UUIDMixin`.
        """
        return self.add(MemoryDomain(name=name))

    def exists_domain(self, domain_id: uuid.UUID) -> bool:
        """Existe um domínio com este `domain_id`?

        Usado pela pré-checagem de `MemoryDomainMembershipRepository`
        para tornar determinado o diagnóstico entre as duas FKs da
        membership. Consulta a própria tabela — nenhuma dependência do
        domínio cognitivo.
        """
        stmt = select(MemoryDomain.id).where(MemoryDomain.id == domain_id).limit(1)
        return self._session.execute(stmt).first() is not None

    def list_domains(
        self, *, limit: int | None = None, offset: int | None = None
    ) -> list[MemoryDomain]:
        """Domínios em ordem determinística canônica.

        `created_at ASC, id ASC` — ordem total, o que torna a paginação
        por offset estável (mesma justificativa de E3.8).
        """
        stmt = select(MemoryDomain).order_by(MemoryDomain.created_at.asc(), MemoryDomain.id.asc())
        if offset is not None:
            stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self._session.execute(stmt).scalars().all())
