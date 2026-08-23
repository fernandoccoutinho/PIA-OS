"""
Guarda estática da fronteira do SDK (E6.3).

```text
SDK_SOURCE_OF_TRUTH = FALSE
RUNTIME_IMPORT_FROM_BACKEND_APP = FORBIDDEN
SDK_INVENTS_ROUTE = FORBIDDEN
BACKEND_IMPORTS_SDK = FORBIDDEN
```

Mora no backend de propósito: a suíte do SDK poderia ser removida do
pipeline sem que nada acusasse, e a fronteira que interessa proteger é a
do produto, não a do pacote cliente.

Tudo por AST e leitura de fonte. Docstring não é símbolo de runtime.
"""

import ast
import hashlib
import json
import pathlib

import pytest

pytestmark = pytest.mark.unit

RAIZ = pathlib.Path(__file__).resolve().parents[3]
SDK = RAIZ / "sdk" / "python"
RUNTIME = SDK / "pia_os_sdk"
SNAPSHOT = SDK / "schema" / "openapi_chain107_r1.json"
BACKEND_APP = RAIZ / "backend" / "app"

# Pacotes que o runtime do SDK jamais pode importar. Um SDK que importa o
# backend deixa de ser cliente: passa a exigir o servidor instalado e a
# poder tocar banco, ciência e migration.
PROIBIDOS_NO_RUNTIME = frozenset(
    {"app", "main", "sqlalchemy", "alembic", "psycopg", "fastapi", "starlette", "tests"}
)

# Símbolos científicos/governança que não podem migrar para o cliente.
CIENCIA_E_GOVERNANCA = (
    "predictive_route_batch",
    "predictive_route_item",
    "predictive_evaluate_batch",
    "predictive_evaluate_and_reconfigure_batch",
    "predictive_conflict_for_batch",
    "predictive_assertiveness",
    "predictive_final_routing",
    "PiapEnvelope",
    "serialize_piap_envelope",
    "ApprovalBinding",
    "AuthorityContext",
    "canonical_scopes",
    "consume_quota",
)


def _arvore(caminho: pathlib.Path) -> ast.Module:
    return ast.parse(caminho.read_text(encoding="utf-8"))


def _imports(caminho: pathlib.Path) -> set[str]:
    modulos: set[str] = set()
    for no in ast.walk(_arvore(caminho)):
        if isinstance(no, ast.Import):
            modulos.update(a.name for a in no.names)
        elif isinstance(no, ast.ImportFrom) and no.module:
            modulos.add(no.module)
    return modulos


def _fontes_runtime() -> list[pathlib.Path]:
    return sorted(RUNTIME.glob("*.py"))


def test_e63s01_o_sdk_existe_no_caminho_autorizado() -> None:
    assert RUNTIME.is_dir(), "sdk/python/pia_os_sdk ausente"
    assert (RUNTIME / "client.py").is_file()
    assert (RUNTIME / "models.py").is_file()
    assert (RUNTIME / "errors.py").is_file()
    assert SNAPSHOT.is_file()


def test_e63s02_runtime_do_sdk_nao_importa_backend_banco_nem_framework() -> None:
    for caminho in _fontes_runtime():
        for modulo in _imports(caminho):
            raiz = modulo.split(".")[0]
            assert raiz not in PROIBIDOS_NO_RUNTIME, (caminho.name, modulo)


def test_e63s03_runtime_do_sdk_nao_contem_ciencia_nem_governanca() -> None:
    for caminho in _fontes_runtime():
        texto = caminho.read_text(encoding="utf-8")
        for simbolo in CIENCIA_E_GOVERNANCA:
            assert simbolo not in texto, (caminho.name, simbolo)


def test_e63s04_o_backend_nao_importa_o_sdk() -> None:
    """A dependência é de mão única. O contrário faria o produto depender
    do cliente, e o cliente é derivado — não fonte."""
    for caminho in sorted(BACKEND_APP.rglob("*.py")):
        for modulo in _imports(caminho):
            assert not modulo.startswith("pia_os_sdk"), (caminho.name, modulo)


def test_e63s05_o_sdk_so_referencia_rotas_que_existem_no_snapshot() -> None:
    """`SDK_INVENTS_ROUTE = FORBIDDEN`.

    A proposta original previa `get_capacity_limits()`; a Chain107-R1 não
    tem esse endpoint, então o método não existe. Inventar a rota para
    cumprir um plano antigo criaria um SDK que chama o que não há.
    """
    documento = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    caminhos = set(documento["paths"])
    for caminho in _fontes_runtime():
        for no in ast.walk(_arvore(caminho)):
            if (
                isinstance(no, ast.Constant)
                and isinstance(no.value, str)
                and no.value.startswith("/api/")
            ):
                assert no.value in caminhos, (caminho.name, no.value)


# Campos voláteis do `app.openapi()` — removidos do snapshot porque mudam a
# cada processo e tornariam `REGENERATION_DIFF = ZERO` impossível. A lista é
# repetida aqui de propósito: `sdk/python/tools/snapshot_openapi.py` a define
# do lado do SDK, e o backend não importa o SDK. Divergir as duas faz este
# teste reprovar, que é o comportamento desejado.
VOLATEIS: tuple[tuple[str, ...], ...] = (("info", "x-metadata", "generated_at"),)


def _sem_volateis(documento: dict) -> dict:
    copia = json.loads(json.dumps(documento))
    for ponteiro in VOLATEIS:
        no = copia
        for chave in ponteiro[:-1]:
            no = no.get(chave) if isinstance(no, dict) else None
            if no is None:
                break
        if isinstance(no, dict):
            no.pop(ponteiro[-1], None)
    return copia


# --- projeção histórica E6.3 ------------------------------------------------
#
# ```text
# SDK_CHAIN107_R1 = HISTORICAL_IMMUTABLE_ARTIFACT
# E6_SNAPSHOT = HISTORICAL_CONTRACT
# E6_GUARD = HISTORICAL_PROJECTION_EXACT
# E7_ADDITIONS = ALLOWED_OUTSIDE_E6_PROJECTION
# ```
#
# ATUALIZADO PELA E7.2, e a causa importa. A versão anterior exigia
# igualdade do documento **inteiro** com o snapshot da Chain107-R1. Com
# cinco rotas novas, restavam duas saídas erradas e uma certa:
#
#   1. regenerar o snapshot — falsificaria a proveniência de um artefato
#      que se declara derivado da Chain107-R1, e `sdk/` é Stop Condition
#      sem autorização arquitetural;
#   2. apagar a guarda — perderia a proteção do contrato publicado;
#   3. medir a PROJEÇÃO: tudo o que o snapshot histórico contém continua
#      presente e idêntico no documento vivo, e só adições ficam livres.
#
# A terceira é a implementada. Ela é mais estrita que a igualdade em um
# ponto: verifica também o fechamento transitivo dos schemas alcançáveis
# pelas rotas históricas, de modo que alterar um `$ref` aninhado reprova.


def _referencias(no: object) -> set[str]:
    """Todo `$ref` alcançável a partir de um nó, em profundidade."""
    encontradas: set[str] = set()
    if isinstance(no, dict):
        for chave, valor in no.items():
            if chave == "$ref" and isinstance(valor, str):
                encontradas.add(valor.rsplit("/", 1)[-1])
            else:
                encontradas |= _referencias(valor)
    elif isinstance(no, list):
        for item in no:
            encontradas |= _referencias(item)
    return encontradas


def _fechamento_de_schemas(documento: dict, sementes: set[str]) -> set[str]:
    """Fecho transitivo dos schemas a partir de um conjunto inicial."""
    schemas = documento.get("components", {}).get("schemas", {})
    alcancados: set[str] = set()
    pendentes = set(sementes)
    while pendentes:
        atual = pendentes.pop()
        if atual in alcancados or atual not in schemas:
            continue
        alcancados.add(atual)
        pendentes |= _referencias(schemas[atual])
    return alcancados


def _projecao_historica(documento: dict, snapshot: dict) -> dict:
    """Recorta do documento vivo exatamente o que o snapshot cobre."""
    caminhos = {
        caminho: operacoes
        for caminho, operacoes in documento.get("paths", {}).items()
        if caminho in snapshot.get("paths", {})
    }
    sementes = _referencias(caminhos)
    nomes = _fechamento_de_schemas(documento, sementes)
    esquemas_vivos = documento.get("components", {}).get("schemas", {})
    seguranca_usada = {
        nome
        for operacoes in caminhos.values()
        for operacao in operacoes.values()
        if isinstance(operacao, dict)
        for entrada in operacao.get("security", [])
        for nome in entrada
    }
    return {
        "paths": caminhos,
        "schemas": {n: esquemas_vivos[n] for n in sorted(nomes) if n in esquemas_vivos},
        "securitySchemes": {
            nome: documento.get("components", {}).get("securitySchemes", {})[nome]
            for nome in sorted(seguranca_usada)
            if nome in documento.get("components", {}).get("securitySchemes", {})
        },
    }


def test_e63s06_a_projecao_historica_do_openapi_vivo_e_identica_ao_snapshot() -> None:
    """Toda rota da Chain107-R1 sobrevive byte a byte no documento vivo.

    Segurança, operações, respostas, parâmetros e o fecho transitivo dos
    schemas referenciados entram na comparação. Adições da E7.2 ficam
    **fora** da projeção e não a afetam — e são medidas pelas guardas
    próprias da E7.2, não por esta.
    """
    from main import app

    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    vivo = _sem_volateis(app.openapi())
    assert _projecao_historica(vivo, snapshot) == _projecao_historica(snapshot, snapshot)


def test_e63s06a_a_projecao_nao_e_vazia_e_cobre_a_rota_preditiva() -> None:
    """Não-vacuidade: uma projeção vazia passaria por qualquer coisa."""
    from main import app

    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    projecao = _projecao_historica(_sem_volateis(app.openapi()), snapshot)
    assert "/api/v1/predictive-evaluations" in projecao["paths"]
    assert len(projecao["paths"]) == len(snapshot["paths"])
    assert projecao["schemas"], "o fecho de schemas não pode ser vazio"
    assert "PIAServiceBearer" in projecao["securitySchemes"]


@pytest.mark.parametrize(
    "sabotagem",
    ["remover_rota", "alterar_seguranca", "alterar_schema_alcancavel"],
)
def test_e63s06c_a_projecao_reprova_quando_o_contrato_historico_muda(sabotagem: str) -> None:
    """Provas adversariais: a guarda tem de morrer nos três casos.

    Sem elas, "a projeção é igual" poderia ser verdade por a projeção não
    medir nada.
    """
    from main import app

    snapshot = json.loads(SNAPSHOT.read_text(encoding="utf-8"))
    vivo = _sem_volateis(app.openapi())
    adulterado = json.loads(json.dumps(vivo))
    rota = "/api/v1/predictive-evaluations"

    if sabotagem == "remover_rota":
        adulterado["paths"].pop(rota)
    elif sabotagem == "alterar_seguranca":
        adulterado["paths"][rota]["post"]["security"] = [{"OutroEsquema": []}]
    else:
        alvo = sorted(_referencias(adulterado["paths"][rota]))[0]
        adulterado["components"]["schemas"][alvo]["title"] = "adulterado"

    assert _projecao_historica(adulterado, snapshot) != _projecao_historica(
        snapshot, snapshot
    ), f"a guarda não reprovou a sabotagem {sabotagem!r}"


def test_e63s06d_o_snapshot_historico_permanece_intocado() -> None:
    """`SDK_DELTA_E7_2 = NONE`, medido pelo hash do artefato."""
    assert (
        hashlib.sha256(SNAPSHOT.read_bytes()).hexdigest()
        == "961d506c62fdd0acfbbfea2a3a06da547e5b0422a4b4b607ae3c6d60327bf58d"
    )
    assert (
        hashlib.sha256((RUNTIME / "models.py").read_bytes()).hexdigest()
        == "955c76bdc176bfe05b08bb04ca5bd7610dee9292866f3060bbd97563e426b24c"
    )


def test_e63s06b_o_campo_volatil_realmente_existe_no_documento_vivo() -> None:
    """Se o backend parar de emiti-lo, a normalização vira código morto."""
    from main import app

    assert "generated_at" in app.openapi()["info"]["x-metadata"]


def test_e63s07_os_modelos_gerados_declaram_o_sha_do_snapshot() -> None:
    digest = hashlib.sha256(SNAPSHOT.read_bytes()).hexdigest()
    texto = (RUNTIME / "models.py").read_text(encoding="utf-8")
    assert f'OPENAPI_SNAPSHOT_SHA256 = "{digest}"' in texto


def test_e63s08_os_modelos_sao_gerados_e_marcados_como_tal() -> None:
    """`HAND_EDIT_GENERATED_MODELS = FORBIDDEN` precisa estar no arquivo."""
    texto = (RUNTIME / "models.py").read_text(encoding="utf-8")
    assert "ARQUIVO GERADO" in texto
    assert "HAND_EDIT = FORBIDDEN" in texto


def test_e63s09_o_sdk_nao_faz_retry_nem_pagina() -> None:
    """`RETRY != DUPLICATE_EFFECT` — e paginação/streaming estão fora.

    Por AST, não por substring: `upstream_unavailable` contém "stream", e
    a constante `CLIENT_RETRIES_AUTOMATICALLY = FALSE` contém "retry". Uma
    busca textual reprovaria o código correto e ensinaria a desligar a
    guarda.
    """
    proibidos = {
        "retry",
        "retries",
        "backoff",
        "sleep",
        "aretry",
        "paginate",
        "next_page",
    }
    for caminho in _fontes_runtime():
        for no in ast.walk(_arvore(caminho)):
            if isinstance(no, ast.Call):
                alvo = no.func
                nome = alvo.id if isinstance(alvo, ast.Name) else getattr(alvo, "attr", "")
                assert nome.lower() not in proibidos, (caminho.name, nome)
            if isinstance(no, ast.FunctionDef):
                assert no.name.lower() not in proibidos, (caminho.name, no.name)


def test_e63s10_o_sdk_nao_toca_arquivo_nem_processo() -> None:
    """O runtime não lê disco, não abre processo e não fala socket cru."""
    proibidos = {"subprocess", "os", "pathlib", "socket", "shutil", "tempfile"}
    for caminho in _fontes_runtime():
        for modulo in _imports(caminho):
            assert modulo.split(".")[0] not in proibidos, (caminho.name, modulo)


def test_e63s11_campo_volatil_nao_autorizado_reprova() -> None:
    """A normalização é uma lista FECHADA, não uma política geral.

    Só `info.x-metadata.generated_at` foi autorizado. Um campo instável
    novo tem de aparecer como divergência e obrigar uma decisão — se a
    remoção virasse regra ampla, o snapshot passaria a esconder mudanças
    de contrato.

    ```text
    AUTHORIZED_VOLATILE = {info.x-metadata.generated_at}
    ANY_OTHER_VOLATILE -> FAIL
    ```
    """
    from main import app

    documento = _sem_volateis(app.openapi())
    documento["info"]["x-metadata"]["outro_campo_instavel"] = "2020-01-01T00:00:00+00:00"
    assert json.loads(SNAPSHOT.read_text(encoding="utf-8")) != documento


def test_e63s12_a_lista_de_volateis_dos_dois_lados_e_identica() -> None:
    """Backend e SDK enumeram os mesmos ponteiros, sem um importar o outro."""
    import ast

    fonte = (SDK / "tools" / "snapshot_openapi.py").read_text(encoding="utf-8")
    declarado: tuple[tuple[str, ...], ...] | None = None
    for no in ast.walk(ast.parse(fonte)):
        if isinstance(no, ast.AnnAssign) and getattr(no.target, "id", "") == "VOLATILE_POINTERS":
            declarado = ast.literal_eval(no.value)  # type: ignore[arg-type]
    assert declarado == VOLATEIS, (declarado, VOLATEIS)
