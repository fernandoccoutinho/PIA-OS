"""
Construtores de requisição pública `E6.2`, compartilhados entre os testes.

Um lote `ready` que atravessa a cadeia científica inteira exige um contexto
completo: as três alternativas `A0/A1/A2`, as seis dimensões de fardo e
pares de treino com variância residual não nula. Montar isso em cada
arquivo de teste produziria cópias que divergem em silêncio — aqui é um
construtor só.

```text
FIXTURE_IS_INPUT_ONLY = TRUE
NO_DERIVED_RESULT_IN_FIXTURE = TRUE
```

Nada aqui pré-calcula desfecho: a fixture entrega **entrada** pública, e
quem decide continua sendo a `E5`.
"""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from app.predictive_accessibility.piap.authority import (
    ApprovalBinding,
    AuthorityContext,
    BoundObjectRef,
)
from app.predictive_accessibility.piap.enums import (
    AuthorityStatus,
    BoundObjectKind,
    PiapContractVersion,
    TemporalAvailability,
)
from app.predictive_accessibility.piap.envelope import (
    ClaimSubject,
    Horizon,
    PiapEnvelope,
    ProvenanceKind,
    ProvenanceRecord,
    SourceReference,
    serialize_piap_envelope,
)
from app.schemas import predictive_evaluation as dto
from app.services.predictive_evaluation_mapping import encode_canonical_piap_transport

_T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _source(seq: int = 1) -> SourceReference:
    return SourceReference(
        kind=ProvenanceKind("policy.registry"),
        ref=uuid.UUID(int=seq),
        source_version=3,
        content_sha256="a" * 64,
    )


def canonical_envelope() -> PiapEnvelope:
    """Envelope PIAP canônico mínimo e válido para a cadeia completa."""
    return PiapEnvelope(
        contract_version=PiapContractVersion.V1_0,
        subject=ClaimSubject(
            target="grid.load",
            signal="demand.peak",
            horizon=Horizon(
                delta=timedelta(hours=1),
                reference_time=_T0,
                availability=TemporalAvailability.AVAILABLE_AT_REFERENCE_TIME,
            ),
        ),
        provenance=ProvenanceRecord(
            origin=_source(), recorded_at=_T0, jurisdiction="br", policy_ref="pol.a"
        ),
        authority=AuthorityContext(
            status=AuthorityStatus.ASSERTED_AUTHORIZED,
            approval=ApprovalBinding(
                approval_reference="APR-0001",
                approval_version=2,
                approval_scope=("bound.read",),
                approval_expiry=datetime(2026, 6, 1, tzinfo=UTC),
                approval_jurisdiction="br",
                bound_to=BoundObjectRef(
                    kind=BoundObjectKind.PROMOTION_CANDIDATE, ref=uuid.UUID(int=99)
                ),
            ),
        ),
        payload_refs=(_source(),),
        sealed_at=_T0,
    )


DEFAULT_AT = "2026-03-01T00:00:00Z"

_DIMENSION_KINDS = (
    "financial_resources",
    "social_human",
    "critical_service_continuity",
    "distribution_equity",
    "opportunity_delay",
    "irreversibility_recovery",
)

_KEY: dict[str, Any] = {
    "target": "grid.load",
    "population": "br.sergipe",
    "jurisdiction": "br",
    "horizon": 1,
    "regime": "stable",
    "unit": "mw",
}


def _vector(magnitude: float) -> dict[str, Any]:
    return {
        "dimensions": [
            {
                "kind": kind,
                "magnitude": magnitude,
                "unit": "brl" if kind == "financial_resources" else "index",
                "source": "policy.registry",
                "source_version": 3,
                "observed_at": "2026-01-01T00:00:00Z",
                "uncertainty": [max(0.0, magnitude - 1.0), magnitude + 1.0],
                "incidence": "litoral",
            }
            for kind in _DIMENSION_KINDS
        ],
        "probability_validation": "validated",
    }


def _alternative(kind: str, custo: float, reversivel: bool, descricao: str) -> dict[str, Any]:
    return {
        "kind": kind,
        "key": dict(_KEY),
        "cost_knowledge": "known",
        "cost_value": custo,
        "reversible": reversivel,
        "description": descricao,
    }


def governed_quality_payload() -> dict[str, Any]:
    """Entradas governadas completas — três alternativas, seis dimensões."""
    return {
        "conclusion_signature": "pico acima do limiar",
        "comparability_key": dict(_KEY),
        "decisive_constraint": "janela de validade histórica",
        "protection_candidates": [],
        "guidance": {
            "reference": "GUID-1",
            "authority": "defesa civil",
            "provenance": "policy.registry",
            "jurisdiction": "br",
            "version": 3,
            "valid_from": "2026-01-01T00:00:00Z",
            "valid_until": "2027-01-01T00:00:00Z",
        },
        "expected_guidance_jurisdiction": "br",
        "expected_guidance_version": 3,
        "alternatives": [
            _alternative("a0_inaction", 0.0, True, "não agir"),
            _alternative("a1_reversible_escalation", 10.0, True, "escalonada reversível"),
            _alternative("a2_full_action", 25.0, False, "ação plena"),
        ],
        "burden_entries": [
            {"alternative": "a0_inaction", "vector": _vector(0.5)},
            {"alternative": "a1_reversible_escalation", "vector": _vector(1.0)},
            {"alternative": "a2_full_action", "vector": _vector(2.0)},
        ],
        "materiality_required_scope": ["bound.read"],
    }


def evaluation_context_payload(at: str = DEFAULT_AT) -> dict[str, Any]:
    """Contexto completo. Pares de treino com resíduo não nulo de propósito."""
    return {
        "registry": {
            "channels": [{"name": "lag_1", "lag": 1}],
            "estimator_library": ["gaussian_marginal_baseline", "gaussian_ar1_ols"],
        },
        "observed_at_offset": 1,
        "observations": [{"reference": "k1", "provenance": "p1", "relevance_score": 0.9}],
        "rho_min": 0.5,
        "d_regime": 0.1,
        "theta": 0.5,
        "beats_fluctuation": False,
        "horizon_points": [
            {"horizon": 1, "a_minus": 0.4, "gates_pass": True, "regime": "no_shift"}
        ],
        "training_pairs": [[0.0, 1.0], [1.0, 2.1], [2.0, 2.9], [3.0, 4.2], [4.0, 4.8]],
        "blind_pairs": [[5.0, 6.1], [6.0, 6.9], [7.0, 8.2]],
        "bootstrap_replicates": 200,
        "bootstrap_seed": 11,
        "alpha_corrected": 0.016666666666666666,
        "placebo_permutations": 200,
        "placebo_seed": 22,
        "a_rel": 0.02,
        "at": at,
        "expected_version": 2,
        "required_scope": ["bound.read"],
        "expected_jurisdiction": "br",
        "expected_binding_kind": "promotion_candidate",
    }


def ready_item_payload(at: str = DEFAULT_AT) -> dict[str, Any]:
    return {
        "kind": "ready",
        "canonical_piap_transport": encode_canonical_piap_transport(
            serialize_piap_envelope(canonical_envelope())
        ),
        "evaluation_context": evaluation_context_payload(at),
        "governed_quality": governed_quality_payload(),
    }


def unavailable_item_payload(reference: str = "src-1") -> dict[str, Any]:
    return {
        "kind": "upstream_unavailable",
        "reference": reference,
        "reason": "fonte fora do ar",
    }


def ready_item(at: str = DEFAULT_AT) -> dto.PublicReadyItem:
    return dto.PublicReadyItem.model_validate(ready_item_payload(at))


def unavailable_item(reference: str = "src-1") -> dto.PublicUpstreamUnavailableItem:
    return dto.PublicUpstreamUnavailableItem.model_validate(unavailable_item_payload(reference))


def request_payload(*items: dict[str, Any]) -> dict[str, Any]:
    return {"items": list(items)}
