"""`E5.k` — espectro de horizonte: `H_pred`, `Δ_cont` e `R_pred`.

O espectro **preserva lacunas**. Reduzi-lo a um supremo único apagaria a
descontinuidade, que é justamente o fato interessante.

```text
DISCONTINUOUS_SPECTRUM != SINGLE_SUPREMUM
```
"""

from __future__ import annotations

from dataclasses import dataclass

from app.predictive_accessibility.regime import PredictiveRegimeStatus


@dataclass(frozen=True)
class PredictiveHorizonPoint:
    """Um horizonte já avaliado, com `A⁻`, gates e regime."""

    horizon: int
    a_minus: float
    gates_pass: bool
    regime: PredictiveRegimeStatus

    def __post_init__(self) -> None:
        if self.horizon < 1:
            raise ValueError(f"horizonte deve ser >= 1, recebido {self.horizon}")

    @property
    def admissible(self) -> bool:
        return self.a_minus > 0.0 and self.gates_pass


@dataclass(frozen=True)
class PredictiveHorizonSpectrum:
    """`H_pred`, prefixo contínuo e admissíveis fora dele."""

    h_pred: tuple[PredictiveHorizonPoint, ...]
    delta_cont: tuple[PredictiveHorizonPoint, ...]
    r_pred: tuple[PredictiveHorizonPoint, ...]

    def __post_init__(self) -> None:
        if len(self.delta_cont) + len(self.r_pred) != len(self.h_pred):
            raise ValueError("delta_cont e r_pred devem particionar h_pred")


def predictive_horizon_spectrum(
    points: tuple[PredictiveHorizonPoint, ...],
) -> PredictiveHorizonSpectrum:
    if not points:
        raise ValueError("espectro exige ao menos um horizonte avaliado")
    ordenados = tuple(sorted(points, key=lambda p: p.horizon))
    admissiveis = tuple(p for p in ordenados if p.admissible)
    prefixo: list[PredictiveHorizonPoint] = []
    esperado = ordenados[0].horizon
    for ponto in ordenados:
        if ponto.admissible and ponto.horizon == esperado:
            prefixo.append(ponto)
            esperado += 1
        else:
            break
    contínuo = tuple(prefixo)
    resto = tuple(p for p in admissiveis if p not in contínuo)
    return PredictiveHorizonSpectrum(h_pred=admissiveis, delta_cont=contínuo, r_pred=resto)
