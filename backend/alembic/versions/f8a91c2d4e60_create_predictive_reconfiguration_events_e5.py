"""create predictive_reconfiguration_events append-only table (E5.l)

Revision ID: f8a91c2d4e60
Revises: e7c25a91f4b3
Create Date: 2026-08-21 10:40:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f8a91c2d4e60"
down_revision: str | None = "e7c25a91f4b3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABLE = "predictive_reconfiguration_events"
_FUNCTION = "reject_predictive_reconfiguration_mutation"
_FUNCTION_STRING_ARRAY = "predictive_string_array_is_canonical"
_ROW_TRIGGER = "trg_predictive_reconfiguration_append_only"
_TRUNCATE_TRIGGER = "trg_predictive_reconfiguration_no_truncate"


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            sa.text(
                f"""
                CREATE OR REPLACE FUNCTION {_FUNCTION_STRING_ARRAY}(
                    value jsonb,
                    require_nonempty boolean
                )
                RETURNS boolean
                LANGUAGE plpgsql
                IMMUTABLE
                SET search_path = pg_catalog
                AS $$
                DECLARE
                    item jsonb;
                    previous text := NULL;
                    current_value text;
                BEGIN
                    IF value IS NULL OR jsonb_typeof(value) <> 'array' THEN
                        RETURN false;
                    END IF;
                    IF require_nonempty AND jsonb_array_length(value) = 0 THEN
                        RETURN false;
                    END IF;
                    FOR item IN SELECT * FROM jsonb_array_elements(value) LOOP
                        IF jsonb_typeof(item) <> 'string' THEN
                            RETURN false;
                        END IF;
                        current_value := item #>> '{{}}';
                        IF length(btrim(current_value)) = 0 THEN
                            RETURN false;
                        END IF;
                        IF previous IS NOT NULL AND current_value <= previous THEN
                            RETURN false;
                        END IF;
                        previous := current_value;
                    END LOOP;
                    RETURN true;
                END;
                $$;
                """
            )
        )
    op.create_table(
        _TABLE,
        sa.Column("event_id", sa.Uuid(), nullable=False),
        sa.Column("subject_key", sa.String(length=64), nullable=False),
        sa.Column(
            "event_kind",
            sa.Enum(
                "PROMOTE",
                "ROLLBACK",
                name="predictive_reconfiguration_event_kind",
                native_enum=False,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("from_version", sa.Integer(), nullable=False),
        sa.Column("to_version", sa.Integer(), nullable=False),
        sa.Column("active_candidate_ref", sa.Uuid(), nullable=False),
        sa.Column("candidate_payload_sha256", sa.String(length=64), nullable=False),
        sa.Column("model_ref", sa.String(length=255), nullable=False),
        sa.Column(
            "hypothesis_refs",
            sa.JSON().with_variant(sa.dialects.postgresql.JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.Column("validation_ref", sa.String(length=255), nullable=False),
        sa.Column("cost_ref", sa.String(length=255), nullable=False),
        sa.Column("responsible_ref", sa.String(length=255), nullable=False),
        sa.Column("rollback_plan_ref", sa.String(length=255), nullable=False),
        sa.Column("approval_reference", sa.String(length=255), nullable=False),
        sa.Column("approval_version", sa.Integer(), nullable=False),
        sa.Column(
            "approval_scope",
            sa.JSON().with_variant(sa.dialects.postgresql.JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.Column("approval_jurisdiction", sa.String(length=255), nullable=True),
        sa.Column("approval_bound_kind", sa.String(length=64), nullable=False),
        sa.Column("approval_bound_ref", sa.Uuid(), nullable=False),
        sa.Column("rollback_of_event_id", sa.Uuid(), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("event_id"),
        sa.ForeignKeyConstraint(
            ["rollback_of_event_id"],
            [f"{_TABLE}.event_id"],
            name="fk_predictive_reconfiguration_rollback_event",
        ),
        sa.UniqueConstraint(
            "subject_key",
            "to_version",
            name="uq_predictive_reconfiguration_subject_version",
        ),
        sa.CheckConstraint(
            "from_version >= 0 AND to_version >= 1 AND to_version = from_version + 1",
            name="ck_predictive_reconfiguration_version_step",
        ),
        sa.CheckConstraint(
            "event_kind IN ('PROMOTE','ROLLBACK')",
            name="ck_predictive_reconfiguration_event_kind",
        ),
        sa.CheckConstraint(
            "(event_kind='PROMOTE' AND rollback_of_event_id IS NULL) OR "
            "(event_kind='ROLLBACK' AND rollback_of_event_id IS NOT NULL)",
            name="ck_predictive_reconfiguration_rollback_binding",
        ),
        sa.CheckConstraint(
            "subject_key ~ '^[0-9a-f]{64}$' AND " "candidate_payload_sha256 ~ '^[0-9a-f]{64}$'",
            name="ck_predictive_reconfiguration_hashes",
        ),
        sa.CheckConstraint(
            "approval_version >= 1",
            name="ck_predictive_reconfiguration_approval_version",
        ),
        sa.CheckConstraint(
            "approval_bound_kind = 'promotion_candidate'",
            name="ck_predictive_reconfiguration_approval_bound_kind",
        ),
        sa.CheckConstraint(
            "length(btrim(model_ref)) > 0 AND length(btrim(validation_ref)) > 0 "
            "AND length(btrim(cost_ref)) > 0 AND length(btrim(responsible_ref)) > 0 "
            "AND length(btrim(rollback_plan_ref)) > 0",
            name="ck_predictive_reconfiguration_candidate_metadata",
        ),
    )
    if op.get_bind().dialect.name == "postgresql":
        op.create_check_constraint(
            "ck_predictive_reconfiguration_hypotheses_canonical",
            _TABLE,
            sa.text(f"{_FUNCTION_STRING_ARRAY}(hypothesis_refs, true)"),
        )
        op.create_check_constraint(
            "ck_predictive_reconfiguration_scope_canonical",
            _TABLE,
            sa.text(f"{_FUNCTION_STRING_ARRAY}(approval_scope, true)"),
        )
    op.create_index(
        "ix_predictive_reconfiguration_current",
        _TABLE,
        ["subject_key", "to_version"],
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            sa.text(
                f"""
                CREATE OR REPLACE FUNCTION {_FUNCTION}()
                RETURNS TRIGGER
                LANGUAGE plpgsql
                SET search_path = pg_catalog
                AS $$
                BEGIN
                    RAISE EXCEPTION
                        '{_TABLE} is append-only: % rejected', TG_OP
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
                BEFORE UPDATE OR DELETE ON {_TABLE}
                FOR EACH ROW EXECUTE FUNCTION {_FUNCTION}();
                """
            )
        )
        op.execute(
            sa.text(
                f"""
                CREATE TRIGGER {_TRUNCATE_TRIGGER}
                BEFORE TRUNCATE ON {_TABLE}
                FOR EACH STATEMENT EXECUTE FUNCTION {_FUNCTION}();
                """
            )
        )


def downgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(sa.text(f"SELECT count(*) FROM {_TABLE}")).scalar_one()
    if rows:
        raise RuntimeError(
            f"downgrade recusado: {rows} evento(s) de reconfiguração registrado(s); "
            "o histórico append-only não pode ser apagado implicitamente"
        )
    if connection.dialect.name == "postgresql":
        op.execute(sa.text(f"DROP TRIGGER IF EXISTS {_TRUNCATE_TRIGGER} ON {_TABLE}"))
        op.execute(sa.text(f"DROP TRIGGER IF EXISTS {_ROW_TRIGGER} ON {_TABLE}"))
        op.execute(sa.text(f"DROP FUNCTION IF EXISTS {_FUNCTION}()"))
    op.drop_index("ix_predictive_reconfiguration_current", table_name=_TABLE)
    op.drop_table(_TABLE)
    if connection.dialect.name == "postgresql":
        op.execute(sa.text(f"DROP FUNCTION IF EXISTS {_FUNCTION_STRING_ARRAY}(jsonb, boolean)"))
