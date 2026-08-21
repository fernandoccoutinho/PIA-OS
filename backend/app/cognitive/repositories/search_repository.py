"""
`SearchRepository` — composição determinística de consulta
(`E3.8`/`LIB-08`).

**Somente leitura.** Nenhum método aqui insere, atualiza ou remove
qualquer coisa; a busca não tem semântica de commit.

Por que não reutilizar `IndexRepository` (E3.7) diretamente: aquele
repositório oferece **caminhos de acesso** por uma dimensão de cada
vez (`INDEX = ACCESS PATH`). Compor uma conjunção chamando vários
métodos dele e intersectando as listas em Python carregaria patrimônio
inteiro para a memória e faria exatamente o que o §21 do módulo
proíbe. Aqui a conjunção vira **uma única consulta SQL**, resolvida
pelo PostgreSQL sobre os índices que `E3.7` já criou — nenhum índice
novo, nenhuma migração.

```text
INDEX  = ACCESS PATH
SEARCH = QUERY COMPOSITION
```

A ordenação é a canônica do projeto (`created_at ASC, id ASC`,
`E3.1.2`) — determinística e estável, o que é o que torna
`offset`/`limit` seguros. Ordenação **não é ranking semântico**; não
existe score aqui.
"""

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from app.cognitive.models.cognitive_object import CognitiveObject
from app.cognitive.models.provenance_record import ProvenanceRecord
from app.cognitive.schemas.search_criteria import SearchCriteria


class SearchRepository:
    """Resolve uma `SearchCriteria` em uma única consulta composta."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def _build(self, criteria: SearchCriteria) -> Select[tuple[CognitiveObject]]:
        stmt: Select[tuple[CognitiveObject]] = select(CognitiveObject)

        if criteria.coid is not None:
            stmt = stmt.where(CognitiveObject.id == criteria.coid)
        if criteria.clid is not None:
            stmt = stmt.where(CognitiveObject.clid == criteria.clid)
        if criteria.accessibility is not None:
            stmt = stmt.where(CognitiveObject.accessibility == criteria.accessibility)
        if criteria.revision_status is not None:
            stmt = stmt.where(CognitiveObject.revision_status == criteria.revision_status)
        if criteria.created_from is not None:
            stmt = stmt.where(CognitiveObject.created_at >= criteria.created_from)
        if criteria.created_until is not None:
            stmt = stmt.where(CognitiveObject.created_at <= criteria.created_until)
        if criteria.trace_id is not None:
            # `trace_id` vive em `ProvenanceRecord`, nunca no objeto:
            # `EXISTS` em vez de `JOIN` para não multiplicar linhas
            # quando o mesmo objeto tem vários registros de
            # proveniência com o mesmo trace (e sem precisar de
            # `DISTINCT`, que atrapalharia a ordenação).
            stmt = stmt.where(
                select(ProvenanceRecord.id)
                .where(
                    ProvenanceRecord.coid == CognitiveObject.id,
                    ProvenanceRecord.trace_id == criteria.trace_id,
                )
                .exists()
            )
        if not criteria.include_deleted:
            stmt = stmt.where(CognitiveObject.deleted_at.is_(None))

        return stmt.order_by(CognitiveObject.created_at.asc(), CognitiveObject.id.asc())

    def search(
        self,
        criteria: SearchCriteria,
        *,
        limit: int | None = None,
        offset: int | None = None,
    ) -> list[CognitiveObject]:
        """Executa a consulta composta. Devolve as entidades
        persistidas — nunca cópias, nunca projeções materializadas."""
        stmt = self._build(criteria)
        if offset is not None:
            stmt = stmt.offset(offset)
        if limit is not None:
            stmt = stmt.limit(limit)
        return list(self._session.execute(stmt).scalars().all())

    def count(self, criteria: SearchCriteria) -> int:
        """Quantos objetos satisfazem os critérios, ignorando
        paginação. Útil para o chamador saber se há mais páginas sem
        materializar o resultado inteiro."""
        from sqlalchemy import func

        inner = self._build(criteria).order_by(None).subquery()
        return int(self._session.execute(select(func.count()).select_from(inner)).scalar_one())
