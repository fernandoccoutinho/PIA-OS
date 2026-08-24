"""enforce receipt route coherence and manual truth (E7.4-1 corrective R1)

Revision ID: c58d1e0a94f7
Revises: b47e9c05d3fa
Create Date: 2026-08-24 06:10:00.000000

Corretivo do achado C1 da auditoria independente da Chain118. Filha única
de `b47e9c05d3fa`; a migration anterior **não** é alterada
retroativamente.

## O defeito, reproduzido antes de corrigido

O vínculo bilateral do recibo provava **dono**, e não **rota**:

```text
COHERENT_OWNER != COHERENT_ROUTE
```

Por SQL bruto, um perfil `manual_handoff` aceitava um recibo declarado
`direct_provider_api`, e o inverso. Como o recibo é a única evidência da
rota realmente usada, ele podia falsificar exatamente aquilo que existe
para provar.

Segundo facet: a autoridade R3 fixa quatro valores para o repasse manual,
e o banco só impunha um deles indiretamente. Entrava um recibo
`manual_handoff` com operador, modelo solicitado, modelo observado e
atestação `attested` — atribuição inteiramente inventada, com a
bicondicional da atestação satisfeita.

## As duas correções

```text
uq_connection_profiles_id_principal_method       alvo ternário
FK (connection_id, control_principal_ref, connection_method)
   -> connection_profiles (id, control_principal_ref, method)
CHECK manual_handoff => provider/requested/observed NULL e atestação unknown
```

`RECEIPT_METHOD == PROFILE_METHOD` passa a ser garantia de schema. A
terceira coluna do alvo é redundante em cardinalidade (`id` já é a chave
primária) e obrigatória em referência — mesmo precedente de
`uq_handoff_attempts_id_step_schedule` e de
`uq_connection_profiles_id_principal`.

## Por que a FK antiga é substituída, e não somada

Duas FKs para o mesmo alvo lógico dariam duas fontes de verdade sobre a
mesma coerência, e a mais fraca continuaria passando o que a mais forte
recusa. A ternária **implica** a binária: coerência de dono é subconjunto
de coerência de rota.

## Downgrade

Recusado com linhas em `connection_execution_receipts`. Restaura a FK
binária e remove o `CHECK` e o alvo ternário — reversibilidade de schema,
nunca apagamento de história.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c58d1e0a94f7"
down_revision: str | None = "b47e9c05d3fa"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PROFILES = "connection_profiles"
_RECEIPTS = "connection_execution_receipts"

_UQ_TERNARIO = "uq_connection_profiles_id_principal_method"
_FK_ROTA = "fk_connection_execution_receipts_connection_within_principal"
_CHECK_MANUAL = "ck_connection_execution_receipts_manual_truth"

_MANUAL_TRUTH_SQL = (
    "connection_method <> 'manual_handoff' OR ("
    "access_provider IS NULL AND requested_model IS NULL "
    "AND observed_model IS NULL AND model_attestation_level = 'unknown')"
)


def upgrade() -> None:
    op.create_unique_constraint(_UQ_TERNARIO, _PROFILES, ["id", "control_principal_ref", "method"])

    # A FK binária sai e a ternária entra. Somar as duas deixaria a mais
    # fraca aceitando o que a mais forte recusa.
    op.drop_constraint(_FK_ROTA, _RECEIPTS, type_="foreignkey")
    op.create_foreign_key(
        _FK_ROTA,
        _RECEIPTS,
        _PROFILES,
        ["connection_id", "control_principal_ref", "connection_method"],
        ["id", "control_principal_ref", "method"],
    )

    op.create_check_constraint(_CHECK_MANUAL, _RECEIPTS, sa.text(_MANUAL_TRUTH_SQL))


def downgrade() -> None:
    connection = op.get_bind()
    linhas = connection.execute(sa.text(f"SELECT count(*) FROM {_RECEIPTS}")).scalar_one()
    if linhas:
        raise RuntimeError(
            f"downgrade recusado: {linhas} recibo(s) de execução em {_RECEIPTS}; "
            "atribuição operacional é história e não pode ser afrouxada por um "
            "rollback de schema com linhas presentes"
        )

    op.drop_constraint(_CHECK_MANUAL, _RECEIPTS, type_="check")
    op.drop_constraint(_FK_ROTA, _RECEIPTS, type_="foreignkey")
    op.create_foreign_key(
        _FK_ROTA,
        _RECEIPTS,
        _PROFILES,
        ["connection_id", "control_principal_ref"],
        ["id", "control_principal_ref"],
    )
    op.drop_constraint(_UQ_TERNARIO, _PROFILES, type_="unique")
