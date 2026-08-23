"""create delegation, control, observation and audit tables (E7.3)

Revision ID: f2c60d8a41b9
Revises: e5b21c9704af
Create Date: 2026-08-23 10:40:00.000000

Quatro tabelas, filha única de `e5b21c9704af`.

```text
service_delegations           ciclo de vida monotônico, NÃO append-only
orchestration_control_events  APPEND-ONLY
execution_observations        APPEND-ONLY
audit_opinions                APPEND-ONLY
```

## Por que `service_delegations` não é append-only, e mesmo assim é protegida

A delegação tem ciclo de vida (`active -> consumed|revoked|expired`),
enquanto evento, observação e parecer descrevem atos instantâneos já
terminados. Um trigger de UPDATE nela impediria o próprio consumo.

Não ser append-only não é ser descartável:

```text
DELETE / TRUNCATE        -> RECUSADOS
binding (schedule_id, step_id, content_sha256, scope, valid_until,
         granted_by_principal_ref, created_at)  -> IMUTÁVEL
transições               -> APENAS ACTIVE -> CONSUMED | REVOKED | EXPIRED
TERMINAL -> qualquer outro estado -> RECUSADO
```

Tudo por trigger, porque SQL bruto não passa pelo repositório. Sem isso,
um `UPDATE` poderia reativar uma delegação consumida ou trocar o hash a
que ela está ligada — e a garantia de uso único viraria convenção.

## FK composta e diferida do consumo

`consumed_by_attempt_id` referencia
`(id, step_id, schedule_id)` de `handoff_attempts`,
`DEFERRABLE INITIALLY DEFERRED`.

Composta porque duas referências válidas isoladamente não provam
coerência — a lição da Chain111. Diferida porque o consumo é gravado
**antes** de a Attempt existir, na mesma transação: uma FK imediata
falharia no `UPDATE`, e omiti-la repetiria o defeito. Diferida, o commit
só passa se a Attempt correspondente tiver sido criada.

O alvo exige `uq_handoff_attempts_id_step_schedule`, acrescentado a
`handoff_attempts` — ampliação declarada, redundante em cardinalidade e
obrigatória em referência.

## Expiração

Não há sweeper. `EXPIRED` é materializado sincronicamente pelo serviço,
sob lock, na avaliação e no grant. Declarar um produtor em segundo plano
seria declarar um worker que este programa não tem.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "f2c60d8a41b9"
down_revision: str | None = "e5b21c9704af"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ATTEMPTS = "handoff_attempts"
_STEPS = "schedule_steps"
_DELEGATIONS = "service_delegations"
_EVENTS = "orchestration_control_events"
_OBSERVATIONS = "execution_observations"
_OPINIONS = "audit_opinions"

_UQ_ATTEMPT_TARGET = "uq_handoff_attempts_id_step_schedule"
_FUNCTION_APPEND_ONLY = "reject_governance_record_mutation"
_FUNCTION_DELEGATION_GUARD = "guard_service_delegation_transition"
_FUNCTION_AUDIT_MATRIX = "orchestration_audit_opinion_matrix_is_valid"
_FUNCTION_GATE_MARKER = "orchestration_gate_marker_is_valid"
_CHECK_GATE_MARKER = "ck_schedule_steps_gate_marker_valid"
_INDEX_SINGLE_ACTIVE = "ix_service_delegations_single_active"

_APPEND_ONLY = (
    (_EVENTS, "trg_control_events_append_only", "trg_control_events_no_truncate"),
    (_OBSERVATIONS, "trg_observations_append_only", "trg_observations_no_truncate"),
    (_OPINIONS, "trg_audit_opinions_append_only", "trg_audit_opinions_no_truncate"),
)

_DELEGATION_STATES = ("active", "consumed", "revoked", "expired")
_EVENT_KINDS = ("paused", "resumed", "stopped", "cancelled", "completed")
_REASON_CODES = (
    "operator_requested",
    "delegation_missing",
    "delegation_expired",
    "delegation_content_changed",
    "human_gate_unavailable",
    "stop_condition_declared",
    "all_steps_returned",
)
_STOP_CATEGORIES = (
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
)
_OBSERVATION_KINDS = ("declared_provider_switch",)
_OPINIONS_VOCAB = ("concur", "dissent", "insufficient_evidence", "out_of_scope")
_REASONS_VOCAB = (
    "contract_conforms",
    "contract_nonconformity",
    "evidence_missing",
    "scope_excluded",
)


def _json_type() -> sa.types.TypeEngine[object]:
    return sa.JSON().with_variant(sa.dialects.postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def _timestamps() -> list[sa.Column[object]]:
    return [
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
    ]


def upgrade() -> None:
    e_postgres = op.get_bind().dialect.name == "postgresql"

    op.create_unique_constraint(_UQ_ATTEMPT_TARGET, _ATTEMPTS, ["id", "step_id", "schedule_id"])

    # --- service_delegations ------------------------------------------------
    op.create_table(
        _DELEGATIONS,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("schedule_id", sa.Uuid(), nullable=False),
        sa.Column("step_id", sa.Uuid(), nullable=False),
        sa.Column("content_sha256", sa.String(length=64), nullable=False),
        sa.Column("scope", sa.String(length=32), nullable=False),
        sa.Column("granted_by_principal_ref", sa.String(length=255), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "state",
            sa.Enum(
                *_DELEGATION_STATES,
                name="orchestration_delegation_state",
                native_enum=False,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_by_attempt_id", sa.Uuid(), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["schedule_id"], ["schedules.id"], name="fk_service_delegations_schedule"
        ),
        sa.ForeignKeyConstraint(
            ["step_id", "schedule_id"],
            [f"{_STEPS}.id", f"{_STEPS}.schedule_id"],
            name="fk_service_delegations_step_within_schedule",
        ),
        sa.ForeignKeyConstraint(
            ["consumed_by_attempt_id", "step_id", "schedule_id"],
            [f"{_ATTEMPTS}.id", f"{_ATTEMPTS}.step_id", f"{_ATTEMPTS}.schedule_id"],
            name="fk_service_delegations_consumed_attempt",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.CheckConstraint(
            "length(content_sha256) = 64", name="ck_service_delegations_content_sha256_length"
        ),
        sa.CheckConstraint(
            "length(btrim(granted_by_principal_ref)) > 0",
            name="ck_service_delegations_granted_by_not_blank",
        ),
        sa.CheckConstraint(
            "(state = 'consumed') = (consumed_at IS NOT NULL)",
            name="ck_service_delegations_consumed_at_coherent",
        ),
        sa.CheckConstraint(
            "(state = 'consumed') = (consumed_by_attempt_id IS NOT NULL)",
            name="ck_service_delegations_consumed_attempt_coherent",
        ),
    )
    op.create_index("ix_service_delegations_step", _DELEGATIONS, ["step_id"])

    # --- orchestration_control_events ---------------------------------------
    op.create_table(
        _EVENTS,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("schedule_id", sa.Uuid(), nullable=False),
        sa.Column("step_id", sa.Uuid(), nullable=True),
        sa.Column(
            "event_kind",
            sa.Enum(
                *_EVENT_KINDS,
                name="orchestration_control_event_kind",
                native_enum=False,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column(
            "reason_code",
            sa.Enum(
                *_REASON_CODES,
                name="orchestration_control_reason_code",
                native_enum=False,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column(
            "stop_condition_category",
            sa.Enum(
                *_STOP_CATEGORIES,
                name="orchestration_stop_condition_category",
                native_enum=False,
                length=40,
            ),
            nullable=True,
        ),
        sa.Column("declared_by_principal_ref", sa.String(length=255), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["schedule_id"], ["schedules.id"], name="fk_control_events_schedule"
        ),
        sa.ForeignKeyConstraint(
            ["step_id", "schedule_id"],
            [f"{_STEPS}.id", f"{_STEPS}.schedule_id"],
            name="fk_control_events_step_within_schedule",
        ),
        sa.CheckConstraint(
            "(reason_code = 'stop_condition_declared') = (stop_condition_category IS NOT NULL)",
            name="ck_control_events_stop_category_matrix",
        ),
        sa.CheckConstraint(
            "length(btrim(declared_by_principal_ref)) > 0",
            name="ck_control_events_principal_not_blank",
        ),
    )
    op.create_index("ix_control_events_schedule", _EVENTS, ["schedule_id"])

    # --- execution_observations ---------------------------------------------
    op.create_table(
        _OBSERVATIONS,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("schedule_id", sa.Uuid(), nullable=False),
        sa.Column("step_id", sa.Uuid(), nullable=False),
        sa.Column(
            "observation_kind",
            sa.Enum(
                *_OBSERVATION_KINDS,
                name="orchestration_observation_kind",
                native_enum=False,
                length=40,
            ),
            nullable=False,
        ),
        sa.Column("previous_attempt_id", sa.Uuid(), nullable=False),
        sa.Column("current_attempt_id", sa.Uuid(), nullable=False),
        sa.Column("previous_declared_provider_id", sa.String(length=255), nullable=True),
        sa.Column("current_declared_provider_id", sa.String(length=255), nullable=True),
        sa.Column("self_declared", sa.Boolean(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["schedule_id"], ["schedules.id"], name="fk_execution_observations_schedule"
        ),
        sa.ForeignKeyConstraint(
            ["step_id", "schedule_id"],
            [f"{_STEPS}.id", f"{_STEPS}.schedule_id"],
            name="fk_execution_observations_step_within_schedule",
        ),
        sa.ForeignKeyConstraint(
            ["previous_attempt_id", "step_id", "schedule_id"],
            [f"{_ATTEMPTS}.id", f"{_ATTEMPTS}.step_id", f"{_ATTEMPTS}.schedule_id"],
            name="fk_execution_observations_previous_attempt",
        ),
        sa.ForeignKeyConstraint(
            ["current_attempt_id", "step_id", "schedule_id"],
            [f"{_ATTEMPTS}.id", f"{_ATTEMPTS}.step_id", f"{_ATTEMPTS}.schedule_id"],
            name="fk_execution_observations_current_attempt",
        ),
        sa.CheckConstraint("self_declared", name="ck_execution_observations_self_declared_true"),
        sa.CheckConstraint(
            "previous_attempt_id <> current_attempt_id",
            name="ck_execution_observations_distinct_attempts",
        ),
        sa.CheckConstraint(
            "previous_declared_provider_id IS DISTINCT FROM current_declared_provider_id",
            name="ck_execution_observations_provider_actually_changed",
        ),
    )
    op.create_index("ix_execution_observations_step", _OBSERVATIONS, ["step_id"])

    # --- audit_opinions -----------------------------------------------------
    op.create_table(
        _OPINIONS,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("handoff_result_id", sa.Uuid(), nullable=False),
        sa.Column(
            "opinion",
            sa.Enum(
                *_OPINIONS_VOCAB,
                name="orchestration_audit_opinion",
                native_enum=False,
                length=24,
            ),
            nullable=False,
        ),
        sa.Column("reason_codes", _json_type(), nullable=False),
        sa.Column("auditor_execution_ref", sa.String(length=255), nullable=False),
        sa.Column("issued_by_principal_ref", sa.String(length=255), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["handoff_result_id"], ["handoff_results.id"], name="fk_audit_opinions_result"
        ),
        sa.CheckConstraint(
            "length(btrim(auditor_execution_ref)) > 0",
            name="ck_audit_opinions_auditor_ref_not_blank",
        ),
        sa.CheckConstraint(
            "length(btrim(issued_by_principal_ref)) > 0",
            name="ck_audit_opinions_principal_not_blank",
        ),
    )
    op.create_index("ix_audit_opinions_result", _OPINIONS, ["handoff_result_id"])

    if not e_postgres:
        return

    # índice parcial: uma ACTIVE por (schedule_id, step_id, scope)
    op.execute(
        sa.text(
            f"""
            CREATE UNIQUE INDEX {_INDEX_SINGLE_ACTIVE}
            ON {_DELEGATIONS} (schedule_id, step_id, scope)
            WHERE state = 'active'
            """
        )
    )

    op.create_check_constraint(
        "ck_service_delegations_content_sha256_hex",
        _DELEGATIONS,
        sa.text("content_sha256 ~ '^[0-9a-f]{64}$'"),
    )

    # --- camada 3 do gate: o banco recusa marcador inválido -----------------
    #
    # ```text
    # APP_TYPED_BOUNDARY != DATABASE_INTEGRITY
    # ```
    #
    # O value object recusa na composição e o DTO recusa na entrada; nenhum
    # dos dois alcança SQL bruto. Sem esta função, uma linha com
    # `pia.gate.required = 'human'` entraria no banco e o interpretador de
    # gate teria de decidir o que fazer com uma declaração que o domínio
    # considera inexistente — e qualquer decisão ali seria invenção.
    op.execute(
        sa.text(
            f"""
            CREATE OR REPLACE FUNCTION {_FUNCTION_GATE_MARKER}(value jsonb)
            RETURNS boolean
            LANGUAGE plpgsql
            IMMUTABLE
            SET search_path = pg_catalog
            AS $$
            DECLARE
                chave text;
                reservadas int := 0;
                requerido text;
                escopo text;
            BEGIN
                IF value IS NULL OR jsonb_typeof(value) <> 'object' THEN
                    RETURN false;
                END IF;
                FOR chave IN SELECT jsonb_object_keys(value) LOOP
                    IF chave LIKE 'pia.gate.%' THEN
                        IF chave NOT IN ('pia.gate.required', 'pia.gate.scope') THEN
                            RETURN false;
                        END IF;
                        reservadas := reservadas + 1;
                    END IF;
                END LOOP;
                IF reservadas = 0 THEN
                    RETURN true;          -- ausência = sem gate, retrocompatível
                END IF;
                IF reservadas <> 2 THEN
                    RETURN false;         -- declaração pela metade
                END IF;
                requerido := value ->> 'pia.gate.required';
                escopo := value ->> 'pia.gate.scope';
                IF requerido IS NULL OR escopo IS NULL THEN
                    RETURN false;
                END IF;
                IF requerido NOT IN ('service_delegation', 'service_delegation_and_human') THEN
                    RETURN false;
                END IF;
                IF escopo <> 'dispatch' THEN
                    RETURN false;
                END IF;
                RETURN true;
            END;
            $$;
            """
        )
    )
    op.create_check_constraint(
        _CHECK_GATE_MARKER,
        _STEPS,
        sa.text(f"{_FUNCTION_GATE_MARKER}(constraints)"),
    )

    # matriz opinião x motivo, e exclusão explícita de PASS_FINAL
    #
    # Em FUNÇÃO, e não inline: `CHECK` do PostgreSQL não aceita
    # subconsulta, e `jsonb_array_elements_text` exige uma. Mesmo
    # precedente de `orchestration_validation_codes_are_canonical`.
    op.execute(
        sa.text(
            f"""
            CREATE OR REPLACE FUNCTION {_FUNCTION_AUDIT_MATRIX}(opinion text, codes jsonb)
            RETURNS boolean
            LANGUAGE plpgsql
            IMMUTABLE
            SET search_path = pg_catalog
            AS $$
            DECLARE
                esperado jsonb;
            BEGIN
                IF codes IS NULL OR jsonb_typeof(codes) <> 'array' THEN
                    RETURN false;
                END IF;
                IF jsonb_array_length(codes) <> 1 THEN
                    RETURN false;
                END IF;
                esperado := CASE opinion
                    WHEN 'concur' THEN '["contract_conforms"]'::jsonb
                    WHEN 'dissent' THEN '["contract_nonconformity"]'::jsonb
                    WHEN 'insufficient_evidence' THEN '["evidence_missing"]'::jsonb
                    WHEN 'out_of_scope' THEN '["scope_excluded"]'::jsonb
                    ELSE NULL
                END;
                IF esperado IS NULL THEN
                    RETURN false;
                END IF;
                RETURN codes = esperado;
            END;
            $$;
            """
        )
    )
    op.create_check_constraint(
        "ck_audit_opinions_reason_matrix",
        _OPINIONS,
        sa.text(f"{_FUNCTION_AUDIT_MATRIX}(opinion, reason_codes)"),
    )
    op.create_check_constraint(
        "ck_audit_opinions_never_pass_final",
        _OPINIONS,
        sa.text("opinion <> 'pass_final' AND NOT (reason_codes @> '[\"pass_final\"]'::jsonb)"),
    )
    # Redundante com o enum e com a matriz, e deliberado: uma proibição que
    # existe num lugar só some com um `git revert` desatento.

    # --- append-only nas três tabelas de registro ---------------------------
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
    for tabela, trigger_linha, trigger_truncate in _APPEND_ONLY:
        op.execute(
            sa.text(
                f"CREATE TRIGGER {trigger_linha} BEFORE UPDATE OR DELETE ON {tabela} "
                f"FOR EACH ROW EXECUTE FUNCTION {_FUNCTION_APPEND_ONLY}();"
            )
        )
        op.execute(
            sa.text(
                f"CREATE TRIGGER {trigger_truncate} BEFORE TRUNCATE ON {tabela} "
                f"FOR EACH STATEMENT EXECUTE FUNCTION {_FUNCTION_APPEND_ONLY}();"
            )
        )

    # --- guarda de ciclo de vida da delegação -------------------------------
    op.execute(
        sa.text(
            f"""
            CREATE OR REPLACE FUNCTION {_FUNCTION_DELEGATION_GUARD}()
            RETURNS TRIGGER
            LANGUAGE plpgsql
            SET search_path = pg_catalog
            AS $$
            BEGIN
                IF TG_OP IN ('DELETE', 'TRUNCATE') THEN
                    RAISE EXCEPTION
                        'service_delegations is not deletable: % rejected', TG_OP
                        USING ERRCODE = 'raise_exception';
                END IF;

                IF OLD.state <> 'active' THEN
                    RAISE EXCEPTION
                        'service_delegation is terminal (%): transition to % rejected',
                        OLD.state, NEW.state
                        USING ERRCODE = 'raise_exception';
                END IF;
                IF NEW.state NOT IN ('consumed', 'revoked', 'expired') THEN
                    RAISE EXCEPTION
                        'service_delegation transition active -> % is not allowed', NEW.state
                        USING ERRCODE = 'raise_exception';
                END IF;

                IF NEW.id <> OLD.id
                   OR NEW.schedule_id <> OLD.schedule_id
                   OR NEW.step_id <> OLD.step_id
                   OR NEW.content_sha256 <> OLD.content_sha256
                   OR NEW.scope <> OLD.scope
                   OR NEW.valid_until <> OLD.valid_until
                   OR NEW.granted_by_principal_ref <> OLD.granted_by_principal_ref
                   OR NEW.created_at <> OLD.created_at THEN
                    RAISE EXCEPTION
                        'service_delegation binding is immutable'
                        USING ERRCODE = 'raise_exception';
                END IF;

                RETURN NEW;
            END;
            $$;
            """
        )
    )
    op.execute(
        sa.text(
            f"CREATE TRIGGER trg_service_delegations_lifecycle "
            f"BEFORE UPDATE OR DELETE ON {_DELEGATIONS} "
            f"FOR EACH ROW EXECUTE FUNCTION {_FUNCTION_DELEGATION_GUARD}();"
        )
    )
    op.execute(
        sa.text(
            f"CREATE TRIGGER trg_service_delegations_no_truncate "
            f"BEFORE TRUNCATE ON {_DELEGATIONS} "
            f"FOR EACH STATEMENT EXECUTE FUNCTION {_FUNCTION_APPEND_ONLY}();"
        )
    )


def downgrade() -> None:
    connection = op.get_bind()
    for tabela in (_OPINIONS, _OBSERVATIONS, _EVENTS, _DELEGATIONS):
        linhas = connection.execute(sa.text(f"SELECT count(*) FROM {tabela}")).scalar_one()
        if linhas:
            raise RuntimeError(
                f"downgrade recusado: {linhas} linha(s) em {tabela}; delegação consumida, "
                "evento de controle, observação e parecer são história de governança e "
                "não podem ser apagados por um rollback de schema"
            )
    if connection.dialect.name == "postgresql":
        op.execute(
            sa.text(f"DROP TRIGGER IF EXISTS trg_service_delegations_no_truncate ON {_DELEGATIONS}")
        )
        op.execute(
            sa.text(f"DROP TRIGGER IF EXISTS trg_service_delegations_lifecycle ON {_DELEGATIONS}")
        )
        op.execute(sa.text(f"DROP FUNCTION IF EXISTS {_FUNCTION_DELEGATION_GUARD}()"))
        for tabela, trigger_linha, trigger_truncate in _APPEND_ONLY:
            op.execute(sa.text(f"DROP TRIGGER IF EXISTS {trigger_truncate} ON {tabela}"))
            op.execute(sa.text(f"DROP TRIGGER IF EXISTS {trigger_linha} ON {tabela}"))
        op.execute(sa.text(f"DROP FUNCTION IF EXISTS {_FUNCTION_APPEND_ONLY}()"))
        op.execute(sa.text(f"DROP INDEX IF EXISTS {_INDEX_SINGLE_ACTIVE}"))
        op.drop_constraint(_CHECK_GATE_MARKER, _STEPS, type_="check")
        op.execute(sa.text(f"DROP FUNCTION IF EXISTS {_FUNCTION_GATE_MARKER}(jsonb)"))
    op.drop_index("ix_audit_opinions_result", table_name=_OPINIONS)
    op.drop_table(_OPINIONS)
    # A função da matriz só cai DEPOIS da tabela: o `CHECK` depende dela, e
    # dropá-la antes falha com DependentObjectsStillExist.
    if connection.dialect.name == "postgresql":
        op.execute(sa.text(f"DROP FUNCTION IF EXISTS {_FUNCTION_AUDIT_MATRIX}(text, jsonb)"))
    op.drop_index("ix_execution_observations_step", table_name=_OBSERVATIONS)
    op.drop_table(_OBSERVATIONS)
    op.drop_index("ix_control_events_schedule", table_name=_EVENTS)
    op.drop_table(_EVENTS)
    op.drop_index("ix_service_delegations_step", table_name=_DELEGATIONS)
    op.drop_table(_DELEGATIONS)
    op.drop_constraint(_UQ_ATTEMPT_TARGET, _ATTEMPTS, type_="unique")
