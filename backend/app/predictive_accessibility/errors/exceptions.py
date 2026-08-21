"""Exceções da camada PIAP (`E5.a`)."""

import uuid

from app.exceptions.base import PIAOSException
from app.predictive_accessibility.errors.codes import (
    PIA_8052_PIAP_UNSUPPORTED_VERSION,
    PIA_8053_PIAP_CONTRACT_VIOLATION,
    PIA_8054_RECONFIGURATION_EVENT_IDENTITY_MISMATCH,
    PIA_8055_RECONFIGURATION_EVENT_IMMUTABLE,
    PIA_8056_RECONFIGURATION_CONTRACT_VIOLATION,
)


class PiapUnsupportedVersionError(PIAOSException):
    """Versão de contrato fora da allowlist.

    ```text
    NEWER_VERSION != COMPATIBLE_BY_DEFAULT
    OLDER_VERSION != READABLE_BY_DEFAULT
    FAIL_OPEN = FORBIDDEN
    ```
    """

    error_code = PIA_8052_PIAP_UNSUPPORTED_VERSION


class PiapContractViolationError(PIAOSException):
    """Payload serializado fora da forma canônica do contrato.

    Campo ausente, campo extra, chave JSON duplicada ou tipo errado. Nada
    é descartado, defaultado ou normalizado em silêncio para fazer o
    payload caber.

    ```text
    SILENT_FIELD_DROP = FORBIDDEN
    SILENT_NORMALIZATION = FORBIDDEN
    ```
    """

    error_code = PIA_8053_PIAP_CONTRACT_VIOLATION


class PredictiveReconfigurationEventIdentityMismatchError(PIAOSException):
    """Replay de identidade com payload divergente; nada é sobrescrito."""

    error_code = PIA_8054_RECONFIGURATION_EVENT_IDENTITY_MISMATCH

    def __init__(self, event_id: uuid.UUID, diverging_fields: tuple[str, ...]) -> None:
        self.event_id = event_id
        self.diverging_fields = diverging_fields
        super().__init__(
            message=f"Evento preditivo {event_id} já existe com conteúdo diferente.",
            detail={
                "event_id": str(event_id),
                "diverging_fields": list(diverging_fields),
            },
        )


class PredictiveReconfigurationEventImmutableError(PIAOSException):
    """Recusa de UPDATE/DELETE no log append-only."""

    error_code = PIA_8055_RECONFIGURATION_EVENT_IMMUTABLE

    def __init__(self, operation: str) -> None:
        super().__init__(
            message=f"predictive_reconfiguration_events é append-only: {operation} recusado.",
            detail={"operation": operation},
        )


class PredictiveReconfigurationContractError(PIAOSException):
    """Contrato de promoção ou rollback inválido antes de qualquer SQL."""

    error_code = PIA_8056_RECONFIGURATION_CONTRACT_VIOLATION
