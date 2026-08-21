"""`E5.q` — contrafactual `A0`/`A1`/`A2` governado por `E5.n`, `E5.o` e `E5.p`.

```text
A0 = inação ou curso atual · A1 = ação escalonada REVERSÍVEL · A2 = ação plena
UNKNOWN_INACTION_COST != ZERO
INVALID_GUIDANCE -> NO_PROCEDURAL_ENDORSEMENT
UNRESOLVED_PROTECTION -> NO_COMPLETE_ANSWER
```
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.predictive_accessibility.assertiveness import PredictiveAssertiveness
from app.predictive_accessibility.guidance import (
    PredictiveGuidanceOutcome,
    PredictiveRecommendationQualityResult,
)
from app.predictive_accessibility.predictive_claim_conflict import PredictiveComparabilityKey
from app.predictive_accessibility.protection import PredictiveProtectionSet


class PredictiveAlternativeKind(StrEnum):
    A0_INACTION = "a0_inaction"
    A1_REVERSIBLE_ESCALATION = "a1_reversible_escalation"
    A2_FULL_ACTION = "a2_full_action"


class PredictiveCostKnowledge(StrEnum):
    KNOWN = "known"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class PredictiveAlternative:
    kind: PredictiveAlternativeKind
    key: PredictiveComparabilityKey
    cost_knowledge: PredictiveCostKnowledge
    cost_value: float | None
    reversible: bool
    description: str

    def __post_init__(self) -> None:
        if self.cost_knowledge is PredictiveCostKnowledge.UNKNOWN and (self.cost_value is not None):
            raise ValueError("custo desconhecido não pode carregar valor numérico")
        if self.kind is PredictiveAlternativeKind.A1_REVERSIBLE_ESCALATION and (
            not self.reversible
        ):
            raise ValueError("A1 precisa ser reversível")


@dataclass(frozen=True)
class PredictiveCounterfactualSet:
    """As três alternativas mais o que a qualidade permite endossar."""

    alternatives: tuple[PredictiveAlternative, ...]
    asymmetry_justification: str | None
    assertiveness: PredictiveAssertiveness
    protection: PredictiveProtectionSet
    quality: PredictiveRecommendationQualityResult
    procedural_endorsement_allowed: bool
    complete_answer_allowed: bool
    reason: str

    def __post_init__(self) -> None:
        tipos = {a.kind for a in self.alternatives}
        if tipos != set(PredictiveAlternativeKind):
            raise ValueError("contrafactual exige A0, A1 e A2")
        if len({a.key for a in self.alternatives}) > 1 and not self.asymmetry_justification:
            raise ValueError("comparação assimétrica exige justificativa explícita")

    def of(self, kind: PredictiveAlternativeKind) -> PredictiveAlternative:
        return next(a for a in self.alternatives if a.kind is kind)


def predictive_counterfactual_set(
    alternatives: tuple[PredictiveAlternative, ...],
    *,
    assertiveness: PredictiveAssertiveness,
    protection: PredictiveProtectionSet,
    quality: PredictiveRecommendationQualityResult,
    asymmetry_justification: str | None = None,
) -> PredictiveCounterfactualSet:
    """`E5.p` bloqueia endosso procedimental; `E5.o` bloqueia resposta completa."""
    endosso = quality.guidance_outcome is PredictiveGuidanceOutcome.VALID
    completo = protection.complete_answer_allowed
    if not endosso:
        motivo = f"orientação {quality.guidance_outcome.value}: sem endosso procedimental"
    elif not completo:
        motivo = "ramo protetivo não resolvido: resposta não pode ser declarada completa"
    else:
        motivo = "A0, A1 e A2 comparadas com orientação vigente e proteção resolvida"
    return PredictiveCounterfactualSet(
        alternatives=alternatives,
        asymmetry_justification=asymmetry_justification,
        assertiveness=assertiveness,
        protection=protection,
        quality=quality,
        procedural_endorsement_allowed=endosso,
        complete_answer_allowed=completo,
        reason=motivo,
    )
