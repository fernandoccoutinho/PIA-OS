"""
Cliente síncrono tipado do `pia-os-sdk`.

```text
SDK_SOURCE_OF_TRUTH = FALSE
CLIENT_RECALCULATES_SCIENCE = FALSE
CLIENT_RECALCULATES_ROUTE = FALSE
CLIENT_NORMALIZES_PIAP = FALSE
CLIENT_RETRIES_AUTOMATICALLY = FALSE
```

O cliente representa. Envia o DTO público, recebe o envelope e preserva
campos e ordem. Não recalcula ciência, aprovação ou roteamento, não
normaliza PIAP e não decide por conta própria o que fazer com um erro:
tudo isso pertence ao servidor, que é onde está auditado.

A credencial de serviço só compõe o header `Authorization`, e **somente
nas operações que o OpenAPI declara com `security`**. Hoje é uma só:
`POST /api/v1/predictive-evaluations`. As três rotas de observabilidade
são públicas no contrato e não recebem o segredo.

```text
PUBLIC_OPERATION_WITHOUT_SECURITY_REQUIREMENT
  -> MUST_NOT_RECEIVE_SERVICE_CREDENTIAL
SERVER_ACCEPTS_HEADER != CLIENT_SHOULD_SEND_HEADER
```

O servidor aceitar o header não torna necessário enviá-lo. Cada ponto a
mais por onde o segredo passa é um lugar a mais onde middleware, proxy,
telemetria ou handler público pode observá-lo.

A credencial não aparece em `repr`, exceção ou log — um segredo que
circula em representação textual acaba num relatório de erro.
"""

from __future__ import annotations

from types import TracebackType
from typing import Any

import httpx

from pia_os_sdk.errors import PiaApiError, PiaTransportError
from pia_os_sdk.models import (
    HealthResponse,
    PublicEvaluationRequest,
    StatusResponse,
    SuccessResponsePublicEvaluationResponse,
    VersionResponse,
)

__all__ = ["DEFAULT_TIMEOUT_SECONDS", "PiaClient"]

# Timeout explícito e obrigatório. O padrão do `httpx` é generoso demais
# para uma chamada síncrona de avaliação: sem teto, um servidor lento
# trava o chamador sem que ele tenha escolhido isso.
DEFAULT_TIMEOUT_SECONDS = 30.0

_PATH_EVALUATE = "/api/v1/predictive-evaluations"
_PATH_HEALTH = "/api/v1/health"
_PATH_STATUS = "/api/v1/status"
_PATH_VERSION = "/api/v1/version"


class PiaClient:
    """Cliente do PIA-OS para credencial de SERVIÇO.

    A credencial não representa usuário humano e nunca concede aprovação
    PIAP — ela apenas autoriza chamar a operação HTTP.
    """

    def __init__(
        self,
        base_url: str,
        credential: str,
        *,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.BaseTransport | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        if not base_url:
            raise ValueError("base_url é obrigatória")
        if not credential:
            raise ValueError("credential é obrigatória")
        self._base_url = base_url.rstrip("/")
        # Guardado em atributo privado e nunca exposto em `repr`.
        self.__credential = credential
        self._timeout = timeout
        self._owns_client = client is None
        self._client = client or httpx.Client(
            base_url=self._base_url, timeout=timeout, transport=transport
        )

    # --- ciclo de vida -----------------------------------------------------

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def __enter__(self) -> PiaClient:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def __repr__(self) -> str:
        """Sem credencial. Nem mascarada — o que não é impresso não vaza."""
        return f"PiaClient(base_url={self._base_url!r}, timeout={self._timeout!r})"

    # --- transporte --------------------------------------------------------

    def _headers(self, *, authenticated: bool) -> dict[str, str]:
        """`Accept` sempre; `Authorization` só quando a operação exige.

        O parâmetro é obrigatório e sem default: quem adicionar uma
        operação nova é forçado a declarar se ela é autenticada, em vez de
        herdar silenciosamente o comportamento do vizinho.
        """
        cabecalhos = {"Accept": "application/json"}
        if authenticated:
            cabecalhos["Authorization"] = f"Bearer {self.__credential}"
        return cabecalhos

    def _request(
        self, metodo: str, caminho: str, *, authenticated: bool, json_body: Any = None
    ) -> Any:
        """Transporte único. `authenticated` é decisão explícita da chamada.

        Não é derivado de substring da URL nem de lista configurável em
        runtime: um casamento de prefixo mandaria o segredo para qualquer
        rota nova cujo caminho se pareça com a autenticada, e uma lista
        mutável permitiria ampliar a exposição sem alterar código revisado.

        ```text
        AUTH_DECISION = PER_CALL_EXPLICIT
        AUTH_DECISION != URL_SUBSTRING
        AUTH_DECISION != RUNTIME_CONFIG
        ```
        """
        try:
            resposta = self._client.request(
                metodo,
                caminho,
                json=json_body,
                headers=self._headers(authenticated=authenticated),
            )
        except httpx.HTTPError as exc:
            # Sem status nem código PIA: não houve resposta do servidor.
            raise PiaTransportError(f"falha de transporte em {metodo} {caminho}") from exc

        if resposta.status_code >= 400:
            try:
                corpo: object = resposta.json()
            except ValueError:
                corpo = resposta.text
            raise PiaApiError.from_response(resposta.status_code, corpo)
        return resposta.json()

    # --- superfície pública ------------------------------------------------

    def evaluate(self, request: PublicEvaluationRequest) -> SuccessResponsePublicEvaluationResponse:
        """`POST /api/v1/predictive-evaluations` — avaliar e rotear.

        Modo único: avaliar e rotear. O SDK não promove, não reconfigura,
        não escolhe provedor e não executa ação externa, porque a rota
        também não faz nada disso.
        """
        corpo = request.model_dump(mode="json")
        return SuccessResponsePublicEvaluationResponse.model_validate(
            self._request("POST", _PATH_EVALUATE, authenticated=True, json_body=corpo)
        )

    def health(self) -> HealthResponse:
        """`GET /api/v1/health` — vivacidade. Pública: sem credencial."""
        return HealthResponse.model_validate(
            self._request("GET", _PATH_HEALTH, authenticated=False)
        )

    def status(self) -> StatusResponse:
        """`GET /api/v1/status` — prontidão. Pública: sem credencial."""
        return StatusResponse.model_validate(
            self._request("GET", _PATH_STATUS, authenticated=False)
        )

    def version(self) -> VersionResponse:
        """`GET /api/v1/version` — versões. Pública: sem credencial."""
        return VersionResponse.model_validate(
            self._request("GET", _PATH_VERSION, authenticated=False)
        )
