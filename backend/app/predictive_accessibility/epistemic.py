"""`E5.j` — três estados epistêmicos e o `CLAIM_EVALUATION_RESULT`.

`E5.j` **monta**, não interpreta, e nunca produz rejeição causal.

```text
PREDICTABLE                 A- > 0 E gates confirmatórios = PASS
UNRESOLVED                  A- <= 0 E A*_worst >= A_rel
PREDICTIVELY_INACCESSIBLE   A- <= 0 E A*_worst <  A_rel, relativo a (C,S,Δ,A_rel)

PROIBIDO  UNRESOLVED -> PREDICTIVELY_INACCESSIBLE por baixa potência
```
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.predictive_accessibility.channel import PredictiveChannelRegistry
from app.predictive_accessibility.claim import PredictiveClaim
from app.predictive_accessibility.history import PredictiveHistoricalValidity
from app.predictive_accessibility.horizon import PredictiveHorizonSpectrum
from app.predictive_accessibility.piap.enums import ApprovalValidationOutcome
from app.predictive_accessibility.power import PredictivePowerOutcome
from app.predictive_accessibility.regime import PredictiveRegimeAssessment


class PredictiveEpistemicState(StrEnum):
    """Estado por alegação. Sempre relativo a `(C, S, horizonte, A_rel)`."""

    PREDICTABLE = "predictable"
    UNRESOLVED = "unresolved"
    PREDICTIVELY_INACCESSIBLE = "predictively_inaccessible"


@dataclass(frozen=True)
class PredictiveProvenance:
    """Proveniência da avaliação: quem produziu, sobre qual biblioteca."""

    registry: PredictiveChannelRegistry
    a_rel: float
    historical_validity: PredictiveHistoricalValidity


@dataclass(frozen=True)
class PredictiveClaimEvaluationResult:
    """`CLAIM_EVALUATION_RESULT` — oito componentes, nenhum opcional."""

    claim: PredictiveClaim
    provenance: PredictiveProvenance
    regime: PredictiveRegimeAssessment
    evidence: PredictivePowerOutcome
    uncertainty: tuple[float, float]
    horizon: PredictiveHorizonSpectrum
    state: PredictiveEpistemicState
    approval_validation_outcome: ApprovalValidationOutcome

    def __post_init__(self) -> None:
        for nome in (
            "claim",
            "provenance",
            "regime",
            "evidence",
            "uncertainty",
            "horizon",
            "state",
            "approval_validation_outcome",
        ):
            if getattr(self, nome) is None:
                raise ValueError(f"{nome} é componente obrigatório do CLAIM_EVALUATION_RESULT")


def predictive_classify_epistemic_state(
    evidence: PredictivePowerOutcome, *, a_rel: float, confirmatory_pass: bool
) -> PredictiveEpistemicState:
    if evidence.a_minus > 0.0:
        if not confirmatory_pass:
            return PredictiveEpistemicState.UNRESOLVED
        return PredictiveEpistemicState.PREDICTABLE
    if evidence.a_star_worst >= a_rel:
        return PredictiveEpistemicState.UNRESOLVED
    return PredictiveEpistemicState.PREDICTIVELY_INACCESSIBLE


def predictive_assemble_claim_evaluation_result(
    *,
    claim: PredictiveClaim,
    registry: PredictiveChannelRegistry,
    evidence: PredictivePowerOutcome,
    approval_validation_outcome: ApprovalValidationOutcome,
    a_rel: float,
    confirmatory_pass: bool,
    regime: PredictiveRegimeAssessment,
    horizon: PredictiveHorizonSpectrum,
    historical_validity: PredictiveHistoricalValidity,
) -> PredictiveClaimEvaluationResult:
    return PredictiveClaimEvaluationResult(
        claim=claim,
        provenance=PredictiveProvenance(
            registry=registry, a_rel=a_rel, historical_validity=historical_validity
        ),
        regime=regime,
        evidence=evidence,
        uncertainty=(evidence.a_minus, evidence.a_upper),
        horizon=horizon,
        state=predictive_classify_epistemic_state(
            evidence, a_rel=a_rel, confirmatory_pass=confirmatory_pass
        ),
        approval_validation_outcome=approval_validation_outcome,
    )
