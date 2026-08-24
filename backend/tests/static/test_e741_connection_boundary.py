"""
Guarda estática da fronteira do kernel de conexões `E7.4-1`.

```text
KERNEL_NÃO_IMPORTA_MCP · SEM REDE · SEM CREDENCIAL
ENUM_OR_REGISTRY != AVAILABLE
NEW_MANUAL_ATTEMPT = EXACTLY_ONE_RECEIPT
ROUTER_PODE_LER_REPOSITORIO != MCP_PODE_LER_REPOSITORIO
GUARD_WITHOUT_MUTANT = UNVERIFIED_GUARD
```

Tudo por AST. Docstring não é símbolo de runtime, e por isso os
invariantes que citam nomes proibidos são medidos sobre a árvore
sintática — exceto onde o alvo é o texto de um arquivo de requisitos.

## Classificação exaustiva, não enumeração parcial

```text
PARTIAL_ENUMERATION = GUARD_WITH_A_HOLE
```

A Chain110 foi reprovada porque o gate listava os cinco métodos
escopados e nada dizia sobre os demais. Aqui todo método público do
`ConnectionRepository` cai em uma de quatro categorias **disjuntas e
exaustivas**, e um método novo sem categoria reprova por omissão em vez
de passar por ela.
"""

import ast
import pathlib

import pytest

pytestmark = pytest.mark.unit

BACKEND = pathlib.Path(__file__).resolve().parents[2]
APP = BACKEND / "app"
CONEXOES = APP / "connections"
REPOSITORIO = CONEXOES / "repositories" / "connection_repository.py"
PERFIL_SERVICE = CONEXOES / "services" / "connection_profile_service.py"
MANUAL_EXPORT = APP / "orchestration" / "services" / "manual_handoff_export_service.py"
ROUTER_ORQUESTRACAO = APP / "routers" / "orchestration.py"
CONSULTA = APP / "orchestration" / "services" / "orchestration_query_service.py"
BASE_REQUIREMENTS = BACKEND / "requirements" / "base.txt"

#: O kernel nunca importa transporte, adaptador, rede ou MCP.
PACOTES_PROIBIDOS_NO_KERNEL = (
    "app.mcp",
    "app.routers",
    "app.api",
    "app.memory",
    "app.cognitive",
    "app.predictive_accessibility",
    "fastapi",
    "httpx",
    "requests",
    "aiohttp",
    "urllib",
    "socket",
    "http",
    "ssl",
)

#: Vocabulário que denuncia custódia de credencial dentro do kernel.
SIMBOLOS_DE_SEGREDO = frozenset(
    {
        "password",
        "passwd",
        "cookie",
        "session_cookie",
        "access_token",
        "refresh_token",
        "bearer",
        "client_secret",
        "api_key",
        "private_key",
        "raw_output",
        "raw_content",
    }
)

#: Dependências de runtime que a E7.4-1 não pode introduzir.
DEPENDENCIAS_PROIBIDAS = frozenset(
    {"httpx", "requests", "aiohttp", "mcp", "pyjwt", "jwt", "oauthlib", "authlib", "cryptography"}
)


def _arvore(caminho: pathlib.Path) -> ast.Module:
    return ast.parse(caminho.read_text(encoding="utf-8"))


def _arquivos_do_kernel() -> list[pathlib.Path]:
    return sorted(p for p in CONEXOES.rglob("*.py"))


def _imports(caminho: pathlib.Path) -> list[str]:
    modulos: list[str] = []
    for no in ast.walk(_arvore(caminho)):
        if isinstance(no, ast.Import):
            modulos.extend(alias.name for alias in no.names)
        elif isinstance(no, ast.ImportFrom) and no.module:
            modulos.append(no.module)
    return modulos


def _nomes(caminho: pathlib.Path) -> set[str]:
    encontrados: set[str] = set()
    for no in ast.walk(_arvore(caminho)):
        if isinstance(no, ast.Name):
            encontrados.add(no.id)
        elif isinstance(no, ast.Attribute):
            encontrados.add(no.attr)
        elif isinstance(no, ast.arg):
            encontrados.add(no.arg)
        elif isinstance(no, ast.Constant) and isinstance(no.value, str):
            encontrados.add(no.value)
    return encontrados


def _metodos_publicos(caminho: pathlib.Path, classe: str) -> list[ast.FunctionDef]:
    for no in ast.walk(_arvore(caminho)):
        if isinstance(no, ast.ClassDef) and no.name == classe:
            return [
                m for m in no.body if isinstance(m, ast.FunctionDef) and not m.name.startswith("_")
            ]
    raise AssertionError(f"classe {classe} não encontrada em {caminho}")


def _primeira_linha_docstring(metodo: ast.FunctionDef) -> str:
    texto = ast.get_docstring(metodo) or ""
    return texto.splitlines()[0] if texto else ""


# --- fronteira do kernel ----------------------------------------------------


def test_e741s01_kernel_nao_importa_transporte_rede_nem_mcp() -> None:
    """`KERNEL_NÃO_IMPORTA_MCP`.

    Remover o adaptador no futuro não pode quebrar o núcleo, e a única
    forma de garantir isso é o núcleo nunca ter dependido dele.
    """
    for arquivo in _arquivos_do_kernel():
        for modulo in _imports(arquivo):
            raiz = modulo.split(".")[0]
            assert not any(
                modulo == proibido or modulo.startswith(f"{proibido}.") or raiz == proibido
                for proibido in PACOTES_PROIBIDOS_NO_KERNEL
            ), f"{arquivo.relative_to(BACKEND)} importa {modulo}"


def test_e741s02_kernel_nao_guarda_segredo_token_nem_conteudo_bruto() -> None:
    """Prova 7 — ausência de senha, cookie, token e conteúdo bruto.

    ```text
    TOKEN_PASSTHROUGH = FORBIDDEN
    RAW_OUTPUT_IN_DATABASE = FORBIDDEN
    ```
    """
    for arquivo in _arquivos_do_kernel():
        encontrados = {n.lower() for n in _nomes(arquivo)} & SIMBOLOS_DE_SEGREDO
        assert not encontrados, f"{arquivo.relative_to(BACKEND)} cita {sorted(encontrados)}"


def test_e741s03_base_requirements_sem_dependencia_nova() -> None:
    """Stop Condition: dependência nova em `base.txt` é ato próprio."""
    linhas = BASE_REQUIREMENTS.read_text(encoding="utf-8").lower()
    for proibida in DEPENDENCIAS_PROIBIDAS:
        assert f"\n{proibida}" not in f"\n{linhas}", f"{proibida} entrou em base.txt"


def test_e741s04_nenhuma_varredura_local() -> None:
    """Prova 24 — descoberta local **sem varredura**.

    ```text
    NUNCA: varredura de portas, processos ou arquivos locais
    ```

    A ausência é medida, não afirmada: nenhum arquivo do kernel importa
    `os`, `socket`, `subprocess`, `glob` ou `psutil`, e não há membro de
    `CapabilitySource` que pudesse rotular o resultado de uma varredura.
    """
    varredores = {"os", "socket", "subprocess", "glob", "psutil", "shutil", "pathlib"}
    for arquivo in _arquivos_do_kernel():
        raizes = {m.split(".")[0] for m in _imports(arquivo)}
        assert not (raizes & varredores), f"{arquivo.relative_to(BACKEND)} importa varredor"

    from app.connections.models.enums import CapabilitySource

    rotulos = {m.value for m in CapabilitySource}
    assert not any("scan" in r or "varredura" in r or "probe" in r for r in rotulos)


# --- classificação exaustiva do repositório ---------------------------------

CATEGORIAS = (
    "SCOPED_READ",
    "SCOPED_WRITE",
    "CATALOG_READ",
    "CATALOG_WRITE",
    "INFRASTRUCTURE",
)
"""Cinco categorias **disjuntas e exaustivas**.

`INFRASTRUCTURE` cobre o que não lê nem escreve domínio — relógio do
banco e savepoint. Ela existe porque a alternativa seria classificar
`database_now` como leitura escopada e exigir dela um
`control_principal_ref` que não significa nada ali: uma categoria
forçada é pior que uma categoria a mais, porque faz a guarda medir o
que não é.
"""


def test_e741s05_todo_metodo_publico_do_repositorio_tem_categoria() -> None:
    """Classificação **exaustiva** em quatro categorias disjuntas.

    ```text
    PARTIAL_ENUMERATION = GUARD_WITH_A_HOLE
    ```

    Um método novo sem categoria na primeira linha da docstring reprova
    por omissão — que é o oposto de passar por omissão.
    """
    metodos = _metodos_publicos(REPOSITORIO, "ConnectionRepository")
    assert metodos, "nenhum método público encontrado"
    sem_categoria = [
        m.name
        for m in metodos
        if not any(_primeira_linha_docstring(m).startswith(c) for c in CATEGORIAS)
    ]
    assert not sem_categoria, f"métodos sem categoria declarada: {sem_categoria}"


INFRAESTRUTURA_PERMITIDA = frozenset({"database_now", "nested_transaction"})
"""Lista **fechada**. Ampliar exige alterar esta linha, que é o ponto.

```text
CATEGORIA_FORÇADA = GUARDA_QUE_MEDE_O_QUE_NÃO_É
CATEGORIA_ABERTA  = PORTA_DOS_FUNDOS
```

A categoria existe porque `database_now` e `nested_transaction` não leem
nem escrevem domínio, e exigir deles um `control_principal_ref` seria
prometer um isolamento que a operação não tem. Mas uma categoria sem
lista fechada viraria o lugar onde qualquer método novo escapa da
classificação — por isso a enumeração é literal, e não um predicado.
"""


def test_e741s05b_infraestrutura_e_exatamente_dois_metodos_e_nao_toca_entidade() -> None:
    """As quatro condições da categoria, verificadas — não afirmadas.

    1. contém exclusivamente `database_now` e `nested_transaction`;
    2. nenhum dos dois devolve ou consulta entidade;
    3. a enumeração é exaustiva e literal;
    4. método público novo sem categoria reprova (`test_e741s05`).
    """
    metodos = _metodos_publicos(REPOSITORIO, "ConnectionRepository")
    declarados = {
        m.name for m in metodos if _primeira_linha_docstring(m).startswith("INFRASTRUCTURE")
    }
    assert declarados == INFRAESTRUTURA_PERMITIDA, (
        f"categoria INFRASTRUCTURE deixou de ser exatamente {sorted(INFRAESTRUTURA_PERMITIDA)}: "
        f"{sorted(declarados)}"
    )

    modelos = {
        "ConnectionProfile",
        "CapabilitySnapshot",
        "EntitlementClaim",
        "EvaluationEvidence",
        "ConnectionExecutionReceipt",
        "ProviderFamily",
        "ModelFamily",
        "ModelRelease",
        "AccessProvider",
    }
    for metodo in metodos:
        if metodo.name not in INFRAESTRUTURA_PERMITIDA:
            continue
        citados = set()
        for no in ast.walk(metodo):
            if isinstance(no, ast.Name):
                citados.add(no.id)
            elif isinstance(no, ast.Attribute):
                citados.add(no.attr)
        assert not (
            citados & modelos
        ), f"{metodo.name} é INFRASTRUCTURE e cita entidade {sorted(citados & modelos)}"
        # Nem consulta: `select`/`update`/`delete` de entidade ficam fora.
        assert "add" not in citados and "scalars" not in citados


def test_e741s06_todo_metodo_scoped_exige_control_principal_ref() -> None:
    """`SCOPED_READ_PATH != SCOPED_WRITE_PATH`.

    O escopo mora no repositório, e vale para leitura **e** escrita. A
    Chain110 impunha o vínculo só nas leituras; a Chain111 e a Chain112
    mostraram que derivar o dono do próprio dado é tautologia.
    """
    for metodo in _metodos_publicos(REPOSITORIO, "ConnectionRepository"):
        categoria = _primeira_linha_docstring(metodo).split(" ")[0]
        if not categoria.startswith("SCOPED"):
            continue
        argumentos = {a.arg for a in metodo.args.args} | {a.arg for a in metodo.args.kwonlyargs}
        assert (
            "control_principal_ref" in argumentos
        ), f"{metodo.name} é {categoria} e não recebe control_principal_ref"


def test_e741s07_catalogo_nao_finge_escopo() -> None:
    """Categoria de catálogo é curadoria global — e isso é **declarado**.

    Um método de catálogo que recebesse `control_principal_ref` estaria
    prometendo um isolamento que a tabela não tem.
    """
    for metodo in _metodos_publicos(REPOSITORIO, "ConnectionRepository"):
        if not _primeira_linha_docstring(metodo).startswith("CATALOG"):
            continue
        argumentos = {a.arg for a in metodo.args.args} | {a.arg for a in metodo.args.kwonlyargs}
        assert (
            "control_principal_ref" not in argumentos
        ), f"{metodo.name} é CATALOG e recebe control_principal_ref"


# --- dependência obrigatória do recibo no handoff manual --------------------


def _construcoes_de(nome_classe: str) -> list[tuple[pathlib.Path, ast.Call]]:
    achados: list[tuple[pathlib.Path, ast.Call]] = []
    for arquivo in sorted(APP.rglob("*.py")):
        for no in ast.walk(_arvore(arquivo)):
            if (
                isinstance(no, ast.Call)
                and isinstance(no.func, ast.Name)
                and no.func.id == nome_classe
            ):
                achados.append((arquivo, no))
    return achados


def test_e741s08_toda_construcao_do_manual_injeta_o_recibo() -> None:
    """Varre **todo** `app/`: nenhuma raiz de composição sem a dependência.

    ```text
    NEW_MANUAL_ATTEMPT = EXACTLY_ONE_RECEIPT
    NO_DEFAULT · NO_SILENT_FALLBACK
    ```

    A varredura é de `app/` inteiro, e não das duas raízes conhecidas: uma
    guarda que enumera os chamadores de hoje não protege o chamador de
    amanhã.
    """
    construcoes = _construcoes_de("ManualHandoffExportService")
    assert construcoes, "nenhuma construção encontrada — guarda vazia"
    for arquivo, chamada in construcoes:
        nomeados = {kw.arg for kw in chamada.keywords}
        assert "connection_receipts" in nomeados, (
            f"{arquivo.relative_to(BACKEND)}:{chamada.lineno} constrói o serviço manual "
            "sem connection_receipts"
        )
        assert "connection_profiles" in nomeados, (
            f"{arquivo.relative_to(BACKEND)}:{chamada.lineno} constrói o serviço manual "
            "sem connection_profiles"
        )


def test_e741s09_a_dependencia_nao_tem_default_nem_fallback() -> None:
    """`= None` faria "esqueci de injetar" e "decidi não atribuir" empatarem."""
    for no in ast.walk(_arvore(MANUAL_EXPORT)):
        if not (isinstance(no, ast.FunctionDef) and no.name == "__init__"):
            continue
        obrigatorios = {a.arg for a in no.args.kwonlyargs}
        assert {"connection_profiles", "connection_receipts"} <= obrigatorios
        for arg, default in zip(no.args.kwonlyargs, no.args.kw_defaults, strict=True):
            if arg.arg in {"connection_profiles", "connection_receipts"}:
                assert default is None, f"{arg.arg} não pode ter default"
        return
    raise AssertionError("__init__ não encontrado")


def test_e741s10_a_gravacao_do_recibo_esta_no_servico_e_nao_no_router() -> None:
    """A garantia precisa valer para todo chamador, inclusive os futuros.

    Se a gravação vivesse no router, um segundo chamador do serviço
    produziria Attempt sem atribuição — e o documento continuaria dizendo
    que toda Attempt tem recibo.
    """
    chamadas_no_servico = {
        no.func.attr
        for no in ast.walk(_arvore(MANUAL_EXPORT))
        if isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute)
    }
    assert "record_execution" in chamadas_no_servico
    assert "ensure_manual_profile" in chamadas_no_servico

    chamadas_no_router = {
        no.func.attr
        for no in ast.walk(_arvore(ROUTER_ORQUESTRACAO))
        if isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute)
    }
    assert "record_execution" not in chamadas_no_router, "o router grava o recibo"


def test_e741s11_nao_existe_producao_de_recibo_retroativo() -> None:
    """`LEGACY_ATTEMPT_WITHOUT_RECEIPT != FABRICATE_HISTORY`.

    Nenhum caminho varre Attempts antigas para criar atribuição que
    ninguém observou. A ausência é medida pela inexistência de qualquer
    símbolo de retroatividade no kernel e no serviço manual.
    """
    proibidos = {"backfill", "retroactive", "retroativo", "migrar_attempts", "seed_receipts"}
    for arquivo in [*_arquivos_do_kernel(), MANUAL_EXPORT]:
        encontrados = {n.lower() for n in _nomes(arquivo)} & proibidos
        assert not encontrados, f"{arquivo.relative_to(BACKEND)} cita {sorted(encontrados)}"

    from app.connections.repositories.connection_repository import ConnectionRepository

    publicos = [n for n in dir(ConnectionRepository) if not n.startswith("_")]
    assert not any("list_attempts" in n or "backfill" in n for n in publicos)


# --- fronteira de leitura: nenhum bypass de repositório no router -----------


def test_e741s12_router_nao_alcanca_o_repositorio_de_orquestracao() -> None:
    """Prova 28 / correção R1 — `OrchestrationQueryService` absorve as nove.

    ```text
    ROUTER_PODE_LER_REPOSITORIO != MCP_PODE_LER_REPOSITORIO
    BYPASS_AST = 0
    ```

    Medido na Chain117: nove chamadas diretas ao repositório, nas linhas
    444, 447, 452, 605, 608, 839, 845, 851 e 857. Hoje isso é aceitável
    porque o router é transporte do próprio PIA; expor por MCP daria ao
    boundary um caminho que passa ao lado dos serviços.
    """
    assert CONSULTA.exists(), "OrchestrationQueryService não existe"

    leitura_de_repositorio = {
        "list_attempts",
        "get_handoff_result",
        "get_handoff_attribution",
        "get_attempt",
        "get_step",
        "list_delegations",
        "list_control_events",
        "list_execution_observations",
        "list_audit_opinions",
    }
    bypass = [
        (no.lineno, no.func.attr)
        for no in ast.walk(_arvore(ROUTER_ORQUESTRACAO))
        if isinstance(no, ast.Call)
        and isinstance(no.func, ast.Attribute)
        and no.func.attr in leitura_de_repositorio
        and isinstance(no.func.value, ast.Name)
        and no.func.value.id in {"repositorio", "repository"}
    ]
    assert bypass == [], f"BYPASS_AST != 0: {bypass}"


def test_e741s13_o_servico_de_consulta_devolve_dataclass_congelada() -> None:
    """Nenhuma instância ORM cruza a fronteira pública.

    Um retorno mutável daria ao chamador a impressão de poder alterar o
    que leu — e um `DetachedInstanceError` seria o melhor desfecho.
    """
    congeladas = [
        no.name
        for no in ast.walk(_arvore(CONSULTA))
        if isinstance(no, ast.ClassDef)
        and any(
            isinstance(d, ast.Call)
            and isinstance(d.func, ast.Name)
            and d.func.id == "dataclass"
            and any(kw.arg == "frozen" and kw.value.value is True for kw in d.keywords)
            for d in no.decorator_list
        )
    ]
    assert congeladas, "nenhuma dataclass congelada no serviço de consulta"


# --- vocabulário: declarar não é disponibilizar -----------------------------


def test_e741s14_apenas_o_manual_pode_estar_available() -> None:
    """`ENUM_OR_REGISTRY != AVAILABLE`, nas três camadas."""
    from app.connections.models.enums import (
        AVAILABLE_CONNECTION_METHODS,
        BASELINE_METHOD_STATE,
        ConnectionMethod,
        ConnectionState,
    )

    assert frozenset({ConnectionMethod.MANUAL_HANDOFF}) == AVAILABLE_CONNECTION_METHODS
    disponiveis = {
        metodo
        for metodo, estado in BASELINE_METHOD_STATE.items()
        if estado is ConnectionState.AVAILABLE
    }
    assert disponiveis == {ConnectionMethod.MANUAL_HANDOFF}
    assert (
        BASELINE_METHOD_STATE[ConnectionMethod.PROVIDER_NATIVE_MCP_INBOUND]
        is ConnectionState.PREFLIGHT_REQUIRED
    )
    assert set(BASELINE_METHOD_STATE) == set(ConnectionMethod), "método sem estado de nascimento"


def test_e741s15_familia_release_provedor_e_conexao_nao_colapsam() -> None:
    """Prova 16 — quatro identidades, quatro tabelas, quatro chaves."""
    from app.connections.models.capability import CapabilitySnapshot
    from app.connections.models.catalog import (
        AccessProvider,
        ModelFamily,
        ModelRelease,
        ProviderFamily,
    )
    from app.connections.models.connection_profile import ConnectionProfile

    tabelas = {
        ProviderFamily.__tablename__,
        ModelFamily.__tablename__,
        ModelRelease.__tablename__,
        AccessProvider.__tablename__,
        ConnectionProfile.__tablename__,
        CapabilitySnapshot.__tablename__,
    }
    assert len(tabelas) == 6, "duas entidades compartilham tabela"
    assert "provider_family_id" in ModelFamily.__table__.columns
    assert "model_family_id" in ModelRelease.__table__.columns
    assert "access_provider_id" in ConnectionProfile.__table__.columns
    # Capacidade NÃO vive no perfil: vive em snapshot com TTL.
    assert "capabilities" not in ConnectionProfile.__table__.columns
    assert "valid_until" in CapabilitySnapshot.__table__.columns
