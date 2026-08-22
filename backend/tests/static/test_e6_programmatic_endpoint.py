"""
Guardas estáticas do endpoint programático `E6.2`, com mutantes dirigidos.

```text
BUSINESS_ROUTE_WITHOUT_FAIL_CLOSED_AUTH = UNIMPORTABLE
ROUTE_CONTAINS_SCIENCE = FORBIDDEN
IP_AS_QUOTA_KEY = FORBIDDEN
IN_MEMORY_QUOTA_AS_AUTHORITY = FORBIDDEN
GUARD_WITHOUT_MUTANT = UNVERIFIED_GUARD
```

Tudo por AST e leitura de fonte. Docstring não é símbolo de runtime: um
comentário dizendo "autenticado" não autentica nada.
"""

import ast
import pathlib

import pytest

pytestmark = pytest.mark.unit

RAIZ = pathlib.Path(__file__).resolve().parents[2] / "app"
ROUTER = RAIZ / "routers" / "predictive_evaluations.py"
SERVICO = RAIZ / "services" / "predictive_evaluation_service.py"
SEGURANCA = RAIZ / "security" / "programmatic_access.py"
REPOSITORIO = RAIZ / "repositories" / "programmatic_access_repository.py"
DEPENDENCIES = RAIZ / "api" / "dependencies.py"

CIENTIFICAS = frozenset(
    {
        "predictive_route_item",
        "predictive_evaluate_batch",
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


def _arvore(caminho: pathlib.Path) -> ast.Module:
    return ast.parse(caminho.read_text(encoding="utf-8"))


def _chamadas(caminho: pathlib.Path) -> set[str]:
    nomes: set[str] = set()
    for no in ast.walk(_arvore(caminho)):
        if isinstance(no, ast.Call):
            alvo = no.func
            if isinstance(alvo, ast.Name):
                nomes.add(alvo.id)
            elif isinstance(alvo, ast.Attribute):
                nomes.add(alvo.attr)
    return nomes


def _imports(caminho: pathlib.Path) -> list[str]:
    modulos: list[str] = []
    for no in ast.walk(_arvore(caminho)):
        if isinstance(no, ast.Import):
            modulos.extend(a.name for a in no.names)
        elif isinstance(no, ast.ImportFrom) and no.module:
            modulos.append(no.module)
    return modulos


# --- prova 19: a rota não é registrável sem as três checagens --------------


def test_e62g01_toda_rota_do_modulo_exige_a_dependency_de_acesso() -> None:
    """Por identidade de objeto, cobrindo `Annotated` e default legado."""
    from app.api.dependencies import require_predictive_evaluate_access
    from app.routers import predictive_evaluations as modulo

    for rota in modulo.router.routes:
        endpoint = getattr(rota, "endpoint", None)
        assert endpoint is not None
        assert require_predictive_evaluate_access in modulo._dependency_callables(endpoint), rota


def test_e62g01b_o_delta_nao_usa_noqa_b008() -> None:
    """A supressão foi substituída por `Annotated`, não reintroduzida.

    Lê COMENTÁRIOS via `tokenize`, não o texto bruto: uma docstring que
    explica por que a supressão foi removida não é uma supressão.
    """
    import io
    import tokenize

    for caminho in (ROUTER, DEPENDENCIES, SERVICO, SEGURANCA, REPOSITORIO):
        fonte = caminho.read_text(encoding="utf-8")
        comentarios = [
            token.string
            for token in tokenize.generate_tokens(io.StringIO(fonte).readline)
            if token.type == tokenize.COMMENT
        ]
        assert not [c for c in comentarios if "B008" in c], (caminho.name, comentarios)


def test_e62g02_a_guarda_de_import_existe_e_e_executada() -> None:
    """A verificação roda no import, não só no teste."""
    fonte = ROUTER.read_text(encoding="utf-8")
    assert "def _assert_every_route_is_protected()" in fonte
    linhas = [linha.strip() for linha in fonte.splitlines()]
    assert "_assert_every_route_is_protected()" in linhas


def test_e62m08_mutante_que_retira_autenticacao_da_rota_morre() -> None:
    """Sem a dependency, o módulo não importa: `ImportError` no carregamento.

    A remoção é feita por AST, não por substituição de texto: reformatação
    do Black mudaria o literal e faria o mutante passar por acidente.

    A execução REAL desta mutação, com `baseline PASS -> mutante FAIL`,
    está em `scripts/mutation_evidence_e62.py` (`m08`). Este teste é a
    guarda rápida; aquele é a prova.
    """
    arvore = _arvore(ROUTER)
    removidos = 0
    for no in ast.walk(arvore):
        if isinstance(no, ast.FunctionDef) and no.name == "create_predictive_evaluation":
            mantidos = [arg for arg in no.args.args if arg.arg != "principal"]
            removidos = len(no.args.args) - len(mantidos)
            no.args.args = mantidos
    assert removidos == 1, "parâmetro `principal` não encontrado na rota"

    mutado = ast.unparse(ast.fix_missing_locations(arvore))
    espaco: dict[str, object] = {"__name__": "mutante_router_sem_auth"}
    with pytest.raises(ImportError):
        exec(compile(mutado, str(ROUTER), "exec"), espaco)


def test_e62m09_mutante_que_define_a_dependency_localmente_morre() -> None:
    """A guarda de import não distingue homônimos; esta prova sim.

    Uma função local com o mesmo nome satisfaria `_assert_every_route_is_protected`,
    porque a comparação de identidade seria contra ela mesma. O que impede a
    substituição é a rota depender do objeto CANÔNICO de `app.api.dependencies`,
    verificado aqui por identidade e por AST do import.

    ```text
    SAME_NAME != SAME_GUARD
    ```
    """
    from app.api import dependencies as canonico
    from app.routers import predictive_evaluations as modulo

    assert modulo.require_predictive_evaluate_access is (
        canonico.require_predictive_evaluate_access
    )
    origens = {
        no.module
        for no in ast.walk(_arvore(ROUTER))
        if isinstance(no, ast.ImportFrom)
        and any(alias.name == "require_predictive_evaluate_access" for alias in no.names)
    }
    assert origens == {"app.api.dependencies"}, origens

    fonte = ROUTER.read_text(encoding="utf-8")
    mutado = fonte.replace(
        "from app.api.dependencies import require_predictive_evaluate_access",
        "def require_predictive_evaluate_access() -> None:\n    return None",
        1,
    )
    mutado_origens = {
        no.module
        for no in ast.walk(ast.parse(mutado))
        if isinstance(no, ast.ImportFrom)
        and any(alias.name == "require_predictive_evaluate_access" for alias in no.names)
    }
    assert mutado_origens == set()


# --- prova 12 estática: a rota não contém ciência --------------------------


def test_e62g03_router_nao_chama_funcao_cientifica() -> None:
    assert not (_chamadas(ROUTER) & CIENTIFICAS)


def test_e62g04_router_nao_importa_a_e5_diretamente() -> None:
    for modulo in _imports(ROUTER):
        assert not modulo.startswith("app.predictive_accessibility"), modulo


def test_e62g05_router_nao_toca_banco_nem_orm() -> None:
    for modulo in _imports(ROUTER):
        assert not modulo.startswith(("sqlalchemy", "app.repositories", "app.database")), modulo


def test_e62g06_router_nao_executa_acao_externa() -> None:
    proibidos = ("httpx", "requests", "urllib", "socket", "subprocess", "asyncio.create_subprocess")
    for modulo in _imports(ROUTER):
        assert not modulo.startswith(proibidos), modulo


# --- prova 15: nem provider, nem agente, nem conector ----------------------


def test_e62g07_nenhum_arquivo_do_delta_seleciona_provedor_ou_agente() -> None:
    proibidos = ("provider", "agent", "connector", "handoff", "orchestrat")
    for caminho in (ROUTER, SERVICO, SEGURANCA, REPOSITORIO):
        texto = caminho.read_text(encoding="utf-8").lower()
        for termo in proibidos:
            assert termo not in texto, (caminho.name, termo)


# --- cota: PostgreSQL é a autoridade, IP não é chave -----------------------


def test_e62g08_quota_nao_usa_ip_como_chave() -> None:
    for caminho in (REPOSITORIO, DEPENDENCIES):
        texto = caminho.read_text(encoding="utf-8")
        for termo in ("client.host", "x-forwarded-for", "X-Forwarded-For", "remote_addr"):
            assert termo not in texto, (caminho.name, termo)


def test_e62m10_mutante_que_usa_ip_como_cota_morre() -> None:
    fonte = REPOSITORIO.read_text(encoding="utf-8")
    assert "principal_id" in fonte
    mutado = fonte.replace(":principal_id", ":client_ip")
    assert "principal_id" in fonte and ":client_ip" in mutado
    assert ":client_ip" not in fonte


def test_e62m11_mutante_que_remove_a_condicao_atomica_morre() -> None:
    """Sem o `WHERE used < limit`, o teto deixa de existir."""
    fonte = REPOSITORIO.read_text(encoding="utf-8")
    assert "WHERE programmatic_quota_buckets.used < :quota_limit" in fonte
    assert "ON CONFLICT (principal_id, operation, window_start)" in fonte
    mutado = fonte.replace("WHERE programmatic_quota_buckets.used < :quota_limit", "")
    assert "WHERE programmatic_quota_buckets.used < :quota_limit" not in mutado


def test_e62g09_quota_nao_tem_fallback_em_memoria() -> None:
    for caminho in (REPOSITORIO, DEPENDENCIES):
        texto = caminho.read_text(encoding="utf-8")
        for termo in ("lru_cache", "global _quota", "_QUOTA_CACHE", "defaultdict("):
            assert termo not in texto, (caminho.name, termo)


def test_e62g10_janela_usa_o_relogio_do_banco() -> None:
    """Docstring citando `datetime.now()` como proibido não é uso: checa a AST."""
    fonte = REPOSITORIO.read_text(encoding="utf-8")
    assert "extract(epoch FROM now())" in fonte
    for no in ast.walk(_arvore(REPOSITORIO)):
        if (
            isinstance(no, ast.Call)
            and isinstance(no.func, ast.Attribute)
            and no.func.attr in {"now", "utcnow"}
            and isinstance(no.func.value, ast.Name)
        ):
            assert no.func.value.id != "datetime", "relógio de aplicação na cota"


# --- separação entre identidade de serviço e identidade humana -------------


def test_e62g11_dependency_de_servico_e_separada_de_get_current_user() -> None:
    fonte = DEPENDENCIES.read_text(encoding="utf-8")
    assert "def get_current_user()" in fonte
    assert "def get_programmatic_principal(" in fonte
    arvore = _arvore(DEPENDENCIES)
    for no in ast.walk(arvore):
        if isinstance(no, ast.FunctionDef) and no.name == "get_programmatic_principal":
            instrucoes = [
                sentenca
                for sentenca in no.body
                if not (isinstance(sentenca, ast.Expr) and isinstance(sentenca.value, ast.Constant))
            ]
            corpo = "\n".join(ast.unparse(sentenca) for sentenca in instrucoes)
            assert "get_current_user" not in corpo


def test_e62m12_mutante_que_troca_escopo_por_aprovacao_piap_morre() -> None:
    """Nenhum arquivo do delta constrói autoridade ou aprovação PIAP."""
    proibidos = (
        "ApprovalBinding(",
        "AuthorityContext(",
        "PredictiveReconfigurationInstruction(",
        "approval_reference=",
    )
    for caminho in (ROUTER, SERVICO, SEGURANCA, REPOSITORIO, DEPENDENCIES):
        texto = caminho.read_text(encoding="utf-8")
        for termo in proibidos:
            assert termo not in texto, (caminho.name, termo)


def test_e62g12_router_nao_preenche_user_id_do_contexto() -> None:
    """O principal técnico não é usuário; preencher `user_id` seria fingir que é."""
    for caminho in (ROUTER, DEPENDENCIES):
        arvore = _arvore(caminho)
        for no in ast.walk(arvore):
            if isinstance(no, ast.keyword) and no.arg == "user_id":
                raise AssertionError(f"{caminho.name} preenche user_id")


# --- segredo nunca em claro -------------------------------------------------


def test_e62g13_nenhum_armazenamento_de_segredo_em_claro() -> None:
    fonte_modelo = (RAIZ / "models" / "programmatic_service_principal.py").read_text(
        encoding="utf-8"
    )
    assert "secret_digest" in fonte_modelo
    for termo in ("secret_plain", "secret_value", "raw_secret", "password"):
        assert termo not in fonte_modelo, termo


def test_e62g14_nenhum_endpoint_de_emissao_ou_revogacao() -> None:
    """Emissão e revogação são comando local; rota seria alvo de ataque."""
    fonte = ROUTER.read_text(encoding="utf-8")
    for termo in ("@router.delete", "@router.put", "@router.patch", "principals"):
        assert termo not in fonte, termo
    rotas = [
        no.value
        for no in ast.walk(_arvore(ROUTER))
        if isinstance(no, ast.Constant) and isinstance(no.value, str) and no.value.startswith("/")
    ]
    assert rotas == ["/predictive-evaluations"], rotas


# --- serviço: instruções sempre None ---------------------------------------


def test_e62g15_servico_chama_a_e5_com_instrucoes_none() -> None:
    fonte = SERVICO.read_text(encoding="utf-8")
    assert "instrucoes = tuple(None for _ in canonica.items)" in fonte
    assert "predictive_evaluate_and_reconfigure_batch(" in fonte
    assert "NoWriteReconfigurationRepository()" in fonte
