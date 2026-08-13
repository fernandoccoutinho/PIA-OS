import pytest

from app.config.config import ConfigurationError, validate_environment
from app.config.environment import Environment
from app.config.settings import Settings


def test_development_with_defaults_passes_validation():
    settings = Settings(environment=Environment.DEVELOPMENT)
    validate_environment(settings)  # não deve lançar


def test_production_with_default_secret_key_fails():
    settings = Settings(environment=Environment.PRODUCTION, debug=False)
    with pytest.raises(ConfigurationError, match="SECRET_KEY"):
        validate_environment(settings)


def test_production_with_debug_enabled_fails():
    settings = Settings(
        environment=Environment.PRODUCTION,
        secret_key="a-real-production-secret",
        debug=True,
    )
    with pytest.raises(ConfigurationError, match="DEBUG"):
        validate_environment(settings)


def test_production_with_default_database_credentials_fails():
    settings = Settings(
        environment=Environment.PRODUCTION,
        secret_key="a-real-production-secret",
        debug=False,
        database_url="postgresql+psycopg://pia_user:pia_password@db:5432/pia_os",
    )
    with pytest.raises(ConfigurationError, match="DATABASE_URL"):
        validate_environment(settings)


def test_production_with_proper_configuration_passes():
    settings = Settings(
        environment=Environment.PRODUCTION,
        secret_key="a-real-production-secret",
        debug=False,
        database_url="postgresql+psycopg://prod_user:prod_pw@prod-host:5432/prod_db",
    )
    validate_environment(settings)  # não deve lançar


def test_staging_has_the_same_hardening_as_production():
    settings = Settings(environment=Environment.STAGING, debug=False)
    with pytest.raises(ConfigurationError, match="SECRET_KEY"):
        validate_environment(settings)


def test_configuration_error_message_lists_all_problems_at_once():
    settings = Settings(environment=Environment.PRODUCTION, debug=True)
    with pytest.raises(ConfigurationError) as exc_info:
        validate_environment(settings)
    message = str(exc_info.value)
    assert "SECRET_KEY" in message
    assert "DEBUG" in message


def test_production_with_secret_key_entirely_absent_from_environment_fails(monkeypatch):
    """Variável ausente (não apenas com valor padrão explícito) também deve falhar.

    Simula o cenário real de deploy: SECRET_KEY nunca foi definida em produção
    (nem no .env, nem no ambiente do processo) — Settings() cai no default e
    a validação deve recusar a inicialização com mensagem clara.
    """
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.setenv("ENVIRONMENT", "production")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://prod:pw@prod-host:5432/prod_db")
    settings = Settings()
    with pytest.raises(ConfigurationError, match="SECRET_KEY"):
        validate_environment(settings)
