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
        if arquivo.name.startswith("c8a3f5017e94"):
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
    for proibido in ("casefold", "normalize", "unicodedata", "lower()", "upper()"):
        assert proibido not in corpo, proibido
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
