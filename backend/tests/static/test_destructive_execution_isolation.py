"""
Guardas estáticas da composição destrutiva (`E4.9.9.d`).

```text
SUBSTRING_SEARCH != PROOF_OF_CONSUMPTION
SUBSTRING_SEARCH != PROOF_OF_ORDER
SUBSTRING_SEARCH != PROOF_OF_ABSENCE_OF_ADAPTER
```

Nenhuma guarda aqui procura substring quando o alvo é conceito de
código. Consumo é medido por **chamada** na AST; ordem, por posição de
origem `(lineno, col_offset)`; ausência de adaptador, por **corpo** de
método; contrato do recibo, por schema.

Cada guarda tem um mutante `g99_*` que aplica **a mesma lógica** a uma
fonte sintética defeituosa. Guarda sem mutante é guarda cuja falha
ninguém verificou.
"""

import ast
import pathlib

import pytest

from app.memory.schemas.destructive_approval import SafeTargetSnapshot
from app.memory.services.destructive_execution_service import CAMPOS_DO_BINDING

APP = pathlib.Path(__file__).resolve().parents[2] / "app"
TESTES = pathlib.Path(__file__).resolve().parents[1]

SERVICO = APP / "memory" / "services" / "destructive_execution_service.py"
CONTRATOS = APP / "memory" / "schemas" / "destructive_execution.py"
VOCABULARIOS = APP / "memory" / "models" / "destructive_execution_enums.py"
NOVOS = (SERVICO, CONTRATOS, VOCABULARIOS)

METODOS_COMPOSTOS = ("consume_once", "resolve_target", "attempt_effect", "append_observed")
"""Os quatro contratos que esta fatia compõe pela primeira vez."""


def _fontes() -> list[pathlib.Path]:
    return [p for p in sorted(APP.rglob("*.py")) if "__pycache__" not in p.parts]


def _fontes_de_teste() -> list[pathlib.Path]:
    return [p for p in sorted(TESTES.rglob("*.py")) if "__pycache__" not in p.parts]


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


def _modulos_que_chamam(arvores: dict[str, ast.Module], metodo: str) -> set[str]:
    encontrados = set()
    for rotulo, arvore in arvores.items():
        for no in ast.walk(arvore):
            if isinstance(no, ast.Call) and _nome_chamado(no) == metodo:
                encontrados.add(rotulo)
                break
    return encontrados


def _classes_com_corpo(arvores: dict[str, ast.Module], metodos: tuple[str, ...]) -> list[str]:
    """Classes que IMPLEMENTAM o método — `Protocol` com `...` não conta.

    ```text
    DECLARED_BOUNDARY != CONCRETE_ADAPTER
    ```
    """
    encontradas: list[str] = []
    for rotulo, arvore in arvores.items():
        for no in ast.walk(arvore):
            if not isinstance(no, ast.ClassDef):
                continue
            if any(isinstance(base, ast.Name) and base.id == "Protocol" for base in no.bases):
                continue
            for membro in no.body:
                if not isinstance(membro, ast.FunctionDef | ast.AsyncFunctionDef):
                    continue
                if membro.name not in metodos:
                    continue
                corpo = [
                    linha
                    for linha in membro.body
                    if not (isinstance(linha, ast.Expr) and isinstance(linha.value, ast.Constant))
                ]
                if corpo:
                    encontradas.append(f"{rotulo}:{no.name}.{membro.name}")
    return encontradas


def _ordem_na_funcao(arvore: ast.Module, primeiro: str, segundo: str) -> list[str]:
    """Funções em que `primeiro` precede `segundo` na ordem DE ORIGEM.

    ```text
    WALK_ORDER != SOURCE_ORDER
    ```

    `ast.walk` percorre em largura e devolveria as chamadas fora da ordem
    do código-fonte — a lição que a E4.9.9.c pagou na guarda `s10`.
    """
    aprovadas: list[str] = []
    for no in ast.walk(arvore):
        if not isinstance(no, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        chamadas = sorted(
            (
                (filho.lineno, filho.col_offset, _nome_chamado(filho))
                for filho in ast.walk(no)
                if isinstance(filho, ast.Call)
            ),
            key=lambda item: (item[0], item[1]),
        )
        nomes = [nome for _, _, nome in chamadas]
        if primeiro in nomes and segundo in nomes and nomes.index(primeiro) < nomes.index(segundo):
            aprovadas.append(no.name)
    return aprovadas


def _construcoes_de_referencia(arvore: ast.Module) -> list[int]:
    """Linhas que montam a referência de resolução por concatenação.

    Procura f-string cujo primeiro trecho literal comece com `approval:`
    — a forma que uma concatenação espalhada teria. O helper puro é o
    único lugar autorizado, e o recibo é append-only: uma referência
    gravada com formato divergente não se corrige depois.
    """
    linhas: list[int] = []
    for no in ast.walk(arvore):
        if not isinstance(no, ast.JoinedStr):
            continue
        for parte in no.values:
            if isinstance(parte, ast.Constant) and isinstance(parte.value, str):
                if parte.value.startswith("approval:"):
                    linhas.append(no.lineno)
                break
    return linhas


TERMOS_PROIBIDOS = (
    "Any",
    "cast",
    "pickle",
    "asdict",
    "__dict__",
    "monkeypatch",
)


def _termos_presentes(arvore: ast.Module) -> set[str]:
    """Nomes proibidos usados como CÓDIGO — docstring e comentário não contam."""
    presentes: set[str] = set()
    for no in ast.walk(arvore):
        nome = None
        if isinstance(no, ast.Name):
            nome = no.id
        elif isinstance(no, ast.Attribute):
            nome = no.attr
        elif isinstance(no, ast.ImportFrom | ast.Import):
            for apelido in no.names:
                if apelido.name in TERMOS_PROIBIDOS:
                    presentes.add(apelido.name)
        if nome in TERMOS_PROIBIDOS:
            presentes.add(nome)
    return presentes


# ----------------------------------------------------------------------
# g01 — consumidor único e autorizado
# ----------------------------------------------------------------------


@pytest.mark.parametrize("metodo", METODOS_COMPOSTOS)
def test_g01_o_servico_e_o_unico_consumidor_de_producao(metodo):
    """EXATAMENTE um consumidor por contrato, e ele é a composição.

    ```text
    AUTHORIZED_CONSUMER = destructive_execution_service.py
    SECOND_CONSUMER = FORBIDDEN
    ```

    Medido por **chamada** na AST. A definição do método no repositório
    ou no `Protocol` não é chamada, e por isso não conta.
    """
    arvores = {
        str(caminho.relative_to(APP)): _arvore(caminho)
        for caminho in _fontes()
        if caminho.name
        not in (
            "approval_record_repository.py",
            "erasure_record_repository.py",
            "erasure_effect.py",
            "erasure_target.py",
        )
    }
    assert _modulos_que_chamam(arvores, metodo) == {
        "memory/services/destructive_execution_service.py"
    }


def test_g99_1_a_guarda_de_consumidor_detecta_um_segundo():
    fonte = "class Outro:\n    def agir(self):\n        self.repo.consume_once(envelope)\n"
    arvores = {"intruso.py": ast.parse(fonte)}
    assert _modulos_que_chamam(arvores, "consume_once") == {"intruso.py"}


# ----------------------------------------------------------------------
# g02 — nenhum adaptador concreto em produção
# ----------------------------------------------------------------------


def test_g02_nenhum_adaptador_concreto_de_efeito_ou_resolucao():
    """`PRODUCTION_EFFECT_ADAPTER = NONE`, medido por corpo de método."""
    arvores = {str(c.relative_to(APP)): _arvore(c) for c in _fontes()}
    assert _classes_com_corpo(arvores, ("attempt_effect", "resolve_target")) == []


def test_g99_2_a_guarda_de_adaptador_distingue_protocolo_de_implementacao():
    """Mutante bilateral: o `Protocol` passa, o adaptador não."""
    protocolo = "class P(Protocol):\n    def attempt_effect(self, r):\n        ...\n"
    adaptador = "class A:\n    def attempt_effect(self, r):\n        return apagar(r)\n"
    assert _classes_com_corpo({"p.py": ast.parse(protocolo)}, ("attempt_effect",)) == []
    assert _classes_com_corpo({"a.py": ast.parse(adaptador)}, ("attempt_effect",)) == [
        "a.py:A.attempt_effect"
    ]


# ----------------------------------------------------------------------
# g03 — commit precede o efeito no fluxo executável
# ----------------------------------------------------------------------


def test_g03_o_commit_precede_lexicalmente_o_efeito():
    """`EFFECT_BEFORE_CONSUMPTION_COMMIT = FORBIDDEN`.

    A precedência é medida **dentro da mesma função**: as duas chamadas
    vivem em `execute`, e é por isso que a ordem é verificável sem ler
    várias funções.
    """
    assert _ordem_na_funcao(_arvore(SERVICO), "commit", "attempt_effect") == ["execute"]


def test_g99_3_a_guarda_de_ordem_detecta_a_inversao():
    invertida = (
        "def execute(self):\n"
        "    r = self.port.attempt_effect(pedido)\n"
        "    uow.commit()\n"
        "    return r\n"
    )
    correta = (
        "def execute(self):\n"
        "    uow.commit()\n"
        "    r = self.port.attempt_effect(pedido)\n"
        "    return r\n"
    )
    assert _ordem_na_funcao(ast.parse(invertida), "commit", "attempt_effect") == []
    assert _ordem_na_funcao(ast.parse(correta), "commit", "attempt_effect") == ["execute"]


def test_g99_3_1_a_guarda_de_ordem_usa_ordem_de_origem_e_nao_de_walk():
    """`WALK_ORDER != SOURCE_ORDER` — a armadilha da E4.9.9.c.

    O `commit()` está aninhado num `with` e o `attempt_effect` no corpo
    plano da função. Em largura, o menos profundo sairia primeiro e a
    guarda leria a ordem ao contrário.
    """
    fonte = (
        "def execute(self):\n"
        "    with uow() as u:\n"
        "        u.commit()\n"
        "    return self.port.attempt_effect(pedido)\n"
    )
    assert _ordem_na_funcao(ast.parse(fonte), "commit", "attempt_effect") == ["execute"]


# ----------------------------------------------------------------------
# g04 — sem API, worker, fila, scheduler ou outbox
# ----------------------------------------------------------------------


def test_g04_a_fatia_nao_cria_superficie_de_execucao():
    """`PUBLIC_API = NONE`, `SCHEDULER = NONE`, `QUEUE = NONE`."""
    proibidos = (
        "APIRouter",
        "FastAPI",
        "BackgroundTasks",
        "Celery",
        "Scheduler",
        "Outbox",
        "Queue",
    )
    infratores: list[str] = []
    for caminho in NOVOS:
        presentes = _termos_de_codigo(_arvore(caminho), proibidos)
        infratores.extend(f"{caminho.name}:{termo}" for termo in presentes)
    assert infratores == []


def _termos_de_codigo(arvore: ast.Module, termos: tuple[str, ...]) -> set[str]:
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
    return encontrados


def test_g99_4_a_guarda_de_superficie_detecta_um_router():
    fonte = "from fastapi import APIRouter\nrouter = APIRouter()\n"
    assert _termos_de_codigo(ast.parse(fonte), ("APIRouter",)) == {"APIRouter"}


# ----------------------------------------------------------------------
# g05 — sem escapes de tipagem nem reflexão
# ----------------------------------------------------------------------


def test_g05_nenhum_escape_de_tipagem_nos_arquivos_novos():
    """`Any`, `cast`, `pickle`, `asdict`, `__dict__` — nenhum."""
    for caminho in NOVOS:
        assert _termos_presentes(_arvore(caminho)) == set(), caminho.name


def _supressoes(caminho: pathlib.Path) -> list[int]:
    """Supressões em COMENTÁRIO — docstring que as menciona não conta.

    ```text
    MENTIONED_IN_PROSE != APPLIED_AS_SUPPRESSION
    ```

    A primeira versão desta guarda procurava a substring no arquivo
    inteiro e acusou a própria docstring que EXPLICA por que o
    estreitamento existe para não precisar de `cast` nem `type: ignore`.
    Uma guarda que proíbe falar do problema é a guarda errada — e é
    exatamente o caso em que substring isolada não prova nada.

    A leitura passou a ser por **token**: só o que o tokenizador
    classifica como `COMMENT` é supressão.
    """
    import io
    import tokenize

    encontrados: list[int] = []
    with caminho.open("rb") as fonte:
        for token in tokenize.tokenize(io.BytesIO(fonte.read()).readline):
            if token.type != tokenize.COMMENT:
                continue
            if "type: ignore" in token.string or "noqa" in token.string:
                encontrados.append(token.start[0])
    return encontrados


def test_g05_1_nenhum_type_ignore_nos_arquivos_novos():
    """Supressão é comentário, e por isso é lida como token."""
    for caminho in NOVOS:
        assert _supressoes(caminho) == [], caminho.name


def test_g99_5_1_a_guarda_de_supressao_distingue_comentario_de_docstring():
    """Mutante bilateral: o comentário é pego, a docstring não."""
    import tempfile

    with tempfile.TemporaryDirectory() as pasta:
        comentario = pathlib.Path(pasta) / "com.py"
        comentario.write_text("x = f()  # type: ignore[arg-type]\n", encoding="utf-8")
        prosa = pathlib.Path(pasta) / "sem.py"
        prosa.write_text('"""Não usamos type: ignore aqui."""\nx = 1\n', encoding="utf-8")
        assert _supressoes(comentario) == [1]
        assert _supressoes(prosa) == []


def test_g99_5_a_guarda_de_escape_detecta_cast():
    fonte = "from typing import cast\nx = cast(int, y)\n"
    assert "cast" in _termos_presentes(ast.parse(fonte))


# ----------------------------------------------------------------------
# g06 — sem relógio local e sem `set` onde a ordem importa
# ----------------------------------------------------------------------


def test_g06_o_servico_nao_tem_relogio_proprio():
    """Todo instante vem do banco ou do desfecho observado.

    ```text
    CLOCK_IS_OBSERVED, NEVER_INVENTED
    ```
    """
    chamados = {_nome_chamado(no) for no in ast.walk(_arvore(SERVICO)) if isinstance(no, ast.Call)}
    assert not chamados & {"now", "utcnow", "today", "time"}


def test_g06_1_nenhuma_colecao_ordenada_vira_set():
    """`set` perderia a ordem aprovada — e a ordem faz parte do binding."""
    for caminho in (SERVICO, CONTRATOS):
        for no in ast.walk(_arvore(caminho)):
            if isinstance(no, ast.Call) and _nome_chamado(no) in ("sorted", "frozenset"):
                # `sorted` reordenaria; `frozenset` só é aceitável em
                # constante de módulo, e a guarda `g06_2` fixa quais.
                assert caminho is CONTRATOS, f"{caminho.name}: {_nome_chamado(no)}"


def test_g06_2_os_unicos_conjuntos_sao_constantes_de_vocabulario():
    conjuntos = [
        alvo.id
        for no in ast.walk(_arvore(CONTRATOS))
        if isinstance(no, ast.Assign)
        for alvo in no.targets
        if isinstance(alvo, ast.Name)
        and isinstance(no.value, ast.Call)
        and _nome_chamado(no.value) == "frozenset"
    ]
    assert conjuntos == ["RAZOES_DE_LOTE"]


def test_g99_6_a_guarda_de_relogio_detecta_datetime_now():
    fonte = "def f():\n    return datetime.now(UTC)\n"
    chamados = {_nome_chamado(no) for no in ast.walk(ast.parse(fonte)) if isinstance(no, ast.Call)}
    assert chamados & {"now"}


# ----------------------------------------------------------------------
# g07 — a referência de resolução tem um único ponto de montagem
# ----------------------------------------------------------------------


def test_g07_a_referencia_de_resolucao_nasce_num_helper_unico():
    """Concatenação espalhada divergiria na primeira mudança de formato."""
    assert _construcoes_de_referencia(_arvore(SERVICO)) == []
    assert len(_construcoes_de_referencia(_arvore(CONTRATOS))) == 1


def test_g99_7_a_guarda_de_referencia_detecta_concatenacao_solta():
    fonte = 'def f(i):\n    return f"approval:{i}:governance-resolution"\n'
    assert len(_construcoes_de_referencia(ast.parse(fonte))) == 1


# ----------------------------------------------------------------------
# g08 — nenhum digest, hash ou identidade fabricada
# ----------------------------------------------------------------------


def test_g08_nenhum_digest_ou_uuid_fabricado():
    """`FABRICATED_RULE_IDENTITY = FORBIDDEN`.

    Nem `hashlib`, nem `uuid4`, nem `uuid5`: as três seriam formas de
    inventar a identidade da regra que o §6 proíbe.
    """
    proibidos = ("sha256", "md5", "blake2b", "uuid4", "uuid5", "uuid3", "hexdigest")
    for caminho in NOVOS:
        assert _termos_de_codigo(_arvore(caminho), proibidos) == set(), caminho.name


def test_g99_8_a_guarda_de_digest_detecta_uuid5():
    fonte = "import uuid\nx = uuid.uuid5(uuid.NAMESPACE_DNS, regra)\n"
    assert _termos_de_codigo(ast.parse(fonte), ("uuid5",)) == {"uuid5"}


# ----------------------------------------------------------------------
# g09 — os sete campos comparados são os do contrato real
# ----------------------------------------------------------------------


def test_g09_a_lista_de_campos_do_binding_acompanha_o_snapshot():
    """Enumeração literal, fixada contra os campos reais.

    `dataclasses.fields` daria a mesma lista hoje e mudaria sozinho
    amanhã. A guarda existe para que a mudança seja uma decisão.
    """
    assert [atributo for _, atributo in CAMPOS_DO_BINDING] == list(
        SafeTargetSnapshot.__dataclass_fields__
    )


def test_g99_9_a_guarda_de_campos_detecta_omissao():
    campos = [atributo for _, atributo in CAMPOS_DO_BINDING][:-1]
    assert campos != list(SafeTargetSnapshot.__dataclass_fields__)


# ----------------------------------------------------------------------
# g10 — o sandbox vive só em tests/
# ----------------------------------------------------------------------


def test_g10_nenhuma_classe_sandbox_e_exportada_por_app():
    """Os únicos `attempt_effect`/`resolve_target` com corpo estão em `tests/`."""
    producao = {str(c.relative_to(APP)): _arvore(c) for c in _fontes()}
    assert _classes_com_corpo(producao, ("attempt_effect", "resolve_target")) == []

    testes = {str(c.relative_to(TESTES)): _arvore(c) for c in _fontes_de_teste()}
    implementacoes = _classes_com_corpo(testes, ("attempt_effect", "resolve_target"))
    assert implementacoes, "o sandbox precisa existir para que a separação signifique algo"


def test_g10_1_nenhum_modulo_de_producao_importa_de_tests():
    for caminho in _fontes():
        for no in ast.walk(_arvore(caminho)):
            if isinstance(no, ast.ImportFrom) and no.module:
                assert not no.module.startswith("tests"), caminho.name


def test_g99_10_a_guarda_de_sandbox_detecta_import_invertido():
    fonte = "from tests.helpers.destructive_execution import envelope\n"
    modulos = [
        no.module
        for no in ast.walk(ast.parse(fonte))
        if isinstance(no, ast.ImportFrom) and no.module
    ]
    assert any(modulo.startswith("tests") for modulo in modulos)


# ----------------------------------------------------------------------
# g11 — o serviço não importa a E3 nem o avaliador de retenção
# ----------------------------------------------------------------------


def test_g11_o_servico_nao_importa_a_e3():
    """Nenhuma mutação de patrimônio cognitivo nesta composição."""
    for no in ast.walk(_arvore(SERVICO)):
        if isinstance(no, ast.ImportFrom) and no.module:
            assert not no.module.startswith("app.cognitive")


def test_g11_1_o_servico_nao_importa_o_avaliador_de_retencao():
    """`RETENTION_ASSESSMENT != DELETION_AUTHORITY`."""
    importados = {
        no.module
        for no in ast.walk(_arvore(SERVICO))
        if isinstance(no, ast.ImportFrom) and no.module
    }
    assert "app.memory.services.retention_evaluator" not in importados


def test_g99_11_a_guarda_de_acoplamento_detecta_o_import():
    fonte = "from app.memory.services.retention_evaluator import avaliar_retencao\n"
    importados = {
        no.module
        for no in ast.walk(ast.parse(fonte))
        if isinstance(no, ast.ImportFrom) and no.module
    }
    assert "app.memory.services.retention_evaluator" in importados


# ----------------------------------------------------------------------
# g12 — o contrato do recibo não tem onde guardar localizador
# ----------------------------------------------------------------------


def test_g12_nenhum_resultado_tem_campo_de_localizador_ou_capacidade():
    """Medido por **schema**: os nomes de campo das dataclasses novas."""
    proibidos = {
        "transient_locator",
        "capability",
        "locator",
        "credential",
        "token",
        "secret",
        "opaque_reference",
        "governance_resolution",
        "descriptor",
    }
    for no in ast.walk(_arvore(CONTRATOS)):
        if not isinstance(no, ast.ClassDef):
            continue
        campos = {
            membro.target.id
            for membro in no.body
            if isinstance(membro, ast.AnnAssign) and isinstance(membro.target, ast.Name)
        }
        assert not campos & proibidos, f"{no.name}: {campos & proibidos}"


def test_g12_1_o_erro_de_recibo_expoe_apenas_chaves_fechadas():
    """`PIA-8049` distingue desfecho observado de recibo confirmado."""
    import uuid

    from app.memory.errors.exceptions import ErasureReceiptNotPersistedError
    from app.memory.models.erasure_enums import ErasureOutcome
    from app.memory.schemas.destructive_execution import PartialExecutionEvidence

    erro = ErasureReceiptNotPersistedError(
        ErasureOutcome.PARTIAL,
        PartialExecutionEvidence(
            approval_id=uuid.uuid4(),
            failed_position=0,
            subject_coid=uuid.uuid4(),
            attempts_observed=1,
            receipts_persisted=0,
        ),
    )
    assert set(erro.detail) == {
        "approval_id",
        "observed_outcome",
        "failed_position",
        "subject_coid",
        "attempts_observed",
        "receipts_persisted",
    }
    assert erro.detail["observed_outcome"] == "partial"
    assert erro.detail["receipts_persisted"] == 0


def test_g99_12_a_guarda_de_campo_detecta_um_localizador():
    fonte = "@dataclass\nclass R:\n    transient_locator: str\n"
    campos = {
        membro.target.id
        for no in ast.walk(ast.parse(fonte))
        if isinstance(no, ast.ClassDef)
        for membro in no.body
        if isinstance(membro, ast.AnnAssign) and isinstance(membro.target, ast.Name)
    }
    assert "transient_locator" in campos


# ----------------------------------------------------------------------
# g13 — a migration recusa antes de qualquer DDL
# ----------------------------------------------------------------------


def _ddl_depois_da_recusa(arvore: ast.Module) -> bool:
    """No `downgrade`, todo DDL vem DEPOIS do `raise` de recusa?

    ```text
    REFUSE_BEFORE_ALTER, NEVER_MID_MIGRATION
    ```
    """
    for no in ast.walk(arvore):
        if not isinstance(no, ast.FunctionDef) or no.name != "downgrade":
            continue
        recusa = [
            filho.lineno
            for filho in ast.walk(no)
            if isinstance(filho, ast.Raise) and filho.exc is not None
        ]
        # DDL é o que passa por `op`. `ligacao.execute(SELECT ...)` é a
        # MEDIÇÃO, e contá-la como DDL faria a guarda reprovar justamente
        # a ordem correta — o receptor é a distinção, não o nome do
        # método.
        ddl = [
            filho.lineno
            for filho in ast.walk(no)
            if isinstance(filho, ast.Call)
            and isinstance(filho.func, ast.Attribute)
            and isinstance(filho.func.value, ast.Name)
            and filho.func.value.id == "op"
            and filho.func.attr in ("execute", "drop_constraint", "alter_column")
            and filho.lineno > _linha_do_ramo_postgres(no)
        ]
        if not recusa:
            return False
        return all(linha > min(recusa) for linha in ddl)
    return False


def _linha_do_ramo_postgres(no: ast.FunctionDef) -> int:
    """Ignora o ramo não-PostgreSQL, que retorna antes e não é medido."""
    for filho in ast.walk(no):
        if isinstance(filho, ast.Return):
            return filho.lineno
    return 0


def test_g13_o_downgrade_recusa_antes_de_qualquer_ddl():
    versoes = APP.parent / "alembic" / "versions"
    migracao = next(versoes.glob("d5b31f7a08c4_*.py"))
    assert _ddl_depois_da_recusa(ast.parse(migracao.read_text(encoding="utf-8")))


def test_g99_13_a_guarda_de_ordem_da_migration_detecta_ddl_antes():
    ruim = (
        "def downgrade():\n"
        "    if d != 'postgresql':\n"
        "        return\n"
        "    op.drop_constraint(c, t)\n"
        "    if impedem:\n"
        "        raise RuntimeError('nao da')\n"
        "    op.execute(alter)\n"
    )
    boa = (
        "def downgrade():\n"
        "    if d != 'postgresql':\n"
        "        return\n"
        "    if impedem:\n"
        "        raise RuntimeError('nao da')\n"
        "    op.drop_constraint(c, t)\n"
        "    op.execute(alter)\n"
    )
    assert _ddl_depois_da_recusa(ast.parse(ruim)) is False
    assert _ddl_depois_da_recusa(ast.parse(boa)) is True
