"""create retention_policies table with append-only trigger (E4.9.6)

Revision ID: c8a3f5017e94
Revises: 9d4f1a7c2be8
Create Date: 2026-08-17 21:05:00.000000

Segunda migration do projeto a instalar trigger, seguindo o padrão que
a E4.9.5 estabeleceu — com função e trigger de **nomes próprios**, não
compartilhados com `erasure_records`.

Nomes próprios importam: uma função compartilhada faria o downgrade de
uma tabela derrubar a proteção da outra, e a mensagem de erro citaria
a tabela errada.

As triggers das policies antigas (`governance_policies`,
`accessibility_policies`) **não** são alteradas por esta migration —
elas não têm trigger, e retroagir nelas seria escopo de outra fatia.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c8a3f5017e94"
down_revision: str | None = "9d4f1a7c2be8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_FUNCTION_NAME = "reject_retention_policy_mutation"
_TRIGGER_NAME = "trg_retention_policies_append_only"


def upgrade() -> None:
    op.create_table(
        "retention_policies",
        sa.Column("policy_key", sa.String(length=256), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("governance_policy_key", sa.String(length=256), nullable=False),
        sa.Column(
            "rules",
            sa.JSON().with_variant(sa.dialects.postgresql.JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_until", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint("version >= 1", name="ck_retention_policies_version_positive"),
        sa.CheckConstraint(
            "length(btrim(policy_key)) > 0",
            name="ck_retention_policies_policy_key_not_blank",
        ),
        sa.CheckConstraint(
            "length(btrim(governance_policy_key)) > 0",
            name="ck_retention_policies_governance_key_not_blank",
        ),
        sa.CheckConstraint(
            "effective_until IS NULL OR effective_from IS NULL "
            "OR effective_until > effective_from",
            name="ck_retention_policies_effective_window",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("policy_key", "version", name="uq_retention_policies_key_version"),
    )
    op.create_index("ix_retention_policies_policy_key", "retention_policies", ["policy_key"])

    # Camada 3 da imutabilidade — a única que vale em SQL bruto.
    # Só no PostgreSQL: os testes RAW rodam em SQLite, onde a garantia
    # segue sendo ORM + repositório.
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
                        'retention_policies is append-only: % rejected',
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
                BEFORE UPDATE OR DELETE ON retention_policies
                FOR EACH ROW
                EXECUTE FUNCTION {_FUNCTION_NAME}();
                """
            )
        )


def downgrade() -> None:
    # Ordem segura: trigger, função, índice, tabela. Remover a tabela
    # primeiro derrubaria a trigger junto e deixaria a função órfã.
    # `erasure_records` e sua função não são tocadas.
    if op.get_bind().dialect.name == "postgresql":
        op.execute(sa.text(f"DROP TRIGGER IF EXISTS {_TRIGGER_NAME} ON retention_policies"))
        op.execute(sa.text(f"DROP FUNCTION IF EXISTS {_FUNCTION_NAME}()"))

    op.drop_index("ix_retention_policies_policy_key", table_name="retention_policies")
    op.drop_table("retention_policies")
