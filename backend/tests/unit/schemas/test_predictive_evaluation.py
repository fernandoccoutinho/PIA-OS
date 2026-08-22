"""Contrato público `E6.1` — o DTO representa e nada mais.

```text
PUBLIC_DTO_IMPORTS_E5_INTERNALS = FORBIDDEN
CLIENT_SUPPLIES_DERIVED_RESULT = FORBIDDEN
```
"""

import ast
import pathlib

import pytest
from pydantic import ValidationError

from app.schemas import predictive_evaluation as dto

pytestmark = pytest.mark.unit

FONTE = pathlib.Path(dto.__file__)


def test_e61_schema_publico_nao_importa_a_e5() -> None:
    """Prova por AST, não por convenção de revisão."""
    arvore = ast.parse(FONTE.read_text(encoding="utf-8"))
    modulos: list[str] = []
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            modulos.extend(a.name for a in no.names)
        elif isinstance(no, ast.ImportFrom) and no.module:
            modulos.append(no.module)
    assert not any(m.startswith("app.predictive_accessibility") for m in modulos), modulos
    assert not any(m.startswith("app.services") for m in modulos), modulos


def test_e61_uniao_discriminada_de_itens() -> None:
    pronto = dto.PublicEvaluationRequest.model_validate({"items": [_ready_payload()]})
    indisponivel = dto.PublicEvaluationRequest.model_validate(
        {"items": [{"kind": "upstream_unavailable", "reference": "u1", "reason": "fora"}]}
    )
    assert isinstance(pronto.items[0], dto.PublicReadyItem)
    assert isinstance(indisponivel.items[0], dto.PublicUpstreamUnavailableItem)


def test_e61_kind_desconhecido_reprova() -> None:
    with pytest.raises(ValidationError):
        dto.PublicEvaluationRequest.model_validate(
            {"items": [{"kind": "promotion", "reference": "x", "reason": "y"}]}
        )


@pytest.mark.parametrize(
    "extra",
    [
        {"promotion": True},
        {"route": "predict"},
        {"approval_outcome": "valid"},
        {"reconfiguration": {"decision": "promoted"}},
        {"recommended_alternative": "a1_reversible_escalation"},
        {"sidecar": {}},
    ],
)
def test_e61_resultado_derivado_e_recusado_como_extra(extra) -> None:
    """`extra='forbid'`: nenhum resultado calculado entra pela requisição."""
    corpo = _ready_payload() | extra
    with pytest.raises(ValidationError):
        dto.PublicEvaluationRequest.model_validate({"items": [corpo]})


def test_e61_contexto_ausente_nao_vira_default() -> None:
    corpo = _ready_payload()
    del corpo["evaluation_context"]
    with pytest.raises(ValidationError):
        dto.PublicEvaluationRequest.model_validate({"items": [corpo]})


@pytest.mark.parametrize(
    "campo",
    [
        "registry",
        "observed_at_offset",
        "rho_min",
        "training_pairs",
        "blind_pairs",
        "bootstrap_seed",
        "alpha_corrected",
        "a_rel",
        "at",
        "expected_binding_kind",
    ],
)
def test_e61_campo_obrigatorio_do_contexto_nao_tem_default(campo) -> None:
    corpo = _ready_payload()
    del corpo["evaluation_context"][campo]
    with pytest.raises(ValidationError):
        dto.PublicEvaluationRequest.model_validate({"items": [corpo]})


def test_e61_apenas_dois_campos_do_contexto_tem_default() -> None:
    """Os dois defaults reproduzem o objeto interno; nenhum outro existe."""
    com_default = {
        nome
        for nome, campo in dto.PublicEvaluationContext.model_fields.items()
        if not campo.is_required()
    }
    assert com_default == {"high_prediction_error", "model_disagreement"}


def test_e61_modelos_de_requisicao_sao_frozen_e_forbid() -> None:
    for modelo in (
        dto.PublicEvaluationRequest,
        dto.PublicReadyItem,
        dto.PublicUpstreamUnavailableItem,
        dto.PublicEvaluationContext,
        dto.PublicGovernedQualityInput,
    ):
        assert modelo.model_config["extra"] == "forbid", modelo.__name__
        assert modelo.model_config["frozen"] is True, modelo.__name__


def test_e61_schema_publico_nao_reproduz_constantes_de_limite() -> None:
    """Os tetos 8/512 e PIAP pertencem ao servidor, não ao contrato público."""
    texto = FONTE.read_text(encoding="utf-8")
    for constante in ("262144", "MAX_CLAIMS_PER_EVALUATION", "MAX_TOTAL_REFERENCES"):
        assert constante not in texto, constante
    arvore = ast.parse(texto)
    numeros = {
        no.value
        for no in ast.walk(arvore)
        if isinstance(no, ast.Constant) and isinstance(no.value, int)
    }
    assert 512 not in numeros
    assert 256 not in numeros


def test_e61_saida_representa_as_tres_variantes_cientificas() -> None:
    assert dto.PublicClaimEvaluationView.model_fields["kind"].default == "evaluated"
    assert dto.PublicCausalRejectionView.model_fields["kind"].default == "causal_rejected"
    assert dto.PublicUpstreamUnavailableView.model_fields["kind"].default == "upstream_unavailable"


def test_e61_saida_representa_as_tres_variantes_de_roteamento() -> None:
    assert dto.PublicFinalRoutingView.model_fields["kind"].default == "routed"
    assert (
        dto.PublicCausalRejectedRoutingView.model_fields["kind"].default
        == "causal_rejected_routing"
    )
    assert (
        dto.PublicUpstreamUnavailableRoutingView.model_fields["kind"].default
        == "upstream_unavailable_routing"
    )


def test_e61_saida_nao_expoe_sidecar_aprovacao_nem_orm() -> None:
    proibidos = (
        "approval_binding",
        "bound_to",
        "reconfiguration",
        "sidecar",
        "repository",
        "event_id",
        "resulting_version",
    )
    for modelo in (
        dto.PublicClaimEvaluationView,
        dto.PublicCausalRejectionView,
        dto.PublicUpstreamUnavailableView,
        dto.PublicFinalRoutingView,
        dto.PublicRecommendationQualityView,
        dto.PublicConflictAssessmentView,
        dto.PublicEvaluationResultItem,
        dto.PublicEvaluationResponse,
    ):
        campos = set(modelo.model_fields)
        for proibido in proibidos:
            assert not any(proibido in c for c in campos), (modelo.__name__, proibido)


def test_e61_c2_resposta_carrega_request_length_e_dimensoes_decompostas() -> None:
    campos = set(dto.PublicEvaluationResponse.model_fields)
    assert {"request_length", "decomposed_conflict_dimensions", "items"} <= campos


def test_e61_c2_view_cientifica_tem_os_oito_componentes() -> None:
    campos = set(dto.PublicClaimEvaluationView.model_fields) - {"kind"}
    assert campos == {
        "claim",
        "provenance",
        "regime",
        "evidence",
        "uncertainty",
        "horizon",
        "state",
        "approval_validation_outcome",
    }


def test_e61_c2_view_de_roteamento_tem_os_nove_componentes() -> None:
    campos = set(dto.PublicFinalRoutingView.model_fields) - {"kind"}
    assert campos == {
        "route",
        "abstained",
        "recommended_alternative",
        "conflict_assessment",
        "limits",
        "reason",
        "assertiveness",
        "revalidated_route",
        "quality",
    }


def test_e61_versao_do_contrato_e_literal_fechado() -> None:
    with pytest.raises(ValidationError):
        dto.PublicEvaluationRequest.model_validate(
            {"contract_version": "outra", "items": [_ready_payload()]}
        )


# --- payload de referência -------------------------------------------------


def _ready_payload() -> dict:
    return {
        "kind": "ready",
        "canonical_piap_transport": "AAAA",
        "evaluation_context": {
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
            "training_pairs": [[0.0, 1.0], [1.0, 2.0], [2.0, 3.0]],
            "blind_pairs": [[3.0, 4.0], [4.0, 5.0]],
            "bootstrap_replicates": 200,
            "bootstrap_seed": 11,
            "alpha_corrected": 0.016666666666666666,
            "placebo_permutations": 200,
            "placebo_seed": 22,
            "a_rel": 0.02,
            "at": "2026-03-01T00:00:00Z",
            "expected_version": 2,
            "required_scope": ["bound.read"],
            "expected_jurisdiction": "br",
            "expected_binding_kind": "promotion_candidate",
        },
        "governed_quality": {
            "conclusion_signature": "pico acima do limiar",
            "comparability_key": {
                "target": "grid.load",
                "population": "br.sergipe",
                "jurisdiction": "br",
                "horizon": 1,
                "regime": "stable",
                "unit": "mw",
            },
            "decisive_constraint": "janela de validade histórica",
            "protection_candidates": [],
            "guidance": None,
            "expected_guidance_jurisdiction": "br",
            "expected_guidance_version": 3,
            "alternatives": [],
            "burden_entries": [],
        },
    }
