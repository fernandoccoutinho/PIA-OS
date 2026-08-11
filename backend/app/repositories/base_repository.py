"""
Repositório genérico — operações comuns de acesso a dados.

Regra arquitetural a partir do Módulo 2.3: nenhum componente fora de
`app/repositories/` deve importar SQLAlchemy diretamente para consultar
ou persistir dados. Todo acesso ao banco passa por um repositório (ou
pelo `UnitOfWork`, para transações que envolvem múltiplos repositórios).

`BaseRepository` não contém regra de negócio nem é específico de nenhuma
entidade do domínio do PIA-OS — é reutilizado por composição/herança
pelos repositórios concretos que serão criados em módulos futuros, e
cumpre `RepositoryProtocol` (ver `repository_protocol.py`).

Compatibilidade com o Módulo 2.3: `create()` e `exists()` continuam
disponíveis e com o mesmo comportamento. `add()` (Módulo 2.4) é o nome
canônico daqui em diante — `create()` passou a ser um alias.
"""

from dataclasses import dataclass
from typing import Generic, TypeVar

from sqlalchemy import exists as sa_exists
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database.base import Base
from app.repositories.exceptions import EntityNotFoundError, PersistenceError

ModelType = TypeVar("ModelType", bound=Base)


@dataclass(frozen=True)
class Page(Generic[ModelType]):
    """Resultado de uma consulta paginada — itens da página atual + total geral."""

    items: list[ModelType]
    total: int
    page: int
    page_size: int

    @property
    def total_pages(self) -> int:
        if self.page_size <= 0:
            return 0
        return -(-self.total // self.page_size)  # divisão inteira arredondada para cima

    @property
    def has_next(self) -> bool:
        return self.page < self.total_pages


class BaseRepository(Generic[ModelType]):
    """Repositório genérico parametrizado pelo tipo de entidade ORM.

    Não commita a sessão — quem controla a transação é o chamador (ou o
    `UnitOfWork`). Isso permite compor múltiplas operações de múltiplos
    repositórios em uma única transação atômica.
    """

    def __init__(self, session: Session, model: type[ModelType]) -> None:
        self._session = session
        self._model = model

    def add(self, entity: ModelType) -> ModelType:
        """Adiciona uma nova entidade à sessão (flush, sem commit).

        Levanta `PersistenceError` se o flush violar uma constraint do
        banco (chave duplicada, not-null, etc.) — nunca propaga a exceção
        crua do SQLAlchemy/driver para fora da camada de repositório.
        """
        try:
            self._session.add(entity)
            self._session.flush()
        except SQLAlchemyError as exc:
            self._session.rollback()
            raise PersistenceError(f"Falha ao adicionar {self._model.__name__}: {exc}") from exc
        return entity

    def create(self, entity: ModelType) -> ModelType:
        """Alias de `add()` — mantido por compatibilidade com o Módulo 2.3."""
        return self.add(entity)

    def get_by_id(self, entity_id: object) -> ModelType | None:
        """Busca uma entidade pela chave primária. None se não encontrada."""
        return self._session.get(self._model, entity_id)

    def get_by_id_or_raise(self, entity_id: object) -> ModelType:
        """Como `get_by_id`, mas levanta `EntityNotFoundError` se ausente."""
        entity = self.get_by_id(entity_id)
        if entity is None:
            raise EntityNotFoundError(self._model.__name__, entity_id)
        return entity

    def list(self, *, limit: int | None = None, offset: int | None = None) -> list[ModelType]:
        """Lista entidades, com paginação opcional (limit/offset)."""
        stmt = select(self._model)
        if offset is not None:
            stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self._session.execute(stmt).scalars().all())

    def update(self, entity: ModelType) -> ModelType:
        """Persiste alterações feitas em uma entidade já rastreada pela sessão."""
        try:
            self._session.flush()
        except SQLAlchemyError as exc:
            self._session.rollback()
            raise PersistenceError(f"Falha ao atualizar {self._model.__name__}: {exc}") from exc
        return entity

    def delete(self, entity: ModelType) -> None:
        """Remove uma entidade (flush, sem commit)."""
        try:
            self._session.delete(entity)
            self._session.flush()
        except SQLAlchemyError as exc:
            self._session.rollback()
            raise PersistenceError(f"Falha ao remover {self._model.__name__}: {exc}") from exc

    def refresh(self, entity: ModelType) -> ModelType:
        """Recarrega o estado da entidade a partir do banco (descarta alterações
        locais não persistidas)."""
        self._session.refresh(entity)
        return entity

    def exists(self, entity_id: object) -> bool:
        """Verifica existência por chave primária sem carregar a entidade inteira."""
        pk_columns = list(self._model.__table__.primary_key.columns)
        if len(pk_columns) != 1:
            return self.get_by_id(entity_id) is not None
        stmt = select(sa_exists().where(pk_columns[0] == entity_id))
        return bool(self._session.execute(stmt).scalar())

    def exists_by(self, **filters: object) -> bool:
        """Verifica existência por igualdade de colunas arbitrárias.

            repo.exists_by(email="a@b.com")

        Apenas igualdade simples (AND entre os filtros) — consultas mais
        elaboradas (OR, comparações, joins) pertencem a um repositório
        concreto de domínio, não a esta camada genérica.
        """
        stmt = select(sa_exists().where(*self._equality_clauses(filters)))
        return bool(self._session.execute(stmt).scalar())

    def count(self, **filters: object) -> int:
        """Conta entidades, opcionalmente filtradas por igualdade de colunas.

        repo.count()                  # total da tabela
        repo.count(status="ativo")    # total filtrado
        """
        stmt = select(func.count()).select_from(self._model)
        if filters:
            stmt = stmt.where(*self._equality_clauses(filters))
        return int(self._session.execute(stmt).scalar_one())

    def paginate(self, *, page: int = 1, page_size: int = 20, **filters: object) -> Page[ModelType]:
        """Lista entidades paginadas, com contagem total da coleção filtrada.

        `page` é 1-indexado. Não substitui `list()` — para listagens sem
        necessidade de contagem total (mais barato), `list()` continua
        sendo a opção mais direta.
        """
        if page < 1:
            raise ValueError("page deve ser >= 1")
        if page_size < 1:
            raise ValueError("page_size deve ser >= 1")

        stmt = select(self._model)
        if filters:
            stmt = stmt.where(*self._equality_clauses(filters))

        total = self.count(**filters)
        items = list(
            self._session.execute(stmt.offset((page - 1) * page_size).limit(page_size))
            .scalars()
            .all()
        )
        return Page(items=items, total=total, page=page, page_size=page_size)

    def _equality_clauses(self, filters: dict[str, object]) -> list:
        """Traduz `campo=valor` em cláusulas `Coluna == valor`, validando
        que cada campo existe no modelo (evita erros silenciosos por typo)."""
        clauses = []
        for field_name, value in filters.items():
            column = getattr(self._model, field_name, None)
            if column is None:
                raise ValueError(f"{self._model.__name__} não possui o campo '{field_name}'.")
            clauses.append(column == value)
        return clauses
