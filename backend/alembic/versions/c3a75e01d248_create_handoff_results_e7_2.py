"""create handoff_results and handoff_attributions (E7.2)

Revision ID: c3a75e01d248
Revises: b8c04e2fd137
Create Date: 2026-08-23 03:10:00.000000

Duas tabelas append-only e um índice parcial único.

```text
handoff_results       veredito sobre um retorno; 1 por tentativa importada
handoff_attributions  qual IA alegou ter respondido; 1 por tentativa
ix_handoff_attempts_single_open   no máximo uma Attempt OPEN por Step
```

Três decisões do schema merecem registro, porque são o que torna as
provas possíveis em vez de prováveis:

1. **Índice parcial único** sobre `handoff_attempts (step_id) WHERE state
   = 'open'`. A aplicação também verifica sob lock, e as duas coisas não
   são redundantes:

   ```text
   APPLICATION_CHECK != DATABASE_GUARANTEE
   ```

   O `SELECT ... FOR UPDATE` serializa quem passa pelo serviço; o índice
   recusa quem chegar por SQL bruto, por réplica futura ou por um caminho
   que ainda não existe. Parcial, e não total, porque tentativas fechadas
   se acumulam por design — o histórico é o produto.

2. **Coerência status × códigos** por `CHECK` com `jsonb_array_length`:
   `VALIDATED` exige lista vazia, `REJECTED` exige ao menos um código. Um
   veredito aprovado carregando motivo de recusa seria uma linha que
   contradiz a si mesma, e nenhuma leitura posterior saberia qual metade
   acreditar.

3. **Append-only nas duas tabelas**, no molde medido de `seal_receipts`:
   função + trigger de linha para UPDATE/DELETE + trigger de statement
   para TRUNCATE. Resultado rejeitado e atribuição divergente são
   exatamente o que alguém teria interesse em apagar.

`provenance_record_ref` é coluna **nullable sem chave estrangeira**.

```text
REFERENCE != FOREIGN_KEY
```

A FK foi tentada e removida por causa de camada, não por conveniência:
declará-la no ORM exige `provenance_records` no mesmo `MetaData` durante
o flush, o que obrigaria `app.orchestration` a importar `app.cognitive` —
o escopo negativo da E7 proíbe exatamente isso, e a guarda estática
reprova. O precedente do programa para referência entre domínios é a
referência opaca, como `Schedule.control_principal_ref`.

Custo declarado: sem integridade referencial verificada pelo banco nesta
coluna. Referenciar continua não sendo escrever — a E7.2 deixa a coluna
`NULL` em toda linha que cria, não importa `ProvenanceManager` e não toca
a tabela de proveniência.

Nenhuma coluna de conteúdo bruto, prompt, resposta ou transcrição existe
aqui. O que sobrevive de um retorno é hash, tamanho, media type e códigos.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "c3a75e01d248"
down_revision: str | None = "b8c04e2fd137"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_RESULTS = "handoff_results"
_ATTRIBUTIONS = "handoff_attributions"
_ATTEMPTS = "handoff_attempts"

_INDEX_SINGLE_OPEN = "ix_handoff_attempts_single_open"
_FUNCTION_APPEND_ONLY = "reject_handoff_record_mutation"
_TRIGGERS = (
    (_RESULTS, "trg_handoff_results_append_only", "trg_handoff_results_no_truncate"),
    (_ATTRIBUTIONS, "trg_handoff_attributions_append_only", "trg_handoff_attributions_no_truncate"),
)

_RESULT_STATUSES = ("validated", "rejected")


def _json_type() -> sa.types.TypeEngine[object]:
    return sa.JSON().with_variant(sa.dialects.postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def upgrade() -> None:
    e_postgres = op.get_bind().dialect.name == "postgresql"

    op.create_table(
        _RESULTS,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                *_RESULT_STATUSES,
                name="orchestration_handoff_result_status",
                native_enum=False,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("expected_output_contract", sa.String(length=255), nullable=False),
        sa.Column("output_media_type", sa.String(length=64), nullable=False),
        sa.Column("output_sha256", sa.String(length=64), nullable=False),
        sa.Column("output_bytes", sa.Integer(), nullable=False),
        sa.Column("declared_output_ref", sa.String(length=1024), nullable=True),
        sa.Column("validation_codes", _json_type(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["attempt_id"], [f"{_ATTEMPTS}.id"], name="fk_handoff_results_attempt"
        ),
        sa.UniqueConstraint("attempt_id", name="uq_handoff_results_attempt"),
        sa.CheckConstraint(
            "length(output_sha256) = 64", name="ck_handoff_results_output_sha256_length"
        ),
        sa.CheckConstraint(
            "output_bytes >= 0", name="ck_handoff_results_output_bytes_non_negative"
        ),
        sa.CheckConstraint(
            "length(btrim(expected_output_contract)) > 0",
            name="ck_handoff_results_contract_not_blank",
        ),
        sa.CheckConstraint(
            "length(btrim(output_media_type)) > 0", name="ck_handoff_results_media_type_not_blank"
        ),
    )
    op.create_index("ix_handoff_results_status", _RESULTS, ["status"])

    op.create_table(
        _ATTRIBUTIONS,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("role", sa.String(length=64), nullable=False),
        sa.Column("declared_provider_id", sa.String(length=255), nullable=True),
        sa.Column("declared_model_id", sa.String(length=255), nullable=True),
        sa.Column("declared_instance_id", sa.String(length=255), nullable=False),
        sa.Column("declared_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("self_declared", sa.Boolean(), nullable=False),
        sa.Column("provenance_record_ref", sa.Uuid(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["attempt_id"], [f"{_ATTEMPTS}.id"], name="fk_handoff_attributions_attempt"
        ),
        sa.UniqueConstraint("attempt_id", name="uq_handoff_attributions_attempt"),
        sa.CheckConstraint("self_declared", name="ck_handoff_attributions_self_declared_true"),
        sa.CheckConstraint(
            "length(btrim(role)) > 0", name="ck_handoff_attributions_role_not_blank"
        ),
        sa.CheckConstraint(
            "length(btrim(declared_instance_id)) > 0",
            name="ck_handoff_attributions_instance_not_blank",
        ),
    )
    op.create_index("ix_handoff_attributions_provider", _ATTRIBUTIONS, ["declared_provider_id"])

    if e_postgres:
        op.create_check_constraint(
            "ck_handoff_results_output_sha256_hex",
            _RESULTS,
            sa.text("output_sha256 ~ '^[0-9a-f]{64}$'"),
        )
        op.create_check_constraint(
            "ck_handoff_results_status_codes_coherent",
            _RESULTS,
            sa.text(
                "(status = 'validated' AND jsonb_array_length(validation_codes) = 0) "
                "OR (status = 'rejected' AND jsonb_array_length(validation_codes) >= 1)"
            ),
        )
        op.create_check_constraint(
            "ck_handoff_results_codes_is_array",
            _RESULTS,
            sa.text("jsonb_typeof(validation_codes) = 'array'"),
        )
        # Uma única tentativa OPEN por Step, imposta pelo banco.
        op.execute(
            sa.text(
                f"""
                CREATE UNIQUE INDEX {_INDEX_SINGLE_OPEN}
                ON {_ATTEMPTS} (step_id)
                WHERE state = 'open'
                """
            )
        )
        op.execute(
            sa.text(
                f"""
                CREATE OR REPLACE FUNCTION {_FUNCTION_APPEND_ONLY}()
                RETURNS TRIGGER
                LANGUAGE plpgsql
                SET search_path = pg_catalog
                AS $$
                BEGIN
                    RAISE EXCEPTION
                        '% is append-only: % rejected', TG_TABLE_NAME, TG_OP
                        USING ERRCODE = 'raise_exception';
                END;
                $$;
                """
            )
        )
        for tabela, trigger_linha, trigger_truncate in _TRIGGERS:
            op.execute(
                sa.text(
                    f"""
                    CREATE TRIGGER {trigger_linha}
                    BEFORE UPDATE OR DELETE ON {tabela}
                    FOR EACH ROW EXECUTE FUNCTION {_FUNCTION_APPEND_ONLY}();
                    """
                )
            )
            op.execute(
                sa.text(
                    f"""
                    CREATE TRIGGER {trigger_truncate}
                    BEFORE TRUNCATE ON {tabela}
                    FOR EACH STATEMENT EXECUTE FUNCTION {_FUNCTION_APPEND_ONLY}();
                    """
                )
            )


def downgrade() -> None:
    connection = op.get_bind()
    for tabela in (_RESULTS, _ATTRIBUTIONS):
        linhas = connection.execute(sa.text(f"SELECT count(*) FROM {tabela}")).scalar_one()
        if linhas:
            raise RuntimeError(
                f"downgrade recusado: {linhas} linha(s) em {tabela}; o histórico "
                "append-only de vereditos e atribuições não pode ser apagado "
                "implicitamente por um rollback de schema"
            )
    e_postgres = connection.dialect.name == "postgresql"
    if e_postgres:
        for tabela, trigger_linha, trigger_truncate in _TRIGGERS:
            op.execute(sa.text(f"DROP TRIGGER IF EXISTS {trigger_truncate} ON {tabela}"))
            op.execute(sa.text(f"DROP TRIGGER IF EXISTS {trigger_linha} ON {tabela}"))
        op.execute(sa.text(f"DROP FUNCTION IF EXISTS {_FUNCTION_APPEND_ONLY}()"))
        op.execute(sa.text(f"DROP INDEX IF EXISTS {_INDEX_SINGLE_OPEN}"))
    op.drop_index("ix_handoff_attributions_provider", table_name=_ATTRIBUTIONS)
    op.drop_table(_ATTRIBUTIONS)
    op.drop_index("ix_handoff_results_status", table_name=_RESULTS)
    op.drop_table(_RESULTS)
