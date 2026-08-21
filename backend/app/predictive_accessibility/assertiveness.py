"""`E5.n` — conclusão candidata e assertividade **por alegação**.

Assertividade não é confiança: é a conclusão candidata acompanhada da restrição
que a decide, da incerteza, do estado de autoridade, da próxima rota governada
e do gatilho de revisão ou parada.

```text
PER_CLAIM_ASSERTIVENESS != SET_LEVEL_DECISION
E5_S_REVALIDATES_AND_MAY_ONLY_BE_MORE_CONSERVATIVE
```
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.predictive_accessibility.epistemic import (
    PredictiveClaimEvaluationResult,
    PredictiveEpistemicState,
)
from app.predictive_accessibility.piap.enums import ApprovalValidationOutcome


class PredictiveAuthorityState(StrEnum):
    AUTHORIZED = "authorized"
    NOT_AUTHORIZED = "not_authorized"


@dataclass(frozen=True)
class PredictiveAssertiveness:
    """Objeto imutável com os seis componentes obrigatórios."""

    candidate_conclusion: str
    decisive_constraint: str
    uncertainty: tuple[float, float]
    authority_state: PredictiveAuthorityState
    next_governed_route: str
    review_or_stop_trigger: str
    conflict_assessment: object = None

    def __post_init__(self) -> None:
        for nome in (
            "candidate_conclusion",
            "decisive_constraint",
            "next_governed_route",
            "review_or_stop_trigger",
        ):
            if not getattr(self, nome):
                raise ValueError(f"{nome} é componente obrigatório da assertividade")


def predictive_assertiveness(
    evaluation: PredictiveClaimEvaluationResult,
    *,
    candidate_conclusion: str,
    decisive_constraint: str,
    conflict_assessment: object,
) -> PredictiveAssertiveness:
    """`conflict` vem de `E5.m` e é decisivo quando há conflito real."""
    autorizado = evaluation.approval_validation_outcome is ApprovalValidationOutcome.VALID
    rotas = {
        PredictiveEpistemicState.PREDICTABLE: "predict",
        PredictiveEpistemicState.UNRESOLVED: "investigate",
        PredictiveEpistemicState.PREDICTIVELY_INACCESSIBLE: "robust",
    }
    restricao = decisive_constraint
    if getattr(conflict_assessment, "blocks_safe_route", False):
        restricao = f"conflito real entre alegações; {decisive_constraint}"
    return PredictiveAssertiveness(
        candidate_conclusion=candidate_conclusion,
        decisive_constraint=restricao,
        uncertainty=evaluation.uncertainty,
        authority_state=(
            PredictiveAuthorityState.AUTHORIZED
            if autorizado
            else PredictiveAuthorityState.NOT_AUTHORIZED
        ),
        conflict_assessment=conflict_assessment,
        next_governed_route=(
            "investigate"
            if getattr(conflict_assessment, "blocks_safe_route", False)
            else rotas[evaluation.state]
        ),
        review_or_stop_trigger=(
            "revisar ao mudar regime, aprovação ou janela de validade histórica"
        ),
    )
