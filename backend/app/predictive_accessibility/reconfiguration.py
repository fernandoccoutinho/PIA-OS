"""`E5.l` — reconfiguração governada e log append-only próprio da E5."""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any, Protocol

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    event,
)
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, TypeDecorator, TypeEngine

from app.database.base import Base
from app.predictive_accessibility.epistemic import (
    PredictiveClaimEvaluationResult,
    PredictiveEpistemicState,
)
from app.predictive_accessibility.errors.exceptions import (
    PredictiveReconfigurationContractError,
)
from app.predictive_accessibility.piap.authority import BoundObjectRef, validate_approval
from app.predictive_accessibility.piap.enums import (
    ApprovalValidationOutcome,
    BoundObjectKind,
)
from app.predictive_accessibility.piap.envelope import PiapEnvelope
from app.predictive_accessibility.regime import PredictiveRegimeStatus

_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class PredictiveReconfigurationEventKind(StrEnum):
    PROMOTE = "PROMOTE"
    ROLLBACK = "ROLLBACK"


class PredictiveReconfigurationDecision(StrEnum):
    PROMOTED = "promoted"
    REPLAYED = "replayed"
    LOST_CONCURRENT_RACE = "lost_concurrent_race"
    NOT_APPLICABLE = "not_applicable"
    REJECTED_APPROVAL = "rejected_approval"
    REJECTED_VALIDATION = "rejected_validation"


@dataclass(frozen=True)
class PredictiveReconfigurationCandidate:
    candidate_ref: uuid.UUID
    subject_key: str
    model_ref: str
    hypothesis_refs: tuple[str, ...]
    validation_ref: str
    cost_ref: str
    responsible_ref: str
    rollback_plan_ref: str
    candidate_payload_sha256: str
    expected_version: int
    proposed_version: int

    def __post_init__(self) -> None:
        text_fields = (
            self.model_ref,
            self.validation_ref,
            self.cost_ref,
            self.responsible_ref,
            self.rollback_plan_ref,
        )
        if any(not value.strip() for value in text_fields):
            raise ValueError("metadados do candidato não podem ser vazios")
        if not self.hypothesis_refs or any(not value.strip() for value in self.hypothesis_refs):
            raise ValueError("candidato exige referências de hipótese")
        if tuple(sorted(set(self.hypothesis_refs))) != self.hypothesis_refs:
            raise ValueError("hypothesis_refs deve ser canônica, ordenada e sem duplicatas")
        if not _SHA256.fullmatch(self.subject_key):
            raise ValueError("subject_key deve ser SHA-256 canônico")
        if not _SHA256.fullmatch(self.candidate_payload_sha256):
            raise ValueError("candidate_payload_sha256 deve ser SHA-256 canônico")
        if self.expected_version < 0 or self.proposed_version != self.expected_version + 1:
            raise ValueError("proposed_version deve ser expected_version + 1")


class PredictiveStringTupleType(TypeDecorator[tuple[str, ...]]):
    """Tupla canônica de textos persistida como JSON/JSONB."""

    impl = JSON
    cache_ok = True

    def load_dialect_impl(self, dialect: Dialect) -> TypeEngine[Any]:
        if dialect.name == "postgresql":
            return dialect.type_descriptor(JSONB())  # type: ignore[no-untyped-call]
        return dialect.type_descriptor(JSON())

    def process_bind_param(self, value: tuple[str, ...] | None, dialect: Dialect) -> list[str]:
        if value is None or not isinstance(value, tuple):
            raise TypeError("valor deve ser tuple[str, ...]")
        if any(not isinstance(item, str) or not item.strip() for item in value):
            raise ValueError("tupla contém texto inválido")
        if tuple(sorted(set(value))) != value:
            raise ValueError("tupla deve ser canônica, ordenada e sem duplicatas")
        return list(value)

    def process_result_value(self, value: object, dialect: Dialect) -> tuple[str, ...]:
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            raise TypeError("tupla persistida em formato inesperado")
        result = tuple(value)
        if tuple(sorted(set(result))) != result:
            raise ValueError("tupla persistida não é canônica")
        return result


class PredictiveReconfigurationEvent(Base):
    """Evento imutável de promoção ou rollback."""

    __tablename__ = "predictive_reconfiguration_events"
    __table_args__ = (
        UniqueConstraint(
            "subject_key",
            "to_version",
            name="uq_predictive_reconfiguration_subject_version",
        ),
        CheckConstraint(
            "from_version >= 0 AND to_version >= 1 AND to_version = from_version + 1",
            name="ck_predictive_reconfiguration_version_step",
        ),
        CheckConstraint(
            "event_kind IN ('PROMOTE','ROLLBACK')",
            name="ck_predictive_reconfiguration_event_kind",
        ),
        CheckConstraint(
            "(event_kind='PROMOTE' AND rollback_of_event_id IS NULL) OR "
            "(event_kind='ROLLBACK' AND rollback_of_event_id IS NOT NULL)",
            name="ck_predictive_reconfiguration_rollback_binding",
        ),
        CheckConstraint(
            "length(subject_key)=64 AND length(candidate_payload_sha256)=64",
            name="ck_predictive_reconfiguration_hash_lengths",
        ),
        CheckConstraint(
            "approval_version >= 1",
            name="ck_predictive_reconfiguration_approval_version",
        ),
        CheckConstraint(
            "approval_bound_kind = 'promotion_candidate'",
            name="ck_predictive_reconfiguration_approval_bound_kind",
        ),
        Index(
            "ix_predictive_reconfiguration_current",
            "subject_key",
            "to_version",
        ),
    )

    event_id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    subject_key: Mapped[str] = mapped_column(String(64), nullable=False)
    event_kind: Mapped[PredictiveReconfigurationEventKind] = mapped_column(
        SAEnum(
            PredictiveReconfigurationEventKind,
            name="predictive_reconfiguration_event_kind",
            native_enum=False,
            length=16,
            values_callable=lambda cls: [member.value for member in cls],
        ),
        nullable=False,
    )
    from_version: Mapped[int] = mapped_column(Integer, nullable=False)
    to_version: Mapped[int] = mapped_column(Integer, nullable=False)
    active_candidate_ref: Mapped[uuid.UUID] = mapped_column(nullable=False)
    candidate_payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    model_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    hypothesis_refs: Mapped[tuple[str, ...]] = mapped_column(
        PredictiveStringTupleType(), nullable=False
    )
    validation_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    cost_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    responsible_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    rollback_plan_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    approval_reference: Mapped[str] = mapped_column(String(255), nullable=False)
    approval_version: Mapped[int] = mapped_column(Integer, nullable=False)
    approval_scope: Mapped[tuple[str, ...]] = mapped_column(
        PredictiveStringTupleType(), nullable=False
    )
    approval_jurisdiction: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approval_bound_kind: Mapped[str] = mapped_column(String(64), nullable=False)
    approval_bound_ref: Mapped[uuid.UUID] = mapped_column(nullable=False)
    rollback_of_event_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey(
            "predictive_reconfiguration_events.event_id",
            name="fk_predictive_reconfiguration_rollback_event",
        ),
        nullable=True,
    )
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


@event.listens_for(PredictiveReconfigurationEvent, "before_update")
def _reject_predictive_reconfiguration_update(
    mapper: object, connection: object, target: PredictiveReconfigurationEvent
) -> None:
    """Camada ORM da garantia append-only."""
    from app.predictive_accessibility.errors.exceptions import (
        PredictiveReconfigurationEventImmutableError,
    )

    raise PredictiveReconfigurationEventImmutableError("update")


@event.listens_for(PredictiveReconfigurationEvent, "before_delete")
def _reject_predictive_reconfiguration_delete(
    mapper: object, connection: object, target: PredictiveReconfigurationEvent
) -> None:
    """Camada ORM da garantia append-only."""
    from app.predictive_accessibility.errors.exceptions import (
        PredictiveReconfigurationEventImmutableError,
    )

    raise PredictiveReconfigurationEventImmutableError("delete")


@dataclass(frozen=True)
class PredictiveReconfigurationAppendResult:
    decision: PredictiveReconfigurationDecision
    event: PredictiveReconfigurationEvent | None


@dataclass(frozen=True)
class PredictiveEvaluatedReconfigurationOutcome:
    """Resultado E5.l do único ramo autorizado a consultar o log."""

    decision: PredictiveReconfigurationDecision
    event_id: uuid.UUID | None
    subject_key: str
    resulting_version: int | None
    reason: str


@dataclass(frozen=True)
class PredictiveCausalRejectedReconfigurationOutcome:
    """Resultado tipado do ramo causal; não transporta comando de escrita."""

    subject_key: str
    reason: str
    decision: PredictiveReconfigurationDecision = PredictiveReconfigurationDecision.NOT_APPLICABLE


@dataclass(frozen=True)
class PredictiveUpstreamUnavailableReconfigurationOutcome:
    """Resultado tipado do ramo upstream; não transporta comando de escrita."""

    source_reference: str
    reason: str
    decision: PredictiveReconfigurationDecision = PredictiveReconfigurationDecision.NOT_APPLICABLE


PredictiveReconfigurationOutcome = (
    PredictiveEvaluatedReconfigurationOutcome
    | PredictiveCausalRejectedReconfigurationOutcome
    | PredictiveUpstreamUnavailableReconfigurationOutcome
)


class PredictiveReconfigurationRepositoryPort(Protocol):
    def get(self, event_id: uuid.UUID) -> PredictiveReconfigurationEvent | None: ...

    def current(self, subject_key: str) -> PredictiveReconfigurationEvent | None: ...

    def append(
        self, event: PredictiveReconfigurationEvent
    ) -> PredictiveReconfigurationAppendResult: ...


def predictive_reconfiguration_gate(
    *,
    evaluation: PredictiveClaimEvaluationResult,
    envelope: PiapEnvelope,
    candidate: PredictiveReconfigurationCandidate,
    event_id: uuid.UUID,
    recorded_at: datetime,
    repository: PredictiveReconfigurationRepositoryPort,
) -> PredictiveEvaluatedReconfigurationOutcome:
    """Promove somente candidato cego, potente e validamente aprovado."""
    if candidate.subject_key != evaluation.claim.subject_key:
        raise PredictiveReconfigurationContractError("candidate subject diverge da alegação")
    if evaluation.regime.status is not PredictiveRegimeStatus.REGIME_SHIFT_CANDIDATE:
        return PredictiveEvaluatedReconfigurationOutcome(
            PredictiveReconfigurationDecision.NOT_APPLICABLE,
            None,
            candidate.subject_key,
            None,
            "mudança de regime não é candidata",
        )
    if (
        evaluation.evidence.a_minus <= 0.0
        or evaluation.state is not PredictiveEpistemicState.PREDICTABLE
    ):
        return PredictiveEvaluatedReconfigurationOutcome(
            PredictiveReconfigurationDecision.REJECTED_VALIDATION,
            None,
            candidate.subject_key,
            None,
            "avaliação cega não demonstrou ganho previsível",
        )
    approval = envelope.authority.approval
    valid_binding = (
        evaluation.approval_validation_outcome is ApprovalValidationOutcome.VALID
        and approval is not None
        and approval.bound_to.kind is BoundObjectKind.PROMOTION_CANDIDATE
        and approval.bound_to.ref == candidate.candidate_ref
        and approval.approval_version == candidate.proposed_version
    )
    if not valid_binding:
        return PredictiveEvaluatedReconfigurationOutcome(
            PredictiveReconfigurationDecision.REJECTED_APPROVAL,
            None,
            candidate.subject_key,
            None,
            "aprovação ausente, inválida ou vinculada a outro candidato/versão",
        )
    current = repository.current(candidate.subject_key)
    actual_version = current.to_version if current is not None else 0
    if actual_version != candidate.expected_version:
        return PredictiveEvaluatedReconfigurationOutcome(
            PredictiveReconfigurationDecision.LOST_CONCURRENT_RACE,
            current.event_id if current is not None else None,
            candidate.subject_key,
            actual_version,
            "expected_version não é a versão corrente",
        )
    assert approval is not None
    event = PredictiveReconfigurationEvent(
        event_id=event_id,
        subject_key=candidate.subject_key,
        event_kind=PredictiveReconfigurationEventKind.PROMOTE,
        from_version=candidate.expected_version,
        to_version=candidate.proposed_version,
        active_candidate_ref=candidate.candidate_ref,
        candidate_payload_sha256=candidate.candidate_payload_sha256,
        model_ref=candidate.model_ref,
        hypothesis_refs=candidate.hypothesis_refs,
        validation_ref=candidate.validation_ref,
        cost_ref=candidate.cost_ref,
        responsible_ref=candidate.responsible_ref,
        rollback_plan_ref=candidate.rollback_plan_ref,
        approval_reference=approval.approval_reference,
        approval_version=approval.approval_version,
        approval_scope=approval.approval_scope,
        approval_jurisdiction=approval.approval_jurisdiction,
        approval_bound_kind=approval.bound_to.kind.value,
        approval_bound_ref=approval.bound_to.ref,
        rollback_of_event_id=None,
        recorded_at=recorded_at,
    )
    appended = repository.append(event)
    persisted = appended.event
    return PredictiveEvaluatedReconfigurationOutcome(
        appended.decision,
        persisted.event_id if persisted is not None else None,
        candidate.subject_key,
        persisted.to_version if persisted is not None else actual_version,
        "evento persistido" if persisted is not None else "corrida concorrente perdida",
    )


@dataclass(frozen=True)
class PredictiveRollbackRequest:
    """Rollback como novo evento; nunca UPDATE do evento anterior."""

    event_id: uuid.UUID
    subject_key: str
    rollback_of_event_id: uuid.UUID
    expected_version: int
    required_scope: tuple[str, ...]
    expected_jurisdiction: str | None
    recorded_at: datetime


def predictive_rollback_gate(
    *,
    request: PredictiveRollbackRequest,
    envelope: PiapEnvelope,
    repository: PredictiveReconfigurationRepositoryPort,
) -> PredictiveEvaluatedReconfigurationOutcome:
    """Reativa candidato histórico por um novo evento auditável."""
    approval = envelope.authority.approval
    target = repository.get(request.rollback_of_event_id)
    approval_outcome = (
        validate_approval(
            envelope.authority,
            at=request.recorded_at,
            expected_version=request.expected_version + 1,
            required_scope=request.required_scope,
            expected_jurisdiction=request.expected_jurisdiction,
            expected_binding=BoundObjectRef(
                BoundObjectKind.PROMOTION_CANDIDATE,
                target.active_candidate_ref,
            ),
        )
        if target is not None
        else ApprovalValidationOutcome.BINDING_MISMATCH
    )
    valid = (
        approval_outcome is ApprovalValidationOutcome.VALID
        and approval is not None
        and target is not None
        and target.subject_key == request.subject_key
        and approval.bound_to.kind is BoundObjectKind.PROMOTION_CANDIDATE
        and approval.bound_to.ref == target.active_candidate_ref
        and approval.approval_version == request.expected_version + 1
    )
    if not valid:
        return PredictiveEvaluatedReconfigurationOutcome(
            PredictiveReconfigurationDecision.REJECTED_APPROVAL,
            None,
            request.subject_key,
            None,
            "rollback sem alvo compatível e aprovação válida",
        )
    current = repository.current(request.subject_key)
    actual_version = current.to_version if current is not None else 0
    if actual_version != request.expected_version:
        return PredictiveEvaluatedReconfigurationOutcome(
            PredictiveReconfigurationDecision.LOST_CONCURRENT_RACE,
            current.event_id if current is not None else None,
            request.subject_key,
            actual_version,
            "expected_version não é a versão corrente",
        )
    assert target is not None and approval is not None
    event = PredictiveReconfigurationEvent(
        event_id=request.event_id,
        subject_key=request.subject_key,
        event_kind=PredictiveReconfigurationEventKind.ROLLBACK,
        from_version=request.expected_version,
        to_version=request.expected_version + 1,
        active_candidate_ref=target.active_candidate_ref,
        candidate_payload_sha256=target.candidate_payload_sha256,
        model_ref=target.model_ref,
        hypothesis_refs=target.hypothesis_refs,
        validation_ref=target.validation_ref,
        cost_ref=target.cost_ref,
        responsible_ref=target.responsible_ref,
        rollback_plan_ref=target.rollback_plan_ref,
        approval_reference=approval.approval_reference,
        approval_version=approval.approval_version,
        approval_scope=approval.approval_scope,
        approval_jurisdiction=approval.approval_jurisdiction,
        approval_bound_kind=approval.bound_to.kind.value,
        approval_bound_ref=approval.bound_to.ref,
        rollback_of_event_id=target.event_id,
        recorded_at=request.recorded_at,
    )
    appended = repository.append(event)
    persisted = appended.event
    return PredictiveEvaluatedReconfigurationOutcome(
        appended.decision,
        persisted.event_id if persisted is not None else None,
        request.subject_key,
        persisted.to_version if persisted is not None else actual_version,
        "rollback registrado" if persisted is not None else "corrida concorrente perdida",
    )
