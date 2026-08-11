"""
Registro de Schemas públicos.

Lista explícita dos schemas expostos na API (usados como `response_model`
ou aninhados neles) — usada por `app/api/documentation.py` para verificar
automaticamente que todos têm `description` em cada campo.
"""

from pydantic import BaseModel

from app.api.responses import MessageResponse, SuccessResponse
from app.schemas.common import Message, PaginationMeta, PaginationParams, SortParams
from app.schemas.error import ErrorDetail, ErrorResponse, ValidationErrorItem, ValidationResponse
from app.schemas.health import (
    ComponentStatus,
    HealthResponse,
    MetricsResponse,
    RootResponse,
    StatusResponse,
    VersionResponse,
)

PUBLIC_SCHEMAS: tuple[type[BaseModel], ...] = (
    HealthResponse,
    ComponentStatus,
    VersionResponse,
    StatusResponse,
    MetricsResponse,
    RootResponse,
    ErrorDetail,
    ErrorResponse,
    ValidationErrorItem,
    ValidationResponse,
    PaginationParams,
    SortParams,
    PaginationMeta,
    Message,
    MessageResponse,
    SuccessResponse,
)


def fields_missing_description(schema: type[BaseModel]) -> list[str]:
    """Retorna os nomes dos campos de `schema` sem `description` definida."""
    missing = []
    for field_name, field_info in schema.model_fields.items():
        if not field_info.description:
            missing.append(field_name)
    return missing
