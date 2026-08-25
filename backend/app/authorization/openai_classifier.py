"""
`OpenAISemanticCapabilityClassifier` — composição produtiva da porta
semântica da E8 (`E7.4-1 B3`).

```text
CONTRACT_PROVEN != CAPABILITY_PROVEN
```

Até aqui a não-vacuidade da E8 estava provada como **contrato**: um
classificador declarava cobrir o vocabulário fechado e o broker o exigia.
Declaração de cobertura não classifica nada. Este adaptador é o produtor
real, e é o que separa `BRIDGE_READY` de `OPERATIONAL_PROTECTION`.

## Superfície mínima, deliberadamente

A chamada é **transporte interno de segurança**: nenhuma ferramenta,
nenhuma busca, nenhum arquivo, nenhuma memória, nenhuma execução,
`store=false`. O modelo recebe o objetivo e devolve dois rótulos de
vocabulário fechado. Nada mais.

```text
CLASSIFIER_WITH_TOOLS = SECOND_EXECUTION_PATH
STORED_PROMPT = PAYLOAD_ARCHIVE_OF_THE_THING_WE_REFUSED
```

Dar ferramentas ao classificador criaria um segundo caminho de execução
dentro do gate que existe para impedir execução. Persistir o prompt
arquivaria justamente o conteúdo que a fronteira se comprometeu a não
guardar.

## Sem default silencioso

Credencial e modelo vêm do ambiente e **não** têm default. Um modelo
default faria uma instalação mal configurada classificar em silêncio com
competência que ninguém escolheu — e passar no gate.

```text
SILENT_DEFAULT_MODEL = UNCHOSEN_AUTHORITY
```

## Identidade da competência

`classifier_version` carrega provider, modelo e os hashes do schema e do
prompt. Trocar qualquer um dos três muda a versão, e versão nova invalida
a calibração: a evidência de que o classificador acerta foi colhida sobre
uma competência específica, não sobre a ideia de classificar.

```text
MODEL_SWAP -> CALIBRATION_VOID
PROMPT_SWAP -> CALIBRATION_VOID
SCHEMA_SWAP -> CALIBRATION_VOID
```

## Falhar é recusar

Timeout, rede, credencial ausente, recusa do provider, JSON inválido,
rótulo fora do vocabulário — tudo vira `PIA-8070` pelo broker, com zero
efeito. Nenhum caminho aqui devolve classificação de conveniência.
"""

import json
import os
import urllib.error
import urllib.request
from typing import Any, Final

from app.authorization.broker import IntentAuthorizationUnavailableError
from app.authorization.classification_contract import (
    CAPABILITY_VALUES as CAPABILITY_VALUES,
)
from app.authorization.classification_contract import (
    CLASSIFICATION_PROMPT,
    PROMPT_SHA256,
    RESPONSE_SCHEMA,
    SCHEMA_SHA256,
    interpret_classification_text,
)
from app.authorization.classification_contract import (
    ENGAGEMENT_VALUES as ENGAGEMENT_VALUES,
)
from app.authorization.ports import SemanticClassification
from app.memory.models.governance_enums import CriticalCapability

API_KEY_ENV: Final = "PIA_SAFETY_OPENAI_API_KEY"
MODEL_ENV: Final = "PIA_SAFETY_OPENAI_MODEL"
ENDPOINT: Final = "https://api.openai.com/v1/responses"
PROVIDER: Final = "openai"
DEFAULT_TIMEOUT_SECONDS: Final = 20.0


class HttpTransport:
    """Transporte mínimo. Existe para ser substituído em teste."""

    def post_json(
        self, *, url: str, payload: dict[str, Any], headers: dict[str, str], timeout: float
    ) -> dict[str, Any]:
        corpo = json.dumps(payload).encode("utf-8")
        requisicao = urllib.request.Request(url, data=corpo, headers=headers, method="POST")
        with urllib.request.urlopen(requisicao, timeout=timeout) as resposta:  # noqa: S310
            decodificado: object = json.loads(resposta.read().decode("utf-8"))
        if not isinstance(decodificado, dict):
            raise ValueError("resposta do provider não é um objeto JSON")
        return decodificado


class OpenAISemanticCapabilityClassifier:
    """Produtor semântico real da E8, sobre a Responses API."""

    def __init__(
        self,
        *,
        transport: HttpTransport | None = None,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        environ: dict[str, str] | None = None,
    ) -> None:
        ambiente = environ if environ is not None else dict(os.environ)

        modelo = ambiente.get(MODEL_ENV, "").strip()
        if not modelo:
            raise IntentAuthorizationUnavailableError(
                f"{MODEL_ENV} não definido — sem modelo default: uma instalação mal "
                "configurada classificaria em silêncio com competência não escolhida"
            )

        credencial = ambiente.get(API_KEY_ENV, "").strip()
        if not credencial:
            raise IntentAuthorizationUnavailableError(
                f"{API_KEY_ENV} não definida — credencial só pode vir desta variável"
            )

        self._model = modelo
        self._credential = credencial
        self._transport = transport if transport is not None else HttpTransport()
        self._timeout = timeout

    @property
    def classifier_version(self) -> str:
        """Provider, modelo e os hashes do schema e do prompt.

        Curto nos hashes (12 dígitos) porque o campo tem limite de tamanho
        no binding; longo o bastante para que uma troca não colida.
        """
        return (
            f"{PROVIDER}:{self._model}"
            f":schema-{SCHEMA_SHA256[:12]}"
            f":prompt-{PROMPT_SHA256[:12]}"
        )

    @property
    def covered_capabilities(self) -> frozenset[CriticalCapability]:
        """Cobertura real: o schema enumera o vocabulário fechado inteiro."""
        return frozenset(CriticalCapability)

    def classify(self, *, objective: str) -> SemanticClassification:
        """Classifica o objetivo. Qualquer falha vira recusa."""
        payload: dict[str, Any] = {
            "model": self._model,
            "store": False,
            "tools": [],
            "input": [
                {"role": "system", "content": CLASSIFICATION_PROMPT},
                {"role": "user", "content": objective},
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "capability_classification",
                    "strict": True,
                    "schema": RESPONSE_SCHEMA,
                }
            },
        }
        headers = {
            "Authorization": f"Bearer {self._credential}",
            "Content-Type": "application/json",
        }

        try:
            resposta = self._transport.post_json(
                url=ENDPOINT, payload=payload, headers=headers, timeout=self._timeout
            )
        except urllib.error.HTTPError as falha:
            raise IntentAuthorizationUnavailableError(
                f"provider recusou a classificação (HTTP {falha.code})"
            ) from falha
        except (urllib.error.URLError, TimeoutError, OSError) as falha:
            raise IntentAuthorizationUnavailableError(
                f"transporte falhou ao classificar: {falha}"
            ) from falha
        except Exception as falha:  # noqa: BLE001 - nenhuma falha vira permissão
            raise IntentAuthorizationUnavailableError(
                f"classificação não pôde ser obtida: {falha}"
            ) from falha

        return self._interpretar(resposta)

    @staticmethod
    def _interpretar(resposta: object) -> SemanticClassification:
        """Extrai os dois rótulos, ou recusa.

        Recusa explícita do provider é tratada como indisponibilidade, e
        não como "nada encontrado": um `refusal` convertido em conjunto
        vazio viraria permissão silenciosa exatamente no caso em que o
        provider achou o objetivo grave demais para responder.
        """
        if not isinstance(resposta, dict):
            raise IntentAuthorizationUnavailableError("resposta do provider não é um objeto")

        texto: str | None = None
        for item in resposta.get("output", []) or []:
            if not isinstance(item, dict):
                continue
            for parte in item.get("content", []) or []:
                if not isinstance(parte, dict):
                    continue
                if parte.get("type") == "refusal":
                    raise IntentAuthorizationUnavailableError(
                        "provider recusou classificar — recusa não é ausência de capacidade"
                    )
                if parte.get("type") in ("output_text", "text") and isinstance(
                    parte.get("text"), str
                ):
                    texto = parte["text"]

        if texto is None:
            texto_direto = resposta.get("output_text")
            if isinstance(texto_direto, str):
                texto = texto_direto

        if texto is None:
            raise IntentAuthorizationUnavailableError(
                "resposta do provider não trouxe saída classificatória"
            )

        return interpret_classification_text(texto)
