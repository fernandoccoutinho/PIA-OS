"""`E5.r` — vetor de ônus de seis dimensões **por alternativa** `A0`/`A1`/`A2`.

```text
NO_SUM · NO_SCORE · NO_MONETIZATION · NO_AUTOMATIC_WEIGHT
TOTAL_BURDEN_VECTOR != L_total
UNVALIDATED_PROBABILITY -> EXPECTED_LOSS = FORBIDDEN
```
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.predictive_accessibility.counterfactual import (
    PredictiveAlternativeKind,
    PredictiveCounterfactualSet,
)


class PredictiveBurdenDimensionKind(StrEnum):
    FINANCIAL_RESOURCES = "financial_resources"
    SOCIAL_HUMAN = "social_human"
    CRITICAL_SERVICE_CONTINUITY = "critical_service_continuity"
    DISTRIBUTION_EQUITY = "distribution_equity"
    OPPORTUNITY_DELAY = "opportunity_delay"
    IRREVERSIBILITY_RECOVERY = "irreversibility_recovery"


class PredictiveProbabilityValidation(StrEnum):
    VALIDATED = "validated"
    NOT_VALIDATED = "not_validated"


class PredictiveExpectedLossError(ValueError):
    """Perda esperada numérica inválida: probabilidade não validada ou fora de [0,1]."""


class PredictiveIncomparableBurdenError(ValueError):
    """Dimensões não comparáveis: unidade, fonte, versão ou tempo divergentes."""


@dataclass(frozen=True)
class PredictiveBurdenDimension:
    kind: PredictiveBurdenDimensionKind
    magnitude: float
    unit: str
    source: str
    source_version: int
    observed_at: str
    uncertainty: tuple[float, float]
    incidence: str
    vulnerable_incidence: bool = False

    def __post_init__(self) -> None:
        if not self.unit or not self.source or not self.incidence:
            raise ValueError("dimensão exige unidade, fonte e incidência")


@dataclass(frozen=True)
class PredictiveTotalBurdenVector:
    dimensions: tuple[PredictiveBurdenDimension, ...]
    probability_validation: PredictiveProbabilityValidation

    def __post_init__(self) -> None:
        tipos = [d.kind for d in self.dimensions]
        if set(tipos) != set(PredictiveBurdenDimensionKind) or len(tipos) != len(set(tipos)):
            raise ValueError("o vetor exige exatamente as seis dimensões, sem repetição")

    @property
    def magnitudes(self) -> dict[PredictiveBurdenDimensionKind, float]:
        return {d.kind: d.magnitude for d in self.dimensions}

    @property
    def touches_vulnerable(self) -> bool:
        return any(d.vulnerable_incidence for d in self.dimensions)

    def comparability_failure(self, other: PredictiveTotalBurdenVector) -> str | None:
        """Antes de Pareto: unidade, fonte, versão e tempo têm de coincidir."""
        meus = {d.kind: d for d in self.dimensions}
        outros = {d.kind: d for d in other.dimensions}
        for kind in PredictiveBurdenDimensionKind:
            a, c = meus[kind], outros[kind]
            for campo in ("unit", "source", "source_version", "observed_at"):
                if getattr(a, campo) != getattr(c, campo):
                    return f"{kind.value}: {campo} divergente"
        return None

    def dominates(self, other: PredictiveTotalBurdenVector) -> bool:
        """Pareto: ônus maior ou igual em tudo, e estritamente maior em algo."""
        falha = self.comparability_failure(other)
        if falha is not None:
            raise PredictiveIncomparableBurdenError(falha)
        meus, outros = self.magnitudes, other.magnitudes
        return all(meus[k] >= outros[k] for k in meus) and any(meus[k] > outros[k] for k in meus)

    def trade_offs(
        self, other: PredictiveTotalBurdenVector
    ) -> tuple[PredictiveBurdenDimensionKind, ...]:
        falha = self.comparability_failure(other)
        if falha is not None:
            raise PredictiveIncomparableBurdenError(falha)
        meus, outros = self.magnitudes, other.magnitudes
        maiores = {k for k in meus if meus[k] > outros[k]}
        menores = {k for k in meus if meus[k] < outros[k]}
        if maiores and menores:
            return tuple(sorted(maiores | menores, key=lambda k: k.value))
        return ()

    def expected_loss(self, probability: float) -> float:
        if self.probability_validation is not PredictiveProbabilityValidation.VALIDATED:
            raise PredictiveExpectedLossError(
                "probabilidade não validada não pode gerar perda esperada numérica"
            )
        if not 0.0 <= probability <= 1.0:
            raise PredictiveExpectedLossError(
                f"probabilidade fora de [0,1]: {probability}. O rótulo de validação "
                "não autoriza valor impossível"
            )
        financeira = next(
            d
            for d in self.dimensions
            if d.kind is PredictiveBurdenDimensionKind.FINANCIAL_RESOURCES
        )
        return probability * financeira.magnitude


@dataclass(frozen=True)
class PredictiveBurdenComparison:
    """Um vetor por alternativa, mais as relações de Pareto entre elas."""

    counterfactual: PredictiveCounterfactualSet
    entries: tuple[tuple[PredictiveAlternativeKind, PredictiveTotalBurdenVector], ...]
    dominated: tuple[PredictiveAlternativeKind, ...]
    trade_off_pairs: tuple[tuple[PredictiveAlternativeKind, PredictiveAlternativeKind], ...]
    incomparable: tuple[str, ...]

    def __post_init__(self) -> None:
        tipos = [k for k, _ in self.entries]
        if set(tipos) != set(PredictiveAlternativeKind) or len(tipos) != len(set(tipos)):
            raise ValueError("é preciso um vetor de ônus por alternativa A0, A1 e A2")

    @property
    def vectors(self) -> dict[PredictiveAlternativeKind, PredictiveTotalBurdenVector]:
        """Cópia. Nenhuma referência mutável sobrevive à construção."""
        return dict(self.entries)

    def is_dominated(self, kind: PredictiveAlternativeKind) -> bool:
        return kind in self.dominated

    @property
    def non_dominated(self) -> tuple[PredictiveAlternativeKind, ...]:
        return tuple(k for k in PredictiveAlternativeKind if k not in self.dominated)


def predictive_burden_comparison(
    counterfactual: PredictiveCounterfactualSet,
    entries: tuple[tuple[PredictiveAlternativeKind, PredictiveTotalBurdenVector], ...],
) -> PredictiveBurdenComparison:
    """Sem soma e sem peso: só dominância de Pareto e cruzamentos.

    Incomparabilidade vira limite explícito, jamais comparação numérica.
    """
    mapa = dict(entries)
    dominadas: list[PredictiveAlternativeKind] = []
    cruzamentos: list[tuple[PredictiveAlternativeKind, PredictiveAlternativeKind]] = []
    incomparaveis: list[str] = []
    for a in PredictiveAlternativeKind:
        for b in PredictiveAlternativeKind:
            if a is b:
                continue
            falha = mapa[a].comparability_failure(mapa[b])
            if falha is not None:
                aviso = f"{a.value} vs {b.value}: {falha}"
                if aviso not in incomparaveis:
                    incomparaveis.append(aviso)
                continue
            if mapa[a].dominates(mapa[b]) and a not in dominadas:
                dominadas.append(a)
            if mapa[a].trade_offs(mapa[b]) and (b, a) not in cruzamentos:
                cruzamentos.append((a, b))
    return PredictiveBurdenComparison(
        counterfactual=counterfactual,
        entries=tuple(entries),
        dominated=tuple(dominadas),
        trade_off_pairs=tuple(cruzamentos),
        incomparable=tuple(incomparaveis),
    )
