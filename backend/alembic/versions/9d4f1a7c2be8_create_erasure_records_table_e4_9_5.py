"""create erasure_records table with append-only trigger (E4.9.5)

Revision ID: 9d4f1a7c2be8
Revises: 7b2e4c9a15df
Create Date: 2026-08-17 20:10:00.000000

Primeira migration do projeto a instalar trigger. Até aqui, a
imutabilidade de `governance_policies` e `accessibility_policies` era
garantida no ORM e no repositório, e os próprios modelos registravam
honestamente que um `UPDATE`/`DELETE` em SQL bruto continuava possível.

Para o recibo de apagamento essa honestidade não basta. O registro que
prova o que foi destruído é justamente o que alguém teria motivo para
reescrever, e a única camada que continua valendo fora do ORM é o
banco.

```text
ERASING THE RECEIPT OF AN ERASURE = MAKING DESTRUCTION UNAUDITABLE
```

A função é `pg_catalog`-safe (`search_path` fixo) e os nomes são
determinísticos, para que o downgrade remova exatamente o que criou.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9d4f1a7c2be8"
down_revision: str | None = "7b2e4c9a15df"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_FUNCTION_NAME = "reject_erasure_record_mutation"
_TRIGGER_NAME = "trg_erasure_records_append_only"


def upgrade() -> None:
    op.create_table(
        "erasure_records",
        sa.Column("subject_identifier", sa.String(length=256), nullable=False),
        sa.Column(
            "target_class",
            sa.Enum(
                "pia_managed_artifact",
                "authorized_connector_referent",
                "cognitive_metadata_record",
                "unresolved_opaque_reference",
                name="erasure_target_class",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("scope_token", sa.String(length=256), nullable=False),
        sa.Column(
            "outcome",
            sa.Enum(
                "succeeded",
                "failed",
                "partial",
                name="erasure_outcome",
                native_enum=False,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("retention_policy_id", sa.Uuid(), nullable=True),
        sa.Column("retention_policy_key", sa.String(length=256), nullable=True),
        sa.Column("retention_policy_version", sa.Integer(), nullable=True),
        sa.Column("governance_policy_id", sa.Uuid(), nullable=False),
        sa.Column("governance_policy_key", sa.String(length=256), nullable=False),
        sa.Column("governance_policy_version", sa.Integer(), nullable=False),
        sa.Column("governance_rule_id", sa.Uuid(), nullable=False),
        sa.Column("governance_resolution_ref", sa.String(length=256), nullable=False),
        sa.Column("approval_ref", sa.String(length=256), nullable=False),
        sa.Column("executor_ref", sa.String(length=256), nullable=False),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
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
        sa.CheckConstraint(
            "length(btrim(subject_identifier)) > 0",
            name="ck_erasure_records_subject_identifier_not_blank",
        ),
        sa.CheckConstraint(
            "length(btrim(scope_token)) > 0",
            name="ck_erasure_records_scope_token_not_blank",
        ),
        sa.CheckConstraint(
            "length(btrim(governance_policy_key)) > 0",
            name="ck_erasure_records_governance_policy_key_not_blank",
        ),
        sa.CheckConstraint(
            "length(btrim(governance_resolution_ref)) > 0",
            name="ck_erasure_records_governance_resolution_ref_not_blank",
        ),
        sa.CheckConstraint(
            "length(btrim(approval_ref)) > 0",
            name="ck_erasure_records_approval_ref_not_blank",
        ),
        sa.CheckConstraint(
            "length(btrim(executor_ref)) > 0",
            name="ck_erasure_records_executor_ref_not_blank",
        ),
        sa.CheckConstraint(
            "governance_policy_version >= 1",
            name="ck_erasure_records_governance_version_positive",
        ),
        sa.CheckConstraint(
            "retention_policy_version IS NULL OR retention_policy_version >= 1",
            name="ck_erasure_records_retention_version_positive",
        ),
        sa.CheckConstraint(
            "(retention_policy_id IS NULL AND retention_policy_key IS NULL "
            "AND retention_policy_version IS NULL) OR "
            "(retention_policy_id IS NOT NULL AND retention_policy_key IS NOT NULL "
            "AND length(btrim(retention_policy_key)) > 0 "
            "AND retention_policy_version IS NOT NULL)",
            name="ck_erasure_records_retention_trio_all_or_none",
        ),
        sa.CheckConstraint(
            "outcome IN ('succeeded', 'failed', 'partial')",
            name="ck_erasure_records_outcome_vocabulary",
        ),
        sa.CheckConstraint(
            "target_class IN ('pia_managed_artifact', 'authorized_connector_referent', "
            "'cognitive_metadata_record', 'unresolved_opaque_reference')",
            name="ck_erasure_records_target_class_vocabulary",
        ),
        sa.CheckConstraint(
            "completed_at >= attempted_at",
            name="ck_erasure_records_completed_after_attempted",
        ),
        sa.CheckConstraint(
            "(outcome = 'succeeded' AND failure_code IS NULL) OR "
            "(outcome IN ('failed', 'partial') AND failure_code IS NOT NULL "
            "AND length(btrim(failure_code)) > 0)",
            name="ck_erasure_records_failure_code_matches_outcome",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_erasure_records_subject_identifier",
        "erasure_records",
        ["subject_identifier"],
    )
    op.create_index("ix_erasure_records_outcome", "erasure_records", ["outcome"])
    op.create_index("ix_erasure_records_approval_ref", "erasure_records", ["approval_ref"])
    op.create_index(
        "ix_erasure_records_attempted_at_id",
        "erasure_records",
        ["attempted_at", "id"],
    )

    # Camada 3 da imutabilidade — a única que vale em SQL bruto.
    # Só no PostgreSQL: os testes RAW rodam em SQLite, onde a garantia
    # segue sendo ORM + repositório, e os testes de integração provam
    # a trigger no banco real.
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            sa.text(
                f"""
                CREATE OR REPLACE FUNCTION {_FUNCTION_NAME}()
                RETURNS TRIGGER
                LANGUAGE plpgsql
                SET search_path = pg_catalog
                AS $$
                BEGIN
                    RAISE EXCEPTION
                        'erasure_records is append-only: % rejected',
                        TG_OP
                        USING ERRCODE = 'raise_exception';
                END;
                $$;
                """
            )
        )
        op.execute(
            sa.text(
                f"""
                CREATE TRIGGER {_TRIGGER_NAME}
                BEFORE UPDATE OR DELETE ON erasure_records
                FOR EACH ROW
                EXECUTE FUNCTION {_FUNCTION_NAME}();
                """
            )
        )


def downgrade() -> None:
    # Ordem segura: trigger depende da função, função é referenciada
    # pela trigger, e a tabela é dona da trigger. Remover a tabela
    # primeiro derrubaria a trigger junto e deixaria a função órfã.
    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text(f"DROP TRIGGER IF EXISTS {_TRIGGER_NAME} ON erasure_records"))
        op.execute(sa.text(f"DROP FUNCTION IF EXISTS {_FUNCTION_NAME}()"))

    op.drop_index("ix_erasure_records_attempted_at_id", table_name="erasure_records")
    op.drop_index("ix_erasure_records_approval_ref", table_name="erasure_records")
    op.drop_index("ix_erasure_records_outcome", table_name="erasure_records")
    op.drop_index("ix_erasure_records_subject_identifier", table_name="erasure_records")
    op.drop_table("erasure_records")
    # Os enums são `native_enum=False` (VARCHAR + CHECK), como em todo
    # o projeto: não há tipo PostgreSQL a remover.
