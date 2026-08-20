"""Exceções da camada PIAP (`E5.a`)."""

from app.exceptions.base import PIAOSException
from app.predictive_accessibility.errors.codes import (
    PIA_8052_PIAP_UNSUPPORTED_VERSION,
    PIA_8053_PIAP_CONTRACT_VIOLATION,
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
