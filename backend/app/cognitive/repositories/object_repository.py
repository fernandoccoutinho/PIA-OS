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

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cognitive.errors.exceptions import CoidCollisionError
from app.cognitive.models.cognitive_object import CognitiveObject
from app.cognitive.models.enums import RevisionStatus
from app.repositories.base_repository import BaseRepository, Page
from app.repositories.exceptions import PersistenceError

# SQLSTATE padrão SQL (independente de driver) para unique_violation —
# cobre tanto UNIQUE quanto PRIMARY KEY no PostgreSQL, já que PK é
# implementada internamente como um índice único. Ver
# https://www.postgresql.org/docs/current/errcodes-appendix.html
_POSTGRES_UNIQUE_VIOLATION_SQLSTATE = "23505"

# Nomes de erro estruturados do stdlib `sqlite3` (Python 3.11+,
# `sqlite3.Error.sqlite_errorname`) para violação de PK/UNIQUE.
_SQLITE_UNIQUE_OR_PK_ERROR_NAMES = frozenset(
    {"SQLITE_CONSTRAINT_PRIMARYKEY", "SQLITE_CONSTRAINT_UNIQUE"}
)


def _is_unique_or_pk_violation(exc: PersistenceError) -> bool:
    """Verifica, via sinal estruturado do driver — nunca por parsing de
    mensagem —, se a causa original de um `PersistenceError` é uma
    violação de unicidade/chave primária (correção E3.2.1, débito C1).

    - **PostgreSQL** (`psycopg` 3, driver desta baseline —
      `requirements/base.txt`): `orig.sqlstate == "23505"`.
    - **SQLite** (usado nos testes unitários): `orig.sqlite_errorname`
      em `SQLITE_CONSTRAINT_PRIMARYKEY`/`SQLITE_CONSTRAINT_UNIQUE`.

    Ambos os sinais foram validados empiricamente contra os dois
    backends antes desta implementação (PostgreSQL 16 real e SQLite em
    memória). Nenhum outro backend é suportado hoje por
    `app.database.engine` — se um novo backend for adicionado sem
    sinal estruturado equivalente, esta função deve ser revisada
    explicitamente, não contornada com parsing de mensagem (§2/§3 do
    módulo E3.2.1).
    """
    orig = getattr(exc.__cause__, "orig", None)
    if orig is None:
        return False
    if getattr(orig, "sqlstate", None) == _POSTGRES_UNIQUE_VIOLATION_SQLSTATE:
        return True
    return getattr(orig, "sqlite_errorname", None) in _SQLITE_UNIQUE_OR_PK_ERROR_NAMES


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

    def add(self, entity: CognitiveObject) -> CognitiveObject:
        """Persiste um novo `CognitiveObject`.

        Correção E3.2.1 (C1): traduz `PersistenceError` para
        `CoidCollisionError` **somente** quando a causa original for,
        de fato, uma violação de unicidade/chave primária — não
        qualquer `PersistenceError` (a versão de E3.2 fazia isso
        incondicionalmente, o que classificava incorretamente qualquer
        outro erro de persistência como colisão de COID). Outras
        falhas de integridade continuam propagando como
        `PersistenceError`, sem reinterpretação.

        Cobre a janela de corrida (TOCTOU) que uma pré-checagem
        isolada (`CoidManager.assert_unique`) sozinha não cobre — a
        autoridade final de unicidade continua sendo a constraint de
        PK do banco.
        """
        try:
            return super().add(entity)
        except PersistenceError as exc:
            if _is_unique_or_pk_violation(exc):
                raise CoidCollisionError(entity.id) from exc
            raise

    def get_by_id(
        self, entity_id: object, *, include_deleted: bool = False
    ) -> CognitiveObject | None:
        stmt = select(CognitiveObject).where(CognitiveObject.id == entity_id)
        if not include_deleted:
            stmt = stmt.where(CognitiveObject.deleted_at.is_(None))
        return self._session.execute(stmt).scalar_one_or_none()

    def refresh_for_update(self, entity: CognitiveObject) -> CognitiveObject:
        """Bloqueia a linha (`SELECT ... FOR UPDATE`) e recarrega todos
        os atributos de `entity` a partir do estado atual do banco —
        correção E3.3.1 (débito C1).

        Necessário porque, sem isso, o identity map do SQLAlchemy
        manteria os valores já carregados em memória mesmo que outra
        transação tenha commitado uma mudança nesta linha enquanto a
        atual esperava o lock — usa `Session.refresh(...,
        with_for_update=True)` (mecanismo nativo do SQLAlchemy, não
        uma query manual). A linha permanece bloqueada até o fim da
        transação (commit/rollback) da `UnitOfWork` chamadora.

        No PostgreSQL real, isso serializa duas transações concorrentes
        que tentem atribuir CLID ao mesmo `CognitiveObject` pela primeira
        vez: a segunda transação bloqueia em `FOR UPDATE` até a primeira
        commitar, e então enxerga o `clid` já definido pela primeira —
        nunca um "last-write-wins" silencioso. No SQLite (usado nos
        testes unitários), `FOR UPDATE` é compilado como no-op pelo
        dialeto — o `refresh()` ainda funciona, mas sem a garantia real
        de bloqueio entre conexões (SQLite não suporta lock de linha);
        por isso a validação de concorrência real usa PostgreSQL
        (`tests/integration/cognitive/`), não SQLite.
        """
        self._session.refresh(entity, with_for_update=True)
        return entity

    def get_current_by_clid(self, clid: uuid.UUID) -> CognitiveObject | None:
        """Retorna o `CognitiveObject` com `revision_status = CURRENT`
        para este CLID, se existir (correção E3.4.1).

        Usado por `VersionManager.revise()` como **pré-checagem**
        (defesa em profundidade contra `source` incorreto passado pelo
        chamador) — não é a autoridade final: sozinha, esta consulta
        está sujeita a TOCTOU sob concorrência real. A garantia final
        vem do índice único parcial `uq_cognitive_objects_one_current_per_clid`
        (`CognitiveObject.__table_args__`), que rejeita no banco
        qualquer tentativa de um segundo `CURRENT` para o mesmo CLID,
        mesmo sob duas transações concorrentes.
        """
        stmt = select(CognitiveObject).where(
            CognitiveObject.clid == clid,
            CognitiveObject.revision_status == RevisionStatus.CURRENT,
        )
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
