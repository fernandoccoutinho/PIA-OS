"""
`CausalHistory` / `CausalHistoryEvent` — história causal preservada
(`E3.9`/`LIB-09`).

Contrato base: `E3_DOMAIN_MODEL_DRAFT.md`, seção "3. CausalHistory /
CausalHistoryEvent". O Draft é a autoridade estrutural; o que segue
registra apenas as **concretizações** que ele delega a `E3.9` e as
duas adições, ambas justificadas e nenhuma decorativa.

Concretizações do Draft:

- `subject_ref: COID | distinction_id` → concretizado como
  `subject_coid` (FK real para `cognitive_objects.id`).
  `CognitiveDistinction` está `DEFERRED` desde `E3.5` e não existe
  como entidade; mesma decisão, pelo mesmo motivo, já tomada em
  `E3.6` para `ProvenanceRecord.coid`.
- `event_type: str  # vocabulário fechado em E3.9` → `CausalEventType`,
  fechado exatamente nos quatro valores que o Draft exemplifica.
- `actor_ref: ProvenanceRecord ref?` → FK nullable para
  `provenance_records.id`.
- `payload_ref: object?  # referência opaca — nunca conteúdo bruto` →
  `String(512)` nullable. Referência, nunca conteúdo:
  `CAUSAL_TRACE != TRANSCRIPT`.

Adições além da lista literal de campos do Draft (mesmo padrão de
`ProvenanceRecord.coid` em `E3.6`, documentado e não silencioso):

- `predecessor_event_id` — o próprio Draft exige que "correção de um
  evento histórico é um novo evento **que referencia o anterior**".
  Sem uma referência explícita de evento para evento, essa referência
  não teria onde existir, e a única forma de ligar dois eventos seria
  inferir causalidade a partir de `created_at` — proibido
  (`TEMPORAL PRECEDENCE != CAUSALITY`). A referência é opcional:
  ausência significa "nenhum predecessor causal registrado", nunca
  "não houve predecessor".
- `occurred_at` — tempo do **evento**, distinto do tempo de
  **registro** (`created_at`, `server_default=now()`). Nullable, e
  `NULL` significa exatamente "o PIA não sabe quando ocorreu" — não é
  preenchido com `created_at` por conveniência. Sem este campo, um
  evento sobre um fato passado seria indistinguível de um fato
  ocorrido no instante do registro, e o sistema estaria afirmando
  implicitamente algo que não sabe (`EPISTEMIC NON-FABRICATION`).

Append-only por construção: `update()`/`delete()` são rejeitados no
repositório, e não existe campo de edição. Corrigir história é
acrescentar evento, nunca reescrever o passado — o próprio registro é
um rastro preservado (`COUT-CH-9`).
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.cognitive.models.enums import CausalEventType
from app.models.base_model import BaseModel


class CausalHistory(BaseModel):
    """História causal de um sujeito cognitivo.

    `ONE_HISTORY_PER_SUBJECT = TRUE` (decisão `E3.9.1`): um sujeito
    tem no máximo uma história (`UNIQUE(subject_coid)`). A história é
    o **agregado histórico daquele sujeito**, não uma coleção
    arbitrária de coleções — ramificação causal acontece entre
    eventos, nunca criando várias histórias para o mesmo sujeito.

    Isso **não** confina causalidade à história: um evento pode
    declarar como predecessor um evento da história de outro sujeito
    (`CROSS_HISTORY_PREDECESSOR = ALLOWED`). Ver
    `CausalHistoryEvent.predecessor_event_id`:

    ```text
    history boundary != causal boundary
    ```
    """

    __tablename__ = "causal_histories"

    subject_coid: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("cognitive_objects.id"), nullable=False, unique=True, index=True
    )
    """Sujeito da história — `subject_ref` do Draft, concretizado como
    COID. Sem `ondelete`: apagar fisicamente um objeto que tem
    história registrada não é operação prevista, e o soft delete de
    `E3.1` não remove a linha."""


class CausalHistoryEvent(BaseModel):
    """Fato preservado dentro de uma história causal.

    Não é log de aplicação: cada linha é um fato histórico que o PIA
    registrou, e a ausência de linha significa ausência de registro —
    nunca ausência de acontecimento.
    """

    __tablename__ = "causal_history_events"

    __table_args__ = (
        CheckConstraint(
            "predecessor_event_id IS NULL OR predecessor_event_id != id",
            name="ck_causal_history_events_no_self_predecessor",
        ),
    )
    """Um evento não pode ser predecessor causal de si mesmo. Defesa em
    profundidade: o manager já rejeita antes, mas o banco é a
    autoridade final.

    Ciclos indiretos não precisam de proteção adicional e a política
    **não** foi copiada de `LineageEdge` (`SELF_ONLY`) por hábito:
    aqui a proteção é *estrutural*. Como a tabela é append-only e a FK
    exige que o predecessor **já exista** no momento do INSERT, toda
    aresta aponta necessariamente para um evento anterior — o grafo é
    um DAG por construção, e não existe operação de update capaz de
    fechar um ciclo depois."""

    history_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("causal_histories.id"), nullable=False, index=True
    )
    """`history_ref` do Draft."""

    event_type: Mapped[CausalEventType] = mapped_column(
        SAEnum(CausalEventType, name="causal_event_type", native_enum=False, length=32),
        nullable=False,
    )
    """Vocabulário fechado em `E3.9`, conforme o Draft determina."""

    actor_ref: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("provenance_records.id"), nullable=True, default=None
    )
    """`ProvenanceRecord` responsável, quando conhecido. Referência —
    nenhum campo de provider/model/session/agent é copiado para cá:
    `PROVENANCE != CAUSAL HISTORY`."""

    payload_ref: Mapped[str | None] = mapped_column(String(512), nullable=True, default=None)
    """Referência opaca a evidência externa. **Nunca** conteúdo:
    `CAUSAL_TRACE != TRANSCRIPT`, `TRANSCRIPT_AUTO_STORAGE = NONE`."""

    predecessor_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("causal_history_events.id"), nullable=True, default=None, index=True
    )
    """Predecessor causal **explícito**. `None` significa "nenhum
    predecessor registrado", nunca "não houve predecessor" — e nunca
    autoriza inferir um a partir de `created_at`.

    `CROSS_HISTORY_PREDECESSOR = ALLOWED` (decisão `E3.9.1`): a FK é
    global sobre `causal_history_events`, deliberadamente **sem**
    restrição `child.history_id == predecessor.history_id`.
    Transmissão causal atravessa sujeitos — uma fonte produz um
    evento, um receptor registra outro que o referencia — e proibir
    isso obrigaria a fundir as duas histórias, o que apagaria a
    distinção entre os dois sujeitos.

    Referenciar não é fundir:

    ```text
    cross-history predecessor != shared identity
    COID_A != COID_B  e  HISTORY_A != HISTORY_B
    permanecem válidos mesmo com event_B.predecessor_event_id = event_A.id
    ```
    """

    occurred_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    """Tempo do evento, quando conhecido. `None` = desconhecido, e o
    PIA não o substitui por `created_at`. `occurred_at <= created_at` é
    o caso normal de um rastro arqueológico: o fato ocorreu antes de
    ser observado/registrado."""
