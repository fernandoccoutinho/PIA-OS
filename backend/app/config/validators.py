"""
Validadores reutilizáveis para os campos de configuração.

Funções puras, sem estado, usadas como `field_validator` dentro de
`settings.py`. Mantidas separadas para permitir reuso e testes
isolados, sem acoplar validação à definição dos campos.
"""

from urllib.parse import urlparse

from app.config.constants import (
    MAX_PORT,
    MIN_PORT,
    VALID_JWT_ALGORITHMS,
    VALID_LOG_DESTINATIONS,
    VALID_LOG_FORMATS,
    VALID_LOG_LEVELS,
)


def validate_port(value: int) -> int:
    """Valida que um valor está dentro da faixa de portas TCP válidas."""
    if not (MIN_PORT <= value <= MAX_PORT):
        raise ValueError(f"Porta {value} fora da faixa válida ({MIN_PORT}-{MAX_PORT}).")
    return value


def validate_log_level(value: str) -> str:
    """Valida que o nível de log é um dos níveis padrão do logging."""
    normalized = value.strip().upper()
    if normalized not in VALID_LOG_LEVELS:
        valid = ", ".join(sorted(VALID_LOG_LEVELS))
        raise ValueError(f"LOG_LEVEL '{value}' inválido. Valores aceitos: {valid}.")
    return normalized


def validate_log_format(value: str) -> str:
    """Valida que o formato de log é 'json' ou 'text'."""
    normalized = value.strip().lower()
    if normalized not in VALID_LOG_FORMATS:
        valid = ", ".join(sorted(VALID_LOG_FORMATS))
        raise ValueError(f"LOG_FORMAT '{value}' inválido. Valores aceitos: {valid}.")
    return normalized


def validate_log_destination(value: str) -> str:
    """Valida LOG_DESTINATION — lista separada por vírgula de destinos
    conhecidos (console, file, syslog). Normaliza espaços e caixa."""
    parts = [p.strip().lower() for p in value.split(",") if p.strip()]
    if not parts:
        raise ValueError("LOG_DESTINATION não pode ser vazio.")
    invalid = set(parts) - VALID_LOG_DESTINATIONS
    if invalid:
        valid = ", ".join(sorted(VALID_LOG_DESTINATIONS))
        raise ValueError(
            f"LOG_DESTINATION contém valor(es) inválido(s): {sorted(invalid)}. "
            f"Valores aceitos: {valid}."
        )
    return ",".join(parts)


def validate_jwt_algorithm(value: str) -> str:
    """Valida que o algoritmo JWT é um dos suportados por esta plataforma."""
    normalized = value.strip().upper()
    if normalized not in VALID_JWT_ALGORITHMS:
        valid = ", ".join(sorted(VALID_JWT_ALGORITHMS))
        raise ValueError(f"JWT_ALGORITHM '{value}' inválido. Valores aceitos: {valid}.")
    return normalized


def validate_non_empty_name(value: str, *, field_name: str) -> str:
    """Valida que um nome (app, banco, etc.) não é vazio nem apenas espaços."""
    if not value or not value.strip():
        raise ValueError(f"{field_name} não pode ser vazio.")
    return value.strip()


def validate_database_url(value: str) -> str:
    """Valida que a URL de banco de dados tem um esquema e um host reconhecíveis."""
    parsed = urlparse(value)
    if not parsed.scheme or "postgresql" not in parsed.scheme:
        raise ValueError(
            f"DATABASE_URL deve usar o esquema postgresql(+driver)://, recebido: '{value}'."
        )
    if not parsed.hostname:
        raise ValueError("DATABASE_URL deve conter um host válido.")
    return value
