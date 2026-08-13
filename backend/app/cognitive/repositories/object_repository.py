"""
ObjectRepository — repositório concreto de `CognitiveObject` (LIB-01).

Reutiliza `BaseRepository`/`Page`/`RepositoryProtocol` da baseline sem
reimplementar CRUD genérico (§11 do módulo E3.1). O comportamento
adicionado é o que `BaseRepository` genuinamente não pode saber:
exclusão lógica (soft delete) específica de `CognitiveObject` — a base
genérica não tem conhecimento de `SoftDeleteMixin`.

Correção E3.1.1 (débito C1): o filtro de soft delete é aplicado **no
SQL**, antes de LIMIT/OFFSET/COUNT — não mais em memória após a
consulta. `paginate()` reutiliza o mecanismo público `**filters` de
`BaseRepository` (`deleted_at=None` já é traduzido para `IS NULL` pelo
SQLAlchemy via `_equality_clauses`, mecanismo já existente, nenhuma
mudança na baseline). `get_by_id()`/`list()` não têm mecanismo público
equivalente em `BaseRepository.list()` (que não aceita `**filters`) —
constroem um `select()` próprio usando `self._session` (já herdado),
mesma composição que `BaseRepository.list()` já faz, com o predicado
adicional que só faz sentido para esta entidade.

Não controla commit — quem decide quando commitar é o chamador (via
`UnitOfWork`), exatamente como `BaseRepository` (§12 do módulo E3.1).
"""

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cognitive.models.cognitive_object import CognitiveObject
from app.repositories.base_repository import BaseRepository, Page


class ObjectRepository(BaseRepository[CognitiveObject]):
    """Repositório de `CognitiveObject`.

    Por padrão, `get_by_id`/`list`/`paginate` **excluem** objetos com
    exclusão lógica aplicada (`deleted_at IS NOT NULL`) — filtrado no
    banco, antes de LIMIT/OFFSET/COUNT (correção E3.1.1). Um objeto
    "apagado" deve se comportar, para a maioria dos consumidores, como
    ausente, sem que isso seja confundido com `AccessibilityState`
    (que é um conceito diferente, de propriedade de E3.6). Passe
    `include_deleted=True` explicitamente quando precisar enxergá-los
    (ex.: auditoria futura) — nenhum mecanismo administrativo além
    deste flag é criado nesta correção.
    """

    def __init__(self, session: Session) -> None:
        super().__init__(session, CognitiveObject)

    def get_by_id(
        self, entity_id: object, *, include_deleted: bool = False
    ) -> CognitiveObject | None:
        stmt = select(CognitiveObject).where(CognitiveObject.id == entity_id)
        if not include_deleted:
            stmt = stmt.where(CognitiveObject.deleted_at.is_(None))
        return self._session.execute(stmt).scalar_one_or_none()

    def list(
        self,
        *,
        limit: int | None = None,
        offset: int | None = None,
        include_deleted: bool = False,
    ) -> list[CognitiveObject]:
        stmt = select(CognitiveObject)
        if not include_deleted:
            stmt = stmt.where(CognitiveObject.deleted_at.is_(None))
        if offset is not None:
            stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self._session.execute(stmt).scalars().all())

    def paginate(  # type: ignore[override]
        self,
        *,
        page: int = 1,
        page_size: int = 20,
        include_deleted: bool = False,
        **filters: object,
    ) -> Page[CognitiveObject]:
        """Paginação com o filtro de soft delete aplicado no SQL.

        `deleted_at=None` é passado como mais um filtro de igualdade
        para `BaseRepository.paginate()` — o mesmo mecanismo público
        que qualquer chamador já usaria (`repo.paginate(status="x")`),
        sem necessidade de tocar `BaseRepository`. `Page.total` reflete
        corretamente a contagem de itens ativos (correção E3.1.1: antes
        contava soft-deleted também).

        `filters` não deve incluir `deleted_at` — esse campo é
        gerenciado internamente por `include_deleted`, não exposto
        para filtragem arbitrária do chamador (evita ambiguidade entre
        os dois mecanismos).
        """
        if include_deleted:
            return super().paginate(page=page, page_size=page_size, **filters)
        return super().paginate(page=page, page_size=page_size, deleted_at=None, **filters)

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
