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
from app.predictive_accessibility import availability as mod_availability
from app.predictive_accessibility import channel as mod_channel
from app.predictive_accessibility import claim as mod_claim
from app.predictive_accessibility import epistemic as mod_epistemic
from app.predictive_accessibility import estimator as mod_estimator
from app.predictive_accessibility import history as mod_history
from app.predictive_accessibility import horizon as mod_horizon
from app.predictive_accessibility import power as mod_power
from app.predictive_accessibility import reconfiguration as mod_reconfiguration
from app.predictive_accessibility import regime as mod_regime
from app.predictive_accessibility.batch import (
    PredictiveEvaluationBatchResult,
    PredictiveEvaluationContext,
    PredictiveEvaluationRequest,
    PredictiveReadyEvaluationItem,
    PredictiveRequestItemOutcome,
    PredictiveUpstreamUnavailableInput,
    PredictiveUpstreamUnavailableOutcome,
)
from app.predictive_accessibility.power import PredictivePowerOutcome

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

    def __post_init__(self) -> None:
        if len(self.evaluation.outcomes) != len(self.reconfiguration):
            raise ValueError("sidecar E5.l deve estar alinhado ao lote externo")


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
    return PredictiveCoordinatedBatchResult(evaluation, tuple(sidecar))
