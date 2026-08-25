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

## O principal validado não viaja no token

`verify_token` devolve o `AccessToken` do SDK, que não tem campo para o
nosso `principal_ref`. Guardamos a resolução num mapa efêmero indexado
pelo próprio token, consumido pela tool no mesmo ciclo de requisição.
O token nunca é persistido, nunca sai deste processo, e o mapa é limpo
ao ser lido.

```text
EPHEMERAL_BY_CONSTRUCTION · NEVER_PERSISTED
```
"""

from datetime import UTC, datetime
from typing import Any

from mcp.server.auth.provider import AccessToken, TokenVerifier

from app.mcp.auth import (
    ErroDeAutenticacao,
    ErroDeAutorizacao,
    PrincipalAutenticado,
    ResourceServerAuthenticator,
)


class PiaTokenVerifier(TokenVerifier):
    """Traduz o `TokenVerifier` do SDK para a validação já existente."""

    def __init__(self, autenticador: ResourceServerAuthenticator) -> None:
        self._autenticador = autenticador
        self._resolvidos: dict[str, PrincipalAutenticado] = {}

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
            escopos = getattr(falha, "escopos_do_token", None)
            if escopos is None:
                return None
            return AccessToken(
                token=token, client_id="pia-mcp", scopes=sorted(escopos), expires_at=None
            )
        except ErroDeAutenticacao:
            return None
        except Exception:
            # Falha inesperada nunca vira permissão.
            return None

        self._resolvidos[token] = principal
        return AccessToken(
            token=token,
            client_id="pia-mcp",
            scopes=sorted(principal.scopes),
            expires_at=None,
        )

    def consumir_principal(self, token: str) -> PrincipalAutenticado | None:
        """Lê e descarta. O token não permanece indexado após a leitura."""
        return self._resolvidos.pop(token, None)


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
