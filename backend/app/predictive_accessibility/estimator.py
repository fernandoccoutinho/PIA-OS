"""Estimador: baseline Gaussiana marginal, candidato AR(1) por OLS, ganho.

Ajuste **somente** no treino. O bloco cego não participa de ajuste, seleção
ou mudança de limiar.

```text
TRAIN_ONLY_FIT = REQUIRED
BLIND_BLOCK_TOUCHES_NOTHING_BUT_SCORING = TRUE
```
"""

from __future__ import annotations

import math
from dataclasses import dataclass

_LOG_2PI = math.log(2.0 * math.pi)


@dataclass(frozen=True)
class PredictiveBaselineModel:
    """Gaussiana marginal: média e variância amostral dos alvos do treino."""

    mean: float
    variance: float

    def log_density(self, target: float) -> float:
        return -0.5 * (
            _LOG_2PI + math.log(self.variance) + (target - self.mean) ** 2 / self.variance
        )


@dataclass(frozen=True)
class PredictiveAr1Model:
    """AR(1) Gaussiano: intercepto e coeficiente por OLS, resíduo com `n-2`."""

    intercept: float
    coefficient: float
    residual_variance: float

    def log_density(self, target: float, predictor: float) -> float:
        media = self.intercept + self.coefficient * predictor
        return -0.5 * (
            _LOG_2PI
            + math.log(self.residual_variance)
            + (target - media) ** 2 / self.residual_variance
        )


def predictive_fit_baseline(targets: tuple[float, ...]) -> PredictiveBaselineModel:
    n = len(targets)
    if n < 2:
        raise ValueError("baseline exige ao menos duas observações de treino")
    media = math.fsum(targets) / n
    variancia = math.fsum((y - media) ** 2 for y in targets) / (n - 1)
    if variancia <= 0.0:
        raise ValueError("variância do baseline não pode ser nula")
    return PredictiveBaselineModel(mean=media, variance=variancia)


def predictive_fit_ar1(pairs: tuple[tuple[float, float], ...]) -> PredictiveAr1Model:
    """`pairs` são `(preditor, alvo)` do treino, nessa ordem."""
    n = len(pairs)
    if n < 3:
        raise ValueError("AR(1) exige ao menos três pares de treino")
    media_x = math.fsum(x for x, _ in pairs) / n
    media_y = math.fsum(y for _, y in pairs) / n
    sxx = math.fsum((x - media_x) ** 2 for x, _ in pairs)
    if sxx <= 0.0:
        raise ValueError("preditor sem variação: OLS indeterminado")
    sxy = math.fsum((x - media_x) * (y - media_y) for x, y in pairs)
    coeficiente = sxy / sxx
    intercepto = media_y - coeficiente * media_x
    residuos = math.fsum((y - intercepto - coeficiente * x) ** 2 for x, y in pairs)
    variancia = residuos / (n - 2)
    if variancia <= 0.0:
        raise ValueError("variância residual não pode ser nula")
    return PredictiveAr1Model(
        intercept=intercepto, coefficient=coeficiente, residual_variance=variancia
    )


def predictive_per_event_gains(
    baseline: PredictiveBaselineModel,
    candidate: PredictiveAr1Model,
    blind_pairs: tuple[tuple[float, float], ...],
) -> tuple[float, ...]:
    """Ganho por evento, em nats: `log p_AR1(y|x) - log p_baseline(y)`."""
    if not blind_pairs:
        raise ValueError("bloco cego vazio")
    return tuple(candidate.log_density(y, x) - baseline.log_density(y) for x, y in blind_pairs)
