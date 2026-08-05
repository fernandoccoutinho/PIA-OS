"""
Interface (Protocol) de repositório.

Define o contrato estrutural que qualquer repositório deve cumprir, sem
exigir herança explícita (duck typing verificável estaticamente). Permite
substituir `BaseRepository` por uma implementação alternativa (ex.: um
repositório em memória para testes rápidos, ou um adaptador para outro
banco) sem que o código que o consome precise mudar — basta cumprir o
Protocol.

Nenhuma lógica aqui — apenas assinaturas.
"""

from typing import Protocol, TypeVar, runtime_checkable

from app.database.base import Base

ModelType = TypeVar("ModelType", bound=Base)


@runtime_checkable
class RepositoryProtocol(Protocol[ModelType]):
    """Contrato mínimo que todo repositório deve cumprir."""

    def get_by_id(self, entity_id: object) -> ModelType | None:
        """Busca uma entidade pela chave primária. None se não encontrada."""
        ...

    def list(self, *, limit: int | None = None, offset: int | None = None) -> list[ModelType]:
        """Lista entidades, com paginação opcional."""
        ...

    def add(self, entity: ModelType) -> ModelType:
        """Adiciona uma nova entidade."""
        ...

    def update(self, entity: ModelType) -> ModelType:
        """Persiste alterações em uma entidade existente."""
        ...

    def delete(self, entity: ModelType) -> None:
        """Remove uma entidade."""
        ...
