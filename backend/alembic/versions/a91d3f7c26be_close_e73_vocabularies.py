"""close E7.3 vocabularies at the database level (corrective R1)

Revision ID: a91d3f7c26be
Revises: f2c60d8a41b9
Create Date: 2026-08-23 21:30:00.000000

Corretivo da Chain116. Filha única de `f2c60d8a41b9`; a migration
anterior **não** é alterada retroativamente.

## Achado C3 — os vocabulários não estavam fechados no banco

`SAEnum(..., native_enum=False)` do SQLAlchemy 2.x **não** cria `CHECK`
por padrão: a coluna vira `VARCHAR(n)` e aceita qualquer texto que caiba.

```text
TYPED_IN_PYTHON != CONSTRAINED_IN_POSTGRES
APP_TYPED_BOUNDARY != DATABASE_INTEGRITY
```

Por SQL bruto era possível inserir estado de delegação, tipo de evento,
motivo, categoria de Stop Condition, escopo e tipo de observação
inválidos — e, pior, as linhas resultantes ficavam **protegidas pelos
triggers append-only**, isto é, indeléveis. Um vocabulário que só existe
em Python é convenção, não fechamento.

Os `CHECK` abaixo são o fechamento de fato. Cada um lista o vocabulário
literal: ampliar um enum passa a exigir migration, que é exatamente o
ponto — "adicionar um valor" deve ser um ato visível, não um efeito
colateral de edição de código.

Nada é convertido para `ENUM` nativo do PostgreSQL: tipo nativo torna a
remoção de um valor uma operação de schema pesada, e o programa já paga
pedágio de folha suficiente.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a91d3f7c26be"
down_revision: str | None = "f2c60d8a41b9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_VOCABULARIOS: tuple[tuple[str, str, str, tuple[str, ...], bool], ...] = (
    (
        "service_delegations",
        "ck_service_delegations_state_vocabulary",
        "state",
        ("active", "consumed", "revoked", "expired"),
        False,
    ),
    (
        "service_delegations",
        "ck_service_delegations_scope_vocabulary",
        "scope",
        ("dispatch",),
        False,
    ),
    (
        "orchestration_control_events",
        "ck_control_events_kind_vocabulary",
        "event_kind",
        ("paused", "resumed", "stopped", "cancelled", "completed"),
        False,
    ),
    (
        "orchestration_control_events",
        "ck_control_events_reason_vocabulary",
        "reason_code",
        (
            "operator_requested",
            "delegation_missing",
            "delegation_expired",
            "delegation_content_changed",
            "human_gate_unavailable",
            "stop_condition_declared",
            "all_steps_returned",
        ),
        False,
    ),
    (
        "orchestration_control_events",
        "ck_control_events_stop_category_vocabulary",
        "stop_condition_category",
        (
            "missing_authority",
            "scope_or_impact_change",
            "provider_or_tool_switch",
            "cost_quota_or_duration_limit",
            "secret_or_privacy_risk",
            "artifact_identity_mismatch",
            "mandatory_gate_failed",
            "material_audit_finding",
            "external_effect_requested",
            "provenance_or_isolation_failure",
        ),
        True,
    ),
    (
        "execution_observations",
        "ck_execution_observations_kind_vocabulary",
        "observation_kind",
        ("declared_provider_switch",),
        False,
    ),
    (
        "audit_opinions",
        "ck_audit_opinions_opinion_vocabulary",
        "opinion",
        ("concur", "dissent", "insufficient_evidence", "out_of_scope"),
        False,
    ),
)


def _expressao(coluna: str, valores: tuple[str, ...], anulavel: bool) -> str:
    lista = ", ".join(f"'{valor}'" for valor in valores)
    predicado = f"{coluna} IN ({lista})"
    return f"{coluna} IS NULL OR {predicado}" if anulavel else predicado


def upgrade() -> None:
    for tabela, nome, coluna, valores, anulavel in _VOCABULARIOS:
        regra = _expressao(coluna, valores, anulavel)
        op.create_check_constraint(nome, tabela, sa.text(regra))


def downgrade() -> None:
    for tabela, nome, _coluna, _valores, _anulavel in reversed(_VOCABULARIOS):
        op.drop_constraint(nome, tabela, type_="check")
