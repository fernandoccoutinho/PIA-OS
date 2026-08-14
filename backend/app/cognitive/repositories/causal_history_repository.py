"""
`CausalHistoryRepository` — persistência append-only da história causal
(`E3.9`/`LIB-09`).

`update()`/`delete()` sempre rejeitam, para `CausalHistory` e para
`CausalHistoryEvent`. Mesma disciplina de `LineageRepository`,
`TransformationRepository` e `ProvenanceRepository` — e aqui com uma
razão a mais: apagar um evento não simula a extinção de um rastro
físico, apenas destrói a evidência que o módulo existe para preservar
(`COUT-CH-9`: o registro histórico é ele próprio um rastro).

Navegação é **explícita e de um salto**. `predecessors()` e
`successors()` seguem exclusivamente `predecessor_event_id`; nenhuma
consulta aqui deriva parentesco de `created_at`
(`TEMPORAL PRECEDENCE != CAUSALITY`). Não há caminho mais curto,
centralidade, score causal ou caminho inferido — isso seria graph
engine, `DEFERRED`.

Ordenação: `created_at ASC, id ASC` (canônica desde `E3.1.2`). O Draft
exige eventos "ordenados por created_at, nunca reordenados
retroativamente" — ordenar por tempo de registro é apresentação, e
**não** afirma causalidade entre eventos consecutivos.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.cognitive.errors.exceptions import (
    CausalEventSelfPredecessorError,
    CausalHistoryImmutableError,
)
from app.cognitive.models.causal_history import CausalHistory, CausalHistoryEvent
from app.repositories.base_repository import BaseRepository


class CausalHistoryRepository(BaseRepository[CausalHistory]):
    """Histórias e seus eventos — append-only."""

    def __init__(self, session: Session) -> None:
        super().__init__(session, CausalHistory)

    # --- História -----------------------------------------------------

    def get_by_subject(self, subject_coid: uuid.UUID) -> CausalHistory | None:
        """História de um sujeito, se **registrada**. `None` significa
        "nenhuma história registrada", nunca "nada aconteceu" — e esta
        consulta não cria história alguma."""
        stmt = select(CausalHistory).where(CausalHistory.subject_coid == subject_coid)
        return self._session.execute(stmt).scalar_one_or_none()

    def add_history(self, history: CausalHistory) -> CausalHistory:
        return super().add(history)

    # --- Eventos ------------------------------------------------------

    def add_event(self, event: CausalHistoryEvent) -> CausalHistoryEvent:
        """Anexa um evento. Rejeita auto-predecessor antes de tocar o
        banco — o `CheckConstraint`
        `ck_causal_history_events_no_self_predecessor` é a autoridade
        final, esta é defesa em profundidade (mesmo padrão de
        `LineageRepository`/`RelationshipEngine`)."""
        if event.predecessor_event_id is not None and event.predecessor_event_id == event.id:
            raise CausalEventSelfPredecessorError(event.id)
        self._session.add(event)
        self._session.flush()
        return event

    def get_event(self, event_id: uuid.UUID) -> CausalHistoryEvent | None:
        stmt = select(CausalHistoryEvent).where(CausalHistoryEvent.id == event_id)
        return self._session.execute(stmt).scalar_one_or_none()

    def list_events(self, history_id: uuid.UUID) -> list[CausalHistoryEvent]:
        """Eventos de uma história, em ordem determinística de
        registro. Ordem de registro não é ordem causal."""
        stmt = (
            select(CausalHistoryEvent)
            .where(CausalHistoryEvent.history_id == history_id)
            .order_by(CausalHistoryEvent.created_at.asc(), CausalHistoryEvent.id.asc())
        )
        return list(self._session.execute(stmt).scalars().all())

    def successors(self, event_id: uuid.UUID) -> list[CausalHistoryEvent]:
        """Eventos que declaram `event_id` como predecessor causal —
        explicitamente, nunca por proximidade temporal. Vários
        sucessores para o mesmo predecessor é ramificação legítima, não
        conflito a resolver."""
        stmt = (
            select(CausalHistoryEvent)
            .where(CausalHistoryEvent.predecessor_event_id == event_id)
            .order_by(CausalHistoryEvent.created_at.asc(), CausalHistoryEvent.id.asc())
        )
        return list(self._session.execute(stmt).scalars().all())

    def roots(self, history_id: uuid.UUID) -> list[CausalHistoryEvent]:
        """Eventos sem predecessor registrado. "Sem predecessor
        registrado" nunca significa "não houve predecessor"."""
        stmt = (
            select(CausalHistoryEvent)
            .where(
                CausalHistoryEvent.history_id == history_id,
                CausalHistoryEvent.predecessor_event_id.is_(None),
            )
            .order_by(CausalHistoryEvent.created_at.asc(), CausalHistoryEvent.id.asc())
        )
        return list(self._session.execute(stmt).scalars().all())

    # --- Append-only --------------------------------------------------

    def update(self, entity: CausalHistory) -> CausalHistory:
        """Sempre rejeita — história causal não é reescrita."""
        raise CausalHistoryImmutableError(entity.id, operation="update", entity="CausalHistory")

    def delete(self, entity: CausalHistory) -> None:
        """Sempre rejeita — apagar história destrói o rastro."""
        raise CausalHistoryImmutableError(entity.id, operation="delete", entity="CausalHistory")

    def update_event(self, event: CausalHistoryEvent) -> CausalHistoryEvent:
        """Sempre rejeita. Correção histórica é evento novo que
        referencia o anterior (`predecessor_event_id`)."""
        raise CausalHistoryImmutableError(event.id, operation="update", entity="CausalHistoryEvent")

    def delete_event(self, event: CausalHistoryEvent) -> None:
        """Sempre rejeita."""
        raise CausalHistoryImmutableError(event.id, operation="delete", entity="CausalHistoryEvent")
