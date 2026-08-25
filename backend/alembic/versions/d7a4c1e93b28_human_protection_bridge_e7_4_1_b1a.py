"""create the human protection enforcement bridge (E7.4-1 B1a)

Revision ID: d7a4c1e93b28
Revises: c58d1e0a94f7
Create Date: 2026-08-24 21:40:00.000000

Filha única de `c58d1e0a94f7`. Nenhuma migration anterior é alterada.

## O que entra

```text
uq_schedules_id_principal              UNIQUE corretivo, alvo da FK composta
human_protection_events                30 CHECK · 3 FK · UNIQUE de idempotência
human_protection_event_capabilities     2 CHECK · 1 FK · PK composta
2 gatilhos append-only por tabela      UPDATE/DELETE e TRUNCATE
2 constraint triggers DIFERIDOS        coerência pai/filha, avaliada no COMMIT
```

## Por que as três FKs, e não uma

```text
TWO_VALID_REFERENCES != ONE_COHERENT_REFERENCE
```

A do Schedule prova dono; a da etapa prova que a etapa é daquele Schedule; a
da tentativa prova a rota inteira. Nenhuma é derivada de outra — vínculo
derivado do próprio dado que se quer autorizar é tautologia, e foi o achado
que reprovou a Chain111. A da tentativa é `DEFERRABLE INITIALLY DEFERRED`
porque em G3 evento e tentativa nascem na mesma transação.

## Por que a coerência pai/filha é gatilho, e não CHECK

`CHECK` não cruza tabelas. Um bloqueio precisa de ao menos uma capacidade, um
não-bloqueio de nenhuma, e os ordinais precisam ser exatamente `0..n-1` — três
propriedades que só existem quando as duas linhas já estão escritas. Elas são
avaliadas no `COMMIT` por constraint triggers diferidos.

Achado medido na validação R10.1 e preservado aqui: o `TRUNCATE` do pai é
recusado **pela FK do filho**, antes do gatilho; só `TRUNCATE CASCADE` alcança
o gatilho do evento.

```text
FK_REFUSAL != TRIGGER_REFUSAL
```

## Downgrade

Recusado com linhas presentes: o evento é evidência de proteção humana e
append-only, e afrouxar schema com história dentro seria apagamento por
rollback. Sem linhas, remove o que criou — reversibilidade de schema, nunca
apagamento de história.

```text
SCHEMA REVERSIBILITY != HISTORICAL ERASURE
```
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d7a4c1e93b28"
down_revision: str | None = "c58d1e0a94f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SCHEDULES = "schedules"
_EVENTOS = "human_protection_events"
_CAPACIDADES = "human_protection_event_capabilities"

_UQ_SCHEDULES = "uq_schedules_id_principal"
_UQ_IDEMPOTENCIA = "uq_hpe_decision_gate_binding"

_OUTCOMES_SQL = "('allowed','blocked','review_required')"
_ENGAGEMENTS_SQL = "('operational_enablement','analytical','preventive','unspecified')"
_ENGAGEMENTS_QUE_BLOQUEIAM_SQL = "('operational_enablement','unspecified')"
_GATES_SQL = "('g1','g2','g3','g4')"
_PRODUCER_REF_SQL = "'orchestration.protection.bridge.v1'"
_CAPACIDADES_SQL = (
    "('child_sexual_exploitation',"
    "'minor_targeting_for_exploitation',"
    "'weapon_of_mass_destruction_enablement',"
    "'catastrophic_harm_enablement')"
)

#: Os trinta `CHECK` de linha do evento, na ordem do schema aprovado no R10.1.
#: O mesmo conjunto é declarado no ORM (`CHECKS_DO_EVENTO`); um teste estático
#: compara os dois com o `pg_constraint` real, porque cópia parcial é
#: `PARTIAL_ENUMERATION = GUARD_WITH_A_HOLE`.
_CHECKS_DO_EVENTO: tuple[tuple[str, str], ...] = (
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
        f"outcome <> 'blocked' OR capability_engagement IN " f"{_ENGAGEMENTS_QUE_BLOQUEIAM_SQL}",
    ),
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

_CHECKS_DA_CAPACIDADE: tuple[tuple[str, str], ...] = (
    ("ck_hpec_ordinal_non_negative", "ordinal >= 0"),
    ("ck_hpec_capability_vocab", f"critical_capability IN {_CAPACIDADES_SQL}"),
)

_APPEND_ONLY = (
    (_EVENTOS, "trg_hpe_append_only", "trg_hpe_no_truncate"),
    (_CAPACIDADES, "trg_hpec_append_only", "trg_hpec_no_truncate"),
)

_FUNCAO_APPEND_ONLY = "hp_append_only"
_FUNCAO_COERENCIA = "hp_event_coherence"


def upgrade() -> None:
    e_postgres = op.get_bind().dialect.name == "postgresql"

    # Alvo composto exigido pela FK de dono do evento. Redundante em
    # cardinalidade, obrigatório em referência.
    op.create_unique_constraint(_UQ_SCHEDULES, _SCHEDULES, ["id", "control_principal_ref"])

    op.create_table(
        _EVENTOS,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("control_principal_ref", sa.String(length=255), nullable=False),
        sa.Column("schedule_id", sa.Uuid(), nullable=True),
        sa.Column("step_id", sa.Uuid(), nullable=True),
        sa.Column("attempt_id", sa.Uuid(), nullable=True),
        sa.Column("binding_attempt_id", sa.Uuid(), nullable=True),
        sa.Column("objective_sha256", sa.String(length=64), nullable=False),
        sa.Column("decision_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("fingerprint_algo_version", sa.String(length=8), nullable=False),
        sa.Column("binding_sha256", sa.String(length=64), nullable=False),
        sa.Column("binding_algo_version", sa.String(length=8), nullable=False),
        sa.Column("outcome", sa.String(length=20), nullable=False),
        sa.Column("capability_engagement", sa.String(length=32), nullable=True),
        sa.Column("boundary_version", sa.Integer(), nullable=False),
        sa.Column("classifier_version", sa.String(length=16), nullable=False),
        sa.Column("cognitive_operation", sa.String(length=32), nullable=False),
        sa.Column("gate_position", sa.String(length=2), nullable=False),
        sa.Column("producer_ref", sa.String(length=64), nullable=False),
        sa.Column("pause_applied", sa.Boolean(), nullable=False),
        sa.Column("delegations_revoked", sa.Integer(), nullable=False),
        sa.Column(
            "decided_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id", name="pk_human_protection_events"),
        sa.UniqueConstraint(
            "decision_fingerprint",
            "gate_position",
            "binding_sha256",
            name=_UQ_IDEMPOTENCIA,
        ),
        *(sa.CheckConstraint(sa.text(sql), name=nome) for nome, sql in _CHECKS_DO_EVENTO),
        sa.ForeignKeyConstraint(
            ["schedule_id", "control_principal_ref"],
            [f"{_SCHEDULES}.id", f"{_SCHEDULES}.control_principal_ref"],
            name="fk_hpe_schedule",
        ),
        sa.ForeignKeyConstraint(
            ["step_id", "schedule_id"],
            ["schedule_steps.id", "schedule_steps.schedule_id"],
            name="fk_hpe_step",
        ),
        sa.ForeignKeyConstraint(
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
    )
    op.create_index("ix_hpe_control_principal_ref", _EVENTOS, ["control_principal_ref"])
    op.create_index("ix_hpe_decision_fingerprint", _EVENTOS, ["decision_fingerprint"])

    op.create_table(
        _CAPACIDADES,
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("critical_capability", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("event_id", "ordinal", name="pk_hpec"),
        sa.UniqueConstraint("event_id", "critical_capability", name="uq_hpec_event_capability"),
        *(sa.CheckConstraint(sa.text(sql), name=nome) for nome, sql in _CHECKS_DA_CAPACIDADE),
        sa.ForeignKeyConstraint(["event_id"], [f"{_EVENTOS}.id"], name="fk_hpec_event"),
    )

    if not e_postgres:  # pragma: no cover - a suíte roda em PostgreSQL real
        return

    op.execute(
        sa.text(
            f"""
            CREATE OR REPLACE FUNCTION {_FUNCAO_APPEND_ONLY}()
            RETURNS TRIGGER
            LANGUAGE plpgsql
            AS $$
            BEGIN
                RAISE EXCEPTION
                    'append-only: % is rejected on %', TG_OP, TG_TABLE_NAME;
            END;
            $$;
            """
        )
    )
    for tabela, gatilho_linha, gatilho_truncate in _APPEND_ONLY:
        op.execute(
            sa.text(
                f"CREATE TRIGGER {gatilho_linha} BEFORE UPDATE OR DELETE ON {tabela} "
                f"FOR EACH ROW EXECUTE FUNCTION {_FUNCAO_APPEND_ONLY}()"
            )
        )
        # O gatilho de LINHA criado no pai NÃO cobre `TRUNCATE`: são eventos
        # distintos, e um `TRUNCATE` direto atravessaria sem ele.
        op.execute(
            sa.text(
                f"CREATE TRIGGER {gatilho_truncate} BEFORE TRUNCATE ON {tabela} "
                f"FOR EACH STATEMENT EXECUTE FUNCTION {_FUNCAO_APPEND_ONLY}()"
            )
        )

    op.execute(
        sa.text(
            f"""
            CREATE OR REPLACE FUNCTION {_FUNCAO_COERENCIA}()
            RETURNS TRIGGER
            LANGUAGE plpgsql
            AS $$
            DECLARE
                alvo uuid; desfecho text; n integer; max_ord integer;
            BEGIN
                -- `CASE` avaliaria os DOIS ramos na atribuição, e
                -- `NEW.event_id` não existe na tabela pai. `IF` resolve o
                -- campo por ramo.
                IF TG_TABLE_NAME = '{_EVENTOS}' THEN
                    alvo := NEW.id;
                ELSE
                    alvo := NEW.event_id;
                END IF;
                SELECT outcome INTO desfecho FROM {_EVENTOS} WHERE id = alvo;
                IF NOT FOUND THEN RETURN NULL; END IF;
                SELECT count(*), coalesce(max(ordinal), -1) INTO n, max_ord
                  FROM {_CAPACIDADES} WHERE event_id = alvo;
                IF desfecho = 'blocked' AND n < 1 THEN
                    RAISE EXCEPTION
                        'blocked requires at least one capability (event %)', alvo;
                END IF;
                IF desfecho <> 'blocked' AND n <> 0 THEN
                    RAISE EXCEPTION
                        'only blocked carries capabilities (event %)', alvo;
                END IF;
                IF n > 0 AND max_ord <> n - 1 THEN
                    RAISE EXCEPTION
                        'ordinals must be 0..n-1 (event %)', alvo;
                END IF;
                RETURN NULL;
            END;
            $$;
            """
        )
    )
    op.execute(
        sa.text(
            f"CREATE CONSTRAINT TRIGGER trg_hpe_coherence AFTER INSERT ON {_EVENTOS} "
            f"DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
            f"EXECUTE FUNCTION {_FUNCAO_COERENCIA}()"
        )
    )
    op.execute(
        sa.text(
            f"CREATE CONSTRAINT TRIGGER trg_hpec_coherence AFTER INSERT ON {_CAPACIDADES} "
            f"DEFERRABLE INITIALLY DEFERRED FOR EACH ROW "
            f"EXECUTE FUNCTION {_FUNCAO_COERENCIA}()"
        )
    )


def downgrade() -> None:
    conexao = op.get_bind()
    e_postgres = conexao.dialect.name == "postgresql"

    linhas = conexao.execute(sa.text(f"SELECT count(*) FROM {_EVENTOS}")).scalar_one()
    if linhas:
        raise RuntimeError(
            f"downgrade recusado: {linhas} evento(s) de proteção humana em {_EVENTOS}; "
            "evidência append-only de proteção humana é história e não pode ser "
            "afrouxada por um rollback de schema com linhas presentes"
        )

    if e_postgres:  # pragma: no cover - a suíte roda em PostgreSQL real
        for gatilho, tabela in (
            ("trg_hpec_coherence", _CAPACIDADES),
            ("trg_hpe_coherence", _EVENTOS),
        ):
            op.execute(sa.text(f"DROP TRIGGER IF EXISTS {gatilho} ON {tabela}"))
        for tabela, gatilho_linha, gatilho_truncate in _APPEND_ONLY:
            op.execute(sa.text(f"DROP TRIGGER IF EXISTS {gatilho_truncate} ON {tabela}"))
            op.execute(sa.text(f"DROP TRIGGER IF EXISTS {gatilho_linha} ON {tabela}"))
        op.execute(sa.text(f"DROP FUNCTION IF EXISTS {_FUNCAO_COERENCIA}()"))
        op.execute(sa.text(f"DROP FUNCTION IF EXISTS {_FUNCAO_APPEND_ONLY}()"))

    op.drop_table(_CAPACIDADES)
    op.drop_index("ix_hpe_decision_fingerprint", table_name=_EVENTOS)
    op.drop_index("ix_hpe_control_principal_ref", table_name=_EVENTOS)
    op.drop_table(_EVENTOS)
    op.drop_constraint(_UQ_SCHEDULES, _SCHEDULES, type_="unique")
