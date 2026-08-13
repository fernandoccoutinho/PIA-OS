"""
LineageRepository — repositório concreto de `LineageEdge` (E3.3/LIB-03).

Reutiliza `BaseRepository`/`Page` sem reimplementar CRUD genérico
(mesmo princípio de `ObjectRepository`, E3.1 §11). Adiciona apenas o
que a base genuinamente não pode saber: consultas de `parent`/`child`
ordenadas deterministicamente, e classificação de violação de
integridade específica de `LineageEdge` (self-link, edge duplicada,
endpoint inexistente).

Nota de design: a classificação de violação de integridade abaixo
(`_classify_lineage_integrity_violation`) usa o mesmo princípio de
sinal estruturado (SQLSTATE/`sqlite_errorname`) já validado em
`ObjectRepository`/correção E3.2.1 — mas é uma implementação própria,
não uma reutilização de `object_repository._is_unique_or_pk_violation`.
Decisão deliberada: a instrução de E3.3 é explícita ("não refatore
E3.1/E3.2 sem necessidade demonstrada") — tocar em
`object_repository.py`, já auditado e corrigido duas vezes, para
extrair um helper compartilhado não é necessário para o objetivo deste
módulo. A pequena duplicação (~15 linhas) é o custo aceito dessa
escolha.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cognitive.errors.exceptions import (
    LineageDuplicateEdgeError,
    LineageEndpointNotFoundError,
    LineageSelfLinkError,
)
from app.cognitive.models.enums import LineageRelation
from app.cognitive.models.lineage_edge import LineageEdge
from app.repositories.base_repository import BaseRepository
from app.repositories.exceptions import PersistenceError

_POSTGRES_UNIQUE_VIOLATION_SQLSTATE = "23505"
_POSTGRES_FOREIGN_KEY_VIOLATION_SQLSTATE = "23503"
_SQLITE_UNIQUE_ERROR_NAME = "SQLITE_CONSTRAINT_UNIQUE"
_SQLITE_FOREIGN_KEY_ERROR_NAME = "SQLITE_CONSTRAINT_FOREIGNKEY"


def _classify_lineage_integrity_violation(exc: PersistenceError) -> str | None:
    """Retorna `"unique"`, `"foreign_key"` ou `None` (causa não
    reconhecida) — via sinal estruturado do driver, nunca parsing de
    mensagem. Mesmos sinais validados empiricamente contra PostgreSQL
    16 real e SQLite antes desta implementação (ver
    `E3_3_LIB03_CLID_LINEAGE.md`)."""
    orig = getattr(exc.__cause__, "orig", None)
    if orig is None:
        return None
    sqlstate = getattr(orig, "sqlstate", None)
    if sqlstate == _POSTGRES_UNIQUE_VIOLATION_SQLSTATE:
        return "unique"
    if sqlstate == _POSTGRES_FOREIGN_KEY_VIOLATION_SQLSTATE:
        return "foreign_key"
    sqlite_errorname = getattr(orig, "sqlite_errorname", None)
    if sqlite_errorname == _SQLITE_UNIQUE_ERROR_NAME:
        return "unique"
    if sqlite_errorname == _SQLITE_FOREIGN_KEY_ERROR_NAME:
        return "foreign_key"
    return None


class LineageRepository(BaseRepository[LineageEdge]):
    """Repositório de `LineageEdge`.

    `list_children`/`list_parents` ordenam por `created_at ASC, id ASC`
    — mesma convenção de ordenação determinística de `ObjectRepository`
    (E3.1.2), para não repetir o débito já corrigido lá (§34 do módulo
    E3.3).
    """

    def __init__(self, session: Session) -> None:
        super().__init__(session, LineageEdge)

    def add_edge(
        self, *, parent_coid: uuid.UUID, child_coid: uuid.UUID, relation_type: LineageRelation
    ) -> LineageEdge:
        """Registra uma nova `LineageEdge`.

        Rejeita self-link (`parent_coid == child_coid`) no domínio,
        antes de qualquer tentativa de escrita — mais rápido e com
        mensagem melhor que esperar a `CHECK` constraint do banco
        (que continua existindo como defesa em profundidade, ver
        `LineageEdge.__table_args__`).

        Traduz violação de integridade para erro de domínio: unicidade
        → `LineageDuplicateEdgeError` (`PIA-8007`); chave estrangeira
        → `LineageEndpointNotFoundError` (`PIA-8008`, `parent_coid` ou
        `child_coid` não existe). Qualquer outra causa de
        `PersistenceError` é relançada sem reinterpretação (mesmo
        princípio da correção E3.2.1 — não classificar por eliminação).
        """
        if parent_coid == child_coid:
            raise LineageSelfLinkError(parent_coid)

        entity = LineageEdge(
            parent_coid=parent_coid, child_coid=child_coid, relation_type=relation_type
        )
        try:
            return self.add(entity)
        except PersistenceError as exc:
            violation = _classify_lineage_integrity_violation(exc)
            if violation == "unique":
                raise LineageDuplicateEdgeError(parent_coid, child_coid, relation_type) from exc
            if violation == "foreign_key":
                # Não temos, a partir do driver, qual dos dois COIDs
                # (parent/child) especificamente violou a FK — melhor
                # esforço: reportar o `child_coid`, e documentar a
                # limitação (ver E3_3_LIB03_CLID_LINEAGE.md).
                raise LineageEndpointNotFoundError(child_coid) from exc
            raise

    def list_children(
        self, parent_coid: uuid.UUID, *, relation_type: LineageRelation | None = None
    ) -> list[LineageEdge]:
        """Edges onde `parent_coid` é a origem — ordenadas
        deterministicamente. `LineageEdge` não tem soft delete (é
        append-only), então não há parâmetro `include_deleted` aqui —
        a história de lineage nunca desaparece por soft delete do
        `CognitiveObject` (§33 do módulo E3.3), já que a FK aponta
        para a linha física, que soft delete não remove."""
        stmt = (
            select(LineageEdge)
            .where(LineageEdge.parent_coid == parent_coid)
            .order_by(LineageEdge.created_at.asc(), LineageEdge.id.asc())
        )
        if relation_type is not None:
            stmt = stmt.where(LineageEdge.relation_type == relation_type)
        return list(self._session.execute(stmt).scalars().all())

    def list_parents(
        self, child_coid: uuid.UUID, *, relation_type: LineageRelation | None = None
    ) -> list[LineageEdge]:
        """Edges onde `child_coid` é o destino — ordenadas
        deterministicamente."""
        stmt = (
            select(LineageEdge)
            .where(LineageEdge.child_coid == child_coid)
            .order_by(LineageEdge.created_at.asc(), LineageEdge.id.asc())
        )
        if relation_type is not None:
            stmt = stmt.where(LineageEdge.relation_type == relation_type)
        return list(self._session.execute(stmt).scalars().all())

    def edge_exists(
        self, parent_coid: uuid.UUID, child_coid: uuid.UUID, relation_type: LineageRelation
    ) -> bool:
        """Verificação O(1) via índice, sem carregar a entidade."""
        stmt = select(LineageEdge.id).where(
            LineageEdge.parent_coid == parent_coid,
            LineageEdge.child_coid == child_coid,
            LineageEdge.relation_type == relation_type,
        )
        return self._session.execute(stmt).first() is not None
