"""
Provisionamento administrativo LOCAL de principal técnico (E6.2).

```text
HTTP_CREDENTIAL_ISSUANCE = FORBIDDEN
SECRET_SHOWN_ONCE = TRUE
SECRET_RECOVERY = IMPOSSIBLE
```

Comando de terminal, não endpoint. Um endpoint de emissão seria uma rota
que cria credenciais — precisaria de sua própria autenticação e viraria o
alvo mais valioso da API. Aqui a autoridade é o acesso ao servidor e ao
banco, que já existe e já é controlado.

Uso:

    python -m scripts.programmatic_principal create \\
        --scope predictive:evaluate --quota-limit 60 --quota-window 60
    python -m scripts.programmatic_principal revoke --key-id <key_id>

O segredo aparece uma única vez em stdout. Não há listagem de segredos e
não há recuperação: perdida a credencial, revoga-se e emite-se outra.
"""

import argparse
import sys
from datetime import UTC, datetime

from app.database.session import session_scope
from app.models.programmatic_service_principal import (
    PROGRAMMATIC_SCOPES,
    canonical_scopes,
)
from app.repositories.programmatic_access_repository import ProgrammaticAccessRepository
from app.security.programmatic_access import (
    TOKEN_PREFIX,
    compute_secret_digest,
    generate_key_id,
    generate_secret,
)

MAX_QUOTA_LIMIT = 1_000_000
MAX_QUOTA_WINDOW_SECONDS = 86_400


class ProvisioningError(ValueError):
    """Entrada administrativa inválida — recusada antes de tocar o banco."""


def _validate(quota_limit: int, quota_window_seconds: int, scopes: tuple[str, ...]) -> None:
    if quota_limit <= 0 or quota_limit > MAX_QUOTA_LIMIT:
        raise ProvisioningError(f"quota-limit deve estar entre 1 e {MAX_QUOTA_LIMIT}")
    if quota_window_seconds <= 0 or quota_window_seconds > MAX_QUOTA_WINDOW_SECONDS:
        raise ProvisioningError(
            f"quota-window deve estar entre 1 e {MAX_QUOTA_WINDOW_SECONDS} segundos"
        )
    if not scopes:
        raise ProvisioningError("informe ao menos um escopo")


def create_principal(
    *,
    scopes: tuple[str, ...],
    quota_limit: int,
    quota_window_seconds: int,
    description: str | None = None,
    expires_at: datetime | None = None,
) -> tuple[str, str]:
    """Cria o principal e devolve `(key_id, token_completo)` UMA vez.

    O token completo nunca é persistido nem devolvido de novo: o banco
    recebe apenas o digest.
    """
    canonicos = canonical_scopes(scopes)
    _validate(quota_limit, quota_window_seconds, canonicos)
    if expires_at is not None and expires_at <= datetime.now(UTC):
        raise ProvisioningError("expires-at deve ser um instante futuro")

    key_id = generate_key_id()
    secret = generate_secret()
    digest = compute_secret_digest(key_id, secret)
    with session_scope() as sessao:
        repositorio = ProgrammaticAccessRepository(sessao)
        if repositorio.get_by_key_id(key_id) is not None:  # pragma: no cover - colisão improvável
            raise ProvisioningError("colisão de key_id; execute o comando novamente")
        repositorio.create_principal(
            key_id=key_id,
            secret_digest=digest,
            scopes=canonicos,
            quota_limit=quota_limit,
            quota_window_seconds=quota_window_seconds,
            description=description,
            expires_at=expires_at,
        )
    return key_id, f"{TOKEN_PREFIX}{key_id}.{secret}"


def revoke_principal(key_id: str) -> bool:
    """Idempotente. Não revela digest nem segredo, apenas se existia."""
    if not key_id or not key_id.strip():
        raise ProvisioningError("key-id é obrigatório")
    with session_scope() as sessao:
        return ProgrammaticAccessRepository(sessao).revoke(key_id.strip())


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="programmatic_principal",
        description="Provisionamento local de principal técnico (E6.2).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    criar = sub.add_parser("create", help="Cria um principal e exibe a credencial uma vez.")
    criar.add_argument(
        "--scope",
        action="append",
        default=None,
        choices=sorted(PROGRAMMATIC_SCOPES),
        help="Escopo técnico; repetível. Padrão: predictive:evaluate.",
    )
    criar.add_argument("--quota-limit", type=int, required=True)
    criar.add_argument("--quota-window", type=int, required=True, dest="quota_window")
    criar.add_argument("--description", default=None)
    criar.add_argument(
        "--expires-at", default=None, help="ISO-8601 com timezone, ex.: 2027-01-01T00:00:00Z"
    )

    revogar = sub.add_parser("revoke", help="Revoga um principal pelo key_id (idempotente).")
    revogar.add_argument("--key-id", required=True, dest="key_id")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        if args.command == "create":
            expira = (
                datetime.fromisoformat(args.expires_at.replace("Z", "+00:00"))
                if args.expires_at
                else None
            )
            key_id, token = create_principal(
                scopes=tuple(args.scope or ["predictive:evaluate"]),
                quota_limit=args.quota_limit,
                quota_window_seconds=args.quota_window,
                description=args.description,
                expires_at=expira,
            )
            print(f"key_id: {key_id}")
            print(f"credential (exibida uma unica vez): {token}")
            print("guarde agora; nao ha recuperacao nem listagem de segredo")
            return 0
        existia = revoke_principal(args.key_id)
        print("revogado" if existia else "key_id inexistente")
        return 0 if existia else 1
    except (ProvisioningError, ValueError) as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover - entrypoint
    raise SystemExit(main())
