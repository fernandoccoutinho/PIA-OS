"""`E5.f` — validade histórica: `V_t` e `K_history`.

Relevância **não** é idade. Uma observação antiga com validade demonstrada
permanece em `V_t`; uma recente sem validade vai para `K_history`, com sua
proveniência preservada.

```text
RECENCY != RELEVANCE
K_HISTORY = TRANSIENT ; NOTHING_IS_PERSISTED ; NOTHING_WRITES_E4
```
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PredictiveObservation:
    """Referência opaca, proveniência preservada e `R(k→t)` pré-registrado."""

    reference: str
    provenance: str
    relevance_score: float

    def __post_init__(self) -> None:
        if not self.reference:
            raise ValueError("observação exige referência opaca não vazia")
        if not self.provenance:
            raise ValueError("proveniência não pode ser descartada")


@dataclass(frozen=True)
class PredictiveHistoricalValidity:
    """Partição transiente entre validade demonstrada e história sem validade."""

    valid_window: tuple[PredictiveObservation, ...]
    historical_kernel: tuple[PredictiveObservation, ...]
    rho_min: float

    def __post_init__(self) -> None:
        referencias = [o.reference for o in (*self.valid_window, *self.historical_kernel)]
        if len(referencias) != len(set(referencias)):
            raise ValueError("uma observação não pode estar nas duas partições")


def predictive_historical_validity(
    observations: tuple[PredictiveObservation, ...], *, rho_min: float
) -> PredictiveHistoricalValidity:
    """Particiona por `relevance_score`, jamais por posição ou idade."""
    if not observations:
        raise ValueError("validade histórica exige ao menos uma observação")
    validas = tuple(o for o in observations if o.relevance_score > rho_min)
    resto = tuple(o for o in observations if o.relevance_score <= rho_min)
    return PredictiveHistoricalValidity(
        valid_window=validas, historical_kernel=resto, rho_min=rho_min
    )
