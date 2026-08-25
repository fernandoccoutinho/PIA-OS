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
    ErroDeAutenticacao,
    ErroDeAutorizacao,
    ErroDeTransporte,
    ResourceServerAuthenticator,
    ResourceServerConfig,
    metadata_do_recurso,
    redigir,
)
from app.mcp.tools import McpTools, ToolDesconhecidaError


def criar_app(
    *,
    tools: McpTools,
    autenticador: ResourceServerAuthenticator,
    config: ResourceServerConfig,
) -> Any:
    """Constrói a aplicação. Nunca chamada na composição produtiva."""
    from mcp.server.fastmcp import FastMCP

    servidor = FastMCP(
        name="pia-os",
        stateless_http=True,
        json_response=True,
    )

    for nome in tools.nomes():
        _registrar(servidor, tools, autenticador, nome)

    aplicacao = servidor.streamable_http_app()
    _montar_metadata(aplicacao, config)
    return aplicacao


def _registrar(
    servidor: Any,
    tools: McpTools,
    autenticador: ResourceServerAuthenticator,
    nome: str,
) -> None:
    """Registra uma tool autorizada, com autenticação obrigatória."""

    async def _executar(
        arguments: dict[str, Any], authorization: str | None = None
    ) -> dict[str, Any]:
        try:
            principal = autenticador.autenticar(headers={"Authorization": authorization or ""})
            return tools.chamar(nome=nome, argumentos=arguments, principal=principal)
        except (ErroDeAutenticacao, ErroDeAutorizacao, ErroDeTransporte) as falha:
            # A mensagem pode ter passado por texto do provider: redigir de
            # novo antes de deixar o boundary. Redação em camadas é barata;
            # um token num log é irreversível.
            raise RuntimeError(redigir(str(falha), authorization or "")) from None
        except ToolDesconhecidaError:
            raise RuntimeError("tool não autorizada") from None

    _executar.__name__ = nome.replace(".", "_")
    servidor.tool(name=nome)(_executar)


def _montar_metadata(aplicacao: Any, config: ResourceServerConfig) -> None:
    """`/.well-known/oauth-protected-resource`, sem endpoint de AS."""
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    async def _metadata(_request: Any) -> Any:
        return JSONResponse(metadata_do_recurso(config))

    aplicacao.router.routes.append(
        Route("/.well-known/oauth-protected-resource", _metadata, methods=["GET"])
    )
