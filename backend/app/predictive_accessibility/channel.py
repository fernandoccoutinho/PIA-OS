"""`E5.d` — registro de canais e biblioteca pré-registrada `(C, S)`.

Não mede nada. Declara quais canais existem e qual é a biblioteca finita de
formas sobre a qual `A*_worst` é o supremo.

```text
SUPREMUM_OVER_A_FINITE_LIBRARY != SUPREMUM_OVER_ALL_FORMS
```
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PredictiveChannel:
    """Um canal candidato: nome e defasagem em que ele é conhecido."""

    name: str
    lag: int

    def __post_init__(self) -> None:
        if self.lag < 1:
            raise ValueError(f"lag deve ser >= 1, recebido {self.lag}")


@dataclass(frozen=True)
class PredictiveChannelRegistry:
    """`C` e `S` pré-registrados, congelados antes de qualquer medição."""

    channels: tuple[PredictiveChannel, ...]
    estimator_library: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.channels:
            raise ValueError("registry exige ao menos um canal")
        if not self.estimator_library:
            raise ValueError("a biblioteca S pré-registrada não pode ser vazia")
