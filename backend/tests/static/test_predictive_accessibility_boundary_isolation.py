"""
Guardas de **camada** da Predictive Accessibility (`E5.b`).

```text
LAYER_GUARD = DYNAMIC_DISCOVERY_OVER_THE_WHOLE_NAMESPACE
DEFINITION_NAME_GUARD != LAYER_CAPABILITY_GUARD
FROZEN_INVENTORY != LAYER_PROTECTION
```

A `E5.a` deixou guardas **locais**, presas a uma lista fixa de doze arquivos.
Duas consequências foram medidas antes desta etapa, em clone descartável da
Chain102:

1. **falso negativo** — dentro de um arquivo já autorizado, cinco capacidades
   normativamente proibidas passavam intactas pela suíte estática inteira:
   constante `COUT_P_SCORE`, `INACCESSIBLE` sem qualificação, `Conflict` sem
   qualificação, seleção de provedor e import de rede. A guarda local olhava
   apenas nomes de *definição* (classe e função), então **atribuição, parâmetro
   e atributo** ficavam fora do alcance;
2. **falso positivo** — um módulo científico futuro corretamente nomeado
   (`predictive_claim.py`, `class PredictiveClaim`) reprovava **só por
   existir**, porque a lista fixa afirmava igualdade com o namespace inteiro.

Este arquivo descobre as fontes por varredura recursiva, sem lista fixa, e
analisa tudo por AST. Nenhuma regra usa busca textual no arquivo inteiro: isso
acusaria as próprias docstrings, escritas justamente para nomear o que a camada
**não** faz.

```text
DOCSTRING != RUNTIME_SYMBOL
COUT-P = DOCUMENTARY_NAME_ONLY
```

## Colisão nominal que a tokenização resolve

`EDR_COUT_PIA_E3` existe na documentação do repositório. Uma busca ingênua por
`cout_p` casaria `cout_pia` e produziria falso positivo. Os identificadores são
quebrados em *tokens* (`_`, `-` e fronteira CamelCase) antes de comparar, então
`COUT_PIA` vira `["cout", "pia"]` e não casa, enquanto `COUT_PScore` vira
`["cout", "p", "score"]` e casa.

## Identificadores congelados pelo Master

`PREDICTIVELY_INACCESSIBLE`, `CLAIM_EVALUATION_RESULT` e
`MAX_CLAIMS_PER_EVALUATION` são nomes exatos já congelados. A regra de prefixo
alcança tipos, serviços e funções científicas públicas — não renomeia estado
nem constante congelada.

## Persistência própria da E5

O Master admite persistência exclusivamente em `E5.l`, no Patch 3. Aqui a
allowlist é materializada **vazia e explícita**: uma allowlist ausente seria
indistinguível de uma permissão esquecida.

```text
PATCH_2_E5_OWN_PERSISTENCE_ALLOWLIST = EMPTY
E5_WRITES_E3_OR_E4 = FORBIDDEN_UNCONDITIONALLY
```

Os `test_b99_*` no fim demonstram que cada mecanismo consegue reprovar.

```text
GUARD_WITHOUT_MUTANT = UNVERIFIED_GUARD
```
"""

import ast
import pathlib
import re

import pytest

pytestmark = pytest.mark.unit

RAIZ = pathlib.Path(__file__).resolve().parents[2]
PACOTE = RAIZ / "app" / "predictive_accessibility"
MIGRACOES = RAIZ / "alembic" / "versions"

# Sub-pacotes protocolares da E5.a. A regra de prefixo científico não se aplica
# a eles: `PiapEnvelope`, `ApprovalBinding` e `GovernedReadPort` são protocolo,
# não componente científico.
SUBPACOTES_PROTOCOLARES = ("piap", "errors", "ports")

# Nomes exatos congelados pelo Master; jamais reprovados pela regra de prefixo.
IDENTIFICADORES_CONGELADOS = frozenset(
    {
        "PREDICTIVELY_INACCESSIBLE",
        "CLAIM_EVALUATION_RESULT",
        "MAX_CLAIMS_PER_EVALUATION",
    }
)

# Persistência própria e exclusiva de E5.l, materializada no Patch 3.
ALLOWLIST_PERSISTENCIA_E5 = frozenset(
    {
        "reconfiguration.py",
        "repositories/reconfiguration_repository.py",
    }
)

MODULOS_E4_PROIBIDOS = ("app.memory", "app.cognitive")

SDK_DE_PROVIDER = (
    "anthropic",
    "openai",
    "cohere",
    "mistralai",
    "litellm",
    "boto3",
    "botocore",
    "google.generativeai",
    "vertexai",
    "transformers",
)

REDE = ("requests", "httpx", "aiohttp", "socket", "urllib", "http.client", "websockets")

PROCESSO_FILA_SCHEDULER = (
    "queue",
    "asyncio.queues",
    "subprocess",
    "multiprocessing",
    "celery",
    "apscheduler",
    "rq",
    "kombu",
    "redis",
    "sched",
    "signal",
    "pty",
)

PERSISTENCIA_E_API = (
    "sqlalchemy",
    "alembic",
    "psycopg",
    "asyncpg",
    "fastapi",
    "starlette",
    "uvicorn",
    "pydantic",
)

# Verbos de efeito material. `post` foi deliberadamente EXCLUÍDO: casaria
# `__post_init__`, que é protocolo de dataclass e não efeito externo.
VERBOS_DE_EFEITO = frozenset(
    {
        "dispatch",
        "publish",
        "notify",
        "alert",
        "broadcast",
        "evacuate",
        "mobilize",
        "escalate",
        "enqueue",
        "spawn",
    }
)

# Conector e adaptador de capacidade material pertencem à E8.
TOKENS_DE_CAPACIDADE_MATERIAL = frozenset({"connector", "adapter", "gateway", "driver"})

# Escrita e remoção de arquivo: efeito externo, qualquer que seja a biblioteca.
CHAMADAS_DE_ESCRITA_EM_ARQUIVO = frozenset(
    {
        "write_text",
        "write_bytes",
        "touch",
        "unlink",
        "mkdir",
        "rmdir",
        "symlink_to",
        "hardlink_to",
        "chmod",
    }
)

# `rename` e `replace` sao AMBIGUOS: `str.replace` e legitimo e a camada o usa
# em `_instante`. So contam como escrita quando o arquivo importa um modulo de
# sistema de arquivos — sem ele nao existe objeto de caminho.
#
#     AMBIGUOUS_METHOD_NAME != FILESYSTEM_CAPABILITY
CHAMADAS_DE_ESCRITA_AMBIGUAS = frozenset({"rename", "replace"})
MODULOS_DE_SISTEMA_DE_ARQUIVOS = ("pathlib", "os", "shutil", "tempfile", "io")

# Execução externa por COMBINAÇÃO semântica: um verbo de execução com um alvo
# externo. `search_executed` é campo histórico legítimo da porta de leitura
# governada — tem "executed", não tem alvo externo, e não pode ser atingido.
#
#     TOKEN_ISOLADO != CAPACIDADE
VERBOS_DE_EXECUCAO = frozenset({"execute", "exec", "run", "invoke", "perform", "launch"})
ALVOS_EXTERNOS = frozenset({"external", "remote", "shell", "command", "process", "system"})

VERBOS_DE_SELECAO = frozenset({"select", "choose", "pick", "resolve", "route"})
ALVOS_DE_SELECAO = frozenset({"provider", "agent", "vendor"})

TOKENS_DE_HANDOFF = frozenset({"handoff", "relay"})
TOKENS_DE_BENCHMARK = frozenset({"benchmark"})

SUFIXOS_DE_ESCRITA = ("Repository", "Manager", "Writer", "Session", "Engine")


# --- descoberta dinâmica ---------------------------------------------------


def _fontes() -> list[pathlib.Path]:
    """Toda fonte Python da camada, descoberta por varredura recursiva.

    Sem lista fixa: um módulo autorizado dos Patches 3 e 4 é analisado assim
    que existir, e não reprova apenas por existir.
    """
    return sorted(p for p in PACOTE.rglob("*.py") if "__pycache__" not in p.parts)


def _relativo(caminho: pathlib.Path) -> str:
    return str(caminho.relative_to(PACOTE)).replace("\\", "/")


def _arvore(caminho: pathlib.Path) -> ast.Module:
    return ast.parse(caminho.read_text(encoding="utf-8"))


def _tokens(nome: str) -> list[str]:
    """Quebra um identificador em tokens minúsculos.

    Separa por `_` e `-` e por fronteira CamelCase, tratando siglas: `COUT_PIA`
    vira `["cout", "pia"]` e `COUT_PScore` vira `["cout", "p", "score"]`.
    """
    saida: list[str] = []
    for parte in re.split(r"[_\-]+", nome):
        saida.extend(
            t.lower() for t in re.findall(r"[A-Z]+(?![a-z])|[A-Z][a-z]*|[a-z]+|\d+", parte)
        )
    return saida


def _e_cout_p(nome: str) -> bool:
    tokens = _tokens(nome)
    if "coutp" in tokens:
        return True
    return any(a == "cout" and b == "p" for a, b in zip(tokens, tokens[1:], strict=False))


def _identificadores(caminho: pathlib.Path) -> set[tuple[str, str]]:
    """Todo identificador de runtime do arquivo, por espécie.

    Cobre módulo, classe, função, método, argumento, parâmetro, variável,
    constante, atributo, alias de import e nome de argumento nomeado em
    chamada. Docstring e comentário NÃO entram: não são símbolos de runtime.
    """
    achados: set[tuple[str, str]] = set()
    for no in ast.walk(_arvore(caminho)):
        if isinstance(no, ast.ClassDef):
            achados.add(("classe", no.name))
        elif isinstance(no, ast.FunctionDef | ast.AsyncFunctionDef):
            achados.add(("funcao", no.name))
            argumentos = no.args
            for arg in [*argumentos.posonlyargs, *argumentos.args, *argumentos.kwonlyargs]:
                achados.add(("argumento", arg.arg))
            for extra in (argumentos.vararg, argumentos.kwarg):
                if extra is not None:
                    achados.add(("argumento", extra.arg))
        elif isinstance(no, ast.Assign):
            for alvo in no.targets:
                for sub in ast.walk(alvo):
                    if isinstance(sub, ast.Name):
                        achados.add(("variavel", sub.id))
                    elif isinstance(sub, ast.Attribute):
                        achados.add(("atributo", sub.attr))
        elif isinstance(no, ast.AnnAssign | ast.AugAssign):
            alvo = no.target
            if isinstance(alvo, ast.Name):
                achados.add(("variavel", alvo.id))
            elif isinstance(alvo, ast.Attribute):
                achados.add(("atributo", alvo.attr))
        elif isinstance(no, ast.alias):
            achados.add(("alias", (no.asname or no.name).split(".")[-1]))
        elif isinstance(no, ast.keyword) and no.arg is not None:
            achados.add(("argumento", no.arg))
        elif isinstance(no, ast.Name) and isinstance(no.ctx, ast.Store):
            achados.add(("variavel", no.id))
        elif (
            isinstance(no, ast.ExceptHandler | ast.MatchAs | ast.MatchStar) and no.name is not None
        ):
            achados.add(("variavel", no.name))
        elif isinstance(no, ast.MatchMapping) and no.rest is not None:
            achados.add(("variavel", no.rest))
        elif isinstance(no, ast.Global | ast.Nonlocal):
            achados.update(("variavel", nome) for nome in no.names)
        elif isinstance(no, ast.comprehension):
            for sub in ast.walk(no.target):
                if isinstance(sub, ast.Name):
                    achados.add(("variavel", sub.id))
    return achados


def _identificadores_da_camada() -> list[tuple[str, str, str]]:
    """`(arquivo, especie, nome)` para toda a camada, incluindo nomes de módulo."""
    saida: list[tuple[str, str, str]] = []
    for caminho in _fontes():
        rel = _relativo(caminho)
        saida.append((rel, "modulo", caminho.stem))
        for parte in caminho.relative_to(PACOTE).parts[:-1]:
            saida.append((rel, "pacote", parte))
        saida.extend((rel, especie, nome) for especie, nome in _identificadores(caminho))
    return saida


def _modulos_importados(caminho: pathlib.Path) -> set[str]:
    modulos: set[str] = set()
    for no in ast.walk(_arvore(caminho)):
        if isinstance(no, ast.Import):
            modulos.update(alias.name for alias in no.names)
        elif isinstance(no, ast.ImportFrom) and no.module is not None:
            modulos.add(no.module)
    return modulos


def _nomes_chamados(caminho: pathlib.Path) -> set[str]:
    """Nome final de cada chamada: `a.b.c(...)` devolve `c`."""
    chamados: set[str] = set()
    for no in ast.walk(_arvore(caminho)):
        if not isinstance(no, ast.Call):
            continue
        alvo = no.func
        if isinstance(alvo, ast.Name):
            chamados.add(alvo.id)
        elif isinstance(alvo, ast.Attribute):
            chamados.add(alvo.attr)
    return chamados


def _prefixado(modulo: str, prefixos: tuple[str, ...]) -> bool:
    return any(modulo == p or modulo.startswith(f"{p}.") for p in prefixos)


# --- nomenclatura ----------------------------------------------------------


def test_b01_nomenclatura_cout_p_ausente_em_todo_identificador_de_runtime() -> None:
    """`COUT-P` é nome documental; em runtime, nenhuma grafia é admitida."""
    achados = [
        (arquivo, especie, nome)
        for arquivo, especie, nome in _identificadores_da_camada()
        if _e_cout_p(nome)
    ]
    assert achados == [], achados


def test_b02_nomenclatura_cout_p_ausente_em_nome_de_modulo_e_pacote() -> None:
    for caminho in _fontes():
        rel = _relativo(caminho)
        for parte in caminho.relative_to(PACOTE).parts:
            assert not _e_cout_p(parte), f"{rel}: {parte}"


def test_b03_inaccessible_sem_qualificacao_ausente_na_camada() -> None:
    """`INACCESSIBLE` nu é semântica de memória da E3/E4, não da E5."""
    achados = [
        (arquivo, especie, nome)
        for arquivo, especie, nome in _identificadores_da_camada()
        if _tokens(nome) == ["inaccessible"]
    ]
    assert achados == [], achados


def test_b04_conflict_sem_qualificacao_ausente_na_camada() -> None:
    """Conflito entre alegações é `PredictiveClaimConflict`, nunca `Conflict`.

    A baseline já usa `Conflict` com três significados de identidade
    (`SyncConflict`, `ValidatedExperienceConflictError`, `ConflictException`),
    nenhum deles conflito entre alegações preditivas.
    """
    achados = []
    for arquivo, especie, nome in _identificadores_da_camada():
        tokens = _tokens(nome)
        if not tokens or tokens[-1] != "conflict":
            continue
        if "predictive" in tokens and "claim" in tokens:
            continue
        achados.append((arquivo, especie, nome))
    assert achados == [], achados


def test_b05_componente_cientifico_publico_novo_usa_prefixo_predictive() -> None:
    """Fora de `piap`, `errors` e `ports`, tipo e função pública são `Predictive`.

    Identificador congelado pelo Master não é renomeado por esta regra, e ela
    não alcança constantes nem estados.
    """
    achados = []
    for caminho in _fontes():
        primeira = caminho.relative_to(PACOTE).parts[0]
        if primeira in SUBPACOTES_PROTOCOLARES or caminho.name == "__init__.py":
            continue
        for no in _arvore(caminho).body:
            if not isinstance(no, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            nome = no.name
            if nome.startswith("_") or nome in IDENTIFICADORES_CONGELADOS:
                continue
            if nome.startswith("Predictive") or nome.startswith("predictive_"):
                continue
            achados.append((_relativo(caminho), nome))
    assert achados == [], achados


# --- fronteira com a E4 ----------------------------------------------------


def test_b06_fronteira_e4_nenhum_import_de_app_memory_ou_app_cognitive() -> None:
    """A integração é estrutural por `GovernedReadPort`; composição fica fora."""
    for caminho in _fontes():
        for modulo in _modulos_importados(caminho):
            assert not _prefixado(modulo, MODULOS_E4_PROIBIDOS), f"{_relativo(caminho)}: {modulo}"


def test_b07_fronteira_e4_nenhum_writer_repository_manager_orm_ou_migration() -> None:
    for caminho in _fontes():
        rel = _relativo(caminho)
        if rel in ALLOWLIST_PERSISTENCIA_E5:
            continue
        for modulo in _modulos_importados(caminho):
            assert not _prefixado(modulo, PERSISTENCIA_E_API), f"{rel}: {modulo}"
        for no in ast.walk(_arvore(caminho)):
            if isinstance(no, ast.ClassDef):
                assert not no.name.endswith(SUFIXOS_DE_ESCRITA), f"{rel}: {no.name}"
                bases = {ast.unparse(b) for b in no.bases}
                assert not any("Base" in b or "Model" in b for b in bases), f"{rel}: {no.name}"
    assert not [p for p in PACOTE.rglob("*migration*")]
    repositorios = {_relativo(p) for p in PACOTE.rglob("*repository.py") if p.is_file()}
    assert repositorios == {"repositories/reconfiguration_repository.py"}


def test_b08_fronteira_e4_allowlist_de_persistencia_da_e5_e_exata() -> None:
    """Somente E5.l pode persistir; E3/E4 continuam fora da fronteira."""
    assert {
        "reconfiguration.py",
        "repositories/reconfiguration_repository.py",
    } == ALLOWLIST_PERSISTENCIA_E5
    assert isinstance(ALLOWLIST_PERSISTENCIA_E5, frozenset)


# --- owners E6–E9 ----------------------------------------------------------


def test_b09_owner_e6_e9_nenhum_import_de_sdk_rede_processo_fila_ou_scheduler() -> None:
    proibidos = SDK_DE_PROVIDER + REDE + PROCESSO_FILA_SCHEDULER
    for caminho in _fontes():
        for modulo in _modulos_importados(caminho):
            assert not _prefixado(modulo, proibidos), f"{_relativo(caminho)}: {modulo}"


def test_b10_owner_e6_e9_nenhuma_selecao_de_provider_ou_agent() -> None:
    """Seleção de provedor e de agente pertence à E7."""
    achados = []
    for arquivo, especie, nome in _identificadores_da_camada():
        tokens = set(_tokens(nome))
        if tokens & VERBOS_DE_SELECAO and tokens & ALVOS_DE_SELECAO:
            achados.append((arquivo, especie, nome))
    for caminho in _fontes():
        for chamado in _nomes_chamados(caminho):
            tokens = set(_tokens(chamado))
            if tokens & VERBOS_DE_SELECAO and tokens & ALVOS_DE_SELECAO:
                achados.append((_relativo(caminho), "chamada", chamado))
    assert achados == [], achados


def test_b11_owner_e6_e9_nenhum_efeito_material_definido_ou_chamado() -> None:
    """Alerta, dispatch, publish, evacuação e mobilização pertencem à E8."""
    achados = []
    for arquivo, especie, nome in _identificadores_da_camada():
        if nome.startswith("__") and nome.endswith("__"):
            continue
        if set(_tokens(nome)) & VERBOS_DE_EFEITO:
            achados.append((arquivo, especie, nome))
    for caminho in _fontes():
        for chamado in _nomes_chamados(caminho):
            if chamado.startswith("__") and chamado.endswith("__"):
                continue
            if set(_tokens(chamado)) & VERBOS_DE_EFEITO:
                achados.append((_relativo(caminho), "chamada", chamado))
    assert achados == [], achados


def test_b11b_owner_e6_e9_nenhum_conector_ou_adaptador_material() -> None:
    """Conector e adaptador de capacidade material pertencem à E8."""
    achados = [
        (arquivo, especie, nome)
        for arquivo, especie, nome in _identificadores_da_camada()
        if set(_tokens(nome)) & TOKENS_DE_CAPACIDADE_MATERIAL
    ]
    assert achados == [], achados


def test_b11c_owner_e6_e9_nenhuma_escrita_ou_remocao_de_arquivo() -> None:
    """`write_text`, `unlink` e irmãos são efeito externo, venham de onde vierem."""
    achados = []
    for caminho in _fontes():
        importa_fs = any(
            _prefixado(m, MODULOS_DE_SISTEMA_DE_ARQUIVOS) for m in _modulos_importados(caminho)
        )
        proibidas = CHAMADAS_DE_ESCRITA_EM_ARQUIVO | (
            CHAMADAS_DE_ESCRITA_AMBIGUAS if importa_fs else frozenset()
        )
        for chamado in _nomes_chamados(caminho):
            if chamado in proibidas:
                achados.append((_relativo(caminho), "chamada", chamado))
    assert achados == [], achados


def test_b11d_owner_e6_e9_nenhuma_execucao_externa_por_combinacao_semantica() -> None:
    """Verbo de execução MAIS alvo externo. Um token isolado não é capacidade.

    `search_executed`, campo histórico de `GovernedReadPort`, tem `executed` e
    nenhum alvo externo — e continua legítimo. `test_b99` fixa os dois lados.
    """
    achados = []
    for arquivo, especie, nome in _identificadores_da_camada():
        tokens = set(_tokens(nome))
        if tokens & VERBOS_DE_EXECUCAO and tokens & ALVOS_EXTERNOS:
            achados.append((arquivo, especie, nome))
    for caminho in _fontes():
        for chamado in _nomes_chamados(caminho):
            tokens = set(_tokens(chamado))
            if tokens & VERBOS_DE_EXECUCAO and tokens & ALVOS_EXTERNOS:
                achados.append((_relativo(caminho), "chamada", chamado))
    assert achados == [], achados


def test_b12_owner_e6_e9_nenhum_envelope_de_handoff_multi_ia() -> None:
    achados = [
        (arquivo, especie, nome)
        for arquivo, especie, nome in _identificadores_da_camada()
        if set(_tokens(nome)) & TOKENS_DE_HANDOFF
    ]
    assert achados == [], achados


def test_b13_owner_e6_e9_nenhuma_alegacao_de_benchmark_independente() -> None:
    """Benchmark independente é da E9; a E5 não o representa em runtime."""
    achados = [
        (arquivo, especie, nome)
        for arquivo, especie, nome in _identificadores_da_camada()
        if set(_tokens(nome)) & TOKENS_DE_BENCHMARK
    ]
    assert achados == [], achados


def test_b14_owner_e6_e9_nenhum_efeito_externo_por_builtin() -> None:
    """Chamada NUA de builtin de efeito, e caminho pontuado de processo.

    `re.compile` é chamada de atributo e legítima; `compile(...)` nu não é. A
    distinção é sintática e vem do AST, não de busca por substring.

    ```text
    ATTRIBUTE_CALL != BARE_BUILTIN_CALL
    ```
    """
    nus_proibidos = {"open", "exec", "eval", "compile", "__import__", "input"}
    pontuados_proibidos = {"os.system", "os.popen", "os.execv", "os.fork", "os.spawnl"}
    for caminho in _fontes():
        rel = _relativo(caminho)
        for no in ast.walk(_arvore(caminho)):
            if not isinstance(no, ast.Call):
                continue
            if isinstance(no.func, ast.Name):
                assert no.func.id not in nus_proibidos, f"{rel}: {no.func.id}"
            elif isinstance(no.func, ast.Attribute):
                completo = ast.unparse(no.func)
                assert completo not in pontuados_proibidos, f"{rel}: {completo}"


# --- migrations ------------------------------------------------------------


def _literal(no: ast.expr) -> str | None:
    return no.value if isinstance(no, ast.Constant) and isinstance(no.value, str) else None


def _nomes_de_tabela_e_coluna() -> list[tuple[str, str, str]]:
    """`(arquivo, especie, nome)` extraídos por AST das chamadas de migration.

    Só o primeiro argumento posicional de `create_table`, `rename_table`,
    `drop_table`, `add_column`, `Column`, `create_index` e `drop_index` é lido.
    Nenhuma string solta entra: o literal `"inaccessible"` que a E3 usa dentro
    de `sa.Enum` é valor de enum, não nome de coluna, e continua legítimo.

    ```text
    SEMANTIC_AST_EXTRACTION != NAIVE_TEXT_SEARCH
    ```
    """
    achados: list[tuple[str, str, str]] = []
    if not MIGRACOES.is_dir():
        return achados
    for arquivo in sorted(MIGRACOES.glob("*.py")):
        for no in ast.walk(ast.parse(arquivo.read_text(encoding="utf-8"))):
            if not isinstance(no, ast.Call) or not no.args:
                continue
            alvo = ast.unparse(no.func)
            if alvo.endswith(("create_table", "rename_table", "drop_table", "add_column")):
                valor = _literal(no.args[0])
                if valor is not None:
                    achados.append((arquivo.name, "tabela", valor))
            elif alvo.endswith("Column"):
                valor = _literal(no.args[0])
                if valor is not None:
                    achados.append((arquivo.name, "coluna", valor))
            elif alvo.endswith(("create_index", "drop_index")) and len(no.args) >= 2:
                valor = _literal(no.args[1])
                if valor is not None:
                    achados.append((arquivo.name, "tabela", valor))
    return achados


def test_b15_migration_nenhum_nome_de_tabela_ou_coluna_com_cout_p() -> None:
    achados = [
        (arquivo, especie, nome)
        for arquivo, especie, nome in _nomes_de_tabela_e_coluna()
        if _e_cout_p(nome)
    ]
    assert achados == [], achados


def test_b16_migration_extrai_nomes_de_verdade_e_nao_texto_solto() -> None:
    """Controle do extrator: ele precisa achar algo, e não pode achar tudo.

    Um extrator que devolve lista vazia passaria em `b15` por vacuidade.
    """
    achados = _nomes_de_tabela_e_coluna()
    tabelas = {nome for _, especie, nome in achados if especie == "tabela"}
    colunas = {nome for _, especie, nome in achados if especie == "coluna"}
    assert "cognitive_objects" in tabelas
    assert "coid" in colunas
    assert "inaccessible" not in tabelas | colunas


# --- descoberta ------------------------------------------------------------


def test_b17_descoberta_e_dinamica_e_cobre_os_arquivos_da_e5_a() -> None:
    """A varredura não usa lista fixa, mas tem de conter o que já existe."""
    encontrados = {_relativo(p) for p in _fontes()}
    congelados = {
        "__init__.py",
        "piap/__init__.py",
        "piap/capacity.py",
        "piap/enums.py",
        "piap/envelope.py",
        "piap/authority.py",
        "piap/version.py",
        "ports/__init__.py",
        "ports/governed_read.py",
        "errors/__init__.py",
        "errors/codes.py",
        "errors/exceptions.py",
    }
    assert congelados <= encontrados, congelados - encontrados


def test_b18_todo_arquivo_da_camada_e_utf8_estrito_e_analisavel() -> None:
    for caminho in _fontes():
        ast.parse(caminho.read_bytes().decode("utf-8"))


# --- mutantes do instrumento ----------------------------------------------
#
# Cada um demonstra que o mecanismo correspondente consegue reprovar.
#
#     GUARD_WITHOUT_MUTANT = UNVERIFIED_GUARD


def _fonte_temporaria(tmp_path: pathlib.Path, conteudo: str) -> pathlib.Path:
    caminho = tmp_path / "mutante.py"
    caminho.write_text(conteudo, encoding="utf-8")
    return caminho


def test_b99_tokenizacao_separa_cout_p_de_cout_pia() -> None:
    assert _e_cout_p("COUT_P_SCORE")
    assert _e_cout_p("coutp_score")
    assert _e_cout_p("cout_p_engine")
    assert _e_cout_p("COUT-P_valor")
    assert _e_cout_p("COUT_PScore")
    assert _e_cout_p("CoutP")
    assert not _e_cout_p("COUT_PIA")
    assert not _e_cout_p("EDR_COUT_PIA_E3")
    assert not _e_cout_p("predictive_accessibility")


def test_b99_mecanismo_alcanca_variavel_parametro_e_atributo(
    tmp_path: pathlib.Path,
) -> None:
    """O buraco medido na E5.a: nome que não é classe nem função."""
    caminho = _fonte_temporaria(
        tmp_path,
        "COUT_P_SCORE = 0\n\n\ndef f(coutp_score: int) -> None:\n    obj.cout_p_attr = 1\n",
    )
    nomes = {nome for _, nome in _identificadores(caminho)}
    assert "COUT_P_SCORE" in nomes
    assert "coutp_score" in nomes
    assert "cout_p_attr" in nomes


def test_b99_mecanismo_de_inaccessible_reprova(tmp_path: pathlib.Path) -> None:
    caminho = _fonte_temporaria(tmp_path, 'INACCESSIBLE = "x"\n')
    nomes = {nome for _, nome in _identificadores(caminho)}
    assert any(_tokens(n) == ["inaccessible"] for n in nomes)
    assert not any(_tokens(n) == ["inaccessible"] for n in {"PREDICTIVELY_INACCESSIBLE"})


def test_b99_mecanismo_de_conflict_reprova_e_aceita_o_qualificado() -> None:
    def nu(nome: str) -> bool:
        tokens = _tokens(nome)
        if not tokens or tokens[-1] != "conflict":
            return False
        return not {"predictive", "claim"} <= set(tokens)

    assert nu("Conflict")
    assert nu("SyncConflict")
    assert not nu("PredictiveClaimConflict")


def test_b99_mecanismo_de_import_detecta_fronteira(tmp_path: pathlib.Path) -> None:
    caminho = _fonte_temporaria(
        tmp_path, "import requests\nimport anthropic\nfrom app.memory.ports import retrieval\n"
    )
    modulos = _modulos_importados(caminho)
    assert _prefixado("requests", REDE)
    assert any(_prefixado(m, SDK_DE_PROVIDER) for m in modulos)
    assert any(_prefixado(m, MODULOS_E4_PROIBIDOS) for m in modulos)


def test_b99_mecanismo_de_efeito_e_selecao_reprova(tmp_path: pathlib.Path) -> None:
    caminho = _fonte_temporaria(
        tmp_path,
        "def select_provider(n):\n    return n\n\n\ndef dispatch_alert(m):\n    return None\n",
    )
    nomes = {nome for _, nome in _identificadores(caminho)}
    assert any(
        set(_tokens(n)) & VERBOS_DE_SELECAO and set(_tokens(n)) & ALVOS_DE_SELECAO for n in nomes
    )
    assert any(set(_tokens(n)) & VERBOS_DE_EFEITO for n in nomes)


def test_b99_mecanismo_de_efeito_nao_reprova_dunder() -> None:
    """`__post_init__` é protocolo de dataclass, não efeito externo."""
    assert "post" not in VERBOS_DE_EFEITO


def test_b99_mecanismo_de_migration_reprova_por_ast(tmp_path: pathlib.Path) -> None:
    caminho = tmp_path / "mut.py"
    caminho.write_text(
        "import sqlalchemy as sa\nfrom alembic import op\n\n\n"
        "def upgrade():\n"
        '    op.create_table("cout_p_scores", sa.Column("COUT-P_valor", sa.String()))\n',
        encoding="utf-8",
    )
    nomes = []
    for no in ast.walk(ast.parse(caminho.read_text(encoding="utf-8"))):
        if isinstance(no, ast.Call) and no.args:
            alvo = ast.unparse(no.func)
            if alvo.endswith(("create_table", "Column")):
                valor = _literal(no.args[0])
                if valor is not None:
                    nomes.append(valor)
    assert nomes and all(_e_cout_p(n) for n in nomes)


def test_b99_mecanismo_alcanca_todo_binding_de_store(tmp_path: pathlib.Path) -> None:
    """`B1` da auditoria: `for X in ():` liga `X` sem `Assign`.

    A versão rejeitada cobria só alvos de `Assign`, `AnnAssign` e `AugAssign`.
    Isto não é ofuscação: é sintaxe Python comum.
    """
    caminho = _fonte_temporaria(
        tmp_path,
        "for COUT_P_SCORE in ():\n    pass\n"
        "with open('x') as cout_p_ctx:\n    pass\n"
        "[cout_p_comp for cout_p_comp in ()]\n",
    )
    nomes = {nome for _, nome in _identificadores(caminho)}
    assert "COUT_P_SCORE" in nomes
    assert "cout_p_ctx" in nomes
    assert "cout_p_comp" in nomes


def test_b99_mecanismo_alcanca_binding_sem_ast_name(tmp_path: pathlib.Path) -> None:
    """`except ... as X`, `match` e `global` ligam nomes sem produzir `ast.Name`."""
    caminho = _fonte_temporaria(
        tmp_path,
        "try:\n    pass\nexcept ValueError as cout_p_erro:\n    pass\n"
        "def f(v):\n    match v:\n        case [*cout_p_estrela]:\n            pass\n"
        "        case {'k': 1, **cout_p_resto}:\n            pass\n"
        "        case _ as cout_p_como:\n            pass\n"
        "def g():\n    global cout_p_global\n",
    )
    nomes = {nome for _, nome in _identificadores(caminho)}
    for esperado in (
        "cout_p_erro",
        "cout_p_estrela",
        "cout_p_resto",
        "cout_p_como",
        "cout_p_global",
    ):
        assert esperado in nomes, esperado


def test_b99_mecanismo_bloqueia_a_fila_padrao() -> None:
    assert _prefixado("queue", PROCESSO_FILA_SCHEDULER)
    assert _prefixado("queue.Queue", PROCESSO_FILA_SCHEDULER)
    assert not _prefixado("queueing_theory", PROCESSO_FILA_SCHEDULER)


def test_b99_mecanismo_reprova_conector_e_adaptador() -> None:
    assert set(_tokens("PredictiveMaterialAdapter")) & TOKENS_DE_CAPACIDADE_MATERIAL
    assert set(_tokens("predictive_connector")) & TOKENS_DE_CAPACIDADE_MATERIAL
    assert not set(_tokens("PredictiveClaim")) & TOKENS_DE_CAPACIDADE_MATERIAL


def test_b99_mecanismo_reprova_escrita_em_arquivo(tmp_path: pathlib.Path) -> None:
    """Inequívocos sempre; `rename` e `replace` só com módulo de FS importado."""
    caminho = _fonte_temporaria(
        tmp_path,
        "import pathlib\n\n\ndef f(p):\n    p.write_text('x')\n    p.unlink()\n    p.rename('y')\n",
    )
    chamados = _nomes_chamados(caminho)
    assert chamados & CHAMADAS_DE_ESCRITA_EM_ARQUIVO
    assert chamados & CHAMADAS_DE_ESCRITA_AMBIGUAS
    assert any(_prefixado(m, MODULOS_DE_SISTEMA_DE_ARQUIVOS) for m in _modulos_importados(caminho))

    sem_fs = _fonte_temporaria(tmp_path, "def g(s):\n    return s.replace('a', 'b')\n")
    assert not any(
        _prefixado(m, MODULOS_DE_SISTEMA_DE_ARQUIVOS) for m in _modulos_importados(sem_fs)
    )


def test_b99_mecanismo_de_execucao_externa_nao_atinge_search_executed() -> None:
    """Os DOIS lados: a combinação reprova, o campo histórico não."""

    def externo(nome: str) -> bool:
        tokens = set(_tokens(nome))
        return bool(tokens & VERBOS_DE_EXECUCAO and tokens & ALVOS_EXTERNOS)

    assert externo("predictive_execute_external")
    assert externo("run_shell_command")
    assert not externo("search_executed")
    assert not externo("execution_horizon")


def test_b99_descoberta_encontra_arquivo_novo(tmp_path: pathlib.Path) -> None:
    """Substitui o mutante de 'arquivo extra': agora extra é descoberto, não proibido."""
    (tmp_path / "sub").mkdir()
    (tmp_path / "predictive_claim.py").write_text("class PredictiveClaim:\n    pass\n", "utf-8")
    (tmp_path / "sub" / "outro.py").write_text("VALOR = 1\n", encoding="utf-8")
    encontrados = {
        str(p.relative_to(tmp_path)).replace("\\", "/")
        for p in tmp_path.rglob("*.py")
        if "__pycache__" not in p.parts
    }
    assert encontrados == {"predictive_claim.py", "sub/outro.py"}
