"""align erasure_records.governance_rule_id to opaque text (E4.9.9.d)

Revision ID: d5b31f7a08c4
Revises: a1f7c2d40e93
Create Date: 2026-08-19 03:10:00.000000

```text
OPAQUE_RULE_REFERENCE != UUID
FABRICATED_RULE_IDENTITY = FORBIDDEN
```

A coluna nasceu `UUID` na E4.9.5 e a fonte do valor é
`GovernanceResolution.matched_rule_id`, que é `str` desde a E4.3. O
preflight independente mediu a incompatibilidade entre contratos já
publicados; esta migration a fecha do lado do recibo, porque a E4.3 não
pode ser tocada.

## Upgrade — conversão que preserva

`USING governance_rule_id::text` grava a **representação canônica** do
UUID existente. Nenhum valor é perdido, reescrito ou renumerado: um
recibo que citava `3fa85f64-…` continua citando exatamente esse texto.

## Downgrade — recusa explícita em vez de destruição

Depois que valores textuais não-UUID entrarem (`"rule-1"` é o caso
real), a volta para `UUID` é **impossível sem destruir informação**. As
saídas erradas seriam truncar, descartar a linha ou sortear um UUID; as
três apagam ou inventam a identidade da regra que fundamentou um
apagamento.

```text
IRREVERSIBLE_BY_DATA != IRREVERSIBLE_BY_SCHEMA
DOWNGRADE_REFUSES_LOUDLY, NEVER_SILENTLY_TRUNCATES
```

O downgrade **mede** antes de agir: se toda linha for UUID-castável, ele
volta; se qualquer uma não for, ele falha com mensagem que diz quantas
linhas impedem a volta. Mesmo padrão de guarda condicional que a
E3.6.1d, a E4.9.5 e a E4.9.6 já usaram — reversibilidade
**condicional**, declarada, nunca fingida.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d5b31f7a08c4"
down_revision: str | None = "a1f7c2d40e93"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABELA = "erasure_records"
_COLUNA = "governance_rule_id"
_TAMANHO = 256
_CHECK_NAO_BRANCO = "ck_erasure_records_governance_rule_id_not_blank"

_PADRAO_UUID = r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-" r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
"""Forma canônica que o `::uuid` do PostgreSQL aceita sem ambiguidade."""


def upgrade() -> None:
    ligacao = op.get_bind()
    if ligacao.dialect.name == "postgresql":
        op.execute(
            sa.text(
                f"ALTER TABLE {_TABELA} "
                f"ALTER COLUMN {_COLUNA} TYPE VARCHAR({_TAMANHO}) "
                f"USING {_COLUNA}::text"
            )
        )
    else:  # pragma: no cover - a suíte migra contra PostgreSQL real
        op.alter_column(
            _TABELA,
            _COLUNA,
            type_=sa.String(_TAMANHO),
            existing_nullable=False,
        )

    op.create_check_constraint(
        _CHECK_NAO_BRANCO,
        _TABELA,
        f"length(btrim({_COLUNA})) > 0",
    )


def downgrade() -> None:
    ligacao = op.get_bind()
    if ligacao.dialect.name != "postgresql":  # pragma: no cover
        op.drop_constraint(_CHECK_NAO_BRANCO, _TABELA, type_="check")
        op.alter_column(_TABELA, _COLUNA, type_=sa.Uuid(), existing_nullable=False)
        return

    # A MEDIÇÃO VEM ANTES DE QUALQUER DDL, e a ordem é a garantia.
    #
    # ```text
    # REFUSE_BEFORE_ALTER, NEVER_MID_MIGRATION
    # ```
    #
    # A primeira versão desta migration derrubava o `CHECK` e só então
    # media. Um downgrade impeditivo deixaria o schema alterado e a
    # migration abortada — estado que nenhum dos dois lados descreve.
    # Recusar antes preserva schema e dados intactos.
    impedem = ligacao.execute(
        sa.text(f"SELECT count(*) FROM {_TABELA} WHERE {_COLUNA} !~ :padrao"),
        {"padrao": _PADRAO_UUID},
    ).scalar_one()
    if impedem:
        raise RuntimeError(
            f"downgrade recusado: {impedem} recibo(s) citam regra de governança "
            "cujo identificador não é UUID. Converter truncaria, e sortear "
            "fabricaria a identidade da regra que fundamentou um apagamento. "
            "IRREVERSIBLE_BY_DATA != IRREVERSIBLE_BY_SCHEMA."
        )

    op.drop_constraint(_CHECK_NAO_BRANCO, _TABELA, type_="check")
    op.execute(
        sa.text(f"ALTER TABLE {_TABELA} " f"ALTER COLUMN {_COLUNA} TYPE UUID USING {_COLUNA}::uuid")
    )
