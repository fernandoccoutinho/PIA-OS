"""add structural indexes (E3.7 / LIB-07 Index Manager)

Cria apenas índices — nenhuma tabela, coluna, constraint, dado ou
default. Todos são estruturas **derivadas e reconstruíveis**: o
patrimônio cognitivo vive inteiramente nas tabelas já existentes, e
nenhuma linha depende destes índices para existir.

Consequência para reversibilidade (E3.7 §23/§24):

    DROPPING AN INDEX != DROPPING COGNITIVE HISTORY

Este `downgrade()` remove otimização de acesso, nunca distinção
cognitiva — por isso a migração é genuinamente `REVERSIBLE` e **não**
recebe migração-guarda, ao contrário de `f11551e97026` (Relationship,
E3.5.2) e `0460b6556563` (Provenance, E3.6.1), onde o downgrade podia
apagar fatos históricos irrecuperáveis. Guard só quando há perda
semântica possível; perda de performance não é perda cognitiva.

Revision ID: b7c41d0e92a5
Revises: 0460b6556563
"""

from collections.abc import Sequence

from alembic import op

revision: str = "b7c41d0e92a5"
down_revision: str | None = "0460b6556563"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # CLID: alta seletividade, nullable — índice parcial cobre apenas
    # objetos que já receberam continuidade. Complementa (não substitui)
    # `uq_cognitive_objects_one_current_per_clid`, que só enxerga as
    # linhas CURRENT e portanto não serve para localizar o histórico
    # completo de um CLID (E3.7 §9: SUPERSEDED continua patrimônio).
    op.create_index(
        "ix_cognitive_objects_clid",
        "cognitive_objects",
        ["clid"],
        unique=False,
        postgresql_where="clid IS NOT NULL",
    )
    # Accessibility e revision_status são de baixa cardinalidade; o
    # índice útil é o composto com a ordenação determinística já
    # canônica no projeto (`created_at ASC, id ASC`, E3.1.2), que
    # atende ORDER BY + LIMIT sem sort.
    op.create_index(
        "ix_cognitive_objects_accessibility_created_at_id",
        "cognitive_objects",
        ["accessibility", "created_at", "id"],
        unique=False,
    )
    op.create_index(
        "ix_cognitive_objects_revision_status_created_at_id",
        "cognitive_objects",
        ["revision_status", "created_at", "id"],
        unique=False,
        postgresql_where="revision_status IS NOT NULL",
    )
    # trace_id: alta seletividade, nullable, provider-neutral.
    op.create_index(
        "ix_provenance_records_trace_id",
        "provenance_records",
        ["trace_id"],
        unique=False,
        postgresql_where="trace_id IS NOT NULL",
    )


def downgrade() -> None:
    op.drop_index("ix_provenance_records_trace_id", table_name="provenance_records")
    op.drop_index(
        "ix_cognitive_objects_revision_status_created_at_id", table_name="cognitive_objects"
    )
    op.drop_index(
        "ix_cognitive_objects_accessibility_created_at_id", table_name="cognitive_objects"
    )
    op.drop_index("ix_cognitive_objects_clid", table_name="cognitive_objects")
