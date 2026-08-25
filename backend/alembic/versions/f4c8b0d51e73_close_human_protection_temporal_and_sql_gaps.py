"""close human-protection temporal and SQL gaps (E7.4-1 Chain124)

Revision ID: f4c8b0d51e73
Revises: d7a4c1e93b28
Create Date: 2026-08-25 10:30:00.000000

Filha única da Chain123. Endurece a coerência de engajamento sem reescrever a
migration histórica: bloqueio exige engajamento material e permissão não pode
carregar engajamento.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "f4c8b0d51e73"
down_revision: str | None = "d7a4c1e93b28"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_EVENTOS = "human_protection_events"
_ENGAGEMENTS_QUE_BLOQUEIAM_SQL = "('operational_enablement','unspecified')"

CHECKS_CORRETIVOS: tuple[tuple[str, str], ...] = (
    (
        "ck_hpe_blocked_engagement",
        "outcome <> 'blocked' OR (capability_engagement IS NOT NULL AND "
        f"capability_engagement IN {_ENGAGEMENTS_QUE_BLOQUEIAM_SQL})",
    ),
    (
        "ck_hpe_allowed_no_engagement",
        "outcome <> 'allowed' OR capability_engagement IS NULL",
    ),
)

_PREDICADO_CHAIN123 = (
    "outcome <> 'blocked' OR capability_engagement IN " f"{_ENGAGEMENTS_QUE_BLOQUEIAM_SQL}"
)


def upgrade() -> None:
    op.drop_constraint("ck_hpe_blocked_engagement", _EVENTOS, type_="check")
    for nome, predicado in CHECKS_CORRETIVOS:
        op.create_check_constraint(nome, _EVENTOS, predicado)


def downgrade() -> None:
    op.drop_constraint("ck_hpe_allowed_no_engagement", _EVENTOS, type_="check")
    op.drop_constraint("ck_hpe_blocked_engagement", _EVENTOS, type_="check")
    op.create_check_constraint("ck_hpe_blocked_engagement", _EVENTOS, _PREDICADO_CHAIN123)
