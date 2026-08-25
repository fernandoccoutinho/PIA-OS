"""Cliente MCP real sobre o ASGI, concorrência e cota.

```text
PER_REQUEST_BY_CONSTRUCTION · NOTHING_SHARED · NOTHING_RETAINED
QUOTA_EXHAUSTED != INVALID_TOKEN
```
"""

import asyncio
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest

from app.mcp.auth import ESCOPO_EXIGIDO, ResourceServerAuthenticator, ResourceServerConfig
from app.mcp.runtime import criar_app
from app.mcp.token_verifier import PiaAccessToken, PiaTokenVerifier
from app.mcp.tools import McpTools, ServicosCompostos

CONFIG = ResourceServerConfig(
    issuer="https://idp.local/", audience="pia-os-mcp", resource_url="https://pia.local/mcp"
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture(scope="module")
def chave() -> dict[str, Any]:
    from cryptography.hazmat.primitives.asymmetric import rsa

    privada = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return {"privada": privada, "publica": privada.public_key(), "kid": "kid-cli-1"}


def _emitir(chave: dict[str, Any], *, scope: str = ESCOPO_EXIGIDO, sub: str = "sub-1") -> str:
    import jwt

    agora = int(datetime.now(UTC).timestamp())
    return jwt.encode(
        {
            "iss": CONFIG.issuer,
            "aud": CONFIG.audience,
            "sub": sub,
            "iat": agora,
            "exp": agora + 300,
            "scope": scope,
        },
        chave["privada"],
        algorithm="RS256",
        headers={"kid": chave["kid"]},
    )


@dataclass
class _Vista:
    schedule_id: uuid.UUID
    state: str = "active"


class _Schedules:
    def __init__(self) -> None:
        self.principais: list[str] = []

    def get_schedule(self, *, control_principal_ref: str, schedule_id: uuid.UUID) -> _Vista:
        self.principais.append(control_principal_ref)
        return _Vista(schedule_id=schedule_id)


class _Consultas:
    def list_attempts(self, **_: Any) -> tuple:
        return ()

    def read_governance(self, *, control_principal_ref: str, schedule_id: uuid.UUID) -> Any:
        @dataclass
        class _G:
            schedule_id: uuid.UUID
            schedule_state: str = "active"
            delegations: tuple = ()
            events: tuple = ()

        return _G(schedule_id=schedule_id)


class _Jwks:
    def __init__(self, chave: dict[str, Any]) -> None:
        self._c = chave

    def chave_para(self, *, kid: str, alg: str) -> Any:
        if kid != self._c["kid"]:
            raise LookupError("kid desconhecido")
        return self._c["publica"]


class _Resolver:
    def resolver(self, *, subject: str) -> str | None:
        return {"sub-1": "principal-1", "sub-2": "principal-2"}.get(subject)


class _Quota:
    def __init__(self, restante: int = 100) -> None:
        self.restante = restante
        self.consumos = 0

    def consumir(self, **_: Any) -> bool:
        self.consumos += 1
        if self.restante <= 0:
            return False
        self.restante -= 1
        return True


def _verificador(chave: dict[str, Any], quota: _Quota | None = None) -> PiaTokenVerifier:
    return PiaTokenVerifier(
        ResourceServerAuthenticator(
            config=CONFIG,
            jwks=_Jwks(chave),
            resolver=_Resolver(),
            quota=quota if quota is not None else _Quota(),
        )
    )


# --- 1. o mapa não existe mais ----------------------------------------------


def test_cli01_verificador_nao_retem_token_nem_principal(chave: dict[str, Any]) -> None:
    """`INDEXED_BY_RAW_TOKEN` eliminado — o verificador não tem estado."""
    verificador = _verificador(chave)
    atributos = {
        nome: valor
        for nome, valor in vars(verificador).items()
        if isinstance(valor, dict | list | set)
    }
    assert atributos == {}, f"verificador reteve estado: {atributos}"

    import inspect

    from app.mcp import token_verifier

    fonte = inspect.getsource(token_verifier)
    assert "_resolvidos" not in fonte
    assert "consumir_principal" not in fonte


# --- 3. concorrência com o MESMO token --------------------------------------


@pytest.mark.anyio
async def test_cli02_mesmo_token_em_paralelo_resolve_o_mesmo_principal(
    chave: dict[str, Any],
) -> None:
    """`POP_ON_READ` matava uma das duas. Agora ambas concluem."""
    verificador = _verificador(chave)
    token = _emitir(chave)

    resultados = await asyncio.gather(*[verificador.verify_token(token) for _ in range(8)])

    assert all(r is not None for r in resultados)
    assert all(isinstance(r, PiaAccessToken) for r in resultados)
    assert {r.principal_ref for r in resultados} == {"principal-1"}
    assert all(ESCOPO_EXIGIDO in r.scopes for r in resultados)


@pytest.mark.anyio
async def test_cli03_tokens_diferentes_em_paralelo_nao_interferem(
    chave: dict[str, Any],
) -> None:
    verificador = _verificador(chave)
    a, b = _emitir(chave, sub="sub-1"), _emitir(chave, sub="sub-2")
    pares = await asyncio.gather(*[verificador.verify_token(t) for t in (a, b, a, b, a, b)])
    assert [p.principal_ref for p in pares] == [
        "principal-1",
        "principal-2",
        "principal-1",
        "principal-2",
        "principal-1",
        "principal-2",
    ]


# --- 4. cota esgotada não é 401 ---------------------------------------------


@pytest.mark.anyio
async def test_cli04_cota_esgotada_nao_vira_invalid_token(chave: dict[str, Any]) -> None:
    """`QUOTA_EXHAUSTED != INVALID_TOKEN` — 403, não 401."""
    verificador = _verificador(chave, quota=_Quota(restante=0))
    concedido = await verificador.verify_token(_emitir(chave))
    assert concedido is not None, "cota esgotada não pode virar 401"
    assert isinstance(concedido, PiaAccessToken)
    assert concedido.quota_exhausted is True
    assert ESCOPO_EXIGIDO not in concedido.scopes
    assert concedido.principal_ref == ""


@pytest.mark.anyio
async def test_cli05_uma_chamada_consome_uma_unica_unidade(chave: dict[str, Any]) -> None:
    """`ONE_CALL = ONE_QUOTA_UNIT` — a tool não revalida nem reconsome."""
    quota = _Quota(restante=10)
    verificador = _verificador(chave, quota=quota)
    await verificador.verify_token(_emitir(chave))
    assert quota.consumos == 1
    assert quota.restante == 9


# --- 5. cliente MCP real: initialize -> tools/list -> tools/call -------------


def _app(
    chave: dict[str, Any], *, quota: _Quota | None = None, schedules: _Schedules | None = None
) -> Any:
    tools = McpTools(
        ServicosCompostos(
            schedules=schedules if schedules is not None else _Schedules(),
            consultas=_Consultas(),
            handoff_supervisionado=None,
            retorno=None,
        )
    )
    autenticador = ResourceServerAuthenticator(
        config=CONFIG,
        jwks=_Jwks(chave),
        resolver=_Resolver(),
        quota=quota if quota is not None else _Quota(),
    )
    return criar_app(tools=tools, autenticador=autenticador, config=CONFIG)


async def _sessao(aplicacao: Any, token: str | None):  # type: ignore[no-untyped-def]
    """Cliente REAL do SDK sobre o ASGI, via transporte ASGI do httpx."""
    import httpx
    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamablehttp_client

    cabecalhos = {"Authorization": f"Bearer {token}"} if token else {}

    def _fabrica(**kwargs: Any) -> httpx.AsyncClient:
        kwargs["transport"] = httpx.ASGITransport(app=aplicacao)
        kwargs.setdefault("base_url", "http://pia.local")
        kwargs.pop("verify", None)
        return httpx.AsyncClient(**kwargs)

    return (
        streamablehttp_client(
            "http://pia.local/mcp",
            headers=cabecalhos,
            httpx_client_factory=_fabrica,
        ),
        ClientSession,
    )


@pytest.mark.anyio
async def test_cli06_cliente_real_faz_initialize_list_e_call(chave: dict[str, Any]) -> None:
    """`initialize -> tools/list -> tools/call` pelo cliente do SDK.

    O `streamable_http_app` do SDK inicializa o gerenciador de sessao no
    LIFESPAN. Sem entrar nele, o manager recusa qualquer requisicao — e
    testar por fora dele testaria uma aplicacao que nunca subiu.
    """
    from mcp.client.session import ClientSession

    aplicacao = _app(chave)
    contexto, _ = await _sessao(aplicacao, _emitir(chave))

    async with (
        aplicacao.router.lifespan_context(aplicacao),
        contexto as (
            leitura,
            escrita,
            _,
        ),
    ):
        sessao = ClientSession(leitura, escrita)
        async with sessao:
            await sessao.initialize()

            listadas = await sessao.list_tools()
            assert len(listadas.tools) == 5
            assert {t.name for t in listadas.tools} == {
                "schedule.read",
                "handoff.export",
                "return.import",
                "attempts.list",
                "governance.read",
            }
            for ferramenta in listadas.tools:
                texto = str(ferramenta.inputSchema).lower()
                for proibido in ("authorization", "token", "access_token", "bearer"):
                    assert proibido not in texto

            resposta = await sessao.call_tool(
                "schedule.read", {"arguments": {"schedule_id": str(uuid.uuid4())}}
            )
            assert resposta.isError is False


@pytest.mark.anyio
async def test_cli07_chamada_sem_token_nao_alcanca_a_tool(chave: dict[str, Any]) -> None:
    import httpx

    schedules = _Schedules()
    aplicacao = _app(chave, schedules=schedules)
    transporte = httpx.ASGITransport(app=aplicacao)
    async with httpx.AsyncClient(transport=transporte, base_url="http://pia.local") as c:
        resposta = await c.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            headers={"Accept": "application/json, text/event-stream"},
        )
    assert resposta.status_code == 401
    assert "WWW-Authenticate" in resposta.headers
    assert schedules.principais == []


@pytest.mark.anyio
async def test_cli08_token_invalido_e_401(chave: dict[str, Any]) -> None:
    import httpx

    aplicacao = _app(chave)
    transporte = httpx.ASGITransport(app=aplicacao)
    async with httpx.AsyncClient(transport=transporte, base_url="http://pia.local") as c:
        resposta = await c.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            headers={
                "Authorization": "Bearer nao-e-um-token",
                "Accept": "application/json, text/event-stream",
            },
        )
    assert resposta.status_code == 401


@pytest.mark.anyio
async def test_cli09_token_na_query_nao_autentica(chave: dict[str, Any]) -> None:
    """Query string vaza em log, proxy e referer — nunca autentica."""
    import httpx

    aplicacao = _app(chave)
    transporte = httpx.ASGITransport(app=aplicacao)
    async with httpx.AsyncClient(transport=transporte, base_url="http://pia.local") as c:
        resposta = await c.post(
            f"/mcp?access_token={_emitir(chave)}",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            headers={"Accept": "application/json, text/event-stream"},
        )
    assert resposta.status_code == 401


@pytest.mark.anyio
async def test_cli10_escopo_insuficiente_e_403(chave: dict[str, Any]) -> None:
    import httpx

    aplicacao = _app(chave)
    transporte = httpx.ASGITransport(app=aplicacao)
    async with httpx.AsyncClient(transport=transporte, base_url="http://pia.local") as c:
        resposta = await c.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            headers={
                "Authorization": f"Bearer {_emitir(chave, scope='outro:escopo')}",
                "Accept": "application/json, text/event-stream",
            },
        )
    assert resposta.status_code == 403
    assert "WWW-Authenticate" in resposta.headers


@pytest.mark.anyio
async def test_cli11_cota_esgotada_e_403_nao_401(chave: dict[str, Any]) -> None:
    import httpx

    aplicacao = _app(chave, quota=_Quota(restante=0))
    transporte = httpx.ASGITransport(app=aplicacao)
    async with httpx.AsyncClient(transport=transporte, base_url="http://pia.local") as c:
        resposta = await c.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"},
            headers={
                "Authorization": f"Bearer {_emitir(chave)}",
                "Accept": "application/json, text/event-stream",
            },
        )
    assert resposta.status_code == 403, "cota esgotada nunca é 401"
