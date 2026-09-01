"""
Guardas estáticas do gate final da Entrega 4 (`E4.12`).

```text
PRODUCTION_DELTA = NONE
MIGRATION_DELTA  = NONE
LEARNING_ENGINE_IMPLEMENTED = NO
```

A E4.12 é gate de **integração**: ela não escreve produção nem
migration, e a maior parte destas guardas mede exatamente isso — que o
que a fatia acrescenta são provas, não capacidades.

Cada guarda tem um mutante `m99_*` que aplica **a mesma lógica** a uma
entrada sintética defeituosa. Guarda sem mutante é guarda cuja falha
ninguém verificou.
"""

import ast
import io
import json
import pathlib
import re
import shutil
import subprocess
import tokenize

import pytest

BACKEND = pathlib.Path(__file__).resolve().parents[2]
APP = BACKEND / "app"
REPO = BACKEND.parent
DOCS = BACKEND / "docs" / "entregas" / "entrega-4"

CENARIO = BACKEND / "tests" / "integration" / "memory" / "test_e4_12_final_integration_gate.py"

# ----------------------------------------------------------------------
# Freeze efetivo da E3
# ----------------------------------------------------------------------

E3_COMMIT_ORIGINAL = "014455f93bf7433232a945062e2024d536f7a004"
E3_TREE_ORIGINAL = "f32780bc37c45bc495aed000898354a7d71c8b1b"
E3_COMMIT_EFETIVO = "b4e61a4702a4428dd1dea7464efe09a180bf797c"
E3_TREE_EFETIVA = "be407b46f679a009e0f7f7e9f01fb784f08dea54"

DELTA_AUTORIZADO_E3: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "M",
        "100644",
        "f76a4557eabb0658c9f947c85f899d513d6689ba",
        "15fb8a93b217bc5f728509032fd586072b6a8c28",
        "backend/app/cognitive/errors/__init__.py",
    ),
    (
        "M",
        "100644",
        "d1339811f05443277a0594fda0922cf3c4471da6",
        "64f261ebf69960f68099a1fcd10c71b74dfcc9b7",
        "backend/app/cognitive/errors/codes.py",
    ),
    (
        "M",
        "100644",
        "8a2040b461417b05af89e3681f2e5758a5cff203",
        "2f115b15a3311c5d5bf8d5c0cb25b796d38aa31a",
        "backend/app/cognitive/errors/exceptions.py",
    ),
    (
        "A",
        "100644",
        "0" * 40,
        "d979327fd0dae8857bcb730588c0e7c0a080f940",
        "backend/app/cognitive/schemas/multi_input_transformation.py",
    ),
    (
        "A",
        "100644",
        "0" * 40,
        "4ce8df39209ab0829392dad28e636a49d77550f7",
        "backend/app/cognitive/services/multi_input_transformation_manager.py",
    ),
)
"""O delta autorizado E3.4.2 + E3.4.2.1 — caminho, status, modo e blobs.

```text
INSERTION_STATS != PATH_STATUS
```

Três arquivos foram **modificados** e dois **adicionados**. Uma leitura
que se apoiasse em "0 remoções" concluiria, erradamente, que nada
pré-existente foi tocado — e uma guarda por estatística aceitaria
qualquer conteúdo novo com o mesmo número de linhas.
"""


GIT = shutil.which("git") or "/usr/bin/git"
"""Caminho ABSOLUTO do executável.

Resolver o caminho é o que dispensa a supressão de lint: um comando por
nome depende do `PATH` de quem executa, e a guarda passaria a medir o
ambiente em vez do repositório.
"""


def _git(*argumentos: str) -> str:
    return subprocess.run(
        [GIT, "-C", str(REPO), *argumentos],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def _cadeia_dsvh_canonica() -> bool:
    """`True` só quando o repositório contém os commits congelados da cadeia DSVH.

    As guardas `m01`–`m06`, `m14*` e o mutante `m99_2_1` afirmam sobre a
    **identidade git** da fatia E4.12 — SHAs de commit, hashes de tree e
    fronteiras da cadeia canônica. Um repositório reconstruído por squash
    (o handoff ao desenvolvedor) preserva o CONTEÚDO da fatia, mas não os
    commits originais, então esses meta-testes de história não são
    aplicáveis fora da cadeia canônica. O restante do gate — varreduras de
    AST sobre a produção e os demais mutantes — continua valendo.
    """
    # Ancestralidade, não mera existência do objeto: um commit congelado pode
    # estar presente no object store (p.ex. trazido por um bundle/fetch) sem
    # fazer parte da história do HEAD. A fatia só é canônica se o freeze
    # efetivo da E3 for ANCESTRAL do HEAD. `merge-base --is-ancestor` devolve
    # 0 para ancestral, 1 para não-ancestral e outro código quando o commit
    # não existe ou o diretório não é um repositório git — todos tratados como
    # "fora da cadeia canônica".
    try:
        resultado = subprocess.run(
            [GIT, "-C", str(REPO), "merge-base", "--is-ancestor", E3_COMMIT_EFETIVO, "HEAD"],
            capture_output=True,
        )
    except OSError:
        # git ausente (p.ex. o container de teste não o instala): não há como
        # ser a cadeia canônica, então os meta-testes de história não se aplicam.
        return False
    return resultado.returncode == 0


fora_da_cadeia_canonica = pytest.mark.skipif(
    not _cadeia_dsvh_canonica(),
    reason=(
        "repositório não é a cadeia DSVH canônica (commits E3 congelados ausentes); "
        "meta-teste de história git da fatia E4.12 não aplicável"
    ),
)


def _delta_da_e3(de: str, para: str) -> tuple[tuple[str, str, str, str, str], ...]:
    """Delta de `backend/app/cognitive`, por caminho, status, modo e blob.

    `git diff --raw` devolve modos e blobs abreviados dos dois lados —
    é a leitura que compara **conteúdo identificado**, não contagem.
    """
    # `--no-abbrev` devolve os blobs COMPLETOS de 40 caracteres.
    # Blobs abreviados podem colidir e comparam menos do que parecem —
    # `ABBREVIATED_BLOB != FULL_BLOB`.
    bruto = _git("diff", "--raw", "--no-abbrev", de, para, "--", "backend/app/cognitive")
    entradas: list[tuple[str, str, str, str, str]] = []
    for linha in bruto.splitlines():
        if not linha.startswith(":"):
            continue
        campos, caminho = linha.split("\t", 1)
        modo_antigo, modo_novo, blob_antigo, blob_novo, status = campos[1:].split()
        modo = modo_novo if modo_novo != "000000" else modo_antigo
        entradas.append((status, modo, blob_antigo, blob_novo, caminho))
    return tuple(sorted(entradas, key=lambda item: item[4]))


@fora_da_cadeia_canonica
def test_m01_a_e3_sofreu_exatamente_o_delta_autorizado():
    """`E3_ORIGINAL_DELTA = ONLY_AUTHORIZED_E3_4_2_AND_E3_4_2_1`.

    A E3 foi **explicitamente reaberta** para dois corretivos. Comparar
    cegamente com a árvore original reportaria o corretivo autorizado
    como regressão; ignorar o original perderia a prova de que só ele
    entrou. A guarda usa os dois lados.
    """
    assert _delta_da_e3(E3_COMMIT_ORIGINAL, E3_COMMIT_EFETIVO) == tuple(
        sorted(DELTA_AUTORIZADO_E3, key=lambda item: item[4])
    )


@fora_da_cadeia_canonica
def test_m02_a_e3_nao_mudou_depois_do_freeze_efetivo():
    """`E3_AFTER_EFFECTIVE_FREEZE_MODIFIED = NO`.

    Igualdade de **árvore git**: um único byte alterado em qualquer
    arquivo sob `app/cognitive` produziria outro hash.
    """
    assert _git("rev-parse", f"{E3_COMMIT_EFETIVO}:backend/app/cognitive") == E3_TREE_EFETIVA
    assert _git("rev-parse", "HEAD:backend/app/cognitive") == E3_TREE_EFETIVA
    assert _delta_da_e3(E3_COMMIT_EFETIVO, "HEAD") == ()


MIGRATIONS_E3_ESPERADAS = 13
"""Quantas migrations Python existem no commit original da E3.

Constante de PREMISSA, não lista: se o número mudar, a guarda falha e
alguém precisa olhar. O CONJUNTO é derivado do repositório.
"""


def _artefatos_originais_da_e3() -> dict[str, tuple[str, str]]:
    """Todo artefato de `alembic/versions` no commit original da E3.

    ```text
    PARTIAL_HARDCODED_LIST != COMPLETE_FREEZE
    ```

    CORRIGIDO NO CORRETIVO FINAL. A versão anterior nomeava **cinco**
    arquivos à mão, de treze que existem — protegia o que alguém lembrou
    de escrever e deixava oito livres.

    O conjunto passa a ser DERIVADO por `git ls-tree -r` no commit
    original, com modo e blob de cada entrada. Nada é digitado.

    Devolve `caminho -> (modo, blob)`.
    """
    bruto = _git("ls-tree", "-r", E3_COMMIT_ORIGINAL, "backend/alembic/versions")
    encontrados: dict[str, tuple[str, str]] = {}
    for linha in bruto.splitlines():
        if not linha.strip():
            continue
        metadados, caminho = linha.split("\t", 1)
        modo, tipo, blob = metadados.split()
        if tipo != "blob":
            continue
        encontrados[caminho] = (modo, blob)
    return encontrados


def _artefato_no_head(caminho: str) -> tuple[str, str] | None:
    """Modo e blob do mesmo caminho no HEAD, ou `None` se sumiu."""
    bruto = _git("ls-tree", "HEAD", caminho)
    if not bruto.strip():
        return None
    metadados, _ = bruto.split("\t", 1)
    modo, _tipo, blob = metadados.split()
    return (modo, blob)


@fora_da_cadeia_canonica
def test_m02_1_toda_migration_original_da_e3_esta_intacta():
    """`FROZEN_E3_MIGRATIONS_UNCHANGED`, por caminho, modo e blob completo.

    Migrations NOVAS da E4 são esperadas e não são alteração da E3 — a
    guarda percorre os artefatos ORIGINAIS, não a pasta atual.
    """
    originais = _artefatos_originais_da_e3()
    divergentes: list[str] = []
    for caminho, (modo, blob) in sorted(originais.items()):
        atual = _artefato_no_head(caminho)
        if atual is None:
            divergentes.append(f"{caminho}: REMOVIDO")
        elif atual != (modo, blob):
            divergentes.append(f"{caminho}: {modo}/{blob} -> {atual[0]}/{atual[1]}")
    assert divergentes == []


@fora_da_cadeia_canonica
def test_m02_2_a_derivacao_encontra_as_treze_migrations_e_o_gitkeep():
    """Guarda de PREMISSA: sem ela, `m02_1` passaria sobre um conjunto vazio.

    Treze migrations Python mais o `.gitkeep` — catorze artefatos.
    """
    originais = _artefatos_originais_da_e3()
    python = [c for c in originais if c.endswith(".py")]
    assert len(python) == MIGRATIONS_E3_ESPERADAS, sorted(python)
    assert any(c.endswith(".gitkeep") for c in originais)
    assert len(originais) == MIGRATIONS_E3_ESPERADAS + 1
    for modo, blob in originais.values():
        assert modo == "100644"
        assert len(blob) == 40, "blob abreviado compara menos do que parece"


@fora_da_cadeia_canonica
def test_m02_3_migrations_posteriores_sao_permitidas():
    """Acrescentar migration da E4 não é alterar a E3.

    A guarda mede os artefatos originais; o HEAD tem mais arquivos, e
    isso é o esperado.
    """
    originais = set(_artefatos_originais_da_e3())
    atuais = {
        linha.split("\t", 1)[1]
        for linha in _git("ls-tree", "-r", "HEAD", "backend/alembic/versions").splitlines()
        if linha.strip()
    }
    assert originais <= atuais
    assert len(atuais) > len(originais)


@fora_da_cadeia_canonica
def test_m99_2_1_a_guarda_de_migrations_detecta_uma_lista_incompleta():
    """Mutante: retirar uma migration da lista deixa de detectar a alteração.

    Aplica a MESMA lógica de `m02_1` a um conjunto ao qual falta um
    caminho — e o caminho ausente passa despercebido, que é exatamente o
    defeito da lista parcial.
    """
    originais = _artefatos_originais_da_e3()
    alvo = sorted(c for c in originais if c.endswith(".py"))[0]

    def _divergentes(conjunto: dict[str, tuple[str, str]]) -> list[str]:
        # Simula o alvo adulterado no HEAD.
        return [
            caminho
            for caminho, valor in conjunto.items()
            if caminho == alvo and valor == ("100644", "d" * 40)
        ]

    adulterado = dict(originais)
    adulterado[alvo] = ("100644", "d" * 40)
    assert _divergentes(adulterado) == [alvo]
    incompleta_adulterada = {c: v for c, v in adulterado.items() if c != alvo}
    assert _divergentes(incompleta_adulterada) == []


@fora_da_cadeia_canonica
def test_m03_a_arvore_original_da_e3_e_diferente_e_isso_e_esperado():
    """Guarda de premissa: sem ela, `m01` passaria por coincidência.

    Se as duas árvores fossem iguais, o delta autorizado seria vazio e
    `m01` estaria medindo nada.
    """
    assert _git("rev-parse", f"{E3_COMMIT_ORIGINAL}:backend/app/cognitive") == E3_TREE_ORIGINAL
    assert E3_TREE_ORIGINAL != E3_TREE_EFETIVA


def test_m99_1_a_guarda_da_e3_detecta_blob_alterado():
    """Mutante: mesmo caminho, mesmo status, blob diferente."""
    esperado = tuple(sorted(DELTA_AUTORIZADO_E3, key=lambda item: item[4]))
    mutante = tuple(
        (status, modo, antigo, "d" * 40 if caminho.endswith("codes.py") else novo, caminho)
        for status, modo, antigo, novo, caminho in esperado
    )
    assert mutante != esperado


def test_m99_2_a_guarda_da_e3_detecta_status_trocado():
    """Mutante: `M` apresentado como `A` — a distinção que eu errei."""
    esperado = tuple(sorted(DELTA_AUTORIZADO_E3, key=lambda item: item[4]))
    mutante = tuple(
        ("A" if caminho.endswith("codes.py") else status, modo, antigo, novo, caminho)
        for status, modo, antigo, novo, caminho in esperado
    )
    assert mutante != esperado


# ----------------------------------------------------------------------
# Zero delta em produção e migrations
# ----------------------------------------------------------------------

PARENT_CADEIA_96 = "5eeab210627ae631bc2e58237fc5268dc663a93d"

E4_12_FINAL_COMMIT = "340443aa96da16824b624ff767ea24cf1e019daf"
"""Fim da fatia E4.12, fixado.

A fatia é um intervalo **histórico** e fechado:

```text
E4_12_DELTA = PARENT_CHAIN96..E4_12_FINAL_COMMIT
E4_12_DELTA != PARENT_CHAIN96..CURRENT_HEAD
```

A versão anterior destas guardas comparava com `HEAD`. Enquanto `HEAD` era o
próprio commit da E4.12, ou um descendente apenas documental, a diferença não
aparecia. A partir do momento em que a E5 acrescentou produção autorizada, a
mesma asserção passou a proibir permanentemente qualquer entrega futura — e
uma prova sobre o passado virou uma proibição sobre o futuro.

```text
HISTORICAL_SLICE_ASSERTION_AGAINST_HEAD = DEFECTIVE_INSTRUMENT
```

Vale registrar por que o defeito demorou a aparecer: os gates da cadeia 99
foram executados **antes** do commit, como o processo manda, e naquele instante
os arquivos novos ainda estavam untracked — `git diff <parent> HEAD` não os via.
A guarda passou por um motivo alheio à sua intenção.

```text
GIT_BASED_GUARD_BEFORE_COMMIT != GIT_BASED_GUARD_AFTER_COMMIT
```
"""

E4_12_PARENT_APP_TREE = "7b5ce7c4737da8e2ce8bad0fac0ba946f9d7ef64"
E4_12_FINAL_APP_TREE = "7b5ce7c4737da8e2ce8bad0fac0ba946f9d7ef64"
E4_12_PARENT_ALEMBIC_TREE = "eb5216dfc69f3eafe0b4073fe848ff8636614691"
E4_12_FINAL_ALEMBIC_TREE = "eb5216dfc69f3eafe0b4073fe848ff8636614691"
"""Árvores fixas dos dois lados da fatia.

Fixá-las é o que impede que a prova continue passando por acidente se algum dia
os dois extremos do intervalo forem trocados por outra coisa.
"""


def _arquivos_alterados(de: str, para: str, prefixo: str) -> tuple[str, ...]:
    """Diferença entre DOIS commits explícitos, nunca contra `HEAD` implícito.

    Nenhum helper que pretenda medir uma fatia histórica pode escolher o lado
    direito sozinho.
    """
    bruto = _git("diff", "--name-only", de, para, "--", prefixo)
    return tuple(sorted(linha for linha in bruto.splitlines() if linha))


@fora_da_cadeia_canonica
def test_m04_producao_tem_delta_zero():
    """`PRODUCTION_DELTA = NONE` — `backend/app/` byte a byte igual NA FATIA."""
    assert _arquivos_alterados(PARENT_CADEIA_96, E4_12_FINAL_COMMIT, "backend/app") == ()
    assert _git("rev-parse", f"{PARENT_CADEIA_96}:backend/app") == _git(
        "rev-parse", f"{E4_12_FINAL_COMMIT}:backend/app"
    )


@fora_da_cadeia_canonica
def test_m05_migrations_tem_delta_zero():
    """`MIGRATION_DELTA = NONE` na fatia E4.12.

    Não percorre `alembic/versions` da worktree corrente: aquele diretório
    descreve o estado ATUAL do repositório, não o histórico da E4.12, e usá-lo
    aqui repetiria o defeito de `HEAD` por outro caminho. A cabeça global
    vigente continua verificada pelo gate `alembic heads`, fora desta prova.

    ```text
    CURRENT_WORKTREE_STATE != HISTORICAL_SLICE_STATE
    ```
    """
    assert _arquivos_alterados(PARENT_CADEIA_96, E4_12_FINAL_COMMIT, "backend/alembic") == ()
    assert _git("rev-parse", f"{PARENT_CADEIA_96}:backend/alembic") == _git(
        "rev-parse", f"{E4_12_FINAL_COMMIT}:backend/alembic"
    )


@fora_da_cadeia_canonica
def test_m06_o_delta_da_fatia_e_apenas_teste_e_documentacao():
    """A E4.12 acrescenta provas, não capacidades."""
    alterados = _arquivos_alterados(PARENT_CADEIA_96, E4_12_FINAL_COMMIT, "backend")
    assert alterados, "a fatia precisa alterar alguma coisa"
    for caminho in alterados:
        assert caminho.startswith(
            ("backend/tests/", "backend/docs/", "backend/README_BACKEND.md")
        ), caminho


# --- premissas da fatia, agora explícitas ------------------------------


@fora_da_cadeia_canonica
def test_m04_1_o_commit_final_e_filho_direto_do_parent_da_cadeia_96():
    """Sem isto, o intervalo poderia pular commits e a prova não seria da fatia."""
    assert _git("rev-parse", f"{E4_12_FINAL_COMMIT}^") == PARENT_CADEIA_96


@fora_da_cadeia_canonica
def test_m04_2_as_arvores_de_producao_da_fatia_sao_as_fixadas():
    assert _git("rev-parse", f"{PARENT_CADEIA_96}:backend/app") == E4_12_PARENT_APP_TREE
    assert _git("rev-parse", f"{E4_12_FINAL_COMMIT}:backend/app") == E4_12_FINAL_APP_TREE


@fora_da_cadeia_canonica
def test_m05_1_as_arvores_de_migration_da_fatia_sao_as_fixadas():
    assert _git("rev-parse", f"{PARENT_CADEIA_96}:backend/alembic") == E4_12_PARENT_ALEMBIC_TREE
    assert _git("rev-parse", f"{E4_12_FINAL_COMMIT}:backend/alembic") == E4_12_FINAL_ALEMBIC_TREE


@fora_da_cadeia_canonica
def test_m04_3_existe_producao_posterior_a_fatia_e_por_isso_head_nao_a_representa():
    """A razão do corretivo, provada e não apenas afirmada.

    Se um dia esta asserção falhar, é porque não há mais produção depois da
    E4.12 — e aí o corretivo teria virado inócuo sem ninguém perceber.
    """
    posteriores = _arquivos_alterados(E4_12_FINAL_COMMIT, "HEAD", "backend/app")
    assert posteriores, "a cadeia corrente deveria conter produção posterior à E4.12"
    assert _arquivos_alterados(PARENT_CADEIA_96, "HEAD", "backend/app") != ()
    assert _arquivos_alterados(PARENT_CADEIA_96, E4_12_FINAL_COMMIT, "backend/app") == ()


@fora_da_cadeia_canonica
def test_m04_4_o_helper_bilateral_detecta_producao_num_intervalo_que_a_contenha():
    """O instrumento consegue acusar — não é uma guarda que só sabe passar."""
    contendo_producao = _arquivos_alterados(PARENT_CADEIA_96, "HEAD", "backend/app")
    assert any(c.startswith("backend/app/") for c in contendo_producao)
    infratores = [
        c
        for c in _arquivos_alterados(PARENT_CADEIA_96, "HEAD", "backend")
        if not c.startswith(("backend/tests/", "backend/docs/", "backend/README_BACKEND.md"))
    ]
    assert infratores, "um intervalo que contém produção precisa ser acusado pelo helper"


FUNCOES_DA_FATIA_HISTORICA = (
    "_arquivos_alterados",
    "test_m04_producao_tem_delta_zero",
    "test_m05_migrations_tem_delta_zero",
    "test_m06_o_delta_da_fatia_e_apenas_teste_e_documentacao",
    "test_m14_nenhum_cout_p_ou_predictive_accessibility_implementado",
)
"""As que provam a FATIA. Nenhuma delas pode olhar para `HEAD`.

`test_m04_3_*` e `test_m04_4_*` usam `HEAD` de propósito — provam que existe
produção depois da fatia — e por isso ficam fora desta lista.
"""


def _funcoes_deste_arquivo() -> dict[str, ast.FunctionDef]:
    arvore = ast.parse(pathlib.Path(__file__).read_text(encoding="utf-8"))
    return {no.name: no for no in ast.walk(arvore) if isinstance(no, ast.FunctionDef)}


def test_m99_8_nenhuma_guarda_da_fatia_referencia_head():
    """Prova ESTRUTURAL de que o defeito não pode voltar em silêncio.

    Duas das guardas corrigidas — `m05` e `m14` — passam hoje mesmo se alguém
    devolver `HEAD` ao lugar do commit fixo: a E5.a não criou migration, e não
    nomeou nenhuma definição com o vocabulário proibido. Uma prova puramente
    comportamental não distingue os dois casos, e um mutante que troca o commit
    por `HEAD` sobreviveria — foi o que aconteceu na primeira execução dos
    mutantes deste corretivo.

    ```text
    BEHAVIOURALLY_EQUIVALENT_TODAY != CORRECT_INSTRUMENT
    LATENT_DEFECT_THAT_PASSES = STILL_A_DEFECT
    ```

    A guarda olha para a própria árvore sintática: nenhuma função da fatia
    histórica pode conter a constante `"HEAD"`.
    """
    funcoes = _funcoes_deste_arquivo()
    infratores: list[str] = []
    for nome in FUNCOES_DA_FATIA_HISTORICA:
        assert nome in funcoes, nome
        for no in ast.walk(funcoes[nome]):
            if isinstance(no, ast.Constant) and no.value == "HEAD":
                infratores.append(nome)
            if isinstance(no, ast.JoinedStr) and "HEAD" in ast.unparse(no):
                infratores.append(nome)
    assert infratores == []


def test_m99_9_m14_le_a_arvore_congelada_e_nao_a_worktree():
    """`m14` não pode chamar o helper que lê a worktree.

    Mesmo motivo do teste anterior: hoje as duas leituras dariam o mesmo
    resultado, porque a E5.a evitou o vocabulário proibido de propósito. A
    diferença é de instrumento, não de resultado, e só a AST a enxerga.
    """
    m14 = _funcoes_deste_arquivo()[
        "test_m14_nenhum_cout_p_ou_predictive_accessibility_implementado"
    ]
    chamadas = {
        no.func.id
        for no in ast.walk(m14)
        if isinstance(no, ast.Call) and isinstance(no.func, ast.Name)
    }
    assert "_fontes_de_producao" not in chamadas
    assert "_fontes_de_producao_no_commit" in chamadas


def test_m99_10_o_mecanismo_de_deteccao_de_head_consegue_acusar():
    """Mutante do próprio mecanismo: uma função que usa `HEAD` é acusada."""
    fonte = 'def g():\n    return _git("diff", "--name-only", A, "HEAD")\n'
    alvo = next(no for no in ast.walk(ast.parse(fonte)) if isinstance(no, ast.FunctionDef))
    achou = any(isinstance(no, ast.Constant) and no.value == "HEAD" for no in ast.walk(alvo))
    assert achou


def test_m99_3_a_guarda_de_delta_detecta_um_arquivo_de_producao():
    fingido = ("backend/tests/x.py", "backend/app/memory/models/y.py")
    infratores = [
        c
        for c in fingido
        if not c.startswith(("backend/tests/", "backend/docs/", "backend/README_BACKEND.md"))
    ]
    assert infratores == ["backend/app/memory/models/y.py"]


# ----------------------------------------------------------------------
# Nenhuma policy altera existência
# ----------------------------------------------------------------------

MUTACOES = frozenset({"add", "delete", "merge", "execute", "commit", "flush"})
RECEPTORES = frozenset({"session", "sessao", "uow", "db", "conn", "connection"})

SERVICOS_DE_POLICY = (
    "governance_manager.py",
    "accessibility_policy_manager.py",
    "retention_evaluator.py",
    "compliance_evaluator.py",
)


def _mutacoes_de_persistencia(arvore: ast.Module) -> set[str]:
    """Escritas de persistência, distinguidas pelo **receptor**.

    ```text
    SET_ADD != SESSION_ADD
    ```
    """
    encontradas: set[str] = set()
    for no in ast.walk(arvore):
        if not isinstance(no, ast.Call) or not isinstance(no.func, ast.Attribute):
            continue
        if no.func.attr not in MUTACOES:
            continue
        receptor = no.func.value
        alvo = receptor.attr if isinstance(receptor, ast.Attribute) else getattr(receptor, "id", "")
        if alvo.lower() in RECEPTORES:
            encontradas.add(f"{alvo}.{no.func.attr}")
    return encontradas


def test_m07_nenhum_servico_de_policy_escreve_no_patrimonio():
    """`POLICY_CAN_ALTER_EXISTENCE = NO`, medido por AST.

    Governança, acessibilidade, retenção e conformidade **decidem** e
    **descrevem**; a escrita pertence a quem tem autoridade material, e
    nenhum destes tem.
    """
    infratores: list[str] = []
    for nome in SERVICOS_DE_POLICY:
        caminho = APP / "memory" / "services" / nome
        achados = _mutacoes_de_persistencia(ast.parse(caminho.read_text(encoding="utf-8")))
        infratores.extend(f"{nome}:{achado}" for achado in sorted(achados))
    assert infratores == []


def test_m08_nenhum_servico_de_policy_toca_o_patrimonio_da_e3():
    """Nenhum deles importa repositório de objeto cognitivo."""
    proibidos = ("app.cognitive.repositories", "app.cognitive.models")
    for nome in SERVICOS_DE_POLICY:
        caminho = APP / "memory" / "services" / nome
        arvore = ast.parse(caminho.read_text(encoding="utf-8"))
        for no in ast.walk(arvore):
            if isinstance(no, ast.ImportFrom) and no.module:
                assert not no.module.startswith(proibidos), f"{nome}: {no.module}"


def test_m99_4_a_guarda_de_escrita_detecta_session_add():
    escreve = "def f(session):\n    session.add(x)\n"
    acumula = "def f():\n    vistos = set()\n    vistos.add(1)\n"
    assert _mutacoes_de_persistencia(ast.parse(escreve)) == {"session.add"}
    assert _mutacoes_de_persistencia(ast.parse(acumula)) == set()


# ----------------------------------------------------------------------
# Nenhum learning engine, nenhum consumidor comportamental
# ----------------------------------------------------------------------

FRONTEIRA_E4_11 = {
    "memory/models/validated_experience_enums.py",
    "memory/models/validated_experience.py",
    "memory/models/__init__.py",
    "memory/schemas/validated_experience.py",
    "memory/repositories/validated_experience_repository.py",
}

SIMBOLOS_E4_11 = ("ValidatedExperience", "ValidatedExperienceRepository")


def _fontes_de_producao() -> list[pathlib.Path]:
    return [p for p in sorted(APP.rglob("*.py")) if "__pycache__" not in p.parts]


def _consumo_comportamental(arvore: ast.Module, simbolos: tuple[str, ...]) -> set[str]:
    """Chamadas e ramificações — `IMPORT != BEHAVIOR`."""
    procurados = frozenset(simbolos)
    encontrados: set[str] = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Call):
            alvo = no.func
            nome = alvo.attr if isinstance(alvo, ast.Attribute) else getattr(alvo, "id", None)
            if nome in procurados:
                encontrados.add(f"call:{nome}")
        elif isinstance(no, ast.If):
            usados = {f.id for f in ast.walk(no.test) if isinstance(f, ast.Name)}
            encontrados |= {f"if:{s}" for s in usados & procurados}
    return encontrados


def test_m09_nenhum_consumidor_comportamental_de_validated_experience():
    """`BEHAVIORAL_CONSUMERS_OUTSIDE_BOUNDARY = 0`.

    ```text
    IF REMOVING THE RECORD CHANGES SYSTEM BEHAVIOR
    THEN IT IS A LEARNING ENGINE
    ```
    """
    infratores: list[str] = []
    for caminho in _fontes_de_producao():
        relativo = str(caminho.relative_to(APP))
        if relativo in FRONTEIRA_E4_11:
            continue
        achados = _consumo_comportamental(
            ast.parse(caminho.read_text(encoding="utf-8")), SIMBOLOS_E4_11
        )
        infratores.extend(f"{relativo}:{a}" for a in sorted(achados))
    assert infratores == []


def test_m10_nenhum_termo_de_aprendizado_em_producao():
    """`LEARNING_ENGINE_IMPLEMENTED = NO`, em toda a árvore de produção."""
    proibidos = {
        "fit",
        "train",
        "predict",
        "embedding",
        "gradient",
        "backprop",
        "reinforce",
    }
    infratores: list[str] = []
    for caminho in _fontes_de_producao():
        arvore = ast.parse(caminho.read_text(encoding="utf-8"))
        for no in ast.walk(arvore):
            definicao = isinstance(no, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
            if definicao and no.name.lower() in proibidos:
                infratores.append(f"{caminho.name}:{no.name}")
    assert infratores == []


def test_m99_5_a_guarda_de_consumo_distingue_import_de_chamada():
    apenas_import = "from app.memory.models.validated_experience import ValidatedExperience\n"
    chama = "def f(s):\n    return ValidatedExperienceRepository(s).get(x)\n"
    assert _consumo_comportamental(ast.parse(apenas_import), SIMBOLOS_E4_11) == set()
    assert "call:ValidatedExperienceRepository" in _consumo_comportamental(
        ast.parse(chama), SIMBOLOS_E4_11
    )


# ----------------------------------------------------------------------
# Neutralidade de provider e capacidades proibidas
# ----------------------------------------------------------------------

SDKS_PROIBIDOS = (
    "openai",
    "anthropic",
    "boto3",
    "google.cloud",
    "azure",
    "cohere",
    "huggingface",
    "transformers",
    "langchain",
)


def _importa(arvore: ast.Module) -> set[str]:
    encontrados: set[str] = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.ImportFrom) and no.module:
            encontrados.add(no.module)
        elif isinstance(no, ast.Import):
            encontrados |= {apelido.name for apelido in no.names}
    return encontrados


def test_m11_neutralidade_de_provider_em_toda_a_producao():
    """Nenhum SDK de fornecedor específico é importado."""
    infratores: list[str] = []
    for caminho in _fontes_de_producao():
        modulos = _importa(ast.parse(caminho.read_text(encoding="utf-8")))
        for modulo in modulos:
            if modulo.split(".")[0] in {s.split(".")[0] for s in SDKS_PROIBIDOS}:
                infratores.append(f"{caminho.name}:{modulo}")
    assert infratores == []


def test_m12_nenhum_worker_scheduler_fila_ou_execucao_em_background():
    proibidos = (
        "celery",
        "apscheduler",
        "rq",
        "kombu",
        "dramatiq",
        "huey",
    )
    infratores: list[str] = []
    for caminho in _fontes_de_producao():
        modulos = _importa(ast.parse(caminho.read_text(encoding="utf-8")))
        infratores.extend(f"{caminho.name}:{m}" for m in modulos if m.split(".")[0] in proibidos)
    assert infratores == []


def test_m13_nenhum_adaptador_material_fora_de_testes():
    """`PRODUCTION_EFFECT_ADAPTER = NONE` — corpo vivo, não `Protocol`."""
    infratores: list[str] = []
    for caminho in _fontes_de_producao():
        arvore = ast.parse(caminho.read_text(encoding="utf-8"))
        for no in ast.walk(arvore):
            if not isinstance(no, ast.ClassDef):
                continue
            if any(isinstance(b, ast.Name) and b.id == "Protocol" for b in no.bases):
                continue
            for membro in no.body:
                if not isinstance(membro, ast.FunctionDef | ast.AsyncFunctionDef):
                    continue
                if membro.name not in ("attempt_effect", "resolve_target"):
                    continue
                corpo = [
                    linha
                    for linha in membro.body
                    if not (isinstance(linha, ast.Expr) and isinstance(linha.value, ast.Constant))
                ]
                if corpo:
                    infratores.append(f"{caminho.name}:{no.name}.{membro.name}")
    assert infratores == []


def _fontes_de_producao_no_commit(commit: str) -> list[tuple[str, str]]:
    """Fontes Python de `backend/app` **naquele commit**, lidas por Git.

    Deliberadamente separado de `_fontes_de_producao`, que lê a worktree e
    serve às guardas cujo invariante é sobre o estado atual. Reaproveitar aquele
    helper aqui reescoparia `m09`–`m13` sem autorização.
    """
    listagem = _git("ls-tree", "-r", "--name-only", commit, "--", "backend/app")
    caminhos = [linha for linha in listagem.splitlines() if linha.endswith(".py")]
    return [(caminho, _git("show", f"{commit}:{caminho}")) for caminho in caminhos]


@fora_da_cadeia_canonica
def test_m14_nenhum_cout_p_ou_predictive_accessibility_implementado():
    """Candidato exclusivo da E5; nada dele podia nascer NA FATIA E4.12.

    Esta é uma afirmação **temporal** sobre o fechamento da E4.12, não uma
    proibição perpétua. A E5 foi autorizada e iniciada depois, e varrer a
    produção de um `HEAD` futuro mediria a coisa errada mesmo quando passasse
    por coincidência nominal.

    ```text
    E5_CAPABILITY_AT_E4_12_FINAL_COMMIT = ABSENT
    E5_CAPABILITY_AFTER_AUTHORIZED_E5_START = ALLOWED
    ```

    O vocabulário proibido e a força da afirmação permanecem os mesmos; o que
    muda é o alvo, que passa a ser a árvore congelada.
    """
    proibidos = ("COUTP", "CoutP", "PredictiveAccessibility", "predictive_accessibility")
    infratores: list[str] = []
    for caminho, texto in _fontes_de_producao_no_commit(E4_12_FINAL_COMMIT):
        arvore = ast.parse(texto)
        for no in ast.walk(arvore):
            definicao = isinstance(no, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
            if definicao and any(termo in no.name for termo in proibidos):
                infratores.append(f"{caminho}:{no.name}")
    assert infratores == []


@fora_da_cadeia_canonica
def test_m14_1_a_varredura_historica_le_a_arvore_congelada_e_nao_a_worktree():
    """O alvo de `m14` é o commit da fatia, e as duas árvores já divergem."""
    historicas = {caminho for caminho, _ in _fontes_de_producao_no_commit(E4_12_FINAL_COMMIT)}
    assert historicas
    assert not any("predictive_accessibility" in caminho for caminho in historicas)
    atuais = {f"backend/app/{p.relative_to(APP)}" for p in _fontes_de_producao()}
    assert atuais - historicas, "a worktree atual deveria ter produção que a fatia não tem"


def test_m99_6_a_guarda_de_provider_detecta_um_sdk():
    fonte = "import openai\n"
    modulos = _importa(ast.parse(fonte))
    assert "openai" in {m.split(".")[0] for m in modulos}


def test_m99_7_a_guarda_de_adaptador_distingue_protocolo_de_implementacao():
    protocolo = "class P(Protocol):\n    def attempt_effect(self, r):\n        ...\n"
    adaptador = "class A:\n    def attempt_effect(self, r):\n        return apagar(r)\n"

    def _implementa(fonte: str) -> bool:
        for no in ast.walk(ast.parse(fonte)):
            if not isinstance(no, ast.ClassDef):
                continue
            if any(isinstance(b, ast.Name) and b.id == "Protocol" for b in no.bases):
                continue
            for membro in no.body:
                if isinstance(membro, ast.FunctionDef) and membro.name == "attempt_effect":
                    corpo = [
                        linha
                        for linha in membro.body
                        if not (
                            isinstance(linha, ast.Expr) and isinstance(linha.value, ast.Constant)
                        )
                    ]
                    if corpo:
                        return True
        return False

    assert _implementa(protocolo) is False
    assert _implementa(adaptador) is True


# ----------------------------------------------------------------------
# Manifestos coerentes e alcançáveis
# ----------------------------------------------------------------------

STATUS_FECHADOS = frozenset(
    {
        "IMPLEMENTED",
        "CONTRACT_ONLY",
        "DEFERRED",
        "FORBIDDEN",
        "NOT_APPLICABLE",
        "FUTURE_STOP_CONDITION",
    }
)


def _manifesto() -> dict[str, object]:
    return json.loads((DOCS / "E4_FINAL_MANIFEST.json").read_text(encoding="utf-8"))


def test_m15_o_manifesto_json_e_parseavel_e_fechado():
    dados = _manifesto()
    assert {
        "slices",
        "tables",
        "error_codes",
        "deferred",
        "forbidden_capabilities",
        "doc_roots",
    } <= set(dados)
    for fatia in dados["slices"]:
        assert fatia["status"] in STATUS_FECHADOS, fatia
    for item in dados["deferred"]:
        assert item["status"] in STATUS_FECHADOS, item


def test_m16_1_o_handoff_concorda_com_o_manifesto_sobre_os_deferidos():
    """AMPLIADA NO CORRETIVO FINAL: o handoff também é comparado.

    ```text
    TWO_DOCUMENTS_TWO_TRUTHS = DIVERGENCE
    ```

    O candidato `d5f466ef` classificava COUT-P como `DEFERRED` no
    manifesto e mantinha `FUTURE_STOP_CONDITION` no handoff. Um leitor
    tirava conclusões opostas conforme o arquivo que abrisse.
    """
    dados = _manifesto()
    handoff = (DOCS / "E4_TO_E5_HANDOFF.md").read_text(encoding="utf-8")

    cout = next(item for item in dados["deferred"] if item["id"] == "COUT_P_V1_2")
    assert cout["status"] == "DEFERRED"
    assert re.search(r"STATUS\s*=\s*DEFERRED", handoff)
    # `!=` é marcador de DISTINÇÃO, não atribuição.
    assert re.search(r"(?<![!])=\s*FUTURE_STOP_CONDITION\b", handoff) is None

    # Nenhum diferido é apresentado como pré-condição universal da E5.
    for item in dados["deferred"]:
        if "universal_precondition_for_e5" in item:
            assert item["universal_precondition_for_e5"] is False, item["id"]


def test_m99_8_1_a_guarda_de_handoff_detecta_a_divergencia():
    """Mutante: o handoff que ATRIBUI `FUTURE_STOP_CONDITION`."""
    divergente = "STATUS = FUTURE_STOP_CONDITION\n"
    coerente = "STATUS = DEFERRED\nDEFERRED_CANDIDATE != FUTURE_STOP_CONDITION\n"
    padrao = r"(?<![!])=\s*FUTURE_STOP_CONDITION\b"
    assert re.search(padrao, divergente) is not None
    assert re.search(padrao, coerente) is None


def test_m16_o_manifesto_humano_e_o_json_concordam():
    """Coerência **automática**, não revisão manual.

    Cada fatia e cada diferido do JSON precisa aparecer no manifesto
    humano com o mesmo status — dois documentos que divergem são duas
    verdades sobre a mesma entrega.
    """
    dados = _manifesto()
    humano = (DOCS / "E4_FINAL_MANIFEST.md").read_text(encoding="utf-8")
    for fatia in dados["slices"]:
        assert fatia["id"] in humano, fatia["id"]
        linha = next(
            texto for texto in humano.splitlines() if texto.startswith(f"| `{fatia['id']}`")
        )
        assert fatia["status"] in linha, (fatia["id"], linha)
    for item in dados["deferred"]:
        assert item["id"] in humano, item["id"]


def test_m17_o_manifesto_declara_as_duas_raizes_documentais():
    """`DOC_ROOTS_UNIFIED = NO` — a divergência é histórica e declarada."""
    dados = _manifesto()
    raizes = dados["doc_roots"]
    assert raizes["unified"] is False
    assert "docs/entregas/entrega-4" in raizes["root"]["path"]
    assert "backend/docs/entregas/entrega-4" in raizes["backend"]["path"]


def test_m18_o_manifesto_nao_marca_contrato_como_implementacao():
    """Transporte é contrato entregue **sem** implementação."""
    dados = _manifesto()
    transporte = next(
        item for item in dados["deferred"] if item["id"] == "VALIDATED_EXPERIENCE_TRANSPORT"
    )
    assert transporte["status"] == "DEFERRED"
    # CORRIGIDO NO CORRETIVO (achado A6): `FUTURE_STOP_CONDITION` é
    # reservado ao que PODERIA bloquear a entrega se fosse exigido. Nada
    # na E4 depende de COUT-P, então classificá-lo assim inflaria a lista
    # de bloqueios potenciais com um item que não é um.
    #
    # ```text
    # DEFERRED_CANDIDATE != FUTURE_STOP_CONDITION
    # ```
    cout = next(item for item in dados["deferred"] if item["id"] == "COUT_P_V1_2")
    assert cout["status"] == "DEFERRED"


def test_m19_o_estado_final_nao_declara_pass_final():
    """`PASS_FINAL` pertence ao auditor independente."""
    dados = _manifesto()
    estado = dados["final_state"]
    assert estado["PASS_FINAL"] == "NOT_DECLARED"
    assert estado["READY_FOR_E5"] == "FALSE"
    assert estado["E4_FINAL_FREEZE"] == "PENDING_INDEPENDENT_AUDIT"


@pytest.mark.parametrize(
    "nome",
    [
        "E4_12_FINAL_INTEGRATION_GATE.md",
        "E4_FINAL_MANIFEST.md",
        "E4_FINAL_MANIFEST.json",
        "E4_TO_E5_HANDOFF.md",
    ],
)
def test_m20_os_documentos_finais_existem_e_sao_alcancaveis(nome):
    assert (DOCS / nome).is_file(), nome
    indice = (BACKEND / "README_BACKEND.md").read_text(encoding="utf-8")
    assert f"docs/entregas/entrega-4/{nome}" in indice, nome


def test_m99_8_a_guarda_de_coerencia_detecta_status_divergente():
    """Mutante: o JSON diz `IMPLEMENTED`, o humano diz `DEFERRED`."""
    humano = "| `E4.99` | algo | DEFERRED |"
    fatia = {"id": "E4.99", "status": "IMPLEMENTED"}
    linha = next(texto for texto in humano.splitlines() if texto.startswith(f"| `{fatia['id']}`"))
    assert fatia["status"] not in linha


def test_m99_9_a_guarda_de_status_detecta_vocabulario_aberto():
    assert "QUASE_PRONTO" not in STATUS_FECHADOS


# ----------------------------------------------------------------------
# O próprio cenário integrado
# ----------------------------------------------------------------------


def _supressoes(caminho: pathlib.Path) -> list[int]:
    """Supressões em COMENTÁRIO — `MENTIONED_IN_PROSE != APPLIED`."""
    encontrados: list[int] = []
    with caminho.open("rb") as fonte:
        for token in tokenize.tokenize(io.BytesIO(fonte.read()).readline):
            if token.type == tokenize.COMMENT and (
                "type: ignore" in token.string or "noqa" in token.string
            ):
                encontrados.append(token.start[0])
    return encontrados


def test_m21_o_cenario_usa_postgresql_real_e_apis_publicas():
    """Sem mock do que precisa ser real: o gate mede integração."""
    texto = CENARIO.read_text(encoding="utf-8")
    assert "UnitOfWork" in texto
    for proibido in ("MagicMock", "unittest.mock", "monkeypatch.setattr"):
        assert proibido not in texto, proibido


def test_m22_o_cenario_compara_censo_canonico_e_nao_contagem():
    """`ROW_COUNT != CANONICAL_CENSUS`."""
    arvore = ast.parse(CENARIO.read_text(encoding="utf-8"))
    censos = [
        no for no in ast.walk(arvore) if isinstance(no, ast.FunctionDef) and "censo" in no.name
    ]
    assert censos, "não há função de censo"
    corpo = ast.unparse(censos[0])
    assert "ORDER BY" in corpo
    assert "count(*)" not in corpo, "censo por contagem não detecta valor alterado"


def test_m23_nenhuma_supressao_no_cenario_nem_nas_guardas():
    for caminho in (CENARIO, pathlib.Path(__file__)):
        assert _supressoes(caminho) == [], caminho.name


def test_m99_10_a_guarda_de_censo_detecta_contagem():
    fonte = "def censo():\n    return session.execute('SELECT count(*) FROM t')\n"
    censos = [no for no in ast.walk(ast.parse(fonte)) if isinstance(no, ast.FunctionDef)]
    assert "count(*)" in ast.unparse(censos[0])
