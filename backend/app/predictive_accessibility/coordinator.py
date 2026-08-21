"""Coordenador científico do Patch 3 — despacho e curto-circuito reais.

O curto-circuito vive **aqui**, na produção, e não num `if` reproduzido pelo
teste. As arestas obrigatórias:

```text
UPSTREAM_UNAVAILABLE -> zero ciência
READY_PIAP -> E5.c -> E5.d -> E5.e
CAUSAL_REJECTED      -> zero chamadas E5.f/g/h/i/k/j
CAUSAL_AVAILABLE     -> E5.f/g/h/i/k -> approval validation -> E5.j
```

O sidecar `E5.l` permanece separado do desfecho externo e **não** cria uma
quarta variante por item.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from app.predictive_accessibility import approval_validation as mod_approval
from app.predictive_accessibility import assertiveness as mod_assertiveness
from app.predictive_accessibility import availability as mod_availability
from app.predictive_accessibility import burden as mod_burden
from app.predictive_accessibility import channel as mod_channel
from app.predictive_accessibility import claim as mod_claim
from app.predictive_accessibility import counterfactual as mod_counterfactual
from app.predictive_accessibility import epistemic as mod_epistemic
from app.predictive_accessibility import estimator as mod_estimator
from app.predictive_accessibility import guidance as mod_guidance
from app.predictive_accessibility import history as mod_history
from app.predictive_accessibility import horizon as mod_horizon
from app.predictive_accessibility import power as mod_power
from app.predictive_accessibility import predictive_claim_conflict as mod_conflict_assessment
from app.predictive_accessibility import protection as mod_protection
from app.predictive_accessibility import reconfiguration as mod_reconfiguration
from app.predictive_accessibility import regime as mod_regime
from app.predictive_accessibility import routing as mod_routing
from app.predictive_accessibility.batch import (
    PredictiveEvaluationBatchResult,
    PredictiveEvaluationContext,
    PredictiveEvaluationRequest,
    PredictiveGovernedQualityInput,
    PredictiveReadyEvaluationItem,
    PredictiveRequestItemOutcome,
    PredictiveRoutingBatchResult,
    PredictiveUpstreamUnavailableInput,
    PredictiveUpstreamUnavailableOutcome,
)
from app.predictive_accessibility.epistemic import PredictiveClaimEvaluationResult
from app.predictive_accessibility.piap.authority import ApprovalBinding
from app.predictive_accessibility.power import PredictivePowerOutcome
from app.predictive_accessibility.predictive_claim_conflict import (
    PredictiveConflictAssessment,
)
from app.predictive_accessibility.routing import PredictiveRoutingOutcome

MVP_ESTIMATOR_LIBRARY = ("gaussian_marginal_baseline", "gaussian_ar1_ols")


class PredictiveUnsupportedLibraryError(ValueError):
    """Falha fechada fora da biblioteca finita congelada para o MVP."""


@dataclass(frozen=True)
class PredictiveReconfigurationInstruction:
    """Instrução alinhada ao item; `None` significa nenhuma promoção proposta."""

    candidate: mod_reconfiguration.PredictiveReconfigurationCandidate
    event_id: uuid.UUID
    recorded_at: datetime


@dataclass(frozen=True)
class PredictiveCoordinatedBatchResult:
    """Resultado externo e sidecar interno E5.l, ambos alinhados."""

    evaluation: PredictiveEvaluationBatchResult
    reconfiguration: tuple[mod_reconfiguration.PredictiveReconfigurationOutcome, ...]
    approval_bindings: tuple[ApprovalBinding | None, ...]

    def __post_init__(self) -> None:
        if len(self.evaluation.outcomes) != len(self.reconfiguration):
            raise ValueError("sidecar E5.l deve estar alinhado ao lote externo")
        if len(self.evaluation.outcomes) != len(self.approval_bindings):
            raise ValueError("sidecar de aprovação deve estar alinhado ao lote externo")


@dataclass(frozen=True)
class PredictiveBatchConflictAssessment:
    """Avaliação de conflito alinhada por item e decomposta por chave."""

    per_item: tuple[PredictiveConflictAssessment | None, ...]
    decomposed_dimensions: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.per_item:
            raise ValueError("avaliação de conflito do lote não pode ser vazia")


def predictive_power_outcome_for(
    context: PredictiveEvaluationContext,
) -> PredictivePowerOutcome:
    """Executa E5.h/i no treino e no bloco cego; não aceita evidência pronta."""
    if tuple(context.registry.estimator_library) != MVP_ESTIMATOR_LIBRARY:
        raise PredictiveUnsupportedLibraryError(
            "A_star_worst=max(0,A_upper_AR1) só vale para a biblioteca MVP "
            f"{MVP_ESTIMATOR_LIBRARY}; recebida {tuple(context.registry.estimator_library)}"
        )
    baseline = mod_estimator.predictive_fit_baseline(
        tuple(target for _, target in context.training_pairs)
    )
    candidate = mod_estimator.predictive_fit_ar1(context.training_pairs)
    gains = mod_estimator.predictive_per_event_gains(baseline, candidate, context.blind_pairs)
    a_minus, a_upper = mod_power.predictive_circular_block_bootstrap(
        gains,
        replicates=context.bootstrap_replicates,
        seed=context.bootstrap_seed,
        alpha_corrected=context.alpha_corrected,
    )
    baseline_log = tuple(baseline.log_density(y) for _, y in context.blind_pairs)
    placebo_p, g_real, shuffled_p95 = mod_power.predictive_deterministic_placebo(
        baseline_log,
        candidate.log_density,
        context.blind_pairs,
        permutations=context.placebo_permutations,
        seed=context.placebo_seed,
    )
    return PredictivePowerOutcome(
        a_minus=a_minus,
        a_upper=a_upper,
        a_star_worst=max(0.0, a_upper),
        mean_gain=sum(gains) / len(gains),
        placebo_p=placebo_p,
        g_real=g_real,
        g_shuffled_p95=shuffled_p95,
        sample_size=len(context.blind_pairs),
        alpha_corrected=context.alpha_corrected,
    )


def predictive_evaluate_item(
    item: PredictiveReadyEvaluationItem | PredictiveUpstreamUnavailableInput,
) -> PredictiveRequestItemOutcome:
    """Um desfecho por item, com os curto-circuitos na ordem contratada."""
    if isinstance(item, PredictiveUpstreamUnavailableInput):
        return PredictiveUpstreamUnavailableOutcome(source=item)

    context = item.context
    envelope = item.envelope
    alegacao = mod_claim.predictive_claim_from_envelope(envelope)
    registry = context.registry
    if not isinstance(registry, mod_channel.PredictiveChannelRegistry):
        raise TypeError("registry deve ser PredictiveChannelRegistry")

    disponibilidades = tuple(
        mod_availability.predictive_availability(
            canal, observed_at_offset=context.observed_at_offset
        )
        for canal in registry.channels
    )
    indisponiveis = tuple(d for d in disponibilidades if not d.available)
    if indisponiveis:
        return mod_availability.PredictiveCausalRejectionResult(
            claim=alegacao,
            rejected_channels=indisponiveis,
            reason="nenhum canal com disponibilidade causal no instante de referência",
        )

    validade = mod_history.predictive_historical_validity(
        context.observations, rho_min=context.rho_min
    )
    avaliacao_regime = mod_regime.predictive_regime_assessment(
        d_regime=context.d_regime,
        theta=context.theta,
        beats_fluctuation=context.beats_fluctuation,
        high_prediction_error=context.high_prediction_error,
        model_disagreement=context.model_disagreement,
    )

    evidence = predictive_power_outcome_for(context)
    confirmatory_pass = (
        evidence.placebo_p < context.alpha_corrected and evidence.g_real > evidence.g_shuffled_p95
    )
    espectro = mod_horizon.predictive_horizon_spectrum(context.horizon_points)
    desfecho_aprovacao = mod_approval.predictive_approval_validation(
        envelope,
        at=context.at,
        expected_version=context.expected_version,
        required_scope=context.required_scope,
        expected_jurisdiction=context.expected_jurisdiction,
        expected_binding_kind=context.expected_binding_kind,
    )
    return mod_epistemic.predictive_assemble_claim_evaluation_result(
        claim=alegacao,
        registry=registry,
        evidence=evidence,
        approval_validation_outcome=desfecho_aprovacao,
        a_rel=context.a_rel,
        confirmatory_pass=confirmatory_pass,
        regime=avaliacao_regime,
        horizon=espectro,
        historical_validity=validade,
    )


def predictive_evaluate_batch(
    request: PredictiveEvaluationRequest,
) -> PredictiveEvaluationBatchResult:
    """Mesmo comprimento, mesma ordem, um desfecho por item."""
    return PredictiveEvaluationBatchResult(
        outcomes=tuple(predictive_evaluate_item(item) for item in request.items),
        request_length=len(request.items),
    )


def predictive_evaluate_and_reconfigure_batch(
    request: PredictiveEvaluationRequest,
    instructions: tuple[PredictiveReconfigurationInstruction | None, ...],
    repository: mod_reconfiguration.PredictiveReconfigurationRepositoryPort,
) -> PredictiveCoordinatedBatchResult:
    """Acopla E5.l sem criar uma quarta variante externa por item."""
    if len(instructions) != len(request.items):
        raise ValueError("instruções E5.l devem ter o mesmo comprimento do lote")
    evaluation = predictive_evaluate_batch(request)
    sidecar: list[mod_reconfiguration.PredictiveReconfigurationOutcome] = []
    for item, outcome, instruction in zip(
        request.items, evaluation.outcomes, instructions, strict=True
    ):
        if isinstance(outcome, PredictiveUpstreamUnavailableOutcome):
            sidecar.append(
                mod_reconfiguration.PredictiveUpstreamUnavailableReconfigurationOutcome(
                    source_reference=outcome.source.reference,
                    reason="E5.l não consulta nem escreve quando upstream está indisponível",
                )
            )
            continue
        if isinstance(outcome, mod_availability.PredictiveCausalRejectionResult):
            sidecar.append(
                mod_reconfiguration.PredictiveCausalRejectedReconfigurationOutcome(
                    subject_key=outcome.claim.subject_key,
                    reason="E5.l não consulta nem escreve quando a causalidade foi rejeitada",
                )
            )
            continue
        if instruction is None:
            sidecar.append(
                mod_reconfiguration.PredictiveEvaluatedReconfigurationOutcome(
                    mod_reconfiguration.PredictiveReconfigurationDecision.NOT_APPLICABLE,
                    None,
                    outcome.claim.subject_key,
                    None,
                    "nenhuma promoção foi proposta para o resultado avaliado",
                )
            )
            continue
        if not isinstance(item, PredictiveReadyEvaluationItem):
            raise RuntimeError("outcome avaliado sem ready item correspondente")
        sidecar.append(
            mod_reconfiguration.predictive_reconfiguration_gate(
                evaluation=outcome,
                envelope=item.envelope,
                candidate=instruction.candidate,
                event_id=instruction.event_id,
                recorded_at=instruction.recorded_at,
                repository=repository,
            )
        )
    approval_bindings = tuple(
        (
            item.envelope.authority.approval
            if isinstance(item, PredictiveReadyEvaluationItem)
            and isinstance(outcome, PredictiveClaimEvaluationResult)
            else None
        )
        for item, outcome in zip(request.items, evaluation.outcomes, strict=True)
    )
    return PredictiveCoordinatedBatchResult(evaluation, tuple(sidecar), approval_bindings)


# --- Módulo 4: composição governada de qualidade e roteamento --------------
#
# O curto-circuito e a cadeia causal vivem AQUI, na produção. Um teste que
# reconstruísse a sequência por conta própria não provaria aresta de runtime.
#
#     DOCUMENTED_EDGE_WITHOUT_RUNTIME_EDGE = NOT_AN_EDGE


def predictive_route_item(
    outcome: PredictiveRequestItemOutcome,
    governed: PredictiveGovernedQualityInput | None,
    reconfiguration: mod_reconfiguration.PredictiveReconfigurationOutcome | None,
    approval_binding: ApprovalBinding | None,
    conflict_assessment: PredictiveConflictAssessment | None,
    *,
    at: datetime,
) -> PredictiveRoutingOutcome:
    """Converte UM desfecho científico no desfecho de roteamento tipado.

    ```text
    E5.m -> E5.n -> E5.o -> E5.p -> E5.q -> E5.r -> E5.s
    E5_L_TYPED_OUTCOME vem do SIDECAR, nunca da entrada governada
    ```
    """
    if isinstance(outcome, PredictiveUpstreamUnavailableOutcome):
        return mod_routing.PredictiveUpstreamUnavailableRoutingResult(
            source_reference=outcome.source.reference,
            reason="item indisponível a montante: nenhuma ciência e nenhum roteamento",
        )
    if isinstance(outcome, mod_availability.PredictiveCausalRejectionResult):
        return mod_routing.PredictiveCausalRejectedRoutingResult(
            subject_key=outcome.claim.subject_key,
            reason=outcome.reason,
        )
    if not isinstance(outcome, PredictiveClaimEvaluationResult):
        raise TypeError(f"desfecho científico não reconhecido: {type(outcome).__name__}")
    if governed is None:
        raise ValueError("item avaliado exige entrada governada correspondente")
    if conflict_assessment is None:
        raise ValueError("item avaliado exige avaliação de conflito correspondente")

    assertividade = mod_assertiveness.predictive_assertiveness(
        outcome,
        candidate_conclusion=governed.conclusion_signature,
        decisive_constraint=governed.decisive_constraint,
        conflict_assessment=conflict_assessment,
    )
    protecao = mod_protection.predictive_protection_set(
        governed.protection_candidates,
        assertiveness=assertividade,
        evaluation=outcome,
        approval_binding=approval_binding,
        conflict_assessment=conflict_assessment,
        at=at,
        required_scope=governed.materiality_required_scope,
        required_identifiers=governed.required_protection_identifiers,
        inventory_reference=governed.protection_inventory_reference,
    )
    qualidade = mod_guidance.predictive_recommendation_quality(
        protecao,
        governed.guidance,
        at=at,
        expected_jurisdiction=governed.expected_guidance_jurisdiction,
        expected_version=governed.expected_guidance_version,
    )
    contrafactual = mod_counterfactual.predictive_counterfactual_set(
        governed.alternatives,
        assertiveness=assertividade,
        protection=protecao,
        quality=qualidade,
        asymmetry_justification=governed.asymmetry_justification,
    )
    comparacao = mod_burden.predictive_burden_comparison(contrafactual, governed.burden_entries)
    sidecar = (
        reconfiguration
        if isinstance(
            reconfiguration, mod_reconfiguration.PredictiveEvaluatedReconfigurationOutcome
        )
        else None
    )
    return mod_routing.predictive_final_routing(
        evaluation=outcome,
        reconfiguration=sidecar,
        assertiveness=assertividade,
        quality=qualidade,
        counterfactual=contrafactual,
        burden=comparacao,
        conflict_assessment=conflict_assessment,
    )


def predictive_conflict_for_batch(
    coordinated: PredictiveCoordinatedBatchResult,
    governed_inputs: tuple[PredictiveGovernedQualityInput | None, ...],
) -> PredictiveBatchConflictAssessment:
    """`E5.m` em produção, ANTES de `E5.n`.

    Monta uma alegação comparável por item avaliado e roda a avaliação de
    conflito. Alegações não avaliadas são preservadas, nunca votadas.
    """
    grupos: dict[
        mod_conflict_assessment.PredictiveComparabilityKey,
        list[tuple[int, mod_conflict_assessment.PredictiveComparableClaim]],
    ] = {}
    preservadas: list[tuple[int, object]] = []
    for indice, (desfecho, governado) in enumerate(
        zip(coordinated.evaluation.outcomes, governed_inputs, strict=True)
    ):
        if isinstance(desfecho, PredictiveClaimEvaluationResult) and governado is not None:
            alegacao = mod_conflict_assessment.PredictiveComparableClaim(
                evaluation=desfecho,
                key=governado.comparability_key,
                conclusion_signature=governado.conclusion_signature,
            )
            grupos.setdefault(governado.comparability_key, []).append((indice, alegacao))
        else:
            preservadas.append((indice, desfecho))

    por_item: list[PredictiveConflictAssessment | None] = [
        None for _ in coordinated.evaluation.outcomes
    ]
    for membros in grupos.values():
        avaliacao = mod_conflict_assessment.predictive_conflict_assessment(
            tuple(alegacao for _, alegacao in membros),
            preserved_non_evaluated=tuple(objeto for _, objeto in preservadas),
        )
        for indice, _ in membros:
            por_item[indice] = avaliacao

    dimensoes: set[str] = set()
    chaves = tuple(grupos)
    for indice, esquerda in enumerate(chaves):
        for direita in chaves[indice + 1 :]:
            dimensoes.update(
                mod_conflict_assessment.predictive_incommensurable_dimensions(esquerda, direita)
            )
    return PredictiveBatchConflictAssessment(
        per_item=tuple(por_item),
        decomposed_dimensions=tuple(sorted(dimensoes)),
    )


def predictive_route_batch(
    coordinated: PredictiveCoordinatedBatchResult,
    governed_inputs: tuple[PredictiveGovernedQualityInput | None, ...],
    *,
    at: datetime,
) -> PredictiveRoutingBatchResult:
    """Mesmo comprimento, mesma ordem, um desfecho por item, conflito real.

    Consome o `PredictiveCoordinatedBatchResult` inteiro: avaliação e sidecar
    `E5.l` produzidos juntos. Não existe caminho para o chamador injetar
    promoção.
    """
    desfechos = coordinated.evaluation.outcomes
    if len(governed_inputs) != len(desfechos):
        raise ValueError(
            f"entradas governadas ({len(governed_inputs)}) não alinham com o lote "
            f"({len(desfechos)})"
        )
    conflitos = predictive_conflict_for_batch(coordinated, governed_inputs)
    return PredictiveRoutingBatchResult(
        outcomes=tuple(
            predictive_route_item(
                desfecho,
                governado,
                sidecar,
                approval_binding,
                conflito,
                at=at,
            )
            for desfecho, sidecar, approval_binding, governado, conflito in zip(
                desfechos,
                coordinated.reconfiguration,
                coordinated.approval_bindings,
                governed_inputs,
                conflitos.per_item,
                strict=True,
            )
        ),
        request_length=len(desfechos),
        decomposed_conflict_dimensions=conflitos.decomposed_dimensions,
    )
