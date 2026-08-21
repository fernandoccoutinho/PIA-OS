"""`E5.p` — validação real de orientação e `RECOMMENDATION_QUALITY_RESULT`.

Produtor **único** do resultado de qualidade. Consome toda a saída tipada de
`E5.o`. Orientação é entrada **opcional**: ausência é resultado tipado, não
falha.

O desfecho é **calculado**, nunca fornecido. A candidata rejeitada `81955da8`
recebia `outcome` pronto do chamador e uma referência vazia, com jurisdição
incompatível e versão negativa, saía `VALID`.

```text
SELF_CERTIFIED_PROVENANCE = NOT_VALIDATION
E5_NEVER_GENERATES_ACQUIRES_OR_SELECTS_GUIDANCE
```
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from app.predictive_accessibility.protection import PredictiveProtectionSet


class PredictiveGuidanceOutcome(StrEnum):
    VALID = "valid"
    MISSING = "missing"
    STALE = "stale"
    INVALID = "invalid"
    JURISDICTION_MISMATCH = "jurisdiction_mismatch"
    VERSION_MISMATCH = "version_mismatch"


class PredictiveGuidanceDisposition(StrEnum):
    USE_PROCEDURAL_DETAIL = "use_procedural_detail"
    REFER_TO_COMPETENT_AUTHORITY = "refer_to_competent_authority"
    ABSTAIN_FROM_PROCEDURAL_DETAIL = "abstain_from_procedural_detail"


@dataclass(frozen=True)
class PredictiveGuidanceReference:
    """Referência opaca a orientação externa. **Sem** campo de desfecho."""

    reference: str
    authority: str
    provenance: str
    jurisdiction: str
    version: int
    valid_from: datetime | None
    valid_until: datetime | None


@dataclass(frozen=True)
class PredictiveRecommendationQualityResult:
    """`RECOMMENDATION_QUALITY_RESULT` — produtor único é `E5.p`."""

    protection: PredictiveProtectionSet
    guidance: PredictiveGuidanceReference | None
    guidance_outcome: PredictiveGuidanceOutcome
    disposition: PredictiveGuidanceDisposition
    complete_answer_allowed: bool
    procedural_detail_allowed: bool
    reason: str


def predictive_validate_guidance(
    guidance: PredictiveGuidanceReference | None,
    *,
    at: datetime,
    expected_jurisdiction: str,
    expected_version: int,
) -> PredictiveGuidanceOutcome:
    """Calcula o desfecho. Nenhuma entrada defeituosa pode virar `VALID`."""
    if guidance is None:
        return PredictiveGuidanceOutcome.MISSING
    if not guidance.reference.strip() or not guidance.authority.strip():
        return PredictiveGuidanceOutcome.INVALID
    if not guidance.provenance.strip() or guidance.version < 1:
        return PredictiveGuidanceOutcome.INVALID
    if guidance.valid_from is None or guidance.valid_until is None:
        return PredictiveGuidanceOutcome.INVALID
    if guidance.valid_until <= guidance.valid_from:
        return PredictiveGuidanceOutcome.INVALID
    if guidance.jurisdiction != expected_jurisdiction:
        return PredictiveGuidanceOutcome.JURISDICTION_MISMATCH
    if guidance.version != expected_version:
        return PredictiveGuidanceOutcome.VERSION_MISMATCH
    if at < guidance.valid_from or at >= guidance.valid_until:
        return PredictiveGuidanceOutcome.STALE
    return PredictiveGuidanceOutcome.VALID


def predictive_recommendation_quality(
    protection: PredictiveProtectionSet,
    guidance: PredictiveGuidanceReference | None,
    *,
    at: datetime,
    expected_jurisdiction: str,
    expected_version: int,
) -> PredictiveRecommendationQualityResult:
    desfecho = predictive_validate_guidance(
        guidance,
        at=at,
        expected_jurisdiction=expected_jurisdiction,
        expected_version=expected_version,
    )
    if desfecho is PredictiveGuidanceOutcome.VALID:
        disposicao = PredictiveGuidanceDisposition.USE_PROCEDURAL_DETAIL
        motivo = "orientação vigente, na jurisdição e na versão esperadas"
    elif desfecho is PredictiveGuidanceOutcome.MISSING:
        disposicao = PredictiveGuidanceDisposition.ABSTAIN_FROM_PROCEDURAL_DETAIL
        motivo = "sem orientação; abster-se de detalhe procedimental"
    else:
        disposicao = PredictiveGuidanceDisposition.REFER_TO_COMPETENT_AUTHORITY
        motivo = f"orientação {desfecho.value}; encaminhar à autoridade competente"
    return PredictiveRecommendationQualityResult(
        protection=protection,
        guidance=guidance,
        guidance_outcome=desfecho,
        disposition=disposicao,
        complete_answer_allowed=protection.complete_answer_allowed,
        procedural_detail_allowed=desfecho is PredictiveGuidanceOutcome.VALID,
        reason=motivo,
    )
