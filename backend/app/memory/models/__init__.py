"""Modelos ORM da camada de memória (E4).

Importados aqui para que `Base.metadata` os conheça — mesmo padrão de
`app.cognitive.models`. É este módulo que `alembic/env.py` importa.
"""

from app.memory.models.governance_policy import GovernancePolicy
from app.memory.models.memory_domain import MemoryDomain
from app.memory.models.memory_domain_membership import MemoryDomainMembership

__all__ = ["GovernancePolicy", "MemoryDomain", "MemoryDomainMembership"]
