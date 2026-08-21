"""Bootstrap, placebo, `A⁻` e `A*_worst` — o Power Gate quantitativo.

```text
A_minus      = quantil inferior unilateral corrigido do bootstrap do ganho
A_star_worst = máximo dos quantis superiores unilaterais corrigidos em S
"nao encontrei" != "posso excluir"
```
"""

from __future__ import annotations

import math
import random
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class PredictivePowerOutcome:
    """Saída quantitativa, antes de qualquer classificação de estado."""

    a_minus: float
    a_upper: float
    a_star_worst: float
    mean_gain: float
    placebo_p: float
    g_real: float
    g_shuffled_p95: float
    sample_size: int
    alpha_corrected: float


def _quantile(ordenado: list[float], q: float) -> float:
    if not ordenado:
        raise ValueError("amostra vazia")
    pos = q * (len(ordenado) - 1)
    baixo = int(math.floor(pos))
    alto = min(baixo + 1, len(ordenado) - 1)
    return ordenado[baixo] * (1.0 - (pos - baixo)) + ordenado[alto] * (pos - baixo)


def predictive_block_length(n: int) -> int:
    return max(2, int(math.floor(n ** (1.0 / 3.0))))


def predictive_circular_block_bootstrap(
    gains: tuple[float, ...], *, replicates: int, seed: int, alpha_corrected: float
) -> tuple[float, float]:
    """Devolve `(quantil inferior, quantil superior)` unilaterais corrigidos."""
    n = len(gains)
    if n < 2:
        raise ValueError("bootstrap exige ao menos duas observações")
    tamanho = predictive_block_length(n)
    blocos = -(-n // tamanho)
    rng = random.Random(seed)
    medias: list[float] = []
    for _ in range(replicates):
        amostra: list[float] = []
        for _ in range(blocos):
            inicio = rng.randrange(n)
            amostra.extend(gains[(inicio + i) % n] for i in range(tamanho))
        medias.append(math.fsum(amostra[:n]) / n)
    medias.sort()
    return _quantile(medias, alpha_corrected), _quantile(medias, 1.0 - alpha_corrected)


def predictive_deterministic_placebo(
    baseline_log: tuple[float, ...],
    candidate_log_of: Callable[[float, float], float],
    blind_pairs: tuple[tuple[float, float], ...],
    *,
    permutations: int,
    seed: int,
) -> tuple[float, float, float]:
    """Permuta os preditores cegos sem reajuste. Devolve `(p, G_real, p95)`."""
    preditores = [x for x, _ in blind_pairs]
    alvos = [y for _, y in blind_pairs]
    n = len(alvos)
    ganho_real = (
        math.fsum(candidate_log_of(alvos[i], preditores[i]) - baseline_log[i] for i in range(n)) / n
    )
    rng = random.Random(seed)
    nulos: list[float] = []
    contagem = 0
    for _ in range(permutations):
        embaralhado = preditores[:]
        rng.shuffle(embaralhado)
        ganho = (
            math.fsum(
                candidate_log_of(alvos[i], embaralhado[i]) - baseline_log[i] for i in range(n)
            )
            / n
        )
        nulos.append(ganho)
        if ganho >= ganho_real:
            contagem += 1
    nulos.sort()
    return (1 + contagem) / (permutations + 1), ganho_real, _quantile(nulos, 0.95)
