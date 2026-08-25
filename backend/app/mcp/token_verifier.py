"""
Adapter do `TokenVerifier` oficial do SDK MCP.

```text
AUTH_BELONGS_TO_THE_TRANSPORT · NOT_TO_THE_TOOL_SIGNATURE
```

O defeito que este módulo corrige era material: com `authorization` na
assinatura da tool, o SDK o publicava como campo do `inputSchema`. Isso
transformava a credencial em **parâmetro de entrada anunciado ao
cliente** — visível na descoberta de ferramentas, aceitável no corpo da
chamada, e a um passo de aparecer em log de argumentos.

```text
CREDENTIAL_IN_INPUT_SCHEMA = CREDENTIAL_IN_EVERY_ARGUMENT_LOG
```

Autenticação pertence ao transporte. O SDK lê o Bearer do header HTTP,
chama `verify_token`, e devolve 401/403 com `WWW-Authenticate` pelo seu
próprio middleware — nada disso vira exceção interna da tool.

## O que este adapter faz e não faz

Ele **não** reimplementa validação. Toda a verificação de issuer,
audiência, JWKS, `kid`, algoritmo, janela, `sub`, principal, escopo e
cota continua em `ResourceServerAuthenticator`. O adapter só traduz
entre a interface do SDK e a nossa.

    verify_token(token) -> AccessToken | None

`None` é a resposta que o SDK converte em 401. Escopo insuficiente é
diferente: devolvemos `AccessToken` com os escopos reais e deixamos o
SDK comparar contra `required_scopes` — assim o 403 e o
`WWW-Authenticate` de escopo saem do middleware oficial, com o formato
que o cliente MCP espera.

```text
401_AND_403_COME_FROM_THE_SDK · NOT_FROM_US
```

## O principal viaja no token tipado, nunca num mapa

`PiaAccessToken` e subclasse de `AccessToken` com o `principal_ref` ja
resolvido. O SDK guarda a instancia devolvida por `verify_token` num
`ContextVar`, e `get_access_token()` a recupera dentro da MESMA
requisicao.

Isso substitui um mapa `{token: principal}` defeituoso em tres frentes:

```text
GLOBAL_MUTABLE_MAP   -> estado compartilhado entre requisicoes
INDEXED_BY_RAW_TOKEN -> credencial retida na memoria do processo
POP_ON_READ          -> duas chamadas com o MESMO token competem;
                        uma vence, a outra recebe None
```

A terceira era a pior: falha intermitente sob exatamente a carga que um
servidor MCP recebe.

```text
PER_REQUEST_BY_CONSTRUCTION · NOTHING_SHARED · NOTHING_RETAINED
```

## Cota esgotada nao e token invalido

Cota limita o uso de credencial VALIDA. Colapsa-la em `None` faria o SDK
responder 401 `invalid_token`, e o cliente tentaria reautenticar contra
um limite que reautenticar nao resolve.

```text
QUOTA_EXHAUSTED != INVALID_TOKEN
ONE_CALL = ONE_QUOTA_UNIT
```

A cota e consumida UMA vez, na verificacao, e o resultado viaja no token
tipado: revalidar na tool queimaria duas unidades por chamada.
"""

from datetime import UTC, datetime
from typing import Any

from mcp.server.auth.provider import AccessToken, TokenVerifier

from app.mcp.auth import (
    ErroDeAutenticacao,
    ErroDeAutorizacao,
    ResourceServerAuthenticator,
)


class PiaAccessToken(AccessToken):
    """`AccessToken` do SDK com o principal ja resolvido."""

    principal_ref: str = ""
    quota_exhausted: bool = False
    """Cota ja avaliada e consumida na verificacao. Nunca reavaliar."""


class PiaTokenVerifier(TokenVerifier):
    """Traduz o `TokenVerifier` do SDK para a validação já existente.

    SEM ESTADO. Nenhum atributo guarda token ou principal: seguro para
    uso concorrente por construção.
    """

    def __init__(self, autenticador: ResourceServerAuthenticator) -> None:
        self._autenticador = autenticador

    async def verify_token(self, token: str) -> AccessToken | None:
        """`None` quando o token não vale — o SDK devolve 401.

        Escopo insuficiente **não** vira `None`: devolvemos o token com
        os escopos que ele realmente tem, e o SDK produz o 403 com
        `WWW-Authenticate` de escopo. Colapsar os dois em 401 diria ao
        cliente "sua credencial é inválida" quando ela é válida e apenas
        insuficiente — e ele tentaria reautenticar em vez de pedir
        escopo.
        """
        try:
            principal = self._autenticador.autenticar(headers={"Authorization": f"Bearer {token}"})
        except ErroDeAutorizacao as falha:
            return self._insuficiente(token, falha)
        except ErroDeAutenticacao:
            return None
        except Exception:
            # Falha inesperada nunca vira permissao.
            return None

        return PiaAccessToken(
            token=token,
            client_id="pia-mcp",
            scopes=sorted(principal.scopes),
            expires_at=None,
            principal_ref=principal.principal_ref,
        )

    @staticmethod
    def _insuficiente(token: str, falha: ErroDeAutorizacao) -> AccessToken | None:
        """Token valido, autoridade insuficiente -> 403, nunca 401.

        Escopo insuficiente devolve os escopos REAIS. Cota esgotada
        devolve escopos vazios: o token e valido, mas nesta requisicao
        nao carrega autoridade utilizavel.
        """
        escopos = getattr(falha, "escopos_do_token", None)
        cota_esgotada = "cota" in falha.motivo.lower()
        if escopos is None and not cota_esgotada:
            # Sub sem principal existente: nao ha autoridade a reportar.
            return None
        return PiaAccessToken(
            token=token,
            client_id="pia-mcp",
            scopes=sorted(escopos) if escopos else [],
            expires_at=None,
            principal_ref="",
            quota_exhausted=cota_esgotada,
        )


def agora_utc() -> datetime:
    return datetime.now(UTC)


def montar_auth_settings(*, issuer_url: str, resource_server_url: str, escopo: str) -> Any:
    """`AuthSettings` do SDK, com escopo exigido e URLs próprias."""
    from mcp.server.auth.settings import AuthSettings
    from pydantic import AnyHttpUrl

    return AuthSettings(
        issuer_url=AnyHttpUrl(issuer_url),
        resource_server_url=AnyHttpUrl(resource_server_url),
        required_scopes=[escopo],
    )
