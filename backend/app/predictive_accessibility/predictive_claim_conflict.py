"""`E5.m` — conflito e comensurabilidade entre alegações avaliadas.

Duas alegações só conflitam quando são **comparáveis**. Alvo, população,
jurisdição, horizonte, regime ou unidade diferentes tornam a divergência um
falso conflito, que permanece **decomposto** em vez de resolvido.

```text
DIVERGENCE_WITHOUT_COMMENSURABILITY = FALSE_CONFLICT
AVERAGE = FORBIDDEN · VOTE = FORBIDDEN · MODEL_ARBITRATION = FORBIDDEN
REJECTED_AND_UNAVAILABLE_CLAIMS_ARE_NEVER_VOTED
```
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from app.predictive_accessibility.epistemic import PredictiveClaimEvaluationResult


class PredictiveConflictStatus(StrEnum):
    """Membros qualificados: a guarda de camada proíbe `Conflict` nu.

    ```text
    PREDICTIVE_CLAIM_CONFLICT_QUALIFIES · BARE_CONFLICT_DOES_NOT
    ```
    """

    PREDICTIVE_CLAIM_NO_CONFLICT = "predictive_claim_no_conflict"
    PREDICTIVE_CLAIM_REAL_CONFLICT = "predictive_claim_real_conflict"
    PREDICTIVE_CLAIM_FALSE_CONFLICT_DECOMPOSED = "predictive_claim_false_conflict_decomposed"


@dataclass(frozen=True)
class PredictiveComparabilityKey:
    """As seis coordenadas que precisam coincidir para haver comparação."""

    target: str
    population: str
    jurisdiction: str
    horizon: int
    regime: str
    unit: str


@dataclass(frozen=True)
class PredictiveComparableClaim:
    """Alegação avaliada, chave de comensurabilidade e conclusão explícita.

    A assinatura de conclusão é imutável e declarada. Sem ela, duas previsões
    incompatíveis com o MESMO estado epistêmico passariam como concordantes —
    o defeito da candidata rejeitada `81955da8`.

    ```text
    SAME_STATE != SAME_CONCLUSION
    ```
    """

    evaluation: PredictiveClaimEvaluationResult
    key: PredictiveComparabilityKey
    conclusion_signature: str

    def __post_init__(self) -> None:
        if not self.conclusion_signature.strip():
            raise ValueError("alegação comparável exige assinatura de conclusão explícita")


@dataclass(frozen=True)
class PredictiveConflictAssessment:
    """Nunca agrega: preserva os lados e o motivo da incomparabilidade."""

    status: PredictiveConflictStatus
    compared: tuple[PredictiveComparableClaim, ...]
    incommensurable_dimensions: tuple[str, ...]
    preserved_non_evaluated: tuple[object, ...]
    reason: str

    @property
    def blocks_material_support(self) -> bool:
        """Conflito real entre conclusões impede sustentar materialidade."""
        return self.status is PredictiveConflictStatus.PREDICTIVE_CLAIM_REAL_CONFLICT

    @property
    def blocks_safe_route(self) -> bool:
        """Conflito real sem decomposição não autoriza rota segura."""
        return self.status is PredictiveConflictStatus.PREDICTIVE_CLAIM_REAL_CONFLICT

    def __post_init__(self) -> None:
        if self.status is PredictiveConflictStatus.PREDICTIVE_CLAIM_FALSE_CONFLICT_DECOMPOSED and (
            not self.incommensurable_dimensions
        ):
            raise ValueError("falso conflito exige nomear as dimensões incomensuráveis")
        if self.status is PredictiveConflictStatus.PREDICTIVE_CLAIM_REAL_CONFLICT and (
            self.incommensurable_dimensions
        ):
            raise ValueError("conflito real não admite dimensão incomensurável")


def predictive_incommensurable_dimensions(
    esquerda: PredictiveComparabilityKey, direita: PredictiveComparabilityKey
) -> tuple[str, ...]:
    return tuple(
        nome
        for nome in ("target", "population", "jurisdiction", "horizon", "regime", "unit")
        if getattr(esquerda, nome) != getattr(direita, nome)
    )


def predictive_conflict_assessment(
    claims: tuple[PredictiveComparableClaim, ...],
    *,
    preserved_non_evaluated: tuple[object, ...] = (),
) -> PredictiveConflictAssessment:
    """Compara **apenas** alegações avaliadas; o resto é preservado intacto."""
    if len(claims) < 2:
        return PredictiveConflictAssessment(
            status=PredictiveConflictStatus.PREDICTIVE_CLAIM_NO_CONFLICT,
            compared=claims,
            incommensurable_dimensions=(),
            preserved_non_evaluated=preserved_non_evaluated,
            reason="menos de duas alegações avaliadas comparáveis",
        )
    divergentes: set[str] = set()
    referencia = claims[0].key
    for outra in claims[1:]:
        divergentes.update(predictive_incommensurable_dimensions(referencia, outra.key))
    if divergentes:
        return PredictiveConflictAssessment(
            status=PredictiveConflictStatus.PREDICTIVE_CLAIM_FALSE_CONFLICT_DECOMPOSED,
            compared=claims,
            incommensurable_dimensions=tuple(sorted(divergentes)),
            preserved_non_evaluated=preserved_non_evaluated,
            reason="alegações não são comensuráveis; divergência permanece decomposta",
        )
    # Conflito é sobre CONCLUSÕES incompatíveis, não sobre estados epistêmicos
    # diferentes: `PREDICTABLE` e `UNRESOLVED` sobre a mesma conclusão são
    # graus de evidência, e ambas as rotas têm de ser preservadas.
    #
    #     DIFFERENT_STATE != INCOMPATIBLE_CONCLUSION
    conclusoes = {c.conclusion_signature for c in claims}
    conflito = len(conclusoes) > 1
    return PredictiveConflictAssessment(
        status=(
            PredictiveConflictStatus.PREDICTIVE_CLAIM_REAL_CONFLICT
            if conflito
            else PredictiveConflictStatus.PREDICTIVE_CLAIM_NO_CONFLICT
        ),
        compared=claims,
        incommensurable_dimensions=(),
        preserved_non_evaluated=preserved_non_evaluated,
        reason=(
            "conclusões incompatíveis sobre a mesma chave"
            if conflito
            else "conclusões concordantes sobre a mesma chave"
        ),
    )
