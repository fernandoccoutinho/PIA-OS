"""Exceções da camada de orquestração (`E7.1`)."""

from app.exceptions.base import PIAOSException
from app.orchestration.errors.codes import (
    PIA_8057_ORCHESTRATION_CONTRACT_VIOLATION,
    PIA_8058_ORCHESTRATION_SCOPE_VIOLATION,
    PIA_8059_ORCHESTRATION_LIFECYCLE_VIOLATION,
    PIA_8060_SEAL_RECEIPT_IMMUTABLE,
)


class OrchestrationContractViolationError(PIAOSException):
    """Declaração recusada antes da persistência."""

    error_code = PIA_8057_ORCHESTRATION_CONTRACT_VIOLATION


class OrchestrationScopeViolationError(PIAOSException):
    """Recurso inexistente sob o principal de controle informado."""

    error_code = PIA_8058_ORCHESTRATION_SCOPE_VIOLATION


class OrchestrationLifecycleViolationError(PIAOSException):
    """Operação pedida fora do estado em que ela existe."""

    error_code = PIA_8059_ORCHESTRATION_LIFECYCLE_VIOLATION


class SealReceiptImmutableError(PIAOSException):
    """Recibo de selamento não é alterável nem removível."""

    error_code = PIA_8060_SEAL_RECEIPT_IMMUTABLE
