"""create accessibility policy table (E4.7 — Accessibility Policy)

Cria `accessibility_policies`, a configuração local e versionada de
admissibilidade e transição de `AccessibilityState`.

Reversibilidade: `CONDITIONALLY_REVERSIBLE`.

- tabela vazia → downgrade seguro e permitido;
- com qualquer policy publicada → **bloqueado antes de qualquer
  alteração estrutural**.

`HISTORICAL PRESERVATION > DOWNGRADE CONVENIENCE`.

A guarda vive dentro do próprio `downgrade()`, como em `E3.9`, `E4.1` e
`E4.3` — e não numa migração-guarda posterior, que em `E3.5.2`/`E3.6.1`
só foi necessária porque a original já estava publicada.

Uma versão publicada é o que torna decisões passadas **explicáveis**.
Apagá-la não corrompe patrimônio nenhum, e é justamente por isso que a
perda passaria despercebida até alguém perguntar "sob qual regra este
objeto foi tornado inacessível?" e não haver mais resposta.

Nenhuma tabela da E3 é tocada. Nenhuma coluna nova em `CognitiveObject`:
o estado de acessibilidade continua sendo da E3, e a E4.7 governa a
transição sem criar um segundo lugar onde o estado viva.

`governance_policy_key` é **texto, sem FK**: a autoridade é resolvida
pelo caminho canônico `GovernanceManager.resolve()`, que busca a versão
vigente. Uma FK apontaria para uma linha de versão específica e
congelaria a autoridade numa versão que pode ter sido sucedida.

Revision ID: 7b2e4c9a15df
Revises: 4ca61776b982
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "7b2e4c9a15df"
down_revision: str | None = "4ca61776b982"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


class AccessibilityPolicyDowngradeUnsafeError(RuntimeError):
    """Downgrade recusado por preservação de policy (E4.7)."""


def upgrade() -> None:
    op.create_table(
        "accessibility_policies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("policy_key", sa.String(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("governance_policy_key", sa.String(), nullable=False),
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
        sa.UniqueConstraint("policy_key", "version", name="uq_accessibility_policies_key_version"),
        sa.CheckConstraint("version >= 1", name="ck_accessibility_policies_version_positive"),
        sa.CheckConstraint(
            "effective_until IS NULL OR effective_from IS NULL "
            "OR effective_until > effective_from",
            name="ck_accessibility_policies_effective_window",
        ),
    )
    op.create_index(
        "ix_accessibility_policies_policy_key", "accessibility_policies", ["policy_key"]
    )


def downgrade() -> None:
    bind = op.get_bind()

    has_rows = bind.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM accessibility_policies LIMIT 1)")
    ).scalar()
    if has_rows:
        raise AccessibilityPolicyDowngradeUnsafeError(
            "ACCESSIBILITY_POLICY_DOWNGRADE_SEMANTICALLY_BLOCKED: o downgrade foi "
            "recusado — há policies de acessibilidade publicadas, e o schema "
            "anterior não possui entidade capaz de representá-las. Prosseguir "
            "apagaria as versões que fundamentaram transições já executadas, "
            "tornando-as definitivamente inexplicáveis. Nenhum dado foi alterado, e "
            "nenhum CognitiveObject seria afetado de todo modo — o que se perderia é "
            "a regra sob a qual a acessibilidade foi governada. Exporte/arquive as "
            "policies com um processo próprio e auditável antes de tentar este "
            "downgrade."
        )

    op.drop_index("ix_accessibility_policies_policy_key", table_name="accessibility_policies")
    op.drop_table("accessibility_policies")
