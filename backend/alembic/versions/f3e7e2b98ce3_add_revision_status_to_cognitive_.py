"""add revision_status to cognitive_objects (E3.4.0)

Revision ID: f3e7e2b98ce3
Revises: 4f56e1a4936c
Create Date: 2026-08-13 16:04:39.362832

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f3e7e2b98ce3"
down_revision: str | None = "4f56e1a4936c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "cognitive_objects",
        sa.Column(
            "revision_status",
            sa.Enum(
                "current",
                "superseded",
                name="revision_status",
                native_enum=False,
                length=16,
            ),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("cognitive_objects", "revision_status")
