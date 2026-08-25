"""
Guardas estáticas do registro de experiência validada (`E4.11`).

```text
IF REMOVING THE RECORD CHANGES SYSTEM BEHAVIOR
THEN IT IS A LEARNING ENGINE
```

A guarda central desta fatia não é sobre o que o registro **tem**, e sim
sobre o que o resto do sistema **faz** com ele. Medir só imports não
bastaria: model, schema e repository necessariamente importam o
contrato — são a própria fronteira. O que precisa ser zero é o consumo
**comportamental** fora dela.

```text
AUTHORIZED_CONSUMERS = módulos internos da fronteira E4.11
BEHAVIORAL_CONSUMERS_OUTSIDE_BOUNDARY = 0
```

Consumo comportamental é medido por **chamada** e por **ramificação**
(`if`/`match`), não por substring — importar um nome não é ramificar
sobre ele.

Cada guarda tem um mutante `g99_*` que aplica **a mesma lógica** a uma
fonte sintética defeituosa.
"""

import ast
import io
import pathlib
import tokenize

import pytest

APP = pathlib.Path(__file__).resolve().parents[2] / "app"
BACKEND = APP.parent

ENUMS = APP / "memory" / "models" / "validated_experience_enums.py"
SCHEMAS = APP / "memory" / "schemas" / "validated_experience.py"
MODELO = APP / "memory" / "models" / "validated_experience.py"
REPOSITORIO = APP / "memory" / "repositories" / "validated_experience_repository.py"
NOVOS = (ENUMS, SCHEMAS, MODELO, REPOSITORIO)

FRONTEIRA = {
    "memory/models/validated_experience_enums.py",
    "memory/models/validated_experience.py",
    "memory/models/__init__.py",
    "memory/schemas/validated_experience.py",
    "memory/repositories/validated_experience_repository.py",
}
"""Os módulos que **são** a fronteira E4.11.

`memory/models/__init__.py` entra porque reexporta o contrato, e
reexportar é o oposto de consumir: `REEXPORT != CONSUMPTION`.
"""

SIMBOLOS = ("ValidatedExperience", "ValidatedExperienceAppend", "ValidatedExperienceRepository")


def _fontes() -> list[pathlib.Path]:
    return [p for p in sorted(APP.rglob("*.py")) if "__pycache__" not in p.parts]


def _arvore(caminho: pathlib.Path) -> ast.Module:
    return ast.parse(caminho.read_text(encoding="utf-8"))


def _nome_chamado(no: ast.Call) -> str | None:
    alvo = no.func
    if isinstance(alvo, ast.Attribute):
        return alvo.attr
    if isinstance(alvo, ast.Name):
        return alvo.id
    return None


# ----------------------------------------------------------------------
# Lógicas reutilizadas — guarda e mutante usam LITERALMENTE a mesma
# ----------------------------------------------------------------------


def _nomes_carregados(arvore: ast.Module) -> set[str]:
    return {no.id for no in ast.walk(arvore) if isinstance(no, ast.Name)} | {
        no.attr for no in ast.walk(arvore) if isinstance(no, ast.Attribute)
    }


def _consumo_comportamental(arvore: ast.Module, simbolos: tuple[str, ...]) -> set[str]:
    """Chamadas e ramificações sobre os símbolos do registro.

    ```text
    IMPORT != BEHAVIOR
    CALL_OR_BRANCH = BEHAVIOR
    ```

    Uma chamada usa o registro para fazer algo; um `if`/`match` sobre ele
    faz o sistema tomar caminhos diferentes conforme o registro exista ou
    não — que é exatamente a definição operacional de learning engine
    adotada pelo `E4_ARCHITECTURE_FREEZE` §19.
    """
    procurados = frozenset(simbolos)
    encontrados: set[str] = set()

    for no in ast.walk(arvore):
        if isinstance(no, ast.Call) and _nome_chamado(no) in procurados:
            encontrados.add(f"call:{_nome_chamado(no)}")
        elif isinstance(no, ast.If):
            usados = _nomes_carregados(ast.Module(body=[no.test], type_ignores=[]))
            for simbolo in usados & procurados:
                encontrados.add(f"if:{simbolo}")
        elif isinstance(no, ast.Match):
            usados = _nomes_carregados(ast.Module(body=[ast.Expr(no.subject)], type_ignores=[]))
            for simbolo in usados & procurados:
                encontrados.add(f"match:{simbolo}")
    return encontrados


def _termos_de_codigo(arvore: ast.Module, termos: tuple[str, ...]) -> set[str]:
    """Termos usados como CÓDIGO — docstring e comentário não contam."""
    encontrados: set[str] = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Name) and no.id in termos:
            encontrados.add(no.id)
        elif isinstance(no, ast.Attribute) and no.attr in termos:
            encontrados.add(no.attr)
        elif isinstance(no, ast.ImportFrom | ast.Import):
            for apelido in no.names:
                if apelido.name in termos:
                    encontrados.add(apelido.name)
        elif (
            isinstance(no, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
            and no.name in termos
        ):
            encontrados.add(no.name)
    return encontrados


def _importa_de(arvore: ast.Module, prefixos: tuple[str, ...]) -> set[str]:
    encontrados: set[str] = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.ImportFrom) and no.module:
            for prefixo in prefixos:
                if no.module.startswith(prefixo):
                    encontrados.add(no.module)
        elif isinstance(no, ast.Import):
            for apelido in no.names:
                for prefixo in prefixos:
                    if apelido.name.startswith(prefixo):
                        encontrados.add(apelido.name)
    return encontrados


def _supressoes(caminho: pathlib.Path) -> list[int]:
    """Supressões em COMENTÁRIO — `MENTIONED_IN_PROSE != APPLIED`."""
    encontrados: list[int] = []
    with caminho.open("rb") as fonte:
        for token in tokenize.tokenize(io.BytesIO(fonte.read()).readline):
            if token.type != tokenize.COMMENT:
                continue
            if "type: ignore" in token.string or "noqa" in token.string:
                encontrados.append(token.start[0])
    return encontrados


# ----------------------------------------------------------------------
# g01 — nenhum consumo comportamental fora da fronteira
# ----------------------------------------------------------------------


def test_g01_nenhum_consumo_comportamental_fora_da_fronteira():
    """`BEHAVIORAL_CONSUMERS_OUTSIDE_BOUNDARY = 0`.

    A guarda **não** exige zero imports: o modelo, o schema e o
    repositório importam o contrato porque são a fronteira. O que precisa
    ser zero é chamada e ramificação em qualquer outro lugar.
    """
    infratores: list[str] = []
    for caminho in _fontes():
        relativo = str(caminho.relative_to(APP))
        if relativo in FRONTEIRA:
            continue
        achados = _consumo_comportamental(_arvore(caminho), SIMBOLOS)
        infratores.extend(f"{relativo}:{achado}" for achado in sorted(achados))
    assert infratores == []


def test_g01_1_a_fronteira_e_exatamente_a_declarada():
    """Quem importa o contrato é só quem deveria — nem mais, nem menos."""
    importadores = {
        str(caminho.relative_to(APP))
        for caminho in _fontes()
        if _importa_de(_arvore(caminho), ("app.memory.models.validated_experience",))
        or _importa_de(_arvore(caminho), ("app.memory.schemas.validated_experience",))
    }
    assert importadores == FRONTEIRA - {"memory/models/validated_experience_enums.py"}


def test_g99_1_a_guarda_de_consumo_detecta_chamada_e_ramificacao():
    """Mutante bilateral: import passa, chamada e `if` não."""
    apenas_import = "from app.memory.models.validated_experience import ValidatedExperience\n"
    chama = "def f(s):\n    return ValidatedExperienceRepository(s).get(x)\n"
    ramifica = "def f(r):\n    if ValidatedExperience:\n        return 1\n    return 0\n"
    assert _consumo_comportamental(ast.parse(apenas_import), SIMBOLOS) == set()
    assert "call:ValidatedExperienceRepository" in _consumo_comportamental(
        ast.parse(chama), SIMBOLOS
    )
    assert "if:ValidatedExperience" in _consumo_comportamental(ast.parse(ramifica), SIMBOLOS)


# ----------------------------------------------------------------------
# g02 — nenhum motor de aprendizado, seleção ou recomendação
# ----------------------------------------------------------------------


def test_g02_nenhum_termo_de_aprendizado_no_codigo():
    """`ERROR/SUCCESS/REPETITION != AUTOMATIC_LEARNING`."""
    proibidos = (
        "score",
        "confidence",
        "weight",
        "rank",
        "ranking",
        "priority",
        "recommend",
        "recommendation",
        "generalize",
        "learn",
        "train",
        "fit",
        "predict",
        "embedding",
    )
    for caminho in NOVOS:
        assert _termos_de_codigo(_arvore(caminho), proibidos) == set(), caminho.name


def test_g02_1_nenhuma_definicao_sugere_selecao_ou_promocao():
    proibidos = ("select_best", "promote", "rank_", "score_", "learn_", "train_")
    infratores: list[str] = []
    for caminho in NOVOS:
        for no in ast.walk(_arvore(caminho)):
            definicao = isinstance(no, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
            if definicao and any(no.name.lower().startswith(t) for t in proibidos):
                infratores.append(f"{caminho.name}:{no.name}")
    assert infratores == []


def test_g99_2_a_guarda_de_aprendizado_detecta_um_score():
    fonte = "def f():\n    score = 0.9\n    return score\n"
    assert "score" in _termos_de_codigo(ast.parse(fonte), ("score",))


# ----------------------------------------------------------------------
# g03 — nenhuma promoção automática
# ----------------------------------------------------------------------


def test_g03_nenhum_hook_observer_ou_registro_automatico():
    """`NO_AUTOMATIC_PROMOTION` — erro, sucesso, repetição e finding de
    compliance nunca criam registro sozinhos."""
    proibidos = ("event", "listens_for", "listen", "before_insert", "after_insert", "signal")
    for caminho in (SCHEMAS, REPOSITORIO):
        assert _termos_de_codigo(_arvore(caminho), proibidos) == set(), caminho.name


def test_g03_1_a_fronteira_nao_importa_compliance_retencao_nem_apagamento():
    """Nenhum desses módulos pode decidir que uma validação ocorreu."""
    proibidos = (
        "app.memory.schemas.compliance",
        "app.memory.services.compliance_evaluator",
        "app.memory.services.retention_evaluator",
        "app.memory.services.destructive_execution_service",
        "app.memory.schemas.erasure",
        "app.memory.schemas.accessibility",
        "app.memory.services.governance_manager",
    )
    for caminho in NOVOS:
        assert _importa_de(_arvore(caminho), proibidos) == set(), caminho.name


def test_g03_2_a_fronteira_nao_importa_a_e3():
    """`REFERENCE != FOREIGN_KEY` — referenciamos identidade, não modelo."""
    for caminho in NOVOS:
        assert _importa_de(_arvore(caminho), ("app.cognitive",)) == set(), caminho.name


def test_g99_3_a_guarda_de_hook_detecta_um_listener():
    fonte = "from sqlalchemy import event\n@event.listens_for(X, 'after_insert')\ndef f(*a): ...\n"
    assert _termos_de_codigo(ast.parse(fonte), ("event", "listens_for")) >= {"event"}


# ----------------------------------------------------------------------
# g04 — append-only exposto e imposto
# ----------------------------------------------------------------------


def test_g04_o_repositorio_recusa_toda_mutacao():
    """Recusar é medido por `raise` no corpo — não pela ausência do método.

    Um repositório que simplesmente não definisse `update` herdaria o da
    base e permitiria a escrita.
    """
    arvore = _arvore(REPOSITORIO)
    metodos = {
        no.name: no
        for classe in ast.walk(arvore)
        if isinstance(classe, ast.ClassDef)
        for no in classe.body
        if isinstance(no, ast.FunctionDef)
    }
    for alvo in ("update", "delete", "soft_delete", "bulk_update", "bulk_delete"):
        assert alvo in metodos, alvo
        assert any(isinstance(filho, ast.Raise) for filho in ast.walk(metodos[alvo])), alvo


def test_g04_1_a_migration_cria_a_trigger_de_imutabilidade():
    """A terceira camada é do banco, e é medida no SQL da migration."""
    versoes = BACKEND / "alembic" / "versions"
    migracao = next(versoes.glob("e7c25a91f4b3_*.py"))
    texto = migracao.read_text(encoding="utf-8")
    assert "CREATE TRIGGER" in texto
    assert "BEFORE UPDATE OR DELETE" in texto
    assert "validated_experiences" in texto


def test_g04_2_uma_unica_migration_sucessora_e_nenhuma_tabela_extra():
    versoes = BACKEND / "alembic" / "versions"
    grafo: dict[str, str | None] = {}
    tabelas: set[str] = set()
    for caminho in sorted(versoes.glob("*.py")):
        arvore = _arvore(caminho)
        revisao = pai = None
        for no in ast.walk(arvore):
            if isinstance(no, ast.AnnAssign | ast.Assign):
                alvo = no.target if isinstance(no, ast.AnnAssign) else no.targets[0]
                if isinstance(alvo, ast.Name) and isinstance(no.value, ast.Constant):
                    if alvo.id == "revision":
                        revisao = no.value.value
                    elif alvo.id == "down_revision":
                        pai = no.value.value
            if (
                isinstance(no, ast.Call)
                and _nome_chamado(no) == "create_table"
                and no.args
                and isinstance(no.args[0], ast.Constant)
            ):
                tabelas.add(no.args[0].value)
            elif (
                isinstance(no, ast.Call)
                and _nome_chamado(no) == "create_table"
                and caminho.name.startswith("e7c25a91f4b3")
            ):
                tabelas.add("<dinâmica>")
        if revisao:
            grafo[revisao] = pai

    filhos = [rev for rev, pai in grafo.items() if pai == "d5b31f7a08c4"]
    assert filhos == ["e7c25a91f4b3"], filhos
    netos = [rev for rev, pai in grafo.items() if pai == "e7c25a91f4b3"]
    assert netos == ["f8a91c2d4e60"], netos
    bisnetos = [rev for rev, pai in grafo.items() if pai == "f8a91c2d4e60"]
    assert bisnetos == ["b4d71c58ae02"], bisnetos
    pais = {p for p in grafo.values() if p}
    # ATUALIZADO PELA E7.1: folha única passou a ser `a91d3f7c26be`.
    # ATUALIZADO PELO B1a DA E7.4-1 (proteção humana): a folha passou a ser
    # `d7a4c1e93b28`; antes `c58d1e0a94f7` e `b47e9c05d3fa` (kernel de
    # conexões). A guarda mede folha ÚNICA, não imobilidade.
    #
    #     DOCUMENTAÇÃO_DESATUALIZADA = AFIRMAÇÃO_FALSA_NO_REPOSITÓRIO
    assert sorted(r for r in grafo if r not in pais) == ["d7a4c1e93b28"]

    nova = _arvore(next(versoes.glob("e7c25a91f4b3_*.py")))
    criadas = [
        no.args[0].value
        for no in ast.walk(nova)
        if isinstance(no, ast.Call)
        and _nome_chamado(no) == "create_table"
        and no.args
        and isinstance(no.args[0], ast.Constant)
    ]
    assert criadas == [], criadas or "create_table usa constante de módulo"


def test_g04_3_a_migration_nova_nao_altera_tabela_congelada():
    """Nenhum `alter_table`, `drop_column` ou `add_column` fora da própria."""
    versoes = BACKEND / "alembic" / "versions"
    nova = _arvore(next(versoes.glob("e7c25a91f4b3_*.py")))
    proibidas = {"alter_column", "add_column", "drop_column", "rename_table"}
    chamadas = {_nome_chamado(no) for no in ast.walk(nova) if isinstance(no, ast.Call)}
    assert not chamadas & proibidas


def test_g99_4_a_guarda_de_recusa_distingue_ausencia_de_raise():
    """Mutante bilateral: método que levanta passa, método vazio não."""
    recusa = "class R:\n    def update(self, e):\n        raise Erro('x')\n"
    permite = "class R:\n    def update(self, e):\n        return e\n"
    for fonte, esperado in ((recusa, True), (permite, False)):
        metodos = {
            no.name: no
            for classe in ast.walk(ast.parse(fonte))
            if isinstance(classe, ast.ClassDef)
            for no in classe.body
            if isinstance(no, ast.FunctionDef)
        }
        levanta = any(isinstance(f, ast.Raise) for f in ast.walk(metodos["update"]))
        assert levanta is esperado


# ----------------------------------------------------------------------
# g05 — evidência sem conteúdo, localizador ou capability
# ----------------------------------------------------------------------


def test_g05_nenhum_contrato_tem_campo_de_conteudo_ou_localizador():
    """Medido por **schema**: os nomes de campo das dataclasses novas."""
    proibidos = {
        "content",
        "payload",
        "transcript",
        "body",
        "text",
        "locator",
        "url",
        "uri",
        "path",
        "credential",
        "secret",
        "token",
        "capability",
    }
    for no in ast.walk(_arvore(SCHEMAS)):
        if not isinstance(no, ast.ClassDef):
            continue
        campos = {
            membro.target.id
            for membro in no.body
            if isinstance(membro, ast.AnnAssign) and isinstance(membro.target, ast.Name)
        }
        assert not campos & proibidos, f"{no.name}: {campos & proibidos}"


def test_g05_1_a_referencia_de_evidencia_e_uuid_e_nao_texto():
    """`UUID_HAS_NOWHERE_TO_PUT_A_URL` — a garantia é do tipo."""
    anotacoes: dict[str, str] = {}
    for no in ast.walk(_arvore(SCHEMAS)):
        if isinstance(no, ast.ClassDef) and no.name == "EvidenceReference":
            for membro in no.body:
                if isinstance(membro, ast.AnnAssign) and isinstance(membro.target, ast.Name):
                    anotacao = membro.annotation
                    anotacoes[membro.target.id] = (
                        anotacao.attr
                        if isinstance(anotacao, ast.Attribute)
                        else getattr(anotacao, "id", "")
                    )
    assert anotacoes.get("ref") == "UUID"


def test_g05_2_a_origem_nao_persiste_localidade():
    """`ORIGIN_LOCALITY_PERSISTED = NO` — nem no contrato, nem na coluna."""
    proibidos = ("is_local", "local", "locality")
    for caminho in (SCHEMAS, MODELO):
        for no in ast.walk(_arvore(caminho)):
            if isinstance(no, ast.AnnAssign) and isinstance(no.target, ast.Name):
                assert no.target.id not in proibidos, caminho.name


def test_g99_5_a_guarda_de_campo_detecta_um_localizador():
    fonte = "@dataclass\nclass R:\n    url: str\n"
    campos = {
        membro.target.id
        for no in ast.walk(ast.parse(fonte))
        if isinstance(no, ast.ClassDef)
        for membro in no.body
        if isinstance(membro, ast.AnnAssign) and isinstance(membro.target, ast.Name)
    }
    assert "url" in campos


# ----------------------------------------------------------------------
# g06 — sem escapes de tipagem, sem relógio próprio
# ----------------------------------------------------------------------


def test_g06_nenhum_escape_de_tipagem_nos_contratos():
    proibidos = ("Any", "cast", "pickle", "asdict", "__dict__", "setattr")
    for caminho in (ENUMS, SCHEMAS, REPOSITORIO):
        assert _termos_de_codigo(_arvore(caminho), proibidos) == set(), caminho.name


def test_g06_1_a_fronteira_nao_tem_relogio_proprio():
    """Todo instante entra por argumento — nenhum `now()` interno."""
    for caminho in (ENUMS, SCHEMAS, REPOSITORIO):
        chamadas = {
            _nome_chamado(no) for no in ast.walk(_arvore(caminho)) if isinstance(no, ast.Call)
        }
        assert not chamadas & {"now", "utcnow", "today"}, caminho.name


def test_g06_2_nenhuma_supressao_nos_contratos():
    """O modelo tem UMA supressão herdada do precedente `JSONB` da E4.9.6."""
    for caminho in (ENUMS, SCHEMAS):
        assert _supressoes(caminho) == [], caminho.name
    assert len(_supressoes(MODELO)) == 1
    assert len(_supressoes(REPOSITORIO)) == 1


def test_g99_6_a_guarda_de_supressao_distingue_comentario_de_docstring(tmp_path):
    comentario = tmp_path / "com.py"
    comentario.write_text("x = f()  # type: ignore[arg-type]\n", encoding="utf-8")
    prosa = tmp_path / "sem.py"
    prosa.write_text('"""Sem type: ignore aqui."""\nx = 1\n', encoding="utf-8")
    assert _supressoes(comentario) == [1]
    assert _supressoes(prosa) == []


# ----------------------------------------------------------------------
# g07 — o transporte não foi implementado
# ----------------------------------------------------------------------


def test_g07_a_tabela_nao_foi_registrada_no_sync_da_e3():
    """`TRANSPORT_IMPLEMENTED = NO` — e E3 permanece intocada.

    O que viaja é o que está em `SECTION_BY_TABLE`. Registrar a tabela
    ali seria alterar E3 congelada, e a decisão de portabilidade é do
    **contrato**, não do transporte.
    """
    mapa = APP / "cognitive" / "schemas" / "synchronization.py"
    assert "validated_experiences" not in mapa.read_text(encoding="utf-8")


def test_g07_1_a_atribuicao_de_origem_e_obrigatoria_desde_a_primeira_linha():
    """Append-only não permite retrofit: `ORIGIN_UNKNOWN != LOCAL_ORIGIN`."""
    import dataclasses

    from app.memory.schemas.validated_experience import ValidatedExperienceAppend

    definicao = ValidatedExperienceAppend.__dataclass_fields__["origin"]
    assert definicao.default is dataclasses.MISSING
    assert definicao.default_factory is dataclasses.MISSING

    coluna = None
    for no in ast.walk(_arvore(MODELO)):
        if (
            isinstance(no, ast.AnnAssign)
            and isinstance(no.target, ast.Name)
            and no.target.id == "origin_ref"
        ):
            coluna = no
    assert coluna is not None
    assert "nullable=False" in ast.unparse(coluna)


def test_g99_7_a_guarda_de_sync_detecta_o_registro():
    fonte = 'SECTION_BY_TABLE = {"validated_experiences": "experiences"}\n'
    assert "validated_experiences" in fonte


# ----------------------------------------------------------------------
# g08 — a documentação da fatia é alcançável
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "caminho",
    [
        BACKEND / "docs" / "entregas" / "entrega-4" / "E4_11_VALIDATED_EXPERIENCE_REGISTRY.md",
        BACKEND / "README_BACKEND.md",
    ],
)
def test_g08_os_documentos_da_fatia_existem(caminho):
    assert caminho.is_file(), caminho


def test_g08_1_o_documento_e_referenciado_pelo_indice_canonico():
    indice = (BACKEND / "README_BACKEND.md").read_text(encoding="utf-8")
    assert "docs/entregas/entrega-4/E4_11_VALIDATED_EXPERIENCE_REGISTRY.md" in indice


# ----------------------------------------------------------------------
# g09 — o repositório não é dono da transação  (achado A1)
# ----------------------------------------------------------------------


def _controle_transacional(arvore: ast.Module) -> set[str]:
    """Chamadas que assumem a transação do chamador.

    ```text
    SAVEPOINT_SCOPE != TRANSACTION_SCOPE
    ```

    `begin_nested` **não** entra: um SAVEPOINT desfaz só a si mesmo e é
    exatamente a construção que preserva a transação externa. O que é
    proibido é `commit`/`rollback` sobre a sessão.
    """
    encontrados: set[str] = set()
    for no in ast.walk(arvore):
        if not isinstance(no, ast.Call) or not isinstance(no.func, ast.Attribute):
            continue
        if no.func.attr not in ("commit", "rollback"):
            continue
        receptor = no.func.value
        alvo = receptor.attr if isinstance(receptor, ast.Attribute) else getattr(receptor, "id", "")
        encontrados.add(f"{alvo}.{no.func.attr}")
    return encontrados


def test_g09_o_repositorio_nao_commita_nem_desfaz_a_sessao():
    """CORRIGIDO NA AUDITORIA DA CADEIA 96 (achado A1).

    A versão anterior chamava `Session.rollback()` no caminho da corrida
    e desfazia a transação INTEIRA do chamador — inclusive escritas
    anteriores e não relacionadas. O repositório declara que a
    `UnitOfWork` é dona da transação, e o código contradizia o contrato.
    """
    assert _controle_transacional(_arvore(REPOSITORIO)) == set()


def test_g09_1_o_caminho_da_corrida_usa_savepoint():
    """A construção que substitui o rollback integral precisa existir."""
    chamadas = {
        _nome_chamado(no) for no in ast.walk(_arvore(REPOSITORIO)) if isinstance(no, ast.Call)
    }
    assert "begin_nested" in chamadas


def test_g09_2_nem_todo_integrity_error_vira_replay():
    """Violação de outro invariante não pode ser mascarada como replay."""
    fonte = REPOSITORIO.read_text(encoding="utf-8")
    assert "_e_colisao_de_identidade" in fonte
    chamadas = {
        _nome_chamado(no) for no in ast.walk(_arvore(REPOSITORIO)) if isinstance(no, ast.Call)
    }
    assert "_e_colisao_de_identidade" in chamadas


def test_g99_9_a_guarda_transacional_distingue_savepoint_de_rollback():
    """Mutante bilateral: `begin_nested` passa, `rollback` não."""
    savepoint = "def f(self):\n    with self._session.begin_nested():\n        pass\n"
    desfaz = "def f(self):\n    self._session.rollback()\n"
    commita = "def f(self):\n    self._session.commit()\n"
    assert _controle_transacional(ast.parse(savepoint)) == set()
    assert _controle_transacional(ast.parse(desfaz)) == {"_session.rollback"}
    assert _controle_transacional(ast.parse(commita)) == {"_session.commit"}


# ----------------------------------------------------------------------
# g10 — o banco recusa UPDATE, DELETE e TRUNCATE  (achado A2)
# ----------------------------------------------------------------------


def _operacoes_protegidas(texto: str, tabela: str) -> set[str]:
    """Operações cobertas por trigger de recusa, lidas do SQL da migration.

    ```text
    ROW_TRIGGER_DOES_NOT_SEE_TRUNCATE
    ```

    Exige `CREATE TRIGGER`, a cláusula `BEFORE`, a tabela nomeada no
    `ON` e o `FOR EACH` correspondente — `TRUNCATE` só existe em
    `FOR EACH STATEMENT`, e uma trigger de linha nunca o intercepta.
    """
    # A migration usa f-string com constantes de módulo: o nome da tabela
    # aparece como `{_TABELA}`. A guarda resolve as constantes antes de
    # ler o SQL — medir o texto sem resolver as leria como literais e
    # nunca encontraria a tabela.
    resolvido = texto.replace("{_TABELA}", tabela)
    encontrados: set[str] = set()
    for bloco in resolvido.split("CREATE TRIGGER")[1:]:
        cabeca = bloco.split(";")[0]
        if f"ON {tabela}" not in cabeca:
            continue
        antes = cabeca.split("BEFORE", 1)[1].split("ON")[0] if "BEFORE" in cabeca else ""
        for operacao in ("UPDATE", "DELETE", "TRUNCATE"):
            if operacao in antes:
                encontrados.add(operacao)
    return encontrados


def _migracao_da_fatia() -> str:
    versoes = BACKEND / "alembic" / "versions"
    return next(versoes.glob("e7c25a91f4b3_*.py")).read_text(encoding="utf-8")


def test_g10_a_migration_recusa_update_delete_e_truncate():
    """ACRESCENTADO NA AUDITORIA DA CADEIA 96 (achado A2).

    A migration protegia apenas `BEFORE UPDATE OR DELETE ... FOR EACH
    ROW`, e no PostgreSQL isso não intercepta `TRUNCATE` — que apagava a
    tabela append-only inteira sem encontrar recusa.
    """
    assert _operacoes_protegidas(_migracao_da_fatia(), "validated_experiences") == {
        "UPDATE",
        "DELETE",
        "TRUNCATE",
    }


def test_g10_1_o_downgrade_remove_os_dois_gatilhos_antes_da_funcao():
    texto = _migracao_da_fatia()
    corpo = texto.split("def downgrade")[1]
    linha = corpo.index("_TRIGGER_ROW")
    truncate = corpo.index("_TRIGGER_TRUNCATE")
    funcao = corpo.index("DROP FUNCTION IF EXISTS {_FUNCTION_NAME}")
    assert truncate < funcao and linha < funcao


@pytest.mark.parametrize("ausente", ["UPDATE", "DELETE", "TRUNCATE"])
def test_g99_10_a_guarda_de_gatilho_detecta_cada_operacao_faltante(ausente):
    """Mutante por operação: remover qualquer uma quebra a guarda."""
    presentes = [op for op in ("UPDATE", "DELETE", "TRUNCATE") if op != ausente]
    if "TRUNCATE" in presentes:
        presentes.remove("TRUNCATE")
        sql = (
            f"CREATE TRIGGER a BEFORE {' OR '.join(presentes)} ON t FOR EACH ROW E();"
            " CREATE TRIGGER b BEFORE TRUNCATE ON t FOR EACH STATEMENT E();"
        )
    else:
        sql = f"CREATE TRIGGER a BEFORE {' OR '.join(presentes)} ON t FOR EACH ROW E();"
    assert _operacoes_protegidas(sql, "t") != {"UPDATE", "DELETE", "TRUNCATE"}


# ----------------------------------------------------------------------
# g11 — o lastro é validado pelo banco  (achado A3)
# ----------------------------------------------------------------------


INVARIANTES_DO_LASTRO = (
    ("array", "jsonb_typeof(evidencia) <> 'array'"),
    ("nao vazio", "jsonb_array_length(evidencia) = 0"),
    ("elemento objeto", "jsonb_typeof(item) <> 'object'"),
    ("chaves exatas", "jsonb_object_keys(item)) <> 2"),
    ("chaves nomeadas", "item ? 'kind' AND item ? 'ref'"),
    ("vocabulario fechado", "'transformation_record'"),
    ("uuid canonico", "!~"),
    ("ordem estrita", "atual <= anterior"),
    ("primaria no lastro", "achou_primaria"),
)
"""Os nove invariantes que a função SQL precisa impor.

Enumerados literalmente: derivar a lista do próprio SQL faria a guarda
concordar com qualquer coisa que ele passasse a fazer.
"""


def _invariantes_presentes(texto: str) -> set[str]:
    return {nome for nome, agulha in INVARIANTES_DO_LASTRO if agulha in texto}


def test_g11_a_migration_valida_o_lastro_no_banco():
    """`APP_TYPED_BOUNDARY != DATABASE_INTEGRITY`.

    ACRESCENTADO NA AUDITORIA DA CADEIA 96 (achado A3). A coluna impunha
    só `NOT NULL`, e SQL bruto podia gravar array vazio, chave `url` ou
    `credential`, `kind` inventado, duplicata, ordem não canônica e
    evidência primária fora do conjunto — permanentes, numa tabela
    append-only.
    """
    texto = _migracao_da_fatia()
    assert "validated_experience_evidence_is_canonical" in texto
    assert _invariantes_presentes(texto) == {nome for nome, _ in INVARIANTES_DO_LASTRO}


def test_g11_1_a_constraint_do_lastro_esta_no_orm_e_na_migration():
    """Sem isso, `Base.metadata` divergiria do schema real."""
    assert "ck_validated_experiences_evidence_refs_canonical" in _migracao_da_fatia()
    assert "ck_validated_experiences_evidence_refs_canonical" in MODELO.read_text(encoding="utf-8")


@pytest.mark.parametrize("removido", ["nao vazio", "chaves exatas", "primaria no lastro"])
def test_g99_11_a_guarda_do_lastro_detecta_cada_invariante_removido(removido):
    """Mutante por invariante — os três que a auditoria nomeou."""
    texto = _migracao_da_fatia()
    agulha = dict(INVARIANTES_DO_LASTRO)[removido]
    mutante = texto.replace(agulha, "-- removido --")
    assert _invariantes_presentes(mutante) != {nome for nome, _ in INVARIANTES_DO_LASTRO}


# ----------------------------------------------------------------------
# g12 — a consulta por critério usa as três dimensões  (achado A4)
# ----------------------------------------------------------------------


def _dimensoes_no_filtro(arvore: ast.Module, funcao: str) -> set[str]:
    """Colunas comparadas dentro da função de listagem."""
    for no in ast.walk(arvore):
        if not isinstance(no, ast.FunctionDef) or no.name != funcao:
            continue
        return {
            filho.attr
            for comparacao in ast.walk(no)
            if isinstance(comparacao, ast.Compare)
            for filho in ast.walk(comparacao)
            if isinstance(filho, ast.Attribute)
        }
    return set()


def test_g12_a_consulta_por_criterio_filtra_pelas_tres_dimensoes():
    """`PARTIAL_REFERENCE_QUERY != EXACT_CRITERION_BINDING`.

    ACRESCENTADO NA AUDITORIA DA CADEIA 96 (achado A4): a consulta
    filtrava só por chave e versão, e misturava `PUBLISHED` com
    `DECLARED` de mesma chave e versão.
    """
    dimensoes = _dimensoes_no_filtro(_arvore(REPOSITORIO), "list_by_criterion")
    assert {"criterion_key", "criterion_version", "criterion_origin"} <= dimensoes


def test_g12_1_o_indice_acompanha_o_filtro():
    """Índice e filtro precisam concordar, senão a consulta exata varre."""
    for texto in (_migracao_da_fatia(), MODELO.read_text(encoding="utf-8")):
        bloco = texto.split("ix_validated_experiences_criterion")[1][:300]
        assert "criterion_key" in bloco
        assert "criterion_version" in bloco
        assert "criterion_origin" in bloco


@pytest.mark.parametrize("ausente", ["criterion_key", "criterion_version", "criterion_origin"])
def test_g99_12_a_guarda_de_filtro_detecta_cada_dimensao_faltante(ausente):
    dimensoes = {"criterion_key", "criterion_version", "criterion_origin"} - {ausente}
    fonte = (
        "def list_by_criterion(self, c):\n    return self._listar(\n"
        + "".join(f"        M.{d} == c.{d},\n" for d in sorted(dimensoes))
        + "    )\n"
    )
    encontradas = _dimensoes_no_filtro(ast.parse(fonte), "list_by_criterion")
    assert not {"criterion_key", "criterion_version", "criterion_origin"} <= encontradas
