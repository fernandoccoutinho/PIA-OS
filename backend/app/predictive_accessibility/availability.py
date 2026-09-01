"""`E5.e` — porta de disponibilidade causal e rejeição causal tipada.

`avail(Z, t, Δ) = 0` produz `PredictiveCausalRejectionResult` **antes** do estimador.
Nada conhecido depois de `t` pode demonstrar que a previsão em `t` era
possível.

```text
FUTURE_LEAKAGE = FORBIDDEN
CAUSAL_REJECTED -> NEVER_REACHES_ESTIMATOR_POWER_GATE_OR_E5_J
```
"""

from __future__ import annotations

from dataclasses import dataclass

from app.predictive_accessibility.channel import PredictiveChannel
from app.predictive_accessibility.claim import PredictiveClaim


@dataclass(frozen=True)
class PredictiveAvailabilityOutcome:
    """Disponibilidade causal por canal, com o motivo preservado."""

    channel: PredictiveChannel
    available: bool
    reason: str


@dataclass(frozen=True)
class PredictiveCausalRejectionResult:
    """Ramo terminal: a alegação não chega à ciência."""

    claim: PredictiveClaim
    rejected_channels: tuple[PredictiveAvailabilityOutcome, ...]
    reason: str

    def __post_init__(self) -> None:
        if not self.rejected_channels:
            raise ValueError("rejeição causal exige ao menos um canal indisponível")
        if any(o.available for o in self.rejected_channels):
            raise ValueError("canal disponível não pode compor uma rejeição causal")


def predictive_availability(
    channel: PredictiveChannel, *, observed_at_offset: int
) -> PredictiveAvailabilityOutcome:
    """`observed_at_offset` é a defasagem real com que o canal é observado."""
    disponivel = observed_at_offset >= channel.lag
    return PredictiveAvailabilityOutcome(
        channel=channel,
        available=disponivel,
        reason=(
            "observado com defasagem suficiente"
            if disponivel
            else f"observado com defasagem {observed_at_offset}, exigida {channel.lag}"
        ),
    )
