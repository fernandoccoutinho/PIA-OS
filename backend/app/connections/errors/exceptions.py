"""Exceções do kernel de conexões (`E7.4-1`)."""

from app.connections.errors.codes import (
    PIA_8065_CONNECTION_SCOPE_VIOLATION,
    PIA_8066_CONNECTION_CONTRACT_VIOLATION,
    PIA_8067_CONNECTION_RECORD_IMMUTABLE,
    PIA_8068_ENTITLEMENT_SUCCESSION_VIOLATION,
)
from app.exceptions.base import PIAOSException


class ConnectionScopeViolationError(PIAOSException):
    """Conexão inexistente sob o principal de controle informado."""

    error_code = PIA_8065_CONNECTION_SCOPE_VIOLATION


class ConnectionContractViolationError(PIAOSException):
    """Declaração recusada antes da persistência."""

    error_code = PIA_8066_CONNECTION_CONTRACT_VIOLATION


class ConnectionRecordImmutableError(PIAOSException):
    """Recibo, snapshot e evidência não são alteráveis nem removíveis."""

    error_code = PIA_8067_CONNECTION_RECORD_IMMUTABLE


class EntitlementSuccessionViolationError(PIAOSException):
    """Alegação mutada, autossucedida ou sucedida por registro incoerente."""

    error_code = PIA_8068_ENTITLEMENT_SUCCESSION_VIOLATION
