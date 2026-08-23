"""
Guardas estáticas da fronteira de conformidade (`E4.10`).

```text
SUBSTRING_SEARCH != PROOF_OF_ABSENCE_OF_PERSISTENCE
SUBSTRING_SEARCH != PROOF_OF_PURITY
```

Nenhuma guarda aqui procura substring quando o alvo é conceito de
código. Ausência de persistência é medida por base declarada e por
migration; pureza, por chamada na AST; supressão, por token.

Cada guarda tem um mutante `g99_*` que aplica **a mesma lógica** a uma
fonte sintética defeituosa. Guarda sem mutante é guarda cuja falha
ninguém verificou.
"""

import ast
import io
import pathlib
import tokenize

import pytest

from app.memory.models.compliance_enums import ComplianceCode, PolicyKind
from app.memory.schemas.compliance import CODIGOS_POR_POLITICA, SUJEITO_POR_POLITICA
from app.memory.services.compliance_evaluator import FAMILIA_DE_REGRA, OBSERVACAO_POR_POLITICA

APP = pathlib.Path(__file__).resolve().parents[2] / "app"
BACKEND = APP.parent

ENUMS = APP / "memory" / "models" / "compliance_enums.py"
CONTRATOS = APP / "memory" / "schemas" / "compliance.py"
AVALIADOR = APP / "memory" / "services" / "compliance_evaluator.py"
NOVOS = (ENUMS, CONTRATOS, AVALIADOR)

MUTACOES_INEQUIVOCAS = frozenset(
    {"commit", "flush", "merge", "add_all", "bulk_save_objects", "bulk_update"}
)
"""Nomes que só existem em persistência — nenhum colide com builtin."""

MUTACOES_DE_RECEPTOR = frozenset({"add", "delete", "execute", "update"})
"""Nomes ambíguos: só contam sobre um receptor de persistência.

```text
SET_ADD != SESSION_ADD
```

MEDIDO: a primeira versão desta guarda reprovou
`identificadores.add(regra.rule_id)` — um `set` local acumulando
`rule_id` para detectar duplicata. Proibir o nome sem olhar o receptor
proibiria estrutura de dados, não escrita.
"""

RECEPTORES_DE_PERSISTENCIA = frozenset(
    {"session", "sessao", "uow", "db", "conn", "connection", "engine", "repo", "repository"}
)


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


def _chamadas(arvore: ast.Module) -> set[str]:
    return {_nome_chamado(no) or "" for no in ast.walk(arvore) if isinstance(no, ast.Call)}


def _mutacoes(arvore: ast.Module) -> set[str]:
    """Escritas de persistência — nome inequívoco, ou nome sobre receptor.

    O receptor é a distinção, e não o nome do método: é a mesma lição
    que a guarda `g13` da cadeia 94 pagou ao contar `ligacao.execute` de
    um `SELECT` como DDL.
    """
    encontradas: set[str] = set()
    for no in ast.walk(arvore):
        if not isinstance(no, ast.Call):
            continue
        nome = _nome_chamado(no)
        if nome in MUTACOES_INEQUIVOCAS:
            encontradas.add(nome)
            continue
        if nome not in MUTACOES_DE_RECEPTOR or not isinstance(no.func, ast.Attribute):
            continue
        receptor = no.func.value
        alvo = receptor.id if isinstance(receptor, ast.Name) else getattr(receptor, "attr", "")
        if alvo.lower() in RECEPTORES_DE_PERSISTENCIA:
            encontradas.add(f"{alvo}.{nome}")
    return encontradas


def _classes_persistentes(arvore: ast.Module) -> list[str]:
    """Classes que herdam de uma base ORM ou declaram tabela.

    ```text
    DECLARED_TABLE = PERSISTENCE
    ```

    Medido por base declarada e por `__tablename__`, não pelo nome do
    arquivo: um modelo persistente chamado de outra coisa passaria numa
    busca por nome.
    """
    encontradas: list[str] = []
    for no in ast.walk(arvore):
        if not isinstance(no, ast.ClassDef):
            continue
        bases = {
            base.id if isinstance(base, ast.Name) else getattr(base, "attr", "")
            for base in no.bases
        }
        if bases & {"Base", "BaseModel", "DeclarativeBase"}:
            encontradas.append(no.name)
            continue
        for membro in no.body:
            if isinstance(membro, ast.Assign) and any(
                isinstance(alvo, ast.Name) and alvo.id == "__tablename__" for alvo in membro.targets
            ):
                encontradas.append(no.name)
    return encontradas


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
    """Supressões em COMENTÁRIO — docstring que as menciona não conta.

    ```text
    MENTIONED_IN_PROSE != APPLIED_AS_SUPPRESSION
    ```

    Lição literal da cadeia 94: uma guarda por substring reprovou a
    própria prosa que explicava por que a supressão não era necessária.
    """
    encontrados: list[int] = []
    with caminho.open("rb") as fonte:
        for token in tokenize.tokenize(io.BytesIO(fonte.read()).readline):
            if token.type != tokenize.COMMENT:
                continue
            if "type: ignore" in token.string or "noqa" in token.string:
                encontrados.append(token.start[0])
    return encontrados


# ----------------------------------------------------------------------
# g01 — nada é persistido
# ----------------------------------------------------------------------


def test_g01_nenhum_contrato_de_compliance_e_persistente():
    """`ComplianceFinding` e `ComplianceReport` são transitórios por
    contrato congelado (`E4_PRIMITIVE_OWNERSHIP` §4.5)."""
    for caminho in NOVOS:
        assert _classes_persistentes(_arvore(caminho)) == [], caminho.name


def test_g01_1_nenhuma_migration_cita_compliance():
    """`MIGRATION = NONE` — medido nos arquivos reais de migration."""
    versoes = BACKEND / "alembic" / "versions"
    infratores = [
        caminho.name
        for caminho in sorted(versoes.glob("*.py"))
        if "compliance" in caminho.read_text(encoding="utf-8").lower()
    ]
    assert infratores == []


def test_g01_2_a_e4_10_nao_criou_migration_propria():
    """RENOMEADA NA E4.11 — `GUARD_NAME != GUARD_MEASUREMENT`.

    O nome antigo prometia que a cabeça não mudava, e ela mudou: a E4.11
    criou `validated_experiences`, que é persistida por contrato. O que
    permanece verdadeiro, e é o que esta guarda sempre protegeu, é que a
    **E4.10** não criou migration nenhuma — nenhuma revisão do grafo cita
    compliance, e `test_g01_1` mede isso diretamente.

    A guarda passou a provar que a cabeça é ÚNICA e que a sucessora de
    `d5b31f7a08c4` é exatamente uma.
    """
    versoes = BACKEND / "alembic" / "versions"
    grafo: dict[str, str | None] = {}
    for caminho in sorted(versoes.glob("*.py")):
        arvore = _arvore(caminho)
        revisao = pai = None
        for no in ast.walk(arvore):
            if not isinstance(no, ast.AnnAssign | ast.Assign):
                continue
            alvo = no.target if isinstance(no, ast.AnnAssign) else no.targets[0]
            if not isinstance(alvo, ast.Name) or no.value is None:
                continue
            if isinstance(no.value, ast.Constant):
                if alvo.id == "revision":
                    revisao = no.value.value
                elif alvo.id == "down_revision":
                    pai = no.value.value
        if revisao:
            grafo[revisao] = pai
    sucessoras = [r for r, p in grafo.items() if p == "d5b31f7a08c4"]
    assert sucessoras == ["e7c25a91f4b3"], sucessoras
    sucessoras_e5 = [r for r, p in grafo.items() if p == "e7c25a91f4b3"]
    assert sucessoras_e5 == ["f8a91c2d4e60"], sucessoras_e5
    pais = {p for p in grafo.values() if p}
    folhas = sorted(r for r in grafo if r not in pais)
    # ATUALIZADO PELA E7.1: a folha passou a ser `b8c04e2fd137`
    # (orquestração). A guarda continua medindo folha ÚNICA — não
    # imobilidade da cadeia.
    assert folhas == ["b8c04e2fd137"], folhas


def test_g99_1_a_guarda_de_persistencia_detecta_um_modelo():
    tabela = "class F(Base):\n    __tablename__ = 'compliance_findings'\n"
    inerte = "@dataclass(frozen=True)\nclass F:\n    code: str\n"
    assert _classes_persistentes(ast.parse(tabela)) == ["F"]
    assert _classes_persistentes(ast.parse(inerte)) == []


# ----------------------------------------------------------------------
# g02 — a avaliação não escreve, não commita, não executa efeito
# ----------------------------------------------------------------------


def test_g02_a_avaliacao_nao_chama_nenhuma_mutacao():
    """`ZERO_WRITES · ZERO_COMMITS` — medido por chamada na AST."""
    for caminho in NOVOS:
        assert _mutacoes(_arvore(caminho)) == set(), caminho.name


def test_g02_1_a_avaliacao_nao_chama_o_executor_destrutivo():
    proibidas = {"attempt_effect", "consume_once", "append_observed", "resolve_target"}
    for caminho in NOVOS:
        assert not _chamadas(_arvore(caminho)) & proibidas, caminho.name


def test_g02_2_a_avaliacao_nao_altera_acessibilidade():
    proibidas = {"transition", "apply_transition", "set_state", "transicionar"}
    for caminho in NOVOS:
        assert not _chamadas(_arvore(caminho)) & proibidas, caminho.name


def test_g99_2_a_guarda_de_mutacao_detecta_escrita_e_ignora_estrutura():
    """Mutante bilateral: `session.add` é pego, `set.add` não."""
    escreve = "def f(session):\n    session.add(x)\n    session.commit()\n"
    acumula = "def f():\n    vistos = set()\n    vistos.add(1)\n    return vistos\n"
    assert _mutacoes(ast.parse(escreve)) == {"session.add", "commit"}
    assert _mutacoes(ast.parse(acumula)) == set()


# ----------------------------------------------------------------------
# g03 — sem sessão, sem repositório, sem relógio próprio
# ----------------------------------------------------------------------


def test_g03_a_avaliacao_nao_importa_sessao_nem_repositorio():
    """Tudo entra por argumento. Um repositório aqui convidaria a ler
    patrimônio dentro da função pura."""
    proibidos = ("sqlalchemy", "app.database", "app.repositories", "app.memory.repositories")
    for caminho in NOVOS:
        assert _importa_de(_arvore(caminho), proibidos) == set(), caminho.name


def test_g03_1_a_avaliacao_nao_tem_relogio_proprio():
    """`CLOCK_INJECTED = REQUIRED` — `now()` interno tornaria o teste
    dependente do relógio da máquina."""
    for caminho in NOVOS:
        assert not _chamadas(_arvore(caminho)) & {"now", "utcnow", "today", "time"}


def test_g03_2_o_avaliador_e_funcao_e_nao_classe_com_sessao():
    """Um manager com `__init__(session)` teria onde esconder I/O."""
    classes = [
        no.name
        for no in ast.walk(_arvore(AVALIADOR))
        if isinstance(no, ast.ClassDef)
        and any(
            isinstance(membro, ast.FunctionDef) and membro.name == "__init__" for membro in no.body
        )
    ]
    assert classes == []


def test_g99_3_a_guarda_de_relogio_detecta_datetime_now():
    fonte = "def f():\n    return datetime.now(UTC)\n"
    assert _chamadas(ast.parse(fonte)) & {"now"}


# ----------------------------------------------------------------------
# g04 — não altera política, não repara, não aprende
# ----------------------------------------------------------------------


def test_g04_a_fatia_nao_repara_nem_aprende():
    """`REPAIR_IMPLEMENTED = NO` e nenhum motor de aprendizado."""
    proibidos = ("repair", "fix", "heal", "learn", "train", "adjust_policy")
    infratores: list[str] = []
    for caminho in NOVOS:
        for no in ast.walk(_arvore(caminho)):
            definicao = isinstance(no, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
            if definicao and any(termo in no.name.lower() for termo in proibidos):
                infratores.append(f"{caminho.name}:{no.name}")
    assert infratores == []


def test_g04_1_a_fatia_nao_cria_superficie_de_execucao():
    """`PUBLIC_API = NONE`, `SCHEDULER = NONE`, `QUEUE = NONE`."""
    proibidos = ("APIRouter", "FastAPI", "BackgroundTasks", "Celery", "Scheduler", "Queue")
    infratores: list[str] = []
    for caminho in NOVOS:
        nomes = {no.id for no in ast.walk(_arvore(caminho)) if isinstance(no, ast.Name)} | {
            no.attr for no in ast.walk(_arvore(caminho)) if isinstance(no, ast.Attribute)
        }
        infratores.extend(f"{caminho.name}:{t}" for t in proibidos if t in nomes)
    assert infratores == []


def test_g04_2_a_fatia_nao_toca_a_e3():
    """Nenhuma mutação de patrimônio cognitivo nesta fronteira."""
    for caminho in NOVOS:
        assert _importa_de(_arvore(caminho), ("app.cognitive",)) == set(), caminho.name


def test_g99_4_a_guarda_de_reparo_detecta_uma_funcao():
    fonte = "def repair_finding(f):\n    return f\n"
    nomes = [no.name for no in ast.walk(ast.parse(fonte)) if isinstance(no, ast.FunctionDef)]
    assert any("repair" in nome for nome in nomes)


# ----------------------------------------------------------------------
# g05 — códigos diagnósticos fora do catálogo de exceções
# ----------------------------------------------------------------------


def test_g05_nenhum_codigo_de_compliance_entrou_no_catalogo_de_excecoes():
    """`FINDING != EXCEPTION` — a E3.10 congelou a separação."""
    catalogo = (APP / "memory" / "errors" / "codes.py").read_text(encoding="utf-8")
    assert "COMPLIANCE-" not in catalogo


def test_g05_1_nenhum_codigo_de_compliance_e_um_error_code():
    chamadas = _chamadas(_arvore(ENUMS))
    assert "ErrorCode" not in chamadas


def test_g05_2_os_codigos_sao_unicos_e_bem_formados():
    valores = [membro.value for membro in ComplianceCode]
    assert len(set(valores)) == len(valores)
    for valor in valores:
        familia, area, numero = valor.split("-")
        assert familia == "COMPLIANCE"
        assert area.isalpha() and area.isupper() and len(area) == 3
        assert numero.isdigit() and len(numero) == 3


def test_g99_5_a_guarda_de_catalogo_detecta_a_mistura():
    fonte = 'PIA_9001 = ErrorCode(code="COMPLIANCE-GOV-001")\n'
    assert "COMPLIANCE-" in fonte
    assert "ErrorCode" in _chamadas(ast.parse(fonte))


# ----------------------------------------------------------------------
# g06 — compatibilidade fechada entre os três vocabulários
# ----------------------------------------------------------------------


def test_g06_as_tres_correspondencias_sao_totais_e_biunivocas():
    for mapa in (SUJEITO_POR_POLITICA, FAMILIA_DE_REGRA, OBSERVACAO_POR_POLITICA):
        assert set(mapa) == set(PolicyKind), mapa
        assert len(set(mapa.values())) == len(PolicyKind), mapa


def test_g06_1_todo_codigo_pertence_a_exatamente_uma_familia():
    assert set(CODIGOS_POR_POLITICA) == set(PolicyKind)
    todos = [codigo for familia in CODIGOS_POR_POLITICA.values() for codigo in familia]
    assert len(todos) == len(set(todos)) == len(ComplianceCode)


def test_g06_2_as_correspondencias_sao_literais_e_nao_derivadas():
    """`dict` constante no módulo, não inferência por nome.

    Uma correspondência derivada de strings semelhantes mudaria sozinha
    ao renomear um membro — e a compatibilidade é decisão, não
    coincidência ortográfica.
    """
    constantes = {
        alvo.id
        for no in ast.walk(_arvore(CONTRATOS))
        if isinstance(no, ast.AnnAssign | ast.Assign)
        for alvo in ([no.target] if isinstance(no, ast.AnnAssign) else no.targets)
        if isinstance(alvo, ast.Name) and alvo.id.isupper()
    }
    assert {"SUJEITO_POR_POLITICA", "CODIGOS_POR_POLITICA"} <= constantes


def test_g99_6_a_guarda_de_correspondencia_detecta_um_buraco():
    incompleto = {PolicyKind.GOVERNANCE: 1, PolicyKind.ACCESSIBILITY: 2}
    assert set(incompleto) != set(PolicyKind)


# ----------------------------------------------------------------------
# g07 — sem escapes de tipagem
# ----------------------------------------------------------------------


def test_g07_nenhum_escape_de_tipagem_nos_arquivos_novos():
    proibidos = {"Any", "cast", "pickle", "asdict", "__dict__", "getattr", "setattr"}
    for caminho in NOVOS:
        arvore = _arvore(caminho)
        nomes = {no.id for no in ast.walk(arvore) if isinstance(no, ast.Name)} | {
            no.attr for no in ast.walk(arvore) if isinstance(no, ast.Attribute)
        }
        assert not nomes & proibidos, f"{caminho.name}: {nomes & proibidos}"


def test_g07_1_nenhuma_supressao_nos_arquivos_novos():
    for caminho in NOVOS:
        assert _supressoes(caminho) == [], caminho.name


def test_g99_7_a_guarda_de_supressao_distingue_comentario_de_docstring(tmp_path):
    """Mutante bilateral: o comentário é pego, a docstring não."""
    comentario = tmp_path / "com.py"
    comentario.write_text("x = f()  # type: ignore[arg-type]\n", encoding="utf-8")
    prosa = tmp_path / "sem.py"
    prosa.write_text('"""Não usamos type: ignore aqui."""\nx = 1\n', encoding="utf-8")
    assert _supressoes(comentario) == [1]
    assert _supressoes(prosa) == []


# ----------------------------------------------------------------------
# g08 — a fronteira não ganhou consumidor de produção
# ----------------------------------------------------------------------


def test_g08_o_avaliador_ainda_nao_tem_consumidor_de_producao():
    """A E4.10 entrega a fronteira; quem a consome é decisão posterior.

    ```text
    BOUNDARY_DELIVERED != CONSUMER_CREATED
    ```

    Medido por CHAMADA, não por definição — definir não é consumir, e a
    distinção é a mesma que o instrumento da E4.9.9.d aprendeu ao
    contrário.
    """
    consumidores = [
        str(caminho.relative_to(APP))
        for caminho in _fontes()
        if caminho != AVALIADOR and "avaliar_conformidade" in _chamadas(_arvore(caminho))
    ]
    assert consumidores == []


def test_g08_1_o_avaliador_de_retencao_e_consumido_e_nao_reimplementado():
    """A elegibilidade tem fonte única desde a E4.9.9.c."""
    assert "avaliar_retencao" in _chamadas(_arvore(AVALIADOR))
    proibidas = {"minimum_age_days", "_due_at", "_alcanca"}
    nomes = {no.attr for no in ast.walk(_arvore(AVALIADOR)) if isinstance(no, ast.Attribute)}
    assert not nomes & proibidas


def test_g99_8_a_guarda_de_consumidor_detecta_uma_chamada():
    fonte = "def f():\n    return avaliar_conformidade(subject=s)\n"
    assert "avaliar_conformidade" in _chamadas(ast.parse(fonte))


# ----------------------------------------------------------------------
# g09 — a documentação da fatia é alcançável
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    "caminho",
    [
        BACKEND / "docs" / "entregas" / "entrega-4" / "E4_10_COMPLIANCE_BOUNDARY.md",
        BACKEND / "README_BACKEND.md",
    ],
)
def test_g09_os_documentos_da_fatia_existem(caminho):
    assert caminho.is_file(), caminho


def test_g09_1_o_documento_e_referenciado_pelo_indice_canonico():
    """A prova formal é o checker de consistência documental; esta guarda
    falha mais cedo e diz o porquê."""
    indice = (BACKEND / "README_BACKEND.md").read_text(encoding="utf-8")
    assert "docs/entregas/entrega-4/E4_10_COMPLIANCE_BOUNDARY.md" in indice
