"""Modelos ORM da camada de memória (E4).

Importados aqui para que `Base.metadata` os conheça — mesmo padrão de
`app.cognitive.models`. É este módulo que `alembic/env.py` importa.
"""

from app.memory.models.accessibility_policy import AccessibilityPolicy
from app.memory.models.erasure_enums import ErasureOutcome, ErasureTargetClass
from app.memory.models.erasure_record import ErasureRecord
from app.memory.models.governance_policy import GovernancePolicy
from app.memory.models.memory_domain import MemoryDomain
from app.memory.models.memory_domain_membership import MemoryDomainMembership
from app.memory.models.retention_enums import (
    RetentionAnchor,
    RetentionExpiryAction,
    RetentionScopeKind,
)
from app.memory.models.retention_policy import RetentionPolicy

__all__ = [
    "AccessibilityPolicy",
    "ErasureOutcome",
    "ErasureRecord",
    "ErasureTargetClass",
    "GovernancePolicy",
    "MemoryDomain",
    "MemoryDomainMembership",
    "RetentionAnchor",
    "RetentionExpiryAction",
    "RetentionPolicy",
    "RetentionScopeKind",
]
