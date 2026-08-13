"""
ObjectRepository — repositório concreto de `CognitiveObject` (LIB-01).

Reutiliza `BaseRepository`/`Page`/`RepositoryProtocol` da baseline sem
reimplementar CRUD genérico (§11 do módulo E3.1). O único comportamento
adicionado é o que `BaseRepository` genuinamente não pode saber:
exclusão lógica (soft delete) específica de `CognitiveObject` — a base
genérica não tem conhecimento de `SoftDeleteMixin`.

Não controla commit — quem decide quando commitar é o chamador (via
`UnitOfWork`), exatamente como `BaseRepository` (§12 do módulo E3.1).
"""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.cognitive.models.cognitive_object import CognitiveObject
from app.repositories.base_repository import BaseRepository, Page


class ObjectRepository(BaseRepository[CognitiveObject]):
    """Repositório de `CognitiveObject`.

    Por padrão, `get_by_id`/`list`/`paginate` **excluem** objetos com
    exclusão lógica aplicada (`deleted_at is not None`) — um objeto
    "apagado" deve se comportar, para a maioria dos consumidores, como
    ausente, sem que isso seja confundido com `AccessibilityState`
    (que é um conceito diferente, de propriedade de E3.6). Passe
    `include_deleted=True` explicitamente quando precisar enxergá-los
    (ex.: auditoria futura).
    """

    def __init__(self, session: Session) -> None:
        super().__init__(session, CognitiveObject)

    def get_by_id(
        self, entity_id: object, *, include_deleted: bool = False
    ) -> CognitiveObject | None:
        entity = super().get_by_id(entity_id)
        if entity is not None and entity.is_deleted and not include_deleted:
            return None
        return entity

    def list(
        self,
        *,
        limit: int | None = None,
        offset: int | None = None,
        include_deleted: bool = False,
    ) -> list[CognitiveObject]:
        items = super().list(limit=limit, offset=offset)
        if include_deleted:
            return items
        return [item for item in items if not item.is_deleted]

    def paginate(  # type: ignore[override]
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        include_deleted: bool = False,
        **filters: object,
    ) -> Page[CognitiveObject]:
        """Paginação com o mesmo filtro de soft delete.

        Nota: a contagem `total` de `Page` reflete a coleção filtrada
        por `**filters` do `BaseRepository` — não subtrai objetos soft
        deleted quando `include_deleted=False`, porque o filtro de
        soft delete é aplicado em memória após a consulta (mesma
        limitação que `list()` acima). Suficiente para o volume
        esperado de LIB-01; um filtro de soft delete no nível de SQL é
        candidato natural para `LIB-07 Index Manager` (E3.7), não para
        este módulo.
        """
        result = super().paginate(page=page, page_size=page_size, **filters)
        if include_deleted:
            return result
        filtered_items = [item for item in result.items if not item.is_deleted]
        return Page(
            items=filtered_items,
            total=result.total,
            page=result.page,
            page_size=result.page_size,
        )

    def soft_delete(self, entity: CognitiveObject) -> CognitiveObject:
        """Exclusão lógica — marca `deleted_at`, nunca remove a linha.

        Preferível a `delete()` (herdado, exclusão física) para
        `CognitiveObject`: exclusão física destruiria identidade e
        histórico que módulos futuros (E3.3 Lineage, E3.9 CausalHistory)
        precisarão reconstruir. `delete()` continua disponível
        (herdado de `BaseRepository`) para os casos em que exclusão
        física for genuinamente necessária — não removido, apenas não
        é o caminho recomendado.
        """
        entity.deleted_at = datetime.now(UTC)
        return self.update(entity)
