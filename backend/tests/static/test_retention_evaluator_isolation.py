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


def test_s07_o_avaliador_tem_exatamente_um_consumidor_autorizado() -> None:
    """RENOMEADA NA E4.10 — `GUARD_NAME != GUARD_MEASUREMENT`.

    O nome antigo prometia zero consumidores e anunciava a E4.9.9.d como
    a fatia que os traria. Ela não os trouxe: quem consome a AVALIAÇÃO de
    retenção é a fronteira de conformidade, e a E4.9.9.d deliberadamente
    não a consultou, porque

    ```text
    RETENTION_ASSESSMENT != DELETION_AUTHORITY
    ```

    A guarda ficou MAIS FORTE, não mais frouxa: antes exigia ZERO
    consumidores; agora exige EXATAMENTE UM, e nomeia qual. Um segundo
    passaria numa versão apenas relaxada com `permitidos`.

    ```text
    AUTHORIZED_CONSUMER = compliance_evaluator.py
    SECOND_CONSUMER = FORBIDDEN
    ```
    """
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
    assert infratores == ["memory/services/compliance_evaluator.py"], infratores


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


def test_s12_a_avaliacao_de_retencao_nao_e_autoridade_de_exclusao() -> None:
    """RENOMEADA NA E4.9.9.d, e a medição ficou MAIS FORTE.

    O nome antigo prometia que a fatia `d` não tinha começado. Ela
    começou, foi autorizada, e o que precisa continuar verdadeiro é
    outra coisa:

    ```text
    RETENTION_ASSESSMENT != DELETION_AUTHORITY
    LEGACY_PROTECTION = USER_BINDING, NOT AUTOMATIC_EFFECT
    ```

    A composição destrutiva **não** importa o avaliador. Acoplá-lo ao
    executor o transformaria numa segunda autorização, e a autoridade
    continua sendo a aprovação humana. A guarda mede exatamente esse
    não-acoplamento, que o nome antigo nem chegava a mencionar.
    """
    servico = APP / "memory" / "services" / "destructive_execution_service.py"
    assert servico.is_file(), "a composição final da E4.9 não está onde a guarda a procura"

    importados: set[str] = set()
    chamados: set[str] = set()
    for no in ast.walk(ast.parse(servico.read_text(encoding="utf-8"))):
        if isinstance(no, ast.ImportFrom) and no.module:
            importados.add(no.module)
        elif isinstance(no, ast.Call):
            alvo = no.func
            nome = alvo.id if isinstance(alvo, ast.Name) else getattr(alvo, "attr", None)
            if nome:
                chamados.add(nome)

    assert "app.memory.services.retention_evaluator" not in importados
    assert "avaliar_retencao" not in chamados


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


def test_s14_o_validador_canonico_da_colecao_e_reutilizado() -> None:
    """`COLLECTION_TYPE_CHECK != CANONICAL_COLLECTION_VALIDATION`.

    A cadeia 92 verificava `isinstance(rules, tuple)` e o tipo de cada
    item, e apresentava isso como validação da coleção. Não era:
    `validar_regras_retencao` é o contrato ÚNICO desde a E4.9.6.2 e
    recusa `rule_id` duplicado — que este avaliador precisa, porque
    indexa vencimentos por `rule_id`.

    Guarda estática; o comportamento está em `u36`–`u40`.
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
    assert "validar_regras_retencao" in chamadas


def test_s15_a_unicidade_das_regras_nao_foi_reimplementada() -> None:
    """Não copiar a lógica: duas fontes divergiriam na primeira mudança."""
    executavel = _executavel(APP / "memory" / "services" / "retention_evaluator.py")
    assert "duplicado na mesma versão" not in executavel
    assert "rule_ids_vistos" not in executavel


def test_s16_a_matriz_das_decisoes_vive_no_construtor_publico() -> None:
    """`PUBLIC_RESULT_CONSTRUCTOR_ENFORCES_DECISION_MATRIX`.

    Invariante que vive só na fábrica é contornável pelo construtor
    direto — nona vez que o projeto aplica a lição.
    """
    arvore = ast.parse(
        (APP / "memory" / "services" / "retention_evaluator.py").read_text(encoding="utf-8")
    )
    (classe,) = [
        no
        for no in ast.walk(arvore)
        if isinstance(no, ast.ClassDef) and no.name == "RetentionAssessment"
    ]
    metodos = {no.name for no in classe.body if isinstance(no, ast.FunctionDef)}
    assert "__post_init__" in metodos
    assert "_exigir_matriz_da_decisao" in metodos

    (matriz,) = [
        no
        for no in classe.body
        if isinstance(no, ast.FunctionDef) and no.name == "_exigir_matriz_da_decisao"
    ]
    citadas = {
        no.attr
        for no in ast.walk(matriz)
        if isinstance(no, ast.Attribute)
        and isinstance(no.value, ast.Name)
        and no.value.id == "RetentionAssessmentDecision"
    }
    assert citadas == {
        "POLICY_NOT_EFFECTIVE",
        "OUT_OF_SCOPE",
        "PRESERVE_LEGACY_PROTECTED",
        "NOT_YET_DUE",
        "ASSESS_AND_INFORM",
    }, citadas


def test_s17_os_ids_do_resultado_usam_o_contrato_opaco_existente() -> None:
    """Mesmo validador de `rule_id`, não um paralelo mais frouxo."""
    arvore = ast.parse(
        (APP / "memory" / "services" / "retention_evaluator.py").read_text(encoding="utf-8")
    )
    (classe,) = [
        no
        for no in ast.walk(arvore)
        if isinstance(no, ast.ClassDef) and no.name == "RetentionAssessment"
    ]
    chamadas = {
        no.func.id
        for no in ast.walk(classe)
        if isinstance(no, ast.Call) and isinstance(no.func, ast.Name)
    }
    assert "validar_identificador_opaco" in chamadas


def test_s99_3_a_guarda_do_validador_canonico_detecta_verificacao_fraca() -> None:
    """§ mutante — `s14` é a única prova estática desta propriedade."""

    def chamadas(fonte: str) -> set[str]:
        return {
            no.func.id
            for no in ast.walk(ast.parse(fonte))
            if isinstance(no, ast.Call) and isinstance(no.func, ast.Name)
        }

    canonico = (
        "def avaliar_retencao(rules):\n"
        "    if rules:\n"
        "        validar_regras_retencao('rules', rules)\n"
    )
    fraco = (
        "def avaliar_retencao(rules):\n"
        "    for r in rules:\n"
        "        if not isinstance(r, RetentionRule):\n"
        "            raise TypeError('x')\n"
    )
    assert "validar_regras_retencao" in chamadas(canonico)
    assert "validar_regras_retencao" not in chamadas(fraco)


def test_s99_4_a_guarda_da_matriz_detecta_decisao_nao_coberta() -> None:
    """§ mutante — `s16` é a única prova estática de cobertura das cinco."""

    def cobertas(fonte: str) -> set[str]:
        return {
            no.attr
            for no in ast.walk(ast.parse(fonte))
            if isinstance(no, ast.Attribute)
            and isinstance(no.value, ast.Name)
            and no.value.id == "D"
        }

    completa = (
        "def m():\n"
        "    a = D.POLICY_NOT_EFFECTIVE\n"
        "    b = D.OUT_OF_SCOPE\n"
        "    c = D.PRESERVE_LEGACY_PROTECTED\n"
        "    d = D.NOT_YET_DUE\n"
        "    e = D.ASSESS_AND_INFORM\n"
    )
    faltando = completa.replace("    d = D.NOT_YET_DUE\n", "")
    assert len(cobertas(completa)) == 5
    assert len(cobertas(faltando)) == 4
