"""
Catálogo oficial de códigos de erro do PIA-OS.

Cada código é único, imutável após publicado (não reutilize um código já
catalogado para um erro diferente — crie um novo) e pertence a uma faixa
numérica por categoria:

    PIA-0xxx — sistema / desconhecido
    PIA-1xxx — API / HTTP
    PIA-2xxx — validação
    PIA-3xxx — banco de dados / persistência
    PIA-4xxx — configuração
    PIA-5xxx — infraestrutura
    PIA-6xxx — serviços externos
    PIA-7xxx — autenticação e escopo de principal
"""

from dataclasses import dataclass
from enum import StrEnum


class ErrorCategory(StrEnum):
    SYSTEM = "system"
    API = "api"
    VALIDATION = "validation"
    DATABASE = "database"
    CONFIGURATION = "configuration"
    INFRASTRUCTURE = "infrastructure"
    EXTERNAL = "external"
    AUTHENTICATION = "authentication"


class ErrorSeverity(StrEnum):
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


@dataclass(frozen=True)
class ErrorCode:
    code: str
    default_message: str
    category: ErrorCategory
    http_status: int
    severity: ErrorSeverity


# --- PIA-0xxx — sistema / desconhecido ---
PIA_0001_UNKNOWN_ERROR = ErrorCode(
    code="PIA-0001",
    default_message="Erro desconhecido.",
    category=ErrorCategory.SYSTEM,
    http_status=500,
    severity=ErrorSeverity.CRITICAL,
)
PIA_0002_INTERNAL_ERROR = ErrorCode(
    code="PIA-0002",
    default_message="internal_server_error",
    category=ErrorCategory.SYSTEM,
    http_status=500,
    severity=ErrorSeverity.CRITICAL,
)

# --- PIA-1xxx — API / HTTP ---
PIA_1001_BAD_REQUEST = ErrorCode(
    code="PIA-1001",
    default_message="bad_request",
    category=ErrorCategory.API,
    http_status=400,
    severity=ErrorSeverity.WARNING,
)
PIA_1002_NOT_FOUND = ErrorCode(
    code="PIA-1002",
    default_message="not_found",
    category=ErrorCategory.API,
    http_status=404,
    severity=ErrorSeverity.WARNING,
)
PIA_1003_METHOD_NOT_ALLOWED = ErrorCode(
    code="PIA-1003",
    default_message="method_not_allowed",
    category=ErrorCategory.API,
    http_status=405,
    severity=ErrorSeverity.WARNING,
)
PIA_1004_CONFLICT = ErrorCode(
    code="PIA-1004",
    default_message="conflict",
    category=ErrorCategory.API,
    http_status=409,
    severity=ErrorSeverity.WARNING,
)
PIA_1005_HTTP_ERROR = ErrorCode(
    code="PIA-1005",
    default_message="http_error",
    category=ErrorCategory.API,
    http_status=400,
    severity=ErrorSeverity.WARNING,
)
PIA_1006_PAYLOAD_TOO_LARGE = ErrorCode(
    code="PIA-1006",
    default_message="payload_too_large",
    category=ErrorCategory.API,
    http_status=413,
    severity=ErrorSeverity.WARNING,
)
PIA_1007_UNSUPPORTED_MEDIA_TYPE = ErrorCode(
    code="PIA-1007",
    default_message="unsupported_media_type",
    category=ErrorCategory.API,
    http_status=415,
    severity=ErrorSeverity.WARNING,
)
PIA_1008_TOO_MANY_REQUESTS = ErrorCode(
    code="PIA-1008",
    default_message="too_many_requests",
    category=ErrorCategory.API,
    http_status=429,
    severity=ErrorSeverity.WARNING,
)
PIA_1009_UNTRUSTED_HOST = ErrorCode(
    code="PIA-1009",
    default_message="untrusted_host",
    category=ErrorCategory.API,
    http_status=400,
    severity=ErrorSeverity.ERROR,
)

# --- PIA-2xxx — validação ---
PIA_2001_VALIDATION_ERROR = ErrorCode(
    code="PIA-2001",
    default_message="validation_error",
    category=ErrorCategory.VALIDATION,
    http_status=422,
    severity=ErrorSeverity.WARNING,
)

# --- PIA-3xxx — banco de dados / persistência ---
PIA_3001_DATABASE_ERROR = ErrorCode(
    code="PIA-3001",
    default_message="database_error",
    category=ErrorCategory.DATABASE,
    http_status=500,
    severity=ErrorSeverity.ERROR,
)
PIA_3002_DATABASE_UNAVAILABLE = ErrorCode(
    code="PIA-3002",
    default_message="database_unavailable",
    category=ErrorCategory.DATABASE,
    http_status=503,
    severity=ErrorSeverity.CRITICAL,
)

# --- PIA-4xxx — configuração ---
PIA_4001_CONFIGURATION_ERROR = ErrorCode(
    code="PIA-4001",
    default_message="configuration_error",
    category=ErrorCategory.CONFIGURATION,
    http_status=500,
    severity=ErrorSeverity.CRITICAL,
)

# --- PIA-5xxx — infraestrutura ---
PIA_5001_INFRASTRUCTURE_ERROR = ErrorCode(
    code="PIA-5001",
    default_message="infrastructure_error",
    category=ErrorCategory.INFRASTRUCTURE,
    http_status=503,
    severity=ErrorSeverity.ERROR,
)

# --- PIA-6xxx — serviços externos ---
PIA_6001_EXTERNAL_SERVICE_ERROR = ErrorCode(
    code="PIA-6001",
    default_message="external_service_error",
    category=ErrorCategory.EXTERNAL,
    http_status=502,
    severity=ErrorSeverity.ERROR,
)

# --- PIA-7xxx — autenticação e escopo ---
PIA_7001_AUTHENTICATION_ERROR = ErrorCode(
    code="PIA-7001",
    default_message="authentication_error",
    category=ErrorCategory.AUTHENTICATION,
    http_status=401,
    severity=ErrorSeverity.WARNING,
)
PIA_7002_INSUFFICIENT_SCOPE = ErrorCode(
    code="PIA-7002",
    default_message="insufficient_scope",
    category=ErrorCategory.AUTHENTICATION,
    http_status=403,
    severity=ErrorSeverity.WARNING,
)

ALL_ERROR_CODES: tuple[ErrorCode, ...] = (
    PIA_0001_UNKNOWN_ERROR,
    PIA_0002_INTERNAL_ERROR,
    PIA_1001_BAD_REQUEST,
    PIA_1002_NOT_FOUND,
    PIA_1003_METHOD_NOT_ALLOWED,
    PIA_1004_CONFLICT,
    PIA_1005_HTTP_ERROR,
    PIA_1006_PAYLOAD_TOO_LARGE,
    PIA_1007_UNSUPPORTED_MEDIA_TYPE,
    PIA_1008_TOO_MANY_REQUESTS,
    PIA_1009_UNTRUSTED_HOST,
    PIA_2001_VALIDATION_ERROR,
    PIA_3001_DATABASE_ERROR,
    PIA_3002_DATABASE_UNAVAILABLE,
    PIA_4001_CONFIGURATION_ERROR,
    PIA_5001_INFRASTRUCTURE_ERROR,
    PIA_6001_EXTERNAL_SERVICE_ERROR,
    PIA_7001_AUTHENTICATION_ERROR,
    PIA_7002_INSUFFICIENT_SCOPE,
)

# Mapa código -> ErrorCode, útil para lookup reverso (ex.: documentação,
# um futuro endpoint de catálogo de erros).
ERROR_CODE_BY_CODE: dict[str, ErrorCode] = {ec.code: ec for ec in ALL_ERROR_CODES}


def error_code_for_http_status(status_code: int) -> ErrorCode:
    """Mapeia um status HTTP genérico (de uma `HTTPException` crua, sem
    `PIAOSException` associada) para o `ErrorCode` mais apropriado do
    catálogo. Usado pelo handler de `StarletteHTTPException`."""
    mapping: dict[int, ErrorCode] = {
        400: PIA_1001_BAD_REQUEST,
        404: PIA_1002_NOT_FOUND,
        405: PIA_1003_METHOD_NOT_ALLOWED,
        409: PIA_1004_CONFLICT,
        413: PIA_1006_PAYLOAD_TOO_LARGE,
        415: PIA_1007_UNSUPPORTED_MEDIA_TYPE,
        422: PIA_2001_VALIDATION_ERROR,
        429: PIA_1008_TOO_MANY_REQUESTS,
    }
    return mapping.get(status_code, PIA_1005_HTTP_ERROR)
