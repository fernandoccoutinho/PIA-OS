"""Contratos de `E5.f`, `E5.g`, `E5.k`, lote limitado e coordenador científico.

```text
RECENCY != RELEVANCE
CANDIDATE != CONFIRMED_SHIFT
DISCONTINUOUS_SPECTRUM != SINGLE_SUPREMUM
CAUSAL_REJECTED -> ZERO CHAMADAS E5.f/g/h/i/k/j
```
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.predictive_accessibility import approval_validation as mod_approval
from app.predictive_accessibility import epistemic as mod_epistemic
from app.predictive_accessibility import estimator as mod_estimator
from app.predictive_accessibility import history as mod_history
from app.predictive_accessibility import horizon as mod_horizon
from app.predictive_accessibility import power as mod_power
from app.predictive_accessibility import regime as mod_regime
from app.predictive_accessibility.availability import PredictiveCausalRejectionResult
from app.predictive_accessibility.batch import (
    MAX_CLAIMS_PER_EVALUATION,
    MAX_TOTAL_REFERENCES_PER_EVALUATION,
    PredictiveBatchItemTypeError,
    PredictiveBatchLimitError,
    PredictiveEvaluationContext,
    PredictiveEvaluationRequest,
    PredictiveReadyEvaluationItem,
    PredictiveUpstreamUnavailableInput,
    PredictiveUpstreamUnavailableOutcome,
)
from app.predictive_accessibility.channel import PredictiveChannel, PredictiveChannelRegistry
from app.predictive_accessibility.coordinator import (
    PredictiveReconfigurationInstruction,
    PredictiveUnsupportedLibraryError,
    predictive_evaluate_and_reconfigure_batch,
    predictive_evaluate_batch,
    predictive_power_outcome_for,
)
from app.predictive_accessibility.epistemic import (
    PredictiveClaimEvaluationResult,
    PredictiveEpistemicState,
)
from app.predictive_accessibility.history import PredictiveObservation
from app.predictive_accessibility.horizon import PredictiveHorizonPoint
from app.predictive_accessibility.piap.authority import (
    ApprovalBinding,
    AuthorityContext,
    BoundObjectRef,
)
from app.predictive_accessibility.piap.enums import (
    ApprovalValidationOutcome,
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
)
from app.predictive_accessibility.reconfiguration import (
    PredictiveCausalRejectedReconfigurationOutcome,
    PredictiveEvaluatedReconfigurationOutcome,
    PredictiveReconfigurationCandidate,
    PredictiveReconfigurationDecision,
    PredictiveUpstreamUnavailableReconfigurationOutcome,
)
from app.predictive_accessibility.regime import PredictiveRegimeStatus

pytestmark = pytest.mark.unit

_T0 = datetime(2026, 1, 1, tzinfo=UTC)


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


_REGISTRY = PredictiveChannelRegistry(
    channels=(PredictiveChannel(name="lag_1", lag=1),),
    estimator_library=("gaussian_marginal_baseline", "gaussian_ar1_ols"),
)


def _pares(*, slope: float = 0.8, phase: int = 0) -> tuple[tuple[float, float], ...]:
    return tuple((float(i), slope * i + (0.2 if (i + phase) % 3 else -0.15)) for i in range(40))


def _contexto(
    *, offset: int = 1, slope: float = 0.8, phase: int = 0
) -> PredictiveEvaluationContext:
    pares = _pares(slope=slope, phase=phase)
    return PredictiveEvaluationContext(
        registry=_REGISTRY,
        observed_at_offset=offset,
        observations=(
            PredictiveObservation(reference="obs-antiga", provenance="src-a", relevance_score=0.9),
            PredictiveObservation(reference="obs-recente", provenance="src-b", relevance_score=0.1),
        ),
        rho_min=0.5,
        d_regime=0.9,
        theta=0.5,
        beats_fluctuation=True,
        horizon_points=(
            PredictiveHorizonPoint(
                horizon=1, a_minus=0.4, gates_pass=True, regime=PredictiveRegimeStatus.NO_SHIFT
            ),
        ),
        training_pairs=pares[:24],
        blind_pairs=pares[24:],
        bootstrap_replicates=200,
        bootstrap_seed=7 + phase,
        alpha_corrected=0.05 / 3,
        placebo_permutations=200,
        placebo_seed=17 + phase,
        a_rel=0.02,
        at=_T0,
        expected_version=2,
        required_scope=("bound.read",),
        expected_jurisdiction="br",
        expected_binding_kind=BoundObjectKind.PROMOTION_CANDIDATE,
    )


def _ready(*, refs: int = 1, context: PredictiveEvaluationContext | None = None):
    return PredictiveReadyEvaluationItem(
        envelope=_envelope(refs), context=context if context is not None else _contexto()
    )


# --- E5.f ------------------------------------------------------------------


def test_e5f_antiga_com_score_alto_fica_em_v_t_e_recente_com_score_baixo_sai() -> None:
    antiga = PredictiveObservation(reference="k-1", provenance="p1", relevance_score=0.91)
    recente = PredictiveObservation(reference="k-99", provenance="p2", relevance_score=0.05)
    validade = mod_history.predictive_historical_validity((antiga, recente), rho_min=0.5)
    assert validade.valid_window == (antiga,)
    assert validade.historical_kernel == (recente,)
    assert validade.historical_kernel[0].provenance == "p2"


def test_e5f_observacao_exige_referencia_e_proveniencia() -> None:
    with pytest.raises(ValueError):
        PredictiveObservation(reference="", provenance="p", relevance_score=1.0)
    with pytest.raises(ValueError):
        PredictiveObservation(reference="k", provenance="", relevance_score=1.0)


# --- E5.g ------------------------------------------------------------------


def test_e5g_mudanca_abrupta_vira_candidato() -> None:
    r = mod_regime.predictive_regime_assessment(d_regime=0.9, theta=0.5, beats_fluctuation=True)
    assert r.status is PredictiveRegimeStatus.REGIME_SHIFT_CANDIDATE


def test_e5g_falsa_mudanca_nao_vira_candidato() -> None:
    sem_flutuacao = mod_regime.predictive_regime_assessment(
        d_regime=0.9, theta=0.5, beats_fluctuation=False
    )
    so_erro = mod_regime.predictive_regime_assessment(
        d_regime=0.1, theta=0.5, beats_fluctuation=True, high_prediction_error=True
    )
    so_desacordo = mod_regime.predictive_regime_assessment(
        d_regime=0.1, theta=0.5, beats_fluctuation=True, model_disagreement=True
    )
    for r in (sem_flutuacao, so_erro, so_desacordo):
        assert r.status is PredictiveRegimeStatus.NO_SHIFT


def test_e5g_nao_existe_confirmed_shift_no_vocabulario() -> None:
    assert {m.value for m in PredictiveRegimeStatus} == {"no_shift", "regime_shift_candidate"}


# --- E5.k ------------------------------------------------------------------


def test_e5k_espectro_descontinuo_preserva_lacuna() -> None:
    pontos = (
        PredictiveHorizonPoint(1, 0.4, True, PredictiveRegimeStatus.NO_SHIFT),
        PredictiveHorizonPoint(2, 0.3, True, PredictiveRegimeStatus.NO_SHIFT),
        PredictiveHorizonPoint(3, -0.1, True, PredictiveRegimeStatus.NO_SHIFT),
        PredictiveHorizonPoint(4, 0.2, True, PredictiveRegimeStatus.NO_SHIFT),
    )
    espectro = mod_horizon.predictive_horizon_spectrum(pontos)
    assert tuple(p.horizon for p in espectro.h_pred) == (1, 2, 4)
    assert tuple(p.horizon for p in espectro.delta_cont) == (1, 2)
    assert tuple(p.horizon for p in espectro.r_pred) == (4,)


def test_e5k_gate_reprovado_exclui_horizonte_mesmo_com_a_minus_positivo() -> None:
    pontos = (PredictiveHorizonPoint(1, 0.4, False, PredictiveRegimeStatus.NO_SHIFT),)
    espectro = mod_horizon.predictive_horizon_spectrum(pontos)
    assert espectro.h_pred == ()


# --- lote ------------------------------------------------------------------


def test_lote_no_teto_de_itens_e_aceito_e_um_acima_reprova() -> None:
    PredictiveEvaluationRequest(items=tuple(_ready() for _ in range(MAX_CLAIMS_PER_EVALUATION)))
    with pytest.raises(PredictiveBatchLimitError, match="MAX_CLAIMS_PER_EVALUATION"):
        PredictiveEvaluationRequest(
            items=tuple(_ready() for _ in range(MAX_CLAIMS_PER_EVALUATION + 1))
        )


def test_lote_total_de_referencias_acima_do_teto_reprova() -> None:
    por_item = MAX_TOTAL_REFERENCES_PER_EVALUATION // 4
    ok = PredictiveEvaluationRequest(items=tuple(_ready(refs=por_item) for _ in range(4)))
    assert ok.total_references == MAX_TOTAL_REFERENCES_PER_EVALUATION
    with pytest.raises(PredictiveBatchLimitError, match="MAX_TOTAL_REFERENCES_PER_EVALUATION"):
        PredictiveEvaluationRequest(items=(*ok.items, _ready(refs=1)))


def test_lote_recusa_envelope_cru_string_e_objeto_arbitrario() -> None:
    for invalido in (_envelope(), "not-an-e5-item", object()):
        with pytest.raises(PredictiveBatchItemTypeError, match="PredictiveReadyEvaluationItem"):
            PredictiveEvaluationRequest(items=(invalido,))


def test_item_pronto_e_request_validam_tipos_em_runtime() -> None:
    with pytest.raises(PredictiveBatchItemTypeError):
        PredictiveReadyEvaluationItem(envelope="x", context=_contexto())
    with pytest.raises(PredictiveBatchItemTypeError):
        PredictiveReadyEvaluationItem(envelope=_envelope(), context="x")
    with pytest.raises(PredictiveBatchItemTypeError):
        PredictiveEvaluationRequest(items=[_ready()])


def test_lote_preserva_comprimento_e_ordem() -> None:
    itens = (
        PredictiveUpstreamUnavailableInput(reference="u1", reason="fonte fora"),
        _ready(),
        PredictiveUpstreamUnavailableInput(reference="u2", reason="fonte fora"),
    )
    resultado = predictive_evaluate_batch(PredictiveEvaluationRequest(items=itens))
    assert len(resultado.outcomes) == len(itens)
    assert isinstance(resultado.outcomes[0], PredictiveUpstreamUnavailableOutcome)
    assert isinstance(resultado.outcomes[1], PredictiveClaimEvaluationResult)
    assert isinstance(resultado.outcomes[2], PredictiveUpstreamUnavailableOutcome)
    assert resultado.outcomes[0].source.reference == "u1"
    assert resultado.outcomes[2].source.reference == "u2"


# --- coordenador: as três arestas obrigatórias -----------------------------


def _espioes(monkeypatch) -> list[str]:
    chamadas: list[str] = []
    for modulo, nome in (
        (mod_history, "predictive_historical_validity"),
        (mod_regime, "predictive_regime_assessment"),
        (mod_estimator, "predictive_fit_baseline"),
        (mod_estimator, "predictive_fit_ar1"),
        (mod_estimator, "predictive_per_event_gains"),
        (mod_power, "predictive_circular_block_bootstrap"),
        (mod_power, "predictive_deterministic_placebo"),
        (mod_horizon, "predictive_horizon_spectrum"),
        (mod_approval, "predictive_approval_validation"),
        (mod_epistemic, "predictive_assemble_claim_evaluation_result"),
    ):
        real = getattr(modulo, nome)

        def espiao(*a, _real=real, _nome=nome, **k):
            chamadas.append(_nome)
            return _real(*a, **k)

        monkeypatch.setattr(modulo, nome, espiao)
    return chamadas


def test_coordenador_upstream_indisponivel_executa_zero_ciencia(monkeypatch) -> None:
    chamadas = _espioes(monkeypatch)
    resultado = predictive_evaluate_batch(
        PredictiveEvaluationRequest(
            items=(PredictiveUpstreamUnavailableInput(reference="u", reason="fora"),)
        ),
    )
    assert isinstance(resultado.outcomes[0], PredictiveUpstreamUnavailableOutcome)
    assert chamadas == []


def test_coordenador_rejeicao_causal_nao_chama_e5_f_g_h_i_k_j(monkeypatch) -> None:
    """Sondas no coordenador DE PRODUÇÃO, não num `if` reproduzido no teste."""
    chamadas = _espioes(monkeypatch)
    resultado = predictive_evaluate_batch(
        PredictiveEvaluationRequest(items=(_ready(context=_contexto(offset=0)),))
    )
    assert isinstance(resultado.outcomes[0], PredictiveCausalRejectionResult)
    assert chamadas == []


def test_coordenador_ramo_avaliado_percorre_a_cadeia_e_monta_o_cer(monkeypatch) -> None:
    chamadas = _espioes(monkeypatch)
    resultado = predictive_evaluate_batch(PredictiveEvaluationRequest(items=(_ready(),)))
    cer = resultado.outcomes[0]
    assert isinstance(cer, PredictiveClaimEvaluationResult)
    assert chamadas == [
        "predictive_historical_validity",
        "predictive_regime_assessment",
        "predictive_fit_baseline",
        "predictive_fit_ar1",
        "predictive_per_event_gains",
        "predictive_circular_block_bootstrap",
        "predictive_deterministic_placebo",
        "predictive_horizon_spectrum",
        "predictive_approval_validation",
        "predictive_assemble_claim_evaluation_result",
    ]
    assert cer.state in tuple(PredictiveEpistemicState)
    assert cer.approval_validation_outcome is ApprovalValidationOutcome.VALID


def test_cer_integrado_nao_tem_mais_placeholders_da_fatia_minima() -> None:
    resultado = predictive_evaluate_batch(PredictiveEvaluationRequest(items=(_ready(),)))
    cer = resultado.outcomes[0]
    assert cer.regime.status is PredictiveRegimeStatus.REGIME_SHIFT_CANDIDATE
    assert tuple(p.horizon for p in cer.horizon.h_pred) == (1,)
    assert cer.provenance.historical_validity.valid_window[0].reference == "obs-antiga"
    fonte = __import__("pathlib").Path(mod_epistemic.__file__).read_text(encoding="utf-8")
    assert "NOT_ASSESSED_IN_MINIMAL_SLICE" not in fonte
    assert "SINGLE_HORIZON_FROM_CLAIM" not in fonte


def test_lote_isola_contexto_e_evidencia_por_alegacao() -> None:
    primeiro = _ready(context=_contexto(slope=0.8, phase=0))
    segundo = _ready(context=_contexto(slope=-0.35, phase=1))
    resultado = predictive_evaluate_batch(PredictiveEvaluationRequest(items=(primeiro, segundo)))
    a, b = resultado.outcomes
    assert isinstance(a, PredictiveClaimEvaluationResult)
    assert isinstance(b, PredictiveClaimEvaluationResult)
    assert a.evidence is not b.evidence
    assert a.evidence != b.evidence


def test_biblioteca_fora_da_mvp_falha_fechada() -> None:
    contexto = _contexto()
    invalido = PredictiveEvaluationContext(
        **{
            **contexto.__dict__,
            "registry": PredictiveChannelRegistry(
                channels=contexto.registry.channels,
                estimator_library=("gaussian_marginal_baseline", "unknown"),
            ),
        }
    )
    with pytest.raises(PredictiveUnsupportedLibraryError):
        predictive_power_outcome_for(invalido)


def test_contexto_publico_nao_carrega_evidencia_precomputada() -> None:
    fields = set(PredictiveEvaluationContext.__dataclass_fields__)
    assert "evidence" not in fields
    assert "confirmatory_pass" not in fields
    assert {"training_pairs", "blind_pairs", "bootstrap_seed", "placebo_seed"} <= fields


class _NoSqlRepository:
    def __getattr__(self, name: str):
        raise AssertionError(f"E5.l tentou SQL no ramo não aplicável: {name}")


def test_sidecar_e5l_preserva_alinhamento_e_zero_sql_nos_ramos_curtos() -> None:
    request = PredictiveEvaluationRequest(
        items=(
            PredictiveUpstreamUnavailableInput(reference="u", reason="fora"),
            _ready(context=_contexto(offset=0)),
            _ready(),
        )
    )
    result = predictive_evaluate_and_reconfigure_batch(
        request,
        (None, None, None),
        _NoSqlRepository(),
    )
    assert len(result.evaluation.outcomes) == len(result.reconfiguration) == 3
    assert all(
        outcome.decision is PredictiveReconfigurationDecision.NOT_APPLICABLE
        for outcome in result.reconfiguration
    )
    assert isinstance(
        result.reconfiguration[0], PredictiveUpstreamUnavailableReconfigurationOutcome
    )
    assert isinstance(result.reconfiguration[1], PredictiveCausalRejectedReconfigurationOutcome)
    assert isinstance(result.reconfiguration[2], PredictiveEvaluatedReconfigurationOutcome)


def test_sidecar_e5l_chama_gate_real_de_producao_no_ramo_avaliado(monkeypatch) -> None:
    ready = _ready()
    evaluation = predictive_evaluate_batch(PredictiveEvaluationRequest(items=(ready,)))
    claim = evaluation.outcomes[0]
    assert isinstance(claim, PredictiveClaimEvaluationResult)
    candidate = PredictiveReconfigurationCandidate(
        candidate_ref=uuid.UUID(int=99),
        subject_key=claim.claim.subject_key,
        model_ref="model:v2",
        hypothesis_refs=("hypothesis:shift",),
        validation_ref="validation:blind:1",
        cost_ref="cost:1",
        responsible_ref="owner:1",
        rollback_plan_ref="rollback:1",
        candidate_payload_sha256="b" * 64,
        expected_version=1,
        proposed_version=2,
    )
    calls: list[str] = []

    def _gate(**kwargs):
        calls.append(kwargs["candidate"].model_ref)
        return PredictiveEvaluatedReconfigurationOutcome(
            PredictiveReconfigurationDecision.PROMOTED,
            kwargs["event_id"],
            kwargs["candidate"].subject_key,
            2,
            "spy",
        )

    monkeypatch.setattr(
        "app.predictive_accessibility.reconfiguration.predictive_reconfiguration_gate",
        _gate,
    )
    instruction = PredictiveReconfigurationInstruction(candidate, uuid.uuid4(), _T0)
    result = predictive_evaluate_and_reconfigure_batch(
        PredictiveEvaluationRequest(items=(ready,)),
        (instruction,),
        _NoSqlRepository(),
    )
    assert calls == ["model:v2"]
    assert result.reconfiguration[0].decision is PredictiveReconfigurationDecision.PROMOTED
