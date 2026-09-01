"""`E5.g` — avaliação de regime.

A E5 **não inventa** métrica de distância: recebe `D_regime`, `theta` e o
resultado tipado do teste contra flutuação, todos pré-registrados. Produz
candidato, nunca confirmação, e nunca troca de modelo.

```text
CANDIDATE <=> D_regime > theta AND beats_fluctuation
ERROR_ALONE -> NO_SHIFT ; DISAGREEMENT_ALONE -> NO_SHIFT
CONFIRMED_SHIFT = NOT_PRODUCIBLE_BY_E5_G
```
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class PredictiveRegimeStatus(StrEnum):
    """Vocabulário fechado. `CONFIRMED_SHIFT` não é membro, de propósito."""

    NO_SHIFT = "no_shift"
    REGIME_SHIFT_CANDIDATE = "regime_shift_candidate"


@dataclass(frozen=True)
class PredictiveRegimeAssessment:
    """Distância medida, limiar e o teste contra flutuação, preservados."""

    status: PredictiveRegimeStatus
    d_regime: float
    theta: float
    beats_fluctuation: bool
    high_prediction_error: bool
    model_disagreement: bool


def predictive_regime_assessment(
    *,
    d_regime: float,
    theta: float,
    beats_fluctuation: bool,
    high_prediction_error: bool = False,
    model_disagreement: bool = False,
) -> PredictiveRegimeAssessment:
    candidato = d_regime > theta and beats_fluctuation
    return PredictiveRegimeAssessment(
        status=(
            PredictiveRegimeStatus.REGIME_SHIFT_CANDIDATE
            if candidato
            else PredictiveRegimeStatus.NO_SHIFT
        ),
        d_regime=d_regime,
        theta=theta,
        beats_fluctuation=beats_fluctuation,
        high_prediction_error=high_prediction_error,
        model_disagreement=model_disagreement,
    )
