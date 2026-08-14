"""
`IntegrityRepository` — leituras de auditoria (`E3.10`/`LIB-10`).

**Somente leitura, sem exceção.** Nenhum método aqui insere, atualiza,
remove ou trunca coisa alguma: auditar é observar, e observar não pode
alterar o observado (`PATRIMONY_AFTER == PATRIMONY_BEFORE`).

Cada método devolve **matéria-prima diagnóstica** — arestas, pares
violadores, referências pendentes — e nunca um veredito. Classificar e
reportar é do `IntegrityManager`; decidir o que fazer é da governança,
que pertence a `E4` e não existe aqui.

Consistência da leitura: as consultas rodam dentro da transação do
chamador (`UnitOfWork`), no nível de isolamento configurado pelo
projeto — `READ COMMITTED`, o default do PostgreSQL, não alterado por
`E3.10`. Isso significa que uma auditoria concorrente com escritas
enxerga um recorte consistente **por consulta**, não um snapshot
global do patrimônio. Prometer `SERIALIZABLE` seria falso; quem
precisar dessa garantia deve abrir a transação nesse nível
explicitamente.
"""

import uuid

import sqlalchemy as sa
from sqlalchemy import select
from sqlalchemy.orm import InstrumentedAttribute, Session

from app.cognitive.models.causal_history import CausalHistory, CausalHistoryEvent
from app.cognitive.models.cognitive_object import CognitiveObject
from app.cognitive.models.enums import RelationshipType, RevisionStatus
from app.cognitive.models.lineage_edge import LineageEdge
from app.cognitive.models.provenance_record import ProvenanceRecord
from app.cognitive.models.relationship import Relationship


class IntegrityRepository:
    """Consultas de auditoria sobre o patrimônio persistido."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # --- Grafos -------------------------------------------------------

    def lineage_edges(self) -> list[tuple[uuid.UUID, uuid.UUID, uuid.UUID]]:
        """`(edge_id, parent_coid, child_coid)` — o grafo de linhagem
        inteiro, em ordem determinística.

        O grafo é lido por completo de propósito: ciclo indireto é,
        por definição, propriedade global — nenhuma consulta local o
        encontraria (`E3.3` congelou `CYCLE_PROTECTION = SELF_ONLY` e
        deixou o ciclo indireto explicitamente para este módulo).
        """
        stmt = select(LineageEdge.id, LineageEdge.parent_coid, LineageEdge.child_coid).order_by(
            LineageEdge.created_at.asc(), LineageEdge.id.asc()
        )
        return [(row[0], row[1], row[2]) for row in self._session.execute(stmt).all()]

    def causal_edges(self) -> list[tuple[uuid.UUID, uuid.UUID]]:
        """`(event_id, predecessor_event_id)` — arestas causais
        declaradas, globalmente.

        Global porque `HISTORY_BOUNDARY != CAUSAL_BOUNDARY`
        (`E3.9.1`): um predecessor legítimo pode estar na história de
        outro sujeito, e auditar por história perderia exatamente
        esses elos.
        """
        stmt = (
            select(CausalHistoryEvent.id, CausalHistoryEvent.predecessor_event_id)
            .where(CausalHistoryEvent.predecessor_event_id.is_not(None))
            .order_by(CausalHistoryEvent.created_at.asc(), CausalHistoryEvent.id.asc())
        )
        return [(row[0], row[1]) for row in self._session.execute(stmt).all()]

    # --- Self-links ---------------------------------------------------

    def lineage_self_links(self) -> list[uuid.UUID]:
        stmt = select(LineageEdge.id).where(LineageEdge.parent_coid == LineageEdge.child_coid)
        return list(self._session.execute(stmt).scalars().all())

    def relationship_self_links(self) -> list[uuid.UUID]:
        stmt = select(Relationship.id).where(Relationship.source_coid == Relationship.target_coid)
        return list(self._session.execute(stmt).scalars().all())

    def causal_self_predecessors(self) -> list[uuid.UUID]:
        stmt = select(CausalHistoryEvent.id).where(
            CausalHistoryEvent.predecessor_event_id == CausalHistoryEvent.id
        )
        return list(self._session.execute(stmt).scalars().all())

    # --- Unicidade ----------------------------------------------------

    def clids_with_multiple_current(self) -> list[tuple[uuid.UUID, int]]:
        """CLIDs com mais de um objeto `CURRENT` — o invariante que
        `E3.4.1` fechou com índice único parcial. Auditado mesmo assim:
        um patrimônio importado ou manipulado por SQL direto pode estar
        contaminado, e o diagnóstico precisa ser legível por humano."""
        stmt = (
            select(CognitiveObject.clid, sa.func.count())
            .where(
                CognitiveObject.clid.is_not(None),
                CognitiveObject.revision_status == RevisionStatus.CURRENT,
            )
            .group_by(CognitiveObject.clid)
            .having(sa.func.count() > 1)
            .order_by(CognitiveObject.clid)
        )
        return [(row[0], int(row[1])) for row in self._session.execute(stmt).all()]

    def subjects_with_multiple_histories(self) -> list[tuple[uuid.UUID, int]]:
        """Sujeitos com mais de uma `CausalHistory`
        (`ONE_HISTORY_PER_SUBJECT = TRUE`, `E3.9.1`)."""
        stmt = (
            select(CausalHistory.subject_coid, sa.func.count())
            .group_by(CausalHistory.subject_coid)
            .having(sa.func.count() > 1)
            .order_by(CausalHistory.subject_coid)
        )
        return [(row[0], int(row[1])) for row in self._session.execute(stmt).all()]

    def duplicate_active_relationships(
        self,
    ) -> list[tuple[uuid.UUID, uuid.UUID, RelationshipType, int]]:
        """Triplas `(source, target, type)` com mais de uma relação
        **ativa** — `retired_at IS NULL`. Relações já retiradas podem
        repetir a tripla legitimamente (`E3.5.1`): retirar e recriar é
        o lifecycle previsto, não corrupção."""
        stmt = (
            select(
                Relationship.source_coid,
                Relationship.target_coid,
                Relationship.relationship_type,
                sa.func.count(),
            )
            .where(Relationship.retired_at.is_(None))
            .group_by(
                Relationship.source_coid,
                Relationship.target_coid,
                Relationship.relationship_type,
            )
            .having(sa.func.count() > 1)
        )
        return [(row[0], row[1], row[2], int(row[3])) for row in self._session.execute(stmt).all()]

    def non_canonical_symmetric_relationships(self) -> list[uuid.UUID]:
        """Relações `RELATED_TO` gravadas fora da ordem canônica
        (`source < target`, `E3.5.1`). A simetria é normalizada na
        escrita e imposta por `CheckConstraint`; auditar cobre estado
        legado ou inserido por fora."""
        stmt = select(Relationship.id).where(
            Relationship.relationship_type == RelationshipType.RELATED_TO,
            Relationship.source_coid >= Relationship.target_coid,
        )
        return list(self._session.execute(stmt).scalars().all())

    # --- Referências pendentes ----------------------------------------

    def _dangling(
        self,
        column: InstrumentedAttribute[uuid.UUID],
        id_column: InstrumentedAttribute[uuid.UUID],
    ) -> list[uuid.UUID]:
        """Ids das linhas cuja referência a `cognitive_objects` não
        resolve. No PostgreSQL a FK já impede esse estado; a auditoria
        existe para patrimônio importado, restaurado ou manipulado por
        fora — capacidade diagnóstica, não bypass autorizado."""
        existing = select(CognitiveObject.id).where(CognitiveObject.id == column)
        stmt = select(id_column).where(column.is_not(None), ~existing.exists())
        return list(self._session.execute(stmt).scalars().all())

    def lineage_dangling_endpoints(self) -> list[uuid.UUID]:
        return self._dangling(LineageEdge.parent_coid, LineageEdge.id) + self._dangling(
            LineageEdge.child_coid, LineageEdge.id
        )

    def relationship_dangling_endpoints(self) -> list[uuid.UUID]:
        return self._dangling(Relationship.source_coid, Relationship.id) + self._dangling(
            Relationship.target_coid, Relationship.id
        )

    def provenance_dangling_coids(self) -> list[uuid.UUID]:
        return self._dangling(ProvenanceRecord.coid, ProvenanceRecord.id)

    def causal_dangling_subjects(self) -> list[uuid.UUID]:
        return self._dangling(CausalHistory.subject_coid, CausalHistory.id)

    def causal_dangling_predecessors(self) -> list[uuid.UUID]:
        """Eventos cujo predecessor declarado não existe.

        `MISSING_REFERENCE != AUTHORIZATION_TO_FABRICATE`: o módulo
        reporta o elo pendente e **nunca** cria o evento faltante."""
        predecessor = sa.orm.aliased(CausalHistoryEvent)
        existing = select(predecessor.id).where(
            predecessor.id == CausalHistoryEvent.predecessor_event_id
        )
        stmt = select(CausalHistoryEvent.id).where(
            CausalHistoryEvent.predecessor_event_id.is_not(None), ~existing.exists()
        )
        return list(self._session.execute(stmt).scalars().all())
