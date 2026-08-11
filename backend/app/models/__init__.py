"""
Camada de modelos ORM.

Nenhuma entidade de domínio é definida neste módulo (2.4) — apenas a
infraestrutura reutilizável (`BaseModel`, mixins) que entidades futuras
usarão.
"""

from app.models.base_model import BaseModel
from app.models.mixins import (
    AuditMixin,
    SoftDeleteMixin,
    TimestampMixin,
    UUIDMixin,
    VersionMixin,
)

__all__ = [
    "AuditMixin",
    "BaseModel",
    "SoftDeleteMixin",
    "TimestampMixin",
    "UUIDMixin",
    "VersionMixin",
]
