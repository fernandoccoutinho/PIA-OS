"""
Constantes oficiais da aplicação PIA-OS.

Valores que não variam por ambiente e não são segredos — apenas
identidade e limites padrão da plataforma. Configuração que varia
por ambiente pertence a `settings.py`, não aqui.
"""

from typing import Final

# --- Identidade da aplicação ---
APP_NAME: Final[str] = "PIA-OS Backend"
APP_VERSION: Final[str] = "0.1.0"
API_VERSION: Final[str] = "v1"
API_PREFIX: Final[str] = f"/api/{API_VERSION}"
PIA_OS_VERSION: Final[str] = "1.0.0"

# --- Formatos ---
DATE_FORMAT: Final[str] = "%Y-%m-%d"
DATETIME_FORMAT: Final[str] = "%Y-%m-%dT%H:%M:%S%z"

# --- Rede / limites padrão ---
MIN_PORT: Final[int] = 1
MAX_PORT: Final[int] = 65535
DEFAULT_DB_PORT: Final[int] = 5432

# --- Paginação (limites padrão para uso futuro pelos módulos de negócio) ---
DEFAULT_PAGE_SIZE: Final[int] = 20
MAX_PAGE_SIZE: Final[int] = 200

# --- Logging ---
VALID_LOG_LEVELS: Final[frozenset[str]] = frozenset(
    {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
)
VALID_LOG_FORMATS: Final[frozenset[str]] = frozenset({"json", "text"})
VALID_LOG_DESTINATIONS: Final[frozenset[str]] = frozenset({"console", "file", "syslog"})

# --- Segurança ---
VALID_JWT_ALGORITHMS: Final[frozenset[str]] = frozenset({"HS256", "HS384", "HS512"})
DEFAULT_JWT_ALGORITHM: Final[str] = "HS256"
DEFAULT_JWT_EXPIRATION_MINUTES: Final[int] = 30

# --- Headers HTTP internos ---
REQUEST_ID_HEADER: Final[str] = "X-Request-ID"
RESPONSE_TIME_HEADER: Final[str] = "X-Response-Time-Ms"
