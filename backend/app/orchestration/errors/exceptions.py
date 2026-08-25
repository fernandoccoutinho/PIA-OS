"""Exceções da camada de orquestração (`E7.1`)."""

from app.exceptions.base import PIAOSException
from app.orchestration.errors.codes import (
    PIA_8057_ORCHESTRATION_CONTRACT_VIOLATION,
    PIA_8058_ORCHESTRATION_SCOPE_VIOLATION,
    PIA_8059_ORCHESTRATION_LIFECYCLE_VIOLATION,
    PIA_8060_SEAL_RECEIPT_IMMUTABLE,
    PIA_8061_HANDOFF_RECORD_IMMUTABLE,
    PIA_8062_DISPATCH_BLOCKED,
    PIA_8063_DELEGATION_IMMUTABLE,
    PIA_8064_AUDIT_RECORD_IMMUTABLE,
    PIA_8069_HUMAN_PROTECTION_GATE_UNAVAILABLE,
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


class HandoffRecordImmutableError(PIAOSException):
    """Veredito e atribuição não são alteráveis nem removíveis."""

    error_code = PIA_8061_HANDOFF_RECORD_IMMUTABLE


class DispatchBlockedError(PIAOSException):
    """Despacho recusado por gate; a pausa já foi persistida."""

    error_code = PIA_8062_DISPATCH_BLOCKED


class DelegationImmutableError(PIAOSException):
    """Vínculo imutável ou transição de estado terminal recusada."""

    error_code = PIA_8063_DELEGATION_IMMUTABLE


class GovernanceRecordImmutableError(PIAOSException):
    """Evento, observação e parecer não são alteráveis nem removíveis."""

    error_code = PIA_8064_AUDIT_RECORD_IMMUTABLE


class HumanProtectionGateUnavailableError(PIAOSException):
    """O gate de proteção humana não pôde decidir — zero efeito, nunca permissão."""

    error_code = PIA_8069_HUMAN_PROTECTION_GATE_UNAVAILABLE
