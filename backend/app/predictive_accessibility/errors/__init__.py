"""Erros da camada PIAP (`E5.a`)."""

from app.predictive_accessibility.errors.codes import (
    PIA_8052_PIAP_UNSUPPORTED_VERSION,
    PIA_8053_PIAP_CONTRACT_VIOLATION,
)
from app.predictive_accessibility.errors.exceptions import (
    PiapContractViolationError,
    PiapUnsupportedVersionError,
)

__all__ = [
    "PIA_8052_PIAP_UNSUPPORTED_VERSION",
    "PIA_8053_PIAP_CONTRACT_VIOLATION",
    "PiapContractViolationError",
    "PiapUnsupportedVersionError",
]
