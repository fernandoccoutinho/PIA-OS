"""guard relationship downgrade safety against historical data loss (E3.5.2)

Revision ID: f11551e97026
Revises: 63d205dec996
Create Date: 2026-08-13 19:11:21.584548

Correção E3.5.2 — COUT Data Preservation Rule aplicada ao downgrade de
`relationships`.

O lifecycle de `Relationship` (E3.5) permite legitimamente múltiplas
gerações históricas da mesma tripla `(source_coid, target_coid,
relationship_type)` — uma `retired` e uma `active` (o próprio ciclo
"retirar a antiga, criar uma nova" que a correção E3.5.1 passou a
suportar). O schema anterior a `63d205dec996` exigia
`UNIQUE(source_coid, target_coid, relationship_type)` sobre **todas**
as linhas, sem exceção — se um estado com múltiplas gerações da mesma
tripla existir no banco, um downgrade convencional até esse schema
anterior não consegue recriar a constraint sem perder distinções
históricas (precisaria apagar, fundir ou escolher arbitrariamente qual
geração preservar — tudo isso proibido pela COUT Data Preservation
Rule, ver `EDR_COUT_PIA_E3.md`).

Esta migração não altera schema algum — `upgrade()` é no-op, porque o
schema já está correto desde `63d205dec996`. Seu único propósito é
**interceptar o caminho de downgrade** antes que ele alcance o
`downgrade()` de `63d205dec996` (que recria a `UniqueConstraint`
incondicional): o Alembic processa downgrades multi-passo em ordem
reversa, uma migração por vez — se `downgrade()` aqui abortar
(levantar exceção) antes de qualquer alteração estrutural, o processo
nunca chega a tocar `63d205dec996`, e a transação deste passo é
revertida integralmente (nenhum estado parcial, `alembic_version`
permanece nesta revisão).

Classificação: `MIGRATION_REVERSIBILITY = CONDITIONALLY_REVERSIBLE`.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "f11551e97026"
down_revision: str | None = "63d205dec996"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


class RelationshipDowngradeUnsafeError(Exception):
    """Levantada quando o downgrade de `relationships` até o schema
    anterior a `63d205dec996` perderia distinções históricas
    legítimas — múltiplas gerações (`retired`/`active`) da mesma
    tripla `(source_coid, target_coid, relationship_type)`, que o
    schema anterior (uma `UniqueConstraint` incondicional) não
    consegue representar sem apagar, fundir ou escolher
    arbitrariamente qual geração preservar."""


def upgrade() -> None:
    """No-op — nenhuma alteração de schema. O propósito desta
    migração é exclusivamente proteger o caminho de downgrade (ver
    docstring do módulo)."""


def downgrade() -> None:
    """Verifica, ANTES de qualquer alteração estrutural, se existe
    mais de uma linha para a mesma tripla `(source_coid, target_coid,
    relationship_type)` — o que só é representável no schema atual
    (índice único parcial `WHERE retired_at IS NULL`), não no schema
    anterior a `63d205dec996` (`UniqueConstraint` incondicional).

    Se existir: aborta explicitamente
    (`RelationshipDowngradeUnsafeError`) sem tocar o schema — o
    downgrade multi-passo do Alembic para antes de alcançar
    `63d205dec996`.

    Se não existir: no-op, e o downgrade prossegue normalmente para
    `63d205dec996` (`CASO A` — estado compatível com o schema
    anterior).
    """
    bind = op.get_bind()
    duplicates = bind.execute(
        sa.text(
            """
            SELECT source_coid, target_coid, relationship_type, COUNT(*) AS n
            FROM relationships
            GROUP BY source_coid, target_coid, relationship_type
            HAVING COUNT(*) > 1
            """
        )
    ).fetchall()

    if duplicates:
        example = duplicates[0]
        raise RelationshipDowngradeUnsafeError(
            "DOWNGRADE_SEMANTICALLY_BLOCKED: o downgrade de 'relationships' "
            "para o schema anterior a 63d205dec996 foi recusado — "
            f"{len(duplicates)} tripla(s) (source_coid, target_coid, "
            "relationship_type) possuem mais de uma geração histórica "
            f"(ex.: source_coid={example[0]}, target_coid={example[1]}, "
            f"relationship_type={example[2]}, {example[3]} linhas). "
            "O schema anterior (UNIQUE incondicional) não consegue "
            "representar isso sem apagar, fundir ou escolher "
            "arbitrariamente qual geração preservar — proibido pela "
            "COUT Data Preservation Rule. Nenhuma linha foi alterada. "
            "Resolva manualmente (ex.: exportar/retirar as gerações "
            "excedentes com uma migração de dados própria e auditável) "
            "antes de tentar este downgrade novamente."
        )
