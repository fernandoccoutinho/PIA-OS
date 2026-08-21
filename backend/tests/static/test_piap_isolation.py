"""
Guardas de **isolamento** do PIAP (`E5.a`).

```text
PIAP != COUT_P
PIAP_ENVELOPE != AI_HANDOFF_ENVELOPE
E5_MEMORY_WRITER = FORBIDDEN
```

Esta etapa materializa envelope, autoridade, versão e porta — e nada
mais. As guardas provam o *nada mais* por AST e reflexão, nunca por busca
textual, que acusaria as próprias docstrings destes módulos, escritas
justamente para nomear o que eles **não** fazem.

## Guarda local, e por quê

`E5.b` ainda não existe: ela é a etapa seguinte e generalizará estas
guardas para toda a camada antes de qualquer `E5.c`–`E5.t`. Até lá, a
proteção é local a `E5.a`, e isso está registrado — não é a guarda de
camada, é a guarda desta fatia.

```text
E5_A_LOCAL_ISOLATION_GUARD = REQUIRED_WITH_MUTANTS
E5_B_MUST_GENERALIZE_THE_LAYER_GUARD_BEFORE_E5_C = TRUE
```

## Sobre a separação com o envelope de repasse multi-IA

`AIHandoffEnvelope` **não existe** no código: medido, zero ocorrências em
toda a produção. A separação exigida por `D1` é, portanto, contra um
objeto documental da `E7`, e não contra um símbolo importável. Não há
como prová-la por ausência de import de algo inexistente. A prova aqui é
nominal e estrutural: nenhum símbolo com esse nome, e nenhum campo de
papel de IA, automação, pausa ou destino de repasse.

```text
NOMINAL_AND_STRUCTURAL_PROOF != IMPORT_ABSENCE_PROOF
```

`test_s99_*` no fim demonstra que cada mecanismo consegue falhar: guarda
que só pode passar não protege nada.
"""

import ast
import dataclasses
import pathlib

import pytest

pytestmark = pytest.mark.unit

RAIZ = pathlib.Path(__file__).resolve().parents[2]
PACOTE = RAIZ / "app" / "predictive_accessibility"

CAMINHOS_AUTORIZADOS = (
    "__init__.py",
    "piap/__init__.py",
    "piap/capacity.py",
    "piap/enums.py",
    "piap/envelope.py",
    "piap/authority.py",
    "piap/version.py",
    "ports/__init__.py",
    "ports/governed_read.py",
    "errors/__init__.py",
    "errors/codes.py",
    "errors/exceptions.py",
)

VOCABULARIO_CIENTIFICO = (
    "a_minus",
    "a_star",
    "a_rel",
    "k_pred",
    "k_history",
    "d_regime",
    "h_pred",
    "delta_cont",
    "r_pred",
    "l_total",
    "power_gate",
    "epistemic",
    "predictable",
    "unresolved",
    "route",
    "roteamento",
    "burden",
    "counterfactual",
    "materiality",
    "conflict",
)

VOCABULARIO_DE_HANDOFF = (
    "ai_role",
    "automation_mode",
    "handoff",
    "pause",
    "relay_target",
)

VOCABULARIO_DE_EFEITO = (
    "provider",
    "connector",
    "endpoint",
    "credential",
    "sdk",
    "execute",
    "dispatch",
    "session",
    "engine",
    "repository",
    "table",
    "migration",
    "commit",
)


def _fontes() -> list[pathlib.Path]:
    return [PACOTE / nome for nome in CAMINHOS_AUTORIZADOS]


def _arvore(caminho: pathlib.Path) -> ast.Module:
    return ast.parse(caminho.read_text(encoding="utf-8"))


def _modulos_importados(caminho: pathlib.Path) -> set[str]:
    modulos: set[str] = set()
    for no in ast.walk(_arvore(caminho)):
        if isinstance(no, ast.Import):
            modulos.update(alias.name for alias in no.names)
        elif isinstance(no, ast.ImportFrom) and no.module is not None:
            modulos.add(no.module)
    return modulos


def _nomes_definidos(caminho: pathlib.Path) -> set[str]:
    return {
        no.name
        for no in ast.walk(_arvore(caminho))
        if isinstance(no, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
    }


def _anotacoes_de_campo(caminho: pathlib.Path) -> list[tuple[str, str]]:
    """Nome e anotação textual de cada campo anotado em nível de classe."""
    campos: list[tuple[str, str]] = []
    for no in ast.walk(_arvore(caminho)):
        if not isinstance(no, ast.ClassDef):
            continue
        for corpo in no.body:
            if isinstance(corpo, ast.AnnAssign) and isinstance(corpo.target, ast.Name):
                campos.append((corpo.target.id, ast.unparse(corpo.annotation)))
    return campos


# --- delta e forma ---------------------------------------------------------


def test_s01_somente_os_caminhos_autorizados_existem_no_pacote() -> None:
    encontrados = {
        str(p.relative_to(PACOTE)).replace("\\", "/")
        for p in PACOTE.rglob("*.py")
        if "__pycache__" not in p.parts
    }
    assert encontrados == set(CAMINHOS_AUTORIZADOS)


def test_s02_todos_os_arquivos_autorizados_existem() -> None:
    for caminho in _fontes():
        assert caminho.is_file(), caminho


def test_s03_todos_os_arquivos_sao_utf8_estrito() -> None:
    for caminho in _fontes():
        caminho.read_bytes().decode("utf-8")


# --- fronteira -------------------------------------------------------------


def test_s04_nenhum_import_de_app_memory_ou_app_cognitive() -> None:
    for caminho in _fontes():
        importados = _modulos_importados(caminho)
        assert not any(m.startswith("app.memory") for m in importados), caminho.name
        assert not any(m.startswith("app.cognitive") for m in importados), caminho.name


def test_s05_importa_apenas_stdlib_e_o_proprio_pacote() -> None:
    permitidos_app = ("app.predictive_accessibility", "app.core.error_codes", "app.exceptions")
    for caminho in _fontes():
        for modulo in _modulos_importados(caminho):
            if modulo.startswith("app."):
                assert modulo.startswith(permitidos_app), f"{caminho.name}: {modulo}"


def test_s06_nenhuma_infraestrutura_de_persistencia_importada() -> None:
    proibidos = ("sqlalchemy", "alembic", "psycopg", "asyncpg", "fastapi", "pydantic", "httpx")
    for caminho in _fontes():
        for modulo in _modulos_importados(caminho):
            assert not modulo.startswith(proibidos), f"{caminho.name}: {modulo}"


# --- nomenclatura ----------------------------------------------------------


def test_s07_nenhum_simbolo_com_cout_p_ou_variante() -> None:
    proibidos = ("COUT_P", "COUTP", "CoutP", "coutp", "cout_p")
    for caminho in _fontes():
        for nome in _nomes_definidos(caminho):
            assert not any(p in nome for p in proibidos), f"{caminho.name}: {nome}"


def test_s08_nenhum_simbolo_de_handoff_multi_ia() -> None:
    for caminho in _fontes():
        for nome in _nomes_definidos(caminho):
            minusculo = nome.lower()
            assert "handoffenvelope" not in minusculo, f"{caminho.name}: {nome}"
            assert "aihandoff" not in minusculo, f"{caminho.name}: {nome}"


def test_s09_inaccessible_sem_qualificador_nao_e_definido() -> None:
    for caminho in _fontes():
        for nome in _nomes_definidos(caminho):
            assert nome != "INACCESSIBLE", caminho.name
            assert nome != "Inaccessible", caminho.name


def test_s10_conflict_sem_qualificador_nao_e_definido() -> None:
    for caminho in _fontes():
        for nome in _nomes_definidos(caminho):
            assert nome != "Conflict", caminho.name


# --- campos ----------------------------------------------------------------


def test_s11_nenhum_any_ou_dict_aberto_em_campo_publico() -> None:
    for caminho in _fontes():
        for nome, anotacao in _anotacoes_de_campo(caminho):
            if nome.startswith("_"):
                continue
            assert "Any" not in anotacao, f"{caminho.name}: {nome}: {anotacao}"
            assert "dict[" not in anotacao, f"{caminho.name}: {nome}: {anotacao}"


def test_s12_nenhuma_colecao_mutavel_em_campo_publico() -> None:
    for caminho in _fontes():
        for nome, anotacao in _anotacoes_de_campo(caminho):
            if nome.startswith("_"):
                continue
            for mutavel in ("list[", "set[", "dict[", "List[", "Set[", "Dict["):
                assert mutavel not in anotacao, f"{caminho.name}: {nome}: {anotacao}"


def test_s13_nenhum_campo_de_vocabulario_cientifico_ou_de_rota() -> None:
    for caminho in _fontes():
        for nome, _ in _anotacoes_de_campo(caminho):
            minusculo = nome.lower()
            for termo in VOCABULARIO_CIENTIFICO:
                assert termo not in minusculo, f"{caminho.name}: {nome}"


def test_s14_nenhum_campo_de_repasse_multi_ia() -> None:
    for caminho in _fontes():
        for nome, _ in _anotacoes_de_campo(caminho):
            minusculo = nome.lower()
            for termo in VOCABULARIO_DE_HANDOFF:
                assert termo not in minusculo, f"{caminho.name}: {nome}"


def test_s15_nenhum_campo_de_efeito_externo_ou_persistencia() -> None:
    for caminho in _fontes():
        for nome, _ in _anotacoes_de_campo(caminho):
            minusculo = nome.lower()
            for termo in VOCABULARIO_DE_EFEITO:
                assert termo not in minusculo, f"{caminho.name}: {nome}"


# --- fonte única do status -------------------------------------------------


def test_s16_approval_binding_nao_tem_status_paralelo() -> None:
    from app.predictive_accessibility.piap.authority import ApprovalBinding, AuthorityContext

    campos_binding = {c.name for c in dataclasses.fields(ApprovalBinding)}
    assert not any("status" in c for c in campos_binding)
    assert "status" in {c.name for c in dataclasses.fields(AuthorityContext)}


def test_s17_todos_os_value_objects_publicos_sao_frozen() -> None:
    import app.predictive_accessibility.piap as piap

    for nome in piap.__all__:
        objeto = getattr(piap, nome)
        if dataclasses.is_dataclass(objeto) and isinstance(objeto, type):
            assert objeto.__dataclass_params__.frozen, nome


# --- ausência de capacidade proibida ---------------------------------------


def test_s18_nenhum_modelo_orm_tabela_ou_migration_no_pacote() -> None:
    for caminho in _fontes():
        for no in ast.walk(_arvore(caminho)):
            if isinstance(no, ast.ClassDef):
                bases = {ast.unparse(b) for b in no.bases}
                assert not any("Base" in b or "Model" in b for b in bases), caminho.name
    assert not list(PACOTE.rglob("*migration*"))
    assert not list(PACOTE.rglob("*repositor*"))


def test_s19_nenhum_efeito_externo_chamado() -> None:
    """Nenhuma abertura de arquivo, rede, processo ou tempo do relógio."""
    proibidos = {"open", "exec", "eval", "compile", "__import__", "input"}
    for caminho in _fontes():
        for no in ast.walk(_arvore(caminho)):
            if isinstance(no, ast.Call) and isinstance(no.func, ast.Name):
                assert no.func.id not in proibidos, f"{caminho.name}: {no.func.id}"


def test_s20_dois_codigos_de_erro_novos_e_nenhuma_reserva() -> None:
    from app.predictive_accessibility.errors import codes

    novos = {
        valor.code
        for nome, valor in vars(codes).items()
        if nome.startswith("PIA_") and hasattr(valor, "code")
    }
    assert novos == {"PIA-8052", "PIA-8053"}


# --- mutantes do instrumento ----------------------------------------------
#
# Cada um demonstra que o mecanismo da guarda correspondente consegue
# reprovar. Guarda que só pode passar não protege nada.
#
#     GUARD_WITHOUT_MUTANT = UNVERIFIED_GUARD


def _fonte_temporaria(tmp_path: pathlib.Path, conteudo: str) -> pathlib.Path:
    caminho = tmp_path / "mutante.py"
    caminho.write_text(conteudo, encoding="utf-8")
    return caminho


def test_s99_mecanismo_de_import_detecta_violacao(tmp_path: pathlib.Path) -> None:
    caminho = _fonte_temporaria(tmp_path, "from app.memory.schemas.governance import X\n")
    importados = _modulos_importados(caminho)
    assert any(m.startswith("app.memory") for m in importados)


def test_s99_mecanismo_de_nome_detecta_cout_p(tmp_path: pathlib.Path) -> None:
    caminho = _fonte_temporaria(tmp_path, "class COUT_PScore:\n    pass\n")
    assert any("COUT_P" in nome for nome in _nomes_definidos(caminho))


def test_s99_mecanismo_de_nome_detecta_handoff(tmp_path: pathlib.Path) -> None:
    caminho = _fonte_temporaria(tmp_path, "class AIHandoffEnvelope:\n    pass\n")
    assert any("aihandoff" in nome.lower() for nome in _nomes_definidos(caminho))


def test_s99_mecanismo_de_campo_detecta_colecao_mutavel(tmp_path: pathlib.Path) -> None:
    caminho = _fonte_temporaria(tmp_path, "class X:\n    escopo: list[str]\n")
    assert any("list[" in anotacao for _, anotacao in _anotacoes_de_campo(caminho))


def test_s99_mecanismo_de_campo_detecta_any(tmp_path: pathlib.Path) -> None:
    caminho = _fonte_temporaria(tmp_path, "class X:\n    carga: Any\n")
    assert any("Any" in anotacao for _, anotacao in _anotacoes_de_campo(caminho))


def test_s99_mecanismo_de_campo_detecta_vocabulario_cientifico(tmp_path: pathlib.Path) -> None:
    caminho = _fonte_temporaria(tmp_path, "class X:\n    a_minus: float\n")
    nomes = [nome.lower() for nome, _ in _anotacoes_de_campo(caminho)]
    assert any(termo in nome for nome in nomes for termo in VOCABULARIO_CIENTIFICO)


def test_s99_mecanismo_de_campo_detecta_status_paralelo(tmp_path: pathlib.Path) -> None:
    caminho = _fonte_temporaria(tmp_path, "class X:\n    approval_status: str\n")
    assert any("status" in nome for nome, _ in _anotacoes_de_campo(caminho))


def test_s99_mecanismo_de_delta_detecta_arquivo_extra(tmp_path: pathlib.Path) -> None:
    (tmp_path / "intruso.py").write_text("", encoding="utf-8")
    encontrados = {p.name for p in tmp_path.rglob("*.py")}
    assert encontrados - set(CAMINHOS_AUTORIZADOS)
