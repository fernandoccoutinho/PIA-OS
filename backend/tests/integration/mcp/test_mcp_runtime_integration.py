"""Integração MCP — cliente real do SDK sobre a aplicação ASGI.

```text
CREDENTIAL_IN_INPUT_SCHEMA = CREDENTIAL_IN_EVERY_ARGUMENT_LOG
```
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pytest

from app.mcp.auth import ESCOPO_EXIGIDO, ResourceServerAuthenticator, ResourceServerConfig
from app.mcp.runtime import criar_app
from app.mcp.tools import McpTools, ServicosCompostos

CONFIG = ResourceServerConfig(
    issuer="https://idp.local/",
    audience="pia-os-mcp",
    resource_url="https://pia.local/mcp",
)
CAMPOS_DE_CREDENCIAL = ("authorization", "token", "access_token", "bearer", "secret")


@pytest.fixture(scope="module")
def chave() -> dict[str, Any]:
    from cryptography.hazmat.primitives.asymmetric import rsa

    privada = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return {"privada": privada, "publica": privada.public_key(), "kid": "kid-int-1"}


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
        if control_principal_ref != "principal-1":
            raise PermissionError("Schedule inexistente sob este principal de controle")
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
    def consumir(self, **_: Any) -> bool:
        return True


def _app(chave: dict[str, Any], schedules: _Schedules | None = None) -> Any:
    tools = McpTools(
        ServicosCompostos(
            schedules=schedules if schedules is not None else _Schedules(),
            consultas=_Consultas(),
            handoff_supervisionado=None,
            retorno=None,
        )
    )
    autenticador = ResourceServerAuthenticator(
        config=CONFIG, jwks=_Jwks(chave), resolver=_Resolver(), quota=_Quota()
    )
    return criar_app(tools=tools, autenticador=autenticador, config=CONFIG)


# --- 5. prova mecânica: credencial fora do schema ---------------------------


@pytest.mark.anyio
async def test_int01_nenhuma_tool_publica_credencial_no_input_schema(
    chave: dict[str, Any],
) -> None:
    """A prova que fecha o M0: o SDK não anuncia credencial nenhuma."""
    from mcp.server.fastmcp import FastMCP

    from app.mcp.token_verifier import PiaTokenVerifier, montar_auth_settings

    tools = McpTools(
        ServicosCompostos(
            schedules=_Schedules(),
            consultas=_Consultas(),
            handoff_supervisionado=None,
            retorno=None,
        )
    )
    autenticador = ResourceServerAuthenticator(
        config=CONFIG, jwks=_Jwks(chave), resolver=_Resolver(), quota=_Quota()
    )
    servidor = FastMCP(
        name="pia-os",
        stateless_http=True,
        json_response=True,
        token_verifier=PiaTokenVerifier(autenticador),
        auth=montar_auth_settings(
            issuer_url=CONFIG.issuer,
            resource_server_url=CONFIG.resource_url,
            escopo=ESCOPO_EXIGIDO,
        ),
    )
    from app.mcp.runtime import _registrar

    for nome in tools.nomes():
        _registrar(servidor, tools, nome)

    listadas = await servidor.list_tools()
    assert len(listadas) == 5
    assert {t.name for t in listadas} == set(tools.nomes())

    for ferramenta in listadas:
        propriedades = (ferramenta.inputSchema or {}).get("properties", {})
        texto = str(ferramenta.inputSchema).lower()
        for proibido in CAMPOS_DE_CREDENCIAL:
            assert proibido not in propriedades, f"{ferramenta.name} publica {proibido}"
            assert proibido not in texto, f"{ferramenta.name} menciona {proibido}"


def test_int02_assinatura_das_tools_nao_tem_parametro_de_credencial() -> None:
    """Estática: a regressão volta pela assinatura, então guarda-se a assinatura."""
    import inspect

    from app.mcp import runtime

    fonte = inspect.getsource(runtime._registrar)
    assert "authorization" not in fonte.lower()
    assert "async def _executar(arguments: dict[str, Any]) -> dict[str, Any]:" in fonte


def test_int03_runtime_usa_middleware_oauth_do_sdk() -> None:
    """Stop Condition: runtime sem middleware OAuth do SDK."""
    import inspect

    from app.mcp import runtime

    fonte = inspect.getsource(runtime.criar_app)
    assert "token_verifier=" in fonte
    assert "auth=montar_auth_settings(" in fonte
    assert "stateless_http=True" in fonte
    assert "json_response=True" in fonte


def test_int04_token_verifier_e_o_oficial_do_sdk() -> None:
    """Conformidade ESTRUTURAL — `TokenVerifier` é Protocol não-runtime.

    Herdar não bastaria como prova nem seria exigível: o que o SDK
    consome é a forma de `verify_token`. Provamos a forma.
    """
    import inspect

    from mcp.server.auth.provider import TokenVerifier

    from app.mcp.token_verifier import PiaTokenVerifier

    assert TokenVerifier in PiaTokenVerifier.__mro__
    nosso = inspect.signature(PiaTokenVerifier.verify_token)
    oficial = inspect.signature(TokenVerifier.verify_token)
    assert list(nosso.parameters) == list(oficial.parameters)
    assert inspect.iscoroutinefunction(PiaTokenVerifier.verify_token)


@pytest.mark.anyio
async def test_int05_token_invalido_nao_resolve_principal(chave: dict[str, Any]) -> None:
    from app.mcp.token_verifier import PiaTokenVerifier

    autenticador = ResourceServerAuthenticator(
        config=CONFIG, jwks=_Jwks(chave), resolver=_Resolver(), quota=_Quota()
    )
    verificador = PiaTokenVerifier(autenticador)
    assert await verificador.verify_token("nao-e-um-token") is None


@pytest.mark.anyio
async def test_int06_escopo_insuficiente_nao_colapsa_em_401(chave: dict[str, Any]) -> None:
    """`VALID_BUT_INSUFFICIENT != INVALID` — o SDK precisa poder dar 403."""
    from app.mcp.token_verifier import PiaTokenVerifier

    autenticador = ResourceServerAuthenticator(
        config=CONFIG, jwks=_Jwks(chave), resolver=_Resolver(), quota=_Quota()
    )
    verificador = PiaTokenVerifier(autenticador)
    concedido = await verificador.verify_token(_emitir(chave, scope="outro:escopo"))
    assert concedido is not None
    assert ESCOPO_EXIGIDO not in concedido.scopes


@pytest.mark.anyio
async def test_int07_principal_viaja_no_access_token_tipado(chave: dict[str, Any]) -> None:
    """`PER_REQUEST_BY_CONSTRUCTION` — sem mapa, sem retencao."""
    from app.mcp.token_verifier import PiaAccessToken, PiaTokenVerifier

    autenticador = ResourceServerAuthenticator(
        config=CONFIG, jwks=_Jwks(chave), resolver=_Resolver(), quota=_Quota()
    )
    verificador = PiaTokenVerifier(autenticador)
    concedido = await verificador.verify_token(_emitir(chave))
    assert isinstance(concedido, PiaAccessToken)
    assert concedido.principal_ref == "principal-1"
    assert vars(verificador).get("_resolvidos") is None


@pytest.mark.anyio
async def test_int08_principal_alheio_nao_enxerga_recurso(chave: dict[str, Any]) -> None:
    from app.mcp.auth import PrincipalAutenticado
    from app.mcp.token_verifier import PiaTokenVerifier

    schedules = _Schedules()
    tools = McpTools(
        ServicosCompostos(
            schedules=schedules,
            consultas=_Consultas(),
            handoff_supervisionado=None,
            retorno=None,
        )
    )
    autenticador = ResourceServerAuthenticator(
        config=CONFIG, jwks=_Jwks(chave), resolver=_Resolver(), quota=_Quota()
    )
    concedido = await PiaTokenVerifier(autenticador).verify_token(_emitir(chave, sub="sub-2"))
    assert concedido is not None
    principal = PrincipalAutenticado(
        principal_ref=concedido.principal_ref,
        scopes=frozenset(concedido.scopes),
        subject="sub-2",
    )
    with pytest.raises(PermissionError):
        tools.chamar(
            nome="schedule.read",
            argumentos={"schedule_id": str(uuid.uuid4())},
            principal=principal,
        )
    assert schedules.principais == ["principal-2"]


def test_int09_metadata_e_servida_sem_endpoint_de_as(chave: dict[str, Any]) -> None:
    aplicacao = _app(chave)
    caminhos = [getattr(rota, "path", None) for rota in aplicacao.router.routes]
    assert "/.well-known/oauth-protected-resource" in caminhos


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
