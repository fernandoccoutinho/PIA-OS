"""create transformation_records table (E3.4 / LIB-04)

Revision ID: 2832894b5cb2
Revises: f3e7e2b98ce3
Create Date: 2026-08-13 12:56:24.879534

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2832894b5cb2"
down_revision: str | None = "f3e7e2b98ce3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "transformation_records",
        sa.Column("operation_type", sa.String(length=64), nullable=False),
        sa.Column(
            "transformation_kind",
            sa.Enum(
                "revision",
                "derivation",
                name="transformation_kind",
                native_enum=False,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("input_refs", sa.JSON(), nullable=False),
        sa.Column("output_refs", sa.JSON(), nullable=False),
        sa.Column("actor_ref", sa.Uuid(), nullable=True),
        sa.Column("policy_ref", sa.String(length=255), nullable=True),
        sa.Column("declared_preservations", sa.JSON(), nullable=False),
        sa.Column("declared_losses", sa.JSON(), nullable=False),
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
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("transformation_records")
