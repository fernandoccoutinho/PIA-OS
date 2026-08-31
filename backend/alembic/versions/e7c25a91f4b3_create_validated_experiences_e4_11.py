"""create validated_experiences table with append-only trigger (E4.11)

Revision ID: e7c25a91f4b3
Revises: d5b31f7a08c4
Create Date: 2026-08-19 14:20:00.000000

```text
IF REMOVING THE RECORD CHANGES SYSTEM BEHAVIOR
THEN IT IS A LEARNING ENGINE
```

Uma tabela, sucessora **linear** da cabeça da cadeia 95. Nenhuma tabela
congelada da E3 ou da E4 é tocada.

## Append-only imposto pelo banco

Segue o precedente mais forte do projeto, o da E4.9.5: trigger
`BEFORE UPDATE OR DELETE` que recusa a operação. A E3 declara
explicitamente que **não** impõe append-only no banco para
`ProvenanceRecord`, e essa diferença é deliberada aqui — SQL arbitrário
fora do repositório também precisa ser recusado.

## Downgrade recusa com dados

```text
TABLE_EMPTY    -> downgrade permitido
TABLE_NONEMPTY -> recusa explícita ANTES de qualquer DDL
REFUSE_BEFORE_ALTER, NEVER_MID_MIGRATION
```

A medição vem antes de derrubar trigger, função, índice ou tabela. Um
downgrade impeditivo que já tivesse removido a trigger deixaria a tabela
mutável e a migration abortada — estado que nenhum dos dois lados
descreve. Depois da recusa, tudo permanece intacto.

Registro de validação apagado é evidência apagada, e `DISTINCTION
EXTINCTION != HISTORICAL ERASURE`: o downgrade não decide por conta
própria que a evidência pode desaparecer.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "e7c25a91f4b3"
down_revision: str | None = "d5b31f7a08c4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_TABELA = "validated_experiences"
_FUNCTION_NAME = "reject_validated_experience_mutation"
_TRIGGER_ROW = "trg_validated_experiences_append_only"
_TRIGGER_TRUNCATE = "trg_validated_experiences_no_truncate"
_FUNCTION_EVIDENCE = "validated_experience_evidence_is_canonical"
_CHECK_EVIDENCE = "ck_validated_experiences_evidence_refs_canonical"

_PADRAO_UUID = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
"""Forma canônica minúscula — a mesma que `str(uuid.UUID)` produz."""


def upgrade() -> None:
    # ```text
    # APP_TYPED_BOUNDARY != DATABASE_INTEGRITY
    # JSONB_NOT_NULL     != CLOSED_EVIDENCE_SCHEMA
    # ```
    #
    # ACRESCENTADO NA AUDITORIA DA CADEIA 96 (achado A3). A coluna
    # `evidence_refs` impunha apenas `NOT NULL`, e SQL bruto podia
    # gravar array vazio, objeto no lugar de array, chave `url` ou
    # `credential`, `kind` inventado, UUID inválido, duplicata, ordem não
    # canônica ou evidência primária ausente do conjunto. Numa tabela
    # append-only, uma linha assim fica **permanente**.
    #
    # `CHECK` não aceita subconsulta, então a validação vive numa função
    # `IMMUTABLE` chamada pela constraint. Ela RECUSA — nunca normaliza
    # em silêncio, nunca descarta campo extra.
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            sa.text(
                f"""
                CREATE OR REPLACE FUNCTION {_FUNCTION_EVIDENCE}(
                    evidencia jsonb,
                    primaria_kind text,
                    primaria_ref text
                )
                RETURNS boolean
                LANGUAGE plpgsql
                IMMUTABLE
                SET search_path = pg_catalog
                AS $$
                DECLARE
                    item jsonb;
                    anterior text := NULL;
                    atual text;
                    achou_primaria boolean := false;
                BEGIN
                    IF evidencia IS NULL OR jsonb_typeof(evidencia) <> 'array' THEN
                        RETURN false;
                    END IF;
                    IF jsonb_array_length(evidencia) = 0 THEN
                        RETURN false;
                    END IF;

                    FOR item IN SELECT * FROM jsonb_array_elements(evidencia) LOOP
                        IF jsonb_typeof(item) <> 'object' THEN
                            RETURN false;
                        END IF;
                        -- Chaves EXATAS: nem a menos, nem a mais. É o que
                        -- impede `content`, `url` e `credential` de entrarem.
                        IF (SELECT count(*) FROM jsonb_object_keys(item)) <> 2 THEN
                            RETURN false;
                        END IF;
                        IF NOT (item ? 'kind' AND item ? 'ref') THEN
                            RETURN false;
                        END IF;
                        IF jsonb_typeof(item -> 'kind') <> 'string'
                           OR jsonb_typeof(item -> 'ref') <> 'string' THEN
                            RETURN false;
                        END IF;
                        IF (item ->> 'kind') NOT IN (
                            'cognitive_object',
                            'causal_event',
                            'provenance_record',
                            'transformation_record'
                        ) THEN
                            RETURN false;
                        END IF;
                        IF (item ->> 'ref') !~ '{_PADRAO_UUID}' THEN
                            RETURN false;
                        END IF;

                        atual := (item ->> 'kind') || '|' || (item ->> 'ref');
                        -- Ordem ESTRITAMENTE crescente cobre as duas
                        -- garantias de uma vez: sem duplicata e em ordem
                        -- canônica (kind, ref).
                        IF anterior IS NOT NULL AND atual <= anterior THEN
                            RETURN false;
                        END IF;
                        anterior := atual;

                        IF (item ->> 'kind') = primaria_kind
                           AND (item ->> 'ref') = primaria_ref THEN
                            achou_primaria := true;
                        END IF;
                    END LOOP;

                    RETURN achou_primaria;
                END;
                $$;
                """
            )
        )

    op.create_table(
        _TABELA,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column(
            "subject_kind",
            sa.Enum(
                "cognitive_object",
                "causal_event",
                name="experience_subject_kind",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("subject_ref", sa.Uuid(), nullable=False),
        sa.Column("outcome_token", sa.String(length=64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "primary_evidence_kind",
            sa.Enum(
                "cognitive_object",
                "causal_event",
                "provenance_record",
                "transformation_record",
                name="validated_experience_evidence_kind",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("primary_evidence_ref", sa.Uuid(), nullable=False),
        sa.Column(
            "validator_kind",
            sa.Enum(
                "human",
                "agent",
                "system",
                name="validated_experience_validator_kind",
                native_enum=False,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("validator_ref", sa.String(length=255), nullable=False),
        sa.Column("criterion_key", sa.String(length=128), nullable=False),
        sa.Column("criterion_version", sa.Integer(), nullable=False),
        sa.Column(
            "criterion_origin",
            sa.Enum(
                "published",
                "declared",
                name="validated_experience_criterion_origin",
                native_enum=False,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column(
            "evidence_refs",
            sa.JSON().with_variant(
                sa.dialects.postgresql.JSONB(astext_type=sa.Text()), "postgresql"
            ),
            nullable=False,
        ),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("origin_ref", sa.Uuid(), nullable=False),
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
        sa.CheckConstraint(
            "length(btrim(validator_ref)) > 0",
            name="ck_validated_experiences_validator_ref_not_blank",
        ),
        sa.CheckConstraint(
            "length(btrim(criterion_key)) > 0",
            name="ck_validated_experiences_criterion_key_not_blank",
        ),
        sa.CheckConstraint(
            "length(btrim(outcome_token)) > 0",
            name="ck_validated_experiences_outcome_token_not_blank",
        ),
        sa.CheckConstraint(
            "criterion_version >= 1",
            name="ck_validated_experiences_criterion_version_positive",
        ),
        sa.CheckConstraint(
            "observed_at <= validated_at",
            name="ck_validated_experiences_observed_before_validated",
        ),
    )
    if op.get_bind().dialect.name == "postgresql":
        op.create_check_constraint(
            _CHECK_EVIDENCE,
            _TABELA,
            sa.text(
                f"{_FUNCTION_EVIDENCE}("
                "evidence_refs, primary_evidence_kind::text, "
                "primary_evidence_ref::text)"
            ),
        )
    op.create_index("ix_validated_experiences_subject", _TABELA, ["subject_kind", "subject_ref"])
    # ACRESCENTADO NA AUDITORIA DA CADEIA 96 (achado A4): a origem entra
    # no índice porque entrou no filtro. `PARTIAL_REFERENCE_QUERY !=
    # EXACT_CRITERION_BINDING`.
    op.create_index(
        "ix_validated_experiences_criterion",
        _TABELA,
        ["criterion_key", "criterion_version", "criterion_origin"],
    )

    # SQLite não suporta esta forma de trigger, e a suíte migra contra
    # PostgreSQL real — a garantia de banco é medida onde ela existe.
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            sa.text(
                f"""
                CREATE OR REPLACE FUNCTION {_FUNCTION_NAME}()
                RETURNS TRIGGER
                LANGUAGE plpgsql
                SET search_path = pg_catalog
                AS $$
                BEGIN
                    RAISE EXCEPTION
                        '{_TABELA} is append-only: % rejected',
                        TG_OP
                        USING ERRCODE = 'raise_exception';
                END;
                $$;
                """
            )
        )
        op.execute(
            sa.text(
                f"""
                CREATE TRIGGER {_TRIGGER_ROW}
                BEFORE UPDATE OR DELETE ON {_TABELA}
                FOR EACH ROW
                EXECUTE FUNCTION {_FUNCTION_NAME}();
                """
            )
        )
        # ```text
        # ROW_TRIGGER_DOES_NOT_SEE_TRUNCATE
        # ```
        #
        # ACRESCENTADO NA AUDITORIA DA CADEIA 96 (achado A2). No
        # PostgreSQL, `TRUNCATE` não dispara trigger de linha e exige
        # trigger própria, que só existe em `FOR EACH STATEMENT`. Sem
        # ela, um `TRUNCATE` apagava a tabela append-only inteira sem
        # encontrar nenhuma recusa.
        #
        # A função de recusa é a MESMA: `TG_OP` já diz qual operação foi
        # tentada, e duplicar a mensagem faria duas verdades sobre o
        # mesmo contrato.
        op.execute(
            sa.text(
                f"""
                CREATE TRIGGER {_TRIGGER_TRUNCATE}
                BEFORE TRUNCATE ON {_TABELA}
                FOR EACH STATEMENT
                EXECUTE FUNCTION {_FUNCTION_NAME}();
                """
            )
        )


def downgrade() -> None:
    ligacao = op.get_bind()

    # A MEDIÇÃO VEM ANTES DE QUALQUER DDL, e a ordem é a garantia.
    #
    # ```text
    # REFUSE_BEFORE_ALTER, NEVER_MID_MIGRATION
    # ```
    #
    # Derrubar a trigger primeiro e só então medir deixaria a tabela
    # mutável durante a recusa — e uma evidência append-only que fica
    # gravável no meio de uma migration abortada perdeu a propriedade
    # que a define.
    linhas = ligacao.execute(sa.text(f"SELECT count(*) FROM {_TABELA}")).scalar_one()
    if linhas:
        raise RuntimeError(
            f"downgrade recusado: {linhas} experiência(s) validada(s) registrada(s). "
            "Remover a tabela apagaria evidência auditável de validações que "
            "ocorreram, e este downgrade não decide por conta própria que ela "
            "pode desaparecer. Esvazie a tabela deliberadamente antes, se for "
            "essa a intenção."
        )

    if ligacao.dialect.name == "postgresql":
        # Ordem segura: a trigger depende da função, e a função é
        # referenciada pela trigger. Remover a tabela primeiro derrubaria
        # a trigger junto e deixaria a função órfã.
        # Os DOIS triggers antes da função: ambos dependem dela, e
        # remover a função primeiro deixaria a remoção pela metade.
        op.execute(sa.text(f"DROP TRIGGER IF EXISTS {_TRIGGER_TRUNCATE} ON {_TABELA}"))
        op.execute(sa.text(f"DROP TRIGGER IF EXISTS {_TRIGGER_ROW} ON {_TABELA}"))
        op.execute(sa.text(f"DROP FUNCTION IF EXISTS {_FUNCTION_NAME}()"))

    op.drop_index("ix_validated_experiences_criterion", table_name=_TABELA)
    op.drop_index("ix_validated_experiences_subject", table_name=_TABELA)
    op.drop_table(_TABELA)

    if ligacao.dialect.name == "postgresql":
        # A função de validação do lastro só pode sair DEPOIS da tabela:
        # a constraint que a referencia morre junto com ela.
        op.execute(sa.text(f"DROP FUNCTION IF EXISTS {_FUNCTION_EVIDENCE}(jsonb, text, text)"))
