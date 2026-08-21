"""create causal history tables (E3.9 / LIB-09)

Cria `causal_histories` e `causal_history_events`. Ambas guardam
**fatos históricos**, não estrutura derivada — diferente dos índices de
`E3.7`, que podiam ser recriados sem perda.

Reversibilidade (`E3.9` §43): `CONDITIONALLY_REVERSIBLE`.

- tabelas vazias → o downgrade é seguro e permitido;
- com qualquer evento ou história registrada → o downgrade apagaria
  fatos que nenhum outro lugar preserva, e é **bloqueado antes de
  qualquer alteração estrutural**.

`HISTORICAL PRESERVATION > DOWNGRADE CONVENIENCE`.

A guarda vive dentro deste próprio `downgrade()`, e não numa migração
posterior separada como em `E3.5.2`/`E3.6.1`. A diferença é
deliberada: naqueles casos a migração original **já estava publicada**
e a disciplina do projeto proíbe editá-la, o que obrigava a uma
migração-guarda nova. Aqui a migração nasce com a guarda — criar uma
segunda migração no-op só para replicar o formato seria ruído.

Revision ID: c9a3f61b74d2
Revises: b7c41d0e92a5
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c9a3f61b74d2"
down_revision: str | None = "b7c41d0e92a5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


class CausalHistoryDowngradeUnsafeError(RuntimeError):
    """Downgrade recusado por preservação histórica (E3.9)."""


def upgrade() -> None:
    op.create_table(
        "causal_histories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("subject_coid", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["subject_coid"], ["cognitive_objects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    # `unique=True` + `index=True` no modelo rendem um único índice
    # único — não uma UniqueConstraint separada; manter idêntico ao
    # que `Base.metadata` descreve.
    op.create_index(
        "ix_causal_histories_subject_coid", "causal_histories", ["subject_coid"], unique=True
    )

    op.create_table(
        "causal_history_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("history_id", sa.Uuid(), nullable=False),
        sa.Column("event_type", sa.String(length=32), nullable=False),
        sa.Column("actor_ref", sa.Uuid(), nullable=True),
        sa.Column("payload_ref", sa.String(length=512), nullable=True),
        sa.Column("predecessor_event_id", sa.Uuid(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "predecessor_event_id IS NULL OR predecessor_event_id != id",
            name="ck_causal_history_events_no_self_predecessor",
        ),
        sa.ForeignKeyConstraint(["history_id"], ["causal_histories.id"]),
        sa.ForeignKeyConstraint(["actor_ref"], ["provenance_records.id"]),
        sa.ForeignKeyConstraint(["predecessor_event_id"], ["causal_history_events.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_causal_history_events_history_id", "causal_history_events", ["history_id"])
    op.create_index(
        "ix_causal_history_events_predecessor_event_id",
        "causal_history_events",
        ["predecessor_event_id"],
    )


def downgrade() -> None:
    bind = op.get_bind()

    for table in ("causal_history_events", "causal_histories"):
        has_rows = bind.execute(sa.text(f"SELECT EXISTS (SELECT 1 FROM {table} LIMIT 1)")).scalar()
        if has_rows:
            raise CausalHistoryDowngradeUnsafeError(
                "CAUSAL_HISTORY_DOWNGRADE_SEMANTICALLY_BLOCKED: o downgrade de "
                f"'{table}' foi recusado — há história causal registrada, e o "
                "schema anterior não possui entidade capaz de representá-la; "
                "prosseguir apagaria fatos históricos que nenhum outro lugar "
                "preserva. Nenhum dado foi alterado. O registro histórico é ele "
                "próprio um rastro preservado: exporte/arquive os eventos com um "
                "processo próprio e auditável antes de tentar este downgrade."
            )

    op.drop_index(
        "ix_causal_history_events_predecessor_event_id", table_name="causal_history_events"
    )
    op.drop_index("ix_causal_history_events_history_id", table_name="causal_history_events")
    op.drop_table("causal_history_events")
    op.drop_index("ix_causal_histories_subject_coid", table_name="causal_histories")
    op.drop_table("causal_histories")
