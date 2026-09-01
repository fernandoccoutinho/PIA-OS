"""Isolamento de ambiente para os testes unitários de configuração.

`Settings` (pydantic-settings) lê variáveis de ambiente e o arquivo `.env`.
Estes testes afirmam o comportamento de validação a partir dos DEFAULTS e dos
argumentos explícitos passados a `Settings(...)` — pressupõem, portanto, um
ambiente limpo, como o pytest puro em que foram escritos e no qual passam.

Sob o `docker-compose.test.yml` (que injeta `SECRET_KEY`, `DATABASE_URL` e
`ENVIRONMENT` no processo) ou na presença de um `.env` local, esses valores
vazariam para dentro de `Settings()` e mascarariam as validações — por exemplo,
uma `SECRET_KEY` de ambiente faria `Settings(environment=PRODUCTION)` deixar de
acusar o segredo default. Este fixture autouse remove o vazamento, sem tocar em
nenhuma asserção.
"""

import pytest

from app.config.settings import Settings

_VARS_DE_CONFIG = (
    "SECRET_KEY",
    "DATABASE_URL",
    "DEBUG",
    "ENVIRONMENT",
    "DB_HOST",
    "DB_PORT",
    "DB_NAME",
    "DB_USER",
    "DB_PASSWORD",
    "APP_NAME",
    "LOG_LEVEL",
    "LOG_FORMAT",
)


@pytest.fixture(autouse=True)
def _ambiente_de_config_limpo(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove env vars de configuração e desliga o `.env` para cada teste."""
    for var in _VARS_DE_CONFIG:
        monkeypatch.delenv(var, raising=False)
        monkeypatch.delenv(var.lower(), raising=False)
    # Desliga a leitura do arquivo `.env` (montado no container de teste).
    monkeypatch.setitem(Settings.model_config, "env_file", None)
