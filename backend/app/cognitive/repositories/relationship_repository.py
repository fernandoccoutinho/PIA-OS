"""
RelationshipRepository — repositório concreto de `Relationship`
(`E3.5`/`LIB-05`).

Reutiliza `BaseRepository`/`Page` sem reimplementar CRUD genérico —
mesmo princípio de `ObjectRepository`/`LineageRepository`. Classificação
de violação de integridade é implementação própria (mesmo princípio de
`LineageRepository`: "não refatore E3.1-E3.4 sem necessidade
demonstrada" — pequena duplicação aceita em vez de extrair um helper
compartilhado).

Diferença deliberada em relação a `LineageRepository`: `Relationship`
tem **uma** transição legítima pós-criação (`retire()`, soft-retire) —
`update()` genérico continua sempre rejeitado, mas `retire()` é um
caminho controlado e único que a contorna deliberadamente (chama
`BaseRepository.update()` diretamente, não `self.update()`).
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cognitive.errors.exceptions import (
    RelationshipDuplicateError,
    RelationshipEndpointNotFoundError,
    RelationshipImmutableError,
    RelationshipSelfLinkError,
)
from app.cognitive.models.enums import RelationshipType
from app.cognitive.models.relationship import Relationship
from app.repositories.base_repository import BaseRepository
from app.repositories.exceptions import PersistenceError

_POSTGRES_UNIQUE_VIOLATION_SQLSTATE = "23505"
_POSTGRES_FOREIGN_KEY_VIOLATION_SQLSTATE = "23503"
_SQLITE_UNIQUE_ERROR_NAME = "SQLITE_CONSTRAINT_UNIQUE"
_SQLITE_FOREIGN_KEY_ERROR_NAME = "SQLITE_CONSTRAINT_FOREIGNKEY"


def _classify_relationship_integrity_violation(exc: PersistenceError) -> str | None:
    """Retorna `"unique"`, `"foreign_key"` ou `None` — via sinal
    estruturado do driver, nunca parsing de mensagem. Mesmos sinais já
    validados em E3.2.1/E3.3.1/E3.4.1."""
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


class RelationshipRepository(BaseRepository[Relationship]):
    """Repositório de `Relationship`.

    `outgoing`/`incoming`/`by_type`/`neighbors` excluem relações
    retiradas (`retired_at IS NOT NULL`) por padrão — mesmo padrão de
    soft-delete-aware de `ObjectRepository` (E3.1.1) — com
    `include_retired=True` como escape hatch. Ordenação determinística
    (`created_at ASC, id ASC`), mesma convenção de E3.1.2/E3.3.

    `update()`/`delete()` sempre rejeitam mutação genérica/remoção
    física — a única transição legítima pós-criação é `retire()`.
    """

    def __init__(self, session: Session) -> None:
        super().__init__(session, Relationship)

    def add_relationship(
        self, *, source_coid: uuid.UUID, target_coid: uuid.UUID, relationship_type: RelationshipType
    ) -> Relationship:
        """Registra uma nova `Relationship`.

        Rejeita self-relation (`source_coid == target_coid`) no
        domínio, antes de qualquer tentativa de escrita — mesma
        política aplicada globalmente a todos os tipos nesta fase
        (§11 do módulo E3.5: nenhum dos 5 tipos tem caso de uso
        legítimo identificado para auto-relação).

        Para o tipo simétrico (`RelationshipType.RELATED_TO`), os
        endpoints são normalizados antes da escrita — o menor UUID
        (comparação lexicográfica de `str(uuid)`) sempre vira
        `source_coid` — para que `(A,B)` e `(B,A)` colidam na mesma
        `UniqueConstraint`, em vez de permitir duas linhas
        representando o mesmo fato simétrico (§10 do módulo E3.5).
        Tipos direcionados preservam a ordem exatamente como
        declarada.

        Traduz violação de integridade: unicidade →
        `RelationshipDuplicateError` (`PIA-8014`); chave estrangeira →
        `RelationshipEndpointNotFoundError` (`PIA-8015`). Qualquer
        outra causa de `PersistenceError` é relançada sem
        reinterpretação.
        """
        if source_coid == target_coid:
            raise RelationshipSelfLinkError(source_coid)

        if relationship_type.is_symmetric and str(target_coid) < str(source_coid):
            source_coid, target_coid = target_coid, source_coid

        entity = Relationship(
            source_coid=source_coid, target_coid=target_coid, relationship_type=relationship_type
        )
        try:
            return self.add(entity)
        except PersistenceError as exc:
            violation = _classify_relationship_integrity_violation(exc)
            if violation == "unique":
                raise RelationshipDuplicateError(
                    source_coid, target_coid, relationship_type
                ) from exc
            if violation == "foreign_key":
                # Não temos, a partir do driver, qual dos dois COIDs
                # violou a FK — melhor esforço: reportar `target_coid`
                # (mesma limitação documentada de `LineageRepository`).
                raise RelationshipEndpointNotFoundError(target_coid) from exc
            raise

    def outgoing(
        self,
        source_coid: uuid.UUID,
        *,
        relationship_type: RelationshipType | None = None,
        include_retired: bool = False,
    ) -> list[Relationship]:
        """Relações onde `source_coid` é a origem — ordenadas
        deterministicamente."""
        stmt = (
            select(Relationship)
            .where(Relationship.source_coid == source_coid)
            .order_by(Relationship.created_at.asc(), Relationship.id.asc())
        )
        if not include_retired:
            stmt = stmt.where(Relationship.retired_at.is_(None))
        if relationship_type is not None:
            stmt = stmt.where(Relationship.relationship_type == relationship_type)
        return list(self._session.execute(stmt).scalars().all())

    def incoming(
        self,
        target_coid: uuid.UUID,
        *,
        relationship_type: RelationshipType | None = None,
        include_retired: bool = False,
    ) -> list[Relationship]:
        """Relações onde `target_coid` é o destino — ordenadas
        deterministicamente."""
        stmt = (
            select(Relationship)
            .where(Relationship.target_coid == target_coid)
            .order_by(Relationship.created_at.asc(), Relationship.id.asc())
        )
        if not include_retired:
            stmt = stmt.where(Relationship.retired_at.is_(None))
        if relationship_type is not None:
            stmt = stmt.where(Relationship.relationship_type == relationship_type)
        return list(self._session.execute(stmt).scalars().all())

    def by_type(
        self, relationship_type: RelationshipType, *, include_retired: bool = False
    ) -> list[Relationship]:
        """Todas as relações de um tipo — ordenadas deterministicamente."""
        stmt = (
            select(Relationship)
            .where(Relationship.relationship_type == relationship_type)
            .order_by(Relationship.created_at.asc(), Relationship.id.asc())
        )
        if not include_retired:
            stmt = stmt.where(Relationship.retired_at.is_(None))
        return list(self._session.execute(stmt).scalars().all())

    def neighbors(self, coid: uuid.UUID, *, include_retired: bool = False) -> list[Relationship]:
        """One-hop: todas as relações (`outgoing` + `incoming`) que
        tocam `coid`, em qualquer direção/tipo — ordenadas
        deterministicamente pelo conjunto combinado. Não implementa
        travessia multi-hop (§14 do módulo E3.5 — one-hop nesta fase
        é suficiente para LIB-042)."""
        stmt = (
            select(Relationship)
            .where((Relationship.source_coid == coid) | (Relationship.target_coid == coid))
            .order_by(Relationship.created_at.asc(), Relationship.id.asc())
        )
        if not include_retired:
            stmt = stmt.where(Relationship.retired_at.is_(None))
        return list(self._session.execute(stmt).scalars().all())

    def relationship_exists(
        self,
        source_coid: uuid.UUID,
        target_coid: uuid.UUID,
        relationship_type: RelationshipType,
        *,
        include_retired: bool = False,
    ) -> bool:
        """Verificação O(1) via índice, sem carregar a entidade."""
        if relationship_type.is_symmetric and str(target_coid) < str(source_coid):
            source_coid, target_coid = target_coid, source_coid
        stmt = select(Relationship.id).where(
            Relationship.source_coid == source_coid,
            Relationship.target_coid == target_coid,
            Relationship.relationship_type == relationship_type,
        )
        if not include_retired:
            stmt = stmt.where(Relationship.retired_at.is_(None))
        return self._session.execute(stmt).first() is not None

    def retire(self, relationship: Relationship) -> Relationship:
        """Soft-retire — marca `retired_at`, nunca remove a linha nem
        modifica qualquer outro campo. Único caminho legítimo de
        mutação pós-criação (§9, §12 do módulo E3.5: "remover" não
        apaga o fato histórico). Idempotente — retirar uma relação já
        retirada não é erro, apenas não faz nada.

        Chama `BaseRepository.update()` diretamente (não `self.update()`)
        — `update()` deste repositório está sobrescrito para sempre
        rejeitar mutação genérica; `retire()` é o único caminho
        controlado que a contorna deliberadamente.
        """
        if relationship.retired_at is not None:
            return relationship
        relationship.retired_at = datetime.now(UTC)
        return BaseRepository.update(self, relationship)

    def update(self, entity: Relationship) -> Relationship:
        """Sempre rejeita mutação genérica — use `retire()` para a
        única transição legítima pós-criação."""
        raise RelationshipImmutableError(entity.id, operation="update")

    def delete(self, entity: Relationship) -> None:
        """Sempre rejeita remoção física — use `retire()`."""
        raise RelationshipImmutableError(entity.id, operation="delete")
