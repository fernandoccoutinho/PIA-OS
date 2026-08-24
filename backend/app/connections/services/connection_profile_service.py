"""
`ConnectionProfileService` — produtor único do perfil manual.

```text
MANUAL_PROFILE = ONE_PER_PRINCIPAL
endpoint_ref   = NULL
state          = AVAILABLE
criação        = IDEMPOTENTE (get-or-create sob lock)
```

O perfil manual é **real**, não marcador: é a conexão que de fato existe
e funciona desde a Chain113.

## Por que o protocolo tem savepoint

Sob concorrência, dois chamadores podem passar pelo `SELECT` antes de
qualquer `INSERT` existir. O advisory lock serializa quem chega pelo
serviço; o índice parcial recusa quem chegar por SQL bruto. Mas a
recusa do índice chega como `IntegrityError`, e um `IntegrityError` não
tratado **invalida a transação inteira** — inclusive a Attempt e o
`SealReceipt` que o chamador está no meio de gravar.

```text
PERDER A CORRIDA != INVALIDAR A TRANSAÇÃO EXTERNA
```

Por isso o `INSERT` acontece dentro de um `begin_nested()`: perder a
corrida reverte **apenas** o savepoint, e a releitura do vencedor
prossegue na mesma transação externa, intacta.
"""

import uuid
from dataclasses import dataclass

from sqlalchemy.exc import IntegrityError

from app.connections.errors.exceptions import ConnectionContractViolationError
from app.connections.models.enums import (
    AVAILABLE_CONNECTION_METHODS,
    BASELINE_METHOD_STATE,
    ConnectionMethod,
    ConnectionState,
)
from app.connections.repositories.connection_repository import ConnectionRepository
from app.connections.schemas.projection import ConnectionProfileView

MANUAL_METHOD = ConnectionMethod.MANUAL_HANDOFF
MANUAL_STATE = BASELINE_METHOD_STATE[ConnectionMethod.MANUAL_HANDOFF]


@dataclass(frozen=True)
class ManualProfileOutcome:
    """O perfil manual e **como** ele chegou até aqui.

    `created` distingue inserção de recuperação. A distinção sai do
    próprio caminho percorrido, e não de `xmax` ou de outro detalhe do
    motor — mesmo precedente da idempotência de comando da E7.1.
    """

    profile: ConnectionProfileView
    created: bool


class ConnectionProfileService:
    """Serviço público de perfis. Devolve dataclass congelada, nunca ORM."""

    def __init__(self, repository: ConnectionRepository) -> None:
        self._repository = repository

    def ensure_manual_profile(self, *, control_principal_ref: str) -> ManualProfileOutcome:
        """Get-or-create idempotente do perfil manual deste principal.

        ```text
        4 chamadores concorrentes -> 4 retornos, 1 connection_id, 1 linha,
                                     0 IntegrityError exposto
        ```
        """
        if not control_principal_ref.strip():
            raise ConnectionContractViolationError(
                message="control_principal_ref não pode ser vazio",
                detail={"control_principal_ref": control_principal_ref},
            )

        existente = self._repository.get_manual_profile(control_principal_ref=control_principal_ref)
        if existente is not None:
            return ManualProfileOutcome(profile=_projetar(existente), created=False)

        self._repository.acquire_manual_profile_lock(control_principal_ref=control_principal_ref)

        # Releitura DEPOIS do lock: entre o primeiro SELECT e a aquisição
        # do lock, o vencedor da corrida pode ter commitado.
        existente = self._repository.get_manual_profile(control_principal_ref=control_principal_ref)
        if existente is not None:
            return ManualProfileOutcome(profile=_projetar(existente), created=False)

        try:
            with self._repository.nested_transaction():
                criado = self._repository.create_profile(
                    control_principal_ref=control_principal_ref,
                    method=MANUAL_METHOD,
                    state=MANUAL_STATE,
                    endpoint_ref=None,
                    access_provider_id=None,
                    display_name=None,
                    credential_ref=None,
                )
                vista = _projetar(criado, access_provider_slug=None)
        except IntegrityError:
            # O índice parcial recusou: outro caminho venceu. O savepoint
            # já foi revertido, e a transação externa segue utilizável.
            vencedor = self._repository.get_manual_profile(
                control_principal_ref=control_principal_ref
            )
            if vencedor is None:  # pragma: no cover - defensivo
                raise
            return ManualProfileOutcome(profile=_projetar(vencedor), created=False)

        return ManualProfileOutcome(profile=vista, created=True)

    def declare_profile(
        self,
        *,
        control_principal_ref: str,
        method: ConnectionMethod,
        endpoint_ref: str | None,
        access_provider_id: uuid.UUID | None = None,
        display_name: str | None = None,
    ) -> ConnectionProfileView:
        """Declara um perfil **no estado de nascimento do método**.

        ```text
        ENUM_OR_REGISTRY != AVAILABLE
        ```

        O estado não é parâmetro. Aceitá-lo do chamador seria oferecer a
        promoção a `AVAILABLE` como argumento — exatamente o que o
        mutante `M-AVAILABLE` tenta.
        """
        if method is MANUAL_METHOD:
            raise ConnectionContractViolationError(
                message="perfil manual é criado por ensure_manual_profile, que é idempotente",
                detail={"method": method.value},
            )
        if endpoint_ref is not None and not endpoint_ref.strip():
            raise ConnectionContractViolationError(
                message="endpoint_ref informado não pode ser branco",
                detail={"method": method.value},
            )
        estado = BASELINE_METHOD_STATE[method]
        if estado is ConnectionState.AVAILABLE and method not in AVAILABLE_CONNECTION_METHODS:
            raise ConnectionContractViolationError(  # pragma: no cover - inalcançável hoje
                message="método não pode nascer AVAILABLE",
                detail={"method": method.value},
            )
        criado = self._repository.create_profile(
            control_principal_ref=control_principal_ref,
            method=method,
            state=estado,
            endpoint_ref=endpoint_ref,
            access_provider_id=access_provider_id,
            display_name=display_name,
            credential_ref=None,
        )
        return _projetar(criado, access_provider_slug=self._slug_de(criado))

    def list_profiles(self, *, control_principal_ref: str) -> tuple[ConnectionProfileView, ...]:
        """Perfis deste principal, em ordem determinística."""
        return tuple(
            _projetar(perfil, access_provider_slug=self._slug_de(perfil))
            for perfil in self._repository.list_profiles(
                control_principal_ref=control_principal_ref
            )
        )

    def _slug_de(self, perfil: object) -> str | None:
        """Resolve o slug do operador pelo repositório, dentro da sessão.

        O slug é *lido*, e não copiado do perfil: o perfil guarda a
        referência, e a projeção é leitura corrente. O recibo é que copia
        — é lá que a atribuição precisa sobreviver a mudanças no perfil.
        """
        provedor_id = perfil.access_provider_id  # type: ignore[attr-defined]
        if provedor_id is None:
            return None
        provedor = self._repository.get_access_provider(provider_id=provedor_id)
        return None if provedor is None else provedor.slug


def _projetar(perfil: object, *, access_provider_slug: str | None = None) -> ConnectionProfileView:
    """Extrai colunas **dentro** da sessão e devolve o DTO congelado.

    Lição reincidente: conservar entidade ORM além do fim da UnitOfWork
    dá `DetachedInstanceError`. A regra do programa é extrair na sessão e
    asserir o DTO fora.
    """
    return ConnectionProfileView(
        connection_id=perfil.id,  # type: ignore[attr-defined]
        method=perfil.method,  # type: ignore[attr-defined]
        state=perfil.state,  # type: ignore[attr-defined]
        endpoint_ref=perfil.endpoint_ref,  # type: ignore[attr-defined]
        access_provider_slug=access_provider_slug,
        display_name=perfil.display_name,  # type: ignore[attr-defined]
    )
