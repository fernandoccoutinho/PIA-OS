"""enforce lowercase hexadecimal request_sha256 (E7.2 R2)

Revision ID: e5b21c9704af
Revises: d1f6a83b70c5
Create Date: 2026-08-23 08:05:00.000000

Corretivo da Chain114. Filha única de `d1f6a83b70c5`; as migrations
anteriores não são alteradas.

## O que faltava

`ck_command_receipts_request_sha256_length` verificava apenas o
comprimento. Por SQL bruto, sessenta e quatro caracteres quaisquer
passavam — inclusive maiúsculas e texto não hexadecimal.

```text
LENGTH_CHECK != FORMAT_CHECK
UPPERCASE_DIGEST != CANONICAL_DIGEST
```

Comprimento não é formato. E maiúsculas importam mais do que parecem: a
comparação de replay é textual, então `ABC…` e `abc…` seriam **duas
impressões digitais diferentes para a mesma requisição**, e o mesmo
pedido repetido receberia 409 em vez de replay. Normalizar na leitura
esconderia o problema; recusar na escrita o elimina.

## O que continua permitido

`NULL`, para os recibos históricos criados antes de a coluna existir.
Exigir valor neles obrigaria a inventar a requisição que os originou.

```text
HISTORICAL_NULL = PRESERVED
NEW_PUBLIC_COMMAND_REQUIRES_FINGERPRINT = ENFORCED_IN_SERVICE
```

A obrigatoriedade para comandos novos vive no serviço, não aqui: uma
coluna `NOT NULL` quebraria as linhas anteriores e apagaria a distinção
entre "não havia vínculo" e "o vínculo é este".
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e5b21c9704af"
down_revision: str | None = "d1f6a83b70c5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_COMMANDS = "command_receipts"
_CHECK_HEX = "ck_command_receipts_request_sha256_hex"


def upgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    invalidos = (
        op.get_bind()
        .execute(
            sa.text(
                f"SELECT count(*) FROM {_COMMANDS} "
                "WHERE request_sha256 IS NOT NULL "
                "AND request_sha256 !~ '^[0-9a-f]{64}$'"
            )
        )
        .scalar_one()
    )
    if invalidos:
        raise RuntimeError(
            f"upgrade recusado: {invalidos} recibo(s) com request_sha256 fora da forma "
            "canônica; a incoerência precisa ser examinada, não normalizada em silêncio "
            "por uma migration"
        )
    op.create_check_constraint(
        _CHECK_HEX,
        _COMMANDS,
        sa.text("request_sha256 IS NULL OR request_sha256 ~ '^[0-9a-f]{64}$'"),
    )


def downgrade() -> None:
    if op.get_bind().dialect.name != "postgresql":
        return
    op.drop_constraint(_CHECK_HEX, _COMMANDS, type_="check")
