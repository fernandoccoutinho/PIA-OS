"""
IndexRepository — acesso estrutural determinístico (`E3.7`/`LIB-07`).

Repositório **somente de leitura**. Não escreve, não cria, não altera
e não apaga nada: é a única camada autorizada a falar SQLAlchemy em
nome do Index Manager (regra arquitetural do Módulo 2.3 — nada fora de
`app/repositories/`... `app/cognitive/repositories/` acessa o ORM
diretamente).

Por que um repositório novo em vez de métodos novos nos repositórios
de `E3.1`–`E3.6`: acrescentar consultas àqueles arquivos alteraria
código já congelado e auditado sem necessidade. As consultas aqui são
de outra natureza — localização estrutural, não regra de domínio — e
pertencem ao módulo que as introduz.

Todas as consultas usam a ordenação determinística canônica do projeto
(`created_at ASC, id ASC`, estabelecida em `E3.1.2`) — nunca ordem
indefinida.

O índice **não é fonte da verdade**: cada método aqui devolve
entidades lidas das tabelas persistentes. Nada é materializado, nada é
copiado, nada existe apenas "no índice".
"""

import uuid

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.cognitive.models.cognitive_object import CognitiveObject
from app.cognitive.models.enums import AccessibilityState, RevisionStatus
from app.cognitive.models.provenance_record import ProvenanceRecord


class IndexRepository:
    """Consultas estruturais sobre o patrimônio cognitivo persistido."""

    def __init__(self, session: Session) -> None:
        self._session = session

    @staticmethod
    def _ordered(
        stmt: Select[tuple[CognitiveObject]], *, include_deleted: bool
    ) -> Select[tuple[CognitiveObject]]:
        """Aplica soft delete e a ordenação determinística canônica.

        `include_deleted` espelha a semântica já existente em
        `ObjectRepository.get_by_id`/`list` — soft delete continua
        sendo decisão de `E3.1`, não redefinida aqui.
        """
        if not include_deleted:
            stmt = stmt.where(CognitiveObject.deleted_at.is_(None))
        return stmt.order_by(CognitiveObject.created_at.asc(), CognitiveObject.id.asc())

    def objects_by_clid(
        self, clid: uuid.UUID, *, include_deleted: bool = False
    ) -> list[CognitiveObject]:
        """Todos os objetos que compartilham um CLID — `CURRENT`,
        `SUPERSEDED` e sem `revision_status`, sem distinção.

        Deliberadamente diferente de `ObjectRepository.get_current_by_clid`
        (E3.4.1), que devolve só o `CURRENT`: aqui o histórico inteiro
        é localizável, porque `SUPERSEDED` continua patrimônio
        cognitivo (E3.7 §9).
        """
        stmt = self._ordered(
            select(CognitiveObject).where(CognitiveObject.clid == clid),
            include_deleted=include_deleted,
        )
        return list(self._session.execute(stmt).scalars().all())

    def objects_by_accessibility(
        self,
        state: AccessibilityState,
        *,
        limit: int | None = None,
        include_deleted: bool = False,
    ) -> list[CognitiveObject]:
        """Objetos em um estado de acessibilidade — **todos** os
        estados são localizáveis, inclusive `CAUSALLY_EXTINCT`.

        O índice reflete o patrimônio persistido; decidir o que expor a
        quem é responsabilidade de camadas superiores (E3.7 §8). Não
        aparecer numa consulta filtrada nunca significa deixar de
        existir.
        """
        stmt = self._ordered(
            select(CognitiveObject).where(CognitiveObject.accessibility == state),
            include_deleted=include_deleted,
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self._session.execute(stmt).scalars().all())

    def objects_by_revision_status(
        self,
        status: RevisionStatus,
        *,
        limit: int | None = None,
        include_deleted: bool = False,
    ) -> list[CognitiveObject]:
        """Objetos por `revision_status`. `SUPERSEDED` é tão
        localizável quanto `CURRENT`."""
        stmt = self._ordered(
            select(CognitiveObject).where(CognitiveObject.revision_status == status),
            include_deleted=include_deleted,
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self._session.execute(stmt).scalars().all())

    def objects_by_trace_id(
        self, trace_id: str, *, include_deleted: bool = False
    ) -> list[CognitiveObject]:
        """Objetos associados a um `trace_id` **através de
        `ProvenanceRecord`** — nunca por um campo próprio do objeto.

        `trace_id` continua sendo correlação transversal, não
        identidade cognitiva (E3.7 §11): ele localiza objetos já
        associados ao identificador, e não cria vínculo algum. Um
        objeto pode ter vários `ProvenanceRecord`s com o mesmo
        `trace_id`; o resultado é deduplicado por objeto.
        """
        stmt = self._ordered(
            select(CognitiveObject)
            .join(ProvenanceRecord, ProvenanceRecord.coid == CognitiveObject.id)
            .where(ProvenanceRecord.trace_id == trace_id)
            .distinct(),
            include_deleted=include_deleted,
        )
        return list(self._session.execute(stmt).scalars().all())
