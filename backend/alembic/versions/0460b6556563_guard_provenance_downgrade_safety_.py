"""guard provenance downgrade safety against historical data loss (E3.6.1)

Revision ID: 0460b6556563
Revises: 6bf0c0eb0c2e
Create Date: 2026-08-13 20:04:12.000000

Correção E3.6.1 — COUT Data Preservation Rule aplicada ao downgrade de
`provenance_records` (mesmo princípio já aplicado a `relationships`
em E3.5.2/`f11551e97026`).

O schema anterior a `e2c89ee3aa59` não tinha a tabela
`provenance_records` — depois que qualquer fato de proveniência for
registrado, um downgrade convencional até esse schema anterior
(`DROP TABLE provenance_records`) apagaria distinções históricas
legitimamente preservadas.

Esta migração não altera schema algum — `upgrade()` é no-op. Seu
único propósito é **interceptar o caminho de downgrade** antes que
ele alcance o `downgrade()` de `6bf0c0eb0c2e` (que remove a coluna
`trace_id` — perderia dados se populada) e, mais adiante, de
`e2c89ee3aa59` (que remove a tabela inteira). Como esta migração está
posicionada **depois** de ambas na cadeia, um `alembic downgrade` a
partir da head atual executa primeiro o `downgrade()` daqui — se
`provenance_records` tiver qualquer linha, a execução é abortada antes
de qualquer alteração estrutural, e o downgrade nunca prossegue até as
migrações destrutivas anteriores.

Checagem mínima e determinística (`EXISTS`, não `COUNT`) — não precisa
contar todas as linhas, só confirmar se existe pelo menos uma.

Classificação: `MIGRATION_REVERSIBILITY = CONDITIONALLY_REVERSIBLE`
(revisão da classificação `REVERSIBLE` simples original de E3.6 —
essa classificação estava correta apenas para o caso vazio; a
auditoria de E3.6.1 identificou corretamente que ela não podia ser
declarada incondicionalmente segura assim que dados existissem).
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0460b6556563"
down_revision: str | None = "6bf0c0eb0c2e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


class ProvenanceDowngradeUnsafeError(Exception):
    """Levantada quando o downgrade de `provenance_records` (ou da
    coluna `trace_id` que a antecede na cadeia) perderia distinções
    históricas legítimas — pelo menos uma linha já existe, e o schema
    anterior não tem entidade capaz de representá-la."""


def upgrade() -> None:
    """No-op — nenhuma alteração de schema. O propósito desta
    migração é exclusivamente proteger o caminho de downgrade (ver
    docstring do módulo)."""


def downgrade() -> None:
    """Verifica, ANTES de qualquer alteração estrutural, se existe
    pelo menos uma linha em `provenance_records`.

    Se existir: aborta explicitamente
    (`ProvenanceDowngradeUnsafeError`) sem tocar o schema — o
    downgrade multi-passo do Alembic para antes de alcançar
    `6bf0c0eb0c2e`/`e2c89ee3aa59`.

    Se não existir (`CASO A` — tabela vazia): no-op, e o downgrade
    prossegue normalmente.
    """
    bind = op.get_bind()
    has_any_row = bind.execute(
        sa.text("SELECT EXISTS (SELECT 1 FROM provenance_records LIMIT 1)")
    ).scalar()

    if has_any_row:
        raise ProvenanceDowngradeUnsafeError(
            "PROVENANCE_DOWNGRADE_SEMANTICALLY_BLOCKED: o downgrade de "
            "'provenance_records' foi recusado — há fatos históricos de "
            "Provenance registrados; o schema anterior não possui "
            "entidade capaz de representá-los; prosseguir apagaria "
            "distinções históricas legítimas. Nenhum dado foi alterado. "
            "Resolva manualmente (ex.: exportar/arquivar os registros "
            "existentes com um processo próprio e auditável) antes de "
            "tentar este downgrade novamente."
        )
