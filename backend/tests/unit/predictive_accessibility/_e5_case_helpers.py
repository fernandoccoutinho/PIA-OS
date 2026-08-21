"""Fábricas compartilhadas dos casos 14–45. Sem asserção: só construção."""

import uuid
from datetime import UTC, datetime, timedelta

from app.predictive_accessibility import coordinator as mod_coordinator
from app.predictive_accessibility.batch import (
    PredictiveEvaluationBatchResult,
    PredictiveGovernedQualityInput,
)
from app.predictive_accessibility.burden import (
    PredictiveBurdenDimension,
    PredictiveBurdenDimensionKind,
    PredictiveProbabilityValidation,
    PredictiveTotalBurdenVector,
)
from app.predictive_accessibility.channel import (
    PredictiveChannel,
    PredictiveChannelRegistry,
)
from app.predictive_accessibility.claim import PredictiveClaim
from app.predictive_accessibility.coordinator import PredictiveCoordinatedBatchResult
from app.predictive_accessibility.counterfactual import (
    PredictiveAlternative,
    PredictiveAlternativeKind,
    PredictiveCostKnowledge,
)
from app.predictive_accessibility.epistemic import (
    PredictiveClaimEvaluationResult,
    PredictiveEpistemicState,
    PredictiveProvenance,
)
from app.predictive_accessibility.guidance import PredictiveGuidanceReference
from app.predictive_accessibility.history import (
    PredictiveHistoricalValidity,
    PredictiveObservation,
)
from app.predictive_accessibility.horizon import (
    PredictiveHorizonPoint,
    predictive_horizon_spectrum,
)
from app.predictive_accessibility.piap.authority import ApprovalBinding, BoundObjectRef
from app.predictive_accessibility.piap.enums import (
    ApprovalValidationOutcome,
    BoundObjectKind,
)
from app.predictive_accessibility.power import PredictivePowerOutcome
from app.predictive_accessibility.predictive_claim_conflict import (
    PredictiveComparabilityKey,
)
from app.predictive_accessibility.protection import (
    PredictiveMaterialityAuthority,
    PredictiveProtectionCandidateInput,
)
from app.predictive_accessibility.reconfiguration import (
    PredictiveCausalRejectedReconfigurationOutcome,
    PredictiveEvaluatedReconfigurationOutcome,
    PredictiveReconfigurationDecision,
    PredictiveUpstreamUnavailableReconfigurationOutcome,
)
from app.predictive_accessibility.regime import (
    PredictiveRegimeStatus,
    predictive_regime_assessment,
)

T0 = datetime(2026, 1, 1, tzinfo=UTC)
AGORA = datetime(2026, 3, 1, tzinfo=UTC)
REGISTRY = PredictiveChannelRegistry(
    channels=(PredictiveChannel(name="lag_1", lag=1),),
    estimator_library=("gaussian_marginal_baseline", "gaussian_ar1_ols"),
)
CHAVE = PredictiveComparabilityKey(
    target="grid.load",
    population="br.sergipe",
    jurisdiction="br",
    horizon=1,
    regime="stable",
    unit="mw",
)
AUTORIDADE = PredictiveMaterialityAuthority(
    reference="AUT-1",
    authority="defesa civil",
    jurisdiction="br",
    version=1,
    scope=("bound.read",),
    valid_from=datetime(2026, 1, 1, tzinfo=UTC),
    valid_until=datetime(2027, 1, 1, tzinfo=UTC),
)
APROVACAO = ApprovalBinding(
    approval_reference="AUT-1",
    approval_version=1,
    approval_scope=("bound.read",),
    approval_expiry=datetime(2027, 1, 1, tzinfo=UTC),
    approval_jurisdiction="br",
    bound_to=BoundObjectRef(BoundObjectKind.PROPOSED_BOUND, uuid.UUID(int=1)),
)
ORIENTACAO = PredictiveGuidanceReference(
    reference="GUID-1",
    authority="defesa civil",
    provenance="policy.registry",
    jurisdiction="br",
    version=3,
    valid_from=datetime(2026, 1, 1, tzinfo=UTC),
    valid_until=datetime(2027, 1, 1, tzinfo=UTC),
)


def cer(
    *,
    state: PredictiveEpistemicState = PredictiveEpistemicState.PREDICTABLE,
    approval: ApprovalValidationOutcome = ApprovalValidationOutcome.VALID,
) -> PredictiveClaimEvaluationResult:
    a_minus = 0.5 if state is PredictiveEpistemicState.PREDICTABLE else -0.1
    evidencia = PredictivePowerOutcome(
        a_minus=a_minus,
        a_upper=a_minus + 0.4,
        a_star_worst=max(0.0, a_minus + 0.4),
        mean_gain=a_minus,
        placebo_p=0.0005,
        g_real=0.7,
        g_shuffled_p95=-0.1,
        sample_size=192,
        alpha_corrected=0.05 / 3,
    )
    return PredictiveClaimEvaluationResult(
        claim=PredictiveClaim(
            target="grid.load",
            signal="demand.peak",
            horizon=timedelta(hours=1),
            reference_time=T0,
        ),
        provenance=PredictiveProvenance(
            registry=REGISTRY,
            a_rel=0.02,
            historical_validity=PredictiveHistoricalValidity(
                valid_window=(
                    PredictiveObservation(reference="k1", provenance="p1", relevance_score=0.9),
                ),
                historical_kernel=(),
                rho_min=0.5,
            ),
        ),
        regime=predictive_regime_assessment(d_regime=0.1, theta=0.5, beats_fluctuation=False),
        evidence=evidencia,
        uncertainty=(evidencia.a_minus, evidencia.a_upper),
        horizon=predictive_horizon_spectrum(
            (PredictiveHorizonPoint(1, 0.4, True, PredictiveRegimeStatus.NO_SHIFT),)
        ),
        state=state,
        approval_validation_outcome=approval,
    )


def candidato(
    *,
    ident: str = "prot-1",
    material: bool = True,
    autoridade: PredictiveMaterialityAuthority | None = AUTORIDADE,
    completo: bool = True,
    incompativel_com: tuple[str, ...] = (),
) -> PredictiveProtectionCandidateInput:
    return PredictiveProtectionCandidateInput(
        identifier=ident,
        reason="reduz exposição da população",
        provenance="policy.registry",
        material_effect_claimed=material,
        authority=autoridade,
        owner="defesa civil" if completo else None,
        time_window="24h" if completo else None,
        reversibility="reversível" if completo else None,
        triggers=("regime muda",) if completo else (),
        incompatible_with=incompativel_com,
    )


def alternativas(*, a1_reversivel: bool = True) -> tuple[PredictiveAlternative, ...]:
    return (
        PredictiveAlternative(
            kind=PredictiveAlternativeKind.A0_INACTION,
            key=CHAVE,
            cost_knowledge=PredictiveCostKnowledge.UNKNOWN,
            cost_value=None,
            reversible=True,
            description="curso atual",
        ),
        PredictiveAlternative(
            kind=PredictiveAlternativeKind.A1_REVERSIBLE_ESCALATION,
            key=CHAVE,
            cost_knowledge=PredictiveCostKnowledge.KNOWN,
            cost_value=10.0,
            reversible=a1_reversivel,
            description="escalonada reversível",
        ),
        PredictiveAlternative(
            kind=PredictiveAlternativeKind.A2_FULL_ACTION,
            key=CHAVE,
            cost_knowledge=PredictiveCostKnowledge.KNOWN,
            cost_value=100.0,
            reversible=False,
            description="ação plena",
        ),
    )


def vetor(
    base: float,
    *,
    validacao: PredictiveProbabilityValidation = PredictiveProbabilityValidation.VALIDATED,
    vulneravel: bool = False,
    social: float | None = None,
    unidade_social: str | None = None,
) -> PredictiveTotalBurdenVector:
    return PredictiveTotalBurdenVector(
        dimensions=tuple(
            PredictiveBurdenDimension(
                kind=k,
                magnitude=(
                    social
                    if social is not None and k is PredictiveBurdenDimensionKind.SOCIAL_HUMAN
                    else base
                ),
                unit=(
                    unidade_social
                    if unidade_social is not None
                    and k is PredictiveBurdenDimensionKind.SOCIAL_HUMAN
                    else (
                        "brl" if k is PredictiveBurdenDimensionKind.FINANCIAL_RESOURCES else "index"
                    )
                ),
                source="policy.registry",
                source_version=3,
                observed_at="2026-01-01T00:00:00Z",
                uncertainty=(0.0, 1000.0),
                incidence="população vulnerável do litoral",
                vulnerable_incidence=vulneravel,
            )
            for k in PredictiveBurdenDimensionKind
        ),
        probability_validation=validacao,
    )


def entradas(a0: float = 3.0, a1: float = 1.0, a2: float = 5.0):
    return (
        (PredictiveAlternativeKind.A0_INACTION, vetor(a0)),
        (PredictiveAlternativeKind.A1_REVERSIBLE_ESCALATION, vetor(a1)),
        (PredictiveAlternativeKind.A2_FULL_ACTION, vetor(a2)),
    )


def governada(**kwargs) -> PredictiveGovernedQualityInput:
    padroes = {
        "conclusion_signature": "carga de pico acima do limiar",
        "comparability_key": CHAVE,
        "decisive_constraint": "janela de validade histórica",
        "protection_candidates": (candidato(),),
        "guidance": ORIENTACAO,
        "expected_guidance_jurisdiction": "br",
        "expected_guidance_version": 3,
        "alternatives": alternativas(),
        "burden_entries": entradas(),
        "materiality_required_scope": ("bound.read",),
        "required_protection_identifiers": ("prot-1",),
        "protection_inventory_reference": "PIAP-PROTECTION-INVENTORY-1",
        "asymmetry_justification": None,
    }
    padroes.update(kwargs)
    return PredictiveGovernedQualityInput(**padroes)


def sidecar_para(desfecho, *, promovido: bool = False):
    if isinstance(desfecho, PredictiveClaimEvaluationResult):
        return PredictiveEvaluatedReconfigurationOutcome(
            decision=(
                PredictiveReconfigurationDecision.PROMOTED
                if promovido
                else PredictiveReconfigurationDecision.NOT_APPLICABLE
            ),
            event_id=None,
            subject_key=desfecho.claim.subject_key,
            resulting_version=2 if promovido else None,
            reason="sidecar de teste",
        )
    if hasattr(desfecho, "source"):
        return PredictiveUpstreamUnavailableReconfigurationOutcome(
            source_reference=desfecho.source.reference, reason="indisponível"
        )
    return PredictiveCausalRejectedReconfigurationOutcome(
        subject_key=desfecho.claim.subject_key, reason="causal"
    )


def coordenado(desfechos: tuple, *, promovido: bool = False):
    return PredictiveCoordinatedBatchResult(
        evaluation=PredictiveEvaluationBatchResult(
            outcomes=desfechos, request_length=len(desfechos)
        ),
        reconfiguration=tuple(sidecar_para(d, promovido=promovido) for d in desfechos),
        approval_bindings=tuple(
            APROVACAO if isinstance(d, PredictiveClaimEvaluationResult) else None for d in desfechos
        ),
    )


def rotear(*, evaluation=None, governed=None, promovido: bool = False):
    desfecho = evaluation or cer()
    resultado = mod_coordinator.predictive_route_batch(
        coordenado((desfecho,), promovido=promovido),
        (governed or governada(),),
        at=AGORA,
    )
    return resultado.outcomes[0]
