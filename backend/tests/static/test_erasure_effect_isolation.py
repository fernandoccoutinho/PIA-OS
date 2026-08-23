"""
Guardas de **isolamento** da fronteira de efeito (`E4.9.9.b`).

```text
ERASURE_EFFECT_ADAPTER = NONE
EFFECT != ERASURE_RECORD
```

Esta fatia cria contratos inertes. As guardas provam o *nada além* por
AST e reflexão, e preferem comportamento a busca textual — o
comportamento está em `test_erasure_effect.py`.

Mutante só acompanha a guarda quando ela é a **única** prova de uma
propriedade material.
"""

import ast
import pathlib

APP = pathlib.Path(__file__).resolve().parents[2] / "app"

NOVOS = (
    APP / "memory" / "models" / "erasure_effect_enums.py",
    APP / "memory" / "schemas" / "erasure_effect.py",
    APP / "memory" / "ports" / "erasure_effect.py",
)


def _executavel(arquivo: pathlib.Path) -> str:
    arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
    for no in ast.walk(arvore):
        corpo = getattr(no, "body", None)
        if isinstance(corpo, list):
            novo = [
                filho
                for filho in corpo
                if not (
                    isinstance(filho, ast.Expr)
                    and isinstance(filho.value, ast.Constant)
                    and isinstance(filho.value.value, str)
                )
            ] or [ast.Pass()]
            setattr(no, "body", novo)  # noqa: B010
    return ast.unparse(arvore)


def _fontes() -> list[pathlib.Path]:
    return [p for p in APP.rglob("*.py") if "__pycache__" not in p.parts]


def _importados(arquivo: pathlib.Path) -> set[str]:
    arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
    modulos: set[str] = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.ImportFrom) and no.module:
            modulos.add(no.module)
        elif isinstance(no, ast.Import):
            modulos.update(a.name for a in no.names)
    return modulos


def test_s01_nenhuma_rede_filesystem_shell_ou_conector() -> None:
    proibidos = (
        "requests",
        "httpx",
        "urllib",
        "boto3",
        "socket",
        "subprocess",
        "shutil",
        "os.remove",
        "unlink",
        "open(",
        "pathlib",
        "aiohttp",
    )
    for caminho in NOVOS:
        executavel = _executavel(caminho)
        for termo in proibidos:
            assert termo not in executavel, f"{caminho.name}: {termo}"


def test_s02_nenhum_adaptador_ou_executor() -> None:
    """`ERASURE_EFFECT_ADAPTER = NONE`.

    O port declara fronteira; ele não implementa efeito. Nenhuma classe
    concreta do repositório satisfaz o Protocol.
    """
    infratores: list[str] = []
    for caminho in _fontes():
        arvore = ast.parse(caminho.read_text(encoding="utf-8"))
        for no in ast.walk(arvore):
            if not isinstance(no, ast.ClassDef):
                continue
            bases = {b.id for b in no.bases if isinstance(b, ast.Name)}
            if "Protocol" in bases:
                continue
            metodos = {
                filho.name
                for filho in no.body
                if isinstance(filho, ast.FunctionDef | ast.AsyncFunctionDef)
            }
            if "attempt_effect" in metodos:
                infratores.append(f"{caminho.name}:{no.name}")
    assert infratores == []


def test_s03_nenhuma_escrita_de_recibo_nem_consumo_de_aprovacao() -> None:
    """`EFFECT != ERASURE_RECORD` · nenhum consumo aqui."""
    for caminho in NOVOS:
        executavel = _executavel(caminho)
        for termo in (
            "append_observed",
            "ErasureRecordRepository",
            "ErasureRecord",
            "ApprovalRecordRepository",
            "consume_once",
            "revoke_once",
        ):
            assert termo not in executavel, f"{caminho.name}: {termo}"


def test_s04_nenhuma_persistencia_orm_ou_migration() -> None:
    for caminho in NOVOS:
        executavel = _executavel(caminho)
        for termo in ("mapped_column", "Mapped", "Session", "Repository", "sqlalchemy"):
            assert termo not in executavel, f"{caminho.name}: {termo}"

    versoes = APP.parent / "alembic" / "versions"
    grafo: dict[str, str | None] = {}
    for arquivo in versoes.glob("*.py"):
        revisao = pai = None
        for no in ast.walk(ast.parse(arquivo.read_text(encoding="utf-8"))):
            if isinstance(no, ast.AnnAssign) and isinstance(no.target, ast.Name):
                if no.target.id == "revision" and isinstance(no.value, ast.Constant):
                    revisao = no.value.value
                elif no.target.id == "down_revision" and isinstance(no.value, ast.Constant):
                    pai = no.value.value
        if revisao:
            grafo[revisao] = pai
    pais = {p for p in grafo.values() if p}
    folhas = sorted(r for r in grafo if r not in pais)
    # E4.9.9.d: a migration textual de `governance_rule_id` é a sucessora
    # AUTORIZADA. Ela não pertence a ESTA fatia, e a guarda continua
    # medindo head ÚNICO — só o alvo do "único" mudou.
    # E4.11: a tabela de experiência validada sucede aquela, pelo mesmo
    # critério e sem pertencer a esta fatia.
    filhos_e5 = [r for r, p in grafo.items() if p == "e7c25a91f4b3"]
    assert filhos_e5 == ["f8a91c2d4e60"], filhos_e5
    # ATUALIZADO PELA E7.1: a folha passou a ser `b8c04e2fd137`
    # (orquestração). A guarda continua medindo folha ÚNICA — não
    # imobilidade da cadeia.
    assert folhas == ["b8c04e2fd137"], folhas


def test_s05_nenhuma_re_resolucao_nem_comparacao_de_snapshot() -> None:
    """Isso é E4.9.9.d — alegar aqui seria capacidade acima da camada."""
    for caminho in NOVOS:
        executavel = _executavel(caminho)
        for termo in (
            "SafeTargetSnapshot",
            "comparar_com_snapshot",
            "ErasureTargetResolverPort",
            "resolve_target",
            "RetentionEvaluator",
            "DestructiveExecutionService",
        ):
            assert termo not in executavel, f"{caminho.name}: {termo}"


def test_s06_nenhum_serializer_logger_ou_supressao() -> None:
    import io
    import tokenize

    marcador = "type:" + " ignore"
    for caminho in NOVOS:
        executavel = _executavel(caminho)
        for termo in ("to_dict", "model_dump", "asdict(", "get_logger", "logging", "print("):
            assert termo not in executavel, f"{caminho.name}: {termo}"
        assert "cast(" not in executavel, caminho.name
        assert ": Any" not in executavel, caminho.name
        comentarios = [
            token.string
            for token in tokenize.generate_tokens(
                io.StringIO(caminho.read_text(encoding="utf-8")).readline
            )
            if token.type == tokenize.COMMENT
        ]
        assert not any(marcador in c for c in comentarios), caminho.name


def test_s07_nenhum_consumidor_de_producao_fora_dos_exports() -> None:
    """Contrato sem consumidor é o estado correto desta fatia."""
    modulos = {
        "app.memory.models.erasure_effect_enums",
        "app.memory.schemas.erasure_effect",
        "app.memory.ports.erasure_effect",
    }
    permitidos = set(NOVOS) | {
        APP / "memory" / "models" / "__init__.py",
        APP / "memory" / "schemas" / "__init__.py",
        APP / "memory" / "ports" / "__init__.py",
    }
    # ATUALIZADA NA E4.9.9.d. A composição final é o consumidor
    # AUTORIZADO, e a guarda ficou MAIS FORTE, não mais frouxa: antes
    # exigia ZERO consumidores; agora exige EXATAMENTE UM, e nomeia
    # qual. Um segundo consumidor passaria na versão antiga se ela
    # tivesse sido apenas relaxada com um `permitidos`.
    #
    # ```text
    # AUTHORIZED_CONSUMER = destructive_execution_service.py
    # SECOND_CONSUMER = FORBIDDEN
    # ```
    # DOIS consumidores autorizados, com papéis distintos — e é a
    # distinção que a guarda preserva:
    #
    # ```text
    # schemas/destructive_execution.py   contratos INERTES da composição
    # services/destructive_execution_service.py   a composição EXECUTÁVEL
    # ```
    #
    # Um terceiro é recusado. Comparar CONJUNTOS, e não listas, porque a
    # ordem de varredura do sistema de arquivos não é contrato.
    esperados = {
        "memory/schemas/destructive_execution.py",
        "memory/services/destructive_execution_service.py",
    }
    infratores = [
        str(p.relative_to(APP))
        for p in _fontes()
        if p not in permitidos and modulos & _importados(p)
    ]
    assert set(infratores) == esperados, infratores


def test_s08_a_porta_de_efeito_e_separada_da_de_resolucao() -> None:
    """`RESOLUTION != DELETION_AUTHORITY`.

    Uma porta única deixaria quem sabe **onde** o objeto está com o poder
    de destruí-lo.
    """
    efeito = _executavel(APP / "memory" / "ports" / "erasure_effect.py")
    resolucao = _executavel(APP / "memory" / "ports" / "erasure_target.py")
    assert "attempt_effect" not in resolucao
    assert "resolve" not in efeito


def test_s09_a_uniao_e_fechada_com_exatamente_dois_membros() -> None:
    import typing

    from app.memory.schemas.erasure_effect import (
        ErasureEffectResult,
        MaterialAttemptNotStarted,
        ObservedAttemptResult,
    )

    assert set(typing.get_args(ErasureEffectResult)) == {
        MaterialAttemptNotStarted,
        ObservedAttemptResult,
    }
    assert type(None) not in typing.get_args(ErasureEffectResult)
    assert bool not in typing.get_args(ErasureEffectResult)


def test_s10_stage_e_derivado_nas_duas_classes() -> None:
    """`STAGE = DERIVED_TAG_ONLY` — fixado na AST.

    Se virar campo, alguém constrói uma não-tentativa marcada como
    observada, e a etiqueta compete com o tipo pela verdade.
    """
    arvore = ast.parse(
        (APP / "memory" / "schemas" / "erasure_effect.py").read_text(encoding="utf-8")
    )
    for nome in ("MaterialAttemptNotStarted", "ObservedAttemptResult"):
        (classe,) = [
            no for no in ast.walk(arvore) if isinstance(no, ast.ClassDef) and no.name == nome
        ]
        anotacoes = {
            no.target.id
            for no in classe.body
            if isinstance(no, ast.AnnAssign) and isinstance(no.target, ast.Name)
        }
        assert "stage" not in anotacoes, nome
        (metodo,) = [
            no for no in classe.body if isinstance(no, ast.FunctionDef) and no.name == "stage"
        ]
        assert any(
            isinstance(d, ast.Name) and d.id == "property" for d in metodo.decorator_list
        ), nome


def test_s11_nenhuma_traducao_de_capacidade_para_operacao() -> None:
    """`APPLICATION_LEVEL_CAPABILITY_OPERATION_MAPPING = FORBIDDEN`.

    `capability.operation` é texto opaco do provedor. Uma matriz local
    inventaria semântica, e o erro é assimétrico: poderia deixar passar
    apagamento definitivo com capacidade que só autorizava lixeira.

    Esta guarda é a única prova ESTÁTICA da ausência; a prova de
    comportamento está em `u19`, que aceita seis textos distintos para as
    duas operações aprovadas.
    """
    arvore = ast.parse(
        (APP / "memory" / "schemas" / "erasure_effect.py").read_text(encoding="utf-8")
    )
    lidos = [
        no
        for no in ast.walk(arvore)
        if isinstance(no, ast.Attribute)
        and no.attr == "operation"
        and isinstance(no.value, ast.Attribute)
        and no.value.attr == "capability"
    ]
    assert lidos == []

    executavel = _executavel(APP / "memory" / "schemas" / "erasure_effect.py")
    for forma in (".startswith(", ".endswith(", "CAPABILITY_OPERATION", "OPERACAO_DE_CAPACIDADE"):
        assert forma not in executavel, forma


def _classes_com_metodo(fontes, metodo: str) -> list[str]:
    """Classes de produção que IMPLEMENTAM o método — nunca o `Protocol`.

    ```text
    DECLARED_BOUNDARY != CONCRETE_ADAPTER
    ```

    Um `Protocol` declara a fronteira e tem corpo `...`; um adaptador a
    implementa. A distinção é medida na AST pelo corpo do método, não
    pelo nome do arquivo.
    """
    encontradas: list[str] = []
    for caminho in fontes:
        arvore = ast.parse(caminho.read_text(encoding="utf-8"))
        for no in ast.walk(arvore):
            if not isinstance(no, ast.ClassDef):
                continue
            protocolo = any(
                isinstance(base, ast.Name) and base.id == "Protocol" for base in no.bases
            )
            if protocolo:
                continue
            for membro in no.body:
                if not isinstance(membro, ast.FunctionDef | ast.AsyncFunctionDef):
                    continue
                if membro.name != metodo:
                    continue
                corpo = [
                    linha
                    for linha in membro.body
                    if not (isinstance(linha, ast.Expr) and isinstance(linha.value, ast.Constant))
                ]
                substancial = not (
                    len(corpo) == 1
                    and isinstance(corpo[0], ast.Expr)
                    and isinstance(corpo[0].value, ast.Constant)
                    and corpo[0].value.value is Ellipsis
                )
                if substancial:
                    encontradas.append(f"{caminho.name}:{no.name}")
    return encontradas


def test_s12_a_porta_continua_sem_adaptador_concreto() -> None:
    """RENOMEADA NA E4.9.9.d — ver `test_s13` do isolamento da aprovação.

    ```text
    EFFECT_PORT = DECLARED_BOUNDARY
    EFFECT_ADAPTER = NONE
    ```

    A E4.9.9.d compõe a porta; ela não a implementa. O adaptador
    continua sendo obrigação de uma autorização futura, e os únicos
    `attempt_effect` com corpo vivem em `tests/`.
    """
    assert _classes_com_metodo(_fontes(), "attempt_effect") == []


def test_s13_e3_intocada_pelos_modulos_novos() -> None:
    for caminho in NOVOS:
        assert not any(m.startswith("app.cognitive") for m in _importados(caminho))


def test_s99_1_a_guarda_de_capacidade_detecta_traducao_introduzida() -> None:
    """§ mutante — `s11` é a única prova estática desta propriedade."""
    limpo = (
        "class R:\n"
        "    def __post_init__(self):\n"
        "        if not self.descriptor.capability.verified:\n"
        "            raise ValueError('x')\n"
    )
    com_traducao = (
        "class R:\n"
        "    def __post_init__(self):\n"
        "        if self.descriptor.capability.operation != 'delete_object':\n"
        "            raise ValueError('x')\n"
    )

    def le_operacao_da_capacidade(fonte: str) -> bool:
        return bool(
            [
                no
                for no in ast.walk(ast.parse(fonte))
                if isinstance(no, ast.Attribute)
                and no.attr == "operation"
                and isinstance(no.value, ast.Attribute)
                and no.value.attr == "capability"
            ]
        )

    assert not le_operacao_da_capacidade(limpo)
    assert le_operacao_da_capacidade(com_traducao)


def test_s99_2_a_guarda_de_stage_detecta_campo_introduzido() -> None:
    """§ mutante — `s10` é a única prova estática desta propriedade."""
    derivado = (
        "class X:\n" "    a: int\n" "    @property\n" "    def stage(self):\n" "        return 1\n"
    )
    como_campo = "class X:\n    a: int\n    stage: EffectAttemptStage\n"

    def stage_e_campo(fonte: str) -> bool:
        (classe,) = [no for no in ast.walk(ast.parse(fonte)) if isinstance(no, ast.ClassDef)]
        return "stage" in {
            no.target.id
            for no in classe.body
            if isinstance(no, ast.AnnAssign) and isinstance(no.target, ast.Name)
        }

    assert not stage_e_campo(derivado)
    assert stage_e_campo(como_campo)
