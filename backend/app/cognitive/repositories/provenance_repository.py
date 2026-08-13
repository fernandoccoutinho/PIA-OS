"""
ProvenanceRepository — repositório concreto de `ProvenanceRecord`
(`E3.6`/`LIB-06`).

Reutiliza `BaseRepository` sem reimplementar CRUD genérico. Único
comportamento adicionado: garantir que o histórico é append-only de
verdade — mesma disciplina de `LineageRepository`/
`TransformationRepository`/`RelationshipRepository` (E3.3.1/E3.4/E3.5).
`ProvenanceRecord`, diferente de `Relationship`, não tem lifecycle de
"retire" — é puramente append-only, sem nenhuma transição legítima
pós-criação (§6 do módulo E3.6: "uma correção posterior deve ser um
novo fato/registro, nunca reescrita da história").
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cognitive.errors.exceptions import ProvenanceRecordImmutableError
from app.cognitive.models.provenance_record import ProvenanceRecord
from app.repositories.base_repository import BaseRepository


class ProvenanceRepository(BaseRepository[ProvenanceRecord]):
    """Repositório de `ProvenanceRecord`.

    `list_by_coid` ordena por `created_at ASC, id ASC` — mesma
    convenção determinística de E3.1.2/E3.3/E3.4/E3.5.

    `update()`/`delete()` sempre rejeitam — nenhuma transição legítima
    existe pós-criação (diferente de `Relationship`, que tem
    `retire()`).
    """

    def __init__(self, session: Session) -> None:
        super().__init__(session, ProvenanceRecord)

    def list_by_coid(self, coid: uuid.UUID) -> list[ProvenanceRecord]:
        """Todas as proveniências registradas para um `CognitiveObject`
        — ordenadas deterministicamente. Múltiplas linhas são
        esperadas e válidas (§18 do módulo E3.6: duas IAs podem gerar
        dois `ProvenanceRecord`s distintos para o mesmo COID)."""
        stmt = (
            select(ProvenanceRecord)
            .where(ProvenanceRecord.coid == coid)
            .order_by(ProvenanceRecord.created_at.asc(), ProvenanceRecord.id.asc())
        )
        return list(self._session.execute(stmt).scalars().all())

    def update(self, entity: ProvenanceRecord) -> ProvenanceRecord:
        """Sempre rejeita — `ProvenanceRecord` é append-only puro,
        sem nenhuma transição legítima pós-criação."""
        raise ProvenanceRecordImmutableError(entity.id, operation="update")

    def delete(self, entity: ProvenanceRecord) -> None:
        """Sempre rejeita — ver `update()` acima."""
        raise ProvenanceRecordImmutableError(entity.id, operation="delete")
