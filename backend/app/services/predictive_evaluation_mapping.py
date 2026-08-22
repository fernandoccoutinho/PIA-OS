"""Mapeadores servidor-side do contrato público `E6.1`.

Convertem DTO público em value objects internos e desfechos internos em DTO
público. **Nenhuma** função científica é chamada aqui.

```text
SERVER_MAPPER_CALLS_SCIENTIFIC_FUNCTION = FORBIDDEN
NO_ROUTE · NO_AUTH · NO_SDK · NO_DB · NO_MIGRATION
```

O mapeador é o único ponto que conhece os dois lados. Ele:

1. decodifica `canonical_piap_transport` e **compara byte a byte** o
   recodificado com o recebido antes de qualquer parse;
2. chama `deserialize_piap_envelope`, que continua sendo o mecanismo canônico —
   bytes alterados ou não canônicos são recusados por ele, não por regra nova
   escrita aqui;
3. constrói **explicitamente** cada value object interno, sem default
   inventado.

```text
TRANSPORT_DECODE_THEN_CANONICAL_PARSE
CLIENT_SUPPLIES_DERIVED_RESULT = FORBIDDEN
```

Limites de lote e PIAP continuam aplicados pelos construtores canônicos: este
módulo não reproduz nenhuma das constantes.
"""

from __future__ import annotations

import base64
import binascii
from datetime import timedelta

from app.predictive_accessibility.assertiveness import PredictiveAssertiveness
from app.predictive_accessibility.availability import PredictiveCausalRejectionResult
from app.predictive_accessibility.batch import (
    PredictiveEvaluationBatchResult,
    PredictiveEvaluationContext,
    PredictiveEvaluationRequest,
    PredictiveGovernedQualityInput,
    PredictiveReadyEvaluationItem,
    PredictiveRoutingBatchResult,
    PredictiveUpstreamUnavailableInput,
    PredictiveUpstreamUnavailableOutcome,
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
from app.predictive_accessibility.guidance import (
    PredictiveGuidanceReference,
    PredictiveRecommendationQualityResult,
)
from app.predictive_accessibility.history import PredictiveObservation
from app.predictive_accessibility.horizon import PredictiveHorizonPoint, PredictiveHorizonSpectrum
from app.predictive_accessibility.piap.enums import BoundObjectKind
from app.predictive_accessibility.piap.envelope import (
    PiapEnvelope,
    deserialize_piap_envelope,
)
from app.predictive_accessibility.power import PredictivePowerOutcome
from app.predictive_accessibility.predictive_claim_conflict import (
    PredictiveComparabilityKey,
    PredictiveConflictAssessment,
)
from app.predictive_accessibility.protection import (
    PredictiveMaterialityAuthority,
    PredictiveProtectionCandidate,
    PredictiveProtectionCandidateInput,
)
from app.predictive_accessibility.regime import PredictiveRegimeAssessment, PredictiveRegimeStatus
from app.predictive_accessibility.routing import (
    PredictiveCausalRejectedRoutingResult,
    PredictiveFinalRoutingResult,
    PredictiveRoute,
    PredictiveUpstreamUnavailableRoutingResult,
)
from app.schemas import predictive_evaluation as dto


class PublicContractMappingError(ValueError):
    """Representação pública inválida. Não é erro científico nem de transporte."""


# --- transporte ------------------------------------------------------------


def decode_canonical_piap_transport(transport: str) -> bytes:
    """Base64 padrão, estritamente reversível, comparado byte a byte."""
    try:
        payload = base64.b64decode(transport, validate=True)
    except (binascii.Error, ValueError) as erro:
        raise PublicContractMappingError(
            f"canonical_piap_transport não é base64 padrão válido: {erro}"
        ) from erro
    if base64.b64encode(payload).decode("ascii") != transport:
        raise PublicContractMappingError(
            "canonical_piap_transport não é reversível: a recodificação difere do recebido"
        )
    return payload


def encode_canonical_piap_transport(payload: bytes) -> str:
    if type(payload) is not bytes:
        raise PublicContractMappingError(
            f"payload deve ser bytes, recebido {type(payload).__name__}"
        )
    return base64.b64encode(payload).decode("ascii")


# --- entrada: DTO -> value objects internos --------------------------------


def _registry(modelo: dto.PublicChannelRegistry) -> PredictiveChannelRegistry:
    return PredictiveChannelRegistry(
        channels=tuple(PredictiveChannel(name=c.name, lag=c.lag) for c in modelo.channels),
        estimator_library=tuple(modelo.estimator_library),
    )


def _comparability_key(modelo: dto.PublicComparabilityKey) -> PredictiveComparabilityKey:
    return PredictiveComparabilityKey(
        target=modelo.target,
        population=modelo.population,
        jurisdiction=modelo.jurisdiction,
        horizon=modelo.horizon,
        regime=modelo.regime,
        unit=modelo.unit,
    )


def _authority(
    modelo: dto.PublicMaterialityAuthority | None,
) -> PredictiveMaterialityAuthority | None:
    if modelo is None:
        return None
    return PredictiveMaterialityAuthority(
        reference=modelo.reference,
        authority=modelo.authority,
        jurisdiction=modelo.jurisdiction,
        version=modelo.version,
        scope=tuple(modelo.scope),
        valid_from=modelo.valid_from,
        valid_until=modelo.valid_until,
    )


def _guidance(
    modelo: dto.PublicGuidanceReference | None,
) -> PredictiveGuidanceReference | None:
    if modelo is None:
        return None
    return PredictiveGuidanceReference(
        reference=modelo.reference,
        authority=modelo.authority,
        provenance=modelo.provenance,
        jurisdiction=modelo.jurisdiction,
        version=modelo.version,
        valid_from=modelo.valid_from,
        valid_until=modelo.valid_until,
    )


def _vector(modelo: dto.PublicTotalBurdenVector) -> PredictiveTotalBurdenVector:
    return PredictiveTotalBurdenVector(
        dimensions=tuple(
            PredictiveBurdenDimension(
                kind=PredictiveBurdenDimensionKind(d.kind.value),
                magnitude=d.magnitude,
                unit=d.unit,
                source=d.source,
                source_version=d.source_version,
                observed_at=d.observed_at,
                uncertainty=(d.uncertainty[0], d.uncertainty[1]),
                incidence=d.incidence,
                vulnerable_incidence=d.vulnerable_incidence,
            )
            for d in modelo.dimensions
        ),
        probability_validation=PredictiveProbabilityValidation(modelo.probability_validation.value),
    )


def to_evaluation_context(modelo: dto.PublicEvaluationContext) -> PredictiveEvaluationContext:
    """Constrói os 23 campos explicitamente. Nenhum default inventado."""
    return PredictiveEvaluationContext(
        registry=_registry(modelo.registry),
        observed_at_offset=modelo.observed_at_offset,
        observations=tuple(
            PredictiveObservation(
                reference=o.reference,
                provenance=o.provenance,
                relevance_score=o.relevance_score,
            )
            for o in modelo.observations
        ),
        rho_min=modelo.rho_min,
        d_regime=modelo.d_regime,
        theta=modelo.theta,
        beats_fluctuation=modelo.beats_fluctuation,
        horizon_points=tuple(
            PredictiveHorizonPoint(
                horizon=p.horizon,
                a_minus=p.a_minus,
                gates_pass=p.gates_pass,
                regime=PredictiveRegimeStatus(p.regime.value),
            )
            for p in modelo.horizon_points
        ),
        training_pairs=tuple((a, b) for a, b in modelo.training_pairs),
        blind_pairs=tuple((a, b) for a, b in modelo.blind_pairs),
        bootstrap_replicates=modelo.bootstrap_replicates,
        bootstrap_seed=modelo.bootstrap_seed,
        alpha_corrected=modelo.alpha_corrected,
        placebo_permutations=modelo.placebo_permutations,
        placebo_seed=modelo.placebo_seed,
        a_rel=modelo.a_rel,
        at=modelo.at,
        expected_version=modelo.expected_version,
        required_scope=tuple(modelo.required_scope),
        expected_jurisdiction=modelo.expected_jurisdiction,
        expected_binding_kind=BoundObjectKind(modelo.expected_binding_kind.value),
        high_prediction_error=modelo.high_prediction_error,
        model_disagreement=modelo.model_disagreement,
    )


def to_governed_quality_input(
    modelo: dto.PublicGovernedQualityInput,
) -> PredictiveGovernedQualityInput:
    return PredictiveGovernedQualityInput(
        conclusion_signature=modelo.conclusion_signature,
        comparability_key=_comparability_key(modelo.comparability_key),
        decisive_constraint=modelo.decisive_constraint,
        protection_candidates=tuple(
            PredictiveProtectionCandidateInput(
                identifier=c.identifier,
                reason=c.reason,
                provenance=c.provenance,
                material_effect_claimed=c.material_effect_claimed,
                authority=_authority(c.authority),
                owner=c.owner,
                time_window=c.time_window,
                reversibility=c.reversibility,
                triggers=tuple(c.triggers),
                incompatible_with=tuple(c.incompatible_with),
            )
            for c in modelo.protection_candidates
        ),
        guidance=_guidance(modelo.guidance),
        expected_guidance_jurisdiction=modelo.expected_guidance_jurisdiction,
        expected_guidance_version=modelo.expected_guidance_version,
        alternatives=tuple(
            PredictiveAlternative(
                kind=PredictiveAlternativeKind(a.kind.value),
                key=_comparability_key(a.key),
                cost_knowledge=PredictiveCostKnowledge(a.cost_knowledge.value),
                cost_value=a.cost_value,
                reversible=a.reversible,
                description=a.description,
            )
            for a in modelo.alternatives
        ),
        burden_entries=tuple(
            (PredictiveAlternativeKind(e.alternative.value), _vector(e.vector))
            for e in modelo.burden_entries
        ),
        materiality_required_scope=tuple(modelo.materiality_required_scope),
        required_protection_identifiers=tuple(modelo.required_protection_identifiers),
        protection_inventory_reference=modelo.protection_inventory_reference,
        asymmetry_justification=modelo.asymmetry_justification,
    )


def to_ready_item(modelo: dto.PublicReadyItem) -> PredictiveReadyEvaluationItem:
    """Decodifica, valida canonicidade pelo mecanismo do servidor e constrói."""
    payload = decode_canonical_piap_transport(modelo.canonical_piap_transport)
    envelope: PiapEnvelope = deserialize_piap_envelope(payload)
    return PredictiveReadyEvaluationItem(
        envelope=envelope,
        context=to_evaluation_context(modelo.evaluation_context),
    )


def to_upstream_unavailable_input(
    modelo: dto.PublicUpstreamUnavailableItem,
) -> PredictiveUpstreamUnavailableInput:
    return PredictiveUpstreamUnavailableInput(reference=modelo.reference, reason=modelo.reason)


def to_internal_request(
    request: dto.PublicEvaluationRequest,
) -> tuple[PredictiveEvaluationRequest, tuple[PredictiveGovernedQualityInput | None, ...]]:
    """Constrói o `PredictiveEvaluationRequest` canônico e as governadas alinhadas.

    Devolver tuplas cruas contornaria os tetos de lote: `8/512` só incidem no
    construtor canônico. A R1 rejeitada parava nas tuplas.

    ```text
    RAW_TUPLE != PREDICTIVE_EVALUATION_REQUEST
    DOCUMENTED_CANONICAL_LIMIT_WITHOUT_CONSTRUCTOR_EDGE = BYPASS
    ```

    As constantes `8` e `512` **não** são reproduzidas aqui: quem as aplica é
    `PredictiveEvaluationRequest.__post_init__`.
    """
    itens: list[PredictiveReadyEvaluationItem | PredictiveUpstreamUnavailableInput] = []
    governadas: list[PredictiveGovernedQualityInput | None] = []
    for modelo in request.items:
        if isinstance(modelo, dto.PublicReadyItem):
            itens.append(to_ready_item(modelo))
            governadas.append(to_governed_quality_input(modelo.governed_quality))
        else:
            itens.append(to_upstream_unavailable_input(modelo))
            governadas.append(None)
    canonica = PredictiveEvaluationRequest(items=tuple(itens))
    if len(canonica.items) != len(governadas):
        raise PublicContractMappingError(
            f"cardinalidade divergente: {len(canonica.items)} itens e "
            f"{len(governadas)} entradas governadas"
        )
    return canonica, tuple(governadas)


# --- saída: desfechos internos -> DTO público ------------------------------


def _uncertainty(par: tuple[float, float]) -> dto.PublicUncertaintyView:
    return dto.PublicUncertaintyView(lower=par[0], upper=par[1])


def _claim_view(claim: PredictiveClaim) -> dto.PublicClaimView:
    return dto.PublicClaimView(
        target=claim.target,
        signal=claim.signal,
        horizon_microseconds=int(claim.horizon / timedelta(microseconds=1)),
        reference_time=claim.reference_time,
        subject_key=claim.subject_key,
    )


def _registry_view(registry: PredictiveChannelRegistry) -> dto.PublicChannelRegistryView:
    return dto.PublicChannelRegistryView(
        channels=tuple(dto.PublicChannelView(name=c.name, lag=c.lag) for c in registry.channels),
        estimator_library=tuple(registry.estimator_library),
    )


def _observation_views(
    observacoes: tuple[PredictiveObservation, ...]
) -> tuple[dto.PublicObservationView, ...]:
    return tuple(
        dto.PublicObservationView(
            reference=o.reference, provenance=o.provenance, relevance_score=o.relevance_score
        )
        for o in observacoes
    )


def _provenance_view(provenance: PredictiveProvenance) -> dto.PublicProvenanceView:
    validade = provenance.historical_validity
    return dto.PublicProvenanceView(
        registry=_registry_view(provenance.registry),
        a_rel=provenance.a_rel,
        historical_validity=dto.PublicHistoricalValidityView(
            valid_window=_observation_views(validade.valid_window),
            historical_kernel=_observation_views(validade.historical_kernel),
            rho_min=validade.rho_min,
        ),
    )


def _regime_view(regime: PredictiveRegimeAssessment) -> dto.PublicRegimeAssessmentView:
    return dto.PublicRegimeAssessmentView(
        status=dto.PublicRegimeStatus(regime.status.value),
        d_regime=regime.d_regime,
        theta=regime.theta,
        beats_fluctuation=regime.beats_fluctuation,
        high_prediction_error=regime.high_prediction_error,
        model_disagreement=regime.model_disagreement,
    )


def _evidence_view(evidencia: PredictivePowerOutcome) -> dto.PublicPowerOutcomeView:
    return dto.PublicPowerOutcomeView(
        a_minus=evidencia.a_minus,
        a_upper=evidencia.a_upper,
        a_star_worst=evidencia.a_star_worst,
        mean_gain=evidencia.mean_gain,
        placebo_p=evidencia.placebo_p,
        g_real=evidencia.g_real,
        g_shuffled_p95=evidencia.g_shuffled_p95,
        sample_size=evidencia.sample_size,
        alpha_corrected=evidencia.alpha_corrected,
    )


def _horizon_points(
    pontos: tuple[PredictiveHorizonPoint, ...]
) -> tuple[dto.PublicHorizonPointView, ...]:
    return tuple(
        dto.PublicHorizonPointView(
            horizon=p.horizon,
            a_minus=p.a_minus,
            gates_pass=p.gates_pass,
            regime=dto.PublicRegimeStatus(p.regime.value),
        )
        for p in pontos
    )


def _horizon_view(espectro: PredictiveHorizonSpectrum) -> dto.PublicHorizonSpectrumView:
    return dto.PublicHorizonSpectrumView(
        h_pred=_horizon_points(espectro.h_pred),
        delta_cont=_horizon_points(espectro.delta_cont),
        r_pred=_horizon_points(espectro.r_pred),
    )


def _key_view(chave: PredictiveComparabilityKey) -> dto.PublicComparabilityKeyView:
    return dto.PublicComparabilityKeyView(
        target=chave.target,
        population=chave.population,
        jurisdiction=chave.jurisdiction,
        horizon=chave.horizon,
        regime=chave.regime,
        unit=chave.unit,
    )


def _conflict_view(conflito: PredictiveConflictAssessment) -> dto.PublicConflictAssessmentView:
    return dto.PublicConflictAssessmentView(
        status=dto.PublicConflictStatus(conflito.status.value),
        compared=tuple(
            dto.PublicComparedClaimView(
                subject_key=c.evaluation.claim.subject_key,
                conclusion_signature=c.conclusion_signature,
                key=_key_view(c.key),
                state=dto.PublicEpistemicState(c.evaluation.state.value),
            )
            for c in conflito.compared
        ),
        incommensurable_dimensions=tuple(conflito.incommensurable_dimensions),
        preserved_non_evaluated_count=len(conflito.preserved_non_evaluated),
        reason=conflito.reason,
    )


def _candidate_views(
    candidatos: tuple[PredictiveProtectionCandidate, ...]
) -> tuple[dto.PublicProtectionCandidateView, ...]:
    return tuple(
        dto.PublicProtectionCandidateView(
            identifier=c.identifier,
            reason=c.reason,
            provenance=c.provenance,
            materiality=dto.PublicMaterialityStatus(c.materiality.value),
            classification_reason=c.classification_reason,
            owner=c.owner,
            authority_reference=None if c.authority is None else c.authority.reference,
            time_window=c.time_window,
            reversibility=c.reversibility,
            triggers=tuple(c.triggers),
            incompatible_with=tuple(c.incompatible_with),
        )
        for c in candidatos
    )


def _quality_view(
    qualidade: PredictiveRecommendationQualityResult,
) -> dto.PublicRecommendationQualityView:
    protecao = qualidade.protection
    return dto.PublicRecommendationQualityView(
        guidance_outcome=dto.PublicGuidanceOutcome(qualidade.guidance_outcome.value),
        disposition=dto.PublicGuidanceDisposition(qualidade.disposition.value),
        complete_answer_allowed=qualidade.complete_answer_allowed,
        procedural_detail_allowed=qualidade.procedural_detail_allowed,
        reason=qualidade.reason,
        protection=dto.PublicProtectionSummaryView(
            accepted=_candidate_views(protecao.accepted),
            rejected=_candidate_views(protecao.rejected),
            unresolved=_candidate_views(protecao.unresolved),
            complete_answer_allowed=protecao.complete_answer_allowed,
            coverage_unresolved_reason=protecao.coverage_unresolved_reason,
        ),
    )


def _assertiveness_view(assertividade: PredictiveAssertiveness) -> dto.PublicAssertivenessView:
    return dto.PublicAssertivenessView(
        candidate_conclusion=assertividade.candidate_conclusion,
        decisive_constraint=assertividade.decisive_constraint,
        uncertainty=_uncertainty(assertividade.uncertainty),
        authority_state=dto.PublicAuthorityState(assertividade.authority_state.value),
        next_governed_route=assertividade.next_governed_route,
        review_or_stop_trigger=assertividade.review_or_stop_trigger,
    )


def from_scientific_outcome(outcome: object) -> dto.PublicScientificOutcome:
    if isinstance(outcome, PredictiveUpstreamUnavailableOutcome):
        return dto.PublicUpstreamUnavailableView(
            reference=outcome.source.reference, reason=outcome.source.reason
        )
    if isinstance(outcome, PredictiveCausalRejectionResult):
        return dto.PublicCausalRejectionView(
            subject_key=outcome.claim.subject_key, reason=outcome.reason
        )
    if isinstance(outcome, PredictiveClaimEvaluationResult):
        return dto.PublicClaimEvaluationView(
            claim=_claim_view(outcome.claim),
            provenance=_provenance_view(outcome.provenance),
            regime=_regime_view(outcome.regime),
            evidence=_evidence_view(outcome.evidence),
            uncertainty=_uncertainty(outcome.uncertainty),
            horizon=_horizon_view(outcome.horizon),
            state=dto.PublicEpistemicState(PredictiveEpistemicState(outcome.state).value),
            approval_validation_outcome=dto.PublicApprovalValidationOutcome(
                outcome.approval_validation_outcome.value
            ),
        )
    raise PublicContractMappingError(
        f"desfecho científico não representável: {type(outcome).__name__}"
    )


def from_routing_outcome(outcome: object) -> dto.PublicRoutingOutcome:
    if isinstance(outcome, PredictiveUpstreamUnavailableRoutingResult):
        return dto.PublicUpstreamUnavailableRoutingView(
            source_reference=outcome.source_reference, reason=outcome.reason
        )
    if isinstance(outcome, PredictiveCausalRejectedRoutingResult):
        return dto.PublicCausalRejectedRoutingView(
            subject_key=outcome.subject_key, reason=outcome.reason
        )
    if isinstance(outcome, PredictiveFinalRoutingResult):
        return dto.PublicFinalRoutingView(
            route=(
                None
                if outcome.route is None
                else dto.PublicRoute(PredictiveRoute(outcome.route).value)
            ),
            abstained=outcome.abstained,
            recommended_alternative=(
                None
                if outcome.recommended_alternative is None
                else dto.PublicAlternativeKind(outcome.recommended_alternative.value)
            ),
            conflict_assessment=_conflict_view(outcome.conflict_assessment),
            limits=tuple(outcome.limits),
            reason=outcome.reason,
            assertiveness=_assertiveness_view(outcome.assertiveness),
            revalidated_route=outcome.revalidated_route,
            quality=_quality_view(outcome.quality),
        )
    raise PublicContractMappingError(
        f"desfecho de roteamento não representável: {type(outcome).__name__}"
    )


def to_public_response(
    evaluation: PredictiveEvaluationBatchResult,
    routing: PredictiveRoutingBatchResult,
) -> dto.PublicEvaluationResponse:
    """Consome os batch results TIPADOS, não tuplas soltas.

    Preserva `request_length`, posições e `decomposed_conflict_dimensions`.
    """
    if not isinstance(evaluation, PredictiveEvaluationBatchResult):
        raise PublicContractMappingError(
            f"evaluation deve ser PredictiveEvaluationBatchResult, "
            f"recebido {type(evaluation).__name__}"
        )
    if not isinstance(routing, PredictiveRoutingBatchResult):
        raise PublicContractMappingError(
            f"routing deve ser PredictiveRoutingBatchResult, " f"recebido {type(routing).__name__}"
        )
    scientific_outcomes = evaluation.outcomes
    routing_outcomes = routing.outcomes
    if len(scientific_outcomes) != len(routing_outcomes):
        raise PublicContractMappingError(
            f"cardinalidade divergente: {len(scientific_outcomes)} científicos e "
            f"{len(routing_outcomes)} de roteamento"
        )
    if evaluation.request_length != routing.request_length:
        raise PublicContractMappingError(
            f"request_length divergente: {evaluation.request_length} e " f"{routing.request_length}"
        )
    return dto.PublicEvaluationResponse(
        request_length=evaluation.request_length,
        decomposed_conflict_dimensions=tuple(routing.decomposed_conflict_dimensions),
        items=tuple(
            dto.PublicEvaluationResultItem(
                position=posicao,
                scientific=from_scientific_outcome(cientifico),
                routing=from_routing_outcome(roteamento),
            )
            for posicao, (cientifico, roteamento) in enumerate(
                zip(scientific_outcomes, routing_outcomes, strict=True)
            )
        ),
    )
