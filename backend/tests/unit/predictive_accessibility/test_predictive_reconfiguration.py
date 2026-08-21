"""Contratos de E5.l antes da integração PostgreSQL."""

import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from app.predictive_accessibility.channel import PredictiveChannel, PredictiveChannelRegistry
from app.predictive_accessibility.claim import predictive_claim_from_envelope
from app.predictive_accessibility.epistemic import (
    PredictiveClaimEvaluationResult,
    PredictiveEpistemicState,
    PredictiveProvenance,
)
from app.predictive_accessibility.errors.exceptions import (
    PredictiveReconfigurationEventIdentityMismatchError,
    PredictiveReconfigurationEventImmutableError,
)
from app.predictive_accessibility.history import (
    PredictiveHistoricalValidity,
    PredictiveObservation,
)
from app.predictive_accessibility.horizon import (
    PredictiveHorizonPoint,
    PredictiveHorizonSpectrum,
)
from app.predictive_accessibility.piap.authority import (
    ApprovalBinding,
    AuthorityContext,
    BoundObjectRef,
)
from app.predictive_accessibility.piap.enums import (
    ApprovalValidationOutcome,
    AuthorityStatus,
    BoundObjectKind,
    PiapContractVersion,
    TemporalAvailability,
)
from app.predictive_accessibility.piap.envelope import (
    ClaimSubject,
    Horizon,
    PiapEnvelope,
    ProvenanceKind,
    ProvenanceRecord,
    SourceReference,
)
from app.predictive_accessibility.power import PredictivePowerOutcome
from app.predictive_accessibility.reconfiguration import (
    PredictiveReconfigurationAppendResult,
    PredictiveReconfigurationCandidate,
    PredictiveReconfigurationDecision,
    PredictiveReconfigurationEvent,
    PredictiveReconfigurationEventKind,
    PredictiveRollbackRequest,
    predictive_reconfiguration_gate,
    predictive_rollback_gate,
)
from app.predictive_accessibility.regime import (
    PredictiveRegimeAssessment,
    PredictiveRegimeStatus,
)
from app.predictive_accessibility.repositories.reconfiguration_repository import (
    PredictiveReconfigurationRepository,
)

pytestmark = pytest.mark.unit

_T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _source(seq: int = 1) -> SourceReference:
    return SourceReference(
        kind=ProvenanceKind("policy.registry"),
        ref=uuid.UUID(int=seq),
        source_version=1,
        content_sha256="a" * 64,
    )


def _envelope(candidate_ref: uuid.UUID) -> PiapEnvelope:
    return PiapEnvelope(
        contract_version=PiapContractVersion.V1_0,
        subject=ClaimSubject(
            target="grid.load",
            signal="demand.peak",
            horizon=Horizon(
                delta=timedelta(hours=1),
                reference_time=_T0,
                availability=TemporalAvailability.AVAILABLE_AT_REFERENCE_TIME,
            ),
        ),
        provenance=ProvenanceRecord(
            origin=_source(), recorded_at=_T0, jurisdiction="br", policy_ref="policy"
        ),
        authority=AuthorityContext(
            status=AuthorityStatus.ASSERTED_AUTHORIZED,
            approval=ApprovalBinding(
                approval_reference="APR-1",
                approval_version=1,
                approval_scope=("predictive.promote",),
                approval_expiry=datetime(2027, 1, 1, tzinfo=UTC),
                approval_jurisdiction="br",
                bound_to=BoundObjectRef(
                    kind=BoundObjectKind.PROMOTION_CANDIDATE,
                    ref=candidate_ref,
                ),
            ),
        ),
        payload_refs=(_source(),),
        sealed_at=_T0,
    )


def _evaluation(envelope: PiapEnvelope) -> PredictiveClaimEvaluationResult:
    observation = PredictiveObservation("obs", "source", 0.9)
    history = PredictiveHistoricalValidity((observation,), (), 0.5)
    regime = PredictiveRegimeAssessment(
        PredictiveRegimeStatus.REGIME_SHIFT_CANDIDATE,
        d_regime=0.9,
        theta=0.5,
        beats_fluctuation=True,
        high_prediction_error=True,
        model_disagreement=False,
    )
    horizon_point = PredictiveHorizonPoint(1, 0.4, True, PredictiveRegimeStatus.NO_SHIFT)
    horizon = PredictiveHorizonSpectrum((horizon_point,), (horizon_point,), ())
    evidence = PredictivePowerOutcome(0.4, 0.7, 0.7, 0.5, 0.001, 0.5, 0.0, 100, 0.01)
    return PredictiveClaimEvaluationResult(
        claim=predictive_claim_from_envelope(envelope),
        provenance=PredictiveProvenance(
            PredictiveChannelRegistry(
                (PredictiveChannel("lag_1", 1),),
                ("gaussian_marginal_baseline", "gaussian_ar1_ols"),
            ),
            0.02,
            history,
        ),
        regime=regime,
        evidence=evidence,
        uncertainty=(0.4, 0.7),
        horizon=horizon,
        state=PredictiveEpistemicState.PREDICTABLE,
        approval_validation_outcome=ApprovalValidationOutcome.VALID,
    )


def _candidate(evaluation: PredictiveClaimEvaluationResult, candidate_ref: uuid.UUID):
    return PredictiveReconfigurationCandidate(
        candidate_ref=candidate_ref,
        subject_key=evaluation.claim.subject_key,
        model_ref="model:v2",
        hypothesis_refs=("hypothesis:shift",),
        validation_ref="validation:blind:1",
        cost_ref="cost:1",
        responsible_ref="owner:1",
        rollback_plan_ref="rollback:1",
        candidate_payload_sha256="b" * 64,
        expected_version=0,
        proposed_version=1,
    )


class _FakeRepository:
    def __init__(self, current: PredictiveReconfigurationEvent | None = None) -> None:
        self.current_event = current
        self.current_calls = 0
        self.append_calls = 0

    def current(self, subject_key: str) -> PredictiveReconfigurationEvent | None:
        self.current_calls += 1
        return self.current_event

    def get(self, event_id: uuid.UUID) -> PredictiveReconfigurationEvent | None:
        if self.current_event is not None and self.current_event.event_id == event_id:
            return self.current_event
        return None

    def append(
        self, event: PredictiveReconfigurationEvent
    ) -> PredictiveReconfigurationAppendResult:
        self.append_calls += 1
        self.current_event = event
        return PredictiveReconfigurationAppendResult(
            PredictiveReconfigurationDecision.PROMOTED, event
        )


def test_e5l_promove_somente_com_regime_validacao_e_aprovacao() -> None:
    candidate_ref = uuid.uuid4()
    envelope = _envelope(candidate_ref)
    evaluation = _evaluation(envelope)
    repository = _FakeRepository()
    outcome = predictive_reconfiguration_gate(
        evaluation=evaluation,
        envelope=envelope,
        candidate=_candidate(evaluation, candidate_ref),
        event_id=uuid.uuid4(),
        recorded_at=_T0,
        repository=repository,
    )
    assert outcome.decision is PredictiveReconfigurationDecision.PROMOTED
    assert outcome.resulting_version == 1
    assert repository.append_calls == 1


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("approval", PredictiveReconfigurationDecision.REJECTED_APPROVAL),
        ("validation", PredictiveReconfigurationDecision.REJECTED_VALIDATION),
        ("regime", PredictiveReconfigurationDecision.NOT_APPLICABLE),
    ],
)
def test_e5l_ramos_negativos_fazem_zero_sql(mutation: str, expected) -> None:
    candidate_ref = uuid.uuid4()
    envelope = _envelope(candidate_ref)
    evaluation = _evaluation(envelope)
    candidate = _candidate(evaluation, candidate_ref)
    if mutation == "approval":
        evaluation = replace(
            evaluation, approval_validation_outcome=ApprovalValidationOutcome.EXPIRED
        )
    elif mutation == "validation":
        evaluation = replace(
            evaluation,
            evidence=replace(evaluation.evidence, a_minus=0.0),
            state=PredictiveEpistemicState.UNRESOLVED,
        )
    else:
        evaluation = replace(
            evaluation,
            regime=replace(evaluation.regime, status=PredictiveRegimeStatus.NO_SHIFT),
        )
    repository = _FakeRepository()
    outcome = predictive_reconfiguration_gate(
        evaluation=evaluation,
        envelope=envelope,
        candidate=candidate,
        event_id=uuid.uuid4(),
        recorded_at=_T0,
        repository=repository,
    )
    assert outcome.decision is expected
    assert repository.current_calls == 0
    assert repository.append_calls == 0


def test_e5l_reconcile_idempotente_e_conflito_divergente() -> None:
    candidate_ref = uuid.uuid4()
    evaluation = _evaluation(_envelope(candidate_ref))
    candidate = _candidate(evaluation, candidate_ref)
    repository = _FakeRepository()
    predictive_reconfiguration_gate(
        evaluation=evaluation,
        envelope=_envelope(candidate_ref),
        candidate=candidate,
        event_id=uuid.UUID(int=100),
        recorded_at=_T0,
        repository=repository,
    )
    event = repository.current_event
    assert event is not None
    assert PredictiveReconfigurationRepository._reconcile(event, event) is event
    values = {
        column.key: getattr(event, column.key)
        for column in PredictiveReconfigurationEvent.__table__.columns
    }
    values["candidate_payload_sha256"] = "c" * 64
    divergent = PredictiveReconfigurationEvent(**values)
    with pytest.raises(PredictiveReconfigurationEventIdentityMismatchError):
        PredictiveReconfigurationRepository._reconcile(event, divergent)


def test_e5l_repository_recusa_mutacao() -> None:
    repository = object.__new__(PredictiveReconfigurationRepository)
    with pytest.raises(PredictiveReconfigurationEventImmutableError):
        repository.update(object())
    with pytest.raises(PredictiveReconfigurationEventImmutableError):
        repository.delete(object())


def test_e5l_rollback_e_novo_evento_sem_alterar_o_alvo() -> None:
    candidate_ref = uuid.uuid4()
    first_envelope = _envelope(candidate_ref)
    evaluation = _evaluation(first_envelope)
    repository = _FakeRepository()
    first = predictive_reconfiguration_gate(
        evaluation=evaluation,
        envelope=first_envelope,
        candidate=_candidate(evaluation, candidate_ref),
        event_id=uuid.UUID(int=101),
        recorded_at=_T0,
        repository=repository,
    )
    target = repository.current_event
    assert first.decision is PredictiveReconfigurationDecision.PROMOTED
    assert target is not None

    approval = first_envelope.authority.approval
    assert approval is not None
    rollback_envelope = replace(
        first_envelope,
        authority=replace(
            first_envelope.authority,
            approval=replace(approval, approval_version=2),
        ),
    )
    outcome = predictive_rollback_gate(
        request=PredictiveRollbackRequest(
            event_id=uuid.UUID(int=102),
            subject_key=target.subject_key,
            rollback_of_event_id=target.event_id,
            expected_version=1,
            required_scope=("predictive.promote",),
            expected_jurisdiction="br",
            recorded_at=_T0 + timedelta(seconds=1),
        ),
        envelope=rollback_envelope,
        repository=repository,
    )
    rollback = repository.current_event
    assert outcome.decision is PredictiveReconfigurationDecision.PROMOTED
    assert rollback is not None
    assert rollback.event_kind is PredictiveReconfigurationEventKind.ROLLBACK
    assert rollback.rollback_of_event_id == target.event_id
    assert rollback.active_candidate_ref == target.active_candidate_ref
    assert target.to_version == 1


def test_e5l_rollback_revalida_escopo_em_vez_de_aceitar_status_pronto() -> None:
    candidate_ref = uuid.uuid4()
    envelope = _envelope(candidate_ref)
    evaluation = _evaluation(envelope)
    repository = _FakeRepository()
    predictive_reconfiguration_gate(
        evaluation=evaluation,
        envelope=envelope,
        candidate=_candidate(evaluation, candidate_ref),
        event_id=uuid.UUID(int=111),
        recorded_at=_T0,
        repository=repository,
    )
    target = repository.current_event
    approval = envelope.authority.approval
    assert target is not None and approval is not None
    rollback_envelope = replace(
        envelope,
        authority=replace(
            envelope.authority,
            approval=replace(approval, approval_version=2),
        ),
    )

    outcome = predictive_rollback_gate(
        request=PredictiveRollbackRequest(
            event_id=uuid.UUID(int=112),
            subject_key=target.subject_key,
            rollback_of_event_id=target.event_id,
            expected_version=1,
            required_scope=("predictive.rollback",),
            expected_jurisdiction="br",
            recorded_at=_T0 + timedelta(seconds=1),
        ),
        envelope=rollback_envelope,
        repository=repository,
    )

    assert outcome.decision is PredictiveReconfigurationDecision.REJECTED_APPROVAL
    assert repository.append_calls == 1
