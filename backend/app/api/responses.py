"""
Modelos padronizados de resposta.

Toda API funcional futura deve usar um destes envelopes — não retornar
schemas "nus" sem um formato consistente. As respostas de erro já usam
`ErrorResponse` automaticamente, via `app.middleware.exception_handler`;
`SuccessResponse`/`MessageResponse` são para uso explícito pelos
endpoints funcionais que ainda serão criados em módulos posteriores.
"""

from typing import Generic, TypeVar

from pydantic import BaseModel, Field

from app.schemas.error import ErrorDetail, ErrorResponse, ValidationResponse

T = TypeVar("T")

__all__ = [
    "ErrorDetail",
    "ErrorResponse",
    "MessageResponse",
    "SuccessResponse",
    "ValidationResponse",
]


class SuccessResponse(BaseModel, Generic[T]):
    """Envelope de sucesso genérico: `data` + mensagem opcional."""

    data: T = Field(description="Dado retornado pela operação.")
    message: str | None = Field(default=None, description="Mensagem opcional de confirmação.")


class MessageResponse(BaseModel):
    """Resposta simples de confirmação, sem payload de dados (ex.: uma
    ação que não retorna um recurso)."""

    message: str = Field(description="Texto de confirmação da operação.")
