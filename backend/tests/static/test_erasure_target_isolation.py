"""
Guardas de **isolamento** da resolução de alvo (`E4.9.7`).

```text
RESOLUTION_IS_OBSERVATIONAL = TRUE
TARGET_RESOLUTION != DELETION_AUTHORITY
DELETION_AUTHORITY != EFFECT
```

Esta fatia materializa contratos e nada mais. Estas guardas protegem o
*nada mais* por AST e por estrutura, nunca por leitura de docstring — as
docstrings destes módulos citam nominalmente o que eles **não** fazem, e
comparar texto bruto acusaria justamente as declarações de ausência.

É o quinto módulo do projeto a aprender isso da mesma forma (`gv16` na
E4.3.1, `s02`/`s11` na E4.9.6, `s15` na E4.9.6.1, `u76` na E4.9.6.3), e
por isso aqui a comparação por AST é o padrão desde o primeiro teste.

Arquivo próprio, pela lição da E4.6.3: prova estática em arquivo vizinho
muda a contagem de um módulo congelado por vizinhança.
"""

import ast
import pathlib

APP = pathlib.Path(__file__).resolve().parents[2] / "app"

NOVOS_MODULOS = {
    "app.memory.models.target_resolution_enums",
    "app.memory.schemas.erasure_target",
    "app.memory.ports.erasure_target",
}

CAMINHOS_NOVOS = (
    APP / "memory" / "models" / "target_resolution_enums.py",
    APP / "memory" / "schemas" / "erasure_target.py",
    APP / "memory" / "ports" / "erasure_target.py",
)


def _executavel(arquivo: pathlib.Path) -> str:
    """Código sem docstrings, via AST."""
    arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
    for no in ast.walk(arvore):
        corpo = getattr(no, "body", None)
        if isinstance(corpo, list):
            novo_corpo = [
                filho
                for filho in corpo
                if not (
                    isinstance(filho, ast.Expr)
                    and isinstance(filho.value, ast.Constant)
                    and isinstance(filho.value.value, str)
                )
            ] or [ast.Pass()]
            setattr(no, "body", novo_corpo)  # noqa: B010
    return ast.unparse(arvore)


def _modulos_importados(arquivo: pathlib.Path) -> set[str]:
    arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
    modulos: set[str] = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            modulos.update(alias.name for alias in no.names)
        elif isinstance(no, ast.ImportFrom) and no.module:
            modulos.add(no.module)
    return modulos


def _fontes() -> list[pathlib.Path]:
    return [p for p in APP.rglob("*.py") if "__pycache__" not in p.parts]


def test_s01_nenhum_import_de_app_cognitive() -> None:
    """Fronteira G17/MD6 — a E4 não conhece patrimônio da E3."""
    for caminho in CAMINHOS_NOVOS:
        importados = _modulos_importados(caminho)
        assert not any(m.startswith("app.cognitive") for m in importados), caminho.name


def test_s02_nenhuma_persistencia_nos_contratos_transitorios() -> None:
    """Descritor é capacidade contextual transitória, não entidade."""
    proibidos = (
        "BaseModel",
        "mapped_column",
        "Mapped",
        "Session",
        "UnitOfWork",
        "Repository",
        "sqlalchemy",
        "alembic",
        "declarative",
        "__tablename__",
    )
    for caminho in CAMINHOS_NOVOS:
        executavel = _executavel(caminho)
        for termo in proibidos:
            assert termo not in executavel, f"{caminho.name}: {termo}"


def test_s03_nenhum_efeito_destrutivo_nem_escritor_de_recibo() -> None:
    """`EFFECT != ERASURE_RECORD`, e nenhum dos dois existe aqui."""
    proibidos = (
        "ErasureRecord",
        "ErasureRecordRepository",
        "append_observed",
        "delete",
        "unlink",
        "remove",
        "purge",
        "trash",
        "execute_effect",
        "ErasureEffectPort",
    )
    for caminho in CAMINHOS_NOVOS:
        executavel = _executavel(caminho)
        for termo in proibidos:
            assert termo not in executavel, f"{caminho.name}: {termo}"


def test_s04_nenhum_storage_conector_ou_cliente_externo() -> None:
    proibidos = (
        "requests",
        "httpx",
        "urllib",
        "boto3",
        "aiohttp",
        "socket",
        "subprocess",
        "open(",
        "pathlib",
        "os.remove",
        "shutil",
    )
    for caminho in CAMINHOS_NOVOS:
        executavel = _executavel(caminho)
        for termo in proibidos:
            assert termo not in executavel, f"{caminho.name}: {termo}"


def test_s05_nenhum_parser_de_texto_ou_voz() -> None:
    """Texto e voz convergirão a um envelope futuro; não são desta camada."""
    proibidos = ("parse_command", "transcribe", "ASR", "speech", "def parse", "microphone")
    for caminho in CAMINHOS_NOVOS:
        executavel = _executavel(caminho)
        for termo in proibidos:
            assert termo not in executavel, f"{caminho.name}: {termo}"


def test_s06_nenhuma_supressao_de_tipo_nova() -> None:
    """Supressão vive em COMENTÁRIO; `Any` e `cast` vivem em CÓDIGO.

    São duas buscas diferentes de propósito, e a primeira versão desta
    guarda errou por não distingui-las: procurou o marcador no texto
    bruto e acusou a docstring que **declara** que nenhuma supressão é
    usada. Sexta vez que este projeto vê o mesmo falso positivo.

    A AST não serve para a supressão, porque `ast.unparse` descarta
    comentários — uma supressão real ficaria invisível. `tokenize` lê
    exatamente os comentários e nada mais.

    O marcador é montado em pedaços para que a própria guarda não se
    conte.
    """
    import io
    import tokenize

    marcador = "type:" + " ignore"
    for caminho in CAMINHOS_NOVOS:
        fonte = caminho.read_text(encoding="utf-8")
        comentarios = [
            token.string
            for token in tokenize.generate_tokens(io.StringIO(fonte).readline)
            if token.type == tokenize.COMMENT
        ]
        assert not any(marcador in c for c in comentarios), caminho.name

        executavel = _executavel(caminho)
        assert "cast(" not in executavel, caminho.name
        assert ": Any" not in executavel, caminho.name


def test_s07_nenhuma_migration_nova() -> None:
    """`MIGRATION_DELTA = 0` — descritores são transitórios."""
    versoes = APP.parent / "alembic" / "versions"
    revisoes = {p.name.split("_")[0] for p in versoes.glob("*.py")}
    assert "c8a3f5017e94" in revisoes
    for arquivo in versoes.glob("*.py"):
        if arquivo.name.startswith("c8a3f5017e94"):
            continue
        texto = arquivo.read_text(encoding="utf-8")
        assert 'down_revision: str | None = "c8a3f5017e94"' not in texto, arquivo.name


def test_s08_nenhuma_classe_de_alvo_foi_reeditada() -> None:
    """Uma fonte da verdade sobre classificação, não duas.

    `ErasureTargetClass` é da E4.9.5 e continua sendo a única. Se alguém
    declarar um segundo enum com os mesmos membros, esta guarda cai.
    """
    for caminho in CAMINHOS_NOVOS:
        executavel = _executavel(caminho)
        assert "class ErasureTargetClass" not in executavel, caminho.name
        for token in (
            "pia_managed_artifact",
            "authorized_connector_referent",
            "cognitive_metadata_record",
        ):
            assert token not in executavel, f"{caminho.name}: {token} reescrito"


def test_s09_o_efeito_nao_foi_materializado() -> None:
    """A E4.9.1 autorizou duas portas; esta fatia entrega uma."""
    infratores = [
        str(p.relative_to(APP)) for p in _fontes() if "ErasureEffectPort" in _executavel(p)
    ]
    assert infratores == []


def test_s10_nenhum_consumidor_runtime_da_porta_apareceu() -> None:
    """Contrato sem adaptador é o estado correto desta fatia."""
    permitidos = set(CAMINHOS_NOVOS) | {
        APP / "memory" / "ports" / "__init__.py",
        APP / "memory" / "models" / "__init__.py",
    }
    infratores = [
        str(p.relative_to(APP))
        for p in _fontes()
        if p not in permitidos and NOVOS_MODULOS & _modulos_importados(p)
    ]
    assert infratores == []


def test_s11_o_localizador_nao_tem_caminho_de_saida() -> None:
    """`MUST_NOT_PERSIST` e `MUST_NOT_BE_LOGGED_BY_THIS_MODULE`."""
    executavel = _executavel(APP / "memory" / "schemas" / "erasure_target.py")
    for termo in ("get_logger", "log_event", "logging", "print(", "to_dict", "model_dump"):
        assert termo not in executavel, termo


def test_s12_a_redacao_do_localizador_vive_no_codigo_executavel() -> None:
    """Se alguém remover o `__repr__`, esta guarda cai.

    A dataclass já oculta o campo por `repr=False`, mas um argumento é
    fácil de apagar sem perceber. A redação explícita é a segunda camada.
    """
    arvore = ast.parse(
        (APP / "memory" / "schemas" / "erasure_target.py").read_text(encoding="utf-8")
    )
    (classe,) = [
        no
        for no in ast.walk(arvore)
        if isinstance(no, ast.ClassDef) and no.name == "ErasureTargetDescriptor"
    ]
    metodos = {no.name for no in classe.body if isinstance(no, ast.FunctionDef)}
    assert {"__repr__", "__str__"} <= metodos
    corpo = ast.unparse(classe)
    assert "LOCALIZADOR_OCULTO" in corpo


def test_s13_todos_os_value_objects_sao_frozen() -> None:
    """Congelamento declarado no decorador, não prometido em docstring."""
    arvore = ast.parse(
        (APP / "memory" / "schemas" / "erasure_target.py").read_text(encoding="utf-8")
    )
    classes = [no for no in ast.walk(arvore) if isinstance(no, ast.ClassDef)]
    assert len(classes) == 6
    for classe in classes:
        congelada = any(
            isinstance(dec, ast.Call)
            and isinstance(dec.func, ast.Name)
            and dec.func.id == "dataclass"
            and any(
                kw.arg == "frozen" and isinstance(kw.value, ast.Constant) and kw.value.value is True
                for kw in dec.keywords
            )
            for dec in classe.decorator_list
        )
        assert congelada, classe.name


def test_s14_a_porta_nao_recebe_sessao_repositorio_nem_efeito() -> None:
    """A assinatura é a garantia, provada na AST."""
    arvore = ast.parse((APP / "memory" / "ports" / "erasure_target.py").read_text(encoding="utf-8"))
    (metodo,) = [
        no
        for no in ast.walk(arvore)
        if isinstance(no, ast.FunctionDef) and no.name == "resolve_target"
    ]
    parametros = [arg.arg for arg in metodo.args.args]
    assert parametros == ["self", "reference"]
    assert metodo.args.vararg is None
    assert metodo.args.kwarg is None
    assert metodo.args.kwonlyargs == []


def test_s15_nenhum_relogio_implicito_nos_contratos() -> None:
    """`resolved_at` chega por argumento, como na E4.9.6."""
    for caminho in CAMINHOS_NOVOS:
        arvore = ast.parse(caminho.read_text(encoding="utf-8"))
        chamadas = {
            no.func.attr
            for no in ast.walk(arvore)
            if isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute)
        }
        assert "now" not in chamadas, caminho.name
        assert "utcnow" not in chamadas, caminho.name
        assert "today" not in chamadas, caminho.name


def test_s16_enums_e_policies_anteriores_intocados() -> None:
    """Escopo confinado: nada da E4.9.5/E4.9.6 foi editado."""
    erasure_enums = (APP / "memory" / "models" / "erasure_enums.py").read_text(encoding="utf-8")
    assert "TargetResolutionRefusalReason" not in erasure_enums
    assert "ErasureTargetDescriptor" not in erasure_enums

    retention = (APP / "memory" / "schemas" / "retention.py").read_text(encoding="utf-8")
    assert "ErasureTarget" not in retention
