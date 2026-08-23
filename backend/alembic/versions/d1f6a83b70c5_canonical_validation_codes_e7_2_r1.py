"""enforce canonical validation_codes and bind command to request (E7.2 R1)

Revision ID: d1f6a83b70c5
Revises: c3a75e01d248
Create Date: 2026-08-23 06:20:00.000000

Corretivo da Chain113. Filha única de `c3a75e01d248`; a migration
anterior **não** é alterada retroativamente.

## Achado C3 — `validation_codes` não era canônico no banco

O `CHECK` original verificava apenas que a coluna era um array e que a
quantidade concordava com o status. SQL bruto ainda aceitava código fora
do vocabulário, elemento não textual, duplicata e ordem arbitrária.

```text
APP_TYPED_BOUNDARY != DATABASE_INTEGRITY
COUNT_CHECK != VOCABULARY_CHECK
```

O `TypeDecorator` canonicaliza no caminho da aplicação, e isso não é
integridade: o que não passa pelo ORM não passa pelo decorador. Duas
rejeições pelos mesmos motivos precisam ter a **mesma** forma persistida,
ou comparar veredito passa a depender da ordem em que o validador
acumulou os códigos.

A função `orchestration_validation_codes_are_canonical()` verifica, em
uma passagem: array, todo elemento string, todo código dentro dos cinco
permitidos, sem duplicata e em ordem crescente.

## Achado C1 — vínculo entre comando e requisição

`request_sha256` em `command_receipts`, `nullable` por causa das linhas
históricas — preenchê-las exigiria inventar a requisição que as
originou. Obrigatória para todo comando público novo, o que é imposto no
serviço, e não aqui: uma coluna `NOT NULL` quebraria as linhas anteriores
e apagaria a distinção entre "não havia vínculo" e "o vínculo é este".

```text
SAME_COMMAND_KEY + DIFFERENT_REQUEST = CONFLICT
```

Guarda hash, nunca corpo — `RAW_OUTPUT_IN_DATABASE = FORBIDDEN`.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d1f6a83b70c5"
down_revision: str | None = "c3a75e01d248"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RESULTS = "handoff_results"
_COMMANDS = "command_receipts"
_FUNCTION_CODES = "orchestration_validation_codes_are_canonical"
_CHECK_CODES = "ck_handoff_results_validation_codes_canonical"
_CHECK_SHA = "ck_command_receipts_request_sha256_length"

_CODIGOS = (
    "expected_json_object",
    "expected_non_empty_text",
    "media_type_mismatch",
    "non_canonical_json_number",
    "unsupported_output_contract",
)


def upgrade() -> None:
    e_postgres = op.get_bind().dialect.name == "postgresql"

    op.add_column(_COMMANDS, sa.Column("request_sha256", sa.String(length=64), nullable=True))
    op.create_check_constraint(
        _CHECK_SHA,
        _COMMANDS,
        sa.text("request_sha256 IS NULL OR length(request_sha256) = 64"),
    )

    if not e_postgres:
        return

    vocabulario = ", ".join(f"'{codigo}'" for codigo in _CODIGOS)
    op.execute(
        sa.text(
            f"""
            CREATE OR REPLACE FUNCTION {_FUNCTION_CODES}(value jsonb)
            RETURNS boolean
            LANGUAGE plpgsql
            IMMUTABLE
            SET search_path = pg_catalog
            AS $$
            DECLARE
                item jsonb;
                atual text;
                anterior text := NULL;
            BEGIN
                IF value IS NULL OR jsonb_typeof(value) <> 'array' THEN
                    RETURN false;
                END IF;
                FOR item IN SELECT * FROM jsonb_array_elements(value) LOOP
                    IF jsonb_typeof(item) <> 'string' THEN
                        RETURN false;
                    END IF;
                    atual := item #>> '{{}}';
                    IF atual NOT IN ({vocabulario}) THEN
                        RETURN false;
                    END IF;
                    -- Estritamente crescente: recusa duplicata e ordem
                    -- arbitrária na mesma comparação.
                    IF anterior IS NOT NULL AND atual <= anterior THEN
                        RETURN false;
                    END IF;
                    anterior := atual;
                END LOOP;
                RETURN true;
            END;
            $$;
            """
        )
    )
    op.create_check_constraint(
        _CHECK_CODES,
        _RESULTS,
        sa.text(f"{_FUNCTION_CODES}(validation_codes)"),
    )


def downgrade() -> None:
    connection = op.get_bind()
    e_postgres = connection.dialect.name == "postgresql"
    if e_postgres:
        vinculados = connection.execute(
            sa.text(f"SELECT count(*) FROM {_COMMANDS} WHERE request_sha256 IS NOT NULL")
        ).scalar_one()
        if vinculados:
            raise RuntimeError(
                f"downgrade recusado: {vinculados} recibo(s) de comando com vínculo de "
                "requisição; removê-los apagaria a única prova de qual pedido originou "
                "cada efeito"
            )
        op.drop_constraint(_CHECK_CODES, _RESULTS, type_="check")
        op.execute(sa.text(f"DROP FUNCTION IF EXISTS {_FUNCTION_CODES}(jsonb)"))
    op.drop_constraint(_CHECK_SHA, _COMMANDS, type_="check")
    op.drop_column(_COMMANDS, "request_sha256")
