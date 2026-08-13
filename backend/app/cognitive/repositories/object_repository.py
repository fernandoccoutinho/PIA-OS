"""
ObjectRepository — repositório concreto de `CognitiveObject` (LIB-01).

Reutiliza `BaseRepository`/`Page`/`RepositoryProtocol` da baseline sem
reimplementar CRUD genérico (§11 do módulo E3.1). O comportamento
adicionado é o que `BaseRepository` genuinamente não pode saber:
exclusão lógica (soft delete) específica de `CognitiveObject` — a base
genérica não tem conhecimento de `SoftDeleteMixin` — e, a partir da
correção E3.1.2, ordenação determinística (`BaseRepository` não tem
nenhuma convenção de `ORDER BY`, confirmado por inspeção: nem
`list()` nem `paginate()` ordenam).

Correção E3.1.1 (débito C1): o filtro de soft delete é aplicado **no
SQL**, antes de LIMIT/OFFSET/COUNT — não em memória após a consulta.

Correção E3.1.2: `list()`/`paginate()` agora ordenam por
`created_at ASC, id ASC` — `created_at` como critério primário,
`id` (UUID) como desempate determinístico quando dois objetos têm o
mesmo timestamp (ex.: criados na mesma transação/mesmo instante).
`paginate()` deixa de delegar a `super().paginate()` (que não expõe
nenhum hook de ordenação) e passa a construir sua própria consulta,
reutilizando `self._equality_clauses()` e `self.count()` — herdados,
não duplicados — para o filtro e a contagem total.

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

    `list()`/`paginate()` são deterministicamente ordenados por
    `created_at ASC, id ASC` (correção E3.1.2) — a mesma consulta
    executada duas vezes retorna sempre a mesma sequência de IDs, e
    paginação consecutiva nunca duplica nem perde itens.
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
        stmt = select(CognitiveObject).order_by(
            CognitiveObject.created_at.asc(), CognitiveObject.id.asc()
        )
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
        """Paginação com filtro de soft delete e ordenação determinística
        aplicados no SQL.

        Não delega mais a `BaseRepository.paginate()` (correção
        E3.1.2): a base não expõe nenhum hook público de `ORDER BY`,
        então a única forma de garantir ordenação canônica sem alterar
        `BaseRepository` é construir a consulta aqui — reutilizando
        `self._equality_clauses()` (helper herdado, já usado por
        `BaseRepository.paginate()` internamente) e `self.count()`
        (método público herdado) em vez de duplicar essa lógica.

        `filters` não deve incluir `deleted_at` — esse campo é
        gerenciado internamente por `include_deleted`, não exposto
        para filtragem arbitrária do chamador (evita ambiguidade entre
        os dois mecanismos).
        """
        if page < 1:
            raise ValueError("page deve ser >= 1")
        if page_size < 1:
            raise ValueError("page_size deve ser >= 1")

        effective_filters: dict[str, object] = dict(filters)
        if not include_deleted:
            effective_filters["deleted_at"] = None

        stmt = select(CognitiveObject).order_by(
            CognitiveObject.created_at.asc(), CognitiveObject.id.asc()
        )
        if effective_filters:
            stmt = stmt.where(*self._equality_clauses(effective_filters))

        total = self.count(**effective_filters)
        items = list(
            self._session.execute(stmt.offset((page - 1) * page_size).limit(page_size))
            .scalars()
            .all()
        )
        return Page(items=items, total=total, page=page, page_size=page_size)

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
