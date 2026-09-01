"""Lote limitado: requisição, item, desfecho e os dois tetos congelados.

```text
MAX_CLAIMS_PER_EVALUATION           = 8
MAX_TOTAL_REFERENCES_PER_EVALUATION = 512
E5_EVALUATION_BATCH_RESULT = ordered bounded tuple[E5_REQUEST_ITEM_OUTCOME]
SAME_INPUT_OUTPUT_LENGTH_AND_ORDER = TRUE
```

A recusa é **tipada e fail-fast**, na construção da requisição — que é o único
ponto em que o total de referências passa a ser calculável.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from app.predictive_accessibility.availability import PredictiveCausalRejectionResult
from app.predictive_accessibility.channel import PredictiveChannelRegistry
from app.predictive_accessibility.epistemic import PredictiveClaimEvaluationResult
from app.predictive_accessibility.history import PredictiveObservation
from app.predictive_accessibility.horizon import PredictiveHorizonPoint
from app.predictive_accessibility.piap.enums import BoundObjectKind
from app.predictive_accessibility.piap.envelope import PiapEnvelope

MAX_CLAIMS_PER_EVALUATION = 8
MAX_TOTAL_REFERENCES_PER_EVALUATION = 512


class PredictiveBatchLimitError(ValueError):
    """Recusa tipada de lote. Não é falha de execução."""


class PredictiveBatchItemTypeError(TypeError):
    """Item fora da união admitida, recusado antes do coordenador."""


@dataclass(frozen=True)
class PredictiveUpstreamUnavailableInput:
    """Entrada indisponível a montante. Nunca é desfecho, é entrada."""

    reference: str
    reason: str


@dataclass(frozen=True)
class PredictiveUpstreamUnavailableOutcome:
    """Desfecho do item indisponível. Zero ciência foi executada."""

    source: PredictiveUpstreamUnavailableInput


@dataclass(frozen=True)
class PredictiveEvaluationContext:
    """Entradas pré-registradas e específicas de uma única alegação."""

    registry: PredictiveChannelRegistry
    observed_at_offset: int
    observations: tuple[PredictiveObservation, ...]
    rho_min: float
    d_regime: float
    theta: float
    beats_fluctuation: bool
    horizon_points: tuple[PredictiveHorizonPoint, ...]
    training_pairs: tuple[tuple[float, float], ...]
    blind_pairs: tuple[tuple[float, float], ...]
    bootstrap_replicates: int
    bootstrap_seed: int
    alpha_corrected: float
    placebo_permutations: int
    placebo_seed: int
    a_rel: float
    at: datetime
    expected_version: int
    required_scope: tuple[str, ...]
    expected_jurisdiction: str | None
    expected_binding_kind: BoundObjectKind
    high_prediction_error: bool = False
    model_disagreement: bool = False

    def __post_init__(self) -> None:
        if len(self.training_pairs) < 3:
            raise ValueError("contexto exige ao menos três pares de treino")
        if not self.blind_pairs:
            raise ValueError("contexto exige bloco cego não vazio")
        if self.bootstrap_replicates < 1 or self.placebo_permutations < 1:
            raise ValueError("réplicas de bootstrap e placebo devem ser positivas")
        if not 0.0 < self.alpha_corrected < 1.0:
            raise ValueError("alpha_corrected deve estar entre zero e um")


@dataclass(frozen=True)
class PredictiveReadyEvaluationItem:
    """Envelope pronto e contexto científico exclusivo da alegação."""

    envelope: PiapEnvelope
    context: PredictiveEvaluationContext

    def __post_init__(self) -> None:
        if not isinstance(self.envelope, PiapEnvelope):
            raise PredictiveBatchItemTypeError("ready item exige PiapEnvelope")
        if not isinstance(self.context, PredictiveEvaluationContext):
            raise PredictiveBatchItemTypeError("ready item exige PredictiveEvaluationContext")


@dataclass(frozen=True)
class PredictiveEvaluationRequest:
    """Itens do lote, validados contra os dois tetos na construção."""

    items: tuple[PredictiveReadyEvaluationItem | PredictiveUpstreamUnavailableInput, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.items, tuple):
            raise PredictiveBatchItemTypeError("items deve ser tupla")
        if not self.items:
            raise PredictiveBatchLimitError("requisição exige ao menos um item")
        if any(
            not isinstance(item, PredictiveReadyEvaluationItem | PredictiveUpstreamUnavailableInput)
            for item in self.items
        ):
            raise PredictiveBatchItemTypeError(
                "item deve ser PredictiveReadyEvaluationItem ou "
                "PredictiveUpstreamUnavailableInput"
            )
        if len(self.items) > MAX_CLAIMS_PER_EVALUATION:
            raise PredictiveBatchLimitError(
                f"itens excedem MAX_CLAIMS_PER_EVALUATION: recebido {len(self.items)}, "
                f"permitido no máximo {MAX_CLAIMS_PER_EVALUATION}"
            )
        total = sum(
            len(item.envelope.payload_refs)
            for item in self.items
            if isinstance(item, PredictiveReadyEvaluationItem)
        )
        if total > MAX_TOTAL_REFERENCES_PER_EVALUATION:
            raise PredictiveBatchLimitError(
                f"referências excedem MAX_TOTAL_REFERENCES_PER_EVALUATION: recebido {total}, "
                f"permitido no máximo {MAX_TOTAL_REFERENCES_PER_EVALUATION}"
            )

    @property
    def total_references(self) -> int:
        return sum(
            len(item.envelope.payload_refs)
            for item in self.items
            if isinstance(item, PredictiveReadyEvaluationItem)
        )


# Exatamente três variantes externas por item. Não existe uma quarta.
PredictiveRequestItemOutcome = (
    PredictiveUpstreamUnavailableOutcome
    | PredictiveCausalRejectionResult
    | PredictiveClaimEvaluationResult
)


@dataclass(frozen=True)
class PredictiveEvaluationBatchResult:
    """Um desfecho por item de entrada, na MESMA posição."""

    outcomes: tuple[PredictiveRequestItemOutcome, ...]
    request_length: int

    def __post_init__(self) -> None:
        if len(self.outcomes) != self.request_length:
            raise PredictiveBatchLimitError(
                f"lote devolveu {len(self.outcomes)} desfechos para " f"{self.request_length} itens"
            )


from app.predictive_accessibility.burden import PredictiveTotalBurdenVector  # noqa: E402
from app.predictive_accessibility.counterfactual import (  # noqa: E402
    PredictiveAlternative,
    PredictiveAlternativeKind,
)
from app.predictive_accessibility.guidance import (  # noqa: E402
    PredictiveGuidanceReference,
)
from app.predictive_accessibility.predictive_claim_conflict import (  # noqa: E402
    PredictiveComparabilityKey,
)
from app.predictive_accessibility.protection import (  # noqa: E402
    PredictiveProtectionCandidateInput,
)
from app.predictive_accessibility.routing import PredictiveRoutingOutcome  # noqa: E402

# --- Módulo 4: entradas governadas de qualidade e roteamento ---------------
#
#     GOVERNED_INPUT_CARRIES_REFERENCES · IT_NEVER_GRANTS_AUTHORITY


@dataclass(frozen=True)
class PredictiveGovernedQualityInput:
    """Entradas governadas de UM item, alinhadas ao lote.

    Transporta referências e metadados; não concede autoridade e não decide.
    """

    conclusion_signature: str
    comparability_key: PredictiveComparabilityKey
    decisive_constraint: str
    protection_candidates: tuple[PredictiveProtectionCandidateInput, ...]
    guidance: PredictiveGuidanceReference | None
    expected_guidance_jurisdiction: str
    expected_guidance_version: int
    alternatives: tuple[PredictiveAlternative, ...]
    burden_entries: tuple[tuple[PredictiveAlternativeKind, PredictiveTotalBurdenVector], ...]
    materiality_required_scope: tuple[str, ...] = ()
    required_protection_identifiers: tuple[str, ...] = ()
    protection_inventory_reference: str | None = None
    asymmetry_justification: str | None = None

    def __post_init__(self) -> None:
        # C2: NÃO existe campo público capaz de injetar PROMOTED aqui. O
        # desfecho E5.l chega exclusivamente pelo sidecar do coordenador.
        #
        #     CALLER_INJECTED_PROMOTION = FORBIDDEN
        if not self.conclusion_signature.strip():
            raise PredictiveBatchItemTypeError(
                "entrada governada exige assinatura de conclusão explícita"
            )
        if not self.decisive_constraint.strip():
            raise PredictiveBatchItemTypeError(
                "entrada governada exige restrição decisiva explícita"
            )
        if len(set(self.required_protection_identifiers)) != len(
            self.required_protection_identifiers
        ):
            raise PredictiveBatchItemTypeError(
                "inventário protetivo não admite identificador duplicado"
            )
        if self.required_protection_identifiers and not (
            self.protection_inventory_reference and self.protection_inventory_reference.strip()
        ):
            raise PredictiveBatchItemTypeError(
                "frentes protetivas requeridas exigem referência de inventário"
            )


@dataclass(frozen=True)
class PredictiveRoutingBatchResult:
    """Um desfecho de roteamento por item de entrada, na MESMA posição."""

    outcomes: tuple[PredictiveRoutingOutcome, ...]
    request_length: int
    decomposed_conflict_dimensions: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if len(self.outcomes) != self.request_length:
            raise PredictiveBatchLimitError(
                f"roteamento devolveu {len(self.outcomes)} desfechos para "
                f"{self.request_length} itens"
            )
