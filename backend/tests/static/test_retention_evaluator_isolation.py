"""
Guardas de **isolamento** do avaliador de retenção (`E4.9.9.c`).

```text
SCHEDULER   = NONE
DISPOSITION = NONE
PERSISTENCE = NONE
EVALUATION != DISPOSITION
```
"""

import ast
import pathlib

APP = pathlib.Path(__file__).resolve().parents[2] / "app"

NOVOS = (
    APP / "memory" / "models" / "retention_assessment_enums.py",
    APP / "memory" / "services" / "retention_evaluator.py",
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


def test_s01_nenhum_agendador_worker_ou_disparo_automatico() -> None:
    """`SCHEDULER = NONE` — a função só responde quando chamada."""
    proibidos = (
        "Celery",
        "celery",
        "apscheduler",
        "scheduler",
        "cron",
        "BackgroundTasks",
        "threading",
        "asyncio",
        "Timer",
        "sleep",
    )
    for caminho in NOVOS:
        executavel = _executavel(caminho)
        for termo in proibidos:
            assert termo not in executavel, f"{caminho.name}: {termo}"


def test_s02_nenhum_relogio_interno() -> None:
    """`CLOCK_INJECTED = REQUIRED` — um default seria `now()` disfarçado."""
    for caminho in NOVOS:
        arvore = ast.parse(caminho.read_text(encoding="utf-8"))
        for no in ast.walk(arvore):
            if isinstance(no, ast.Attribute):
                assert no.attr not in {"now", "utcnow", "today"}, caminho.name
            if isinstance(no, ast.Name):
                assert no.id not in {"time", "monotonic"}, caminho.name


def test_s03_nenhuma_persistencia_sessao_ou_repositorio() -> None:
    for caminho in NOVOS:
        executavel = _executavel(caminho)
        for termo in (
            "Session",
            "Repository",
            "sqlalchemy",
            "mapped_column",
            "Mapped",
            "select(",
            "UnitOfWork",
            "engine",
        ):
            assert termo not in executavel, f"{caminho.name}: {termo}"


def test_s04_nenhuma_enumeracao_de_patrimonio() -> None:
    """A função responde sobre UM candidato; não varre nada."""
    for caminho in NOVOS:
        executavel = _executavel(caminho)
        for termo in ("list_all", "scan", "iterate_patrimony", "find_all", "query"):
            assert termo not in executavel, f"{caminho.name}: {termo}"


def test_s05_nenhuma_disposicao_aprovacao_ou_recibo() -> None:
    """`EVALUATION != DISPOSITION`."""
    for caminho in NOVOS:
        executavel = _executavel(caminho)
        for termo in (
            "DestructiveApprovalProposal",
            "DestructiveApprovalEnvelope",
            "ApprovalRecord",
            "ErasureRecord",
            "ErasureEffectPort",
            "ErasureEffectRequest",
            "append_observed",
            "consume_once",
            "DestructiveOperation",
        ):
            assert termo not in executavel, f"{caminho.name}: {termo}"


def test_s06_nenhuma_rede_filesystem_ou_shell() -> None:
    for caminho in NOVOS:
        executavel = _executavel(caminho)
        for termo in ("requests", "httpx", "boto3", "socket", "subprocess", "open(", "shutil"):
            assert termo not in executavel, f"{caminho.name}: {termo}"


def test_s07_nenhum_consumidor_de_producao() -> None:
    """Contrato sem consumidor é o estado correto — a E4.9.9.d o consumirá."""
    modulos = {
        "app.memory.models.retention_assessment_enums",
        "app.memory.services.retention_evaluator",
    }
    permitidos = set(NOVOS) | {
        APP / "memory" / "models" / "__init__.py",
        APP / "memory" / "services" / "__init__.py",
    }
    infratores = [
        str(p.relative_to(APP))
        for p in _fontes()
        if p not in permitidos and modulos & _importados(p)
    ]
    assert infratores == []


def test_s08_a_acao_de_expiracao_nao_foi_ampliada() -> None:
    """`RetentionExpiryAction` com um único membro é a prova de que
    vencimento nunca dispôs de nada."""
    arvore = ast.parse(
        (APP / "memory" / "models" / "retention_enums.py").read_text(encoding="utf-8")
    )
    (classe,) = [
        no
        for no in ast.walk(arvore)
        if isinstance(no, ast.ClassDef) and no.name == "RetentionExpiryAction"
    ]
    membros = [
        no.targets[0].id
        for no in classe.body
        if isinstance(no, ast.Assign) and isinstance(no.targets[0], ast.Name)
    ]
    assert membros == ["ASSESS_AND_INFORM"]


def test_s09_a_ancora_continua_unica() -> None:
    """`updated_at` se move por transição de acessibilidade; ancorar nele
    faria um objeto reclassificado rejuvenescer."""
    executavel = _executavel(APP / "memory" / "services" / "retention_evaluator.py")
    assert "updated_at" not in executavel
    assert "created_at" in executavel


def test_s10_a_precedencia_verifica_vigencia_antes_do_prazo() -> None:
    """Fixada na AST: a ordem dos `return` no corpo da função.

    Esta guarda é a única prova ESTÁTICA da ordem; o comportamento está
    em `u03`–`u11`, que exercitam os cinco degraus.
    """
    arvore = ast.parse(
        (APP / "memory" / "services" / "retention_evaluator.py").read_text(encoding="utf-8")
    )
    (funcao,) = [
        no
        for no in ast.walk(arvore)
        if isinstance(no, ast.FunctionDef) and no.name == "avaliar_retencao"
    ]
    # Ordenado por LINHA, não por `ast.walk` — walk é em largura, e
    # devolveria o `return` final antes dos que estão dentro de `if`.
    # Uma guarda que confundisse as duas mediria outra coisa.
    ordem = [
        no.attr
        for no in sorted(
            (
                n
                for n in ast.walk(funcao)
                if isinstance(n, ast.Attribute)
                and isinstance(n.value, ast.Name)
                and n.value.id == "RetentionAssessmentDecision"
            ),
            key=lambda n: (n.lineno, n.col_offset),
        )
    ]
    assert ordem == [
        "POLICY_NOT_EFFECTIVE",
        "POLICY_NOT_EFFECTIVE",
        "OUT_OF_SCOPE",
        "PRESERVE_LEGACY_PROTECTED",
        "NOT_YET_DUE",
        "ASSESS_AND_INFORM",
    ], ordem


def test_s11_o_prazo_efetivo_e_o_maximo_e_nao_o_minimo() -> None:
    """Uma regra curta não pode neutralizar outra que exige mais tempo.

    Guarda estática; o comportamento está em `u12`–`u15`.
    """
    arvore = ast.parse(
        (APP / "memory" / "services" / "retention_evaluator.py").read_text(encoding="utf-8")
    )
    (funcao,) = [
        no
        for no in ast.walk(arvore)
        if isinstance(no, ast.FunctionDef) and no.name == "avaliar_retencao"
    ]
    chamadas = {
        no.func.id
        for no in ast.walk(funcao)
        if isinstance(no, ast.Call) and isinstance(no.func, ast.Name)
    }
    assert "max" in chamadas
    assert "min" not in chamadas


def test_s12_e4_9_9_d_nao_foi_iniciada() -> None:
    ausentes = ("DestructiveExecutionService", "comparar_com_snapshot")
    infratores: list[str] = []
    for caminho in _fontes():
        arvore = ast.parse(caminho.read_text(encoding="utf-8"))
        for no in ast.walk(arvore):
            if (
                isinstance(no, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
                and no.name in ausentes
            ):
                infratores.append(f"{caminho.name}:{no.name}")
    assert infratores == []


def test_s13_e3_intocada_pelos_modulos_novos() -> None:
    for caminho in NOVOS:
        assert not any(m.startswith("app.cognitive") for m in _importados(caminho))


def test_s99_1_a_guarda_de_precedencia_detecta_ordem_trocada() -> None:
    """§ mutante — `s10` é a única prova estática da ordem."""

    def ordem(fonte: str) -> list[str]:
        return [
            no.attr
            for no in sorted(
                (
                    n
                    for n in ast.walk(ast.parse(fonte))
                    if isinstance(n, ast.Attribute)
                    and isinstance(n.value, ast.Name)
                    and n.value.id == "D"
                ),
                key=lambda n: (n.lineno, n.col_offset),
            )
        ]

    correta = (
        "def f():\n"
        "    if a: return D.OUT_OF_SCOPE\n"
        "    if b: return D.PRESERVE_LEGACY_PROTECTED\n"
    )
    trocada = (
        "def f():\n"
        "    if b: return D.PRESERVE_LEGACY_PROTECTED\n"
        "    if a: return D.OUT_OF_SCOPE\n"
    )
    assert ordem(correta) == ["OUT_OF_SCOPE", "PRESERVE_LEGACY_PROTECTED"]
    assert ordem(trocada) != ordem(correta)


def test_s99_2_a_guarda_do_maximo_detecta_min_introduzido() -> None:
    """§ mutante — `s11` é a única prova estática desta propriedade."""

    def usa(fonte: str) -> set[str]:
        return {
            no.func.id
            for no in ast.walk(ast.parse(fonte))
            if isinstance(no, ast.Call) and isinstance(no.func, ast.Name)
        }

    com_max = "def f(v):\n    return max(v)\n"
    com_min = "def f(v):\n    return min(v)\n"
    assert "max" in usa(com_max) and "min" not in usa(com_max)
    assert "min" in usa(com_min)
