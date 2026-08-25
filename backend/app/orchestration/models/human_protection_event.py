"""
`HumanProtectionEvent` — evento append-only da aplicação do gate (`E7.4-1 B1a`).

```text
SAFETY_EVENT_APPEND_ONLY = REQUIRED
BLOCK_REASON_VOCABULARY = CLOSED_AND_VERSIONED
HUMAN_PROTECTION_EVENT_CONTENT = NONE
```

Nenhuma coluna recebe prompt, resposta, instrução, documento, segredo ou
memória do usuário. O que se prova aqui é que **um gate decidiu**, não o que
foi pedido — `SAFETY_AUDIT_METADATA != DANGEROUS_PAYLOAD_ARCHIVE` (§20.6).

## Herda `Base`, não `BaseModel`

Precedente literal: `PredictiveReconfigurationEvent` (E5). `BaseModel`
acrescentaria `updated_at`, e uma coluna de "última atualização" numa tabela
que recusa `UPDATE` por gatilho seria uma afirmação falsa no schema.
`decided_at` é o instante de persistência atribuído pelo PostgreSQL por
`server_default=now()`; a aplicação não fornece esse valor.

## Vocabulários em `String` com `CHECK` explícito

O `SAEnum(native_enum=False)` gera um `CHECK` próprio, com nome do enum — o
schema aprovado no R10.1 declara `ck_hpe_outcome_vocab`,
`ck_hpe_gate_position`, `ck_hpe_engagement_vocab` e `ck_hpe_cognitive_op` com
esses nomes exatos, e somar os dois mecanismos duplicaria a mesma regra sob
dois donos. A tipagem vive no value object `HumanProtectionApplication`; o
repositório converte na fronteira, e um valor desconhecido lido do banco
levanta em vez de virar texto solto.

## Onde cada garantia mora (Master Parte III §15.2)

```text
DB_LEVEL  os CHECK de linha derivados de CHECKS_DO_EVENTO, 3 FKs e UNIQUE, aqui
DB_LEVEL  UPDATE/DELETE/TRUNCATE recusados por gatilho, na migration
DB_LEVEL  coerência pai/filha avaliada no COMMIT, constraint trigger diferido
APPLICATION_LEVEL  as mesmas regras de linha, em HumanProtectionApplication
```

Os `CHECK` são declarados **aqui e na migration**, e um teste estático compara
os dois conjuntos de nomes com o schema real: cópia parcial é
`PARTIAL_ENUMERATION = GUARD_WITH_A_HOLE`, e a reconciliação é mecânica em vez
de depender de alguém lembrar.
"""

import uuid

import sqlalchemy as sa
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base
from app.orchestration.schemas.envelope import MAX_REF_LENGTH

SHA256_HEX_LENGTH = 64

TABELA_EVENTO = "human_protection_events"
TABELA_CAPACIDADE = "human_protection_event_capabilities"

_OUTCOMES_SQL = "('allowed','blocked','review_required')"
_ENGAGEMENTS_SQL = "('operational_enablement','analytical','preventive','unspecified')"
_ENGAGEMENTS_QUE_BLOQUEIAM_SQL = "('operational_enablement','unspecified')"
_GATES_SQL = "('g1','g2','g3','g4')"
_PRODUCER_REF_SQL = "'orchestration.protection.bridge.v1'"

CHECKS_DO_EVENTO: tuple[tuple[str, str], ...] = (
    ("ck_hpe_outcome_vocab", f"outcome IN {_OUTCOMES_SQL}"),
    (
        "ck_hpe_engagement_vocab",
        f"capability_engagement IS NULL OR capability_engagement IN {_ENGAGEMENTS_SQL}",
    ),
    ("ck_hpe_gate_position", f"gate_position IN {_GATES_SQL}"),
    ("ck_hpe_producer_ref", f"producer_ref = {_PRODUCER_REF_SQL}"),
    ("ck_hpe_cognitive_op", "cognitive_operation IN ('expose')"),
    ("ck_hpe_fingerprint_algo", "fingerprint_algo_version IN ('1')"),
    ("ck_hpe_binding_algo", "binding_algo_version IN ('1')"),
    ("ck_hpe_boundary_version", "boundary_version > 0"),
    ("ck_hpe_objective_hex", "objective_sha256 ~ '^[0-9a-f]{64}$'"),
    ("ck_hpe_fingerprint_hex", "decision_fingerprint ~ '^[0-9a-f]{64}$'"),
    ("ck_hpe_binding_hex", "binding_sha256 ~ '^[0-9a-f]{64}$'"),
    ("ck_hpe_classifier_nonempty", "classifier_version <> ''"),
    ("ck_hpe_revoked_non_neg", "delegations_revoked >= 0"),
    (
        "ck_hpe_blocked_engagement",
        "outcome <> 'blocked' OR (capability_engagement IS NOT NULL AND "
        f"capability_engagement IN {_ENGAGEMENTS_QUE_BLOQUEIAM_SQL})",
    ),
    ("ck_hpe_allowed_no_engagement", "outcome <> 'allowed' OR capability_engagement IS NULL"),
    ("ck_hpe_allowed_no_pause", "outcome <> 'allowed' OR pause_applied = false"),
    ("ck_hpe_allowed_no_revoke", "outcome <> 'allowed' OR delegations_revoked = 0"),
    (
        "ck_hpe_blocked_pauses",
        "outcome <> 'blocked' OR gate_position = 'g1' OR pause_applied = true",
    ),
    (
        "ck_hpe_review_pauses",
        "outcome <> 'review_required' OR gate_position = 'g1' OR pause_applied = true",
    ),
    ("ck_hpe_review_no_revoke", "outcome <> 'review_required' OR delegations_revoked = 0"),
    ("ck_hpe_g1_schedule_null", "gate_position <> 'g1' OR schedule_id IS NULL"),
    ("ck_hpe_non_g1_has_schedule", "gate_position = 'g1' OR schedule_id IS NOT NULL"),
    ("ck_hpe_g1_step_null", "gate_position <> 'g1' OR step_id IS NULL"),
    ("ck_hpe_non_g1_has_step", "gate_position = 'g1' OR step_id IS NOT NULL"),
    ("ck_hpe_g1_no_pause", "gate_position <> 'g1' OR pause_applied = false"),
    (
        "ck_hpe_no_attempt_unless_g3_allowed",
        "attempt_id IS NULL OR (gate_position = 'g3' AND outcome = 'allowed')",
    ),
    (
        "ck_hpe_g3_allowed_requires_attempt",
        "NOT (gate_position = 'g3' AND outcome = 'allowed') OR attempt_id IS NOT NULL",
    ),
    ("ck_hpe_no_attempt_on_refusal", "outcome = 'allowed' OR attempt_id IS NULL"),
    ("ck_hpe_g3_has_binding_attempt", "gate_position <> 'g3' OR binding_attempt_id IS NOT NULL"),
    ("ck_hpe_non_g3_no_binding_attempt", "gate_position = 'g3' OR binding_attempt_id IS NULL"),
    ("ck_hpe_attempt_matches_binding", "attempt_id IS NULL OR attempt_id = binding_attempt_id"),
)
"""Os `CHECK` de linha, na ordem do schema efetivo.

Fonte única desta declaração no ORM; a migration repete o mesmo conjunto e um
teste estático compara os dois com o `pg_constraint` real.
"""

CHECKS_DA_CAPACIDADE: tuple[tuple[str, str], ...] = (
    ("ck_hpec_ordinal_non_negative", "ordinal >= 0"),
    (
        "ck_hpec_capability_vocab",
        "critical_capability IN ("
        "'child_sexual_exploitation',"
        "'minor_targeting_for_exploitation',"
        "'weapon_of_mass_destruction_enablement',"
        "'catastrophic_harm_enablement')",
    ),
)
"""Os dois `CHECK` da associação. O vocabulário é o da E4, por valor.

```text
CANONICAL_BLOCKED_CAPABILITY = E4.CriticalCapability
```
"""

UQ_IDEMPOTENCIA = "uq_hpe_decision_gate_binding"
"""Chave de idempotência da aplicação.

`(decision_fingerprint, gate_position, binding_sha256)`: a mesma decisão em
duas posições produz **duas** linhas com **um** fingerprint e **dois**
bindings; a mesma aplicação repetida produz uma linha só.
"""


class HumanProtectionEvent(Base):
    """Uma aplicação do gate: que decisão, em que posição, com que efeito."""

    __tablename__ = TABELA_EVENTO

    __table_args__ = (
        UniqueConstraint(
            "decision_fingerprint",
            "gate_position",
            "binding_sha256",
            name=UQ_IDEMPOTENCIA,
        ),
        *(CheckConstraint(sa.text(sql), name=nome) for nome, sql in CHECKS_DO_EVENTO),
        ForeignKeyConstraint(
            ["schedule_id", "control_principal_ref"],
            ["schedules.id", "schedules.control_principal_ref"],
            name="fk_hpe_schedule",
        ),
        ForeignKeyConstraint(
            ["step_id", "schedule_id"],
            ["schedule_steps.id", "schedule_steps.schedule_id"],
            name="fk_hpe_step",
        ),
        ForeignKeyConstraint(
            ["attempt_id", "step_id", "schedule_id"],
            [
                "handoff_attempts.id",
                "handoff_attempts.step_id",
                "handoff_attempts.schedule_id",
            ],
            name="fk_hpe_attempt",
            deferrable=True,
            initially="DEFERRED",
        ),
        Index("ix_hpe_control_principal_ref", "control_principal_ref"),
        Index("ix_hpe_decision_fingerprint", "decision_fingerprint"),
    )
    """Três FKs no evento, e cada uma prova uma coerência diferente.

    ```text
    TWO_VALID_REFERENCES != ONE_COHERENT_REFERENCE
    ```

    A do Schedule prova **dono**; a da etapa prova que a etapa pertence
    àquele Schedule; a da tentativa prova a rota inteira `Schedule → etapa →
    tentativa`. Nenhuma é derivada da outra — vínculo derivado do próprio
    dado que se quer autorizar é tautologia, e foi o achado que reprovou a
    Chain111.

    A FK da tentativa é `DEFERRABLE INITIALLY DEFERRED` porque em G3 o evento
    e a tentativa nascem na mesma transação, e exigir ordem entre eles
    obrigaria o gate a escrever depois do efeito que ele existe para
    preceder.
    """

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)

    control_principal_ref: Mapped[str] = mapped_column(String(MAX_REF_LENGTH), nullable=False)
    """Referência opaca ao principal técnico, como em `schedules`."""

    schedule_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    step_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)

    attempt_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    """Tentativa **materializada** — só existe em `g3 + allowed`."""

    binding_attempt_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    """Tentativa **prealocada**, a que entrou no `binding_sha256`.

    ```text
    G3_APPLICATION_WITHOUT_ATTEMPT_ID = STALE_ATTEMPT_PROOF
    ```
    """

    objective_sha256: Mapped[str] = mapped_column(String(SHA256_HEX_LENGTH), nullable=False)
    decision_fingerprint: Mapped[str] = mapped_column(String(SHA256_HEX_LENGTH), nullable=False)
    fingerprint_algo_version: Mapped[str] = mapped_column(String(8), nullable=False)
    binding_sha256: Mapped[str] = mapped_column(String(SHA256_HEX_LENGTH), nullable=False)
    binding_algo_version: Mapped[str] = mapped_column(String(8), nullable=False)

    outcome: Mapped[str] = mapped_column(String(20), nullable=False)
    capability_engagement: Mapped[str | None] = mapped_column(String(32), nullable=True)
    boundary_version: Mapped[int] = mapped_column(Integer, nullable=False)
    classifier_version: Mapped[str] = mapped_column(String(16), nullable=False)
    cognitive_operation: Mapped[str] = mapped_column(String(32), nullable=False)
    gate_position: Mapped[str] = mapped_column(String(2), nullable=False)
    producer_ref: Mapped[str] = mapped_column(String(64), nullable=False)

    pause_applied: Mapped[bool] = mapped_column(Boolean, nullable=False)
    delegations_revoked: Mapped[int] = mapped_column(Integer, nullable=False)

    decided_at: Mapped[sa.DateTime] = mapped_column(
        DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
    )
    """Instante da decisão, mantido **pelo banco** por `server_default`."""
