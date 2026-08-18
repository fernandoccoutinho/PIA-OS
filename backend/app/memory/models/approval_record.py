"""
`ApprovalRecord` — existência durável e de uso único da aprovação destrutiva
(`E4.9.9.a`).

```text
APPROVAL_RECORD    != ERASURE_RECORD
PERSISTED_APPROVAL != AUTHENTICATED_USER
PERSISTED_APPROVAL != EXECUTION
CONSUMED_APPROVAL  != OBSERVED_ERASURE_ATTEMPT
```

## O que este modelo responde, e o que não responde

Responde: **quem** autorizou, **qual** operação, **qual** contexto e
finalidade, **qual** lote seguro foi apresentado, **qual** governança
fundamentou a decisão, **quando** foi emitida, confirmada e expira, e se
**ainda pode ser usada**.

Não responde se o efeito ocorreu. Isso é `ErasureRecord`, e continua sem
escritor de runtime.

## Três tabelas, e por quê

```text
approval_records                   a aprovação e seu binding escalar
approval_record_targets            o lote, ordenado, sem localizador
approval_record_governance_items   as seis tuplas da GovernanceResolution
```

A terceira é decisão autorizada e vale registrar o motivo. Reconstruir
`DestructiveApprovalProposal` exige a `GovernanceResolution` **exata** — o
construtor não aceita menos, e montá-la a partir de referências
significaria inventar treze campos. Ela tem **seis** campos de tupla
ordenada. Guardá-los em JSON reabriria a fronteira que a E4.9.6 fechou em
três corretivos; guardá-los em seis tabelas daria oito ao todo.

```text
JSON_STORAGE = FORBIDDEN
GOVERNANCE_ORDER = PRESERVED
APPROVAL_PERSISTENCE_TABLES = 3
```

## O que NUNCA entra em coluna alguma

```text
conteúdo do usuário · transient_locator · capacidade de deleção
credencial · token · segredo · biometria · material de step-up
comando em linguagem natural · pickle · asdict · __dict__
```

`principal_ref`, `purpose_ref` e `version_etag` são referências opacas já
validadas pelos contratos da E4.9.7/E4.9.8; entram porque o binding não
existe sem elas, e continuam redigidas em `repr`.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.memory.models.approval_enums import (
    AssuranceLevel,
    DestructiveOperation,
    ImpactVolumeKind,
    InputChannel,
    VoiceReviewState,
)
from app.memory.models.approval_lifecycle_enums import (
    ApprovalLifecycleState,
    GovernanceItemKind,
)
from app.memory.models.erasure_enums import ErasureTargetClass
from app.memory.models.governance_enums import (
    CognitiveOperation,
    CriticalCapability,
    GovernanceOutcome,
)
from app.memory.models.target_resolution_enums import (
    LegacyProtectionState,
    ReferenceOrigin,
)
from app.models.base_model import BaseModel

_TEXTO = 512


class ApprovalRecord(BaseModel):
    """A aprovação destrutiva, durável e de uso único.

    `id` é o `approval_id` do envelope — não um identificador paralelo.
    Dois identificadores para a mesma coisa divergiriam no primeiro
    caminho que esquecesse de propagar um deles.
    """

    __tablename__ = "approval_records"

    # --- identidade e ciclo de vida ------------------------------------
    nonce: Mapped[uuid.UUID] = mapped_column(Uuid(), nullable=False, unique=True)
    """Opaco e distinto de `id`, com unicidade **no banco**.

    ```text
    NONCE_PRESENT != CONSUMED
    ```

    A E4.9.8 exigia que fossem distintos em Python; aqui a distinção passa
    a valer contra SQL bruto, por `CHECK` e por índice único.
    """

    state: Mapped[ApprovalLifecycleState] = mapped_column(
        Enum(ApprovalLifecycleState, name="approval_lifecycle_state", native_enum=False, length=32),
        nullable=False,
        default=ApprovalLifecycleState.ACTIVE,
    )
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- operação e identidade declarada --------------------------------
    operation: Mapped[DestructiveOperation] = mapped_column(
        Enum(DestructiveOperation, name="destructive_operation", native_enum=False, length=64),
        nullable=False,
    )
    principal_ref: Mapped[str] = mapped_column(String(_TEXTO), nullable=False)
    assurance_level: Mapped[AssuranceLevel] = mapped_column(
        Enum(AssuranceLevel, name="assurance_level", native_enum=False, length=64), nullable=False
    )
    authenticated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # --- contexto e finalidade ------------------------------------------
    tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(), nullable=False)
    workspace_id: Mapped[uuid.UUID] = mapped_column(Uuid(), nullable=False)
    domain_id: Mapped[uuid.UUID] = mapped_column(Uuid(), nullable=False)
    purpose_ref: Mapped[str] = mapped_column(String(_TEXTO), nullable=False)

    # --- proveniência do canal ------------------------------------------
    channel: Mapped[InputChannel] = mapped_column(
        Enum(InputChannel, name="input_channel", native_enum=False, length=32), nullable=False
    )
    voice_review: Mapped[VoiceReviewState] = mapped_column(
        Enum(VoiceReviewState, name="voice_review_state", native_enum=False, length=64),
        nullable=False,
    )

    # --- impacto apresentado ---------------------------------------------
    impact_item_count: Mapped[int] = mapped_column(Integer(), nullable=False)
    impact_volume_kind: Mapped[ImpactVolumeKind] = mapped_column(
        Enum(ImpactVolumeKind, name="impact_volume_kind", native_enum=False, length=32),
        nullable=False,
    )
    impact_bytes_total: Mapped[int | None] = mapped_column(Integer(), nullable=True)

    # --- governança incorporada, campos escalares -------------------------
    governance_outcome: Mapped[GovernanceOutcome] = mapped_column(
        Enum(GovernanceOutcome, name="governance_outcome", native_enum=False, length=64),
        nullable=False,
    )
    governance_operation: Mapped[CognitiveOperation] = mapped_column(
        Enum(CognitiveOperation, name="cognitive_operation", native_enum=False, length=64),
        nullable=False,
    )
    governance_actor_ref: Mapped[str | None] = mapped_column(String(_TEXTO), nullable=True)
    governance_purpose: Mapped[str | None] = mapped_column(String(_TEXTO), nullable=True)
    governance_safety_boundary_version: Mapped[int] = mapped_column(Integer(), nullable=False)
    governance_safety_rationale: Mapped[str] = mapped_column(String(_TEXTO), nullable=False)
    governance_preserved_intent: Mapped[str | None] = mapped_column(String(_TEXTO), nullable=True)
    governance_policy_key: Mapped[str | None] = mapped_column(String(_TEXTO), nullable=True)
    governance_policy_version: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    governance_policy_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(), nullable=True)
    governance_matched_rule_id: Mapped[str | None] = mapped_column(String(_TEXTO), nullable=True)
    governance_policy_rationale: Mapped[str] = mapped_column(String(_TEXTO), nullable=False)

    # --- instantes do envelope e da proposta ------------------------------
    materialized_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        CheckConstraint("nonce <> id", name="ck_approval_records_nonce_distinct"),
        CheckConstraint(
            "impact_item_count >= 0", name="ck_approval_records_item_count_non_negative"
        ),
        CheckConstraint(
            "(impact_volume_kind = 'KNOWN' AND impact_bytes_total IS NOT NULL "
            "AND impact_bytes_total >= 0) OR "
            "(impact_volume_kind = 'UNKNOWN' AND impact_bytes_total IS NULL)",
            name="ck_approval_records_volume_coherent",
        ),
        # UNKNOWN_VOLUME != ZERO_VOLUME, agora também no banco.
        CheckConstraint(
            "materialized_at <= authenticated_at AND authenticated_at <= confirmed_at "
            "AND materialized_at <= issued_at AND issued_at <= confirmed_at "
            "AND confirmed_at < expires_at",
            name="ck_approval_records_temporal_order",
        ),
        CheckConstraint(
            "(state = 'ACTIVE' AND consumed_at IS NULL AND revoked_at IS NULL) OR "
            "(state = 'CONSUMED' AND consumed_at IS NOT NULL AND revoked_at IS NULL) OR "
            "(state = 'REVOKED' AND revoked_at IS NOT NULL AND consumed_at IS NULL)",
            name="ck_approval_records_state_timestamp_coherent",
        ),
        # Um estado sem o seu instante, ou com o instante do outro, seria um
        # estado impossível materializado.
        Index("ix_approval_records_state", "state"),
        Index("ix_approval_records_workspace", "tenant_id", "workspace_id"),
    )


class ApprovalRecordTarget(BaseModel):
    """Um `SafeTargetSnapshot` do lote aprovado, na posição confirmada.

    ```text
    LOCATOR_NEVER_PERSISTED
    ```

    Sem `transient_locator`, sem capacidade, sem `resolved_at` — as três
    exclusões que `SafeTargetSnapshot.from_descriptor` já faz em memória,
    aqui repetidas na tabela.

    **Sem FK para o objeto material.** `subject_coid` é identificador
    histórico, não chave estrangeira: uma FK faria o apagamento futuro do
    alvo destruir a prova de que ele foi aprovado.
    """

    __tablename__ = "approval_record_targets"

    approval_record_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("approval_records.id", ondelete="RESTRICT"), nullable=False
    )
    position: Mapped[int] = mapped_column(Integer(), nullable=False)
    """Ordem **confirmada**. A E4.9.8 estabeleceu que a ordem do lote faz
    parte do binding; uma coluna a preserva, um `set` a perderia."""

    target_class: Mapped[ErasureTargetClass] = mapped_column(
        Enum(ErasureTargetClass, name="erasure_target_class", native_enum=False, length=64),
        nullable=False,
    )
    subject_coid: Mapped[uuid.UUID] = mapped_column(Uuid(), nullable=False)
    control_workspace_id: Mapped[uuid.UUID] = mapped_column(Uuid(), nullable=False)
    control_tenant_id: Mapped[uuid.UUID] = mapped_column(Uuid(), nullable=False)
    control_principal_ref: Mapped[str] = mapped_column(String(_TEXTO), nullable=False)
    custody_provider: Mapped[str] = mapped_column(String(_TEXTO), nullable=False)
    custody_namespace: Mapped[str] = mapped_column(String(_TEXTO), nullable=False)
    origin_kind: Mapped[ReferenceOrigin] = mapped_column(
        Enum(ReferenceOrigin, name="reference_origin", native_enum=False, length=64), nullable=False
    )
    origin_position: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    legacy_protection_state: Mapped[LegacyProtectionState] = mapped_column(
        Enum(LegacyProtectionState, name="legacy_protection_state", native_enum=False, length=32),
        nullable=False,
    )
    """Obrigatório, sem default — o binding que a E4.9.8.3 fechou."""

    version_etag: Mapped[str | None] = mapped_column(String(_TEXTO), nullable=True)

    __table_args__ = (
        UniqueConstraint("approval_record_id", "position", name="uq_approval_targets_position"),
        UniqueConstraint("approval_record_id", "subject_coid", name="uq_approval_targets_subject"),
        CheckConstraint("position >= 0", name="ck_approval_targets_position_non_negative"),
        CheckConstraint(
            "origin_position IS NULL OR origin_position >= 0",
            name="ck_approval_targets_origin_position_non_negative",
        ),
        Index("ix_approval_targets_record", "approval_record_id"),
    )


class ApprovalRecordGovernanceItem(BaseModel):
    """Um elemento de uma das seis tuplas ordenadas da `GovernanceResolution`.

    Três colunas de valor **mutuamente exclusivas**, com `CHECK`
    condicionado ao `kind` — em vez de uma coluna textual polimórfica, que
    aceitaria um UUID malformado como texto e só falharia na reconstrução.

    ```text
    kind = DOMAIN_ID            -> value_uuid
    kind = BLOCKED_CAPABILITY   -> value_enum
    demais                      -> value_text
    ```
    """

    __tablename__ = "approval_record_governance_items"

    approval_record_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(), ForeignKey("approval_records.id", ondelete="RESTRICT"), nullable=False
    )
    kind: Mapped[GovernanceItemKind] = mapped_column(
        Enum(GovernanceItemKind, name="governance_item_kind", native_enum=False, length=64),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer(), nullable=False)
    value_uuid: Mapped[uuid.UUID | None] = mapped_column(Uuid(), nullable=True)
    value_enum: Mapped[CriticalCapability | None] = mapped_column(
        Enum(CriticalCapability, name="critical_capability", native_enum=False, length=128),
        nullable=True,
    )
    value_text: Mapped[str | None] = mapped_column(String(_TEXTO), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "approval_record_id", "kind", "position", name="uq_approval_gov_items_order"
        ),
        CheckConstraint("position >= 0", name="ck_approval_gov_items_position_non_negative"),
        CheckConstraint(
            "(kind = 'DOMAIN_ID' AND value_uuid IS NOT NULL "
            "AND value_enum IS NULL AND value_text IS NULL) OR "
            "(kind = 'BLOCKED_CAPABILITY' AND value_enum IS NOT NULL "
            "AND value_uuid IS NULL AND value_text IS NULL) OR "
            "(kind NOT IN ('DOMAIN_ID', 'BLOCKED_CAPABILITY') "
            "AND value_text IS NOT NULL AND value_uuid IS NULL AND value_enum IS NULL)",
            name="ck_approval_gov_items_value_matches_kind",
        ),
        Index("ix_approval_gov_items_record", "approval_record_id", "kind", "position"),
    )
