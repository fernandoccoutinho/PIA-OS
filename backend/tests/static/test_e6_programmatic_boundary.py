"""Guarda estática da fronteira programática `E6.1`, com mutantes.

```text
PUBLIC_DTO_IMPORTS_E5_INTERNALS = FORBIDDEN
SERVER_MAPPER_CALLS_SCIENTIFIC_FUNCTION = FORBIDDEN
CLIENT_SUPPLIES_DERIVED_RESULT = FORBIDDEN
BUSINESS_ROUTE_WITHOUT_FAIL_CLOSED_AUTH = FORBIDDEN
GUARD_WITHOUT_MUTANT = UNVERIFIED_GUARD
```

Tudo por AST. Docstring não é símbolo de runtime.
"""

import ast
import pathlib

import pytest

pytestmark = pytest.mark.unit

RAIZ = pathlib.Path(__file__).resolve().parents[2] / "app"
SCHEMA = RAIZ / "schemas" / "predictive_evaluation.py"
MAPPER = RAIZ / "services" / "predictive_evaluation_mapping.py"

CIENTIFICAS = frozenset(
    {
        "predictive_route_batch",
        "predictive_route_item",
        "predictive_evaluate_batch",
        "predictive_evaluate_and_reconfigure_batch",
        "predictive_final_routing",
        "predictive_conflict_assessment",
        "predictive_conflict_for_batch",
        "predictive_assertiveness",
        "predictive_protection_set",
        "predictive_recommendation_quality",
        "predictive_counterfactual_set",
        "predictive_burden_comparison",
        "predictive_power_outcome_for",
        "predictive_classify_epistemic_state",
    }
)

DERIVADOS_PROIBIDOS = frozenset(
    {
        "promotion",
        "reconfiguration",
        "route",
        "approval_outcome",
        "approval_validation_outcome",
        "recommended_alternative",
        "sidecar",
        "event_id",
        "resulting_version",
    }
)


def _arvore(caminho: pathlib.Path) -> ast.Module:
    return ast.parse(caminho.read_text(encoding="utf-8"))


def _imports(caminho: pathlib.Path) -> list[str]:
    modulos: list[str] = []
    for no in ast.walk(_arvore(caminho)):
        if isinstance(no, ast.Import):
            modulos.extend(a.name for a in no.names)
        elif isinstance(no, ast.ImportFrom) and no.module:
            modulos.append(no.module)
    return modulos


def _chamados(caminho: pathlib.Path) -> set[str]:
    return {
        no.func.id if isinstance(no.func, ast.Name) else no.func.attr
        for no in ast.walk(_arvore(caminho))
        if isinstance(no, ast.Call) and isinstance(no.func, ast.Name | ast.Attribute)
    }


def _classes_de_requisicao(caminho: pathlib.Path) -> list[ast.ClassDef]:
    return [
        no
        for no in _arvore(caminho).body
        if isinstance(no, ast.ClassDef) and no.name.startswith("Public")
    ]


# --- contrato --------------------------------------------------------------


def test_e6b01_schema_publico_nao_importa_a_e5() -> None:
    for modulo in _imports(SCHEMA):
        assert not modulo.startswith("app.predictive_accessibility"), modulo


def test_e6b02_mapeador_nao_chama_funcao_cientifica() -> None:
    assert not (_chamados(MAPPER) & CIENTIFICAS)


def test_e6b03_mapeador_usa_o_desserializador_canonico() -> None:
    assert "deserialize_piap_envelope" in _chamados(MAPPER)


def test_e6b04_nenhum_campo_derivado_no_contrato_de_entrada() -> None:
    entrada = {
        "PublicReadyItem",
        "PublicUpstreamUnavailableItem",
        "PublicEvaluationRequest",
        "PublicEvaluationContext",
        "PublicGovernedQualityInput",
    }
    for classe in _classes_de_requisicao(SCHEMA):
        if classe.name not in entrada:
            continue
        campos = {
            f.target.id
            for f in classe.body
            if isinstance(f, ast.AnnAssign) and isinstance(f.target, ast.Name)
        }
        assert not (campos & DERIVADOS_PROIBIDOS), (classe.name, campos & DERIVADOS_PROIBIDOS)


def test_e6b05_modelos_de_requisicao_usam_extra_forbid() -> None:
    texto = SCHEMA.read_text(encoding="utf-8")
    assert 'extra="forbid"' in texto
    assert 'extra="allow"' not in texto
    assert 'extra="ignore"' not in texto


def test_e6b06_e61_nao_registra_rota_nem_autenticacao() -> None:
    """`E6.1` entrega contrato e mapeador. Rota e auth nascem juntas na `E6.2`."""
    for caminho in (SCHEMA, MAPPER):
        texto = caminho.read_text(encoding="utf-8")
        for proibido in ("APIRouter", "@router", "@app.", "Depends(", "OAuth2", "HTTPBearer"):
            assert proibido not in texto, (caminho.name, proibido)


def test_e6b07_mapeador_nao_toca_banco_orm_nem_framework_web() -> None:
    proibidos = ("sqlalchemy", "alembic", "psycopg", "app.repositories", "app.database", "fastapi")
    for modulo in _imports(MAPPER):
        assert not modulo.startswith(proibidos), modulo


def test_e6b08_schema_publico_nao_reproduz_tetos_do_servidor() -> None:
    texto = SCHEMA.read_text(encoding="utf-8")
    for constante in (
        "MAX_CLAIMS_PER_EVALUATION",
        "MAX_TOTAL_REFERENCES_PER_EVALUATION",
        "MAX_PIAP_INPUT_BYTES",
        "262144",
    ):
        assert constante not in texto, constante


# --- mutantes do instrumento ----------------------------------------------
#
#     GUARD_WITHOUT_MUTANT = UNVERIFIED_GUARD


def _detecta_import_e5(fonte: str) -> bool:
    modulos: list[str] = []
    for no in ast.walk(ast.parse(fonte)):
        if isinstance(no, ast.Import):
            modulos.extend(a.name for a in no.names)
        elif isinstance(no, ast.ImportFrom) and no.module:
            modulos.append(no.module)
    return any(m.startswith("app.predictive_accessibility") for m in modulos)


def test_e6b99_mutante_import_de_dataclass_interna_no_schema_morre() -> None:
    limpo = SCHEMA.read_text(encoding="utf-8")
    mutado = "from app.predictive_accessibility.batch import PredictiveEvaluationContext\n" + limpo
    assert not _detecta_import_e5(limpo)
    assert _detecta_import_e5(mutado)


def _detecta_chamada_cientifica(fonte: str) -> bool:
    chamados = {
        no.func.id if isinstance(no.func, ast.Name) else no.func.attr
        for no in ast.walk(ast.parse(fonte))
        if isinstance(no, ast.Call) and isinstance(no.func, ast.Name | ast.Attribute)
    }
    return bool(chamados & CIENTIFICAS)


def test_e6b99_mutante_chamada_cientifica_no_mapeador_morre() -> None:
    limpo = MAPPER.read_text(encoding="utf-8")
    mutado = limpo + "\n\ndef _mut(r):\n    return predictive_route_batch(r)\n"
    assert not _detecta_chamada_cientifica(limpo)
    assert _detecta_chamada_cientifica(mutado)


def _campos_derivados(fonte: str, classe: str) -> set[str]:
    for no in ast.parse(fonte).body:
        if isinstance(no, ast.ClassDef) and no.name == classe:
            campos = {
                f.target.id
                for f in no.body
                if isinstance(f, ast.AnnAssign) and isinstance(f.target, ast.Name)
            }
            return campos & DERIVADOS_PROIBIDOS
    raise AssertionError(f"{classe} não encontrada")


def test_e6b99_mutante_que_aceita_promotion_route_ou_approval_morre() -> None:
    limpo = SCHEMA.read_text(encoding="utf-8")
    assert _campos_derivados(limpo, "PublicReadyItem") == set()
    mutado = limpo.replace(
        '    kind: Literal["ready"]\n',
        '    kind: Literal["ready"]\n    promotion: bool = False\n'
        "    route: str | None = None\n    approval_outcome: str | None = None\n",
        1,
    )
    assert _campos_derivados(mutado, "PublicReadyItem") == {
        "promotion",
        "route",
        "approval_outcome",
    }


def test_e6b99_mutante_que_descarta_item_na_resposta_morre() -> None:
    """O mapeador exige cardinalidade igual; descartar um item reprova."""
    from app.services import predictive_evaluation_mapping as mapper

    with pytest.raises(mapper.PublicContractMappingError):
        mapper.to_public_response((object(), object()), (object(),))


def test_e6b99_mutante_de_extra_permissivo_morre() -> None:
    limpo = SCHEMA.read_text(encoding="utf-8")
    mutado = limpo.replace('extra="forbid"', 'extra="allow"')
    assert 'extra="allow"' not in limpo
    assert 'extra="allow"' in mutado


def test_e6b99_mutante_de_transporte_nao_reversivel_morre() -> None:
    from app.services import predictive_evaluation_mapping as mapper

    assert mapper.decode_canonical_piap_transport("QUJD") == b"ABC"
    with pytest.raises(mapper.PublicContractMappingError):
        mapper.decode_canonical_piap_transport("QUJD\n")


# --- mutantes das correções C1 e C2 ---------------------------------------


def test_e6b99_mutante_que_devolve_tupla_crua_sem_request_morre() -> None:
    """C1: sem `PredictiveEvaluationRequest`, os tetos 8/512 não incidem."""
    fonte = MAPPER.read_text(encoding="utf-8")
    assert "PredictiveEvaluationRequest(items=tuple(itens))" in fonte
    mutado = fonte.replace(
        "canonica = PredictiveEvaluationRequest(items=tuple(itens))",
        "canonica = tuple(itens)",
    )
    assert "PredictiveEvaluationRequest(items=tuple(itens))" not in mutado


def test_e6b99_mutante_que_apaga_componente_cientifico_morre() -> None:
    """C2: os oito componentes congelados são verificados por manifesto."""
    from app.schemas import predictive_evaluation as schema

    campos = set(schema.PublicClaimEvaluationView.model_fields) - {"kind"}
    assert len(campos) == 8
    for componente in campos:
        assert campos - {componente} != campos


def test_e6b99_mutante_que_apaga_componente_de_roteamento_morre() -> None:
    from app.schemas import predictive_evaluation as schema

    campos = set(schema.PublicFinalRoutingView.model_fields) - {"kind"}
    assert {"assertiveness", "conflict_assessment", "quality", "revalidated_route"} <= campos


def test_e6b99_mutante_que_apaga_dimensoes_decompostas_morre() -> None:
    from app.schemas import predictive_evaluation as schema

    assert "decomposed_conflict_dimensions" in schema.PublicEvaluationResponse.model_fields


def test_e6b99_mutante_que_aceita_tupla_solta_na_resposta_morre() -> None:
    """C2: `to_public_response` exige os batch results tipados."""
    from app.services import predictive_evaluation_mapping as mapper

    with pytest.raises(mapper.PublicContractMappingError):
        mapper.to_public_response((), ())
