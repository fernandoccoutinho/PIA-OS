"""
Definição e detecção de ambiente de execução.

Fonte única de verdade para o enum `Environment`. Outros módulos de
configuração (`settings.py`, `config.py`) importam deste arquivo.
"""

from enum import StrEnum


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TESTING = "testing"
    STAGING = "staging"
    PRODUCTION = "production"


PRODUCTION_LIKE_ENVIRONMENTS = frozenset({Environment.STAGING, Environment.PRODUCTION})


def is_production_like(environment: Environment) -> bool:
    """Staging e Production compartilham exigências de segurança mais rígidas."""
    return environment in PRODUCTION_LIKE_ENVIRONMENTS


def parse_environment(raw: str) -> Environment:
    """Converte uma string arbitrária (case-insensitive) em `Environment`.

    Lança ValueError com mensagem clara se o valor não for reconhecido —
    usado tanto pela validação do Pydantic quanto pelo loader.
    """
    normalized = raw.strip().lower()
    try:
        return Environment(normalized)
    except ValueError as exc:
        valid = ", ".join(e.value for e in Environment)
        raise ValueError(f"Ambiente '{raw}' inválido. Valores aceitos: {valid}.") from exc
