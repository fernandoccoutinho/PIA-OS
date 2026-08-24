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
import io
import pathlib
import re
import tokenize

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


#: Leituras que uma tool MCP consumiria — as que o plano mediu (nove) mais
#: as três descobertas por esta guarda no caminho de reconstrução de replay.
LEITURAS_DE_CONSULTA_MCP = frozenset(
    {
        "list_attempts",
        "get_handoff_result",
        "get_handoff_attribution",
        "get_attempt",
        "get_step",
        "get_seal_receipt_by_attempt",
        "list_delegations",
        "list_control_events",
        "list_execution_observations",
        "list_audit_opinions",
    }
)

#: Chamadas diretas ao repositório que o plano PERMITE ao router, porque
#: são caminho de escrita ou de lock do próprio PIA — não superfície de
#: leitura que uma tool consumiria.
CHAMADAS_INTERNAS_PERMITIDAS = frozenset(
    {
        "lock_schedule",
        "get_command_receipt",
        "get_control_event",
        "get_audit_opinion",
        "get_delegation",
    }
)
"""Corretivo R1 do achado C3.

```text
MCP_QUERY_BYPASS_AST = 0   != ZERO_BYPASS_NO_ROUTER
ROUTER_PODE_LER_REPOSITORIO != MCP_PODE_LER_REPOSITORIO
```

A guarda anterior procurava nove nomes predefinidos e eu declarei
`BYPASS_AST = 0`. A afirmação era ampla demais: sobravam cinco chamadas
diretas ao repositório no router (`lock_schedule`, `get_command_receipt`,
`get_control_event`, `get_audit_opinion`, `get_delegation`), e a guarda
provava "zero dentre as consultas catalogadas", não "zero bypass".

O plano permite leitura interna ao router. O que não pode é uma chamada
**não classificada** passar em silêncio — por isso a classificação abaixo
é exaustiva, e não uma lista de proibidos.
"""


def test_e741s12_nenhuma_consulta_de_superficie_mcp_alcanca_o_repositorio() -> None:
    """`MCP_QUERY_BYPASS_AST = 0` — nome honesto do que é medido.

    As doze leituras que uma tool consumiria passam pelo
    `OrchestrationQueryService`. As internas permitidas continuam onde
    estão, declaradas.
    """
    assert CONSULTA.exists(), "OrchestrationQueryService não existe"
    bypass = [
        (no.lineno, no.func.attr)
        for no in ast.walk(_arvore(ROUTER_ORQUESTRACAO))
        if isinstance(no, ast.Call)
        and isinstance(no.func, ast.Attribute)
        and no.func.attr in LEITURAS_DE_CONSULTA_MCP
        and isinstance(no.func.value, ast.Name)
        and no.func.value.id in {"repositorio", "repository"}
    ]
    assert bypass == [], f"MCP_QUERY_BYPASS_AST != 0: {bypass}"


def test_e741s12b_toda_chamada_direta_do_router_esta_classificada() -> None:
    """Classificação **exaustiva**, não lista de proibidos.

    ```text
    PARTIAL_ENUMERATION = GUARD_WITH_A_HOLE
    ```

    Uma chamada direta nova ao repositório reprova por omissão até que
    alguém a classifique como consulta de superfície (e a mova para o
    serviço) ou como interna permitida (e a declare aqui).
    """
    diretas = {
        no.func.attr
        for no in ast.walk(_arvore(ROUTER_ORQUESTRACAO))
        if isinstance(no, ast.Call)
        and isinstance(no.func, ast.Attribute)
        and isinstance(no.func.value, ast.Name)
        and no.func.value.id in {"repositorio", "repository"}
    }
    assert diretas, "nenhuma chamada direta encontrada — guarda vazia"
    nao_classificadas = diretas - LEITURAS_DE_CONSULTA_MCP - CHAMADAS_INTERNAS_PERMITIDAS
    assert (
        not nao_classificadas
    ), f"chamada direta ao repositório sem classificação: {sorted(nao_classificadas)}"
    # Não-vacuidade: a lista de permitidas descreve o que existe HOJE.
    assert diretas == CHAMADAS_INTERNAS_PERMITIDAS, (
        "a lista de internas permitidas divergiu do router: "
        f"faltam {sorted(CHAMADAS_INTERNAS_PERMITIDAS - diretas)}, "
        f"sobram {sorted(diretas - CHAMADAS_INTERNAS_PERMITIDAS)}"
    )


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


def _type_ignores(caminho: pathlib.Path) -> list[tuple[int, str, str]]:
    """TODO comentário `type: ignore` do mypy — qualificado **ou amplo**.

    Devolve `(linha, código, texto)`; o código é o que está entre
    colchetes, ou `<amplo>` quando não há colchetes.

    ```text
    TOKENIZATION = CORRECT
    IGNORE_POLICY = INCOMPLETE   <- o defeito R4-C1
    ```

    ACHADO C1 DA AUDITORIA DA CHAIN121. A versão do R3 tokenizava
    corretamente e procurava o literal `type: ignore[attr-defined]`. Um
    `# type: ignore` **amplo** — que é mais permissivo, porque silencia
    toda categoria de erro e não só `attr-defined` — atravessava o
    detector. Tokenizar certo e procurar a coisa errada continua sendo
    procurar a coisa errada.

    A expressão regular admite espaço variável (`type:ignore`,
    `type:  ignore`) porque o mypy admite; casar só a forma canônica
    reabriria a mesma porta com outra grafia.

    `tokenize` distingue COMMENT de STRING no nível do lexer, então
    menção em docstring não é comentário e não entra — sem depender de
    nenhuma convenção de escrita. Essa parte, herdada do corretivo R3,
    permanece correta: o defeito era a política, não a tokenização.
    """
    fonte = caminho.read_text(encoding="utf-8")
    achados: list[tuple[int, str, str]] = []
    with io.StringIO(fonte) as fluxo:
        for token in tokenize.generate_tokens(fluxo.readline):
            if token.type is not tokenize.COMMENT:
                continue
            if not re.search(r"type:\s*ignore", token.string):
                continue
            qualificado = re.search(r"type:\s*ignore\[([^\]]+)\]", token.string)
            codigo = qualificado.group(1) if qualificado else "<amplo>"
            achados.append((token.start[0], codigo, token.string.strip()))
    return achados


def _funcao_proprietaria(caminho: pathlib.Path, linha: int) -> str:
    """Função que CONTÉM a linha — a mais interna, quando há aninhamento."""
    arvore = _arvore(caminho)
    candidatas = [
        no
        for no in ast.walk(arvore)
        if isinstance(no, ast.FunctionDef | ast.AsyncFunctionDef)
        and no.lineno <= linha <= (no.end_lineno or no.lineno)
    ]
    if not candidatas:
        return "<módulo>"
    return min(candidatas, key=lambda f: (f.end_lineno or f.lineno) - f.lineno).name


# --- corretivo R1: fronteiras tipadas, não silenciadas ---------------------

FRONTEIRAS_TIPADAS = (
    APP / "orchestration" / "services" / "orchestration_query_service.py",
    APP / "connections" / "services" / "connection_profile_service.py",
    APP / "connections" / "services" / "connection_execution_receipt_service.py",
)
"""Arquivos onde `type: ignore[attr-defined]` é PROIBIDO.

```text
SILENCED_BOUNDARY = UNCHECKED_BOUNDARY
```

Achado C2 da auditoria da Chain118: o delta acrescentou 90 ignores de
`attr-defined`, 55 deles só no serviço de consulta. Os helpers recebiam
`object` e silenciavam todo acesso a campo, de modo que drift de nome ou
de tipo atravessaria o mypy sem erro.

E atravessava: ao tipar concretamente, o mypy achou **dois** defeitos
reais que os ignores escondiam — `provenance_record_ref` declarado `str`
sendo `UUID`, e três campos `NOT NULL` declarados opcionais na projeção.

O router NÃO entra nesta lista: ele conserva ignores históricos em
helpers que recebem linha ORM viva dentro da transação de escrita, e
tipá-los é ampliação que esta auditoria não pediu. O que a guarda impede
é a reintrodução nas fronteiras novas.
"""


def test_e741s16_fronteiras_novas_nao_silenciam_acesso_a_campo() -> None:
    """`TYPE_IGNORE = ZERO` nas fronteiras tipadas.

    CORRETIVO R4: a política deixou de ser "nenhum `attr-defined`" e
    passou a ser "**nenhum** `type: ignore`, qualificado ou amplo". Um
    ignore amplo é mais permissivo que o qualificado, e permitir o mais
    permissivo enquanto se proíbe o menos era o defeito R4-C1.
    """
    for arquivo in FRONTEIRAS_TIPADAS:
        culpadas = _type_ignores(arquivo)
        assert not culpadas, f"TYPE_IGNORE != ZERO em {arquivo.relative_to(BACKEND)}: {culpadas}"


def test_e741s17_os_helpers_do_servico_de_consulta_recebem_tipo_concreto() -> None:
    """`object` como parâmetro de projeção é o que permitia o silêncio.

    A guarda mede a **assinatura**, não a ausência do ignore: sem tipo
    concreto, o ignore volta a ser necessário e alguém o recoloca.
    """
    arvore = _arvore(CONSULTA)
    projetores = [
        no
        for no in ast.walk(arvore)
        if isinstance(no, ast.FunctionDef) and no.name.startswith("_projetar")
    ]
    assert projetores, "nenhum projetor encontrado — guarda vazia"
    for funcao in projetores:
        for argumento in funcao.args.args:
            anotacao = argumento.annotation
            assert anotacao is not None, f"{funcao.name}: parâmetro sem anotação"
            assert not (
                isinstance(anotacao, ast.Name) and anotacao.id == "object"
            ), f"{funcao.name}: parâmetro `object` reabre a fronteira silenciada"


# --- corretivo R2: os quatro mapeadores tipados do router ------------------

MAPEADORES_TIPADOS_DO_ROUTER: dict[str, str] = {
    "_delegation_view_da_projecao": "DelegationProjection",
    "_control_event_da_projecao": "ControlEventProjection",
    "_observation_da_projecao": "ObservationProjection",
    "_audit_da_projecao": "AuditOpinionProjection",
    "_result_view": "ResultProjection",
    "_attribution_view": "AttributionProjection",
}
"""Os mapeadores que a Chain118 passou a alimentar com projeções congeladas.

```text
ARQUIVO_EXCLUÍDO_DA_GUARDA != FUNÇÃO_EXCLUÍDA_DA_GUARDA
```

ACHADO R2 DA AUDITORIA DA CHAIN119. `s16` exclui o router inteiro —
correto, porque ele conserva 48 ignores históricos em helpers que recebem
linha ORM viva. Mas a exclusão do **arquivo** deixou estas seis funções
sem proteção nenhuma: alguém poderia rebaixar um parâmetro para `object`
e reintroduzir `attr-defined` sem que guarda alguma reprovasse.

A implementação estava certa; a proteção permanente é que estava
incompleta. A guarda passa a ser por **função**, não por arquivo.
"""


def _funcao_do_router(nome: str) -> ast.FunctionDef:
    for no in ast.walk(_arvore(ROUTER_ORQUESTRACAO)):
        if isinstance(no, ast.FunctionDef) and no.name == nome:
            return no
    raise AssertionError(f"{nome} não existe em {ROUTER_ORQUESTRACAO.name}")


def test_e741s18_os_mapeadores_do_router_tem_tipo_concreto_exato() -> None:
    """Tipo **exato**, não apenas "não é `object`".

    Uma anotação qualquer satisfaria uma guarda que só recusasse
    `object`; exigir o nome da projeção correspondente é o que impede
    trocar o tipo por outro e continuar passando.
    """
    for nome, esperado in MAPEADORES_TIPADOS_DO_ROUTER.items():
        funcao = _funcao_do_router(nome)
        assert len(funcao.args.args) == 1, f"{nome}: assinatura mudou"
        anotacao = funcao.args.args[0].annotation
        assert isinstance(anotacao, ast.Name), f"{nome}: anotação ausente ou não simples"
        assert anotacao.id == esperado, f"{nome}: esperado `{esperado}`, encontrado `{anotacao.id}`"


def test_e741s19_os_mapeadores_do_router_nao_silenciam_acesso_a_campo() -> None:
    """Nenhum `attr-defined` no CORPO destas seis funções.

    O restante do router segue com os seus ignores históricos, e isso é
    deliberado — a guarda mede as funções que o commit converteu, não o
    arquivo inteiro.
    """
    todos = _type_ignores(ROUTER_ORQUESTRACAO)
    for nome in MAPEADORES_TIPADOS_DO_ROUTER:
        funcao = _funcao_do_router(nome)
        fim = funcao.end_lineno or funcao.lineno
        culpadas = [(n, cod, txt) for n, cod, txt in todos if funcao.lineno <= n <= fim]
        assert not culpadas, f"{nome} silencia acesso a campo: {culpadas}"


INVENTARIO_AUTORIZADO_DO_ROUTER: dict[tuple[str, str], int] = {
    ("_assert_every_route_is_protected", "attr-defined"): 1,
    ("_audit_view", "attr-defined"): 6,
    ("_control_event_view", "attr-defined"): 6,
    ("_delegation_view_from", "attr-defined"): 8,
    ("_observation_view", "attr-defined"): 9,
    ("_resposta_export", "attr-defined"): 3,
    ("_resposta_import", "attr-defined"): 2,
    ("_schedule_view", "attr-defined"): 5,
    ("_step_view", "attr-defined"): 8,
}
"""Inventário ESTRUTURAL dos 48 ignores históricos: função, código, quantidade.

```text
CONTAGEM_GLOBAL = INVENTÁRIO_FRACO
```

ACHADO C1 DA AUDITORIA DA CHAIN121, segundo facet. `s20` congelava
apenas o total `48`. Remover um ignore histórico de um helper e
introduzir outro em local novo mantinha o total e atravessava a guarda —
a soma é invariante sob troca, e trocar era exatamente o ataque.

O inventário prende **onde** e **de que tipo**, não quanto. Cada helper
listado recebe linha ORM viva dentro da transação de escrita, e é por
isso que os seus ignores são legítimos; um ignore em qualquer outra
função não é histórico, é novo.
"""


def _divergentes(inventario: dict[tuple[str, str], int]) -> list[tuple[str, str]]:
    """Chaves cuja quantidade difere do autorizado."""
    return [
        chave
        for chave, quantidade in inventario.items()
        if INVENTARIO_AUTORIZADO_DO_ROUTER.get(chave) != quantidade
    ]


def test_e741s20_o_router_conserva_apenas_os_ignores_historicos() -> None:
    """Contagem declarada, não "zero global".

    ```text
    NEW_ATTR_DEFINED_IN_TYPED_BOUNDARIES = 0
    HISTORICAL_ROUTER_ATTR_DEFINED       = 48
    ```

    A guarda prende o número: se subir, alguém reintroduziu silêncio no
    router; se cair, alguém tipou helpers históricos sem declarar a
    ampliação. Os dois merecem revisão, e nenhum deve passar calado.

    CORRETIVO R3: a contagem passou a vir de `_ignores_attr_defined`,
    que tokeniza. A versão da Chain120 filtrava linhas com crase e era
    atravessada por `# type: ignore[attr-defined]  # \N{GRAVE ACCENT}x\N{GRAVE ACCENT}`.

    ```text
    HEURISTICA_DE_LINHA = GUARDA_CONTORNÁVEL
    GUARD_PASSED != PROPERTY_PROVED
    ```
    """
    inventario: dict[tuple[str, str], int] = {}
    for linha, codigo, _ in _type_ignores(ROUTER_ORQUESTRACAO):
        chave = (_funcao_proprietaria(ROUTER_ORQUESTRACAO, linha), codigo)
        inventario[chave] = inventario.get(chave, 0) + 1

    assert inventario == INVENTARIO_AUTORIZADO_DO_ROUTER, (
        "o inventário de ignores do router divergiu do autorizado.\n"
        f"  sobram: {sorted(set(inventario) - set(INVENTARIO_AUTORIZADO_DO_ROUTER))}\n"
        f"  faltam: {sorted(set(INVENTARIO_AUTORIZADO_DO_ROUTER) - set(inventario))}\n"
        f"  quantidade divergente: {sorted(_divergentes(inventario))}"
    )
    assert sum(inventario.values()) == 48, (
        f"HISTORICAL_ROUTER_ATTR_DEFINED mudou de 48 para {sum(inventario.values())}; "
        "se foi ampliação deliberada, atualize o inventário E declare no handoff"
    )


# --- corretivo R3: a documentação não pode contradizer o vínculo real ------


def test_e741s21_a_documentacao_do_recibo_descreve_a_fk_real() -> None:
    """A prosa que explica o vínculo é conferida contra o ORM.

    ```text
    DOCUMENTAÇÃO_DESATUALIZADA = AFIRMAÇÃO_FALSA_NO_REPOSITÓRIO
    ```

    ACHADO C2 DA AUDITORIA DA CHAIN120. O corretivo R1 trocou a FK
    binária pela ternária no ORM e na migration, e deixou dois textos
    dizendo `(connection_id, control_principal_ref)` — a docstring do
    próprio modelo e o documento de entrega. A documentação contradizia
    exatamente o schema que pretendia explicar.

    A guarda lê as colunas da FK **no metadata** e exige que os dois
    textos as mencionem. Comparar contra o ORM, e não contra uma lista
    escrita à mão, é o que impede a guarda de envelhecer junto com a
    prosa.
    """
    from app.connections.models.connection_execution_receipt import ConnectionExecutionReceipt

    alvo = "fk_connection_execution_receipts_connection_within_principal"
    fks = [
        fk
        for fk in ConnectionExecutionReceipt.__table__.constraints
        if getattr(fk, "name", None) == alvo
    ]
    assert len(fks) == 1, f"{alvo} não encontrada no metadata"
    colunas = [c.name for c in fks[0].columns]  # type: ignore[attr-defined]
    assert colunas == [
        "connection_id",
        "control_principal_ref",
        "connection_method",
    ], f"a FK mudou para {colunas}; atualize a documentação E esta guarda"

    # Representação CANÔNICA derivada do metadata, não escrita à mão.
    #
    # ```text
    # PALAVRA_PRESENTE != DESCRIÇÃO_CORRETA
    # ```
    #
    # ACHADO C2 DA AUDITORIA DA CHAIN121. A versão do R3 exigia apenas
    # que a palavra `connection_method` aparecesse em algum lugar e que a
    # tupla binária não aparecesse. Uma descrição com coluna inventada
    # passava, porque a palavra verdadeira estava em outro parágrafo.
    canonica = "(" + ", ".join(colunas) + ")"
    documentos = (
        APP / "connections" / "models" / "connection_execution_receipt.py",
        BACKEND / "docs" / "entregas" / "entrega-7" / "E7_4_1_CONNECTION_KERNEL.md",
    )
    padrao = re.compile(r"\(connection_id,\s*control_principal_ref[^)]*\)")
    for documento in documentos:
        normalizado = " ".join(documento.read_text(encoding="utf-8").split())
        assert canonica in normalizado, (
            f"{documento.name} não contém a representação canônica `{canonica}`; "
            "a descrição do vínculo precisa listar as três colunas, na ordem do schema"
        )
        divergentes = {t for t in padrao.findall(normalizado) if t != canonica}
        assert (
            not divergentes
        ), f"{documento.name} descreve o vínculo de outra forma: {sorted(divergentes)}"
