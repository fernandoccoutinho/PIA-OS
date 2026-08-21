"""
`CausalHistoryManager` — registro e navegação da história causal
(`E3.9`/`LIB-09`).

O que este módulo garante, e que um event log qualquer não garantiria:

```text
COUT-CH-1   PRESENT OBSERVATION MAY ACCESS PAST STATE
COUT-CH-2   CURRENT != ONLY HISTORICALLY ACCESSIBLE STATE
COUT-CH-3   MATERIAL PERSISTENCE != DISTINCTION PERSISTENCE
COUT-CH-4   DISTINCTION EXTINCTION != HISTORICAL ERASURE
COUT-CH-5   NO PRESENT TRACE != NEVER EXISTED
COUT-CH-6   NO PRESENT TRACE != AUTHORIZATION TO ASSERT PAST EXISTENCE
COUT-CH-7   TEMPORAL PRECEDENCE != CAUSALITY
COUT-CH-8   RECORDED HISTORY != COMPLETE HISTORY OF REALITY
COUT-CH-9   HISTORICAL RECORD IS ITSELF A PRESERVED TRACE
COUT-CH-10  TRANSFORMATION MAY PRESERVE SUBSTRATE WHILE DESTROYING A DISTINCTION
```

Três consequências operacionais:

1. **Ler nunca cria.** `history_for()` e `events_for()` devolvem `None`
   e `[]` quando nada foi registrado, e não materializam história
   implicitamente. Ausência de registro é informação honesta sobre o
   que o PIA sabe, não um vazio a ser preenchido.
2. **Causalidade é declarada, nunca inferida.** Um predecessor causal
   só existe se alguém o informou; ordem de `created_at` jamais
   produz parentesco.
3. **Nada é reescrito.** Anexar evento não toca nos anteriores;
   corrigir é anexar.

Fronteiras que este módulo **não** atravessa: não duplica
`ProvenanceRecord` (referencia), não redefine `TransformationRecord`,
`LineageEdge` ou `Relationship`, e **não** altera `AccessibilityState`
— a matriz completa continua sendo de `E4`, e nenhuma transição
automática acontece aqui.
"""

import uuid
from datetime import datetime

from app.cognitive.models.causal_history import CausalHistory, CausalHistoryEvent
from app.cognitive.models.enums import CausalEventType
from app.cognitive.repositories.causal_history_repository import CausalHistoryRepository


class CausalHistoryManager:
    """Registra fatos históricos e navega a história preservada."""

    def __init__(self, repository: CausalHistoryRepository) -> None:
        self._repository = repository

    # --- Leitura (nunca escreve) --------------------------------------

    def history_for(self, subject_coid: uuid.UUID) -> CausalHistory | None:
        """História **registrada** de um sujeito, ou `None`.

        `None` significa "o PIA não tem história registrada sobre este
        sujeito". Não significa que nada aconteceu com ele, e não
        autoriza afirmar que algo aconteceu."""
        return self._repository.get_by_subject(subject_coid)

    def events_for(self, subject_coid: uuid.UUID) -> list[CausalHistoryEvent]:
        """Eventos preservados sobre um sujeito, em ordem de registro.

        Lista vazia = nenhum rastro registrado. O módulo não
        reconstrói, não interpola e não infere eventos ausentes."""
        history = self._repository.get_by_subject(subject_coid)
        if history is None:
            return []
        return self._repository.list_events(history.id)

    def predecessors(self, event: CausalHistoryEvent) -> list[CausalHistoryEvent]:
        """Predecessor causal declarado (zero ou um), como lista para
        que o contrato não mude se o Draft algum dia admitir mais de
        um. Nunca deriva predecessor de proximidade temporal."""
        if event.predecessor_event_id is None:
            return []
        predecessor = self._repository.get_event(event.predecessor_event_id)
        return [] if predecessor is None else [predecessor]

    def successors(self, event: CausalHistoryEvent) -> list[CausalHistoryEvent]:
        """Eventos que declaram este como predecessor. Mais de um é
        ramificação legítima — o módulo não elege um caminho como "o
        verdadeiro"."""
        return self._repository.successors(event.id)

    def roots(self, subject_coid: uuid.UUID) -> list[CausalHistoryEvent]:
        """Eventos sem predecessor registrado na história do sujeito."""
        history = self._repository.get_by_subject(subject_coid)
        if history is None:
            return []
        return self._repository.roots(history.id)

    # --- Escrita (append-only) ----------------------------------------

    def ensure_history(self, subject_coid: uuid.UUID) -> CausalHistory:
        """História do sujeito, criando-a se ainda não existir.

        Explicitamente separada da leitura: quem quer apenas saber se
        há história usa `history_for()`, que nunca cria nada.
        """
        existing = self._repository.get_by_subject(subject_coid)
        if existing is not None:
            return existing
        return self._repository.add_history(CausalHistory(subject_coid=subject_coid))

    def record(
        self,
        *,
        subject_coid: uuid.UUID,
        event_type: CausalEventType,
        actor_ref: uuid.UUID | None = None,
        payload_ref: str | None = None,
        predecessor: CausalHistoryEvent | None = None,
        occurred_at: datetime | None = None,
    ) -> CausalHistoryEvent:
        """Anexa um fato à história do sujeito.

        `predecessor` é o único mecanismo de causalidade: sem ele, o
        evento simplesmente não declara predecessor — e o sistema não
        inventa um. `occurred_at` é o tempo do evento quando conhecido;
        deixado em `None`, permanece `None`, nunca é preenchido com o
        instante do registro.

        Não commita: a transação é do chamador (`UnitOfWork`), mesma
        disciplina de todos os managers desde `E3.3`.
        """
        history = self.ensure_history(subject_coid)
        event = CausalHistoryEvent(
            history_id=history.id,
            event_type=event_type,
            actor_ref=actor_ref,
            payload_ref=payload_ref,
            predecessor_event_id=None if predecessor is None else predecessor.id,
            occurred_at=occurred_at,
        )
        return self._repository.add_event(event)

    def correct(
        self,
        *,
        previous: CausalHistoryEvent,
        event_type: CausalEventType,
        actor_ref: uuid.UUID | None = None,
        payload_ref: str | None = None,
        occurred_at: datetime | None = None,
    ) -> CausalHistoryEvent:
        """Corrige um fato histórico **anexando** um evento novo que
        referencia o anterior — exatamente como o Draft determina
        ("correção de um evento histórico é um novo evento que
        referencia o anterior, nunca uma mutação in-place").

        O evento corrigido permanece intacto e recuperável: corrigir o
        registro não apaga o que foi registrado antes.
        """
        history_subject = self._repository.get_by_id(previous.history_id)
        assert history_subject is not None, "FK garante a existência da história"
        return self.record(
            subject_coid=history_subject.subject_coid,
            event_type=event_type,
            actor_ref=actor_ref,
            payload_ref=payload_ref,
            predecessor=previous,
            occurred_at=occurred_at,
        )
