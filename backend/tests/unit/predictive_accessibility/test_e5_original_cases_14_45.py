"""Casos ORIGINAIS 14–45 — significados LITERAIS do plano E5.0.

Cada teste declara `CASO = "NN"` e o checker `test_c00_*` compara a descrição do
manifesto com a docstring. Renumerar semanticamente reprova.

```text
CASE_NUMBER_WITHOUT_CASE_MEANING = RENUMBERING
```
"""

import json
import pathlib
from dataclasses import replace
from datetime import UTC, datetime

import pytest

from app.predictive_accessibility import guidance as mod_guidance
from app.predictive_accessibility.assertiveness import PredictiveAuthorityState
from app.predictive_accessibility.availability import (
    PredictiveAvailabilityOutcome,
    PredictiveCausalRejectionResult,
)
from app.predictive_accessibility.batch import (
    PredictiveGovernedQualityInput,
    PredictiveUpstreamUnavailableInput,
    PredictiveUpstreamUnavailableOutcome,
)
from app.predictive_accessibility.burden import (
    PredictiveBurdenDimensionKind,
    PredictiveExpectedLossError,
    PredictiveIncomparableBurdenError,
    PredictiveProbabilityValidation,
    PredictiveTotalBurdenVector,
)
from app.predictive_accessibility.channel import PredictiveChannel
from app.predictive_accessibility.counterfactual import (
    PredictiveAlternative,
    PredictiveAlternativeKind,
    PredictiveCostKnowledge,
)
from app.predictive_accessibility.epistemic import PredictiveEpistemicState
from app.predictive_accessibility.guidance import (
    PredictiveGuidanceDisposition,
    PredictiveGuidanceOutcome,
)
from app.predictive_accessibility.piap.enums import ApprovalValidationOutcome
from app.predictive_accessibility.predictive_claim_conflict import (
    PredictiveComparableClaim,
    PredictiveConflictStatus,
    predictive_conflict_assessment,
)
from app.predictive_accessibility.protection import PredictiveMaterialityStatus
from app.predictive_accessibility.routing import (
    PredictiveCausalRejectedRoutingResult,
    PredictiveFinalRoutingResult,
    PredictiveRoute,
    PredictiveUpstreamUnavailableRoutingResult,
)
from tests.unit.predictive_accessibility import _e5_case_helpers as h

pytestmark = pytest.mark.unit

MANIFESTO = json.loads(
    (
        pathlib.Path(__file__).resolve().parents[2]
        / "fixtures"
        / "predictive_accessibility"
        / "case_contracts_14_45.json"
    ).read_text(encoding="utf-8")
)


def test_c00_manifesto_cobre_14_a_45_e_bate_com_os_testes() -> None:
    """Checker mecânico: freeze, manifesto, número e teste têm de coincidir."""
    esperados = {str(n) for n in range(14, 46)}
    assert set(MANIFESTO["cases"]) == esperados

    modulo = pathlib.Path(__file__).read_text(encoding="utf-8")
    import ast

    arvore = ast.parse(modulo)
    declarados: dict[str, str] = {}
    for no in arvore.body:
        if not isinstance(no, ast.FunctionDef) or not no.name.startswith("test_c"):
            continue
        caso = None
        for filho in no.body:
            if (
                isinstance(filho, ast.Assign)
                and isinstance(filho.targets[0], ast.Name)
                and filho.targets[0].id == "CASO"
            ):
                caso = filho.value.value
        if caso is None:
            continue
        docstring = ast.get_docstring(no) or ""
        assert caso not in declarados, f"caso {caso} declarado duas vezes"
        declarados[caso] = docstring.splitlines()[0] if docstring else ""
    assert set(declarados) == esperados, esperados - set(declarados)
    for numero, primeira_linha in declarados.items():
        assert primeira_linha == MANIFESTO["cases"][numero], (
            numero,
            primeira_linha,
            MANIFESTO["cases"][numero],
        )

    freeze = pathlib.Path(__file__).resolve().parents[3] / "docs" / "entregas" / "entrega-5"
    fontes = {
        range(14, 24): freeze / "E5_0_CONFLICT_AND_ASSERTIVENESS.md",
        range(24, 34): freeze / "E5_0_COMPLETENESS_AND_PROTECTION.md",
        range(34, 46): freeze / "E5_0_TOTAL_BURDEN_AND_COUNTERFACTUAL.md",
    }
    for intervalo, documento in fontes.items():
        autoridade = documento.read_text(encoding="utf-8").replace("`", "")
        for numero in intervalo:
            descricao = MANIFESTO["cases"][str(numero)]
            assert f"| {numero} | {descricao} |" in autoridade, (numero, documento)


def test_c14() -> None:
    """mesmo alvo e horizonte, previsões incompatíveis"""
    CASO = "14"
    assert CASO
    a = PredictiveComparableClaim(
        evaluation=h.cer(), key=h.CHAVE, conclusion_signature="pico acima"
    )
    b = PredictiveComparableClaim(
        evaluation=h.cer(), key=h.CHAVE, conclusion_signature="pico abaixo"
    )
    r = predictive_conflict_assessment((a, b))
    assert r.status is PredictiveConflictStatus.PREDICTIVE_CLAIM_REAL_CONFLICT
    assert r.compared == (a, b)


def test_c15() -> None:
    """alvos, horizontes ou regimes diferentes"""
    CASO = "15"
    assert CASO
    a = PredictiveComparableClaim(
        evaluation=h.cer(), key=h.CHAVE, conclusion_signature="pico acima"
    )
    b = PredictiveComparableClaim(
        evaluation=h.cer(),
        key=replace(h.CHAVE, jurisdiction="pt"),
        conclusion_signature="pico abaixo",
    )
    r = predictive_conflict_assessment((a, b))
    assert r.status is PredictiveConflictStatus.PREDICTIVE_CLAIM_FALSE_CONFLICT_DECOMPOSED
    assert "jurisdiction" in r.incommensurable_dimensions


def test_c16() -> None:
    """PREDICTABLE coexistindo com restrição UNRESOLVED"""
    CASO = "16"
    assert CASO
    from app.predictive_accessibility import coordinator as mod_coordinator

    coordenado = h.coordenado((h.cer(), h.cer(state=PredictiveEpistemicState.UNRESOLVED)))
    resultado = mod_coordinator.predictive_route_batch(
        coordenado,
        (
            h.governada(),
            h.governada(conclusion_signature="carga de pico acima do limiar"),
        ),
        at=h.AGORA,
    )
    assert [o.route for o in resultado.outcomes] == [
        PredictiveRoute.PREDICT,
        PredictiveRoute.INVESTIGATE,
    ]


def test_c17() -> None:
    """resposta composta ROBUST com limites legítimos e reversíveis"""
    CASO = "17"
    assert CASO
    r = h.rotear(evaluation=h.cer(state=PredictiveEpistemicState.PREDICTIVELY_INACCESSIBLE))
    assert r.route is PredictiveRoute.ROBUST
    assert r.assertiveness.review_or_stop_trigger


@pytest.mark.parametrize(
    "desfecho",
    [
        ApprovalValidationOutcome.MISSING,
        ApprovalValidationOutcome.EXPIRED,
        ApprovalValidationOutcome.VERSION_MISMATCH,
        ApprovalValidationOutcome.OUT_OF_SCOPE,
    ],
)
def test_c18(desfecho) -> None:
    """ausência de limites autorizados"""
    CASO = "18"
    assert CASO
    r = h.rotear(
        evaluation=h.cer(
            state=PredictiveEpistemicState.PREDICTIVELY_INACCESSIBLE, approval=desfecho
        )
    )
    assert r.route is None and r.abstained


def test_c19() -> None:
    """desacordo entre modelos"""
    CASO = "19"
    assert CASO
    from app.predictive_accessibility.regime import (
        PredictiveRegimeStatus,
        predictive_regime_assessment,
    )

    avaliacao = predictive_regime_assessment(
        d_regime=0.1, theta=0.5, beats_fluctuation=True, model_disagreement=True
    )
    assert avaliacao.status is PredictiveRegimeStatus.NO_SHIFT
    r = h.rotear()
    assert r.route is not PredictiveRoute.RECONFIGURE


def test_c20() -> None:
    """saída assertiva completa"""
    CASO = "20"
    assert CASO
    a = h.rotear(governed=h.governada(conclusion_signature="pico acima")).assertiveness
    assert a.candidate_conclusion == "pico acima"
    assert a.candidate_conclusion != h.cer().state.value
    assert a.decisive_constraint
    assert a.uncertainty and a.next_governed_route and a.review_or_stop_trigger
    assert a.authority_state is PredictiveAuthorityState.AUTHORIZED


def test_c21() -> None:
    """conflito sem rota segura"""
    CASO = "21"
    assert CASO
    from app.predictive_accessibility import coordinator as mod_coordinator

    coordenado = h.coordenado((h.cer(), h.cer()))
    resultado = mod_coordinator.predictive_route_batch(
        coordenado,
        (
            h.governada(conclusion_signature="pico acima"),
            h.governada(conclusion_signature="pico abaixo"),
        ),
        at=h.AGORA,
    )
    for desfecho in resultado.outcomes:
        assert desfecho.route is None
        assert desfecho.abstained
        assert any("conflito real" in limite for limite in desfecho.limits)


def test_c21b_conflito_real_de_um_grupo_nao_some_nem_bloqueia_outro() -> None:
    """Grupo incomensurável não apaga o conflito real nem herda sua abstenção."""
    from app.predictive_accessibility import coordinator as mod_coordinator

    coordenado = h.coordenado((h.cer(), h.cer(), h.cer()))
    resultado = mod_coordinator.predictive_route_batch(
        coordenado,
        (
            h.governada(conclusion_signature="pico acima"),
            h.governada(conclusion_signature="pico abaixo"),
            h.governada(
                conclusion_signature="outra conclusão",
                comparability_key=replace(h.CHAVE, jurisdiction="pt"),
            ),
        ),
        at=h.AGORA,
    )
    assert [o.route for o in resultado.outcomes] == [
        None,
        None,
        PredictiveRoute.PREDICT,
    ]
    assert "jurisdiction" in resultado.decomposed_conflict_dimensions


def test_c22() -> None:
    """tentativa de média ou voto como validação"""
    CASO = "22"
    assert CASO
    import ast

    from app.predictive_accessibility import predictive_claim_conflict as mod

    arvore = ast.parse(pathlib.Path(mod.__file__).read_text(encoding="utf-8"))
    chamados = {
        no.func.id if isinstance(no.func, ast.Name) else no.func.attr
        for no in ast.walk(arvore)
        if isinstance(no, ast.Call) and isinstance(no.func, ast.Name | ast.Attribute)
    }
    assert not (chamados & {"mean", "fmean", "median", "average", "vote", "majority"})


def test_c23() -> None:
    """escolha silenciosa de modelo ou provedor"""
    CASO = "23"
    assert CASO
    import ast

    from app.predictive_accessibility import routing as mod_routing

    base = pathlib.Path(mod_routing.__file__).parent
    for nome in ("routing.py", "coordinator.py", "predictive_claim_conflict.py"):
        arvore = ast.parse((base / nome).read_text(encoding="utf-8"))
        nomes = {n.name for n in ast.walk(arvore) if isinstance(n, ast.FunctionDef | ast.ClassDef)}
        assert not any("provider" in n.lower() or "agent" in n.lower() for n in nomes)


def test_c24() -> None:
    """decisão estratégica correta com proteção material omitida"""
    CASO = "24"
    assert CASO
    r = h.rotear(
        governed=h.governada(
            protection_candidates=(),
            required_protection_identifiers=("protecao-civil",),
        )
    )
    assert r.quality.protection.coverage_unresolved_reason
    assert not r.quality.complete_answer_allowed
    assert r.recommended_alternative is None


def test_c25() -> None:
    """proteção correta com risco de escalada omitido"""
    CASO = "25"
    assert CASO
    r = h.rotear(
        governed=h.governada(
            protection_candidates=(h.candidato(ident="protecao-civil"),),
            required_protection_identifiers=("protecao-civil", "risco-escalada"),
        )
    )
    assert "risco-escalada" in (r.quality.protection.coverage_unresolved_reason or "")
    assert not r.quality.complete_answer_allowed
    assert r.recommended_alternative is None


def test_c26() -> None:
    """múltiplos ramos preservados separadamente"""
    CASO = "26"
    assert CASO
    conjunto = h.rotear(
        governed=h.governada(
            protection_candidates=(
                h.candidato(),
                h.candidato(ident="p2", material=False),
                h.candidato(ident="p3", autoridade=None),
            )
        )
    ).quality.protection
    assert len(conjunto.accepted) == 1
    assert len(conjunto.rejected) == 1
    assert len(conjunto.unresolved) == 1


def test_c27() -> None:
    """orientação emergencial com fonte, versão, jurisdição e tempo válidos"""
    CASO = "27"
    assert CASO
    r = h.rotear()
    assert r.quality.guidance_outcome is PredictiveGuidanceOutcome.VALID
    assert r.quality.disposition is PredictiveGuidanceDisposition.USE_PROCEDURAL_DETAIL
    assert r.quality.procedural_detail_allowed
    assert r.recommended_alternative is not None


@pytest.mark.parametrize(
    ("mutacao", "esperado"),
    [
        (None, PredictiveGuidanceOutcome.MISSING),
        ({"reference": "  "}, PredictiveGuidanceOutcome.INVALID),
        ({"authority": ""}, PredictiveGuidanceOutcome.INVALID),
        ({"version": -999}, PredictiveGuidanceOutcome.INVALID),
        ({"jurisdiction": "xx"}, PredictiveGuidanceOutcome.JURISDICTION_MISMATCH),
        ({"version": 9}, PredictiveGuidanceOutcome.VERSION_MISMATCH),
        (
            {"valid_until": datetime(2026, 2, 1, tzinfo=UTC)},
            PredictiveGuidanceOutcome.STALE,
        ),
    ],
)
def test_c28(mutacao, esperado) -> None:
    """orientação ausente ou obsoleta convertida em instrução"""
    CASO = "28"
    assert CASO
    ruim = None if mutacao is None else replace(h.ORIENTACAO, **mutacao)
    # E5.p calcula
    assert (
        mod_guidance.predictive_validate_guidance(
            ruim, at=h.AGORA, expected_jurisdiction="br", expected_version=3
        )
        is esperado
    )
    r = h.rotear(governed=h.governada(guidance=ruim))
    # E5.p
    assert r.quality.guidance_outcome is esperado
    assert not r.quality.procedural_detail_allowed
    # E5.q e E5.s
    assert r.recommended_alternative is None
    assert any(esperado.value in limite for limite in r.limits)


def test_c29() -> None:
    """ações protetivas incompatíveis combinadas sem evidência"""
    CASO = "29"
    assert CASO
    conjunto = h.rotear(
        governed=h.governada(
            protection_candidates=(
                h.candidato(ident="evacuar", incompativel_com=("abrigar-no-local",)),
                h.candidato(ident="abrigar-no-local", incompativel_com=("evacuar",)),
            ),
            required_protection_identifiers=("evacuar", "abrigar-no-local"),
        )
    ).quality.protection
    assert not conjunto.accepted
    assert {c.identifier for c in conjunto.unresolved} == {"evacuar", "abrigar-no-local"}


def test_c30() -> None:
    """E5 tenta enviar alerta, ordenar abrigo/evacuação ou mobilizar equipes"""
    CASO = "30"
    assert CASO
    import ast

    from app.predictive_accessibility import routing as mod_routing

    base = pathlib.Path(mod_routing.__file__).parent
    verbos = {"dispatch", "publish", "notify", "alert", "broadcast", "evacuate", "mobilize"}
    for nome in ("routing.py", "coordinator.py", "protection.py", "counterfactual.py"):
        arvore = ast.parse((base / nome).read_text(encoding="utf-8"))
        for no in ast.walk(arvore):
            if isinstance(no, ast.FunctionDef | ast.ClassDef):
                tokens = set(no.name.lower().split("_"))
                assert not (tokens & verbos), f"{nome}: {no.name}"


def test_c31() -> None:
    """cenário sem frente adicional material expandido artificialmente"""
    CASO = "31"
    assert CASO
    conjunto = h.rotear(
        governed=h.governada(protection_candidates=(h.candidato(material=False),))
    ).quality.protection
    assert conjunto.rejected[0].materiality is PredictiveMaterialityStatus.NOT_SUPPORTED
    assert not conjunto.accepted


def test_c32() -> None:
    """ataque nuclear não atribuído sem recomendação de proteção civil"""
    CASO = "32"
    assert CASO
    r = h.rotear(
        governed=h.governada(
            conclusion_signature="não retaliar agora",
            protection_candidates=(),
            required_protection_identifiers=("protecao-civil-imediata",),
        )
    )
    assert r.quality.protection.coverage_unresolved_reason
    assert r.recommended_alternative is None


def test_c33b_unresolved_nunca_vira_resposta_completa() -> None:
    """33b: ramo UNRESOLVED permanece visível e bloqueia completude."""
    r = h.rotear(governed=h.governada(protection_candidates=(h.candidato(completo=False),)))
    assert r.quality.protection.unresolved
    assert not r.quality.complete_answer_allowed
    assert r.recommended_alternative is None


def test_c33c_autoridade_material_precisa_bater_com_o_vinculo_piap() -> None:
    """Autoridade e expectativa fabricadas não substituem o vínculo PIAP real."""
    falsa = replace(
        h.AUTORIDADE,
        reference="FAKE-REF",
        authority="autoridade fabricada",
        jurisdiction="zz",
        version=99,
        scope=("fake.scope",),
    )
    r = h.rotear(
        governed=h.governada(
            protection_candidates=(h.candidato(autoridade=falsa),),
            materiality_required_scope=("fake.scope",),
        )
    )
    assert not r.quality.protection.accepted
    assert r.quality.protection.unresolved
    assert "PIAP" in r.quality.protection.unresolved[0].classification_reason


def test_c33() -> None:
    """ramo protetivo sem owner, autoridade ou gatilho aplicável"""
    CASO = "33"
    assert CASO
    aceito = h.rotear().quality.protection.accepted[0]
    assert aceito.owner and aceito.authority is not None and aceito.triggers
    incompleto = h.rotear(
        governed=h.governada(protection_candidates=(h.candidato(completo=False),))
    ).quality.protection
    assert not incompleto.accepted


def test_c34() -> None:
    """ação com custo explícito e inação tratada como custo zero"""
    CASO = "34"
    assert CASO
    with pytest.raises(ValueError):
        PredictiveAlternative(
            kind=PredictiveAlternativeKind.A0_INACTION,
            key=h.CHAVE,
            cost_knowledge=PredictiveCostKnowledge.UNKNOWN,
            cost_value=0.0,
            reversible=True,
            description="inação",
        )


def test_c35() -> None:
    """comparação financeira que omite dano social material"""
    CASO = "35"
    assert CASO
    dimensoes = tuple(
        d
        for d in h.vetor(1.0, social=8.0).dimensions
        if d.kind is not PredictiveBurdenDimensionKind.SOCIAL_HUMAN
    )
    with pytest.raises(ValueError):
        PredictiveTotalBurdenVector(
            dimensions=dimensoes,
            probability_validation=PredictiveProbabilityValidation.VALIDATED,
        )


def test_c36() -> None:
    """monetização ou ponderação social sem método e autoridade"""
    CASO = "36"
    assert CASO
    import ast

    from app.predictive_accessibility import burden as mod

    arvore = ast.parse(pathlib.Path(mod.__file__).read_text(encoding="utf-8"))
    metodos = {n.name for n in ast.walk(arvore) if isinstance(n, ast.FunctionDef)}
    assert "total" not in metodos and "score" not in metodos
    assert not any("monet" in m.lower() or "weight" in m.lower() for m in metodos)


def test_c37() -> None:
    """incidência do ônus sobre grupo vulnerável omitida"""
    CASO = "37"
    assert CASO
    original = h.vetor(3.0, vulneravel=True)
    social = next(
        d for d in original.dimensions if d.kind is PredictiveBurdenDimensionKind.SOCIAL_HUMAN
    )
    with pytest.raises(ValueError):
        replace(social, incidence="")


def test_c38() -> None:
    """horizontes, populações ou regimes assimétricos sem justificativa"""
    CASO = "38"
    assert CASO
    alternativas = list(h.alternativas())
    alternativas[2] = replace(alternativas[2], key=replace(h.CHAVE, horizon=7))
    with pytest.raises(ValueError):
        h.rotear(governed=h.governada(alternatives=tuple(alternativas)))
    assert h.rotear(
        governed=h.governada(
            alternatives=tuple(alternativas),
            asymmetry_justification="horizonte distinto declarado",
        )
    )


def test_c39() -> None:
    """ação escalonada reversível dominante omitida"""
    CASO = "39"
    assert CASO
    alternativas = tuple(
        a
        for a in h.alternativas()
        if a.kind is not PredictiveAlternativeKind.A1_REVERSIBLE_ESCALATION
    )
    with pytest.raises(ValueError):
        h.rotear(governed=h.governada(alternatives=alternativas))


def test_c40() -> None:
    """alternativa dominada recomendada sem restrição decisiva"""
    CASO = "40"
    assert CASO
    entradas = (
        (PredictiveAlternativeKind.A0_INACTION, h.vetor(1.0)),
        (PredictiveAlternativeKind.A1_REVERSIBLE_ESCALATION, h.vetor(9.0)),
        (PredictiveAlternativeKind.A2_FULL_ACTION, h.vetor(9.0)),
    )
    r = h.rotear(governed=h.governada(burden_entries=entradas))
    assert r.recommended_alternative is not PredictiveAlternativeKind.A1_REVERSIBLE_ESCALATION
    assert r.recommended_alternative is not PredictiveAlternativeKind.A2_FULL_ACTION


def test_c41() -> None:
    """inação legitimamente preferível por menor ônus total"""
    CASO = "41"
    assert CASO
    entradas = (
        (PredictiveAlternativeKind.A0_INACTION, h.vetor(1.0)),
        (PredictiveAlternativeKind.A1_REVERSIBLE_ESCALATION, h.vetor(9.0)),
        (PredictiveAlternativeKind.A2_FULL_ACTION, h.vetor(9.0)),
    )
    r = h.rotear(governed=h.governada(burden_entries=entradas))
    assert r.recommended_alternative is PredictiveAlternativeKind.A0_INACTION
    assert any("A0 preservada" in limite for limite in r.limits)


def test_c42() -> None:
    """probabilidade não validada usada em perda esperada numérica"""
    CASO = "42"
    assert CASO
    with pytest.raises(PredictiveExpectedLossError):
        h.vetor(1.0, validacao=PredictiveProbabilityValidation.NOT_VALIDATED).expected_loss(0.5)
    with pytest.raises(PredictiveExpectedLossError):
        h.vetor(1.0).expected_loss(1.5)
    assert h.vetor(2.0).expected_loss(0.5) == pytest.approx(1.0)


def test_c43() -> None:
    """cenários e limites válidos com rota robusta e gatilho de revisão"""
    CASO = "43"
    assert CASO
    r = h.rotear(evaluation=h.cer(state=PredictiveEpistemicState.PREDICTIVELY_INACCESSIBLE))
    assert r.route is PredictiveRoute.ROBUST
    assert r.assertiveness.review_or_stop_trigger
    assert r.revalidated_route in {"robust", "investigate"}
    assert r.quality is not None


def test_c44() -> None:
    """vetor plural preservado sem soma arbitrária, com trade-offs"""
    CASO = "44"
    assert CASO
    entradas = (
        (PredictiveAlternativeKind.A0_INACTION, h.vetor(3.0)),
        (PredictiveAlternativeKind.A1_REVERSIBLE_ESCALATION, h.vetor(1.0, social=9.0)),
        (PredictiveAlternativeKind.A2_FULL_ACTION, h.vetor(5.0)),
    )
    r = h.rotear(governed=h.governada(burden_entries=entradas))
    assert r.conflict_assessment is not None
    assert any("trade-off" in limite for limite in r.limits)
    assert r.recommended_alternative is None
    with pytest.raises(PredictiveIncomparableBurdenError):
        h.vetor(1.0).dominates(h.vetor(1.0, unidade_social="outra"))


def test_c45() -> None:
    """recomendação comparativa convertida em efeito externo pela E5"""
    CASO = "45"
    assert CASO
    import ast

    from app.predictive_accessibility import routing as mod_routing

    base = pathlib.Path(mod_routing.__file__).parent
    proibidos = {"requests", "httpx", "socket", "subprocess", "queue", "smtplib"}
    for nome in ("routing.py", "counterfactual.py", "burden.py", "guidance.py"):
        arvore = ast.parse((base / nome).read_text(encoding="utf-8"))
        for no in ast.walk(arvore):
            modulos = []
            if isinstance(no, ast.Import):
                modulos = [a.name for a in no.names]
            elif isinstance(no, ast.ImportFrom) and no.module:
                modulos = [no.module]
            for modulo in modulos:
                assert modulo.split(".")[0] not in proibidos


def test_c46_nao_existe_campo_publico_para_injetar_promocao() -> None:
    """C2: nenhum caminho permite PROMOTED vindo da entrada governada."""
    campos = set(PredictiveGovernedQualityInput.__dataclass_fields__)
    assert "reconfiguration" not in campos
    assert not any("reconfig" in c.lower() or "promot" in c.lower() for c in campos)


def test_c47_upstream_e_causal_alinhados_com_sidecar_real() -> None:
    """C2: o desfecho E5.l vem do PredictiveCoordinatedBatchResult."""
    from app.predictive_accessibility import coordinator as mod_coordinator

    rejeicao = PredictiveCausalRejectionResult(
        claim=h.cer().claim,
        rejected_channels=(
            PredictiveAvailabilityOutcome(
                channel=PredictiveChannel(name="lag_1", lag=1),
                available=False,
                reason="sem defasagem",
            ),
        ),
        reason="nenhum canal disponível",
    )
    desfechos = (
        PredictiveUpstreamUnavailableOutcome(
            source=PredictiveUpstreamUnavailableInput(reference="u1", reason="fora")
        ),
        h.cer(),
        rejeicao,
    )
    coordenado = h.coordenado(desfechos, promovido=True)
    resultado = mod_coordinator.predictive_route_batch(
        coordenado, (None, h.governada(), None), at=h.AGORA
    )
    assert isinstance(resultado.outcomes[0], PredictiveUpstreamUnavailableRoutingResult)
    assert isinstance(resultado.outcomes[1], PredictiveFinalRoutingResult)
    assert isinstance(resultado.outcomes[2], PredictiveCausalRejectedRoutingResult)
    assert resultado.outcomes[1].route is PredictiveRoute.RECONFIGURE
