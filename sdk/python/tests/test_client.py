"""
Testes do `pia-os-sdk` — representação, não decisão.

```text
CLIENT_SENDS_EXACT_METHOD_PATH_JSON_BEARER
PUBLIC_OPERATION_WITHOUT_SECURITY_REQUIREMENT
  -> MUST_NOT_RECEIVE_SERVICE_CREDENTIAL
CLIENT_PRESERVES_ORDER_AND_CARDINALITY
CREDENTIAL_IN_REPR_OR_ERROR = FORBIDDEN
CLIENT_TRANSLATES_STATUS = FALSE
```

Nenhum teste sobe o backend: o transporte é injetado. O contrato contra o
servidor real é verificado do outro lado, em
`backend/tests/integration/api/test_e6_sdk_contract.py`.
"""

from __future__ import annotations

import ast
import json
import logging
import pathlib
from typing import Any

import httpx
import pytest

from pia_os_sdk import PiaApiError, PiaClient, PiaTransportError
from pia_os_sdk import models as m

RAIZ = pathlib.Path(__file__).resolve().parents[1]
RUNTIME = RAIZ / "pia_os_sdk"

CREDENCIAL = "pia_kid-abcdefgh.segredo-de-alta-entropia-para-teste"


class _Capturador:
    """Transporte injetado: guarda a requisição e devolve resposta fixa."""

    def __init__(self, status: int = 200, corpo: Any = None, texto: str | None = None) -> None:
        self.status = status
        self.corpo = corpo
        self.texto = texto
        self.requisicoes: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requisicoes.append(request)
        if self.texto is not None:
            return httpx.Response(self.status, text=self.texto)
        return httpx.Response(self.status, json=self.corpo)

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)


def _cliente(capturador: _Capturador) -> PiaClient:
    return PiaClient(
        "https://pia.example.test",
        CREDENCIAL,
        transport=capturador.transport(),
    )


def _requisicao_minima() -> m.PublicEvaluationRequest:
    return m.PublicEvaluationRequest(
        items=(
            m.PublicUpstreamUnavailableItem(
                kind="upstream_unavailable",
                reference="src-1",
                reason="fonte fora do ar",
            ),
        )
    )


def _envelope(itens: int = 1) -> dict[str, Any]:
    return {
        "data": {
            "contract_version": "e6.public-evaluation/1",
            "request_length": itens,
            "decomposed_conflict_dimensions": [],
            "items": [
                {
                    "position": i,
                    "scientific": {
                        "kind": "upstream_unavailable",
                        "reference": f"src-{i}",
                        "reason": "fonte fora do ar",
                    },
                    "routing": {
                        "kind": "upstream_unavailable_routing",
                        "source_reference": f"src-{i}",
                        "reason": "fonte fora do ar",
                        "route": None,
                        "abstained": True,
                    },
                }
                for i in range(itens)
            ],
        },
        "message": None,
    }


# --- prova 4: método, rota, JSON e Bearer exatos --------------------------


def test_sdk01_evaluate_envia_metodo_rota_json_e_bearer_exatos() -> None:
    capturador = _Capturador(corpo=_envelope())
    with _cliente(capturador) as cliente:
        cliente.evaluate(_requisicao_minima())

    (requisicao,) = capturador.requisicoes
    assert requisicao.method == "POST"
    assert requisicao.url.path == "/api/v1/predictive-evaluations"
    assert requisicao.headers["Authorization"] == f"Bearer {CREDENCIAL}"
    enviado = json.loads(requisicao.content)
    assert enviado["items"][0]["kind"] == "upstream_unavailable"
    assert enviado["contract_version"] == "e6.public-evaluation/1"


_CORPOS_PUBLICOS = {
    "/api/v1/health": {"status": "ok"},
    "/api/v1/status": {
        "status": "ok",
        "database_connected": True,
        "database_response_time_ms": 1.0,
        "environment": "testing",
        "uptime_seconds": 1.0,
        "api_version": "v1",
        "modules_loaded": 5,
        "components": [],
    },
    "/api/v1/version": {
        "app_name": "PIA-OS Backend",
        "version": "0.1.0",
        "environment": "testing",
        "api_version": "v1",
        "pia_os_version": "1.0.0",
        "database_version": None,
    },
}

_OPERACOES_PUBLICAS = [
    ("health", "/api/v1/health"),
    ("status", "/api/v1/status"),
    ("version", "/api/v1/version"),
]


@pytest.mark.parametrize(("metodo", "caminho"), _OPERACOES_PUBLICAS)
def test_sdk02_observabilidade_usa_get_na_rota_correta(metodo: str, caminho: str) -> None:
    capturador = _Capturador(corpo=_CORPOS_PUBLICOS[caminho])
    with _cliente(capturador) as cliente:
        getattr(cliente, metodo)()
    (requisicao,) = capturador.requisicoes
    assert requisicao.method == "GET"
    assert requisicao.url.path == caminho
    assert requisicao.headers["Accept"] == "application/json"


@pytest.mark.parametrize(("metodo", "caminho"), _OPERACOES_PUBLICAS)
def test_sdk02b_operacao_publica_nao_recebe_a_credencial(metodo: str, caminho: str) -> None:
    """O OpenAPI declara `security` só em `POST /predictive-evaluations`.

    O servidor aceitar o header não torna necessário enviá-lo: cada ponto
    a mais por onde o segredo passa é mais um lugar onde middleware,
    proxy, telemetria ou handler público pode observá-lo.

    ```text
    SERVER_ACCEPTS_HEADER != CLIENT_SHOULD_SEND_HEADER
    SECRET_MINIMIZATION = REQUIRED
    ```
    """
    capturador = _Capturador(corpo=_CORPOS_PUBLICOS[caminho])
    with _cliente(capturador) as cliente:
        getattr(cliente, metodo)()
    (requisicao,) = capturador.requisicoes
    assert "Authorization" not in requisicao.headers
    assert "authorization" not in {chave.lower() for chave in requisicao.headers}
    assert CREDENCIAL not in str(requisicao.headers)


def test_sdk02c_o_snapshot_confirma_quais_operacoes_exigem_credencial() -> None:
    """A regra do cliente é derivada do contrato, não de preferência.

    Se o servidor passar a exigir Bearer numa rota hoje pública, este
    teste reprova e obriga a revisar o cliente — em vez de deixá-lo
    silenciosamente desalinhado.
    """
    documento = json.loads(
        (RAIZ / "schema" / "openapi_chain107_r1.json").read_text(encoding="utf-8")
    )
    com_seguranca = {
        caminho
        for caminho, operacoes in documento["paths"].items()
        for operacao in operacoes.values()
        if isinstance(operacao, dict) and operacao.get("security")
    }
    assert com_seguranca == {"/api/v1/predictive-evaluations"}, com_seguranca
    for _, caminho in _OPERACOES_PUBLICAS:
        assert caminho not in com_seguranca


def test_sdk02d_a_autenticacao_e_parametro_explicito_sem_default() -> None:
    """Operação nova é forçada a declarar; não herda o vizinho.

    Um default faria a próxima rota adicionada enviar (ou omitir) o
    segredo por acidente de posição no arquivo.
    """
    import inspect

    from pia_os_sdk.client import PiaClient as _Cliente

    for nome in ("_request", "_headers"):
        parametro = inspect.signature(getattr(_Cliente, nome)).parameters["authenticated"]
        assert parametro.default is inspect.Parameter.empty, nome
        assert parametro.kind is inspect.Parameter.KEYWORD_ONLY, nome


def test_sdk02e_evaluate_envia_exatamente_um_bearer() -> None:
    capturador = _Capturador(corpo=_envelope())
    with _cliente(capturador) as cliente:
        cliente.evaluate(_requisicao_minima())
    (requisicao,) = capturador.requisicoes
    autorizacoes = [v for k, v in requisicao.headers.multi_items() if k.lower() == "authorization"]
    assert autorizacoes == [f"Bearer {CREDENCIAL}"]


# --- prova 5: ordem e cardinalidade preservadas ---------------------------


def test_sdk03_resposta_preserva_ordem_e_cardinalidade() -> None:
    capturador = _Capturador(corpo=_envelope(itens=3))
    with _cliente(capturador) as cliente:
        resposta = cliente.evaluate(_requisicao_minima())
    assert resposta.data.request_length == 3
    assert [item.position for item in resposta.data.items] == [0, 1, 2]


def test_sdk04_campo_desconhecido_na_resposta_e_recusado() -> None:
    """`extra="forbid"`: divergência de contrato aparece agora, não depois."""
    corpo = _envelope()
    corpo["data"]["campo_que_o_servidor_nao_promete"] = 1
    from pydantic import ValidationError

    capturador = _Capturador(corpo=corpo)
    with _cliente(capturador) as cliente, pytest.raises(ValidationError):
        cliente.evaluate(_requisicao_minima())


# --- prova 6: status e código PIA preservados -----------------------------


@pytest.mark.parametrize(
    ("status", "codigo"),
    [
        (401, "PIA-7001"),
        (403, "PIA-7002"),
        (422, "PIA-2001"),
        (429, "PIA-1008"),
        (500, "PIA-0002"),
        (503, "PIA-3002"),
    ],
)
def test_sdk05_erros_preservam_status_e_codigo(status: int, codigo: str) -> None:
    capturador = _Capturador(
        status=status,
        corpo={
            "success": False,
            "error": {"code": codigo, "message": "erro", "detail": "detalhe público"},
        },
    )
    with _cliente(capturador) as cliente, pytest.raises(PiaApiError) as erro:
        cliente.evaluate(_requisicao_minima())
    assert erro.value.status_code == status
    assert erro.value.code == codigo
    assert erro.value.detail == "detalhe público"


def test_sdk06_o_cliente_nao_reinterpreta_503_como_429() -> None:
    """`QUOTA_EXCEEDED != QUOTA_AUTHORITY_UNAVAILABLE` também no cliente."""
    capturador = _Capturador(
        status=503,
        corpo={"success": False, "error": {"code": "PIA-3002", "message": "indisp"}},
    )
    with _cliente(capturador) as cliente, pytest.raises(PiaApiError) as erro:
        cliente.evaluate(_requisicao_minima())
    assert erro.value.status_code == 503
    assert erro.value.status_code != 429
    assert erro.value.code == "PIA-3002"


def test_sdk07_corpo_de_erro_fora_do_envelope_nao_quebra_o_cliente() -> None:
    """Proxy ou gateway devolvendo HTML não pode virar exceção interna."""
    capturador = _Capturador(status=502, texto="<html>bad gateway</html>")
    with _cliente(capturador) as cliente, pytest.raises(PiaApiError) as erro:
        cliente.health()
    assert erro.value.status_code == 502
    assert erro.value.code is None
    assert "bad gateway" in str(erro.value.detail)


def test_sdk08_falha_de_transporte_nao_vira_erro_de_api() -> None:
    def _explode(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("sem rota para o host")

    cliente = PiaClient(
        "https://pia.example.test", CREDENCIAL, transport=httpx.MockTransport(_explode)
    )
    with cliente, pytest.raises(PiaTransportError):
        cliente.health()


def test_sdk09_nao_ha_retry_automatico() -> None:
    """`RETRY != DUPLICATE_EFFECT` — repetir é decisão de quem chama."""
    capturador = _Capturador(
        status=503,
        corpo={"success": False, "error": {"code": "PIA-3002", "message": "x"}},
    )
    with _cliente(capturador) as cliente, pytest.raises(PiaApiError):
        cliente.evaluate(_requisicao_minima())
    assert len(capturador.requisicoes) == 1


# --- prova 7: credencial não vaza -----------------------------------------


def test_sdk10_credencial_nao_aparece_em_repr() -> None:
    capturador = _Capturador(corpo={"status": "ok"})
    with _cliente(capturador) as cliente:
        texto = f"{cliente!r} {cliente}"
    assert CREDENCIAL not in texto
    assert "segredo-de-alta-entropia" not in texto


def test_sdk11_credencial_nao_aparece_em_erro_nem_em_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    capturador = _Capturador(
        status=401,
        corpo={"success": False, "error": {"code": "PIA-7001", "message": "auth"}},
    )
    with (
        caplog.at_level(logging.DEBUG),
        _cliente(capturador) as cliente,
        pytest.raises(PiaApiError) as erro,
    ):
        cliente.evaluate(_requisicao_minima())
    texto = f"{erro.value} {erro.value!r} {caplog.text}"
    assert CREDENCIAL not in texto


def test_sdk12_credencial_e_base_url_sao_obrigatorias() -> None:
    with pytest.raises(ValueError):
        PiaClient("", CREDENCIAL)
    with pytest.raises(ValueError):
        PiaClient("https://pia.example.test", "")


# --- prova 8: fronteira de import do runtime ------------------------------


def _imports(caminho: pathlib.Path) -> set[str]:
    modulos: set[str] = set()
    for no in ast.walk(ast.parse(caminho.read_text(encoding="utf-8"))):
        if isinstance(no, ast.Import):
            modulos.update(a.name for a in no.names)
        elif isinstance(no, ast.ImportFrom) and no.module:
            modulos.add(no.module)
    return modulos


def test_sdk13_runtime_do_sdk_nao_importa_backend_nem_banco() -> None:
    proibidos = (
        "app",
        "main",
        "sqlalchemy",
        "alembic",
        "psycopg",
        "fastapi",
        "starlette",
    )
    for caminho in sorted(RUNTIME.glob("*.py")):
        for modulo in _imports(caminho):
            assert modulo.split(".")[0] not in proibidos, (caminho.name, modulo)


def test_sdk14_runtime_do_sdk_nao_contem_ciencia_nem_roteamento() -> None:
    """O cliente não pode calcular o que o servidor decide."""
    proibidos = (
        "predictive_route",
        "predictive_evaluate_batch",
        "predictive_conflict",
        "predictive_assertiveness",
        "PiapEnvelope",
        "serialize_piap_envelope",
        "approval_binding",
    )
    for caminho in sorted(RUNTIME.glob("*.py")):
        texto = caminho.read_text(encoding="utf-8")
        for termo in proibidos:
            assert termo not in texto, (caminho.name, termo)


def test_sdk15_o_sdk_nao_inventa_rota_fora_do_openapi() -> None:
    """`get_capacity_limits()` não existe porque o endpoint não existe."""
    documento = json.loads(
        (RAIZ / "schema" / "openapi_chain107_r1.json").read_text(encoding="utf-8")
    )
    caminhos_reais = set(documento["paths"])
    fonte = (RUNTIME / "client.py").read_text(encoding="utf-8")
    for no in ast.walk(ast.parse(fonte)):
        if (
            isinstance(no, ast.Constant)
            and isinstance(no.value, str)
            and no.value.startswith("/api/")
        ):
            assert no.value in caminhos_reais, no.value
    assert "capacity" not in fonte


def test_sdk16_modelos_declaram_o_sha_do_snapshot() -> None:
    import hashlib

    snapshot = (RAIZ / "schema" / "openapi_chain107_r1.json").read_bytes()
    assert hashlib.sha256(snapshot).hexdigest() == m.OPENAPI_SNAPSHOT_SHA256
