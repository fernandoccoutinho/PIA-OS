"""create orchestration core tables (E7.1)

Revision ID: a7f31c05be24
Revises: b4d71c58ae02
Create Date: 2026-08-22 22:55:00.000000

Cinco tabelas, um head, filha única de `b4d71c58ae02`.

```text
schedules        trabalho governado, vinculado ao principal técnico
schedule_steps   composição ordenada, com contexto mínimo declarado
handoff_attempts tentativa de repasse; mesmo conteúdo pode ter várias
seal_receipts    APPEND-ONLY: o ato de selar, com trigger de rejeição
command_receipts idempotência por (principal, operação, chave)
```

Três decisões do schema merecem registro, porque são o que torna as
provas possíveis em vez de prováveis:

1. `uq_command_receipts_principal_operation_key` não é conveniência de
   consulta: é o alvo do `ON CONFLICT` que serializa a reivindicação do
   comando. Sem ela o upsert não teria alvo e duas réplicas produziriam
   dois efeitos para o mesmo comando. Chave global sozinha faria pior:
   colidiria trabalhos de principais diferentes, e a colisão apareceria
   como idempotência.

2. `orchestration_context_refs_are_canonical()` existe porque `CHECK` não
   percorre array sozinho. `NOT NULL` deixaria SQL bruto gravar
   `context_ref` sem `sha256`, com chave a mais ou com `bytes` negativo —
   e o hash do envelope passaria a descrever uma declaração inválida.

   ```text
   APP_TYPED_BOUNDARY != DATABASE_INTEGRITY
   INLINE_CONTENT_WITHOUT_HASH = FORBIDDEN
   ```

3. `seal_receipts` é append-only no banco, no molde medido de
   `predictive_reconfiguration_events` (E5.l): função + trigger de linha
   + trigger de `TRUNCATE`. O `downgrade` recusa com recibos gravados, em
   vez de apagar história por conveniência de rollback.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a7f31c05be24"
down_revision: str | None = "b4d71c58ae02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_SCHEDULES = "schedules"
_STEPS = "schedule_steps"
_ATTEMPTS = "handoff_attempts"
_RECEIPTS = "seal_receipts"
_COMMANDS = "command_receipts"

_FUNCTION_CONTEXT_REFS = "orchestration_context_refs_are_canonical"
_FUNCTION_APPEND_ONLY = "reject_seal_receipt_mutation"
_ROW_TRIGGER = "trg_seal_receipts_append_only"
_TRUNCATE_TRIGGER = "trg_seal_receipts_no_truncate"

_SCHEDULE_STATES = ("draft", "active", "paused", "completed", "cancelled", "stopped")
_STEP_STATES = (
    "pending",
    "dispatched",
    "awaiting_return",
    "returned",
    "rejected",
    "failed",
    "cancelled",
)
_ATTEMPT_STATES = (
    "open",
    "closed_ok",
    "closed_rejected",
    "closed_timeout",
    "closed_cancelled",
)
_HANDOFF_MODES = (
    "manual_handoff",
    "supervised_automatic_handoff",
    "restricted_automatic_continuation",
)


def _json_type() -> sa.types.TypeEngine[object]:
    return sa.JSON().with_variant(sa.dialects.postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    e_postgres = op.get_bind().dialect.name == "postgresql"

    if e_postgres:
        op.execute(
            sa.text(
                f"""
                CREATE OR REPLACE FUNCTION {_FUNCTION_CONTEXT_REFS}(value jsonb)
                RETURNS boolean
                LANGUAGE plpgsql
                IMMUTABLE
                SET search_path = pg_catalog
                AS $$
                DECLARE
                    item jsonb;
                    uri_value text;
                BEGIN
                    IF value IS NULL OR jsonb_typeof(value) <> 'array' THEN
                        RETURN false;
                    END IF;
                    FOR item IN SELECT * FROM jsonb_array_elements(value) LOOP
                        IF jsonb_typeof(item) <> 'object' THEN
                            RETURN false;
                        END IF;
                        IF (SELECT count(*) FROM jsonb_object_keys(item)) <> 3 THEN
                            RETURN false;
                        END IF;
                        IF NOT (item ? 'uri' AND item ? 'sha256' AND item ? 'bytes') THEN
                            RETURN false;
                        END IF;
                        IF jsonb_typeof(item -> 'uri') <> 'string'
                           OR jsonb_typeof(item -> 'sha256') <> 'string'
                           OR jsonb_typeof(item -> 'bytes') <> 'number' THEN
                            RETURN false;
                        END IF;
                        uri_value := item ->> 'uri';
                        IF length(btrim(uri_value)) = 0 THEN
                            RETURN false;
                        END IF;
                        IF (item ->> 'sha256') !~ '^[0-9a-f]{{64}}$' THEN
                            RETURN false;
                        END IF;
                        IF (item ->> 'bytes') !~ '^[0-9]+$' THEN
                            RETURN false;
                        END IF;
                    END LOOP;
                    RETURN true;
                END;
                $$;
                """
            )
        )

    op.create_table(
        _SCHEDULES,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column(
            "state",
            sa.Enum(
                *_SCHEDULE_STATES,
                name="orchestration_schedule_state",
                native_enum=False,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column(
            "execution_mode",
            sa.Enum(
                *_HANDOFF_MODES,
                name="orchestration_handoff_mode",
                native_enum=False,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column("control_principal_ref", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("length(btrim(title)) > 0", name="ck_schedules_title_not_blank"),
        sa.CheckConstraint(
            "length(btrim(control_principal_ref)) > 0",
            name="ck_schedules_control_principal_not_blank",
        ),
    )
    op.create_index("ix_schedules_control_principal_ref", _SCHEDULES, ["control_principal_ref"])

    op.create_table(
        _STEPS,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("schedule_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=64), nullable=False),
        sa.Column("instruction_ref", sa.String(length=255), nullable=False),
        sa.Column("context_refs", _json_type(), nullable=False),
        sa.Column("expected_output_contract", sa.String(length=255), nullable=False),
        sa.Column("constraints", _json_type(), nullable=False),
        sa.Column(
            "state",
            sa.Enum(
                *_STEP_STATES,
                name="orchestration_step_state",
                native_enum=False,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["schedule_id"], [f"{_SCHEDULES}.id"], name="fk_schedule_steps_schedule"
        ),
        sa.UniqueConstraint("schedule_id", "position", name="uq_schedule_steps_position"),
        sa.CheckConstraint("position >= 1", name="ck_schedule_steps_position_positive"),
        sa.CheckConstraint("length(btrim(role)) > 0", name="ck_schedule_steps_role_not_blank"),
        sa.CheckConstraint(
            "length(btrim(instruction_ref)) > 0",
            name="ck_schedule_steps_instruction_ref_not_blank",
        ),
        sa.CheckConstraint(
            "length(btrim(expected_output_contract)) > 0",
            name="ck_schedule_steps_output_contract_not_blank",
        ),
    )
    if e_postgres:
        op.create_check_constraint(
            "ck_schedule_steps_context_refs_canonical",
            _STEPS,
            sa.text(f"{_FUNCTION_CONTEXT_REFS}(context_refs)"),
        )
        op.create_check_constraint(
            "ck_schedule_steps_constraints_object",
            _STEPS,
            sa.text("jsonb_typeof(constraints) = 'object'"),
        )

    op.create_table(
        _ATTEMPTS,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("schedule_id", sa.Uuid(), nullable=False),
        sa.Column("step_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("envelope_version", sa.String(length=16), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column(
            "state",
            sa.Enum(
                *_ATTEMPT_STATES,
                name="orchestration_attempt_state",
                native_enum=False,
                length=24,
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["schedule_id"], [f"{_SCHEDULES}.id"], name="fk_handoff_attempts_schedule"
        ),
        sa.ForeignKeyConstraint(["step_id"], [f"{_STEPS}.id"], name="fk_handoff_attempts_step"),
        sa.UniqueConstraint("step_id", "attempt_number", name="uq_handoff_attempts_step_number"),
        sa.CheckConstraint("attempt_number >= 1", name="ck_handoff_attempts_number_positive"),
        sa.CheckConstraint(
            "length(content_sha256) = 64", name="ck_handoff_attempts_content_sha256_length"
        ),
        sa.CheckConstraint(
            "length(btrim(envelope_version)) > 0",
            name="ck_handoff_attempts_envelope_version_not_blank",
        ),
    )
    op.create_index("ix_handoff_attempts_schedule", _ATTEMPTS, ["schedule_id"])
    op.create_index("ix_handoff_attempts_content_sha256", _ATTEMPTS, ["content_sha256"])
    if e_postgres:
        op.create_check_constraint(
            "ck_handoff_attempts_content_sha256_hex",
            _ATTEMPTS,
            sa.text("content_sha256 ~ '^[0-9a-f]{64}$'"),
        )

    op.create_table(
        _RECEIPTS,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("sealed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("sealer_ref", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["attempt_id"], [f"{_ATTEMPTS}.id"], name="fk_seal_receipts_attempt"
        ),
        sa.UniqueConstraint("attempt_id", name="uq_seal_receipts_attempt"),
        sa.CheckConstraint(
            "length(content_sha256) = 64", name="ck_seal_receipts_content_sha256_length"
        ),
        sa.CheckConstraint(
            "length(btrim(sealer_ref)) > 0", name="ck_seal_receipts_sealer_ref_not_blank"
        ),
    )
    op.create_index("ix_seal_receipts_content_sha256", _RECEIPTS, ["content_sha256"])
    if e_postgres:
        op.create_check_constraint(
            "ck_seal_receipts_content_sha256_hex",
            _RECEIPTS,
            sa.text("content_sha256 ~ '^[0-9a-f]{64}$'"),
        )

    op.create_table(
        _COMMANDS,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("technical_principal_ref", sa.String(length=255), nullable=False),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column("command_key", sa.String(length=255), nullable=False),
        sa.Column("outcome_ref", sa.String(length=255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "technical_principal_ref",
            "operation",
            "command_key",
            name="uq_command_receipts_principal_operation_key",
        ),
        sa.CheckConstraint(
            "length(btrim(technical_principal_ref)) > 0",
            name="ck_command_receipts_principal_not_blank",
        ),
        sa.CheckConstraint(
            "length(btrim(operation)) > 0", name="ck_command_receipts_operation_not_blank"
        ),
        sa.CheckConstraint(
            "length(btrim(command_key)) > 0", name="ck_command_receipts_command_key_not_blank"
        ),
        sa.CheckConstraint(
            "length(btrim(outcome_ref)) > 0", name="ck_command_receipts_outcome_ref_not_blank"
        ),
    )
    op.create_index("ix_command_receipts_principal", _COMMANDS, ["technical_principal_ref"])

    if e_postgres:
        op.execute(
            sa.text(
                f"""
                CREATE OR REPLACE FUNCTION {_FUNCTION_APPEND_ONLY}()
                RETURNS TRIGGER
                LANGUAGE plpgsql
                SET search_path = pg_catalog
                AS $$
                BEGIN
                    RAISE EXCEPTION
                        '{_RECEIPTS} is append-only: % rejected', TG_OP
                        USING ERRCODE = 'raise_exception';
                END;
                $$;
                """
            )
        )
        op.execute(
            sa.text(
                f"""
                CREATE TRIGGER {_ROW_TRIGGER}
                BEFORE UPDATE OR DELETE ON {_RECEIPTS}
                FOR EACH ROW EXECUTE FUNCTION {_FUNCTION_APPEND_ONLY}();
                """
            )
        )
        op.execute(
            sa.text(
                f"""
                CREATE TRIGGER {_TRUNCATE_TRIGGER}
                BEFORE TRUNCATE ON {_RECEIPTS}
                FOR EACH STATEMENT EXECUTE FUNCTION {_FUNCTION_APPEND_ONLY}();
                """
            )
        )


def downgrade() -> None:
    connection = op.get_bind()
    linhas = connection.execute(sa.text(f"SELECT count(*) FROM {_RECEIPTS}")).scalar_one()
    if linhas:
        raise RuntimeError(
            f"downgrade recusado: {linhas} recibo(s) de selamento registrado(s); "
            "o histórico append-only não pode ser apagado implicitamente"
        )
    e_postgres = connection.dialect.name == "postgresql"
    if e_postgres:
        op.execute(sa.text(f"DROP TRIGGER IF EXISTS {_TRUNCATE_TRIGGER} ON {_RECEIPTS}"))
        op.execute(sa.text(f"DROP TRIGGER IF EXISTS {_ROW_TRIGGER} ON {_RECEIPTS}"))
        op.execute(sa.text(f"DROP FUNCTION IF EXISTS {_FUNCTION_APPEND_ONLY}()"))
    op.drop_index("ix_command_receipts_principal", table_name=_COMMANDS)
    op.drop_table(_COMMANDS)
    op.drop_index("ix_seal_receipts_content_sha256", table_name=_RECEIPTS)
    op.drop_table(_RECEIPTS)
    op.drop_index("ix_handoff_attempts_content_sha256", table_name=_ATTEMPTS)
    op.drop_index("ix_handoff_attempts_schedule", table_name=_ATTEMPTS)
    op.drop_table(_ATTEMPTS)
    op.drop_table(_STEPS)
    op.drop_index("ix_schedules_control_principal_ref", table_name=_SCHEDULES)
    op.drop_table(_SCHEDULES)
    if e_postgres:
        op.execute(sa.text(f"DROP FUNCTION IF EXISTS {_FUNCTION_CONTEXT_REFS}(jsonb)"))
