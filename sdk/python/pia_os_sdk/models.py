"""
Modelos públicos do `pia-os-sdk` — ARQUIVO GERADO, não editar à mão.

```text
OPENAPI_SNAPSHOT_SHA256 = 961d506c62fdd0acfbbfea2a3a06da547e5b0422a4b4b607ae3c6d60327bf58d
GENERATOR = tools/generate_models.py
HAND_EDIT = FORBIDDEN
```

Regenere com `python -m tools.generate_models` e verifique com
`--check`, que exige delta zero. Uma edição manual sobrevive até a
próxima regeneração e, nesse intervalo, o cliente aceita o que o
servidor recusa.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

OPENAPI_SNAPSHOT_SHA256 = "961d506c62fdd0acfbbfea2a3a06da547e5b0422a4b4b607ae3c6d60327bf58d"


class PiaModel(BaseModel):
    """Base dos modelos públicos.

    `extra="forbid"` espelha o servidor: um campo desconhecido é erro
    do cliente, e aceitá-lo em silêncio esconderia divergência de
    contrato até o servidor recusar a requisição.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)


class ComponentStatus(PiaModel):
    """Status de um componente individual verificado por `/status`."""

    healthy: bool
    name: str
    detail: str | None = None


class ErrorDetail(PiaModel):
    category: str
    code: str
    message: str
    path: str
    severity: str
    status_code: int
    correlation_id: str | None = None
    detail: object | None = None
    details: dict[str, object] | None = None
    request_id: str | None = None
    timestamp: str | None = None
    trace_id: str | None = None


class ErrorResponse(PiaModel):
    error: ErrorDetail
    success: bool = False


class HealthResponse(PiaModel):
    status: str = "ok"


class MetricsResponse(PiaModel):
    environment: str
    uptime_seconds: float


class PublicAlternative(PiaModel):
    cost_knowledge: PublicCostKnowledge
    description: str
    key: PublicComparabilityKey
    kind: PublicAlternativeKind
    reversible: bool
    cost_value: float | None = None


class PublicAlternativeKind(StrEnum):
    A0_INACTION = "a0_inaction"
    A1_REVERSIBLE_ESCALATION = "a1_reversible_escalation"
    A2_FULL_ACTION = "a2_full_action"


class PublicApprovalValidationOutcome(StrEnum):
    BINDING_MISMATCH = "binding_mismatch"
    EXPIRED = "expired"
    JURISDICTION_MISMATCH = "jurisdiction_mismatch"
    MISSING = "missing"
    NOT_AUTHORIZED = "not_authorized"
    OUT_OF_SCOPE = "out_of_scope"
    VALID = "valid"
    VERSION_MISMATCH = "version_mismatch"


class PublicAssertivenessView(PiaModel):
    """Master §16.14: conclusão, restrição, incerteza, autoridade, rota, gatilho."""

    authority_state: PublicAuthorityState
    candidate_conclusion: str
    decisive_constraint: str
    next_governed_route: str
    review_or_stop_trigger: str
    uncertainty: PublicUncertaintyView


class PublicAuthorityState(StrEnum):
    AUTHORIZED = "authorized"
    NOT_AUTHORIZED = "not_authorized"


class PublicBoundObjectKind(StrEnum):
    PROMOTION_CANDIDATE = "promotion_candidate"
    PROPOSED_BOUND = "proposed_bound"


class PublicBurdenDimension(PiaModel):
    incidence: str
    kind: PublicBurdenDimensionKind
    magnitude: float
    observed_at: str
    source: str
    source_version: int
    uncertainty: tuple[float, float]
    unit: str
    vulnerable_incidence: bool = False


class PublicBurdenDimensionKind(StrEnum):
    CRITICAL_SERVICE_CONTINUITY = "critical_service_continuity"
    DISTRIBUTION_EQUITY = "distribution_equity"
    FINANCIAL_RESOURCES = "financial_resources"
    IRREVERSIBILITY_RECOVERY = "irreversibility_recovery"
    OPPORTUNITY_DELAY = "opportunity_delay"
    SOCIAL_HUMAN = "social_human"


class PublicBurdenEntry(PiaModel):
    """Par explícito alternativa → vetor. Substitui o `dict` interno."""

    alternative: PublicAlternativeKind
    vector: PublicTotalBurdenVector


class PublicCausalRejectedRoutingView(PiaModel):
    reason: str
    subject_key: str
    abstained: bool = True
    kind: Literal["causal_rejected_routing"] = "causal_rejected_routing"
    route: None = None


class PublicCausalRejectionView(PiaModel):
    reason: str
    subject_key: str
    kind: Literal["causal_rejected"] = "causal_rejected"


class PublicChannel(PiaModel):
    lag: int
    name: str


class PublicChannelRegistry(PiaModel):
    channels: tuple[PublicChannel, ...]
    estimator_library: tuple[str, ...]


class PublicChannelRegistryView(PiaModel):
    channels: tuple[PublicChannelView, ...]
    estimator_library: tuple[str, ...]


class PublicChannelView(PiaModel):
    lag: int
    name: str


class PublicClaimEvaluationView(PiaModel):
    """Os OITO componentes congelados pelo Master §16.17.4."""

    approval_validation_outcome: PublicApprovalValidationOutcome
    claim: PublicClaimView
    evidence: PublicPowerOutcomeView
    horizon: PublicHorizonSpectrumView
    provenance: PublicProvenanceView
    regime: PublicRegimeAssessmentView
    state: PublicEpistemicState
    uncertainty: PublicUncertaintyView
    kind: Literal["evaluated"] = "evaluated"


class PublicClaimView(PiaModel):
    horizon_microseconds: int
    reference_time: datetime
    signal: str
    subject_key: str
    target: str


class PublicComparabilityKey(PiaModel):
    horizon: int
    jurisdiction: str
    population: str
    regime: str
    target: str
    unit: str


class PublicComparabilityKeyView(PiaModel):
    horizon: int
    jurisdiction: str
    population: str
    regime: str
    target: str
    unit: str


class PublicComparedClaimView(PiaModel):
    conclusion_signature: str
    key: PublicComparabilityKeyView
    state: PublicEpistemicState
    subject_key: str


class PublicConflictAssessmentView(PiaModel):
    compared: tuple[PublicComparedClaimView, ...]
    incommensurable_dimensions: tuple[str, ...]
    preserved_non_evaluated_count: int
    reason: str
    status: PublicConflictStatus


class PublicConflictStatus(StrEnum):
    PREDICTIVE_CLAIM_FALSE_CONFLICT_DECOMPOSED = "predictive_claim_false_conflict_decomposed"
    PREDICTIVE_CLAIM_NO_CONFLICT = "predictive_claim_no_conflict"
    PREDICTIVE_CLAIM_REAL_CONFLICT = "predictive_claim_real_conflict"


class PublicCostKnowledge(StrEnum):
    KNOWN = "known"
    UNKNOWN = "unknown"


class PublicEpistemicState(StrEnum):
    PREDICTABLE = "predictable"
    PREDICTIVELY_INACCESSIBLE = "predictively_inaccessible"
    UNRESOLVED = "unresolved"


class PublicEvaluationContext(PiaModel):
    """Representação completa de `PredictiveEvaluationContext`."""

    a_rel: float
    alpha_corrected: float
    at: datetime
    beats_fluctuation: bool
    blind_pairs: tuple[tuple[float, float], ...]
    bootstrap_replicates: int
    bootstrap_seed: int
    d_regime: float
    expected_binding_kind: PublicBoundObjectKind
    expected_jurisdiction: str | None
    expected_version: int
    horizon_points: tuple[PublicHorizonPoint, ...]
    observations: tuple[PublicObservation, ...]
    observed_at_offset: int
    placebo_permutations: int
    placebo_seed: int
    registry: PublicChannelRegistry
    required_scope: tuple[str, ...]
    rho_min: float
    theta: float
    training_pairs: tuple[tuple[float, float], ...]
    high_prediction_error: bool = False
    model_disagreement: bool = False


class PublicEvaluationRequest(PiaModel):
    """Requisição pública. Os tetos de lote são do servidor, não deste schema."""

    items: tuple[
        Annotated[PublicReadyItem | PublicUpstreamUnavailableItem, Field(discriminator="kind")],
        ...,
    ]
    contract_version: Literal["e6.public-evaluation/1"] = "e6.public-evaluation/1"


class PublicEvaluationResponse(PiaModel):
    decomposed_conflict_dimensions: tuple[str, ...]
    items: tuple[PublicEvaluationResultItem, ...]
    request_length: int
    contract_version: Literal["e6.public-evaluation/1"] = "e6.public-evaluation/1"


class PublicEvaluationResultItem(PiaModel):
    """Um par científico/roteamento por item de entrada, na mesma posição."""

    position: int
    routing: Annotated[
        PublicFinalRoutingView
        | PublicCausalRejectedRoutingView
        | PublicUpstreamUnavailableRoutingView,
        Field(discriminator="kind"),
    ]
    scientific: Annotated[
        PublicClaimEvaluationView | PublicCausalRejectionView | PublicUpstreamUnavailableView,
        Field(discriminator="kind"),
    ]


class PublicFinalRoutingView(PiaModel):
    """Os NOVE componentes de `PredictiveFinalRoutingResult`."""

    abstained: bool
    assertiveness: PublicAssertivenessView
    conflict_assessment: PublicConflictAssessmentView
    limits: tuple[str, ...]
    quality: PublicRecommendationQualityView
    reason: str
    recommended_alternative: PublicAlternativeKind | None
    revalidated_route: str
    route: PublicRoute | None
    kind: Literal["routed"] = "routed"


class PublicGovernedQualityInput(PiaModel):
    """Representação completa de `PredictiveGovernedQualityInput`."""

    alternatives: tuple[PublicAlternative, ...]
    burden_entries: tuple[PublicBurdenEntry, ...]
    comparability_key: PublicComparabilityKey
    conclusion_signature: str
    decisive_constraint: str
    expected_guidance_jurisdiction: str
    expected_guidance_version: int
    guidance: PublicGuidanceReference | None
    protection_candidates: tuple[PublicProtectionCandidate, ...]
    asymmetry_justification: str | None = None
    materiality_required_scope: tuple[str, ...] = ()
    protection_inventory_reference: str | None = None
    required_protection_identifiers: tuple[str, ...] = ()


class PublicGuidanceDisposition(StrEnum):
    ABSTAIN_FROM_PROCEDURAL_DETAIL = "abstain_from_procedural_detail"
    REFER_TO_COMPETENT_AUTHORITY = "refer_to_competent_authority"
    USE_PROCEDURAL_DETAIL = "use_procedural_detail"


class PublicGuidanceOutcome(StrEnum):
    INVALID = "invalid"
    JURISDICTION_MISMATCH = "jurisdiction_mismatch"
    MISSING = "missing"
    STALE = "stale"
    VALID = "valid"
    VERSION_MISMATCH = "version_mismatch"


class PublicGuidanceReference(PiaModel):
    authority: str
    jurisdiction: str
    provenance: str
    reference: str
    version: int
    valid_from: datetime | None = None
    valid_until: datetime | None = None


class PublicHistoricalValidityView(PiaModel):
    historical_kernel: tuple[PublicObservationView, ...]
    rho_min: float
    valid_window: tuple[PublicObservationView, ...]


class PublicHorizonPoint(PiaModel):
    a_minus: float
    gates_pass: bool
    horizon: int
    regime: PublicRegimeStatus


class PublicHorizonPointView(PiaModel):
    a_minus: float
    gates_pass: bool
    horizon: int
    regime: PublicRegimeStatus


class PublicHorizonSpectrumView(PiaModel):
    delta_cont: tuple[PublicHorizonPointView, ...]
    h_pred: tuple[PublicHorizonPointView, ...]
    r_pred: tuple[PublicHorizonPointView, ...]


class PublicMaterialityAuthority(PiaModel):
    authority: str
    jurisdiction: str
    reference: str
    version: int
    scope: tuple[str, ...] = ()
    valid_from: datetime | None = None
    valid_until: datetime | None = None


class PublicMaterialityStatus(StrEnum):
    NOT_SUPPORTED = "not_supported"
    SUPPORTED = "supported"
    UNRESOLVED = "unresolved"


class PublicObservation(PiaModel):
    provenance: str
    reference: str
    relevance_score: float


class PublicObservationView(PiaModel):
    provenance: str
    reference: str
    relevance_score: float


class PublicPowerOutcomeView(PiaModel):
    """Os nove campos de `PredictivePowerOutcome`, sem recorte."""

    a_minus: float
    a_star_worst: float
    a_upper: float
    alpha_corrected: float
    g_real: float
    g_shuffled_p95: float
    mean_gain: float
    placebo_p: float
    sample_size: int


class PublicProbabilityValidation(StrEnum):
    NOT_VALIDATED = "not_validated"
    VALIDATED = "validated"


class PublicProtectionCandidate(PiaModel):
    identifier: str
    material_effect_claimed: bool
    provenance: str
    reason: str
    authority: PublicMaterialityAuthority | None = None
    incompatible_with: tuple[str, ...] = ()
    owner: str | None = None
    reversibility: str | None = None
    time_window: str | None = None
    triggers: tuple[str, ...] = ()


class PublicProtectionCandidateView(PiaModel):
    authority_reference: str | None
    classification_reason: str
    identifier: str
    incompatible_with: tuple[str, ...]
    materiality: PublicMaterialityStatus
    owner: str | None
    provenance: str
    reason: str
    reversibility: str | None
    time_window: str | None
    triggers: tuple[str, ...]


class PublicProtectionSummaryView(PiaModel):
    accepted: tuple[PublicProtectionCandidateView, ...]
    complete_answer_allowed: bool
    coverage_unresolved_reason: str | None
    rejected: tuple[PublicProtectionCandidateView, ...]
    unresolved: tuple[PublicProtectionCandidateView, ...]


class PublicProvenanceView(PiaModel):
    a_rel: float
    historical_validity: PublicHistoricalValidityView
    registry: PublicChannelRegistryView


class PublicReadyItem(PiaModel):
    """Item pronto: bytes canônicos + contexto + entradas governadas."""

    canonical_piap_transport: str
    evaluation_context: PublicEvaluationContext
    governed_quality: PublicGovernedQualityInput
    kind: Literal["ready"]


class PublicRecommendationQualityView(PiaModel):
    complete_answer_allowed: bool
    disposition: PublicGuidanceDisposition
    guidance_outcome: PublicGuidanceOutcome
    procedural_detail_allowed: bool
    protection: PublicProtectionSummaryView
    reason: str


class PublicRegimeAssessmentView(PiaModel):
    beats_fluctuation: bool
    d_regime: float
    high_prediction_error: bool
    model_disagreement: bool
    status: PublicRegimeStatus
    theta: float


class PublicRegimeStatus(StrEnum):
    NO_SHIFT = "no_shift"
    REGIME_SHIFT_CANDIDATE = "regime_shift_candidate"


class PublicRoute(StrEnum):
    INVESTIGATE = "investigate"
    PREDICT = "predict"
    RECONFIGURE = "reconfigure"
    ROBUST = "robust"


class PublicTotalBurdenVector(PiaModel):
    dimensions: tuple[PublicBurdenDimension, ...]
    probability_validation: PublicProbabilityValidation


class PublicUncertaintyView(PiaModel):
    """`uncertainty` como componente identificado, não projeção anônima."""

    lower: float
    upper: float


class PublicUpstreamUnavailableItem(PiaModel):
    kind: Literal["upstream_unavailable"]
    reason: str
    reference: str


class PublicUpstreamUnavailableRoutingView(PiaModel):
    reason: str
    source_reference: str
    abstained: bool = True
    kind: Literal["upstream_unavailable_routing"] = "upstream_unavailable_routing"
    route: None = None


class PublicUpstreamUnavailableView(PiaModel):
    reason: str
    reference: str
    kind: Literal["upstream_unavailable"] = "upstream_unavailable"


class RootResponse(PiaModel):
    """Resposta de `GET /` — cartão de visitas da plataforma."""

    docs_url: str | None
    environment: str
    name: str
    redoc_url: str | None
    timestamp: str
    version: str


class StatusResponse(PiaModel):
    api_version: str
    database_connected: bool
    environment: str
    modules_loaded: int
    status: str
    uptime_seconds: float
    components: tuple[ComponentStatus, ...] = ()
    database_response_time_ms: float | None = None


class SuccessResponsePublicEvaluationResponse(PiaModel):
    data: PublicEvaluationResponse
    message: str | None = None


class ValidationErrorItem(PiaModel):
    """Um item de erro de validação — mesmo formato usado pelo Pydantic/"""

    loc: tuple[str | int, ...]
    msg: str
    type: str


class ValidationResponse(PiaModel):
    """Formato do corpo de erro para respostas 422 — usado para"""

    error: ErrorDetail
    errors: tuple[ValidationErrorItem, ...] = ()
    success: bool = False


class VersionResponse(PiaModel):
    api_version: str
    app_name: str
    environment: str
    pia_os_version: str
    version: str
    database_version: str | None = None


# Referências para frente: os schemas são emitidos em ordem
# alfabética, então um modelo pode citar outro definido depois.
# `model_rebuild()` resolve todas de uma vez, na ordem em que foram
# emitidas — sem isso, pydantic deixaria modelos incompletos e a
# falha só apareceria na primeira validação.
for _modelo in (
    ComponentStatus,
    ErrorDetail,
    ErrorResponse,
    HealthResponse,
    MetricsResponse,
    PublicAlternative,
    PublicAssertivenessView,
    PublicBurdenDimension,
    PublicBurdenEntry,
    PublicCausalRejectedRoutingView,
    PublicCausalRejectionView,
    PublicChannel,
    PublicChannelRegistry,
    PublicChannelRegistryView,
    PublicChannelView,
    PublicClaimEvaluationView,
    PublicClaimView,
    PublicComparabilityKey,
    PublicComparabilityKeyView,
    PublicComparedClaimView,
    PublicConflictAssessmentView,
    PublicEvaluationContext,
    PublicEvaluationRequest,
    PublicEvaluationResponse,
    PublicEvaluationResultItem,
    PublicFinalRoutingView,
    PublicGovernedQualityInput,
    PublicGuidanceReference,
    PublicHistoricalValidityView,
    PublicHorizonPoint,
    PublicHorizonPointView,
    PublicHorizonSpectrumView,
    PublicMaterialityAuthority,
    PublicObservation,
    PublicObservationView,
    PublicPowerOutcomeView,
    PublicProtectionCandidate,
    PublicProtectionCandidateView,
    PublicProtectionSummaryView,
    PublicProvenanceView,
    PublicReadyItem,
    PublicRecommendationQualityView,
    PublicRegimeAssessmentView,
    PublicTotalBurdenVector,
    PublicUncertaintyView,
    PublicUpstreamUnavailableItem,
    PublicUpstreamUnavailableRoutingView,
    PublicUpstreamUnavailableView,
    RootResponse,
    StatusResponse,
    SuccessResponsePublicEvaluationResponse,
    ValidationErrorItem,
    ValidationResponse,
    VersionResponse,
):
    _modelo.model_rebuild()

del _modelo


__all__ = [
    "OPENAPI_SNAPSHOT_SHA256",
    "PiaModel",
    "ComponentStatus",
    "ErrorDetail",
    "ErrorResponse",
    "HealthResponse",
    "MetricsResponse",
    "PublicAlternative",
    "PublicAlternativeKind",
    "PublicApprovalValidationOutcome",
    "PublicAssertivenessView",
    "PublicAuthorityState",
    "PublicBoundObjectKind",
    "PublicBurdenDimension",
    "PublicBurdenDimensionKind",
    "PublicBurdenEntry",
    "PublicCausalRejectedRoutingView",
    "PublicCausalRejectionView",
    "PublicChannel",
    "PublicChannelRegistry",
    "PublicChannelRegistryView",
    "PublicChannelView",
    "PublicClaimEvaluationView",
    "PublicClaimView",
    "PublicComparabilityKey",
    "PublicComparabilityKeyView",
    "PublicComparedClaimView",
    "PublicConflictAssessmentView",
    "PublicConflictStatus",
    "PublicCostKnowledge",
    "PublicEpistemicState",
    "PublicEvaluationContext",
    "PublicEvaluationRequest",
    "PublicEvaluationResponse",
    "PublicEvaluationResultItem",
    "PublicFinalRoutingView",
    "PublicGovernedQualityInput",
    "PublicGuidanceDisposition",
    "PublicGuidanceOutcome",
    "PublicGuidanceReference",
    "PublicHistoricalValidityView",
    "PublicHorizonPoint",
    "PublicHorizonPointView",
    "PublicHorizonSpectrumView",
    "PublicMaterialityAuthority",
    "PublicMaterialityStatus",
    "PublicObservation",
    "PublicObservationView",
    "PublicPowerOutcomeView",
    "PublicProbabilityValidation",
    "PublicProtectionCandidate",
    "PublicProtectionCandidateView",
    "PublicProtectionSummaryView",
    "PublicProvenanceView",
    "PublicReadyItem",
    "PublicRecommendationQualityView",
    "PublicRegimeAssessmentView",
    "PublicRegimeStatus",
    "PublicRoute",
    "PublicTotalBurdenVector",
    "PublicUncertaintyView",
    "PublicUpstreamUnavailableItem",
    "PublicUpstreamUnavailableRoutingView",
    "PublicUpstreamUnavailableView",
    "RootResponse",
    "StatusResponse",
    "SuccessResponsePublicEvaluationResponse",
    "ValidationErrorItem",
    "ValidationResponse",
    "VersionResponse",
]
