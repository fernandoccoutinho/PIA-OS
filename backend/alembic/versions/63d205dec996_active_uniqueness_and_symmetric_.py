"""active uniqueness and symmetric guarantee for relationships (E3.5.1)

Revision ID: 63d205dec996
Revises: 2826ce7fa4dc
Create Date: 2026-08-13 18:52:37.284332

"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "63d205dec996"
down_revision: str | None = "2826ce7fa4dc"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint("uq_relationships_source_target_type", "relationships", type_="unique")
    op.create_index(
        "uq_relationships_active_source_target_type",
        "relationships",
        ["source_coid", "target_coid", "relationship_type"],
        unique=True,
        postgresql_where=sa.text("retired_at IS NULL"),
        sqlite_where=sa.text("retired_at IS NULL"),
    )
    # CHECK constraint não detectado pelo autogenerate do Alembic
    # (limitação conhecida) — adicionado manualmente. Fecha o débito
    # C2 (correção E3.5.1): garante estruturalmente que uma linha
    # `RELATED_TO` só existe na forma canônica (`source_coid <
    # target_coid`), independentemente do caminho de escrita.
    op.create_check_constraint(
        "ck_relationships_symmetric_canonical_order",
        "relationships",
        "relationship_type != 'related_to' OR source_coid < target_coid",
    )


def downgrade() -> None:
    op.drop_constraint("ck_relationships_symmetric_canonical_order", "relationships", type_="check")
    op.drop_index(
        "uq_relationships_active_source_target_type",
        table_name="relationships",
        postgresql_where=sa.text("retired_at IS NULL"),
        sqlite_where=sa.text("retired_at IS NULL"),
    )
    op.create_unique_constraint(
        "uq_relationships_source_target_type",
        "relationships",
        ["source_coid", "target_coid", "relationship_type"],
    )
