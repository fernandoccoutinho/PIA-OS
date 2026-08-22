"""Contrato público da avaliação preditiva programática — `E6.1`.

Representações Pydantic da requisição e da resposta do recurso
`POST /api/v1/predictive-evaluations`. **Nenhuma** regra científica vive aqui.

```text
PUBLIC_DTO_IMPORTS_E5_INTERNALS = FORBIDDEN
SDK_MODEL = REPRESENTATION_ONLY · SERVER_CONTRACT = SOURCE_OF_TRUTH
CLIENT_SUPPLIES_DERIVED_RESULT = FORBIDDEN
```

Este módulo **não importa** `app.predictive_accessibility`. Os literais de enum
são reproduzidos como texto fechado, e o mapeador servidor-side é quem os
converte nos objetos internos. Reproduzir o literal público não é duplicar
regra: o servidor continua rejeitando qualquer valor que os construtores
canônicos não aceitem.

Os bytes PIAP viajam em `canonical_piap_transport`, codificação **reversível**
de transporte. Não é formato semântico novo e não relaxa
`deserialize_piap_envelope`: o mapeador compara byte a byte após decodificar.

```text
TRANSPORT_ENCODING != SEMANTIC_FORMAT
```

Limites de lote e de PIAP **não** são reproduzidos aqui: quem os aplica é o
construtor canônico do servidor.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

PUBLIC_CONTRACT_VERSION = "e6.public-evaluation/1"

_REQUEST = ConfigDict(extra="forbid", frozen=True)
_RESPONSE = ConfigDict(extra="forbid", frozen=True)


# --- vocabulários públicos -------------------------------------------------


class PublicAlternativeKind(StrEnum):
    A0_INACTION = "a0_inaction"
    A1_REVERSIBLE_ESCALATION = "a1_reversible_escalation"
    A2_FULL_ACTION = "a2_full_action"


class PublicCostKnowledge(StrEnum):
    KNOWN = "known"
    UNKNOWN = "unknown"


class PublicBurdenDimensionKind(StrEnum):
    FINANCIAL_RESOURCES = "financial_resources"
    SOCIAL_HUMAN = "social_human"
    CRITICAL_SERVICE_CONTINUITY = "critical_service_continuity"
    DISTRIBUTION_EQUITY = "distribution_equity"
    OPPORTUNITY_DELAY = "opportunity_delay"
    IRREVERSIBILITY_RECOVERY = "irreversibility_recovery"


class PublicProbabilityValidation(StrEnum):
    VALIDATED = "validated"
    NOT_VALIDATED = "not_validated"


class PublicRegimeStatus(StrEnum):
    NO_SHIFT = "no_shift"
    REGIME_SHIFT_CANDIDATE = "regime_shift_candidate"


class PublicBoundObjectKind(StrEnum):
    PROPOSED_BOUND = "proposed_bound"
    PROMOTION_CANDIDATE = "promotion_candidate"


class PublicEpistemicState(StrEnum):
    PREDICTABLE = "predictable"
    UNRESOLVED = "unresolved"
    PREDICTIVELY_INACCESSIBLE = "predictively_inaccessible"


class PublicApprovalValidationOutcome(StrEnum):
    VALID = "valid"
    MISSING = "missing"
    NOT_AUTHORIZED = "not_authorized"
    EXPIRED = "expired"
    VERSION_MISMATCH = "version_mismatch"
    OUT_OF_SCOPE = "out_of_scope"
    JURISDICTION_MISMATCH = "jurisdiction_mismatch"
    BINDING_MISMATCH = "binding_mismatch"


class PublicAuthorityState(StrEnum):
    AUTHORIZED = "authorized"
    NOT_AUTHORIZED = "not_authorized"


class PublicConflictStatus(StrEnum):
    PREDICTIVE_CLAIM_NO_CONFLICT = "predictive_claim_no_conflict"
    PREDICTIVE_CLAIM_REAL_CONFLICT = "predictive_claim_real_conflict"
    PREDICTIVE_CLAIM_FALSE_CONFLICT_DECOMPOSED = "predictive_claim_false_conflict_decomposed"


class PublicMaterialityStatus(StrEnum):
    SUPPORTED = "supported"
    NOT_SUPPORTED = "not_supported"
    UNRESOLVED = "unresolved"


class PublicGuidanceOutcome(StrEnum):
    VALID = "valid"
    MISSING = "missing"
    STALE = "stale"
    INVALID = "invalid"
    JURISDICTION_MISMATCH = "jurisdiction_mismatch"
    VERSION_MISMATCH = "version_mismatch"


class PublicGuidanceDisposition(StrEnum):
    USE_PROCEDURAL_DETAIL = "use_procedural_detail"
    REFER_TO_COMPETENT_AUTHORITY = "refer_to_competent_authority"
    ABSTAIN_FROM_PROCEDURAL_DETAIL = "abstain_from_procedural_detail"


class PublicRoute(StrEnum):
    PREDICT = "predict"
    RECONFIGURE = "reconfigure"
    INVESTIGATE = "investigate"
    ROBUST = "robust"


# --- blocos compartilhados -------------------------------------------------


class PublicChannel(BaseModel):
    model_config = _REQUEST
    name: str = Field(min_length=1)
    lag: int = Field(ge=1)


class PublicChannelRegistry(BaseModel):
    model_config = _REQUEST
    channels: tuple[PublicChannel, ...] = Field(min_length=1)
    estimator_library: tuple[str, ...] = Field(min_length=1)


class PublicObservation(BaseModel):
    model_config = _REQUEST
    reference: str = Field(min_length=1)
    provenance: str = Field(min_length=1)
    relevance_score: float


class PublicHorizonPoint(BaseModel):
    model_config = _REQUEST
    horizon: int = Field(ge=1)
    a_minus: float
    gates_pass: bool
    regime: PublicRegimeStatus


class PublicComparabilityKey(BaseModel):
    model_config = _REQUEST
    target: str = Field(min_length=1)
    population: str = Field(min_length=1)
    jurisdiction: str = Field(min_length=1)
    horizon: int = Field(ge=1)
    regime: str = Field(min_length=1)
    unit: str = Field(min_length=1)


class PublicMaterialityAuthority(BaseModel):
    model_config = _REQUEST
    reference: str
    authority: str
    jurisdiction: str
    version: int
    scope: tuple[str, ...] = ()
    valid_from: datetime | None = None
    valid_until: datetime | None = None


class PublicProtectionCandidate(BaseModel):
    model_config = _REQUEST
    identifier: str = Field(min_length=1)
    reason: str = Field(min_length=1)
    provenance: str = Field(min_length=1)
    material_effect_claimed: bool
    authority: PublicMaterialityAuthority | None = None
    owner: str | None = None
    time_window: str | None = None
    reversibility: str | None = None
    triggers: tuple[str, ...] = ()
    incompatible_with: tuple[str, ...] = ()


class PublicGuidanceReference(BaseModel):
    model_config = _REQUEST
    reference: str
    authority: str
    provenance: str
    jurisdiction: str
    version: int
    valid_from: datetime | None = None
    valid_until: datetime | None = None


class PublicAlternative(BaseModel):
    model_config = _REQUEST
    kind: PublicAlternativeKind
    key: PublicComparabilityKey
    cost_knowledge: PublicCostKnowledge
    cost_value: float | None = None
    reversible: bool
    description: str = Field(min_length=1)


class PublicBurdenDimension(BaseModel):
    model_config = _REQUEST
    kind: PublicBurdenDimensionKind
    magnitude: float
    unit: str = Field(min_length=1)
    source: str = Field(min_length=1)
    source_version: int
    observed_at: str = Field(min_length=1)
    uncertainty: tuple[float, float]
    incidence: str = Field(min_length=1)
    vulnerable_incidence: bool = False


class PublicTotalBurdenVector(BaseModel):
    model_config = _REQUEST
    dimensions: tuple[PublicBurdenDimension, ...] = Field(min_length=1)
    probability_validation: PublicProbabilityValidation


class PublicChannelView(BaseModel):
    model_config = _RESPONSE
    name: str
    lag: int


class PublicChannelRegistryView(BaseModel):
    model_config = _RESPONSE
    channels: tuple[PublicChannelView, ...]
    estimator_library: tuple[str, ...]


class PublicComparabilityKeyView(BaseModel):
    model_config = _RESPONSE
    target: str
    population: str
    jurisdiction: str
    horizon: int
    regime: str
    unit: str


class PublicBurdenEntry(BaseModel):
    """Par explícito alternativa → vetor. Substitui o `dict` interno."""

    model_config = _REQUEST
    alternative: PublicAlternativeKind
    vector: PublicTotalBurdenVector


# --- contexto de avaliação -------------------------------------------------


class PublicEvaluationContext(BaseModel):
    """Representação completa de `PredictiveEvaluationContext`.

    Todos os 23 campos são explícitos. Os dois últimos têm default **no
    objeto interno**, e o DTO o reproduz; nenhum outro campo obrigatório recebe
    default inventado.
    """

    model_config = _REQUEST
    registry: PublicChannelRegistry
    observed_at_offset: int
    observations: tuple[PublicObservation, ...]
    rho_min: float
    d_regime: float
    theta: float
    beats_fluctuation: bool
    horizon_points: tuple[PublicHorizonPoint, ...] = Field(min_length=1)
    training_pairs: tuple[tuple[float, float], ...] = Field(min_length=1)
    blind_pairs: tuple[tuple[float, float], ...] = Field(min_length=1)
    bootstrap_replicates: int = Field(ge=1)
    bootstrap_seed: int
    alpha_corrected: float = Field(gt=0.0, lt=1.0)
    placebo_permutations: int = Field(ge=1)
    placebo_seed: int
    a_rel: float
    at: datetime
    expected_version: int
    required_scope: tuple[str, ...]
    expected_jurisdiction: str | None
    expected_binding_kind: PublicBoundObjectKind
    high_prediction_error: bool = False
    model_disagreement: bool = False


class PublicGovernedQualityInput(BaseModel):
    """Representação completa de `PredictiveGovernedQualityInput`."""

    model_config = _REQUEST
    conclusion_signature: str = Field(min_length=1)
    comparability_key: PublicComparabilityKey
    decisive_constraint: str = Field(min_length=1)
    protection_candidates: tuple[PublicProtectionCandidate, ...]
    guidance: PublicGuidanceReference | None
    expected_guidance_jurisdiction: str = Field(min_length=1)
    expected_guidance_version: int
    alternatives: tuple[PublicAlternative, ...]
    burden_entries: tuple[PublicBurdenEntry, ...]
    materiality_required_scope: tuple[str, ...] = ()
    required_protection_identifiers: tuple[str, ...] = ()
    protection_inventory_reference: str | None = None
    asymmetry_justification: str | None = None


# --- itens da requisição ---------------------------------------------------


class PublicReadyItem(BaseModel):
    """Item pronto: bytes canônicos + contexto + entradas governadas."""

    model_config = _REQUEST
    kind: Literal["ready"]
    canonical_piap_transport: str = Field(
        min_length=1,
        description="Bytes PIAP canônicos em base64 padrão, reversível e comparado byte a byte.",
    )
    evaluation_context: PublicEvaluationContext
    governed_quality: PublicGovernedQualityInput


class PublicUpstreamUnavailableItem(BaseModel):
    model_config = _REQUEST
    kind: Literal["upstream_unavailable"]
    reference: str = Field(min_length=1)
    reason: str = Field(min_length=1)


PublicRequestItem = Annotated[
    PublicReadyItem | PublicUpstreamUnavailableItem, Field(discriminator="kind")
]


class PublicEvaluationRequest(BaseModel):
    """Requisição pública. Os tetos de lote são do servidor, não deste schema."""

    model_config = _REQUEST
    contract_version: Literal["e6.public-evaluation/1"] = "e6.public-evaluation/1"
    items: tuple[PublicRequestItem, ...] = Field(min_length=1)


# --- itens da resposta -----------------------------------------------------
#
# Os oito componentes congelados do `CLAIM_EVALUATION_RESULT` e os nove do
# `PredictiveFinalRoutingResult` são representados por inteiro. Views podem
# normalizar referências repetidas, mas nada contratual desaparece.
#
#     REPRESENTS_VARIANT_TAG != REPRESENTS_CONTRACTED_RESULT
#     SDK_ACCESS_WITHOUT_CAUSAL_EXPLANATION = CONTRACT_LOSS


class PublicUncertaintyView(BaseModel):
    """`uncertainty` como componente identificado, não projeção anônima."""

    model_config = _RESPONSE
    lower: float
    upper: float


class PublicClaimView(BaseModel):
    model_config = _RESPONSE
    target: str
    signal: str
    horizon_microseconds: int
    reference_time: datetime
    subject_key: str


class PublicObservationView(BaseModel):
    model_config = _RESPONSE
    reference: str
    provenance: str
    relevance_score: float


class PublicHistoricalValidityView(BaseModel):
    model_config = _RESPONSE
    valid_window: tuple[PublicObservationView, ...]
    historical_kernel: tuple[PublicObservationView, ...]
    rho_min: float


class PublicProvenanceView(BaseModel):
    model_config = _RESPONSE
    registry: PublicChannelRegistryView
    a_rel: float
    historical_validity: PublicHistoricalValidityView


class PublicRegimeAssessmentView(BaseModel):
    model_config = _RESPONSE
    status: PublicRegimeStatus
    d_regime: float
    theta: float
    beats_fluctuation: bool
    high_prediction_error: bool
    model_disagreement: bool


class PublicPowerOutcomeView(BaseModel):
    """Os nove campos de `PredictivePowerOutcome`, sem recorte."""

    model_config = _RESPONSE
    a_minus: float
    a_upper: float
    a_star_worst: float
    mean_gain: float
    placebo_p: float
    g_real: float
    g_shuffled_p95: float
    sample_size: int
    alpha_corrected: float


class PublicHorizonPointView(BaseModel):
    model_config = _RESPONSE
    horizon: int
    a_minus: float
    gates_pass: bool
    regime: PublicRegimeStatus


class PublicHorizonSpectrumView(BaseModel):
    model_config = _RESPONSE
    h_pred: tuple[PublicHorizonPointView, ...]
    delta_cont: tuple[PublicHorizonPointView, ...]
    r_pred: tuple[PublicHorizonPointView, ...]


class PublicClaimEvaluationView(BaseModel):
    """Os OITO componentes congelados pelo Master §16.17.4."""

    model_config = _RESPONSE
    kind: Literal["evaluated"] = "evaluated"
    claim: PublicClaimView
    provenance: PublicProvenanceView
    regime: PublicRegimeAssessmentView
    evidence: PublicPowerOutcomeView
    uncertainty: PublicUncertaintyView
    horizon: PublicHorizonSpectrumView
    state: PublicEpistemicState
    approval_validation_outcome: PublicApprovalValidationOutcome


class PublicCausalRejectionView(BaseModel):
    model_config = _RESPONSE
    kind: Literal["causal_rejected"] = "causal_rejected"
    subject_key: str
    reason: str


class PublicUpstreamUnavailableView(BaseModel):
    model_config = _RESPONSE
    kind: Literal["upstream_unavailable"] = "upstream_unavailable"
    reference: str
    reason: str


PublicScientificOutcome = Annotated[
    PublicClaimEvaluationView | PublicCausalRejectionView | PublicUpstreamUnavailableView,
    Field(discriminator="kind"),
]


class PublicAssertivenessView(BaseModel):
    """Master §16.14: conclusão, restrição, incerteza, autoridade, rota, gatilho."""

    model_config = _RESPONSE
    candidate_conclusion: str
    decisive_constraint: str
    uncertainty: PublicUncertaintyView
    authority_state: PublicAuthorityState
    next_governed_route: str
    review_or_stop_trigger: str


class PublicComparedClaimView(BaseModel):
    model_config = _RESPONSE
    subject_key: str
    conclusion_signature: str
    key: PublicComparabilityKeyView
    state: PublicEpistemicState


class PublicConflictAssessmentView(BaseModel):
    model_config = _RESPONSE
    status: PublicConflictStatus
    compared: tuple[PublicComparedClaimView, ...]
    incommensurable_dimensions: tuple[str, ...]
    preserved_non_evaluated_count: int
    reason: str


class PublicProtectionCandidateView(BaseModel):
    model_config = _RESPONSE
    identifier: str
    reason: str
    provenance: str
    materiality: PublicMaterialityStatus
    classification_reason: str
    owner: str | None
    authority_reference: str | None
    time_window: str | None
    reversibility: str | None
    triggers: tuple[str, ...]
    incompatible_with: tuple[str, ...]


class PublicProtectionSummaryView(BaseModel):
    model_config = _RESPONSE
    accepted: tuple[PublicProtectionCandidateView, ...]
    rejected: tuple[PublicProtectionCandidateView, ...]
    unresolved: tuple[PublicProtectionCandidateView, ...]
    complete_answer_allowed: bool
    coverage_unresolved_reason: str | None


class PublicRecommendationQualityView(BaseModel):
    model_config = _RESPONSE
    guidance_outcome: PublicGuidanceOutcome
    disposition: PublicGuidanceDisposition
    complete_answer_allowed: bool
    procedural_detail_allowed: bool
    reason: str
    protection: PublicProtectionSummaryView


class PublicFinalRoutingView(BaseModel):
    """Os NOVE componentes de `PredictiveFinalRoutingResult`."""

    model_config = _RESPONSE
    kind: Literal["routed"] = "routed"
    route: PublicRoute | None
    abstained: bool
    recommended_alternative: PublicAlternativeKind | None
    conflict_assessment: PublicConflictAssessmentView
    limits: tuple[str, ...]
    reason: str
    assertiveness: PublicAssertivenessView
    revalidated_route: str
    quality: PublicRecommendationQualityView


class PublicCausalRejectedRoutingView(BaseModel):
    model_config = _RESPONSE
    kind: Literal["causal_rejected_routing"] = "causal_rejected_routing"
    subject_key: str
    reason: str
    route: None = None
    abstained: bool = True


class PublicUpstreamUnavailableRoutingView(BaseModel):
    model_config = _RESPONSE
    kind: Literal["upstream_unavailable_routing"] = "upstream_unavailable_routing"
    source_reference: str
    reason: str
    route: None = None
    abstained: bool = True


PublicRoutingOutcome = Annotated[
    PublicFinalRoutingView | PublicCausalRejectedRoutingView | PublicUpstreamUnavailableRoutingView,
    Field(discriminator="kind"),
]


class PublicEvaluationResultItem(BaseModel):
    """Um par científico/roteamento por item de entrada, na mesma posição."""

    model_config = _RESPONSE
    position: int = Field(ge=0)
    scientific: PublicScientificOutcome
    routing: PublicRoutingOutcome


class PublicEvaluationResponse(BaseModel):
    model_config = _RESPONSE
    contract_version: Literal["e6.public-evaluation/1"] = "e6.public-evaluation/1"
    request_length: int = Field(ge=0)
    decomposed_conflict_dimensions: tuple[str, ...]
    items: tuple[PublicEvaluationResultItem, ...]
