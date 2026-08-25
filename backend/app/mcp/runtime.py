"""
Runtime ASGI do boundary MCP — Streamable HTTP stateless + JSON response.

```text
MCP_RUNTIME_DEVELOPMENT = IMPLEMENTED
MCP_RUNTIME_PRODUCTION  = DISABLED
```

A aplicação é construída por chamada explícita de `criar_app()`. Não há
instância de módulo, não há import com efeito colateral e nenhum módulo
fora de `app/mcp` a referencia — a guarda `test_mcp10` mede isso.

```text
NO_MOUNT_POINT > FLAG_SET_TO_FALSE
```

Uma flag desligada é uma decisão que alguém pode ligar. A ausência de
ponto de montagem exige escrever código novo, que passa por revisão.

## Stateless por contrato

`stateless_http=True` e `json_response=True`. Stateless porque sessão
implicaria estado de cliente no servidor do boundary, e estado é
superfície: replay, fixação e vazamento entre chamadas passariam a ser
possíveis onde hoje não são.
"""

from typing import Any

from app.mcp.auth import (
    ESCOPO_EXIGIDO,
    ResourceServerAuthenticator,
    ResourceServerConfig,
    metadata_do_recurso,
)
from app.mcp.token_verifier import PiaAccessToken, PiaTokenVerifier, montar_auth_settings
from app.mcp.tools import McpToolsPort


def criar_app(
    *,
    tools: McpToolsPort,
    autenticador: ResourceServerAuthenticator,
    config: ResourceServerConfig,
) -> Any:
    """Constrói a aplicação. Nunca chamada na composição produtiva.

    A autenticação é do **middleware oficial do SDK**: `token_verifier`
    mais `AuthSettings`. Nenhuma tool recebe credencial por parâmetro.

    ```text
    AUTH_IN_TRANSPORT · NEVER_IN_THE_TOOL_SIGNATURE
    ```
    """
    from mcp.server.fastmcp import FastMCP

    verificador = PiaTokenVerifier(autenticador)

    servidor = FastMCP(
        name="pia-os",
        stateless_http=True,
        json_response=True,
        token_verifier=verificador,
        auth=montar_auth_settings(
            issuer_url=config.issuer,
            resource_server_url=config.resource_url,
            escopo=ESCOPO_EXIGIDO,
        ),
    )

    for nome in tools.nomes():
        _registrar(servidor, tools, nome)

    aplicacao = servidor.streamable_http_app()
    _montar_metadata(aplicacao, config)
    return aplicacao


def _registrar(servidor: Any, tools: McpToolsPort, nome: str) -> None:
    """Registra uma tool. A assinatura tem SOMENTE `arguments`.

    Qualquer parâmetro extra aqui vira campo do `inputSchema` publicado
    ao cliente — foi exatamente assim que a credencial vazou para o
    schema na versão anterior.
    """

    async def _executar(arguments: dict[str, Any]) -> dict[str, Any]:
        from anyio import to_thread

        principal = _principal_da_requisicao()
        # Os serviços e a sessão SQLAlchemy são síncronos. Executá-los no
        # event loop serializaria clientes MCP e transformaria uma chamada
        # lenta em indisponibilidade global do runtime.
        return await to_thread.run_sync(
            lambda: tools.chamar(nome=nome, argumentos=arguments, principal=principal)
        )

    _executar.__name__ = nome.replace(".", "_")
    servidor.tool(name=nome)(_executar)


def _principal_da_requisicao() -> Any:
    """Lê o principal do `AccessToken` desta requisição.

    O SDK guarda num `ContextVar` a instância que `verify_token`
    devolveu. Cada requisição tem a sua: nada é compartilhado e o token
    bruto não é indexado em lugar nenhum.

        PER_REQUEST_BY_CONSTRUCTION

    Ausência de principal é recusa, nunca execução anônima.

        NO_PRINCIPAL -> REFUSE · NEVER_ANONYMOUS_EXECUTION
    """
    from mcp.server.auth.middleware.auth_context import get_access_token

    from app.mcp.auth import PrincipalAutenticado

    token_de_acesso = get_access_token()
    if token_de_acesso is None:
        raise PermissionError("requisição sem contexto de autenticação")
    if not isinstance(token_de_acesso, PiaAccessToken) or not token_de_acesso.principal_ref:
        raise PermissionError("principal não resolvido para a credencial apresentada")
    return PrincipalAutenticado(
        principal_ref=token_de_acesso.principal_ref,
        scopes=frozenset(token_de_acesso.scopes),
        subject=token_de_acesso.principal_ref,
    )


def _montar_metadata(aplicacao: Any, config: ResourceServerConfig) -> None:
    """`/.well-known/oauth-protected-resource`, sem endpoint de AS."""
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    async def _metadata(_request: Any) -> Any:
        return JSONResponse(metadata_do_recurso(config))

    aplicacao.router.routes.append(
        Route("/.well-known/oauth-protected-resource", _metadata, methods=["GET"])
    )
