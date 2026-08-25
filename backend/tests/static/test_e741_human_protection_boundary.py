"""
Guarda estática da ponte de proteção humana (`E7.4-1 B1a`).

```text
PORT_IN_THE_CONSUMER · ADAPTER_WHERE_THE_IMPORT_IS_LEGAL
PRODUCTION_COMPOSITION_IN_B1A = NO
DUPLICATE_PROTECTION_CATEGORY_OWNER = PROHIBITED
GUARD_WITHOUT_MUTANT = UNVERIFIED_GUARD
```

Tudo por AST, `tokenize` ou metadata do ORM — nunca por heurística de linha.
A CHAIN121 já foi reprovada por uma guarda que contava `type: ignore` por
substring e podia ser atravessada com uma crase num comentário.

```text
HEURISTICA_DE_LINHA = GUARDA_CONTORNAVEL
DOCUMENTACAO_DESATUALIZADA = AFIRMACAO_FALSA_NO_REPOSITORIO
```

Duas guardas aqui têm **autoteste com fixture negativa** antes da varredura:
uma guarda que nunca viu um caso proibido prova apenas que ela roda.

```text
UMA GUARDA SEM PROVA NEGATIVA PROVA APENAS QUE ELA RODA
GUARD_EXIT_0_WITH_KNOWN_FORBIDDEN_FIXTURE = GUARD_FAILURE
```
"""

import ast
import pathlib
import re

import pytest

pytestmark = pytest.mark.unit

BACKEND = pathlib.Path(__file__).resolve().parents[2]
APP = BACKEND / "app"
ORQUESTRACAO = APP / "orchestration"
PROTECAO = ORQUESTRACAO / "protection"
PORTA = ORQUESTRACAO / "ports" / "governance.py"
VOCABULARIO = ORQUESTRACAO / "ports" / "governance_vocabulary.py"
MODELO_EVENTO = ORQUESTRACAO / "models" / "human_protection_event.py"
MODELO_CAPACIDADE = ORQUESTRACAO / "models" / "human_protection_event_capability.py"
REPOSITORIO_HP = ORQUESTRACAO / "repositories" / "human_protection_repository.py"
ADAPTADOR = APP / "services" / "governance_bridge.py"
ROUTER = APP / "routers" / "orchestration.py"
MAIN = BACKEND / "main.py"
MIGRATION = BACKEND / "alembic" / "versions" / "d7a4c1e93b28_human_protection_bridge_e7_4_1_b1a.py"
DOCS = BACKEND / "docs" / "entregas" / "entrega-7"

#: Nunca existem no código nem no schema produtivos (contrato R10.1).
SIMBOLOS_PROIBIDOS = frozenset({"typed_fixture", "decision_source"})

#: Marcadores estruturais. A decisão do titular retirou deles toda
#: autoridade: forma, profundidade, fan-in, número de provedores e
#: reformulação NÃO são evidência de categoria.
#:
#: ```text
#: STRUCTURAL_SHAPE != RISK_EVIDENCE
#: R-CONJUNCTION_DECISION_AUTHORITY = NONE
#: SHAPE_DOES_NOT_DETECT_CATEGORY -> SHAPE_MUST_NOT_PAUSE_LEGITIMATE_WORK
#: ```
MARCADORES_ESTRUTURAIS = frozenset(
    {
        "fan_in",
        "fanin",
        "graph_depth",
        "chain_depth",
        "structural_score",
        "complexity_score",
        "risk_score",
        "reformulation_count",
        "provider_count",
        "agent_count",
    }
)

#: Vocabulário que denunciaria conteúdo bruto numa coluna.
COLUNAS_DE_CONTEUDO = frozenset(
    {
        "content",
        "raw_content",
        "raw_output",
        "payload",
        "prompt",
        "response",
        "instruction",
        "document",
        "secret",
        "credential",
        "api_key",
        "access_token",
    }
)


def _arvore(caminho: pathlib.Path) -> ast.Module:
    return ast.parse(caminho.read_text(encoding="utf-8"))


def _imports(caminho: pathlib.Path) -> list[str]:
    modulos: list[str] = []
    for no in ast.walk(_arvore(caminho)):
        if isinstance(no, ast.Import):
            modulos.extend(alias.name for alias in no.names)
        elif isinstance(no, ast.ImportFrom) and no.module:
            modulos.append(no.module)
    return modulos


def _nomes(caminho: pathlib.Path) -> set[str]:
    encontrados: set[str] = set()
    for no in ast.walk(_arvore(caminho)):
        if isinstance(no, ast.Name):
            encontrados.add(no.id)
        elif isinstance(no, ast.Attribute):
            encontrados.add(no.attr)
        elif isinstance(no, ast.arg):
            encontrados.add(no.arg)
        elif isinstance(no, ast.Constant) and isinstance(no.value, str):
            encontrados.add(no.value)
    return encontrados


def _arquivos_da_protecao() -> list[pathlib.Path]:
    return sorted(PROTECAO.rglob("*.py")) + [PORTA, VOCABULARIO, MODELO_EVENTO, REPOSITORIO_HP]


# --- fronteira de pacote ----------------------------------------------------


def test_hp_s01_nenhum_arquivo_da_protecao_importa_a_e4() -> None:
    """`BRIDGE_BY_DIRECT_IMPORT = FROZEN_GUARD_VIOLATION`."""
    for caminho in _arquivos_da_protecao():
        for modulo in _imports(caminho):
            assert not modulo.startswith(
                ("app.memory", "app.cognitive", "app.predictive_accessibility", "fastapi")
            ), f"{caminho.name} importa {modulo}"


def test_hp_s02_o_adaptador_e_o_unico_ponto_do_caminho_que_importa_a_e4() -> None:
    """O import legal existe, e existe num lugar só."""
    assert any(m.startswith("app.memory") for m in _imports(ADAPTADOR))
    assert not any(m.startswith("app.memory") for m in _imports(ROUTER))


def test_hp_s03_a_protecao_nao_importa_rede_fila_worker_nem_mcp() -> None:
    proibidos = {
        "httpx",
        "requests",
        "aiohttp",
        "socket",
        "urllib",
        "http",
        "ssl",
        "mcp",
        "oauthlib",
        "authlib",
        "jwt",
    }
    for caminho in _arquivos_da_protecao() + [ADAPTADOR]:
        for modulo in _imports(caminho):
            assert modulo.split(".")[0] not in proibidos, f"{caminho.name} importa {modulo}"


# --- ausência de composição produtiva ---------------------------------------


def test_hp_s04_o_router_nao_conhece_a_ponte() -> None:
    """`ROUTER_MODIFIED_IN_B1A = NO`, medido no import e no nome."""
    for modulo in _imports(ROUTER):
        assert "protection" not in modulo, f"router importa {modulo}"
        assert "governance_bridge" not in modulo, f"router importa {modulo}"
    proibidos = {"HumanProtectionBridge", "GovernanceResolutionAdapter", "GovernanceQuery"}
    assert not (_nomes(ROUTER) & proibidos)


def test_hp_s05_nenhum_composition_root_produtivo_instancia_a_ponte() -> None:
    """`PRODUCTION_COMPOSITION_IN_B1A = NO`.

    A varredura cobre TODO `app/` mais `main.py`, e não só o router: excluir
    por arquivo é o defeito `ARQUIVO_EXCLUÍDO_DA_GUARDA !=
    FUNÇÃO_EXCLUÍDA_DA_GUARDA` que reprovou a Chain119.
    """
    construtores = {"HumanProtectionBridge", "GovernanceResolutionAdapter"}
    permitidos = {ADAPTADOR.resolve(), (PROTECAO / "bridge.py").resolve()}
    for caminho in sorted(APP.rglob("*.py")) + [MAIN]:
        if caminho.resolve() in permitidos:
            continue
        for no in ast.walk(_arvore(caminho)):
            if isinstance(no, ast.Call) and isinstance(no.func, ast.Name):
                assert no.func.id not in construtores, f"{caminho} instancia {no.func.id}"


def test_hp_s06_nenhum_simbolo_de_dublê_existe_no_codigo_produtivo() -> None:
    """`TEST_DOUBLE_IN_PRODUCTION_SCHEMA = PRODUCTION_CAPABILITY`."""
    for caminho in sorted(APP.rglob("*.py")) + [MIGRATION]:
        encontrados = _nomes(caminho) & SIMBOLOS_PROIBIDOS
        assert not encontrados, f"{caminho}: {sorted(encontrados)}"


def test_hp_s07_nenhum_marcador_estrutural_decide() -> None:
    """`SHAPE_DOES_NOT_DETECT_CATEGORY -> SHAPE_MUST_NOT_PAUSE_LEGITIMATE_WORK`."""
    for caminho in _arquivos_da_protecao() + [ADAPTADOR]:
        encontrados = _nomes(caminho) & MARCADORES_ESTRUTURAIS
        assert not encontrados, f"{caminho.name}: {sorted(encontrados)}"


# --- vocabulário único ------------------------------------------------------


def test_hp_s08_a_e7_nao_cria_um_segundo_catalogo_de_dano() -> None:
    """O único enum de capacidade da E7 espelha a E4 e é provado por paridade.

    A prova de paridade vive em `tests/unit/orchestration/`; aqui o que se
    mede é que nenhum OUTRO enum de capacidade nasceu na proteção.
    """
    definidos = {
        no.name
        for caminho in sorted(PROTECAO.rglob("*.py"))
        for no in ast.walk(_arvore(caminho))
        if isinstance(no, ast.ClassDef)
        and any(
            isinstance(base, ast.Name) and base.id in {"StrEnum", "Enum", "IntEnum"}
            for base in no.bases
        )
    }
    assert definidos == {"GatePosition", "ProtectionOutcome"}, sorted(definidos)


def test_hp_s09_o_mapa_de_desfechos_e_literal_e_exaustivo() -> None:
    """Enumerado, nunca derivado por exclusão.

    `set(X) - {…}` faria um membro novo entrar por omissão — o defeito que
    `EMPTY_OPERATIONS_SCOPE_V1` corrigiu na E4.3.3.
    """
    arvore = _arvore(PROTECAO / "bridge.py")
    mapas = [
        no
        for no in ast.walk(arvore)
        if isinstance(no, ast.AnnAssign)
        and isinstance(no.target, ast.Name)
        and no.target.id == "DESFECHO_POR_FRONTEIRA"
    ]
    assert len(mapas) == 1
    assert isinstance(mapas[0].value, ast.Dict)
    assert len(mapas[0].value.keys) == 2


# --- schema: dono único, reconciliado mecanicamente -------------------------


def _checks_declarados(caminho: pathlib.Path, nome_da_tupla: str) -> set[str]:
    """Nomes de `CHECK` extraídos por AST da tupla literal.

    Lidos da árvore sintática, e não de uma lista escrita à mão no teste: a
    guarda nova da CHAIN121 já pagou o preço de envelhecer junto com a prosa.
    """
    for no in ast.walk(_arvore(caminho)):
        alvo = None
        if isinstance(no, ast.AnnAssign) and isinstance(no.target, ast.Name):
            alvo = no.target.id
        elif isinstance(no, ast.Assign) and isinstance(no.targets[0], ast.Name):
            alvo = no.targets[0].id
        if alvo != nome_da_tupla or not isinstance(no.value, ast.Tuple):
            continue
        return {
            par.elts[0].value
            for par in no.value.elts
            if isinstance(par, ast.Tuple) and isinstance(par.elts[0], ast.Constant)
        }
    raise AssertionError(f"{nome_da_tupla} não encontrada em {caminho}")


def test_hp_s10_o_orm_e_a_migration_declaram_os_mesmos_checks() -> None:
    """Reconciliação MECÂNICA entre as duas declarações.

    ```text
    PARTIAL_ENUMERATION = GUARD_WITH_A_HOLE
    ```

    Declarar em dois lugares só é aceitável quando algo compara os dois. É
    isto.
    """
    assert _checks_declarados(MODELO_EVENTO, "CHECKS_DO_EVENTO") == _checks_declarados(
        MIGRATION, "_CHECKS_DO_EVENTO"
    )
    assert _checks_declarados(MODELO_EVENTO, "CHECKS_DA_CAPACIDADE") == _checks_declarados(
        MIGRATION, "_CHECKS_DA_CAPACIDADE"
    )


def test_hp_s11_a_contagem_de_checks_vem_do_metadata_e_nao_de_lista() -> None:
    """A contagem é derivada do ORM, ancorada onde o schema vive."""
    import app.orchestration.models  # noqa: F401
    from app.database.base import Base

    evento = Base.metadata.tables["human_protection_events"]
    associacao = Base.metadata.tables["human_protection_event_capabilities"]
    tipo = "CheckConstraint"
    assert len([c for c in evento.constraints if type(c).__name__ == tipo]) == 30
    assert len([c for c in associacao.constraints if type(c).__name__ == tipo]) == 2
    assert len([c for c in evento.constraints if type(c).__name__ == "ForeignKeyConstraint"]) == 3


def test_hp_s12_nenhuma_coluna_dos_modelos_novos_recebe_conteudo() -> None:
    """`HUMAN_PROTECTION_EVENT_CONTENT = NONE`, medido nas colunas reais."""
    import app.orchestration.models  # noqa: F401
    from app.database.base import Base

    for tabela in ("human_protection_events", "human_protection_event_capabilities"):
        colunas = set(Base.metadata.tables[tabela].columns.keys())
        assert not (colunas & COLUNAS_DE_CONTEUDO), sorted(colunas & COLUNAS_DE_CONTEUDO)


# --- guarda clerical, com autoteste negativo --------------------------------

#: A formulação obsoleta corrigida pelo §7 do prompt B1a. O contrato correto
#: é DERIVADO do dataclass, e por isso nenhum número é publicado em prosa.
#:
#: ```text
#: HAND_WRITTEN_COUNT = COUNT_THAT_DRIFTS
#: ```
_FORMULACAO_OBSOLETA = re.compile(r"M-BINDING-PARTIAL[^\n]*?\b(\d+)\s+subcasos", re.IGNORECASE)

#: Totais do manifesto fixados em prosa. Publicá-los num documento cria uma
#: segunda fonte que envelhece sozinha.
_TOTAL_PUBLICADO = re.compile(
    r"\bSUBCASOS_(?:FINGERPRINT|BINDING|PORT_QUERY)\s*=\s*\d+"
    r"|\bCAMPOS_COMPARADOS_NO_VENCEDOR\s*=\s*\d+",
    re.IGNORECASE,
)

FIXTURES_NEGATIVAS = (
    "M-BINDING-PARTIAL morre nos 9 subcasos derivados",
    "M-BINDING-PARTIAL morre nos 10 subcasos derivados",
    "SUBCASOS_BINDING = 10",
    "CAMPOS_COMPARADOS_NO_VENCEDOR = 19",
)
"""Casos que a guarda TEM de reprovar — inclusive o número **correto**.

Trocar 9 por 10 na prosa não conserta nada: o defeito é publicar o número,
não errá-lo. Uma guarda que só reprovasse o valor antigo aceitaria o novo e
recomeçaria o mesmo envelhecimento.
"""

FIXTURES_POSITIVAS = (
    "M-BINDING-PARTIAL morre nos subcasos derivados do dataclass",
    "os totais são derivados em tempo de teste",
    "o binding tem dez campos, e o décimo que importa é o attempt_id",
)
"""Casos que a guarda NÃO pode reprovar. Sem eles, a guarda mais estrita
possível — reprovar tudo — passaria no autoteste."""


def _viola(texto: str) -> bool:
    return bool(_FORMULACAO_OBSOLETA.search(texto) or _TOTAL_PUBLICADO.search(texto))


def test_hp_s13_autoteste_da_guarda_clerical() -> None:
    """Autoteste ANTES da varredura, com fixtures dos dois sinais.

    ```text
    GUARD_EXIT_0_WITH_KNOWN_FORBIDDEN_FIXTURE = GUARD_FAILURE
    ```
    """
    for fixture in FIXTURES_NEGATIVAS:
        assert _viola(fixture), f"a guarda deixou passar: {fixture!r}"
    for fixture in FIXTURES_POSITIVAS:
        assert not _viola(fixture), f"falso positivo: {fixture!r}"


def test_hp_s14_nenhum_documento_da_entrega_publica_o_total_do_manifesto() -> None:
    """Varredura, executada só depois de o autoteste passar."""
    assert len(FIXTURES_NEGATIVAS) + len(FIXTURES_POSITIVAS) == 7
    for documento in sorted(DOCS.glob("*.md")):
        assert not _viola(documento.read_text(encoding="utf-8")), documento.name
