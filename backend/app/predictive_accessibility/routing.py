"""`E5.s` — produtor **único** de `E5_FINAL_ROUTING_RESULT`.

Quatro rotas exatas. `ABSTAIN` e `NO_SAFE_ROUTE` não são membros: sem rota
segura, `route = None`, os limites são explicados e o comportamento é abster-se.

```text
PREDICT · RECONFIGURE · INVESTIGATE · ROBUST
DOMINATED_ALTERNATIVE_IS_NEVER_RECOMMENDED_WITHOUT_A_DECISIVE_CONSTRAINT
REVALIDATION_MAY_ONLY_BE_EQUAL_OR_MORE_CONSERVATIVE
```
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.predictive_accessibility.assertiveness import PredictiveAssertiveness
from app.predictive_accessibility.burden import (
    PredictiveBurdenComparison,
    PredictiveProbabilityValidation,
)
from app.predictive_accessibility.counterfactual import (
    PredictiveAlternativeKind,
    PredictiveCounterfactualSet,
)
from app.predictive_accessibility.epistemic import (
    PredictiveClaimEvaluationResult,
    PredictiveEpistemicState,
)
from app.predictive_accessibility.guidance import (
    PredictiveGuidanceOutcome,
    PredictiveRecommendationQualityResult,
)
from app.predictive_accessibility.piap.enums import ApprovalValidationOutcome
from app.predictive_accessibility.predictive_claim_conflict import (
    PredictiveConflictAssessment,
)
from app.predictive_accessibility.reconfiguration import (
    PredictiveEvaluatedReconfigurationOutcome,
    PredictiveReconfigurationDecision,
)


class PredictiveRoute(StrEnum):
    """Exatamente quatro membros. Não existe um quinto."""

    PREDICT = "predict"
    RECONFIGURE = "reconfigure"
    INVESTIGATE = "investigate"
    ROBUST = "robust"


@dataclass(frozen=True)
class PredictiveFinalRoutingResult:
    route: PredictiveRoute | None
    abstained: bool
    recommended_alternative: PredictiveAlternativeKind | None
    conflict_assessment: PredictiveConflictAssessment
    limits: tuple[str, ...]
    reason: str
    assertiveness: PredictiveAssertiveness
    revalidated_route: str
    quality: PredictiveRecommendationQualityResult

    def __post_init__(self) -> None:
        if (self.route is None) != self.abstained:
            raise ValueError("route=None e abstained têm de coincidir")
        if self.route is None and not self.limits:
            raise ValueError("abstenção exige explicar os limites")


@dataclass(frozen=True)
class PredictiveUpstreamUnavailableRoutingResult:
    source_reference: str
    reason: str
    route: None = None
    abstained: bool = True
    recommended_alternative: None = None


@dataclass(frozen=True)
class PredictiveCausalRejectedRoutingResult:
    subject_key: str
    reason: str
    route: None = None
    abstained: bool = True
    recommended_alternative: None = None


PredictiveRoutingOutcome = (
    PredictiveFinalRoutingResult
    | PredictiveUpstreamUnavailableRoutingResult
    | PredictiveCausalRejectedRoutingResult
)

_CONSERVADORISMO = {"predict": 0, "reconfigure": 1, "robust": 2, "investigate": 3}


def _escolher_alternativa(
    counterfactual: PredictiveCounterfactualSet,
    burden: PredictiveBurdenComparison,
    limites: list[str],
) -> PredictiveAlternativeKind | None:
    """Recomenda **apenas** a única não dominada. Empate não vira preferência.

    A R1 escolhia A1 sempre que ela não estivesse dominada, mesmo com A0, A1 e
    A2 simultaneamente não dominadas — preferência inventada, sem critério
    autorizado no contrato.

    ```text
    TIE_IS_NOT_A_PREFERENCE
    NO_VALID_GUIDANCE -> NO_RECOMMENDED_ALTERNATIVE
    ```
    """
    if not counterfactual.complete_answer_allowed:
        limites.append("resposta protetiva incompleta: nenhuma alternativa recomendada")
        return None
    if not counterfactual.procedural_endorsement_allowed:
        limites.append(
            f"orientação {counterfactual.quality.guidance_outcome.value}: "
            "nenhuma alternativa recomendada"
        )
        return None
    if burden.incomparable:
        limites.append(f"ônus incomparável: {burden.incomparable[0]}")
        return None
    candidatas = burden.non_dominated
    if not candidatas:
        limites.append("todas as alternativas dominadas: nenhuma recomendação")
        return None
    if len(candidatas) > 1:
        nomes = ", ".join(k.value for k in candidatas)
        limites.append(
            f"mais de uma alternativa não dominada ({nomes}): sem critério decisivo "
            "governado, nenhuma é recomendada"
        )
        return None
    unica = candidatas[0]
    if unica is PredictiveAlternativeKind.A0_INACTION:
        limites.append("A0 preservada como única legitimamente não dominada")
    elif unica is PredictiveAlternativeKind.A1_REVERSIBLE_ESCALATION:
        if not counterfactual.of(unica).reversible:
            limites.append("A1 não reversível: não recomendada")
            return None
        limites.append("A1 reversível preservada como única não dominada")
    return unica


def predictive_final_routing(
    *,
    evaluation: PredictiveClaimEvaluationResult,
    reconfiguration: PredictiveEvaluatedReconfigurationOutcome | None,
    assertiveness: PredictiveAssertiveness,
    quality: PredictiveRecommendationQualityResult,
    counterfactual: PredictiveCounterfactualSet,
    burden: PredictiveBurdenComparison,
    conflict_assessment: PredictiveConflictAssessment,
) -> PredictiveFinalRoutingResult:
    limites: list[str] = []
    if conflict_assessment.blocks_safe_route:
        limites.append(f"conflito real entre alegações: {conflict_assessment.reason}")
    if conflict_assessment.incommensurable_dimensions:
        limites.append(
            "alegações incomensuráveis permanecem decompostas em "
            + ", ".join(conflict_assessment.incommensurable_dimensions)
        )
    aprovado = evaluation.approval_validation_outcome is ApprovalValidationOutcome.VALID
    if not aprovado:
        limites.append(
            f"aprovação {evaluation.approval_validation_outcome.value}: ROBUST bloqueado"
        )
    if not quality.complete_answer_allowed:
        limites.append("ramo protetivo UNRESOLVED impede resposta completa")
    if quality.guidance_outcome is not PredictiveGuidanceOutcome.VALID:
        limites.append(f"orientação {quality.guidance_outcome.value}: sem detalhe procedimental")
    if any(
        v.probability_validation is PredictiveProbabilityValidation.NOT_VALIDATED
        for _, v in burden.entries
    ):
        limites.append("probabilidade não validada: sem perda esperada numérica")
    if burden.trade_off_pairs:
        limites.append("há trade-offs entre alternativas; não há dominância total")
    if any(v.touches_vulnerable for _, v in burden.entries):
        limites.append("incidência sobre população vulnerável preservada")

    alternativa = _escolher_alternativa(counterfactual, burden, limites)

    def entregar(rota: PredictiveRoute | None, motivo: str) -> PredictiveFinalRoutingResult:
        revalidada = assertiveness.next_governed_route
        if rota is not None and _CONSERVADORISMO.get(rota.value, 9) > _CONSERVADORISMO.get(
            revalidada, 9
        ):
            revalidada = rota.value
        if rota is None and not limites:
            limites.append("nenhuma rota segura disponível")
        return PredictiveFinalRoutingResult(
            route=rota,
            abstained=rota is None,
            recommended_alternative=None if rota is None else alternativa,
            conflict_assessment=conflict_assessment,
            limits=tuple(limites),
            reason=motivo,
            assertiveness=assertiveness,
            revalidated_route=revalidada,
            quality=quality,
        )

    if conflict_assessment.blocks_safe_route:
        return entregar(None, "conflito real entre alegações: nenhuma rota segura")

    promovido = (
        reconfiguration is not None
        and reconfiguration.decision is PredictiveReconfigurationDecision.PROMOTED
    )
    if promovido and quality.complete_answer_allowed and aprovado:
        return entregar(PredictiveRoute.RECONFIGURE, "reconfiguração promovida e sustentada")
    if evaluation.state is PredictiveEpistemicState.PREDICTABLE:
        return entregar(PredictiveRoute.PREDICT, "estado PREDICTABLE")
    if evaluation.state is PredictiveEpistemicState.UNRESOLVED:
        return entregar(PredictiveRoute.INVESTIGATE, "estado UNRESOLVED")
    if aprovado and quality.complete_answer_allowed:
        return entregar(
            PredictiveRoute.ROBUST,
            "inacessibilidade preditiva com limites legítimos e aprovação válida",
        )
    return entregar(None, "nenhuma rota segura; abster-se")
