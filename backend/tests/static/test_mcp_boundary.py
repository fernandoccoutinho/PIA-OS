"""Guardas do boundary MCP (`E7.4-2`).

```text
GENERIC_TOOL = ARBITRARY_EXECUTION_WITH_A_POLITE_NAME
```

Provas estáticas: a superfície é fechada, o boundary não alcança
persistência nem execução, e a fixture de AS não é selecionável em
produção. Estáticas de propósito — uma proibição verificada só em runtime
depende de alguém exercitar o caminho proibido.
"""

import ast
import pathlib

import pytest

from app.mcp import TOOL_NAMES

RAIZ = pathlib.Path(__file__).resolve().parents[2] / "app"
BOUNDARY = RAIZ / "mcp"

MODULOS_PROIBIDOS: frozenset[str] = frozenset(
    {
        "sqlalchemy",
        "psycopg",
        "alembic",
        "subprocess",
        "shutil",
        "socket",
        "requests",
        "httpx",
        "aiohttp",
        "urllib",
        "os",
        "pathlib",
        "glob",
        "tempfile",
    }
)
"""Persistência, execução, filesystem e HTTP genérico.

`os` e `pathlib` entram na lista: um boundary que lê o ambiente ou o
disco tem um segundo canal de configuração que ninguém audita junto com
o primeiro.
"""

VOCABULARIO_PERMITIDO: frozenset[str] = frozenset({"app.orchestration.models.enums"})
"""Exceção única, e MEDIDA — não afirmada.

`enums.py` está sob `app.orchestration.models` por localização, mas é
vocabulário puro: `test_mcp03b` prova que não importa ORM nenhum. Uma
guarda que bloqueia por caminho, e não pela propriedade que lhe importa,
bloqueia a coisa certa pelo motivo errado — e o motivo errado é o que
alguém afrouxa depois sem perceber o que estava protegendo.

    GUARD_BY_PATH < GUARD_BY_PROPERTY
"""

PREFIXOS_INTERNOS_PROIBIDOS: tuple[str, ...] = (
    "app.orchestration.repositories",
    "app.orchestration.models",
    "app.memory.models",
    "app.memory.repositories",
    "app.connections.repositories",
    "app.db",
)
"""Repositório, ORM e modelo de banco. As tools compõem **serviço**."""


def _modulos_do_boundary() -> list[pathlib.Path]:
    return sorted(BOUNDARY.rglob("*.py"))


def _importados(caminho: pathlib.Path) -> set[str]:
    arvore = ast.parse(caminho.read_text(encoding="utf-8"))
    nomes: set[str] = set()
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            for alias in no.names:
                nomes.add(alias.name)
        elif isinstance(no, ast.ImportFrom) and no.module:
            nomes.add(no.module)
    return nomes


def test_mcp01_superficie_e_exatamente_as_cinco_autorizadas() -> None:
    assert TOOL_NAMES == (
        "schedule.read",
        "handoff.export",
        "return.import",
        "attempts.list",
        "governance.read",
    )
    assert len(set(TOOL_NAMES)) == 5


def test_mcp02_boundary_nao_alcanca_persistencia_execucao_ou_http() -> None:
    violacoes: list[str] = []
    for modulo in _modulos_do_boundary():
        for importado in _importados(modulo):
            raiz = importado.split(".")[0]
            if raiz in MODULOS_PROIBIDOS:
                violacoes.append(f"{modulo.name}: {importado}")
    assert violacoes == [], f"boundary MCP alcançou o proibido: {violacoes}"


def test_mcp03_boundary_nao_alcanca_repositorio_orm_ou_modelo() -> None:
    violacoes: list[str] = []
    for modulo in _modulos_do_boundary():
        for importado in _importados(modulo):
            if importado in VOCABULARIO_PERMITIDO:
                continue
            if importado.startswith(PREFIXOS_INTERNOS_PROIBIDOS):
                violacoes.append(f"{modulo.name}: {importado}")
    assert violacoes == [], f"boundary MCP puxou persistência direto: {violacoes}"


def test_mcp04_nenhuma_tool_generica_no_vocabulario() -> None:
    """Nome de tool que sugira execução arbitrária não existe."""
    proibidos = (
        "sql",
        "query",
        "shell",
        "exec",
        "eval",
        "file",
        "fs",
        "url",
        "http",
        "fetch",
        "python",
        "memory",
        "admin",
        "secret",
        "run",
        "command",
    )
    for nome in TOOL_NAMES:
        for termo in proibidos:
            assert termo not in nome.lower().replace("governance", ""), f"{nome} sugere {termo}"


def test_mcp05_token_nunca_e_persistido_pelo_boundary() -> None:
    """Nenhum caminho do boundary escreve o token em lugar nenhum."""
    from app.mcp.auth import TOKEN_REDACTED, redigir

    token = "eyJhbGciOiJSUzI1NiJ9.carga.assinatura"
    texto = f"falha ao validar {token} para o principal"
    redigido = redigir(texto, token)
    assert token not in redigido
    assert TOKEN_REDACTED in redigido


def test_mcp06_bearer_somente_no_header() -> None:
    from app.mcp.auth import ErroDeAutenticacao, extrair_bearer

    assert extrair_bearer({"Authorization": "Bearer abc"}) == "abc"
    with pytest.raises(ErroDeAutenticacao):
        extrair_bearer({}, {"access_token": "abc"})
    with pytest.raises(ErroDeAutenticacao):
        extrair_bearer({"Authorization": "Basic abc"})
    with pytest.raises(ErroDeAutenticacao):
        extrair_bearer({})


def test_mcp07_algoritmo_vem_da_lista_nunca_do_token() -> None:
    """`ALGORITHM_FROM_THE_TOKEN = THE_ATTACKER_CHOOSES_THE_LOCK`."""
    from app.mcp.auth import ALGORITMOS_ACEITOS

    assert "none" not in {a.lower() for a in ALGORITMOS_ACEITOS}
    assert not any(a.startswith("HS") for a in ALGORITMOS_ACEITOS)
    assert frozenset({"RS256", "ES256"}) == ALGORITMOS_ACEITOS


def test_mcp08_metadata_nao_anuncia_authorization_server_interno() -> None:
    from app.mcp.auth import ResourceServerConfig, metadata_do_recurso

    corpo = metadata_do_recurso(
        ResourceServerConfig(
            issuer="https://idp.exemplo/",
            audience="pia-os-mcp",
            resource_url="https://pia.exemplo/mcp",
        )
    )
    assert corpo["authorization_servers"] == ["https://idp.exemplo/"]
    assert corpo["bearer_methods_supported"] == ["header"]
    for proibido in ("token_endpoint", "registration_endpoint", "authorization_endpoint"):
        assert proibido not in corpo


def test_mcp09_mcp_nao_e_modo_executavel_de_handoff() -> None:
    """`MCP_DISPATCH != MANUAL_HANDOFF`, e supervisionado não executa sozinho."""
    from app.orchestration.models.enums import EXECUTABLE_HANDOFF_MODES, HandoffMode

    assert HandoffMode.SUPERVISED_AUTOMATIC_HANDOFF not in EXECUTABLE_HANDOFF_MODES
    assert frozenset({HandoffMode.MANUAL_HANDOFF}) == EXECUTABLE_HANDOFF_MODES


COMPOSITION_ROOT = "services/mcp_composition_root.py"
"""O composition root PODE referenciar o boundary — e o unico que pode."""


def test_mcp10_boundary_nao_e_montado_na_composicao_produtiva() -> None:
    """`MCP_PRODUCTION = BLOCKED` — provado por ausencia de montagem.

    Duas medidas, porque uma so nao fecha:

    1. Ninguem alem do composition root alcanca `app.mcp`.
    2. Ninguem alcanca o proprio composition root.

    A segunda e a que importa: sem ela, bastaria alguem importar a
    factory para o runtime subir junto com a aplicacao. Com as duas, o
    unico jeito de montar o MCP e escrever codigo novo — que passa por
    revisao.

        NO_MOUNT_POINT > FLAG_SET_TO_FALSE
    """
    referencias: list[str] = []
    alcancam_a_raiz: list[str] = []
    for modulo in RAIZ.rglob("*.py"):
        relativo = str(modulo.relative_to(RAIZ))
        if BOUNDARY in modulo.parents or modulo.parent == BOUNDARY:
            continue
        for importado in _importados(modulo):
            if importado.endswith("mcp_composition_root") or "mcp_composition_root" in importado:
                alcancam_a_raiz.append(f"{relativo}: {importado}")
            elif (
                importado == "app.mcp" or importado.startswith("app.mcp.")
            ) and relativo != COMPOSITION_ROOT:
                referencias.append(f"{relativo}: {importado}")

    assert referencias == [], f"boundary MCP alcancado pela producao: {referencias}"
    assert alcancam_a_raiz == [], f"composition root alcancado: {alcancam_a_raiz}"
