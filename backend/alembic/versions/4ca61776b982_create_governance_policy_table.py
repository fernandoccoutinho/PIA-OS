"""create governance policy table (E4.3 — Governance Policy)

Cria `governance_policies`, a configuração de governança local e
versionada da Entrega 4.

Reversibilidade: `CONDITIONALLY_REVERSIBLE`.

- tabela vazia → downgrade seguro e permitido;
- com qualquer policy publicada → **bloqueado antes de qualquer
  alteração estrutural**.

`HISTORICAL PRESERVATION > DOWNGRADE CONVENIENCE`.

Por que uma policy merece a mesma proteção que a história causal: uma
versão publicada é o que torna decisões passadas **explicáveis**.
Apagá-la não corrompe patrimônio nenhum — e é exatamente por isso que
a perda passaria despercebida até alguém perguntar "sob qual regra
isto foi decidido?" e não haver mais resposta. Regra de governança é
decisão humana registrada, e decisões não se reconstroem sozinhas.

A guarda vive dentro deste próprio `downgrade()`, como em `E3.9` e na
migração da `E4.1` — e não numa migração-guarda posterior, que em
`E3.5.2`/`E3.6.1` só foi necessária porque a original já estava
publicada.

Nenhuma tabela da E3 é tocada. Nenhuma FK para patrimônio: a policy
referencia `domain_id` **por valor**, dentro das regras, e não por
chave estrangeira — governança não é dona de domínio, e não deve
travar a evolução dele.

Revision ID: 4ca61776b982
Revises: 3799d45ff96d
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "4ca61776b982"
down_revision: str | None = "3799d45ff96d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


class GovernancePolicyDowngradeUnsafeError(RuntimeError):
    """Downgrade recusado por preservação de governança (E4.3)."""


def upgrade() -> None:
    op.create_table(
        "governance_policies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("policy_key", sa.String(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "rules",
            sa.JSON().with_variant(postgresql.JSONB(), "postgresql"),
            nullable=False,
        ),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=True),
        sa.Column("effective_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("policy_key", "version", name="uq_governance_policies_key_version"),
        sa.CheckConstraint("version >= 1", name="ck_governance_policies_version_positive"),
        sa.CheckConstraint(
            "effective_until IS NULL OR effective_from IS NULL "
            "OR effective_until > effective_from",
            name="ck_governance_policies_effective_window",
        ),
    )
    op.create_index("ix_governance_policies_policy_key", "governance_policies", ["policy_key"])


def downgrade() -> None:
    bind = op.get_bind()

    has_rows = bind.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM governance_policies LIMIT 1)")
    ).scalar()
    if has_rows:
        raise GovernancePolicyDowngradeUnsafeError(
            "GOVERNANCE_POLICY_DOWNGRADE_SEMANTICALLY_BLOCKED: o downgrade foi "
            "recusado — há policies de governança publicadas, e o schema anterior "
            "não possui entidade capaz de representá-las. Prosseguir apagaria as "
            "versões que fundamentaram decisões já tomadas, tornando-as "
            "definitivamente inexplicáveis. Nenhum dado foi alterado, e nenhum "
            "CognitiveObject seria afetado de todo modo — o que se perderia é a "
            "regra sob a qual o patrimônio foi governado. Exporte/arquive as "
            "policies com um processo próprio e auditável antes de tentar este "
            "downgrade."
        )

    op.drop_index("ix_governance_policies_policy_key", table_name="governance_policies")
    op.drop_table("governance_policies")
