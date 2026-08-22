"""
Verificador programático `E6.2` — recusa uniforme e fail-closed.

```text
MISSING == MALFORMED == UNKNOWN == WRONG == REVOKED == EXPIRED -> 401
VERIFIER_UNAVAILABLE -> DENY
SECRET_NEVER_IN_ERROR_OR_LOG
```

Sem banco: o repositório é substituído por duplos que devolvem exatamente
o que cada condição exige. As provas com PostgreSQL real estão em
`tests/integration/security/test_programmatic_access_integration.py`.
"""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from app.exceptions.api import AuthenticationException, InsufficientScopeException
from app.models.programmatic_service_principal import (
    PROGRAMMATIC_SCOPES,
    SCOPE_PREDICTIVE_EVALUATE,
    canonical_scopes,
)
from app.security import programmatic_access as pa

pytestmark = pytest.mark.unit

_AGORA = datetime(2026, 8, 22, 12, 0, tzinfo=UTC)


@dataclass
class _Linha:
    """Duplo mínimo de `ProgrammaticServicePrincipal`."""

    id: uuid.UUID
    key_id: str
    secret_digest: str
    scopes: list[str]
    quota_limit: int = 10
    quota_window_seconds: int = 60
    revoked_at: datetime | None = None
    expires_at: datetime | None = None

    def is_active_at(self, moment: datetime) -> bool:
        if self.revoked_at is not None:
            return False
        return self.expires_at is None or self.expires_at > moment


class _Repo:
    def __init__(self, linha: _Linha | None) -> None:
        self._linha = linha

    def get_by_key_id(self, key_id: str) -> _Linha | None:
        if self._linha is not None and self._linha.key_id == key_id:
            return self._linha
        return None

    def database_now(self) -> datetime:
        return _AGORA


class _RepoQuebrado:
    """Verificador indisponível — o caso que nunca pode virar liberação."""

    def get_by_key_id(self, key_id: str) -> object:
        raise RuntimeError("banco fora do ar")

    def database_now(self) -> datetime:  # pragma: no cover - inalcançável
        raise RuntimeError("banco fora do ar")


def _credencial(**kwargs: object) -> tuple[str, str, _Linha]:
    key_id = str(kwargs.get("key_id", "kid-abcdefgh"))
    secret = str(kwargs.get("secret", "segredo-de-teste-com-entropia-suficiente"))
    linha = _Linha(
        id=uuid.uuid4(),
        key_id=key_id,
        secret_digest=pa.compute_secret_digest(key_id, secret),
        scopes=[SCOPE_PREDICTIVE_EVALUATE],
        revoked_at=kwargs.get("revoked_at"),  # type: ignore[arg-type]
        expires_at=kwargs.get("expires_at"),  # type: ignore[arg-type]
    )
    return key_id, secret, linha


def _header(key_id: str, secret: str) -> str:
    return f"Bearer {pa.TOKEN_PREFIX}{key_id}.{secret}"


# --- prova 1/2/3: recusa pública indistinguível ----------------------------


def test_e62a01_sem_header_recusa() -> None:
    with pytest.raises(AuthenticationException) as erro:
        pa.authenticate_programmatic_principal(None, _Repo(None))  # type: ignore[arg-type]
    assert erro.value.detail == pa.PUBLIC_AUTH_DETAIL
    assert erro.value.status_code == 401
    assert erro.value.code == "PIA-7001"


@pytest.mark.parametrize(
    "header",
    [
        "",
        "Basic abc",
        "Bearer",
        "Bearer ",
        "Bearer semprefixo.abc",
        "Bearer pia_semponto",
        "Bearer pia_.somentesecret",
        "Bearer pia_somentekey.",
        "pia_kid.secret",
    ],
)
def test_e62a02_headers_malformados_recusam_igual(header: str) -> None:
    with pytest.raises(AuthenticationException) as erro:
        pa.authenticate_programmatic_principal(header, _Repo(None))  # type: ignore[arg-type]
    assert erro.value.detail == pa.PUBLIC_AUTH_DETAIL


def test_e62a03_resposta_publica_e_identica_em_todas_as_condicoes() -> None:
    """Quatro causas distintas, uma resposta. Diferenciar seria um oráculo."""
    key_id, secret, linha = _credencial()
    _, _, revogada = _credencial(key_id="kid-revogada", revoked_at=_AGORA - timedelta(days=1))
    _, _, expirada = _credencial(key_id="kid-expirada", expires_at=_AGORA - timedelta(seconds=1))

    casos = [
        (_header("kid-desconhecido", secret), _Repo(None)),
        (_header(key_id, "segredo-errado-mas-do-mesmo-tamanho!!"), _Repo(linha)),
        (_header("kid-revogada", secret), _Repo(revogada)),
        (_header("kid-expirada", secret), _Repo(expirada)),
    ]
    vistos = set()
    for header, repo in casos:
        with pytest.raises(AuthenticationException) as erro:
            pa.authenticate_programmatic_principal(header, repo)  # type: ignore[arg-type]
        vistos.add((erro.value.code, erro.value.status_code, str(erro.value.detail)))
    assert len(vistos) == 1, vistos


# --- prova 4: segredo nunca vaza -------------------------------------------


def test_e62a04_segredo_e_token_nunca_aparecem_no_erro() -> None:
    key_id, secret, linha = _credencial()
    header = _header(key_id, "segredo-que-nao-bate")
    with pytest.raises(AuthenticationException) as erro:
        pa.authenticate_programmatic_principal(header, _Repo(linha))  # type: ignore[arg-type]
    texto = f"{erro.value.message} {erro.value.detail} {erro.value!r}"
    assert secret not in texto
    assert "segredo-que-nao-bate" not in texto
    assert header not in texto
    assert linha.secret_digest not in texto


def test_e62a05_comparacao_de_digest_usa_tempo_constante() -> None:
    """`hmac.compare_digest` no fonte; `==` seria oráculo temporal."""
    import pathlib

    fonte = pathlib.Path(pa.__file__).read_text(encoding="utf-8")
    assert "hmac.compare_digest(" in fonte


def test_e62a06_principal_autenticado_nao_carrega_digest() -> None:
    key_id, secret, linha = _credencial()
    principal = pa.authenticate_programmatic_principal(
        _header(key_id, secret), _Repo(linha)  # type: ignore[arg-type]
    )
    assert principal.key_id == key_id
    assert not hasattr(principal, "secret_digest")
    assert linha.secret_digest not in repr(principal)


# --- prova 8: verificador indisponível recusa ------------------------------


def test_e62a07_repositorio_quebrado_recusa_em_vez_de_liberar() -> None:
    key_id, secret, _ = _credencial()
    with pytest.raises(AuthenticationException) as erro:
        pa.authenticate_programmatic_principal(
            _header(key_id, secret), _RepoQuebrado()  # type: ignore[arg-type]
        )
    assert erro.value.detail == pa.PUBLIC_AUTH_DETAIL


# --- prova 5: escopo --------------------------------------------------------


def test_e62a08_escopo_ausente_levanta_403_pia_7002() -> None:
    principal = pa.ProgrammaticPrincipal(
        id=uuid.uuid4(), key_id="kid-abcdefgh", scopes=(), quota_limit=1, quota_window_seconds=60
    )
    with pytest.raises(InsufficientScopeException) as erro:
        pa.require_scope(principal, SCOPE_PREDICTIVE_EVALUATE)
    assert erro.value.status_code == 403
    assert erro.value.code == "PIA-7002"


def test_e62a09_escopo_presente_passa() -> None:
    principal = pa.ProgrammaticPrincipal(
        id=uuid.uuid4(),
        key_id="kid-abcdefgh",
        scopes=(SCOPE_PREDICTIVE_EVALUATE,),
        quota_limit=1,
        quota_window_seconds=60,
    )
    pa.require_scope(principal, SCOPE_PREDICTIVE_EVALUATE)


# --- digest e vocabulário ---------------------------------------------------


def test_e62a10_digest_liga_segredo_ao_key_id() -> None:
    """O mesmo segredo em outro `key_id` produz digest diferente."""
    a = pa.compute_secret_digest("kid-aaaaaaaa", "mesmo-segredo")
    b = pa.compute_secret_digest("kid-bbbbbbbb", "mesmo-segredo")
    assert a != b
    assert len(a) == 64 and int(a, 16) >= 0


def test_e62a11_digest_muda_com_o_rotulo_de_dominio() -> None:
    """Sem separação de domínio, digests de outros usos valeriam aqui."""
    import hashlib
    import hmac

    from app.security.secrets import secrets_manager

    sem_rotulo = hmac.new(
        secrets_manager.get_secret_key().encode(),
        b"kid-aaaaaaaa:mesmo-segredo",
        hashlib.sha256,
    ).hexdigest()
    assert pa.compute_secret_digest("kid-aaaaaaaa", "mesmo-segredo") != sem_rotulo


def test_e62a12_segredo_gerado_tem_entropia_minima() -> None:
    import base64

    secret = pa.generate_secret()
    bruto = base64.urlsafe_b64decode(secret + "=" * (-len(secret) % 4))
    assert len(bruto) >= pa.MIN_SECRET_BYTES


def test_e62a13_key_id_gerado_nao_contem_o_separador() -> None:
    """Um ponto no `key_id` quebraria o parsing do token."""
    for _ in range(50):
        assert "." not in pa.generate_key_id()


def test_e62a14_escopos_sao_canonicos_e_o_vocabulario_e_fechado() -> None:
    assert canonical_scopes(["predictive:evaluate", "predictive:evaluate"]) == (
        "predictive:evaluate",
    )
    with pytest.raises(ValueError):
        canonical_scopes(["admin:*"])
    with pytest.raises(ValueError):
        canonical_scopes([])
    with pytest.raises(ValueError):
        canonical_scopes("predictive:evaluate")
    assert frozenset({SCOPE_PREDICTIVE_EVALUATE}) == PROGRAMMATIC_SCOPES


# --- mutantes dirigidos -----------------------------------------------------


def test_e62m01_mutante_que_aceita_digest_desigual_morre() -> None:
    """Trocar `compare_digest` por `True` autenticaria qualquer segredo."""
    key_id, _, linha = _credencial()
    with pytest.raises(AuthenticationException):
        pa.authenticate_programmatic_principal(
            _header(key_id, "qualquer-outro-segredo"), _Repo(linha)  # type: ignore[arg-type]
        )


def test_e62m02_mutante_que_ignora_revogacao_morre() -> None:
    key_id, secret, linha = _credencial()
    linha.revoked_at = _AGORA - timedelta(seconds=1)
    with pytest.raises(AuthenticationException):
        pa.authenticate_programmatic_principal(
            _header(key_id, secret), _Repo(linha)  # type: ignore[arg-type]
        )
    linha.revoked_at = None
    assert pa.authenticate_programmatic_principal(
        _header(key_id, secret), _Repo(linha)  # type: ignore[arg-type]
    )


def test_e62m03_mutante_que_troca_escopo_por_aprovacao_morre() -> None:
    """Escopo de serviço não é aprovação PIAP e não pode virar uma."""
    import pathlib

    fonte = pathlib.Path(pa.__file__).read_text(encoding="utf-8")
    for proibido in ("ApprovalBinding", "AuthorityContext", "PiapEnvelope", "approval_reference"):
        assert proibido not in fonte, proibido
