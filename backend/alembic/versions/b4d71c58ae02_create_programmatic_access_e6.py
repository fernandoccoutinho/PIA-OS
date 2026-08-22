"""create programmatic access tables (E6.2)

Revision ID: b4d71c58ae02
Revises: f8a91c2d4e60
Create Date: 2026-08-22 05:40:00.000000

Duas tabelas, um head. `programmatic_service_principals` guarda digest —
nunca segredo — e `programmatic_quota_buckets` guarda contagem por janela.

A unicidade `(principal_id, operation, window_start)` não é conveniência
de consulta: é o que torna o `INSERT ... ON CONFLICT ... DO UPDATE ...
WHERE used < limit` atômico. Sem ela o upsert não teria alvo de conflito e
duas réplicas criariam dois buckets para a mesma janela — o teto seria
dobrado silenciosamente.

O downgrade é seguro: as duas tabelas são estado operacional de acesso,
não história causal append-only. Nenhum recibo, apagamento ou evento
científico depende delas.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "b4d71c58ae02"
down_revision: str | None = "f8a91c2d4e60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PRINCIPALS = "programmatic_service_principals"
_BUCKETS = "programmatic_quota_buckets"


def upgrade() -> None:
    e_postgres = op.get_bind().dialect.name == "postgresql"
    tipo_json = postgresql.JSONB() if e_postgres else sa.JSON()

    op.create_table(
        _PRINCIPALS,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("key_id", sa.String(length=64), nullable=False),
        sa.Column("secret_digest", sa.String(length=64), nullable=False),
        sa.Column("scopes", tipo_json, nullable=False),
        sa.Column("quota_limit", sa.Integer(), nullable=False),
        sa.Column("quota_window_seconds", sa.Integer(), nullable=False),
        sa.Column("description", sa.String(length=200), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("key_id", name="uq_programmatic_service_principals_key_id"),
        sa.CheckConstraint(
            "quota_limit > 0", name="ck_programmatic_principal_quota_limit_positive"
        ),
        sa.CheckConstraint(
            "quota_window_seconds > 0", name="ck_programmatic_principal_quota_window_positive"
        ),
        sa.CheckConstraint(
            "char_length(secret_digest) = 64", name="ck_programmatic_principal_digest_length"
        ),
        sa.CheckConstraint(
            "char_length(key_id) >= 8", name="ck_programmatic_principal_key_id_length"
        ),
    )
    op.create_index(
        "ix_programmatic_service_principals_key_id", _PRINCIPALS, ["key_id"], unique=True
    )

    op.create_table(
        _BUCKETS,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("principal_id", sa.Uuid(), nullable=False),
        sa.Column("operation", sa.String(length=64), nullable=False),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["principal_id"],
            [f"{_PRINCIPALS}.id"],
            name="fk_programmatic_quota_bucket_principal",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "principal_id",
            "operation",
            "window_start",
            name="uq_programmatic_quota_bucket_window",
        ),
        sa.CheckConstraint("used >= 0", name="ck_programmatic_quota_bucket_used_non_negative"),
    )


def downgrade() -> None:
    op.drop_table(_BUCKETS)
    op.drop_index("ix_programmatic_service_principals_key_id", table_name=_PRINCIPALS)
    op.drop_table(_PRINCIPALS)
