"""
Guardas estáticas da E7.2 — fronteira, escopo, proveniência, dependências.

```text
API_GUARD != DOMAIN_GUARANTEE
GUARD_WITHOUT_MUTANT = UNVERIFIED_GUARD
PARTIAL_ENUMERATION = GUARD_WITH_A_HOLE
```

Complementa `test_e7_orchestration_boundary.py`, que segue medindo o
núcleo da E7.1. Aqui ficam as guardas do que a E7.2 acrescentou: rotas,
escopo próprio, ausência de escrita cognitiva e de dependência nova.
"""

import ast
import pathlib

import pytest

pytestmark = pytest.mark.unit

BACKEND = pathlib.Path(__file__).resolve().parents[2]
APP = BACKEND / "app"
ORQUESTRACAO = APP / "orchestration"
ROUTER = APP / "routers" / "orchestration.py"
DTO = APP / "schemas" / "orchestration_public.py"
DEPENDENCIES = APP / "api" / "dependencies.py"
BASE_REQUIREMENTS = BACKEND / "requirements" / "base.txt"

ROTAS_ESPERADAS = {
    # E7.2
    ("POST", "/schedules"),
    ("GET", "/schedules/{schedule_id}"),
    ("POST", "/schedules/{schedule_id}/steps/{step_id}/handoff-export"),
    ("POST", "/schedules/{schedule_id}/steps/{step_id}/handoff-import"),
    ("GET", "/schedules/{schedule_id}/attempts"),
    # E7.3, autorizadas pelo addendum R1 §8
    ("POST", "/schedules/{schedule_id}/steps/{step_id}/delegations"),
    ("POST", "/schedules/{schedule_id}/steps/{step_id}/delegations/{delegation_id}/revoke"),
    ("POST", "/schedules/{schedule_id}/control-events"),
    ("POST", "/schedules/{schedule_id}/attempts/{attempt_id}/audit-opinions"),
    ("GET", "/schedules/{schedule_id}/governance"),
}
"""ATUALIZADO PELA E7.3: cinco capacidades técnicas foram autorizadas.

O conjunto continua **exato** — rota nova sem entrar aqui reprova — e é
isso que a guarda protege, não a imobilidade da superfície.
"""

#: Nunca escritos, nunca importados pela E7.
SIMBOLOS_COGNITIVOS = frozenset(
    {
        "ProvenanceManager",
        "ProvenanceRecord",
        "provenance_records",
        "CognitiveObject",
        "cognitive_objects",
        "ApprovalRecord",
        "approval_records",
    }
)

#: Campos que a superfície pública NUNCA aceita na entrada.
CAMPOS_PROIBIDOS_NA_ENTRADA = frozenset(
    {
        "control_principal_ref",
        "sealer_ref",
        "technical_principal_ref",
        "provenance_record_ref",
        "self_declared",
        "declared_at",
        "role",
        "credential",
        "secret",
        "token",
        "authority",
        "approval",
        "state",
        "status",
    }
)

DEPENDENCIAS_PROIBIDAS = frozenset(
    {"httpx", "requests", "aiohttp", "celery", "rq", "arq", "kafka", "redis", "apscheduler"}
)

#: Conteúdo bruto: nome de coluna ou campo que sugira transcrição.
NOMES_DE_CONTEUDO = frozenset(
    {"content", "body", "raw_output", "response", "transcript", "prompt", "output_text"}
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
            modulos.extend(f"{no.module}.{a.name}" for a in no.names)
    return modulos


def _nomes(caminho: pathlib.Path) -> set[str]:
    encontrados: set[str] = set()
    for no in ast.walk(_arvore(caminho)):
        if isinstance(no, ast.Name):
            encontrados.add(no.id)
        elif isinstance(no, ast.Attribute):
            encontrados.add(no.attr)
        elif isinstance(no, ast.alias):
            encontrados.add(no.name.split(".")[-1])
    return encontrados


def _arquivos_e7() -> list[pathlib.Path]:
    return sorted(ORQUESTRACAO.rglob("*.py")) + [ROUTER, DTO]


# --- rotas e proteção -------------------------------------------------------


def test_e72b01_as_cinco_rotas_existem_com_metodo_e_caminho_exatos() -> None:
    from app.routers import orchestration

    encontradas = {
        (metodo, rota.path)
        for rota in orchestration.router.routes
        for metodo in getattr(rota, "methods", set())
        if metodo != "HEAD"
    }
    assert encontradas == ROTAS_ESPERADAS


def test_e72b02_toda_rota_depende_do_escopo_e7_por_identidade_de_objeto() -> None:
    """Identidade, não nome: um homônimo importado de outro módulo passaria
    por comparação textual e não passa por esta."""
    import inspect

    from app.api.dependencies import require_orchestration_operate_access
    from app.routers import orchestration

    for rota in orchestration.router.routes:
        chamadas = set()
        for parametro in inspect.signature(rota.endpoint).parameters.values():
            for meta in getattr(parametro.annotation, "__metadata__", ()):
                alvo = getattr(meta, "dependency", None)
                if alvo is not None:
                    chamadas.add(alvo)
        assert require_orchestration_operate_access in chamadas, rota.path


def test_e72b03_remover_a_dependency_torna_o_modulo_nao_importavel() -> None:
    """A guarda roda no IMPORT. Sem isso, a versão insegura existiria e rodaria."""
    fonte = ROUTER.read_text(encoding="utf-8")
    assert "_assert_every_route_is_protected()" in fonte
    assert fonte.rstrip().endswith("_assert_every_route_is_protected()")
    assert "raise ImportError" in fonte


def test_e72b04_nenhuma_rota_e7_usa_a_dependency_preditiva() -> None:
    assert "require_predictive_evaluate_access" not in _nomes(ROUTER)
    assert "SCOPE_PREDICTIVE_EVALUATE" not in _nomes(ROUTER)


def test_e72b05_o_escopo_e_a_cota_da_e7_sao_proprios() -> None:
    fonte = DEPENDENCIES.read_text(encoding="utf-8")
    assert "SCOPE_ORCHESTRATION_OPERATE" in fonte
    assert "OPERATION_ORCHESTRATION_API" in fonte
    alvo = None
    for no in ast.walk(_arvore(DEPENDENCIES)):
        if isinstance(no, ast.FunctionDef) and no.name == "require_orchestration_operate_access":
            alvo = no
    assert alvo is not None, "dependency da E7 não encontrada"
    # Medido sobre IDENTIFICADORES, não sobre o texto: a docstring explica
    # a diferença entre os dois escopos e citaria "PREDICTIVE" sem que uma
    # única linha de código o usasse.
    identificadores = {no.id for no in ast.walk(alvo) if isinstance(no, ast.Name)} | {
        no.attr for no in ast.walk(alvo) if isinstance(no, ast.Attribute)
    }
    assert "SCOPE_ORCHESTRATION_OPERATE" in identificadores
    assert "OPERATION_ORCHESTRATION_API" in identificadores
    assert not {i for i in identificadores if "PREDICTIVE" in i}, sorted(identificadores)


# --- identidade derivada, nunca aceita --------------------------------------


def test_e72b06_o_router_deriva_o_principal_e_nunca_o_le_do_cliente() -> None:
    fonte = ROUTER.read_text(encoding="utf-8")
    assert "str(principal.id)" in fonte
    for campo in ("payload.control_principal_ref", "payload.sealer_ref", "payload.role"):
        assert campo not in fonte, campo


def test_e72b07_nenhum_dto_de_entrada_aceita_campo_derivavel_ou_sensivel() -> None:
    """Entrada é o que o cliente pode mentir; o servidor deriva o resto."""
    arvore = _arvore(DTO)
    classes = {no.name: no for no in arvore.body if isinstance(no, ast.ClassDef)}
    entradas = [n for n in classes if n.endswith(("Request", "Input"))]
    assert entradas, "nenhum DTO de entrada encontrado"
    for nome in entradas:
        campos = {
            alvo.target.id
            for alvo in classes[nome].body
            if isinstance(alvo, ast.AnnAssign) and isinstance(alvo.target, ast.Name)
        }
        proibidos = set(CAMPOS_PROIBIDOS_NA_ENTRADA)
        if nome == "StepInput":
            # `role` na COMPOSIÇÃO é declaração legítima do cliente: ele
            # define os papéis do trabalho. O `role` proibido é o da
            # ATRIBUIÇÃO do retorno, que precisa ser derivado da etapa —
            # aceitá-lo ali deixaria a atribuição contar história
            # diferente da composição.
            proibidos.discard("role")
        # `content` e `media_type` são legítimos na entrada de importação:
        # o conteúdo precisa chegar para ser medido, e sai transitório.
        encontrados = campos & proibidos
        assert not encontrados, f"{nome} aceita campo proibido: {sorted(encontrados)}"
    atribuicao = {
        alvo.target.id
        for alvo in classes["ReturnAttributionInput"].body
        if isinstance(alvo, ast.AnnAssign) and isinstance(alvo.target, ast.Name)
    }
    assert not (atribuicao & {"role", "self_declared", "declared_at", "provenance_record_ref"})


def test_e72b08_os_dtos_de_entrada_recusam_campo_desconhecido() -> None:
    from app.schemas import orchestration_public as dto

    for classe in (dto.CreateScheduleRequest, dto.ExportHandoffRequest, dto.ImportReturnRequest):
        assert classe.model_config.get("extra") == "forbid", classe.__name__
        assert classe.model_config.get("frozen") is True, classe.__name__


def test_e72b09_nenhuma_resposta_publica_expoe_conteudo_ou_dono() -> None:
    arvore = _arvore(DTO)
    classes = {no.name: no for no in arvore.body if isinstance(no, ast.ClassDef)}
    saidas = [n for n in classes if n.endswith(("View", "Response")) and not n.endswith("Request")]
    for nome in saidas:
        campos = {
            alvo.target.id
            for alvo in classes[nome].body
            if isinstance(alvo, ast.AnnAssign) and isinstance(alvo.target, ast.Name)
        }
        assert "control_principal_ref" not in campos, nome
        vazamento = {c for c in campos if c in NOMES_DE_CONTEUDO}
        assert not vazamento, f"{nome} expõe conteúdo bruto: {sorted(vazamento)}"


# --- proveniência e cognição ------------------------------------------------


def test_e72b10_nenhum_arquivo_da_e7_importa_ou_escreve_cognicao() -> None:
    """Busca exaustiva por AST em toda a superfície da E7.

    ```text
    PROVENANCE_RECORD_WRITE = FORBIDDEN
    COGNITIVE_OBJECT_MATERIALIZATION = FORBIDDEN
    APPROVAL_RECORD_USE = FORBIDDEN
    ```
    """
    for caminho in _arquivos_e7():
        nomes = _nomes(caminho)
        # `provenance_record_ref` é coluna legítima; o SÍMBOLO proibido é
        # a tabela e o gerenciador, nunca a referência opaca.
        encontrados = nomes & SIMBOLOS_COGNITIVOS
        assert not encontrados, f"{caminho.name}: {sorted(encontrados)}"
        for modulo in _imports(caminho):
            assert not modulo.startswith(
                ("app.cognitive", "app.memory", "app.predictive_accessibility")
            ), f"{caminho.name} importa {modulo}"


def test_e72b11_nenhum_caminho_da_e7_preenche_provenance_record_ref() -> None:
    """`E7_2_NON_NULL_WRITER = NONE`, medido no código e não afirmado."""
    escritores = {"HandoffAttribution", "create_handoff_attribution"}
    for caminho in _arquivos_e7():
        for no in ast.walk(_arvore(caminho)):
            if not isinstance(no, ast.Call):
                continue
            alvo = no.func.id if isinstance(no.func, ast.Name) else getattr(no.func, "attr", "")
            if alvo not in escritores:
                continue
            # Só ESCRITA conta. Ler a coluna para devolvê-la numa view é
            # legítimo — e é o que a E7.2 faz, sempre devolvendo `None`.
            for argumento in no.keywords:
                assert (
                    argumento.arg != "provenance_record_ref"
                ), f"{caminho.name}: {alvo}() escreve provenance_record_ref"


def test_e72b12_o_repositorio_nao_expoe_provenance_record_ref_como_parametro() -> None:
    repositorio = ORQUESTRACAO / "repositories" / "orchestration_repository.py"
    for no in ast.walk(_arvore(repositorio)):
        if isinstance(no, ast.FunctionDef):
            argumentos = {a.arg for a in no.args.kwonlyargs} | {a.arg for a in no.args.args}
            assert "provenance_record_ref" not in argumentos, no.name


# --- dependências, rede e escopo negativo -----------------------------------


def test_e72b13_requirements_base_nao_ganhou_dependencia() -> None:
    conteudo = BASE_REQUIREMENTS.read_text(encoding="utf-8").lower()
    for pacote in DEPENDENCIAS_PROIBIDAS:
        assert pacote not in conteudo, pacote
    assert len([linha for linha in conteudo.splitlines() if linha.strip()]) == 11


def test_e72b14_nenhum_arquivo_da_e7_importa_rede_fila_ou_worker() -> None:
    for caminho in _arquivos_e7():
        for modulo in _imports(caminho):
            raiz = modulo.split(".")[0]
            assert raiz not in DEPENDENCIAS_PROIBIDAS, f"{caminho.name}: {modulo}"
            assert raiz not in {
                "socket",
                "urllib",
                "http",
                "subprocess",
                "asyncio",
            }, f"{caminho.name}: {modulo}"


def test_e72b15_o_adaptador_manual_nao_tem_efeito_externo() -> None:
    manual = ORQUESTRACAO / "adapters" / "manual_transport.py"
    proibidos = {"open", "Popen", "run", "connect", "socket", "get", "post", "request"}
    chamados = {
        no.func.id if isinstance(no.func, ast.Name) else no.func.attr
        for no in ast.walk(_arvore(manual))
        if isinstance(no, ast.Call) and isinstance(no.func, ast.Name | ast.Attribute)
    }
    assert not (chamados & proibidos), sorted(chamados & proibidos)


def test_e72b16_o_adaptador_deterministico_nao_entra_no_router_de_producao() -> None:
    assert "deterministic_test_transport" not in ROUTER.read_text(encoding="utf-8")
    assert "DeterministicTestTransport" not in _nomes(ROUTER)


def test_e72b17_a_e7_2_nao_antecipa_a_e7_3() -> None:
    # ATUALIZADO PELA E7.3: delegação, porta de gate, parecer e auditoria
    # deixaram de ser antecipação e viraram entrega autorizada. O que
    # permanece proibido é o que AINDA não foi autorizado.
    proibidos = {
        "StopConditionRuntime",
        "auto_advance",
        "advance_to_next_step",
        "HardCancelService",
        "TimeoutWorker",
        "BudgetEnforcer",
        "GovernedSynthesis",
    }
    for caminho in _arquivos_e7():
        assert not (_nomes(caminho) & proibidos), caminho.name


def test_e72b18_nenhum_modelo_da_e7_tem_coluna_de_conteudo_bruto() -> None:
    for nome in ("handoff_result.py", "handoff_attribution.py"):
        modelo = ORQUESTRACAO / "models" / nome
        colunas = {
            alvo.target.id
            for no in ast.walk(_arvore(modelo))
            if isinstance(no, ast.ClassDef)
            for alvo in no.body
            if isinstance(alvo, ast.AnnAssign) and isinstance(alvo.target, ast.Name)
        }
        vazamento = {c for c in colunas if c in NOMES_DE_CONTEUDO}
        assert not vazamento, f"{nome}: {sorted(vazamento)}"


def test_e72b19_o_seal_step_da_e7_1_manteve_a_pre_condicao_congelada() -> None:
    """`SEAL_STEP_SEMANTICS = FROZEN_AT_E7_1`."""
    servico = ORQUESTRACAO / "services" / "handoff_service.py"
    metodos = {
        no.name: ast.unparse(no)
        for no in ast.walk(_arvore(servico))
        if isinstance(no, ast.FunctionDef)
    }
    assert "seal_step" in metodos and "seal_step_for_export" in metodos
    assert "estados_admitidos=(StepState.PENDING,)" in metodos["seal_step"]
    assert "StepState.AWAITING_RETURN" in metodos["seal_step_for_export"]
