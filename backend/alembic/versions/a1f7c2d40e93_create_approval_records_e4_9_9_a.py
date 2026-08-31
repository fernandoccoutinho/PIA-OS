"""create approval_records tables with lifecycle guard (E4.9.9.a)

Revision ID: a1f7c2d40e93
Revises: c8a3f5017e94
Create Date: 2026-08-18 22:40:00.000000

Terceira migration da E4.9 a instalar trigger, seguindo o padrão que a
E4.9.5 estabeleceu e a E4.9.6 repetiu: função e trigger de **nomes
próprios**, nunca compartilhados entre tabelas.

Diferença material em relação às duas anteriores: `approval_records` **não**
é append-only. Ela tem um ciclo de vida de uso único, e a trigger precisa
distinguir a única transição legítima de qualquer outra escrita.

```text
APPEND_ONLY != SINGLE_USE_LIFECYCLE
```

`DELETE` continua proibido nas três tabelas — a trilha de aprovação não
desaparece —, e todo campo de binding é imutável depois do INSERT.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "a1f7c2d40e93"
down_revision: str | None = "c8a3f5017e94"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


_FUNCTION_RECORDS = "reject_approval_record_invalid_write"
_TRIGGER_RECORDS = "trg_approval_records_lifecycle_guard"
_FUNCTION_TARGETS = "reject_approval_target_mutation"
_TRIGGER_TARGETS = "trg_approval_record_targets_immutable"
_FUNCTION_ITEMS = "reject_approval_governance_item_mutation"
_TRIGGER_ITEMS = "trg_approval_governance_items_immutable"

_TEXTO = 512


def upgrade() -> None:
    op.create_table(
        "approval_records",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("nonce", sa.Uuid(), nullable=False),
        sa.Column(
            "state",
            sa.Enum(
                "ACTIVE",
                "CONSUMED",
                "REVOKED",
                name="approval_lifecycle_state",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "operation",
            sa.Enum(
                "MOVE_TO_TRASH",
                "PERMANENT_ERASURE",
                name="destructive_operation",
                native_enum=False,
                length=64,
            ),
            nullable=False,
        ),
        sa.Column("principal_ref", sa.String(length=_TEXTO), nullable=False),
        sa.Column(
            "assurance_level",
            sa.Enum(
                "UNAUTHENTICATED",
                "AUTHENTICATED",
                "STEP_UP_VERIFIED",
                name="assurance_level",
                native_enum=False,
                length=64,
            ),
            nullable=False,
        ),
        sa.Column("authenticated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tenant_id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("domain_id", sa.Uuid(), nullable=False),
        sa.Column("purpose_ref", sa.String(length=_TEXTO), nullable=False),
        sa.Column(
            "channel",
            sa.Enum("TEXT", "VOICE", name="input_channel", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column(
            "voice_review",
            sa.Enum(
                "NOT_APPLICABLE",
                "NOT_REVIEWED",
                "LOW_CONFIDENCE",
                "AMBIGUOUS",
                "REVIEWED_AND_CONFIRMED",
                name="voice_review_state",
                native_enum=False,
                length=64,
            ),
            nullable=False,
        ),
        sa.Column("impact_item_count", sa.Integer(), nullable=False),
        sa.Column(
            "impact_volume_kind",
            sa.Enum("KNOWN", "UNKNOWN", name="impact_volume_kind", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("impact_bytes_total", sa.Integer(), nullable=True),
        sa.Column(
            "governance_outcome",
            sa.Enum(
                "ADMISSIBLE",
                "INADMISSIBLE",
                "NOT_APPLICABLE",
                "PROHIBITED",
                name="governance_outcome",
                native_enum=False,
                length=64,
            ),
            nullable=False,
        ),
        sa.Column(
            "governance_operation",
            sa.Enum(
                "READ",
                "REFERENCE",
                "DERIVE",
                "TRANSFORM",
                "EXPOSE",
                "SYNCHRONIZE",
                "CONSOLIDATE",
                "ACCESSIBILITY_TRANSITION",
                "RETENTION_ASSESSMENT",
                "RETENTION_DISPOSITION",
                "LEGAL_ERASURE",
                name="cognitive_operation",
                native_enum=False,
                length=64,
            ),
            nullable=False,
        ),
        sa.Column("governance_actor_ref", sa.String(length=_TEXTO), nullable=True),
        sa.Column("governance_purpose", sa.String(length=_TEXTO), nullable=True),
        sa.Column("governance_safety_boundary_version", sa.Integer(), nullable=False),
        sa.Column("governance_safety_rationale", sa.String(length=_TEXTO), nullable=False),
        sa.Column("governance_preserved_intent", sa.String(length=_TEXTO), nullable=True),
        sa.Column("governance_policy_key", sa.String(length=_TEXTO), nullable=True),
        sa.Column("governance_policy_version", sa.Integer(), nullable=True),
        sa.Column("governance_policy_id", sa.Uuid(), nullable=True),
        sa.Column("governance_matched_rule_id", sa.String(length=_TEXTO), nullable=True),
        sa.Column("governance_policy_rationale", sa.String(length=_TEXTO), nullable=False),
        sa.Column("materialized_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
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
        sa.CheckConstraint("nonce <> id", name="ck_approval_records_nonce_distinct"),
        sa.CheckConstraint(
            "state IN ('ACTIVE', 'CONSUMED', 'REVOKED')",
            name="ck_approval_records_state_vocabulary",
        ),
        sa.CheckConstraint(
            "impact_item_count >= 0", name="ck_approval_records_item_count_non_negative"
        ),
        sa.CheckConstraint(
            "(impact_volume_kind = 'KNOWN' AND impact_bytes_total IS NOT NULL "
            "AND impact_bytes_total >= 0) OR "
            "(impact_volume_kind = 'UNKNOWN' AND impact_bytes_total IS NULL)",
            name="ck_approval_records_volume_coherent",
        ),
        sa.CheckConstraint(
            "materialized_at <= authenticated_at AND authenticated_at <= confirmed_at "
            "AND materialized_at <= issued_at AND issued_at <= confirmed_at "
            "AND confirmed_at < expires_at",
            name="ck_approval_records_temporal_order",
        ),
        sa.CheckConstraint(
            "(state = 'ACTIVE' AND consumed_at IS NULL AND revoked_at IS NULL) OR "
            "(state = 'CONSUMED' AND consumed_at IS NOT NULL AND revoked_at IS NULL) OR "
            "(state = 'REVOKED' AND revoked_at IS NOT NULL AND consumed_at IS NULL)",
            name="ck_approval_records_state_timestamp_coherent",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("nonce", name="uq_approval_records_nonce"),
    )
    op.create_index("ix_approval_records_state", "approval_records", ["state"])
    op.create_index(
        "ix_approval_records_workspace", "approval_records", ["tenant_id", "workspace_id"]
    )

    op.create_table(
        "approval_record_targets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("approval_record_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "target_class",
            sa.Enum(
                "PIA_MANAGED_ARTIFACT",
                "AUTHORIZED_CONNECTOR_REFERENT",
                "COGNITIVE_METADATA_RECORD",
                "UNRESOLVED_OPAQUE_REFERENCE",
                name="erasure_target_class",
                native_enum=False,
                length=64,
            ),
            nullable=False,
        ),
        sa.Column("subject_coid", sa.Uuid(), nullable=False),
        sa.Column("control_workspace_id", sa.Uuid(), nullable=False),
        sa.Column("control_tenant_id", sa.Uuid(), nullable=False),
        sa.Column("control_principal_ref", sa.String(length=_TEXTO), nullable=False),
        sa.Column("custody_provider", sa.String(length=_TEXTO), nullable=False),
        sa.Column("custody_namespace", sa.String(length=_TEXTO), nullable=False),
        sa.Column(
            "origin_kind",
            sa.Enum(
                "PAYLOAD_REF",
                "SOURCE_REF",
                "EVIDENCE_REFS",
                "INPUT_REFS",
                "OUTPUT_REFS",
                name="reference_origin",
                native_enum=False,
                length=64,
            ),
            nullable=False,
        ),
        sa.Column("origin_position", sa.Integer(), nullable=True),
        sa.Column(
            "legacy_protection_state",
            sa.Enum(
                "PROTECTED",
                "NOT_PROTECTED",
                name="legacy_protection_state",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("version_etag", sa.String(length=_TEXTO), nullable=True),
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
        sa.CheckConstraint("position >= 0", name="ck_approval_targets_position_non_negative"),
        sa.CheckConstraint(
            "origin_position IS NULL OR origin_position >= 0",
            name="ck_approval_targets_origin_position_non_negative",
        ),
        sa.CheckConstraint(
            "legacy_protection_state IN ('PROTECTED', 'NOT_PROTECTED')",
            name="ck_approval_targets_legacy_vocabulary",
        ),
        sa.ForeignKeyConstraint(
            ["approval_record_id"], ["approval_records.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("approval_record_id", "position", name="uq_approval_targets_position"),
        sa.UniqueConstraint(
            "approval_record_id", "subject_coid", name="uq_approval_targets_subject"
        ),
    )
    op.create_index("ix_approval_targets_record", "approval_record_targets", ["approval_record_id"])

    op.create_table(
        "approval_record_governance_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("approval_record_id", sa.Uuid(), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "DOMAIN_ID",
                "BLOCKED_CAPABILITY",
                "ADMISSIBLE_ALTERNATIVE",
                "CONSTRAINT",
                "DECLARED_PRESERVATION",
                "DECLARED_LOSS",
                name="governance_item_kind",
                native_enum=False,
                length=64,
            ),
            nullable=False,
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("value_uuid", sa.Uuid(), nullable=True),
        sa.Column(
            "value_enum",
            sa.Enum(
                "CHILD_SEXUAL_EXPLOITATION",
                "MINOR_TARGETING_FOR_EXPLOITATION",
                "WEAPON_OF_MASS_DESTRUCTION_ENABLEMENT",
                "CATASTROPHIC_HARM_ENABLEMENT",
                name="critical_capability",
                native_enum=False,
                length=128,
            ),
            nullable=True,
        ),
        sa.Column("value_text", sa.String(length=_TEXTO), nullable=True),
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
        sa.CheckConstraint("position >= 0", name="ck_approval_gov_items_position_non_negative"),
        sa.CheckConstraint(
            "kind IN ('DOMAIN_ID', 'BLOCKED_CAPABILITY', 'ADMISSIBLE_ALTERNATIVE', "
            "'CONSTRAINT', 'DECLARED_PRESERVATION', 'DECLARED_LOSS')",
            name="ck_approval_gov_items_kind_vocabulary",
        ),
        sa.CheckConstraint(
            "(kind = 'DOMAIN_ID' AND value_uuid IS NOT NULL "
            "AND value_enum IS NULL AND value_text IS NULL) OR "
            "(kind = 'BLOCKED_CAPABILITY' AND value_enum IS NOT NULL "
            "AND value_uuid IS NULL AND value_text IS NULL) OR "
            "(kind NOT IN ('DOMAIN_ID', 'BLOCKED_CAPABILITY') "
            "AND value_text IS NOT NULL AND value_uuid IS NULL AND value_enum IS NULL)",
            name="ck_approval_gov_items_value_matches_kind",
        ),
        sa.ForeignKeyConstraint(
            ["approval_record_id"], ["approval_records.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "approval_record_id", "kind", "position", name="uq_approval_gov_items_order"
        ),
    )
    op.create_index(
        "ix_approval_gov_items_record",
        "approval_record_governance_items",
        ["approval_record_id", "kind", "position"],
    )

    if op.get_bind().dialect.name != "postgresql":
        return

    # ------------------------------------------------------------------
    # Camada de banco — a única que vale contra SQL bruto.
    #
    # `approval_records` NÃO é append-only: tem uma transição legítima.
    # A função enumera as colunas de binding e recusa qualquer alteração
    # nelas; permite apenas ACTIVE -> CONSUMED e ACTIVE -> REVOKED, com o
    # instante correspondente preenchido e o outro nulo.
    # ------------------------------------------------------------------
    op.execute(
        sa.text(
            f"""
            CREATE OR REPLACE FUNCTION {_FUNCTION_RECORDS}()
            RETURNS TRIGGER
            LANGUAGE plpgsql
            SET search_path = pg_catalog
            AS $$
            BEGIN
                IF TG_OP = 'DELETE' THEN
                    RAISE EXCEPTION
                        'approval_records forbids DELETE: approval trail is permanent'
                        USING ERRCODE = 'raise_exception';
                END IF;

                IF NEW.id IS DISTINCT FROM OLD.id
                   OR NEW.nonce IS DISTINCT FROM OLD.nonce
                   OR NEW.operation IS DISTINCT FROM OLD.operation
                   OR NEW.principal_ref IS DISTINCT FROM OLD.principal_ref
                   OR NEW.assurance_level IS DISTINCT FROM OLD.assurance_level
                   OR NEW.authenticated_at IS DISTINCT FROM OLD.authenticated_at
                   OR NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
                   OR NEW.workspace_id IS DISTINCT FROM OLD.workspace_id
                   OR NEW.domain_id IS DISTINCT FROM OLD.domain_id
                   OR NEW.purpose_ref IS DISTINCT FROM OLD.purpose_ref
                   OR NEW.channel IS DISTINCT FROM OLD.channel
                   OR NEW.voice_review IS DISTINCT FROM OLD.voice_review
                   OR NEW.impact_item_count IS DISTINCT FROM OLD.impact_item_count
                   OR NEW.impact_volume_kind IS DISTINCT FROM OLD.impact_volume_kind
                   OR NEW.impact_bytes_total IS DISTINCT FROM OLD.impact_bytes_total
                   OR NEW.governance_outcome IS DISTINCT FROM OLD.governance_outcome
                   OR NEW.governance_operation IS DISTINCT FROM OLD.governance_operation
                   OR NEW.governance_actor_ref IS DISTINCT FROM OLD.governance_actor_ref
                   OR NEW.governance_purpose IS DISTINCT FROM OLD.governance_purpose
                   OR NEW.governance_safety_boundary_version
                       IS DISTINCT FROM OLD.governance_safety_boundary_version
                   OR NEW.governance_safety_rationale
                       IS DISTINCT FROM OLD.governance_safety_rationale
                   OR NEW.governance_preserved_intent
                       IS DISTINCT FROM OLD.governance_preserved_intent
                   OR NEW.governance_policy_key IS DISTINCT FROM OLD.governance_policy_key
                   OR NEW.governance_policy_version
                       IS DISTINCT FROM OLD.governance_policy_version
                   OR NEW.governance_policy_id IS DISTINCT FROM OLD.governance_policy_id
                   OR NEW.governance_matched_rule_id
                       IS DISTINCT FROM OLD.governance_matched_rule_id
                   OR NEW.governance_policy_rationale
                       IS DISTINCT FROM OLD.governance_policy_rationale
                   OR NEW.materialized_at IS DISTINCT FROM OLD.materialized_at
                   OR NEW.issued_at IS DISTINCT FROM OLD.issued_at
                   OR NEW.confirmed_at IS DISTINCT FROM OLD.confirmed_at
                   OR NEW.expires_at IS DISTINCT FROM OLD.expires_at
                THEN
                    RAISE EXCEPTION
                        'approval_records binding fields are immutable after INSERT'
                        USING ERRCODE = 'raise_exception';
                END IF;

                IF OLD.state <> 'ACTIVE' THEN
                    RAISE EXCEPTION
                        'approval_records state % is terminal: no transition allowed',
                        OLD.state
                        USING ERRCODE = 'raise_exception';
                END IF;

                IF NEW.state = 'CONSUMED' THEN
                    IF NEW.consumed_at IS NULL OR NEW.revoked_at IS NOT NULL THEN
                        RAISE EXCEPTION
                            'CONSUMED requires consumed_at and no revoked_at'
                            USING ERRCODE = 'raise_exception';
                    END IF;
                ELSIF NEW.state = 'REVOKED' THEN
                    IF NEW.revoked_at IS NULL OR NEW.consumed_at IS NOT NULL THEN
                        RAISE EXCEPTION
                            'REVOKED requires revoked_at and no consumed_at'
                            USING ERRCODE = 'raise_exception';
                    END IF;
                ELSE
                    RAISE EXCEPTION
                        'approval_records allows only ACTIVE -> CONSUMED | REVOKED'
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
            f"""
            CREATE TRIGGER {_TRIGGER_RECORDS}
            BEFORE UPDATE OR DELETE ON approval_records
            FOR EACH ROW
            EXECUTE FUNCTION {_FUNCTION_RECORDS}();
            """
        )
    )

    for funcao, gatilho, tabela in (
        (_FUNCTION_TARGETS, _TRIGGER_TARGETS, "approval_record_targets"),
        (_FUNCTION_ITEMS, _TRIGGER_ITEMS, "approval_record_governance_items"),
    ):
        op.execute(
            sa.text(
                f"""
                CREATE OR REPLACE FUNCTION {funcao}()
                RETURNS TRIGGER
                LANGUAGE plpgsql
                SET search_path = pg_catalog
                AS $$
                BEGIN
                    RAISE EXCEPTION
                        '{tabela} is immutable: % rejected', TG_OP
                        USING ERRCODE = 'raise_exception';
                END;
                $$;
                """
            )
        )
        op.execute(
            sa.text(
                f"""
                CREATE TRIGGER {gatilho}
                BEFORE UPDATE OR DELETE ON {tabela}
                FOR EACH ROW
                EXECUTE FUNCTION {funcao}();
                """
            )
        )


def downgrade() -> None:
    # Ordem segura: trigger, função, índice, tabela — e as filhas antes da
    # pai, senão a FK RESTRICT impede. Remover a tabela primeiro derrubaria
    # a trigger junto e deixaria a função órfã.
    if op.get_bind().dialect.name == "postgresql":
        for gatilho, tabela, funcao in (
            (_TRIGGER_ITEMS, "approval_record_governance_items", _FUNCTION_ITEMS),
            (_TRIGGER_TARGETS, "approval_record_targets", _FUNCTION_TARGETS),
            (_TRIGGER_RECORDS, "approval_records", _FUNCTION_RECORDS),
        ):
            op.execute(sa.text(f"DROP TRIGGER IF EXISTS {gatilho} ON {tabela}"))
            op.execute(sa.text(f"DROP FUNCTION IF EXISTS {funcao}()"))

    op.drop_index("ix_approval_gov_items_record", table_name="approval_record_governance_items")
    op.drop_table("approval_record_governance_items")
    op.drop_index("ix_approval_targets_record", table_name="approval_record_targets")
    op.drop_table("approval_record_targets")
    op.drop_index("ix_approval_records_workspace", table_name="approval_records")
    op.drop_index("ix_approval_records_state", table_name="approval_records")
    op.drop_table("approval_records")
