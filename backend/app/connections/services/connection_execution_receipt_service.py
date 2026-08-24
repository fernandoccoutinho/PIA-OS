"""
`ConnectionExecutionReceiptService` — produtor único do recibo de execução.

```text
1 Attempt = 1 ConnectionExecutionReceipt
PROFILE_DESCREVE_CONFIGURAÇÃO != RECIBO_DESCREVE_EXECUÇÃO
```

Os seis campos operacionais são **copiados no ato**. Copiar, e não
derivar por join na leitura, é o que faz um perfil alterado amanhã não
reescrever a execução de ontem.

## O manual

O repasse manual não tem operador, não solicita modelo e não observa
modelo algum: quem transporta é a pessoa.

```text
access_provider  = NULL
requested_model  = NULL
observed_model   = NULL
atestação        = unknown
```

`unknown` é a verdade, e preencher qualquer um desses campos com um
palpite seria fabricar atribuição.
"""

import uuid
from dataclasses import dataclass
from datetime import datetime

from app.connections.errors.exceptions import ConnectionContractViolationError
from app.connections.models.enums import ConnectionMethod, ModelAttestationLevel
from app.connections.repositories.connection_repository import ConnectionRepository
from app.connections.schemas.projection import ConnectionExecutionReceiptView


@dataclass(frozen=True)
class ExecutionAttribution:
    """Os seis campos operacionais, como o chamador os declara.

    Value object separado do serviço para que a bicondicional da
    atestação seja verificada **antes** de qualquer escrita, e não só
    pelo `CHECK` do banco. As duas camadas não são redundantes: o
    `CHECK` pega SQL bruto, este `__post_init__` pega composição errada
    sem gastar uma transação.
    """

    connection_id: uuid.UUID
    connection_method: ConnectionMethod
    access_provider: str | None
    requested_model: str | None
    observed_model: str | None
    model_attestation_level: ModelAttestationLevel

    def __post_init__(self) -> None:
        atestado = self.model_attestation_level is ModelAttestationLevel.ATTESTED
        if atestado != (self.observed_model is not None):
            raise ValueError("atestação `attested` exige observed_model não nulo, e vice-versa")
        if self.connection_method is ConnectionMethod.MANUAL_HANDOFF and (
            self.access_provider is not None
        ):
            raise ValueError("repasse manual não tem operador de acesso")


def manual_attribution(*, connection_id: uuid.UUID) -> ExecutionAttribution:
    """A atribuição de um repasse manual. Sem palpites."""
    return ExecutionAttribution(
        connection_id=connection_id,
        connection_method=ConnectionMethod.MANUAL_HANDOFF,
        access_provider=None,
        requested_model=None,
        observed_model=None,
        model_attestation_level=ModelAttestationLevel.UNKNOWN,
    )


class ConnectionExecutionReceiptService:
    """Grava o recibo. Append-only em três camadas, como `seal_receipts`."""

    def __init__(self, repository: ConnectionRepository) -> None:
        self._repository = repository

    def database_now(self) -> datetime:
        """Instante do PostgreSQL, exposto pelo serviço.

        O chamador não alcança `Session` nem repositório — expor o
        relógio aqui é o que permite ao serviço manual carimbar
        `observed_at` sem abrir uma segunda fonte de tempo.
        """
        return self._repository.database_now()

    def record_execution(
        self,
        *,
        control_principal_ref: str,
        schedule_id: uuid.UUID,
        step_id: uuid.UUID,
        attempt_id: uuid.UUID,
        attribution: ExecutionAttribution,
        observed_at: datetime,
    ) -> ConnectionExecutionReceiptView:
        """Escreve um recibo para esta Attempt.

        `UNIQUE (attempt_id)` recusa o segundo. A recusa é do banco e não
        de uma verificação prévia, porque uma verificação prévia deixa a
        janela aberta entre o `SELECT` e o `INSERT`.
        """
        if not control_principal_ref.strip():
            raise ConnectionContractViolationError(
                message="control_principal_ref não pode ser vazio",
                detail={"attempt_id": str(attempt_id)},
            )
        recibo = self._repository.create_execution_receipt(
            control_principal_ref=control_principal_ref,
            schedule_id=schedule_id,
            step_id=step_id,
            attempt_id=attempt_id,
            connection_id=attribution.connection_id,
            connection_method=attribution.connection_method,
            access_provider=attribution.access_provider,
            requested_model=attribution.requested_model,
            observed_model=attribution.observed_model,
            model_attestation_level=attribution.model_attestation_level,
            observed_at=observed_at,
        )
        return ConnectionExecutionReceiptView(
            receipt_id=recibo.id,
            attempt_id=recibo.attempt_id,
            step_id=recibo.step_id,
            schedule_id=recibo.schedule_id,
            connection_id=recibo.connection_id,
            connection_method=recibo.connection_method,
            access_provider=recibo.access_provider,
            requested_model=recibo.requested_model,
            observed_model=recibo.observed_model,
            model_attestation_level=recibo.model_attestation_level,
            observed_at=recibo.observed_at,
        )

    def get_by_attempt(
        self, *, control_principal_ref: str, schedule_id: uuid.UUID, attempt_id: uuid.UUID
    ) -> ConnectionExecutionReceiptView | None:
        """Leitura escopada. `schedule_id` vem do chamador, nunca do recibo."""
        recibo = self._repository.get_execution_receipt_by_attempt(
            control_principal_ref=control_principal_ref,
            schedule_id=schedule_id,
            attempt_id=attempt_id,
        )
        if recibo is None:
            return None
        return ConnectionExecutionReceiptView(
            receipt_id=recibo.id,
            attempt_id=recibo.attempt_id,
            step_id=recibo.step_id,
            schedule_id=recibo.schedule_id,
            connection_id=recibo.connection_id,
            connection_method=recibo.connection_method,
            access_provider=recibo.access_provider,
            requested_model=recibo.requested_model,
            observed_model=recibo.observed_model,
            model_attestation_level=recibo.model_attestation_level,
            observed_at=recibo.observed_at,
        )
