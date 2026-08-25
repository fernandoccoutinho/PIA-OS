"""
Autenticação do boundary MCP: **somente** OAuth Resource Server.

```text
AUTHORIZATION_SERVER = EXTERNAL_AND_PROVIDER_NEUTRAL
PIA_INTERNAL_AS      = FORBIDDEN
TOKEN_PASSTHROUGH    = FORBIDDEN
TOKEN_IN_QUERY       = FORBIDDEN
```

O PIA valida token que outro emitiu e nunca emite, nunca guarda e nunca
repassa. PKCE, consentimento, registro de cliente e emissão pertencem ao
IdP externo.

## Por que o token nunca sai daqui

Um token repassado adiante vira credencial ambiente: qualquer serviço a
jusante passa a agir com a autoridade do chamador, e o rastro de quem
autorizou o quê some. O token entra, é validado, produz um principal, e
morre nesta camada.

```text
FORWARDED_TOKEN = AMBIENT_AUTHORITY
AMBIENT_AUTHORITY = AUTHORITY_WITHOUT_A_TRAIL
```

## Por que nunca em query string

Query string vaza em log de servidor, histórico de proxy, referer e
tracing — lugares que ninguém trata como cofre. Bearer só no header
`Authorization`.

## Recusas explícitas

Algoritmo inesperado e `kid` desconhecido são recusados **antes** de
qualquer verificação de assinatura. Aceitar o algoritmo que o próprio
token declara é o defeito clássico: um token forjado com `alg: none` ou
com algoritmo simétrico sobre a chave pública se autoverifica.

```text
ALGORITHM_FROM_THE_TOKEN = THE_ATTACKER_CHOOSES_THE_LOCK
```
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Final, Protocol

ALGORITMOS_ACEITOS: Final[frozenset[str]] = frozenset({"RS256", "ES256"})
"""Enumerado. Nunca lido do cabeçalho do token."""

ESCOPO_EXIGIDO: Final = "orchestration:operate"
COTA: Final = "orchestration_api"
HEADER: Final = "Authorization"
PREFIXO: Final = "Bearer "

TOKEN_REDACTED: Final = "[REDACTED_BEARER]"
"""O que aparece em log, erro, tracing e pacote. Sempre isto, nunca o token."""


class ErroDeAutenticacao(Exception):
    """401 — sem token, malformado, assinatura inválida, expirado, futuro."""

    status_code = 401

    def __init__(self, motivo: str) -> None:
        super().__init__(motivo)
        self.motivo = motivo

    @property
    def www_authenticate(self) -> str:
        return f'Bearer realm="pia-os", error="invalid_token", error_description="{self.motivo}"'


class ErroDeAutorizacao(Exception):
    """403 — token válido, autoridade insuficiente."""

    status_code = 403

    def __init__(
        self,
        motivo: str,
        *,
        escopo: str = ESCOPO_EXIGIDO,
        escopos_do_token: frozenset[str] | None = None,
    ) -> None:
        super().__init__(motivo)
        self.motivo = motivo
        self.escopo = escopo
        # Escopos REAIS do token, quando ele e valido e apenas
        # insuficiente. Permite ao adapter do SDK produzir 403 em vez de
        # colapsar em 401:
        #
        #     VALID_BUT_INSUFFICIENT != INVALID
        self.escopos_do_token = escopos_do_token

    @property
    def www_authenticate(self) -> str:
        return (
            f'Bearer realm="pia-os", error="insufficient_scope", '
            f'scope="{self.escopo}", error_description="{self.motivo}"'
        )


class ErroDeTransporte(Exception):
    """400 — transporte malformado, antes de qualquer questão de autoridade."""

    status_code = 400


@dataclass(frozen=True)
class ResourceServerConfig:
    """Configuração do RS. Issuer e audiência **próprios**, nunca inferidos."""

    issuer: str
    audience: str
    resource_url: str

    def __post_init__(self) -> None:
        for nome in ("issuer", "audience", "resource_url"):
            valor = getattr(self, nome)
            if not isinstance(valor, str) or not valor.strip():
                raise ValueError(f"{nome} é obrigatório no Resource Server")


@dataclass(frozen=True)
class PrincipalAutenticado:
    """O que sobra do token depois da validação. Sem o token."""

    principal_ref: str
    scopes: frozenset[str]
    subject: str

    def __post_init__(self) -> None:
        if not self.principal_ref.strip():
            raise ValueError("principal_ref é obrigatório")


class JwksPort(Protocol):
    """Resolve `kid` em chave pública. Fixture local em teste, IdP em produção."""

    def chave_para(self, *, kid: str, alg: str) -> Any:
        """Levantar exceção quando o `kid` é desconhecido."""
        ...


class PrincipalResolverPort(Protocol):
    """Resolve `sub` validado em principal programático **existente**."""

    def resolver(self, *, subject: str) -> str | None:
        """`None` quando não há principal — que é recusa, não criação."""
        ...


class QuotaPort(Protocol):
    """Cota `orchestration_api` já existente."""

    def consumir(self, *, principal_ref: str, quota: str) -> bool:
        """`False` quando esgotada."""
        ...


def metadata_do_recurso(config: ResourceServerConfig) -> dict[str, Any]:
    """Corpo de `/.well-known/oauth-protected-resource`.

    Declara quem emite e o que o recurso exige. Não declara endpoint de
    autorização, token ou registro: eles não existem aqui, e anunciá-los
    convidaria cliente a tratar o PIA como AS.
    """
    return {
        "resource": config.resource_url,
        "authorization_servers": [config.issuer],
        "scopes_supported": [ESCOPO_EXIGIDO],
        "bearer_methods_supported": ["header"],
    }


def extrair_bearer(headers: dict[str, str], query: dict[str, str] | None = None) -> str:
    """Bearer do header, e recusa ruidosa se vier na query."""
    if query:
        for chave in ("access_token", "token", "bearer"):
            if chave in query:
                raise ErroDeAutenticacao(
                    "token em query string é recusado — vaza em log, proxy e tracing"
                )

    bruto = None
    for nome, valor in headers.items():
        if nome.lower() == HEADER.lower():
            bruto = valor
            break

    if bruto is None:
        raise ErroDeAutenticacao("credencial ausente")
    if not bruto.startswith(PREFIXO):
        raise ErroDeAutenticacao("esquema de autorização não suportado")
    token = bruto[len(PREFIXO) :].strip()
    if not token:
        raise ErroDeAutenticacao("credencial ausente")
    return token


def redigir(texto: str, token: str) -> str:
    """Remove o token de qualquer texto que possa ser persistido."""
    if not token:
        return texto
    return texto.replace(token, TOKEN_REDACTED)


class ResourceServerAuthenticator:
    """Valida o Bearer e devolve principal. Nunca guarda nem repassa o token."""

    def __init__(
        self,
        *,
        config: ResourceServerConfig,
        jwks: JwksPort,
        resolver: PrincipalResolverPort,
        quota: QuotaPort,
        decoder: Any = None,
    ) -> None:
        self._config = config
        self._jwks = jwks
        self._resolver = resolver
        self._quota = quota
        self._decoder = decoder

    def autenticar(
        self,
        *,
        headers: dict[str, str],
        query: dict[str, str] | None = None,
        moment: datetime | None = None,
    ) -> PrincipalAutenticado:
        """Do header ao principal, ou recusa tipada.

        Relógio lido uma vez, injetável — duas leituras num mesmo fluxo
        envelhecem entre si.
        """
        token = extrair_bearer(headers, query)
        agora = moment if moment is not None else datetime.now(UTC)
        if agora.tzinfo is None:
            raise ErroDeTransporte("instante sem fuso")

        cabecalho = self._cabecalho(token)
        alg = cabecalho.get("alg")
        if alg not in ALGORITMOS_ACEITOS:
            raise ErroDeAutenticacao("algoritmo não aceito")
        kid = cabecalho.get("kid")
        if not isinstance(kid, str) or not kid:
            raise ErroDeAutenticacao("kid ausente")

        try:
            chave = self._jwks.chave_para(kid=kid, alg=alg)
        except Exception as falha:
            raise ErroDeAutenticacao("kid desconhecido") from falha

        reivindicacoes = self._verificar(token=token, chave=chave, alg=alg)

        if reivindicacoes.get("iss") != self._config.issuer:
            raise ErroDeAutenticacao("issuer não confere")

        audiencia = reivindicacoes.get("aud")
        audiencias = {audiencia} if isinstance(audiencia, str) else set(audiencia or [])
        if self._config.audience not in audiencias:
            raise ErroDeAutenticacao("audiência não confere")

        self._validar_janela(reivindicacoes, agora)

        subject = reivindicacoes.get("sub")
        if not isinstance(subject, str) or not subject.strip():
            raise ErroDeAutenticacao("sub ausente")

        principal_ref = self._resolver.resolver(subject=subject)
        if not principal_ref:
            raise ErroDeAutorizacao("sub não corresponde a principal programático existente")

        escopos = self._escopos(reivindicacoes)
        if ESCOPO_EXIGIDO not in escopos:
            raise ErroDeAutorizacao("escopo insuficiente", escopos_do_token=frozenset(escopos))

        if not self._quota.consumir(principal_ref=principal_ref, quota=COTA):
            raise ErroDeAutorizacao("cota esgotada", escopo=ESCOPO_EXIGIDO)

        return PrincipalAutenticado(
            principal_ref=principal_ref, scopes=frozenset(escopos), subject=subject
        )

    def _cabecalho(self, token: str) -> dict[str, Any]:
        import jwt

        try:
            cabecalho = jwt.get_unverified_header(token)
        except Exception as falha:
            raise ErroDeAutenticacao("token malformado") from falha
        if not isinstance(cabecalho, dict):
            raise ErroDeAutenticacao("cabeçalho do token malformado")
        return cabecalho

    def _verificar(self, *, token: str, chave: Any, alg: str) -> dict[str, Any]:
        import jwt

        try:
            reivindicacoes = jwt.decode(
                token,
                chave,
                algorithms=[alg],
                audience=self._config.audience,
                issuer=self._config.issuer,
                options={
                    "require": ["exp", "iat", "sub", "aud", "iss"],
                    # A janela e validada por _validar_janela com o instante
                    # INJETADO. Deixar o PyJWT ler o proprio relogio criaria
                    # um segundo relogio no mesmo fluxo, e dois relogios
                    # envelhecem entre si:
                    #
                    #     MULTIPLE_CLOCK_READS = FLAKY_BY_CONSTRUCTION
                    "verify_exp": False,
                    "verify_nbf": False,
                },
            )
        except Exception as falha:
            # A mensagem do provider pode conter o token; redigir antes de
            # deixar qualquer coisa escapar para log ou resposta.
            raise ErroDeAutenticacao(redigir(f"token inválido: {falha}", token)) from falha
        if not isinstance(reivindicacoes, dict):
            raise ErroDeAutenticacao("reivindicações malformadas")
        return reivindicacoes

    @staticmethod
    def _validar_janela(reivindicacoes: dict[str, Any], agora: datetime) -> None:
        """Expiração e not-before, ambos obrigatórios quando presentes."""
        instante = agora.timestamp()
        exp = reivindicacoes.get("exp")
        if exp is None or not isinstance(exp, int | float) or instante >= float(exp):
            raise ErroDeAutenticacao("token expirado")
        nbf = reivindicacoes.get("nbf")
        if nbf is not None and (not isinstance(nbf, int | float) or instante < float(nbf)):
            raise ErroDeAutenticacao("token ainda não é válido")
        iat = reivindicacoes.get("iat")
        if iat is not None and isinstance(iat, int | float) and instante < float(iat):
            raise ErroDeAutenticacao("token emitido no futuro")

    @staticmethod
    def _escopos(reivindicacoes: dict[str, Any]) -> set[str]:
        bruto = reivindicacoes.get("scope") or reivindicacoes.get("scp") or ""
        if isinstance(bruto, str):
            return set(bruto.split())
        if isinstance(bruto, list):
            return {item for item in bruto if isinstance(item, str)}
        return set()
