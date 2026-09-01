"""Guarda R10 **ligada ao runtime**: as arestas do grafo existem no código.

```text
DOCUMENTED_EDGE_WITHOUT_RUNTIME_EDGE = NOT_AN_EDGE
E5.m -> E5.n -> E5.o -> E5.p -> E5.q -> E5.r -> E5.s
E5_L_TYPED_OUTCOME vem do PredictiveCoordinatedBatchResult, nunca do chamador
```

Tudo por AST sobre a produção. Docstring não é símbolo de runtime.
"""

import ast
import pathlib

import pytest

pytestmark = pytest.mark.unit

RAIZ = pathlib.Path(__file__).resolve().parents[2] / "app" / "predictive_accessibility"


def _arvore(nome: str) -> ast.Module:
    return ast.parse((RAIZ / nome).read_text(encoding="utf-8"))


def _funcao(arquivo: str, funcao: str) -> ast.FunctionDef:
    for no in ast.walk(_arvore(arquivo)):
        if isinstance(no, ast.FunctionDef) and no.name == funcao:
            return no
    raise AssertionError(f"{funcao} não existe em {arquivo}")


def _chamadas(no: ast.AST) -> list[str]:
    saida: list[str] = []
    for filho in ast.walk(no):
        if isinstance(filho, ast.Call):
            alvo = filho.func
            if isinstance(alvo, ast.Attribute):
                saida.append(alvo.attr)
            elif isinstance(alvo, ast.Name):
                saida.append(alvo.id)
    return saida


def test_rt01_e5m_roda_no_lote_antes_de_e5n() -> None:
    """`E5.m` em produção, e antes da assertividade."""
    lote = _funcao("coordinator.py", "predictive_route_batch")
    chamadas_lote = _chamadas(lote)
    assert "predictive_conflict_for_batch" in chamadas_lote
    assert chamadas_lote.index("predictive_conflict_for_batch") < chamadas_lote.index(
        "predictive_route_item"
    )
    conflito = _funcao("coordinator.py", "predictive_conflict_for_batch")
    assert "predictive_conflict_assessment" in _chamadas(conflito)


ORDEM_CAUSAL = (
    "predictive_assertiveness",
    "predictive_protection_set",
    "predictive_recommendation_quality",
    "predictive_counterfactual_set",
    "predictive_burden_comparison",
    "predictive_final_routing",
)


def test_rt02_ordem_causal_n_o_p_q_r_s_no_coordenador() -> None:
    chamadas = _chamadas(_funcao("coordinator.py", "predictive_route_item"))
    posicoes = [chamadas.index(nome) for nome in ORDEM_CAUSAL]
    assert posicoes == sorted(posicoes), list(zip(ORDEM_CAUSAL, posicoes, strict=True))


def test_rt03_conflito_chega_a_e5n_e_a_e5o() -> None:
    """Não basta calcular o conflito: ele tem de ser passado adiante."""
    fonte = ast.unparse(_funcao("coordinator.py", "predictive_route_item"))
    for chamada in ("predictive_assertiveness", "predictive_protection_set"):
        trecho = fonte.split(chamada, 1)[1].split(")", 1)[0]
        assert "conflict_assessment=conflict_assessment" in trecho, chamada
    assinatura_n = {
        a.arg for a in _funcao("assertiveness.py", "predictive_assertiveness").args.kwonlyargs
    }
    assinatura_o = {
        a.arg for a in _funcao("protection.py", "predictive_protection_set").args.kwonlyargs
    }
    assert "conflict_assessment" in assinatura_n
    assert "conflict_assessment" in assinatura_o


def test_rt04_e5l_vem_exclusivamente_do_coordinated_batch_result() -> None:
    lote = _funcao("coordinator.py", "predictive_route_batch")
    fonte = ast.unparse(lote)
    assert "coordinated.reconfiguration" in fonte
    assert "strict=True" in fonte
    argumentos = lote.args
    nomes = {a.arg for a in (*argumentos.args, *argumentos.kwonlyargs)}
    assert "coordinated" in nomes


def test_rt05_entrada_governada_nao_tem_campo_de_reconfiguracao() -> None:
    for no in ast.walk(_arvore("batch.py")):
        if isinstance(no, ast.ClassDef) and no.name == "PredictiveGovernedQualityInput":
            campos = {
                f.target.id
                for f in no.body
                if isinstance(f, ast.AnnAssign) and isinstance(f.target, ast.Name)
            }
            assert not any("reconfig" in c.lower() or "promot" in c.lower() for c in campos), campos
            return
    raise AssertionError("PredictiveGovernedQualityInput não encontrada")


def test_rt06_materialidade_nao_tem_campo_valid() -> None:
    for no in ast.walk(_arvore("protection.py")):
        if isinstance(no, ast.ClassDef) and no.name == "PredictiveMaterialityAuthority":
            campos = {
                f.target.id
                for f in no.body
                if isinstance(f, ast.AnnAssign) and isinstance(f.target, ast.Name)
            }
            assert "valid" not in campos, campos
            assert {"jurisdiction", "version", "scope", "valid_from", "valid_until"} <= campos
            return
    raise AssertionError("PredictiveMaterialityAuthority não encontrada")


def test_rt07_orientacao_invalida_zera_a_alternativa_recomendada() -> None:
    escolher = _funcao("routing.py", "_escolher_alternativa")
    corpo = ast.unparse(escolher)
    assert "procedural_endorsement_allowed" in corpo
    indice = corpo.index("procedural_endorsement_allowed")
    assert "return None" in corpo[indice : indice + 400]


def test_rt08_recomendacao_apenas_quando_unica_nao_dominada() -> None:
    corpo = ast.unparse(_funcao("routing.py", "_escolher_alternativa"))
    assert "non_dominated" in corpo
    assert "len(candidatas) > 1" in corpo


@pytest.mark.parametrize(
    ("objeto", "produtor"),
    [
        (
            "PredictiveRecommendationQualityResult",
            ("guidance.py", "predictive_recommendation_quality"),
        ),
        ("PredictiveFinalRoutingResult", ("routing.py", "predictive_final_routing")),
    ],
)
def test_rt09_produtor_unico_no_codigo(objeto, produtor) -> None:
    produtores: list[tuple[str, str]] = []
    for caminho in sorted(RAIZ.rglob("*.py")):
        if "__pycache__" in caminho.parts:
            continue
        for no in ast.parse(caminho.read_text(encoding="utf-8")).body:
            if isinstance(no, ast.FunctionDef) and objeto in _chamadas(no):
                produtores.append((caminho.name, no.name))
    assert produtores == [produtor], produtores


ENTRADAS_OBRIGATORIAS = {
    ("assertiveness.py", "predictive_assertiveness"): (
        "candidate_conclusion",
        "decisive_constraint",
        "conflict_assessment",
    ),
    ("protection.py", "predictive_protection_set"): (
        "assertiveness",
        "evaluation",
        "approval_binding",
        "conflict_assessment",
        "at",
        "required_identifiers",
        "inventory_reference",
    ),
    ("guidance.py", "predictive_recommendation_quality"): (
        "protection",
        "guidance",
        "at",
        "expected_jurisdiction",
        "expected_version",
    ),
    ("counterfactual.py", "predictive_counterfactual_set"): (
        "assertiveness",
        "protection",
        "quality",
    ),
    ("burden.py", "predictive_burden_comparison"): ("counterfactual", "entries"),
    ("routing.py", "predictive_final_routing"): (
        "evaluation",
        "reconfiguration",
        "assertiveness",
        "quality",
        "counterfactual",
        "burden",
        "conflict_assessment",
    ),
}


@pytest.mark.parametrize(("alvo", "obrigatorias"), list(ENTRADAS_OBRIGATORIAS.items()))
def test_rt10_entradas_obrigatorias_declaradas_e_usadas(alvo, obrigatorias) -> None:
    """Aceitar parâmetro e ignorá-lo não conta como aresta."""
    funcao = _funcao(*alvo)
    a = funcao.args
    nomes = {x.arg for x in (*a.posonlyargs, *a.args, *a.kwonlyargs)}
    assert set(obrigatorias) <= nomes, set(obrigatorias) - nomes
    usados = {n.id for n in ast.walk(funcao) if isinstance(n, ast.Name)}
    for parametro in obrigatorias:
        assert parametro in usados, f"{alvo}: {parametro} declarado e não usado"


def test_rt11_vetores_de_onus_sao_imutaveis() -> None:
    for no in ast.walk(_arvore("burden.py")):
        if isinstance(no, ast.ClassDef) and no.name == "PredictiveBurdenComparison":
            for campo in no.body:
                if isinstance(campo, ast.AnnAssign) and isinstance(campo.target, ast.Name):
                    anotacao = ast.unparse(campo.annotation)
                    assert not anotacao.startswith("dict"), (campo.target.id, anotacao)
            return
    raise AssertionError("PredictiveBurdenComparison não encontrada")


def test_rt12_upstream_e_causal_chegam_ao_roteamento() -> None:
    fonte = ast.unparse(_funcao("coordinator.py", "predictive_route_item"))
    assert "PredictiveUpstreamUnavailableRoutingResult" in fonte
    assert "PredictiveCausalRejectedRoutingResult" in fonte


def test_rt13_aprovacao_piap_real_chega_ao_gate_de_materialidade() -> None:
    produtor = ast.unparse(_funcao("coordinator.py", "predictive_evaluate_and_reconfigure_batch"))
    roteador = ast.unparse(_funcao("coordinator.py", "predictive_route_batch"))
    item = ast.unparse(_funcao("coordinator.py", "predictive_route_item"))
    validador = ast.unparse(_funcao("protection.py", "predictive_materiality_authority_failure"))
    assert "item.envelope.authority.approval" in produtor
    assert "coordinated.approval_bindings" in roteador
    assert "approval_binding=approval_binding" in item
    for campo in (
        "approval_reference",
        "approval_version",
        "approval_scope",
        "approval_jurisdiction",
        "approval_expiry",
    ):
        assert campo in validador


def test_rt14_conflito_e_alinhado_por_item_e_nao_global() -> None:
    conflito = ast.unparse(_funcao("coordinator.py", "predictive_conflict_for_batch"))
    roteador = ast.unparse(_funcao("coordinator.py", "predictive_route_batch"))
    assert "grupos.setdefault" in conflito
    assert "per_item" in conflito
    assert "conflitos.per_item" in roteador
    assert "decomposed_conflict_dimensions" in roteador


def test_rt15_conclusao_real_chega_a_assertividade() -> None:
    item = ast.unparse(_funcao("coordinator.py", "predictive_route_item"))
    assert "candidate_conclusion=governed.conclusion_signature" in item


def test_rt16_incompletude_bloqueia_alternativa() -> None:
    escolha = ast.unparse(_funcao("routing.py", "_escolher_alternativa"))
    indice = escolha.index("complete_answer_allowed")
    assert "return None" in escolha[indice : indice + 250]
