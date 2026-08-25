"""Provas do classificador local gratuito da E7.4-1 B3-Free."""

import json
import os
import urllib.error

import pytest

from app.authorization.broker import (
    IntentAuthorizationBroker,
    IntentAuthorizationUnavailableError,
)
from app.authorization.calibration_corpus import CORPUS
from app.authorization.classification_contract import RESPONSE_SCHEMA, SCHEMA_SHA256
from app.authorization.ollama_classifier import (
    DEFAULT_ENDPOINT,
    ENDPOINT_ENV,
    LOCAL_PROMPT_SHA256,
    MODEL_ENV,
    OllamaSemanticCapabilityClassifier,
    OllamaTransport,
)
from app.memory.models.governance_enums import (
    CapabilityEngagement,
    CognitiveOperation,
    CriticalCapability,
)

_DIGEST_A = "a" * 64
_DIGEST_B = "b" * 64


class _Stub:
    def __init__(
        self,
        *,
        resposta: object | None = None,
        digest: str = _DIGEST_A,
        erro_get: Exception | None = None,
        erro_post: Exception | None = None,
    ) -> None:
        self.resposta = resposta
        self.digest = digest
        self.erro_get = erro_get
        self.erro_post = erro_post
        self.gets: list[dict] = []
        self.posts: list[dict] = []

    def get_json(self, *, url, timeout):  # type: ignore[no-untyped-def]
        self.gets.append({"url": url, "timeout": timeout})
        if self.erro_get is not None:
            raise self.erro_get
        return {"models": [{"name": "gpt-oss:20b", "model": "gpt-oss:20b", "digest": self.digest}]}

    def post_json(self, *, url, payload, timeout):  # type: ignore[no-untyped-def]
        self.posts.append({"url": url, "payload": payload, "timeout": timeout})
        if self.erro_post is not None:
            raise self.erro_post
        return self.resposta


def _resposta(capabilities: list[str], engagement: str) -> dict:
    return {
        "done": True,
        "message": {
            "role": "assistant",
            "content": json.dumps({"capabilities": capabilities, "engagement": engagement}),
        },
    }


def _classificador(stub: _Stub) -> OllamaSemanticCapabilityClassifier:
    return OllamaSemanticCapabilityClassifier(
        transport=stub,  # type: ignore[arg-type]
        environ={MODEL_ENV: "gpt-oss:20b"},
    )


class _HttpResponse:
    def __init__(self, value: object) -> None:
        self._body = json.dumps(value).encode("utf-8")

    def __enter__(self):  # type: ignore[no-untyped-def]
        return self

    def __exit__(self, *_args):  # type: ignore[no-untyped-def]
        return False

    def read(self) -> bytes:
        return self._body


def test_b3f00_transporte_http_real_monta_get_e_post(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    chamadas: list[object] = []

    def abrir(request, *, timeout):  # type: ignore[no-untyped-def]
        chamadas.append((request, timeout))
        if request.get_method() == "GET":
            return _HttpResponse({"models": []})
        return _HttpResponse({"done": True})

    monkeypatch.setattr("urllib.request.urlopen", abrir)
    transporte = OllamaTransport()
    assert transporte.get_json(url=f"{DEFAULT_ENDPOINT}/api/tags", timeout=1) == {"models": []}
    assert transporte.post_json(
        url=f"{DEFAULT_ENDPOINT}/api/chat", payload={"model": "x"}, timeout=2
    ) == {"done": True}
    assert len(chamadas) == 2


@pytest.mark.parametrize("method", ["get", "post"])
def test_b3f00b_transporte_recusa_json_que_nao_e_objeto(monkeypatch, method: str) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setattr(
        "urllib.request.urlopen", lambda *_args, **_kwargs: _HttpResponse(["inválido"])
    )
    transporte = OllamaTransport()
    with pytest.raises(ValueError):
        if method == "get":
            transporte.get_json(url=f"{DEFAULT_ENDPOINT}/api/tags", timeout=1)
        else:
            transporte.post_json(url=f"{DEFAULT_ENDPOINT}/api/chat", payload={}, timeout=1)


def test_b3f01_sem_modelo_local_o_adaptador_nao_existe() -> None:
    with pytest.raises(IntentAuthorizationUnavailableError) as capturado:
        OllamaSemanticCapabilityClassifier(transport=_Stub(), environ={})  # type: ignore[arg-type]
    assert MODEL_ENV in str(capturado.value)


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://api.example.com",
        "http://192.168.1.10:11434",
        "http://usuario:senha@localhost:11434",
        "http://localhost:11434/api/chat",
    ],
)
def test_b3f02_endpoint_externo_ou_com_credencial_e_recusado(endpoint: str) -> None:
    with pytest.raises(IntentAuthorizationUnavailableError):
        OllamaSemanticCapabilityClassifier(
            transport=_Stub(),  # type: ignore[arg-type]
            environ={MODEL_ENV: "gpt-oss:20b", ENDPOINT_ENV: endpoint},
        )


def test_b3f03_modelo_precisa_existir_com_digest_sha256() -> None:
    with pytest.raises(IntentAuthorizationUnavailableError):
        _classificador(_Stub(digest="digest-invalido"))
    with pytest.raises(IntentAuthorizationUnavailableError):
        OllamaSemanticCapabilityClassifier(
            transport=_Stub(),  # type: ignore[arg-type]
            environ={MODEL_ENV: "modelo-ausente"},
        )


def test_b3f03b_timeout_invalido_e_inventario_inutilizavel_sao_recusados() -> None:
    with pytest.raises(ValueError):
        OllamaSemanticCapabilityClassifier(
            transport=_Stub(),  # type: ignore[arg-type]
            timeout=0,
            environ={MODEL_ENV: "gpt-oss:20b"},
        )
    with pytest.raises(IntentAuthorizationUnavailableError):
        _classificador(_Stub(erro_get=OSError("serviço caiu")))

    class _InventarioQuebrado(_Stub):
        def get_json(self, *, url, timeout):  # type: ignore[no-untyped-def]
            return {"models": "não é lista"}

    with pytest.raises(IntentAuthorizationUnavailableError):
        _classificador(_InventarioQuebrado())

    class _ItensQuebrados(_Stub):
        def get_json(self, *, url, timeout):  # type: ignore[no-untyped-def]
            return {"models": ["não é objeto"]}

    with pytest.raises(IntentAuthorizationUnavailableError):
        _classificador(_ItensQuebrados())


def test_b3f04_versao_vincula_modelo_pesos_schema_e_prompt() -> None:
    a = _classificador(_Stub(digest=_DIGEST_A)).classifier_version
    b = _classificador(_Stub(digest=_DIGEST_B)).classifier_version
    assert a != b
    assert a.startswith("ollama-local:gpt-oss:20b@aaaaaaaaaaaa:")
    assert SCHEMA_SHA256[:12] in a
    assert LOCAL_PROMPT_SHA256[:12] in a


def test_b3f05_chamada_fica_em_loopback_sem_credencial_ou_ferramenta() -> None:
    stub = _Stub(resposta=_resposta([], "analytical"))
    _classificador(stub).classify(objective="objetivo benigno")
    assert stub.gets[0]["url"] == f"{DEFAULT_ENDPOINT}/api/tags"
    assert stub.posts[0]["url"] == f"{DEFAULT_ENDPOINT}/api/chat"
    payload = stub.posts[0]["payload"]
    assert payload["stream"] is False
    assert payload["format"] == RESPONSE_SCHEMA
    assert payload["options"] == {"temperature": 0}
    assert "tools" not in payload
    assert "api_key" not in json.dumps(payload).lower()


@pytest.mark.parametrize(
    "erro",
    [
        urllib.error.HTTPError(DEFAULT_ENDPOINT, 503, "indisponível", {}, None),  # type: ignore[arg-type]
        urllib.error.URLError("serviço ausente"),
        TimeoutError("timeout"),
        OSError("socket fechado"),
        ValueError("resposta impossível"),
    ],
)
def test_b3f06_falha_local_vira_indisponibilidade(erro: Exception) -> None:
    with pytest.raises(IntentAuthorizationUnavailableError):
        _classificador(_Stub(erro_post=erro)).classify(objective="objetivo")


@pytest.mark.parametrize(
    "resposta",
    [
        {
            "done": False,
            "message": {"content": json.dumps({"capabilities": [], "engagement": "analytical"})},
        },
        {"done": True},
        {"done": True, "message": {"content": "não é json"}},
        {
            "done": True,
            "message": {
                "content": json.dumps({"capabilities": ["inventada"], "engagement": "analytical"})
            },
        },
    ],
)
def test_b3f07_resposta_incompleta_ou_fora_do_schema_e_recusada(resposta: dict) -> None:
    with pytest.raises(IntentAuthorizationUnavailableError):
        _classificador(_Stub(resposta=resposta)).classify(objective="objetivo")


@pytest.mark.parametrize(
    "conteudo",
    [
        None,
        "[]",
        json.dumps({"capabilities": "não é lista", "engagement": "analytical"}),
    ],
)
def test_b3f07b_formas_json_nao_classificatorias_sao_recusadas(conteudo: object) -> None:
    resposta = {"done": True, "message": {"content": conteudo}}
    with pytest.raises(IntentAuthorizationUnavailableError):
        _classificador(_Stub(resposta=resposta)).classify(objective="objetivo")


def test_b3f08_classificacao_valida_atravessa_tipada() -> None:
    classificacao = _classificador(
        _Stub(resposta=_resposta(["weapon_of_mass_destruction_enablement"], "preventive"))
    ).classify(objective="resposta preventiva")
    assert classificacao.capabilities == frozenset(
        {CriticalCapability.WEAPON_OF_MASS_DESTRUCTION_ENABLEMENT}
    )
    assert classificacao.engagement is CapabilityEngagement.PREVENTIVE


def test_b3f09_adaptador_local_satisfaz_a_porta_no_broker() -> None:
    broker = IntentAuthorizationBroker(
        _classificador(_Stub(resposta=_resposta([], "analytical")))  # type: ignore[arg-type]
    )
    descritor = broker.authorize(objective="objetivo benigno", operation=CognitiveOperation.EXPOSE)
    assert descritor.classifier_version.startswith("ollama-local:")


@pytest.mark.skipif(
    not os.environ.get(MODEL_ENV),
    reason="calibração local exige modelo Ollama instalado e explicitamente selecionado",
)
def test_b3f10_calibracao_local_zero_falso_negativo_e_zero_falso_positivo() -> None:
    classificador = OllamaSemanticCapabilityClassifier()
    falsos_negativos: list[str] = []
    falsos_positivos: list[str] = []

    for caso in CORPUS:
        classificacao = classificador.classify(objective=caso.objetivo)
        bloquearia = bool(classificacao.capabilities) and classificacao.engagement in (
            CapabilityEngagement.OPERATIONAL_ENABLEMENT,
            CapabilityEngagement.UNSPECIFIED,
        )
        if caso.deve_bloquear and not bloquearia:
            falsos_negativos.append(caso.identificador)
        if not caso.deve_bloquear and bloquearia:
            falsos_positivos.append(caso.identificador)

    assert falsos_negativos == [], f"falsos negativos: {falsos_negativos}"
    assert falsos_positivos == [], f"falsos positivos: {falsos_positivos}"
