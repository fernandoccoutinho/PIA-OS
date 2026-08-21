"""Contratos da fatia científica mínima do Patch 3 (`E5.c`–`E5.e`, estimador,
Power Gate e `E5.j`).

```text
CAUSAL_REJECTED -> NEVER_REACHES_ESTIMATOR_POWER_GATE_OR_E5_J
CLAIM_EVALUATION_RESULT = EIGHT_COMPONENTS_NONE_OPTIONAL
```
"""

import ast
import pathlib
import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.predictive_accessibility import availability as mod_availability
from app.predictive_accessibility import epistemic as mod_epistemic
from app.predictive_accessibility import estimator as mod_estimator
from app.predictive_accessibility.approval_validation import predictive_approval_validation
from app.predictive_accessibility.availability import (
    PredictiveCausalRejectionResult,
    predictive_availability,
)
from app.predictive_accessibility.channel import PredictiveChannel, PredictiveChannelRegistry
from app.predictive_accessibility.claim import predictive_claim_from_envelope
from app.predictive_accessibility.epistemic import (
    PredictiveClaimEvaluationResult,
    PredictiveEpistemicState,
    predictive_assemble_claim_evaluation_result,
    predictive_classify_epistemic_state,
)
from app.predictive_accessibility.estimator import (
    predictive_fit_ar1,
    predictive_fit_baseline,
    predictive_per_event_gains,
)
from app.predictive_accessibility.history import (
    PredictiveHistoricalValidity,
    PredictiveObservation,
)
from app.predictive_accessibility.horizon import (
    PredictiveHorizonPoint,
    predictive_horizon_spectrum,
)
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
from app.predictive_accessibility.power import (
    PredictivePowerOutcome,
    predictive_circular_block_bootstrap,
)
from app.predictive_accessibility.regime import (
    PredictiveRegimeStatus,
    predictive_regime_assessment,
)

pytestmark = pytest.mark.unit

_T0 = datetime(2026, 1, 1, tzinfo=UTC)
_PRODUCAO = pathlib.Path(mod_epistemic.__file__).resolve().parent


def _fonte(seq: int = 1) -> SourceReference:
    return SourceReference(
        kind=ProvenanceKind("policy.registry"),
        ref=uuid.UUID(int=seq),
        source_version=3,
        content_sha256="a" * 64,
    )


def _envelope(*, kind: BoundObjectKind = BoundObjectKind.PROMOTION_CANDIDATE) -> PiapEnvelope:
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
                bound_to=BoundObjectRef(kind=kind, ref=uuid.UUID(int=99)),
            ),
        ),
        payload_refs=(_fonte(1),),
        sealed_at=_T0,
    )


def _evidencia(**kwargs) -> PredictivePowerOutcome:
    base = {
        "a_minus": 0.5,
        "a_upper": 0.9,
        "a_star_worst": 0.9,
        "mean_gain": 0.7,
        "placebo_p": 0.0005,
        "g_real": 0.7,
        "g_shuffled_p95": -0.1,
        "sample_size": 192,
        "alpha_corrected": 0.05 / 3,
    }
    base.update(kwargs)
    return PredictivePowerOutcome(**base)


_VALIDADE = PredictiveHistoricalValidity(
    valid_window=(PredictiveObservation(reference="k1", provenance="p1", relevance_score=0.9),),
    historical_kernel=(),
    rho_min=0.5,
)
_REGIME = predictive_regime_assessment(d_regime=0.1, theta=0.5, beats_fluctuation=False)
_ESPECTRO = predictive_horizon_spectrum(
    (PredictiveHorizonPoint(1, 0.4, True, PredictiveRegimeStatus.NO_SHIFT),)
)

_REGISTRY = PredictiveChannelRegistry(
    channels=(PredictiveChannel(name="lag_1", lag=1),),
    estimator_library=("gaussian_marginal_baseline", "gaussian_ar1_ols"),
)


# --- E5.c ------------------------------------------------------------------


def test_e5c_alegacao_vem_do_envelope_e_tem_chave_canonica() -> None:
    alegacao = predictive_claim_from_envelope(_envelope())
    assert alegacao.target == "grid.load"
    assert alegacao.signal == "demand.peak"
    assert len(alegacao.subject_key) == 64
    assert alegacao.subject_key == predictive_claim_from_envelope(_envelope()).subject_key


def test_e5c_recusa_entrada_que_nao_e_envelope() -> None:
    with pytest.raises(TypeError):
        predictive_claim_from_envelope({"target": "x"})


# --- E5.d / E5.e -----------------------------------------------------------


def test_e5d_biblioteca_pre_registrada_nao_pode_ser_vazia() -> None:
    with pytest.raises(ValueError):
        PredictiveChannelRegistry(
            channels=(PredictiveChannel(name="c", lag=1),), estimator_library=()
        )


def test_e5e_disponibilidade_causal_por_defasagem() -> None:
    canal = PredictiveChannel(name="lag_1", lag=1)
    assert predictive_availability(canal, observed_at_offset=1).available
    assert not predictive_availability(canal, observed_at_offset=0).available


def test_e5e_rejeicao_causal_nao_admite_canal_disponivel() -> None:
    canal = PredictiveChannel(name="lag_1", lag=1)
    alegacao = predictive_claim_from_envelope(_envelope())
    with pytest.raises(ValueError):
        PredictiveCausalRejectionResult(
            claim=alegacao,
            rejected_channels=(predictive_availability(canal, observed_at_offset=1),),
            reason="x",
        )


def test_e5e_avail_zero_curto_circuita_antes_do_estimador(monkeypatch) -> None:
    """Prova por sonda: estimador, Power Gate e E5.j não são chamados."""
    chamadas: list[str] = []
    for alvo, nome in (
        (mod_estimator, "predictive_fit_baseline"),
        (mod_estimator, "predictive_fit_ar1"),
        (mod_estimator, "predictive_per_event_gains"),
        (mod_epistemic, "predictive_assemble_claim_evaluation_result"),
        (mod_epistemic, "predictive_classify_epistemic_state"),
    ):
        monkeypatch.setattr(
            alvo, nome, lambda *a, n=nome, **k: chamadas.append(n)  # pragma: no cover
        )

    canal = PredictiveChannel(name="lag_1", lag=1)
    resultado = mod_availability.predictive_availability(canal, observed_at_offset=0)
    if not resultado.available:
        rejeicao = PredictiveCausalRejectionResult(
            claim=predictive_claim_from_envelope(_envelope()),
            rejected_channels=(resultado,),
            reason="canal indisponível no instante de referência",
        )
    assert isinstance(rejeicao, PredictiveCausalRejectionResult)
    assert chamadas == []


# --- estimador -------------------------------------------------------------


def test_estimador_baseline_e_ar1_ajustam_e_produzem_ganho() -> None:
    pares = tuple((float(i), 0.8 * i + 0.1) for i in range(20))
    baseline = predictive_fit_baseline(tuple(y for _, y in pares))
    ar1 = predictive_fit_ar1(pares)
    ganhos = predictive_per_event_gains(baseline, ar1, pares[:5])
    assert len(ganhos) == 5
    assert all(isinstance(g, float) for g in ganhos)


def test_estimador_recusa_amostra_insuficiente_e_preditor_sem_variacao() -> None:
    with pytest.raises(ValueError):
        predictive_fit_baseline((1.0,))
    with pytest.raises(ValueError):
        predictive_fit_ar1(tuple((1.0, float(i)) for i in range(5)))


# --- Power Gate ------------------------------------------------------------


def test_power_bootstrap_e_deterministico_por_seed() -> None:
    ganhos = tuple(float(i % 7) - 3.0 for i in range(60))
    a = predictive_circular_block_bootstrap(
        ganhos, replicates=200, seed=7, alpha_corrected=0.05 / 3
    )
    b = predictive_circular_block_bootstrap(
        ganhos, replicates=200, seed=7, alpha_corrected=0.05 / 3
    )
    assert a == b
    assert a[0] <= a[1]


def test_power_gate_os_tres_estados_e_a_proibicao_de_baixa_potencia() -> None:
    assert (
        predictive_classify_epistemic_state(_evidencia(), a_rel=0.02, confirmatory_pass=True)
        is PredictiveEpistemicState.PREDICTABLE
    )
    assert (
        predictive_classify_epistemic_state(
            _evidencia(a_minus=-0.01, a_upper=0.003, a_star_worst=0.003),
            a_rel=0.02,
            confirmatory_pass=True,
        )
        is PredictiveEpistemicState.PREDICTIVELY_INACCESSIBLE
    )
    assert (
        predictive_classify_epistemic_state(
            _evidencia(a_minus=-0.01, a_upper=0.03, a_star_worst=0.03),
            a_rel=0.02,
            confirmatory_pass=True,
        )
        is PredictiveEpistemicState.UNRESOLVED
    )


def test_power_gate_confirmatorio_falho_nao_libera_predictable() -> None:
    assert (
        predictive_classify_epistemic_state(_evidencia(), a_rel=0.02, confirmatory_pass=False)
        is PredictiveEpistemicState.UNRESOLVED
    )


# --- approval step e E5.j --------------------------------------------------


def test_approval_step_produz_desfecho_tipado_e_nunca_none() -> None:
    desfecho = predictive_approval_validation(
        _envelope(),
        at=_T0,
        expected_version=2,
        required_scope=("bound.read",),
        expected_jurisdiction="br",
        expected_binding_kind=BoundObjectKind.PROMOTION_CANDIDATE,
    )
    assert desfecho is ApprovalValidationOutcome.VALID


def test_approval_step_vinculo_divergente_e_binding_mismatch() -> None:
    desfecho = predictive_approval_validation(
        _envelope(kind=BoundObjectKind.PROPOSED_BOUND),
        at=_T0,
        expected_version=2,
        required_scope=("bound.read",),
        expected_jurisdiction="br",
        expected_binding_kind=BoundObjectKind.PROMOTION_CANDIDATE,
    )
    assert desfecho is ApprovalValidationOutcome.BINDING_MISMATCH


def test_e5j_monta_cer_com_os_oito_componentes() -> None:
    resultado = predictive_assemble_claim_evaluation_result(
        claim=predictive_claim_from_envelope(_envelope()),
        registry=_REGISTRY,
        evidence=_evidencia(),
        approval_validation_outcome=ApprovalValidationOutcome.VALID,
        a_rel=0.02,
        confirmatory_pass=True,
        regime=_REGIME,
        horizon=_ESPECTRO,
        historical_validity=_VALIDADE,
    )
    campos = {
        "claim",
        "provenance",
        "regime",
        "evidence",
        "uncertainty",
        "horizon",
        "state",
        "approval_validation_outcome",
    }
    assert {f.name for f in resultado.__dataclass_fields__.values()} == campos
    assert all(getattr(resultado, nome) is not None for nome in campos)
    assert resultado.state is PredictiveEpistemicState.PREDICTABLE


def test_e5j_nao_produz_nem_consome_rejeicao_causal() -> None:
    fonte = pathlib.Path(mod_epistemic.__file__).read_text(encoding="utf-8")
    assert "PredictiveCausalRejectionResult" not in fonte
    assert "CAUSAL_REJECTED" not in fonte
    anotacoes = {f.type for f in PredictiveClaimEvaluationResult.__dataclass_fields__.values()}
    assert not any("Causal" in str(a) for a in anotacoes)


def test_e5j_cer_e_frozen_e_recusa_componente_nulo() -> None:
    resultado = predictive_assemble_claim_evaluation_result(
        claim=predictive_claim_from_envelope(_envelope()),
        registry=_REGISTRY,
        evidence=_evidencia(),
        approval_validation_outcome=ApprovalValidationOutcome.VALID,
        a_rel=0.02,
        confirmatory_pass=True,
        regime=_REGIME,
        horizon=_ESPECTRO,
        historical_validity=_VALIDADE,
    )
    assert resultado.__dataclass_params__.frozen
    with pytest.raises(ValueError):
        PredictiveClaimEvaluationResult(
            claim=resultado.claim,
            provenance=resultado.provenance,
            regime=resultado.regime,
            evidence=resultado.evidence,
            uncertainty=resultado.uncertainty,
            horizon=resultado.horizon,
            state=resultado.state,
            approval_validation_outcome=None,
        )


# --- prevenção de vazamento do fixture -------------------------------------


def test_producao_nao_contem_fixture_seed_phi_hash_ou_resultado_esperado() -> None:
    """O rótulo do braço, a seed e o `phi` pertencem ao teste, não à produção."""
    proibidos = ("E5P3-SYNTH", "fixture_id", "52066", "51991", "51141", "phi", "bb48404b")
    for caminho in sorted(_PRODUCAO.rglob("*.py")):
        if "__pycache__" in caminho.parts:
            continue
        texto = caminho.read_text(encoding="utf-8")
        for termo in proibidos:
            assert termo not in texto, f"{caminho.name}: {termo}"


def test_producao_da_fatia_usa_apenas_biblioteca_padrao() -> None:
    permitidos = ("app.predictive_accessibility",)
    padrao = {
        "__future__",
        "math",
        "random",
        "hashlib",
        "json",
        "dataclasses",
        "datetime",
        "enum",
        "typing",
        "collections",
    }
    novos = (
        "claim.py",
        "channel.py",
        "availability.py",
        "estimator.py",
        "power.py",
        "epistemic.py",
        "approval_validation.py",
    )
    for nome in novos:
        arvore = ast.parse((_PRODUCAO / nome).read_text(encoding="utf-8"))
        for no in ast.walk(arvore):
            modulos = []
            if isinstance(no, ast.Import):
                modulos = [a.name for a in no.names]
            elif isinstance(no, ast.ImportFrom) and no.module:
                modulos = [no.module]
            for modulo in modulos:
                raiz = modulo.split(".")[0]
                assert (
                    modulo.startswith(permitidos) or raiz in padrao or modulo in padrao
                ), f"{nome}: {modulo}"
