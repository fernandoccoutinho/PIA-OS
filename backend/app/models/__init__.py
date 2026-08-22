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
from app.models.programmatic_service_principal import (
    ProgrammaticQuotaBucket,
    ProgrammaticServicePrincipal,
)

__all__ = [
    "AuditMixin",
    "BaseModel",
    "ProgrammaticQuotaBucket",
    "ProgrammaticServicePrincipal",
    "SoftDeleteMixin",
    "TimestampMixin",
    "UUIDMixin",
    "VersionMixin",
]
