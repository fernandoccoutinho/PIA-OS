"""enforce schedule-step composite integrity on handoff_attempts (E7.1 R1)

Revision ID: b8c04e2fd137
Revises: a7f31c05be24
Create Date: 2026-08-23 00:30:00.000000

Corretivo da Chain110. Nenhuma tabela nova, nenhuma coluna nova.

O defeito: `handoff_attempts` guardava `schedule_id` e `step_id` com uma
chave estrangeira **independente** para cada um. As duas eram válidas
isoladamente e nada exigia que a etapa pertencesse àquele Schedule.

```text
TWO_VALID_REFERENCES != ONE_COHERENT_REFERENCE
SCHEDULE_A + STEP_B = ACEITO PELO BANCO (antes deste corretivo)
```

Uma tentativa assim é registro de repasse de uma etapa de outro trabalho,
e sobreviveria a qualquer correção feita só na aplicação — que é
exatamente o motivo de a integridade descer para o schema.

Mecanismo: chave estrangeira **composta** `(step_id, schedule_id)` de
`handoff_attempts` para `schedule_steps (id, schedule_id)`. O alvo exige
um `UNIQUE (id, schedule_id)` em `schedule_steps` — redundante do ponto
de vista de cardinalidade, já que `id` é a chave primária, e obrigatório
do ponto de vista de referência: o PostgreSQL só aceita FK contra um
conjunto de colunas com unicidade declarada.

A FK simples de `step_id` é **preservada**. Removê-la não acrescentaria
garantia e apagaria uma restrição que a Chain110 publicou.

`redundância declarada != redundância acidental`: a coluna `schedule_id`
de `handoff_attempts` continua existindo porque toda consulta é escopada
por Schedule (MAI §17) e depender do join para aplicar escopo deixaria a
garantia à mercê da próxima query escrita. O que faltava não era a
coluna — era a coerência entre ela e a etapa.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b8c04e2fd137"
down_revision: str | None = "a7f31c05be24"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STEPS = "schedule_steps"
_ATTEMPTS = "handoff_attempts"
_UNIQUE_ALVO = "uq_schedule_steps_id_schedule"
_FK_COMPOSTA = "fk_handoff_attempts_step_within_schedule"


def upgrade() -> None:
    incoerentes = (
        op.get_bind()
        .execute(
            sa.text(
                f"""
                SELECT count(*)
                FROM {_ATTEMPTS} a
                JOIN {_STEPS} s ON s.id = a.step_id
                WHERE s.schedule_id <> a.schedule_id
                """
            )
        )
        .scalar_one()
    )
    if incoerentes:
        raise RuntimeError(
            f"upgrade recusado: {incoerentes} tentativa(s) referenciam etapa de outro "
            "Schedule; a incoerência precisa ser examinada, não corrigida em silêncio "
            "por uma migration"
        )

    op.create_unique_constraint(_UNIQUE_ALVO, _STEPS, ["id", "schedule_id"])
    op.create_foreign_key(
        _FK_COMPOSTA,
        _ATTEMPTS,
        _STEPS,
        ["step_id", "schedule_id"],
        ["id", "schedule_id"],
    )


def downgrade() -> None:
    op.drop_constraint(_FK_COMPOSTA, _ATTEMPTS, type_="foreignkey")
    op.drop_constraint(_UNIQUE_ALVO, _STEPS, type_="unique")
