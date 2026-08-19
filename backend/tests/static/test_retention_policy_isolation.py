"""
Guardas de **isolamento** da `RetentionPolicy` (`E4.9.6`).

```text
RETENTION_POLICY_PERSISTENCE != RETENTION_EVALUATION
RETENTION_EVALUATION         != USER_DECISION
USER_DECISION                != DESTRUCTIVE_EXECUTION
```

Esta fatia persiste a regra e nada mais. Estas guardas protegem o
*nada mais* por AST e por estrutura, não por leitura de docstring.

Arquivo próprio, pela lição da E4.6.3: prova estática em arquivo
vizinho muda a contagem de um módulo congelado por vizinhança.

```text
FROZEN MODULE COUNT != NEIGHBOURING FILE
```
"""

import ast
import pathlib

APP = pathlib.Path(__file__).resolve().parents[2] / "app"

NOVOS_MODULOS = {
    "app.memory.models.retention_policy",
    "app.memory.models.retention_enums",
    "app.memory.schemas.retention",
    "app.memory.repositories.retention_policy_repository",
}

PERMITIDOS = {
    APP / "memory" / "models" / "retention_policy.py",
    APP / "memory" / "models" / "retention_enums.py",
    APP / "memory" / "schemas" / "retention.py",
    APP / "memory" / "repositories" / "retention_policy_repository.py",
    APP / "memory" / "models" / "__init__.py",
    APP / "memory" / "errors" / "codes.py",
    APP / "memory" / "errors" / "exceptions.py",
    # E4.9.9.c: o avaliador PURO consome `RetentionRule` — é para isso que
    # a E4.9.6 a criou, e `rule_id` existe desde então "para ser citado
    # como fundamento de uma avaliação futura". Esta é a avaliação futura.
    #
    # O que continua provado, e é o que importa:
    #
    # ```text
    # RETENTION_POLICY_REPOSITORY_CONSUMER = NONE
    # DISPOSITION = NONE   SCHEDULER = NONE   PERSISTENCE = NONE
    # ```
    #
    # `test_retention_evaluator_isolation` prova pelo outro lado que o
    # avaliador não lê banco, não agenda, não dispõe e não forma aprovação.
    APP / "memory" / "services" / "retention_evaluator.py",
}


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


def _executavel(arquivo: pathlib.Path) -> str:
    """Código sem docstrings, via AST.

    As docstrings destes módulos citam nominalmente o que eles **não**
    fazem — `ErasureRecordRepository`, `CognitiveObject`, avaliação — e
    comparar o texto bruto acusaria justamente as declarações de
    ausência. Mesmo falso positivo que a E4.3.1 corrigiu em `gv16` e
    que a guarda da E4.3.5 já resolve assim.
    """
    arvore = ast.parse(arquivo.read_text(encoding="utf-8"))
    for no in ast.walk(arvore):
        corpo = getattr(no, "body", None)
        if isinstance(corpo, list):
            # `setattr` em vez de `no.body = ...`: nem todo nó da AST
            # declara `body`, e o mypy compara contra `ast.AST`.
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


def test_s01_nenhum_servico_importa_a_policy_para_avaliar_ou_agir() -> None:
    """`RETENTION_EVALUATOR = NOT_COMPOSED`."""
    infratores: list[str] = []
    for arquivo in _fontes():
        if arquivo in PERMITIDOS:
            continue
        if NOVOS_MODULOS & _modulos_importados(arquivo):
            infratores.append(str(arquivo.relative_to(APP)))
    assert infratores == [], f"importam a policy sem autorização: {infratores}"


def test_s02_a_policy_nao_escreve_erasure_record() -> None:
    """Nem por import, nem por menção textual."""
    for modulo in NOVOS_MODULOS:
        caminho = APP.parent / (modulo.replace(".", "/") + ".py")
        executavel = _executavel(caminho)
        assert "ErasureRecordRepository" not in executavel, modulo
        assert "append_observed" not in executavel, modulo


def test_s03_nenhum_enum_de_expiracao_contem_acao_destrutiva() -> None:
    from app.memory.models.retention_enums import RetentionExpiryAction

    proibidos = {
        "DELETE",
        "ERASE",
        "TRASH",
        "MARK_INACCESSIBLE",
        "ARCHIVE",
        "NOTIFY_AND_DELETE",
        "AUTO_CLEANUP",
        "PURGE",
        "CLEANUP",
        "REMOVE",
    }
    assert set(RetentionExpiryAction.__members__) & proibidos == set()
    assert [e.value for e in RetentionExpiryAction] == ["assess_and_inform"]


def test_s04_nenhum_modulo_novo_importa_app_cognitive() -> None:
    """Isolamento local da E4 — a policy não conhece patrimônio."""
    for modulo in NOVOS_MODULOS:
        caminho = APP.parent / (modulo.replace(".", "/") + ".py")
        importados = _modulos_importados(caminho)
        assert not any(m.startswith("app.cognitive") for m in importados), modulo


def test_s05_sync_nao_contem_retention_policies() -> None:
    """`RETENTION_POLICY_SYNC = NONE` — autoridade não é transferível."""
    from app.cognitive.schemas.synchronization import SECTION_BY_TABLE

    assert "retention_policies" not in SECTION_BY_TABLE
    assert "erasure_records" not in SECTION_BY_TABLE


def test_s06_nenhuma_rota_expoe_a_policy() -> None:
    candidatos = [
        p
        for p in _fontes()
        if any(parte in {"api", "routers", "routes", "endpoints"} for parte in p.parts)
    ]
    for arquivo in candidatos:
        assert not (NOVOS_MODULOS & _modulos_importados(arquivo)), arquivo


def test_s07_nenhum_parser_de_texto_ou_voz_foi_criado() -> None:
    """Texto e voz convergirão a um envelope futuro; não são desta camada."""
    proibidos = ("parse_command", "transcribe", "def parse", "ASR", "speech")
    for modulo in NOVOS_MODULOS:
        caminho = APP.parent / (modulo.replace(".", "/") + ".py")
        executavel = _executavel(caminho)
        for termo in proibidos:
            assert termo not in executavel, f"{modulo}: {termo}"


def test_s08_revision_status_permanece_intacto() -> None:
    """`RevisionStatus.CURRENT` **não** é `VALIDATED_CURRENT`."""
    from app.cognitive.models.enums import RevisionStatus

    assert [e.value for e in RevisionStatus] == ["current", "superseded"]
    assert "VALIDATED_CURRENT" not in RevisionStatus.__members__


def test_s09_enums_cognitivos_permanecem_intactos() -> None:
    from app.cognitive.models.enums import CausalEventType
    from app.memory.models.governance_enums import CognitiveOperation

    assert [e.value for e in CausalEventType] == [
        "created",
        "transformed",
        "compared",
        "accessed",
    ]
    assert len(CognitiveOperation) == 11


def test_s10_a_policy_nao_tem_relogio_implicito() -> None:
    """Consultar qual regra valia não é decidir que está na hora de agir.

    `effective_version_at` recebe o instante por argumento; um
    repositório que lesse o relógio sozinho estaria a um passo de agir
    sozinho.
    """
    caminho = APP / "memory" / "repositories" / "retention_policy_repository.py"
    arvore = ast.parse(caminho.read_text(encoding="utf-8"))
    chamadas = {
        no.func.attr
        for no in ast.walk(arvore)
        if isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute)
    }
    assert "now" not in chamadas
    assert "utcnow" not in chamadas
    assert "today" not in chamadas


def test_s11_o_repositorio_nao_conhece_patrimonio_nem_efeito() -> None:
    caminho = APP / "memory" / "repositories" / "retention_policy_repository.py"
    texto = _executavel(caminho)
    for termo in (
        "CognitiveObject",
        "ObjectRepository",
        "MemoryRetrievalManager",
        "open(",
        "requests",
        "httpx",
    ):
        assert termo not in texto, termo


# ======================================================================
# E4.9.6.1 — guardas do corretivo
# ======================================================================


def test_s12_nenhuma_migration_nova() -> None:
    """`MIGRATION_DELTA = 0` — o corretivo é tipado, não de schema."""
    versoes = APP.parent / "alembic" / "versions"
    revisoes = {p.name.split("_")[0] for p in versoes.glob("*.py")}
    assert "c8a3f5017e94" in revisoes
    # Nenhuma revisão declara `c8a3f5017e94` como pai: ele é o head.
    for arquivo in versoes.glob("*.py"):
        texto = arquivo.read_text(encoding="utf-8")
        # E4.9.9.a: `a1f7c2d40e93` é a sucessora AUTORIZADA do head
        # anterior. A guarda continua provando que nenhuma OUTRA nasceu.
        if arquivo.name.startswith(("c8a3f5017e94", "a1f7c2d40e93")):
            continue
        assert 'down_revision: str | None = "c8a3f5017e94"' not in texto, arquivo.name


def test_s13_base_repository_e_policies_antigas_intocadas() -> None:
    """Stop Condition 3 do corretivo: nada disso podia mudar.

    Prova estrutural, não de conteúdo: `BaseRepository` continua sem
    conhecer retenção, e as policies antigas continuam expondo o JSON
    da forma como sempre expuseram — o corretivo é confinado à E4.9.6.
    """
    base_repo = (APP / "repositories" / "base_repository.py").read_text(encoding="utf-8")
    assert "Retention" not in base_repo

    for antiga in ("governance_policy.py", "accessibility_policy.py"):
        texto = (APP / "memory" / "models" / antiga).read_text(encoding="utf-8")
        assert "RetentionRulesType" not in texto, antiga
        assert "TypeDecorator" not in texto, antiga


def test_s14_o_congelamento_vive_na_fronteira_do_orm() -> None:
    """A estratégia adotada, provada estruturalmente.

    `rules` é anotada como `tuple[RetentionRule, ...]`, e o
    `TypeDecorator` é quem converte para JSON no bind. Se alguém um dia
    trocar a coluna de volta para `list[dict]`, este teste cai.
    """
    from app.memory.models.retention_policy import RetentionPolicy, RetentionRulesType

    coluna = RetentionPolicy.__table__.c.rules
    assert isinstance(coluna.type, RetentionRulesType)

    fonte = (APP / "memory" / "models" / "retention_policy.py").read_text(encoding="utf-8")
    assert 'Mapped[tuple["RetentionRule", ...]]' in fonte
    assert "Mapped[list[dict[str, Any]]]" not in fonte


def test_s15_validador_opaco_e_compartilhado_e_nao_normaliza() -> None:
    """`VALIDATED OPAQUE KEY != NORMALIZED KEY`."""
    # Pelo código EXECUTÁVEL: a docstring do validador explica por que
    # não normaliza, e uma busca no texto bruto acusaria a explicação.
    executavel = _executavel(APP / "memory" / "schemas" / "retention.py")
    corpo = executavel[executavel.index("def validar_identificador_opaco") :]
    corpo = corpo[: corpo.index("\n@dataclass")]
    # ATUALIZADA NA E4.9.6.2, deliberadamente. A versão da E4.9.6.1
    # proibia o módulo `unicodedata` inteiro, o que era grosso demais: o
    # endurecimento autorizado pela auditoria exige `category`, que
    # CLASSIFICA. O que nunca pode aparecer é o que TRANSFORMA.
    for proibido in (
        "casefold",
        "normalize",
        "lower()",
        "upper()",
        "NFC",
        "NFD",
        "NFKC",
        "NFKD",
        "translate",
        "encode",
    ):
        assert proibido not in corpo, proibido
    assert "unicodedata.category" in corpo
    assert "unicodedata.normalize" not in corpo
    # `strip()` só aparece na CHECAGEM de branco, nunca no valor devolvido.
    assert "return valor" in corpo
    assert "return valor.strip()" not in corpo

    # Duas CHAMADAS no repositório — uma por chave. Contadas na AST, não
    # por substring: o import é multilinha e não repete o parêntese.
    arvore = ast.parse(
        (APP / "memory" / "repositories" / "retention_policy_repository.py").read_text(
            encoding="utf-8"
        )
    )
    chamadas = [
        no
        for no in ast.walk(arvore)
        if isinstance(no, ast.Call)
        and isinstance(no.func, ast.Name)
        and no.func.id == "validar_identificador_opaco"
    ]
    campos = {no.args[0].value for no in chamadas if isinstance(no.args[0], ast.Constant)}
    assert campos == {"policy_key", "governance_policy_key"}


def test_s16_nenhum_avaliador_ou_escritor_apareceu_no_corretivo() -> None:
    """Reafirmação: o corretivo não abriu caminho novo."""
    infratores: list[str] = []
    for arquivo in _fontes():
        if arquivo in PERMITIDOS:
            continue
        if NOVOS_MODULOS & _modulos_importados(arquivo):
            infratores.append(str(arquivo.relative_to(APP)))
    assert infratores == []

    for modulo in NOVOS_MODULOS:
        caminho = APP.parent / (modulo.replace(".", "/") + ".py")
        executavel = _executavel(caminho)
        for termo in ("ErasureRecordRepository", "append_observed", "evaluate", "assess("):
            assert termo not in executavel, f"{modulo}: {termo}"


# ======================================================================
# E4.9.6.2 — guardas de completude de fronteira
# ======================================================================


def test_s17_a_fronteira_de_atribuicao_do_orm_existe() -> None:
    """`TYPE DECORATOR BOUNDARY != ORM ASSIGNMENT BOUNDARY`.

    A E4.9.6.1 confiou só no `TypeDecorator`, que corre no bind e no
    result. Objeto construído em Python e nunca gravado não atravessa
    nenhum dos dois. Esta guarda prova, na AST, que existe um
    `@validates("rules")` — se alguém removê-lo confiando no decorador,
    o defeito A3b volta e este teste cai.
    """
    arvore = ast.parse(
        (APP / "memory" / "models" / "retention_policy.py").read_text(encoding="utf-8")
    )
    decorados = {
        no.args[0].value
        for funcao in ast.walk(arvore)
        if isinstance(funcao, ast.FunctionDef)
        for no in funcao.decorator_list
        if isinstance(no, ast.Call)
        and isinstance(no.func, ast.Name)
        and no.func.id == "validates"
        and no.args
        and isinstance(no.args[0], ast.Constant)
    }
    assert "rules" in decorados


def test_s18_o_contrato_de_regras_e_unico_e_compartilhado() -> None:
    """Uma função, três fronteiras — não três listas de checagens.

    O corretivo existe porque duas fronteiras divergiram. Manter cópias
    locais dos invariantes é como voltariam a divergir, então o
    validador compartilhado precisa ser chamado pelo `@validates`, pelo
    bind e pela leitura defensiva.
    """
    arvore = ast.parse(
        (APP / "memory" / "models" / "retention_policy.py").read_text(encoding="utf-8")
    )
    chamadas = [
        no
        for no in ast.walk(arvore)
        if isinstance(no, ast.Call)
        and isinstance(no.func, ast.Name)
        and no.func.id == "validar_regras_retencao"
    ]
    assert len(chamadas) >= 3, "atribuição, bind e leitura defensiva"

    # Nenhuma cópia local do invariante de não vacuidade sobrou no modelo.
    executavel = _executavel(APP / "memory" / "models" / "retention_policy.py")
    assert "ao menos uma regra" not in executavel


def test_s19_typed_rules_nao_e_passthrough_puro() -> None:
    """`ANNOTATED TYPE != RUNTIME TYPE PROOF`.

    Na cadeia 77 esta propriedade era `return self.rules` e a anotação
    mentia em runtime. Ela precisa reafirmar o contrato.
    """
    arvore = ast.parse(
        (APP / "memory" / "models" / "retention_policy.py").read_text(encoding="utf-8")
    )
    (propriedade,) = [
        no
        for no in ast.walk(arvore)
        if isinstance(no, ast.FunctionDef) and no.name == "typed_rules"
    ]
    corpo = [linha for linha in propriedade.body if not isinstance(linha, ast.Expr)]
    assert corpo, "typed_rules não pode ter corpo só de docstring"
    (retorno,) = corpo
    assert isinstance(retorno, ast.Return)
    assert isinstance(retorno.value, ast.Call), "retorno cru volta a mentir o tipo"


def test_s20_o_corretivo_nao_trouxe_avaliador_nem_efeito() -> None:
    """Reafirmação após a E4.9.6.2 — o escopo continua fechado."""
    for modulo in NOVOS_MODULOS:
        caminho = APP.parent / (modulo.replace(".", "/") + ".py")
        executavel = _executavel(caminho)
        for termo in (
            "ErasureRecordRepository",
            "append_observed",
            "evaluate",
            "assess(",
            "trash",
            "purge",
            "scheduler",
        ):
            assert termo not in executavel, f"{modulo}: {termo}"


def test_s21_categorias_proibidas_sao_exatamente_as_autorizadas() -> None:
    """`Cc`, `Cf`, `Zl`, `Zp` — nem mais, nem menos.

    Menos deixaria passar invisível; mais recusaria letra, número,
    marca, pontuação ou o espaço comum (`Zs`), que a auditoria mandou
    preservar explicitamente.
    """
    from app.memory.schemas.retention import CATEGORIAS_UNICODE_PROIBIDAS

    assert set(CATEGORIAS_UNICODE_PROIBIDAS) == {"Cc", "Cf", "Zl", "Zp"}


# ======================================================================
# E4.9.6.3 — guardas de atribuição, forma JSON e supressões
# ======================================================================


def test_s22_a_reatribuicao_e_recusada_pelo_estado_do_mapeamento() -> None:
    """`INITIALIZATION != REASSIGNMENT`, provado na AST.

    Se alguém trocar a checagem por `"rules" in self.__dict__`, uma
    instância expirada volta a aceitar substituição — o escape que a
    auditoria da cadeia 78 mandou fechar.
    """
    arvore = ast.parse(
        (APP / "memory" / "models" / "retention_policy.py").read_text(encoding="utf-8")
    )
    (validador,) = [
        no
        for no in ast.walk(arvore)
        if isinstance(no, ast.FunctionDef) and no.name == "_validar_rules"
    ]
    executavel = [linha for linha in validador.body if not isinstance(linha, ast.Expr)]
    corpo = "\n".join(ast.unparse(linha) for linha in executavel)
    assert "has_identity" in corpo
    assert "self.__dict__" not in corpo


def test_s23_a_forma_do_json_e_validada_antes_da_conversao() -> None:
    """`JSON ITERABLE != CANONICAL JSON ARRAY`.

    `deserialize_rules` não pode voltar a converter direto: a forma dos
    seis campos é verificada por `regra_de_json` antes de qualquer
    `uuid.UUID()` ou construção de enum.
    """
    arvore = ast.parse(
        (APP / "memory" / "models" / "retention_policy.py").read_text(encoding="utf-8")
    )
    (desserializa,) = [
        no
        for no in ast.walk(arvore)
        if isinstance(no, ast.FunctionDef) and no.name == "deserialize_rules"
    ]
    corpo = ast.unparse(desserializa)
    assert "regra_de_json" in corpo
    assert "uuid.UUID" not in corpo
    assert "RetentionScopeKind(" not in corpo


def test_s24_nenhuma_supressao_de_typing_na_producao_da_retencao() -> None:
    """A histórica do `JSONB()` continua sendo exatamente uma."""
    marcador = "type:" + " ignore["
    contagens = {
        "schemas/retention.py": (APP / "memory" / "schemas" / "retention.py").read_text(
            encoding="utf-8"
        ),
        "models/retention_policy.py": (APP / "memory" / "models" / "retention_policy.py").read_text(
            encoding="utf-8"
        ),
        "repositories/retention_policy_repository.py": (
            APP / "memory" / "repositories" / "retention_policy_repository.py"
        ).read_text(encoding="utf-8"),
    }
    assert {nome: texto.count(marcador) for nome, texto in contagens.items()} == {
        "schemas/retention.py": 0,
        "models/retention_policy.py": 1,
        "repositories/retention_policy_repository.py": 0,
    }
    for nome, texto in contagens.items():
        assert "cast(" not in texto, nome


def test_s25_o_corretivo_nao_trouxe_capability_nova() -> None:
    """Reafirmação após a E4.9.6.3."""
    for modulo in NOVOS_MODULOS:
        caminho = APP.parent / (modulo.replace(".", "/") + ".py")
        executavel = _executavel(caminho)
        for termo in (
            "ErasureRecordRepository",
            "append_observed",
            "evaluate",
            "assess(",
            "trash",
            "purge",
            "scheduler",
            "datetime.now",
        ):
            assert termo not in executavel, f"{modulo}: {termo}"
