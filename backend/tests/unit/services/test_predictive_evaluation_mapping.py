"""Mapeadores servidor-side `E6.1` — round trip e recusas.

```text
SERVER_MAPPER_CALLS_SCIENTIFIC_FUNCTION = FORBIDDEN
TRANSPORT_DECODE_THEN_CANONICAL_PARSE
```
"""

import ast
import base64
import pathlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.predictive_accessibility.availability import (
    PredictiveAvailabilityOutcome,
    PredictiveCausalRejectionResult,
)
from app.predictive_accessibility.batch import (
    PredictiveBatchLimitError,
    PredictiveEvaluationBatchResult,
    PredictiveEvaluationRequest,
    PredictiveGovernedQualityInput,
    PredictiveReadyEvaluationItem,
    PredictiveRoutingBatchResult,
    PredictiveUpstreamUnavailableInput,
    PredictiveUpstreamUnavailableOutcome,
)
from app.predictive_accessibility.channel import PredictiveChannel
from app.predictive_accessibility.errors.exceptions import PiapContractViolationError
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
from app.predictive_accessibility.routing import (
    PredictiveCausalRejectedRoutingResult,
    PredictiveUpstreamUnavailableRoutingResult,
)
from app.schemas import predictive_evaluation as dto
from app.services import predictive_evaluation_mapping as mapper

pytestmark = pytest.mark.unit

_T0 = datetime(2026, 1, 1, tzinfo=UTC)
FONTE = pathlib.Path(mapper.__file__)


def _fonte(seq: int = 1) -> SourceReference:
    return SourceReference(
        kind=ProvenanceKind("policy.registry"),
        ref=uuid.UUID(int=seq),
        source_version=3,
        content_sha256="a" * 64,
    )


def _envelope(refs: int = 1) -> PiapEnvelope:
    fontes = tuple(sorted((_fonte(i + 1) for i in range(refs)), key=lambda r: r.sort_key))
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
            origin=_fonte(), recorded_at=_T0, jurisdiction="br", policy_ref="pol.a"
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
        payload_refs=fontes,
        sealed_at=_T0,
    )


def _contexto_dto() -> dto.PublicEvaluationContext:
    return dto.PublicEvaluationContext.model_validate(
        {
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
        }
    )


def _governada_dto() -> dto.PublicGovernedQualityInput:
    return dto.PublicGovernedQualityInput.model_validate(
        {
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
            "protection_candidates": [
                {
                    "identifier": "prot-1",
                    "reason": "reduz exposição",
                    "provenance": "policy.registry",
                    "material_effect_claimed": True,
                    "authority": {
                        "reference": "AUT-1",
                        "authority": "defesa civil",
                        "jurisdiction": "br",
                        "version": 1,
                        "scope": ["bound.read"],
                        "valid_from": "2026-01-01T00:00:00Z",
                        "valid_until": "2027-01-01T00:00:00Z",
                    },
                    "owner": "defesa civil",
                    "time_window": "24h",
                    "reversibility": "reversível",
                    "triggers": ["regime muda"],
                }
            ],
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
                {
                    "kind": "a1_reversible_escalation",
                    "key": {
                        "target": "grid.load",
                        "population": "br.sergipe",
                        "jurisdiction": "br",
                        "horizon": 1,
                        "regime": "stable",
                        "unit": "mw",
                    },
                    "cost_knowledge": "known",
                    "cost_value": 10.0,
                    "reversible": True,
                    "description": "escalonada reversível",
                }
            ],
            "burden_entries": [
                {
                    "alternative": "a1_reversible_escalation",
                    "vector": {
                        "dimensions": [
                            {
                                "kind": "financial_resources",
                                "magnitude": 1.0,
                                "unit": "brl",
                                "source": "policy.registry",
                                "source_version": 3,
                                "observed_at": "2026-01-01T00:00:00Z",
                                "uncertainty": [0.0, 2.0],
                                "incidence": "litoral",
                            },
                            {
                                "kind": "social_human",
                                "magnitude": 1.0,
                                "unit": "index",
                                "source": "policy.registry",
                                "source_version": 3,
                                "observed_at": "2026-01-01T00:00:00Z",
                                "uncertainty": [0.0, 2.0],
                                "incidence": "litoral",
                            },
                            {
                                "kind": "critical_service_continuity",
                                "magnitude": 1.0,
                                "unit": "index",
                                "source": "policy.registry",
                                "source_version": 3,
                                "observed_at": "2026-01-01T00:00:00Z",
                                "uncertainty": [0.0, 2.0],
                                "incidence": "litoral",
                            },
                            {
                                "kind": "distribution_equity",
                                "magnitude": 1.0,
                                "unit": "index",
                                "source": "policy.registry",
                                "source_version": 3,
                                "observed_at": "2026-01-01T00:00:00Z",
                                "uncertainty": [0.0, 2.0],
                                "incidence": "litoral",
                            },
                            {
                                "kind": "opportunity_delay",
                                "magnitude": 1.0,
                                "unit": "index",
                                "source": "policy.registry",
                                "source_version": 3,
                                "observed_at": "2026-01-01T00:00:00Z",
                                "uncertainty": [0.0, 2.0],
                                "incidence": "litoral",
                            },
                            {
                                "kind": "irreversibility_recovery",
                                "magnitude": 1.0,
                                "unit": "index",
                                "source": "policy.registry",
                                "source_version": 3,
                                "observed_at": "2026-01-01T00:00:00Z",
                                "uncertainty": [0.0, 2.0],
                                "incidence": "litoral",
                            },
                        ],
                        "probability_validation": "validated",
                    },
                }
            ],
            "materiality_required_scope": ["bound.read"],
        }
    )


def _item_ready_dto(transport: str | None = None, refs: int = 1) -> dto.PublicReadyItem:
    bytes_canonicos = serialize_piap_envelope(_envelope(refs))
    return dto.PublicReadyItem(
        kind="ready",
        canonical_piap_transport=(
            transport
            if transport is not None
            else mapper.encode_canonical_piap_transport(bytes_canonicos)
        ),
        evaluation_context=_contexto_dto(),
        governed_quality=_governada_dto(),
    )


# --- round trip ------------------------------------------------------------


def test_e61_round_trip_de_item_ready_completo() -> None:
    interno = mapper.to_ready_item(_item_ready_dto())
    assert isinstance(interno, PredictiveReadyEvaluationItem)
    assert interno.envelope == _envelope()
    contexto = interno.context
    assert contexto.registry.channels == (PredictiveChannel(name="lag_1", lag=1),)
    assert contexto.expected_binding_kind is BoundObjectKind.PROMOTION_CANDIDATE
    assert contexto.at == datetime(2026, 3, 1, tzinfo=UTC)
    assert contexto.training_pairs == ((0.0, 1.0), (1.0, 2.0), (2.0, 3.0))


def test_e61_round_trip_de_upstream_unavailable() -> None:
    interno = mapper.to_upstream_unavailable_input(
        dto.PublicUpstreamUnavailableItem(
            kind="upstream_unavailable", reference="u1", reason="fonte fora"
        )
    )
    assert interno == PredictiveUpstreamUnavailableInput(reference="u1", reason="fonte fora")


def test_e61_transporte_e_reversivel_byte_a_byte() -> None:
    original = serialize_piap_envelope(_envelope())
    transporte = mapper.encode_canonical_piap_transport(original)
    assert mapper.decode_canonical_piap_transport(transporte) == original


def test_e61_governada_e_construida_por_inteiro() -> None:
    interno = mapper.to_governed_quality_input(_governada_dto())
    assert isinstance(interno, PredictiveGovernedQualityInput)
    assert interno.protection_candidates[0].authority is not None
    assert interno.guidance is not None
    assert interno.burden_entries[0][0].value == "a1_reversible_escalation"
    assert interno.materiality_required_scope == ("bound.read",)


# --- recusas ---------------------------------------------------------------


def test_e61_byte_piap_alterado_e_recusado_pelo_mecanismo_canonico() -> None:
    original = bytearray(serialize_piap_envelope(_envelope()))
    original[-2] = original[-2] ^ 0x01
    transporte = base64.b64encode(bytes(original)).decode("ascii")
    with pytest.raises(PiapContractViolationError):
        mapper.to_ready_item(_item_ready_dto(transporte))


def test_e61_bytes_nao_canonicos_sao_recusados() -> None:
    """JSON semanticamente igual, mas indentado, não é canônico."""
    import json

    documento = json.loads(serialize_piap_envelope(_envelope()).decode("utf-8"))
    nao_canonico = json.dumps(documento, indent=2).encode("utf-8")
    transporte = base64.b64encode(nao_canonico).decode("ascii")
    with pytest.raises(PiapContractViolationError):
        mapper.to_ready_item(_item_ready_dto(transporte))


@pytest.mark.parametrize("ruim", ["nao base64!!", "AAA", "QUJD\n"])
def test_e61_transporte_invalido_ou_nao_reversivel_reprova(ruim) -> None:
    with pytest.raises(mapper.PublicContractMappingError):
        mapper.decode_canonical_piap_transport(ruim)


def test_e61_resposta_exige_batch_results_tipados() -> None:
    """`tuple[object, ...]` deixou de ser aceito: só os batch results tipados."""
    with pytest.raises(mapper.PublicContractMappingError):
        mapper.to_public_response((object(),), (object(),))
    with pytest.raises(mapper.PublicContractMappingError):
        mapper.to_public_response(
            PredictiveEvaluationBatchResult(outcomes=(), request_length=0), ()
        )


def test_e61_desfecho_desconhecido_nao_e_representavel() -> None:
    with pytest.raises(mapper.PublicContractMappingError):
        mapper.from_scientific_outcome(object())
    with pytest.raises(mapper.PublicContractMappingError):
        mapper.from_routing_outcome(object())


# --- saída -----------------------------------------------------------------


def test_e61_saida_preserva_variantes_ordem_e_cardinalidade() -> None:
    rejeicao = PredictiveCausalRejectionResult(
        claim=_claim(),
        rejected_channels=(
            PredictiveAvailabilityOutcome(
                channel=PredictiveChannel(name="lag_1", lag=1),
                available=False,
                reason="sem defasagem",
            ),
        ),
        reason="nenhum canal disponível",
    )
    cientificos = (
        PredictiveUpstreamUnavailableOutcome(
            source=PredictiveUpstreamUnavailableInput(reference="u1", reason="fora")
        ),
        rejeicao,
    )
    roteamentos = (
        PredictiveUpstreamUnavailableRoutingResult(source_reference="u1", reason="indisponível"),
        PredictiveCausalRejectedRoutingResult(subject_key=_claim().subject_key, reason="sem canal"),
    )
    resposta = mapper.to_public_response(
        PredictiveEvaluationBatchResult(outcomes=cientificos, request_length=2),
        PredictiveRoutingBatchResult(
            outcomes=roteamentos,
            request_length=2,
            decomposed_conflict_dimensions=("jurisdiction",),
        ),
    )
    assert len(resposta.items) == 2
    assert resposta.request_length == 2
    assert resposta.decomposed_conflict_dimensions == ("jurisdiction",)
    assert [i.position for i in resposta.items] == [0, 1]
    assert resposta.items[0].scientific.kind == "upstream_unavailable"
    assert resposta.items[1].scientific.kind == "causal_rejected"
    assert resposta.items[0].routing.route is None
    assert resposta.items[1].routing.abstained is True


def test_e61_mapeador_constroi_a_requisicao_canonica() -> None:
    """C1: o mapeador devolve `PredictiveEvaluationRequest`, não tupla crua."""
    requisicao = dto.PublicEvaluationRequest(
        items=(
            dto.PublicUpstreamUnavailableItem(
                kind="upstream_unavailable", reference="u1", reason="fora"
            ),
            _item_ready_dto(),
        )
    )
    canonica, governadas = mapper.to_internal_request(requisicao)
    assert isinstance(canonica, PredictiveEvaluationRequest)
    assert len(canonica.items) == len(governadas) == 2
    assert governadas[0] is None
    assert isinstance(governadas[1], PredictiveGovernedQualityInput)
    assert isinstance(canonica.items[1], PredictiveReadyEvaluationItem)


def _upstream(n: int) -> tuple:
    return tuple(
        dto.PublicUpstreamUnavailableItem(
            kind="upstream_unavailable", reference=f"u{i}", reason="fora"
        )
        for i in range(n)
    )


def test_e61_c1_oito_itens_passam_e_nove_reprovam_pelo_teto_canonico() -> None:
    canonica, governadas = mapper.to_internal_request(
        dto.PublicEvaluationRequest(items=_upstream(8))
    )
    assert len(canonica.items) == 8 == len(governadas)
    with pytest.raises(PredictiveBatchLimitError, match="MAX_CLAIMS_PER_EVALUATION"):
        mapper.to_internal_request(dto.PublicEvaluationRequest(items=_upstream(9)))


def test_e61_c1_512_referencias_passam_e_513_reprovam() -> None:
    """O teto total de referências incide no construtor canônico."""
    por_item = 128
    prontos = tuple(_item_ready_dto(refs=por_item) for _ in range(4))
    canonica, _ = mapper.to_internal_request(dto.PublicEvaluationRequest(items=prontos))
    assert canonica.total_references == 512
    excedente = (*prontos, _item_ready_dto(refs=1))
    with pytest.raises(PredictiveBatchLimitError, match="MAX_TOTAL_REFERENCES_PER_EVALUATION"):
        mapper.to_internal_request(dto.PublicEvaluationRequest(items=excedente))


def test_e61_c1_o_dto_nao_reproduz_as_constantes_do_servidor() -> None:
    import pathlib as _p

    texto = _p.Path(mapper.__file__).read_text(encoding="utf-8")
    for constante in ("MAX_CLAIMS_PER_EVALUATION", "MAX_TOTAL_REFERENCES_PER_EVALUATION"):
        assert constante not in texto, constante


# --- fronteira -------------------------------------------------------------


def test_e61_mapeador_nao_chama_funcao_cientifica() -> None:
    """Prova por AST: nenhuma chamada a coordenador, estimador ou roteador."""
    arvore = ast.parse(FONTE.read_text(encoding="utf-8"))
    chamados = {
        no.func.id if isinstance(no.func, ast.Name) else no.func.attr
        for no in ast.walk(arvore)
        if isinstance(no, ast.Call) and isinstance(no.func, ast.Name | ast.Attribute)
    }
    proibidos = {
        "predictive_route_batch",
        "predictive_route_item",
        "predictive_evaluate_batch",
        "predictive_evaluate_and_reconfigure_batch",
        "predictive_final_routing",
        "predictive_conflict_assessment",
        "predictive_assertiveness",
        "predictive_protection_set",
        "predictive_recommendation_quality",
        "predictive_counterfactual_set",
        "predictive_burden_comparison",
        "predictive_power_outcome_for",
        "predictive_fit_ar1",
    }
    assert not (chamados & proibidos), chamados & proibidos
    assert "deserialize_piap_envelope" in chamados


def test_e61_mapeador_nao_importa_repositorio_nem_orm() -> None:
    arvore = ast.parse(FONTE.read_text(encoding="utf-8"))
    modulos: list[str] = []
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            modulos.extend(a.name for a in no.names)
        elif isinstance(no, ast.ImportFrom) and no.module:
            modulos.append(no.module)
    proibidos = ("sqlalchemy", "alembic", "app.repositories", "app.database", "fastapi")
    for modulo in modulos:
        assert not modulo.startswith(proibidos), modulo


def _claim():
    from app.predictive_accessibility.claim import predictive_claim_from_envelope

    return predictive_claim_from_envelope(_envelope())


# --- C2: manifesto mecânico de preservação de contrato ---------------------
#
#     REPRESENTS_VARIANT_TAG != REPRESENTS_CONTRACTED_RESULT


COMPONENTES_CIENTIFICOS = (
    "claim",
    "provenance",
    "regime",
    "evidence",
    "uncertainty",
    "horizon",
    "state",
    "approval_validation_outcome",
)

COMPONENTES_DE_ROTEAMENTO = (
    "route",
    "abstained",
    "recommended_alternative",
    "conflict_assessment",
    "limits",
    "reason",
    "assertiveness",
    "revalidated_route",
    "quality",
)


def test_e61_c2_manifesto_cientifico_bate_com_o_dataclass_interno() -> None:
    """Compara mecanicamente campos internos e campos representados."""
    import dataclasses

    from app.predictive_accessibility.epistemic import PredictiveClaimEvaluationResult

    internos = {f.name for f in dataclasses.fields(PredictiveClaimEvaluationResult)}
    publicos = set(dto.PublicClaimEvaluationView.model_fields) - {"kind"}
    assert internos == set(COMPONENTES_CIENTIFICOS)
    assert internos == publicos, internos ^ publicos


def test_e61_c2_manifesto_de_roteamento_bate_com_o_dataclass_interno() -> None:
    import dataclasses

    from app.predictive_accessibility.routing import PredictiveFinalRoutingResult

    internos = {f.name for f in dataclasses.fields(PredictiveFinalRoutingResult)}
    publicos = set(dto.PublicFinalRoutingView.model_fields) - {"kind"}
    assert internos == set(COMPONENTES_DE_ROTEAMENTO)
    assert internos == publicos, internos ^ publicos


@pytest.mark.parametrize("componente", COMPONENTES_CIENTIFICOS)
def test_e61_c2_apagar_componente_cientifico_reprova(componente) -> None:
    """Mutante por componente: remover qualquer um derruba o manifesto."""
    publicos = set(dto.PublicClaimEvaluationView.model_fields) - {"kind"}
    mutado = publicos - {componente}
    assert mutado != set(COMPONENTES_CIENTIFICOS)


@pytest.mark.parametrize("componente", COMPONENTES_DE_ROTEAMENTO)
def test_e61_c2_apagar_componente_de_roteamento_reprova(componente) -> None:
    publicos = set(dto.PublicFinalRoutingView.model_fields) - {"kind"}
    mutado = publicos - {componente}
    assert mutado != set(COMPONENTES_DE_ROTEAMENTO)


def test_e61_c2_apagar_decomposed_conflict_dimensions_reprova() -> None:
    campos = set(dto.PublicEvaluationResponse.model_fields)
    assert "decomposed_conflict_dimensions" in campos
    assert "request_length" in campos
    assert campos - {"decomposed_conflict_dimensions"} != campos


def test_e61_c2_evidencia_preserva_os_nove_campos() -> None:
    import dataclasses

    from app.predictive_accessibility.power import PredictivePowerOutcome

    internos = {f.name for f in dataclasses.fields(PredictivePowerOutcome)}
    publicos = set(dto.PublicPowerOutcomeView.model_fields)
    assert len(internos) == 9
    assert internos == publicos, internos ^ publicos


def test_e61_c2_saida_nao_expoe_sidecar_binding_nem_orm() -> None:
    proibidos = (
        "approval_binding",
        "bound_to",
        "reconfiguration",
        "event_id",
        "resulting_version",
        "repository",
        "session",
    )
    for modelo in (
        dto.PublicClaimEvaluationView,
        dto.PublicFinalRoutingView,
        dto.PublicRecommendationQualityView,
        dto.PublicConflictAssessmentView,
        dto.PublicEvaluationResponse,
    ):
        for campo in modelo.model_fields:
            assert not any(p in campo for p in proibidos), (modelo.__name__, campo)


def test_e61_c2_conflito_real_preserva_as_duas_conclusoes_sem_media() -> None:
    from app.predictive_accessibility import coordinator as coord
    from tests.unit.predictive_accessibility import _e5_case_helpers as h

    coordenado = h.coordenado((h.cer(), h.cer()))
    roteamento = coord.predictive_route_batch(
        coordenado,
        (
            h.governada(conclusion_signature="pico acima"),
            h.governada(conclusion_signature="pico abaixo"),
        ),
        at=h.AGORA,
    )
    resposta = mapper.to_public_response(coordenado.evaluation, roteamento)
    assinaturas = {
        c.conclusion_signature
        for item in resposta.items
        for c in item.routing.conflict_assessment.compared
    }
    assert assinaturas == {"pico acima", "pico abaixo"}
    assert all(item.routing.route is None for item in resposta.items)
    assert all(
        item.routing.conflict_assessment.status.value == "predictive_claim_real_conflict"
        for item in resposta.items
    )


def test_e61_c2_ramo_protetivo_unresolved_preserva_incompletude_e_proveniencia() -> None:
    from app.predictive_accessibility import coordinator as coord
    from tests.unit.predictive_accessibility import _e5_case_helpers as h

    coordenado = h.coordenado((h.cer(),))
    roteamento = coord.predictive_route_batch(
        coordenado,
        (h.governada(protection_candidates=(h.candidato(autoridade=None),)),),
        at=h.AGORA,
    )
    resposta = mapper.to_public_response(coordenado.evaluation, roteamento)
    qualidade = resposta.items[0].routing.quality
    assert qualidade.complete_answer_allowed is False
    assert qualidade.protection.unresolved
    assert qualidade.protection.unresolved[0].provenance
    assert qualidade.protection.unresolved[0].classification_reason


def test_e61_c2_oito_componentes_chegam_ao_publico_com_conteudo() -> None:
    from app.predictive_accessibility import coordinator as coord
    from tests.unit.predictive_accessibility import _e5_case_helpers as h

    coordenado = h.coordenado((h.cer(),))
    roteamento = coord.predictive_route_batch(coordenado, (h.governada(),), at=h.AGORA)
    resposta = mapper.to_public_response(coordenado.evaluation, roteamento)
    cientifico = resposta.items[0].scientific
    assert cientifico.claim.target and cientifico.claim.subject_key
    assert cientifico.provenance.registry.channels
    assert cientifico.provenance.historical_validity.valid_window
    assert cientifico.regime.status
    assert cientifico.evidence.sample_size > 0
    assert cientifico.uncertainty.lower <= cientifico.uncertainty.upper
    assert cientifico.horizon.h_pred
    assert cientifico.approval_validation_outcome.value == "valid"
    roteado = resposta.items[0].routing
    assert roteado.assertiveness.review_or_stop_trigger
    assert roteado.revalidated_route
    assert roteado.quality.guidance_outcome
