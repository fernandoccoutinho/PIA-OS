"""create memory domain tables (E4.1 — Memory Domain Foundation)

Cria `memory_domains` e `memory_domain_memberships` — o primeiro estado
persistente da Entrega 4.

Reversibilidade: `CONDITIONALLY_REVERSIBLE`.

- tabelas vazias → o downgrade é seguro e permitido;
- com qualquer domínio ou membership registrado → o downgrade apagaria
  a organização que alguém construiu sobre o patrimônio, e nenhum
  outro lugar a preserva. Bloqueado **antes de qualquer alteração
  estrutural**.

`HISTORICAL PRESERVATION > DOWNGRADE CONVENIENCE`.

Vale notar por que a organização merece a mesma proteção que a
história causal: um domínio não é um fato sobre o mundo, é uma decisão
sobre como o patrimônio é lido. Decisões também não se reconstroem
sozinhas, e perder a classificação de milhares de COIDs é perder
trabalho humano irrecuperável — ainda que nenhum `CognitiveObject`
seja tocado.

A guarda vive dentro deste próprio `downgrade()`, como em `E3.9`, e
não numa migração-guarda posterior. Em `E3.5.2`/`E3.6.1` a migração
separada foi necessária apenas porque a original já estava publicada e
a disciplina do projeto proíbe editá-la. Aqui a migração nasce com a
guarda — a dívida não se repete.

Nenhuma FK usa `ON DELETE CASCADE`, seguindo a política de `E3.3`/
`E3.5`: `DOMAIN DELETE MUST NOT CASCADE TO COGNITIVE PATRIMONY`.

Revision ID: 3799d45ff96d
Revises: c9a3f61b74d2
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "3799d45ff96d"
down_revision: str | None = "c9a3f61b74d2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


class MemoryDomainDowngradeUnsafeError(RuntimeError):
    """Downgrade recusado por preservação da organização (E4.1)."""


def upgrade() -> None:
    op.create_table(
        "memory_domains",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "memory_domain_memberships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("domain_id", sa.Uuid(), nullable=False),
        sa.Column("coid", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["domain_id"], ["memory_domains.id"]),
        sa.ForeignKeyConstraint(["coid"], ["cognitive_objects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("domain_id", "coid", name="uq_memory_domain_memberships_domain_coid"),
    )
    op.create_index(
        "ix_memory_domain_memberships_domain_id",
        "memory_domain_memberships",
        ["domain_id"],
    )
    op.create_index(
        "ix_memory_domain_memberships_coid",
        "memory_domain_memberships",
        ["coid"],
    )


def downgrade() -> None:
    bind = op.get_bind()

    for table in ("memory_domain_memberships", "memory_domains"):
        has_rows = bind.execute(sa.text(f"SELECT EXISTS (SELECT 1 FROM {table} LIMIT 1)")).scalar()
        if has_rows:
            raise MemoryDomainDowngradeUnsafeError(
                "MEMORY_DOMAIN_DOWNGRADE_SEMANTICALLY_BLOCKED: o downgrade de "
                f"'{table}' foi recusado — há organização de memória registrada, "
                "e o schema anterior não possui entidade capaz de representá-la; "
                "prosseguir apagaria a classificação do patrimônio, que nenhum "
                "outro lugar preserva. Nenhum dado foi alterado, e nenhum "
                "CognitiveObject seria afetado de todo modo — o que se perderia "
                "é a decisão humana sobre como o patrimônio é organizado. "
                "Exporte/arquive domínios e memberships com um processo próprio "
                "e auditável antes de tentar este downgrade."
            )

    op.drop_index("ix_memory_domain_memberships_coid", table_name="memory_domain_memberships")
    op.drop_index("ix_memory_domain_memberships_domain_id", table_name="memory_domain_memberships")
    op.drop_table("memory_domain_memberships")
    op.drop_table("memory_domains")
