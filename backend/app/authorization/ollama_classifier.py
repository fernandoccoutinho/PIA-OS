"""Classificador semântico local e gratuito da E8 (`E7.4-1 B3-Free`).

O modelo roda no host do DSVH por Ollama. Nenhum objetivo, prompt ou resultado
sai da interface de loopback; não há API key nem cobrança por chamada.

O adaptador continua fail-closed. Serviço ausente, modelo não instalado,
digest inválido, timeout, JSON inválido ou rótulo fora do vocabulário viram
`PIA-8070`, nunca conjunto vazio por conveniência.
"""

import hashlib
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Final

from app.authorization.broker import IntentAuthorizationUnavailableError
from app.authorization.classification_contract import (
    CLASSIFICATION_PROMPT,
    RESPONSE_SCHEMA,
    SCHEMA_SHA256,
    interpret_classification_text,
)
from app.authorization.ports import SemanticClassification
from app.memory.models.governance_enums import CriticalCapability

MODEL_ENV: Final = "PIA_SAFETY_LOCAL_MODEL"
ENDPOINT_ENV: Final = "PIA_SAFETY_LOCAL_ENDPOINT"
DEFAULT_ENDPOINT: Final = "http://127.0.0.1:11434"
DEFAULT_TIMEOUT_SECONDS: Final = 180.0
PROVIDER: Final = "ollama-local"
LOOPBACK_HOSTS: Final = frozenset({"127.0.0.1", "localhost", "::1"})

LOCAL_PROMPT: Final = (
    CLASSIFICATION_PROMPT
    + "\n\nSchema JSON obrigatório:\n"
    + json.dumps(RESPONSE_SCHEMA, sort_keys=True, separators=(",", ":"))
)
LOCAL_PROMPT_SHA256: Final = hashlib.sha256(LOCAL_PROMPT.encode("utf-8")).hexdigest()
_DIGEST_RE: Final = re.compile(r"^[0-9a-f]{64}$")


class OllamaTransport:
    """HTTP mínimo, substituível em prova e restrito pelo adaptador a loopback."""

    def get_json(self, *, url: str, timeout: float) -> dict[str, Any]:
        requisicao = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(requisicao, timeout=timeout) as resposta:  # noqa: S310
            decodificado: object = json.loads(resposta.read().decode("utf-8"))
        if not isinstance(decodificado, dict):
            raise ValueError("resposta do Ollama não é objeto JSON")
        return decodificado

    def post_json(self, *, url: str, payload: dict[str, Any], timeout: float) -> dict[str, Any]:
        corpo = json.dumps(payload).encode("utf-8")
        requisicao = urllib.request.Request(
            url,
            data=corpo,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(requisicao, timeout=timeout) as resposta:  # noqa: S310
            decodificado: object = json.loads(resposta.read().decode("utf-8"))
        if not isinstance(decodificado, dict):
            raise ValueError("resposta do Ollama não é objeto JSON")
        return decodificado


class OllamaSemanticCapabilityClassifier:
    """Produtor semântico local, ligado ao digest real dos pesos instalados."""

    def __init__(
        self,
        *,
        transport: OllamaTransport | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        environ: dict[str, str] | None = None,
    ) -> None:
        ambiente = environ if environ is not None else dict(os.environ)
        modelo = ambiente.get(MODEL_ENV, "").strip()
        if not modelo:
            raise IntentAuthorizationUnavailableError(
                f"{MODEL_ENV} não definido — modelo local não pode ter default silencioso"
            )

        endpoint = ambiente.get(ENDPOINT_ENV, DEFAULT_ENDPOINT).strip().rstrip("/")
        self._require_loopback(endpoint)
        if timeout <= 0:
            raise ValueError("timeout deve ser estritamente positivo")

        self._model = modelo
        self._endpoint = endpoint
        self._transport = transport if transport is not None else OllamaTransport()
        self._timeout = timeout
        self._model_digest = self._resolve_model_digest()

    @staticmethod
    def _require_loopback(endpoint: str) -> None:
        analisado = urllib.parse.urlparse(endpoint)
        if (
            analisado.scheme != "http"
            or analisado.hostname not in LOOPBACK_HOSTS
            or analisado.username is not None
            or analisado.password is not None
            or analisado.path not in ("", "/")
            or analisado.query
            or analisado.fragment
        ):
            raise IntentAuthorizationUnavailableError(
                f"{ENDPOINT_ENV} deve ser HTTP de loopback sem credencial ou caminho"
            )

    def _resolve_model_digest(self) -> str:
        try:
            resposta = self._transport.get_json(
                url=f"{self._endpoint}/api/tags", timeout=self._timeout
            )
        except Exception as falha:  # noqa: BLE001 - descoberta também é fail-closed
            raise IntentAuthorizationUnavailableError(
                f"não foi possível consultar o modelo local: {falha}"
            ) from falha

        modelos = resposta.get("models")
        if not isinstance(modelos, list):
            raise IntentAuthorizationUnavailableError(
                "Ollama não devolveu inventário de modelos utilizável"
            )

        for item in modelos:
            if not isinstance(item, dict):
                continue
            if self._model not in (item.get("name"), item.get("model")):
                continue
            digest = item.get("digest")
            if isinstance(digest, str) and _DIGEST_RE.fullmatch(digest):
                return digest
            raise IntentAuthorizationUnavailableError(
                "modelo local encontrado sem digest SHA-256 utilizável"
            )

        raise IntentAuthorizationUnavailableError(
            f"modelo local '{self._model}' não está instalado no Ollama"
        )

    @property
    def classifier_version(self) -> str:
        return (
            f"{PROVIDER}:{self._model}@{self._model_digest[:12]}"
            f":schema-{SCHEMA_SHA256[:12]}"
            f":prompt-{LOCAL_PROMPT_SHA256[:12]}"
        )

    @property
    def covered_capabilities(self) -> frozenset[CriticalCapability]:
        return frozenset(CriticalCapability)

    def classify(self, *, objective: str) -> SemanticClassification:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": LOCAL_PROMPT},
                {"role": "user", "content": objective},
            ],
            "stream": False,
            "format": RESPONSE_SCHEMA,
            "think": "low",
            "options": {"temperature": 0},
        }
        try:
            resposta = self._transport.post_json(
                url=f"{self._endpoint}/api/chat", payload=payload, timeout=self._timeout
            )
        except urllib.error.HTTPError as falha:
            raise IntentAuthorizationUnavailableError(
                f"Ollama recusou a classificação (HTTP {falha.code})"
            ) from falha
        except (urllib.error.URLError, TimeoutError, OSError) as falha:
            raise IntentAuthorizationUnavailableError(
                f"transporte local falhou ao classificar: {falha}"
            ) from falha
        except Exception as falha:  # noqa: BLE001 - nenhuma falha vira permissão
            raise IntentAuthorizationUnavailableError(
                f"classificação local não pôde ser obtida: {falha}"
            ) from falha

        if resposta.get("done") is not True:
            raise IntentAuthorizationUnavailableError(
                "Ollama não concluiu a resposta classificatória"
            )
        mensagem = resposta.get("message")
        if not isinstance(mensagem, dict):
            raise IntentAuthorizationUnavailableError("Ollama não trouxe mensagem classificatória")
        return interpret_classification_text(mensagem.get("content"))
