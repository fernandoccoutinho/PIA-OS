"""
Schemas reutilizáveis — paginação, ordenação, filtros e metadados.

Nenhum filtro concreto de domínio é definido aqui — apenas a estrutura
genérica que endpoints funcionais (módulos futuros) vão compor. Query
params validados via Pydantic (nunca dict sem tipagem), conforme exigido
pelo Módulo 2.5. Módulo 2.9 apenas adiciona `description` — nenhum
campo, tipo ou default muda.
"""

from enum import StrEnum

from pydantic import BaseModel, Field


class SortOrder(StrEnum):
    ASC = "asc"
    DESC = "desc"


class PaginationParams(BaseModel):
    """Query params de paginação — usar como dependency (`Depends()`) em
    endpoints funcionais futuros: `params: PaginationParams = Depends()`."""

    page: int = Field(default=1, ge=1, description="Número da página, começando em 1.")
    page_size: int = Field(default=20, ge=1, le=200, description="Itens por página (máximo 200).")


class SortParams(BaseModel):
    """Estrutura para ordenação — `sort_by` é validado pelo endpoint
    concreto (contra os campos que fazem sentido para aquele recurso),
    não aqui, já que os campos válidos dependem do domínio."""

    sort_by: str | None = Field(default=None, description="Campo pelo qual ordenar.")
    order: SortOrder = Field(default=SortOrder.ASC, description="Direção da ordenação.")


class PaginationMeta(BaseModel):
    """Metadados de uma resposta paginada."""

    page: int = Field(description="Página atual.")
    page_size: int = Field(description="Itens por página.")
    total: int = Field(description="Total de itens na coleção completa.")
    total_pages: int = Field(description="Total de páginas.")
    has_next: bool = Field(description="Se existe uma próxima página.")
    has_previous: bool = Field(description="Se existe uma página anterior.")


class Metadata(BaseModel):
    """Metadados genéricos anexáveis a qualquer resposta (ex.: contagem,
    filtros aplicados) — estrutura livre por natureza."""

    extra: dict[str, object] = Field(
        default_factory=dict, description="Metadados livres, por chave."
    )


class Message(BaseModel):
    """Mensagem simples — usada por `MessageResponse` em `api/responses.py`."""

    text: str = Field(description="Texto da mensagem.")
