"""create the neutral connection kernel (E7.4-1)

Revision ID: b47e9c05d3fa
Revises: a91d3f7c26be
Create Date: 2026-08-24 02:50:00.000000

Nove tabelas, filha única de `a91d3f7c26be`.

```text
connection_provider_families      curadoria
connection_model_families         curadoria
connection_model_releases         descoberta, com TTL
connection_access_providers       curadoria
connection_profiles               conexões do principal
connection_capability_snapshots   APPEND-ONLY
connection_entitlement_claims     IMMUTABLE_PAYLOAD + MONOTONIC_LIFECYCLE
connection_evaluation_evidence    APPEND-ONLY, e nunca decisória
connection_execution_receipts     APPEND-ONLY
```

## O que o banco fecha, e por quê fecha aqui

`SAEnum(..., native_enum=False)` **não** cria `CHECK` por padrão: a
coluna vira `VARCHAR(n)` e aceita qualquer texto que caiba. O achado é da
Chain117 e vale para toda tabela nova.

```text
TYPED_IN_PYTHON != CONSTRAINED_IN_POSTGRES
APP_TYPED_BOUNDARY != DATABASE_INTEGRITY
```

Três fechamentos merecem destaque:

```text
ck_connection_profiles_available_method
    ENUM_OR_REGISTRY != AVAILABLE — só manual pode estar AVAILABLE
ix_connection_profiles_manual_singleton
    NULL_NÃO_COLIDE_COM_NULL — a trinca geral não cobre endpoint nulo
ck_connection_execution_receipts_attestation_bicondicional
    atestar exige ter observado
```

## Vínculo bilateral do recibo

```text
FK COMPOSTA (attempt_id, step_id, schedule_id)     -> handoff_attempts
FK COMPOSTA (connection_id, control_principal_ref) -> connection_profiles
UNIQUE (attempt_id)
TWO_VALID_REFERENCES != ONE_COHERENT_REFERENCE
COERÊNCIA SOBREVIVE FORA DOS SERVIÇOS
```

A FK da Attempt é `DEFERRABLE INITIALLY DEFERRED` pelo mesmo motivo de
`fk_service_delegations_consumed_attempt`: o recibo é escrito na mesma
transação da Attempt, e uma FK imediata transformaria a ordem de escrita
em contrato implícito.

## Downgrade

Recusado com linhas em qualquer das nove tabelas. Perfil, recibo,
snapshot e alegação são história operacional; um rollback de schema não
apaga história.
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "b47e9c05d3fa"
down_revision: str | None = "a91d3f7c26be"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PROVIDER_FAMILIES = "connection_provider_families"
_MODEL_FAMILIES = "connection_model_families"
_MODEL_RELEASES = "connection_model_releases"
_ACCESS_PROVIDERS = "connection_access_providers"
_PROFILES = "connection_profiles"
_SNAPSHOTS = "connection_capability_snapshots"
_ENTITLEMENTS = "connection_entitlement_claims"
_EVIDENCE = "connection_evaluation_evidence"
_RECEIPTS = "connection_execution_receipts"

_ATTEMPTS = "handoff_attempts"

_ALL_TABLES = (
    _RECEIPTS,
    _EVIDENCE,
    _ENTITLEMENTS,
    _SNAPSHOTS,
    _PROFILES,
    _ACCESS_PROVIDERS,
    _MODEL_RELEASES,
    _MODEL_FAMILIES,
    _PROVIDER_FAMILIES,
)

_FUNCTION_APPEND_ONLY = "reject_connection_record_mutation"
_FUNCTION_ENTITLEMENT_GUARD = "guard_connection_entitlement_transition"

_APPEND_ONLY = (
    (_SNAPSHOTS, "trg_capability_snapshots_append_only", "trg_capability_snapshots_no_truncate"),
    (_EVIDENCE, "trg_evaluation_evidence_append_only", "trg_evaluation_evidence_no_truncate"),
    (_RECEIPTS, "trg_connection_receipts_append_only", "trg_connection_receipts_no_truncate"),
)

_METHODS = (
    "manual_handoff",
    "provider_native_mcp_inbound",
    "direct_provider_api",
    "provider_native_agent_bridge",
    "enterprise_gateway_or_broker",
    "local_model_adapter",
    "browser_assisted_handoff",
    "watched_inbox_outbox",
)
_STATES = (
    "declared",
    "preflight_required",
    "implemented_pending_audit",
    "available",
    "degraded",
    "revoked",
    "unsupported",
)
_ATTESTATIONS = ("attested", "self_declared", "unknown")
_CAPABILITY_SOURCES = ("official_discovery", "user_declared_endpoint", "execution_observed")
_ENDPOINT_TYPES = (
    "generic_mcp_server",
    "openai_compatible_endpoint",
    "anthropic_compatible_endpoint",
    "local_inference_endpoint",
    "attributed_multi_model_gateway",
    "opaque_multi_model_aggregator",
    "external_evaluation_source",
    "scientific_evidence_source",
    "tool_or_application_integration",
)
_ENTITLEMENT_ORIGINS = ("user_declared", "officially_discovered")
_ENTITLEMENT_STATES = ("active", "superseded", "expired", "revoked", "not_confirmed")
_EVIDENCE_CATEGORIES = (
    "external_evaluation",
    "scientific_reference",
    "operator_announcement",
)

_TERMINAL_SQL = "('revoked', 'unsupported')"


def _json_type() -> sa.types.TypeEngine[object]:
    return sa.JSON().with_variant(sa.dialects.postgresql.JSONB(astext_type=sa.Text()), "postgresql")


def _timestamps() -> list[sa.Column[object]]:
    """`server_default=now()` — timestamps são mantidos PELO BANCO.

    Regra permanente do programa desde a E2: o ORM não os envia no
    `INSERT`, e toda migração precisa declarar o `server_default`.
    """
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

    # --- curadoria ----------------------------------------------------------
    op.create_table(
        _PROVIDER_FAMILIES,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(length=128), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_connection_provider_families_slug"),
        sa.CheckConstraint(
            "length(btrim(slug)) > 0", name="ck_connection_provider_families_slug_not_blank"
        ),
        sa.CheckConstraint(
            "length(btrim(display_name)) > 0",
            name="ck_connection_provider_families_display_name_not_blank",
        ),
    )

    op.create_table(
        _MODEL_FAMILIES,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider_family_id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(length=128), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["provider_family_id"],
            [f"{_PROVIDER_FAMILIES}.id"],
            name="fk_connection_model_families_provider",
        ),
        sa.UniqueConstraint(
            "provider_family_id", "slug", name="uq_connection_model_families_family_slug"
        ),
        sa.CheckConstraint(
            "length(btrim(slug)) > 0", name="ck_connection_model_families_slug_not_blank"
        ),
    )
    op.create_index(
        "ix_connection_model_families_provider", _MODEL_FAMILIES, ["provider_family_id"]
    )

    op.create_table(
        _MODEL_RELEASES,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("model_family_id", sa.Uuid(), nullable=False),
        sa.Column("provider_release_id", sa.String(length=255), nullable=False),
        sa.Column("discovered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "discovery_source",
            sa.Enum(
                *_CAPABILITY_SOURCES,
                name="connection_capability_source",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["model_family_id"],
            [f"{_MODEL_FAMILIES}.id"],
            name="fk_connection_model_releases_family",
        ),
        sa.UniqueConstraint(
            "model_family_id",
            "provider_release_id",
            name="uq_connection_model_releases_family_release",
        ),
        sa.CheckConstraint(
            "length(btrim(provider_release_id)) > 0",
            name="ck_connection_model_releases_release_id_not_blank",
        ),
        sa.CheckConstraint(
            "valid_until > discovered_at", name="ck_connection_model_releases_ttl_positive"
        ),
    )
    op.create_index("ix_connection_model_releases_family", _MODEL_RELEASES, ["model_family_id"])

    op.create_table(
        _ACCESS_PROVIDERS,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(length=128), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column(
            "endpoint_type",
            sa.Enum(
                *_ENDPOINT_TYPES,
                name="connection_generic_endpoint_type",
                native_enum=False,
                length=40,
            ),
            nullable=False,
        ),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_connection_access_providers_slug"),
        sa.CheckConstraint(
            "length(btrim(slug)) > 0", name="ck_connection_access_providers_slug_not_blank"
        ),
    )

    # --- perfis -------------------------------------------------------------
    op.create_table(
        _PROFILES,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("control_principal_ref", sa.String(length=255), nullable=False),
        sa.Column(
            "method",
            sa.Enum(*_METHODS, name="connection_method", native_enum=False, length=40),
            nullable=False,
        ),
        sa.Column("endpoint_ref", sa.String(length=512), nullable=True),
        sa.Column("access_provider_id", sa.Uuid(), nullable=True),
        sa.Column(
            "state",
            sa.Enum(*_STATES, name="connection_state", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("credential_ref", sa.String(length=255), nullable=True),
        sa.Column("display_name", sa.String(length=255), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id", "control_principal_ref", name="uq_connection_profiles_id_principal"
        ),
        sa.ForeignKeyConstraint(
            ["access_provider_id"],
            [f"{_ACCESS_PROVIDERS}.id"],
            name="fk_connection_profiles_access_provider",
        ),
        sa.CheckConstraint(
            "length(btrim(control_principal_ref)) > 0",
            name="ck_connection_profiles_principal_not_blank",
        ),
        sa.CheckConstraint(
            "NOT (method = 'manual_handoff' AND endpoint_ref IS NOT NULL)",
            name="ck_connection_profiles_manual_has_no_endpoint",
        ),
        sa.CheckConstraint(
            "state <> 'available' OR method = 'manual_handoff'",
            name="ck_connection_profiles_available_method",
        ),
        sa.CheckConstraint(
            "method IN ('manual_handoff', 'provider_native_mcp_inbound', "
            "'direct_provider_api', 'provider_native_agent_bridge', "
            "'enterprise_gateway_or_broker', 'local_model_adapter', "
            "'browser_assisted_handoff', 'watched_inbox_outbox')",
            name="ck_connection_profiles_method_vocabulary",
        ),
        sa.CheckConstraint(
            "state IN ('declared', 'preflight_required', 'implemented_pending_audit', "
            "'available', 'degraded', 'revoked', 'unsupported')",
            name="ck_connection_profiles_state_vocabulary",
        ),
    )
    op.create_index("ix_connection_profiles_principal", _PROFILES, ["control_principal_ref"])

    # --- capacidade ---------------------------------------------------------
    op.create_table(
        _SNAPSHOTS,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column("control_principal_ref", sa.String(length=255), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "source",
            sa.Enum(
                *_CAPABILITY_SOURCES,
                name="connection_capability_source",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("capabilities", _json_type(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(
            ["connection_id", "control_principal_ref"],
            [f"{_PROFILES}.id", f"{_PROFILES}.control_principal_ref"],
            name="fk_capability_snapshots_connection_within_principal",
        ),
        sa.UniqueConstraint(
            "connection_id", "observed_at", name="uq_capability_snapshots_connection_instant"
        ),
        sa.CheckConstraint(
            "valid_until > observed_at", name="ck_capability_snapshots_ttl_positive"
        ),
        sa.CheckConstraint(
            "length(btrim(control_principal_ref)) > 0",
            name="ck_capability_snapshots_principal_not_blank",
        ),
        sa.CheckConstraint(
            "source IN ('official_discovery', 'user_declared_endpoint', 'execution_observed')",
            name="ck_capability_snapshots_source_vocabulary",
        ),
    )
    op.create_index("ix_capability_snapshots_connection", _SNAPSHOTS, ["connection_id"])

    # --- entitlement --------------------------------------------------------
    op.create_table(
        _ENTITLEMENTS,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("control_principal_ref", sa.String(length=255), nullable=False),
        sa.Column("provider_family_id", sa.Uuid(), nullable=False),
        sa.Column("plan_ref", sa.String(length=128), nullable=False),
        sa.Column(
            "origin",
            sa.Enum(
                *_ENTITLEMENT_ORIGINS,
                name="connection_entitlement_origin",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "state",
            sa.Enum(
                *_ENTITLEMENT_STATES,
                name="connection_entitlement_state",
                native_enum=False,
                length=24,
            ),
            nullable=False,
        ),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("superseded_by_id", sa.Uuid(), nullable=True),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "id", "control_principal_ref", name="uq_entitlement_claims_id_principal"
        ),
        sa.UniqueConstraint("superseded_by_id", name="uq_entitlement_claims_single_antecedent"),
        sa.ForeignKeyConstraint(
            ["provider_family_id"],
            [f"{_PROVIDER_FAMILIES}.id"],
            name="fk_entitlement_claims_family",
        ),
        sa.CheckConstraint(
            "superseded_by_id IS NULL OR superseded_by_id <> id",
            name="ck_entitlement_claims_no_self_succession",
        ),
        sa.CheckConstraint(
            "(state = 'superseded') = (superseded_by_id IS NOT NULL)",
            name="ck_entitlement_claims_superseded_coherent",
        ),
        sa.CheckConstraint(
            "origin IN ('user_declared', 'officially_discovered')",
            name="ck_entitlement_claims_origin_vocabulary",
        ),
        sa.CheckConstraint(
            "state IN ('active', 'superseded', 'expired', 'revoked', 'not_confirmed')",
            name="ck_entitlement_claims_state_vocabulary",
        ),
        sa.CheckConstraint(
            "length(btrim(control_principal_ref)) > 0",
            name="ck_entitlement_claims_principal_not_blank",
        ),
    )
    op.create_index("ix_entitlement_claims_principal", _ENTITLEMENTS, ["control_principal_ref"])
    op.create_foreign_key(
        "fk_entitlement_claims_successor_within_principal",
        _ENTITLEMENTS,
        _ENTITLEMENTS,
        ["superseded_by_id", "control_principal_ref"],
        ["id", "control_principal_ref"],
    )

    # --- evidência externa --------------------------------------------------
    op.create_table(
        _EVIDENCE,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("source_slug", sa.String(length=128), nullable=False),
        sa.Column(
            "category",
            sa.Enum(
                *_EVIDENCE_CATEGORIES,
                name="connection_evidence_category",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("summary", _json_type(), nullable=False),
        sa.Column("is_authoritative", sa.Boolean(), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "source_slug", "category", "observed_at", name="uq_evaluation_evidence_identity"
        ),
        sa.CheckConstraint(
            "length(btrim(source_slug)) > 0", name="ck_evaluation_evidence_source_not_blank"
        ),
        sa.CheckConstraint(
            "category IN ('external_evaluation', 'scientific_reference', "
            "'operator_announcement')",
            name="ck_evaluation_evidence_category_vocabulary",
        ),
        sa.CheckConstraint(
            "is_authoritative = false", name="ck_evaluation_evidence_never_authoritative"
        ),
    )
    op.create_index("ix_evaluation_evidence_source", _EVIDENCE, ["source_slug"])

    # --- recibo de execução -------------------------------------------------
    op.create_table(
        _RECEIPTS,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("control_principal_ref", sa.String(length=255), nullable=False),
        sa.Column("schedule_id", sa.Uuid(), nullable=False),
        sa.Column("step_id", sa.Uuid(), nullable=False),
        sa.Column("attempt_id", sa.Uuid(), nullable=False),
        sa.Column("connection_id", sa.Uuid(), nullable=False),
        sa.Column(
            "connection_method",
            sa.Enum(*_METHODS, name="connection_method", native_enum=False, length=40),
            nullable=False,
        ),
        sa.Column("access_provider", sa.String(length=128), nullable=True),
        sa.Column("requested_model", sa.String(length=255), nullable=True),
        sa.Column("observed_model", sa.String(length=255), nullable=True),
        sa.Column(
            "model_attestation_level",
            sa.Enum(
                *_ATTESTATIONS,
                name="connection_model_attestation_level",
                native_enum=False,
                length=24,
            ),
            nullable=False,
        ),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        *_timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("attempt_id", name="uq_connection_execution_receipts_attempt"),
        sa.ForeignKeyConstraint(
            ["attempt_id", "step_id", "schedule_id"],
            [f"{_ATTEMPTS}.id", f"{_ATTEMPTS}.step_id", f"{_ATTEMPTS}.schedule_id"],
            name="fk_connection_execution_receipts_attempt",
            deferrable=True,
            initially="DEFERRED",
        ),
        sa.ForeignKeyConstraint(
            ["connection_id", "control_principal_ref"],
            [f"{_PROFILES}.id", f"{_PROFILES}.control_principal_ref"],
            name="fk_connection_execution_receipts_connection_within_principal",
        ),
        sa.CheckConstraint(
            "(model_attestation_level = 'attested') = (observed_model IS NOT NULL)",
            name="ck_connection_execution_receipts_attestation_bicondicional",
        ),
        sa.CheckConstraint(
            "length(btrim(control_principal_ref)) > 0",
            name="ck_connection_execution_receipts_principal_not_blank",
        ),
        sa.CheckConstraint(
            "connection_method IN ('manual_handoff', 'provider_native_mcp_inbound', "
            "'direct_provider_api', 'provider_native_agent_bridge', "
            "'enterprise_gateway_or_broker', 'local_model_adapter', "
            "'browser_assisted_handoff', 'watched_inbox_outbox')",
            name="ck_connection_execution_receipts_method_vocabulary",
        ),
        sa.CheckConstraint(
            "model_attestation_level IN ('attested', 'self_declared', 'unknown')",
            name="ck_connection_execution_receipts_attestation_vocabulary",
        ),
    )
    op.create_index("ix_connection_execution_receipts_connection", _RECEIPTS, ["connection_id"])
    op.create_index("ix_connection_execution_receipts_schedule", _RECEIPTS, ["schedule_id"])

    if not e_postgres:
        return

    # Índices parciais: expressão `WHERE` é PostgreSQL, e o metadata
    # precisa criar tabela em qualquer dialeto.
    op.execute(
        sa.text(
            f"""
            CREATE UNIQUE INDEX ix_connection_profiles_manual_singleton
            ON {_PROFILES} (control_principal_ref)
            WHERE method = 'manual_handoff' AND state NOT IN {_TERMINAL_SQL}
            """
        )
    )
    op.execute(
        sa.text(
            f"""
            CREATE UNIQUE INDEX ix_connection_profiles_non_terminal_triple
            ON {_PROFILES} (control_principal_ref, method, endpoint_ref)
            WHERE state NOT IN {_TERMINAL_SQL}
            """
        )
    )

    # --- append-only --------------------------------------------------------
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

    # --- ciclo de vida monotônico do entitlement ----------------------------
    #
    # ```text
    # IMMUTABLE_PAYLOAD + MONOTONIC_LIFECYCLE
    # ACTIVE -> SUPERSEDED
    # ```
    #
    # Não é append-only, e por isso não recebe o trigger acima: o estado
    # avança. Não ser append-only não é ser descartável — DELETE e
    # TRUNCATE são recusados, o payload é imutável, o terminal não volta,
    # e o sucessor precisa ser do mesmo principal.
    op.execute(
        sa.text(
            f"""
            CREATE OR REPLACE FUNCTION {_FUNCTION_ENTITLEMENT_GUARD}()
            RETURNS TRIGGER
            LANGUAGE plpgsql
            SET search_path = pg_catalog
            AS $$
            BEGIN
                IF TG_OP IN ('DELETE', 'TRUNCATE') THEN
                    RAISE EXCEPTION
                        'connection_entitlement_claims is not deletable: % rejected', TG_OP
                        USING ERRCODE = 'raise_exception';
                END IF;

                IF OLD.state <> 'active' THEN
                    RAISE EXCEPTION
                        'entitlement claim is terminal (%): transition to % rejected',
                        OLD.state, NEW.state
                        USING ERRCODE = 'raise_exception';
                END IF;
                IF NEW.state <> 'superseded' THEN
                    RAISE EXCEPTION
                        'entitlement transition active -> % is not implemented', NEW.state
                        USING ERRCODE = 'raise_exception';
                END IF;

                IF NEW.id <> OLD.id
                   OR NEW.control_principal_ref <> OLD.control_principal_ref
                   OR NEW.provider_family_id <> OLD.provider_family_id
                   OR NEW.plan_ref <> OLD.plan_ref
                   OR NEW.origin <> OLD.origin
                   OR NEW.claimed_at <> OLD.claimed_at
                   OR NEW.created_at <> OLD.created_at THEN
                    RAISE EXCEPTION
                        'entitlement payload and origin are immutable'
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
            f"CREATE TRIGGER trg_entitlement_claims_lifecycle "
            f"BEFORE UPDATE OR DELETE ON {_ENTITLEMENTS} "
            f"FOR EACH ROW EXECUTE FUNCTION {_FUNCTION_ENTITLEMENT_GUARD}();"
        )
    )
    op.execute(
        sa.text(
            f"CREATE TRIGGER trg_entitlement_claims_no_truncate "
            f"BEFORE TRUNCATE ON {_ENTITLEMENTS} "
            f"FOR EACH STATEMENT EXECUTE FUNCTION {_FUNCTION_APPEND_ONLY}();"
        )
    )


def downgrade() -> None:
    connection = op.get_bind()
    for tabela in _ALL_TABLES:
        linhas = connection.execute(sa.text(f"SELECT count(*) FROM {tabela}")).scalar_one()
        if linhas:
            raise RuntimeError(
                f"downgrade recusado: {linhas} linha(s) em {tabela}; perfil de conexão, "
                "recibo de execução, snapshot de capacidade e alegação de entitlement são "
                "história operacional e não podem ser apagados por um rollback de schema"
            )

    if connection.dialect.name == "postgresql":
        op.execute(
            sa.text(f"DROP TRIGGER IF EXISTS trg_entitlement_claims_no_truncate ON {_ENTITLEMENTS}")
        )
        op.execute(
            sa.text(f"DROP TRIGGER IF EXISTS trg_entitlement_claims_lifecycle ON {_ENTITLEMENTS}")
        )
        op.execute(sa.text(f"DROP FUNCTION IF EXISTS {_FUNCTION_ENTITLEMENT_GUARD}()"))
        for tabela, trigger_linha, trigger_truncate in _APPEND_ONLY:
            op.execute(sa.text(f"DROP TRIGGER IF EXISTS {trigger_truncate} ON {tabela}"))
            op.execute(sa.text(f"DROP TRIGGER IF EXISTS {trigger_linha} ON {tabela}"))
        op.execute(sa.text(f"DROP FUNCTION IF EXISTS {_FUNCTION_APPEND_ONLY}()"))
        op.execute(sa.text("DROP INDEX IF EXISTS ix_connection_profiles_non_terminal_triple"))
        op.execute(sa.text("DROP INDEX IF EXISTS ix_connection_profiles_manual_singleton"))

    op.drop_index("ix_connection_execution_receipts_schedule", table_name=_RECEIPTS)
    op.drop_index("ix_connection_execution_receipts_connection", table_name=_RECEIPTS)
    op.drop_table(_RECEIPTS)
    op.drop_index("ix_evaluation_evidence_source", table_name=_EVIDENCE)
    op.drop_table(_EVIDENCE)
    op.drop_constraint(
        "fk_entitlement_claims_successor_within_principal", _ENTITLEMENTS, type_="foreignkey"
    )
    op.drop_index("ix_entitlement_claims_principal", table_name=_ENTITLEMENTS)
    op.drop_table(_ENTITLEMENTS)
    op.drop_index("ix_capability_snapshots_connection", table_name=_SNAPSHOTS)
    op.drop_table(_SNAPSHOTS)
    op.drop_index("ix_connection_profiles_principal", table_name=_PROFILES)
    op.drop_table(_PROFILES)
    op.drop_table(_ACCESS_PROVIDERS)
    op.drop_index("ix_connection_model_releases_family", table_name=_MODEL_RELEASES)
    op.drop_table(_MODEL_RELEASES)
    op.drop_index("ix_connection_model_families_provider", table_name=_MODEL_FAMILIES)
    op.drop_table(_MODEL_FAMILIES)
    op.drop_table(_PROVIDER_FAMILIES)
