import pytest
from pydantic import ValidationError

from app.config.settings import Environment, Settings, get_settings


def test_settings_loads_with_defaults():
    settings = Settings()
    assert settings.app_name == "PIA-OS Backend"
    assert settings.environment in list(Environment)


def test_get_settings_is_cached():
    a = get_settings()
    b = get_settings()
    assert a is b


def test_production_flags():
    settings = Settings(environment=Environment.PRODUCTION)
    assert settings.is_production is True
    assert settings.is_testing is False


def test_staging_flags():
    settings = Settings(environment=Environment.STAGING)
    assert settings.is_staging is True
    assert settings.is_production_like is True


def test_development_is_not_production_like():
    settings = Settings(environment=Environment.DEVELOPMENT)
    assert settings.is_production_like is False


def test_grouped_settings_reflect_flat_fields():
    settings = Settings(app_name="Custom", log_level="DEBUG", log_format="text")
    assert settings.app.name == "Custom"
    assert settings.log.level == "DEBUG"
    assert settings.log.format == "text"
    assert settings.log_json is False  # compat: text format => log_json False


def test_database_url_composed_from_parts_when_db_host_set(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings = Settings(
        db_host="myhost", db_port=5433, db_name="mydb", db_user="me", db_password="pw"
    )
    assert settings.database_url == "postgresql+psycopg://me:pw@myhost:5433/mydb"


def test_explicit_database_url_takes_precedence_over_parts(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    settings = Settings(
        database_url="postgresql+psycopg://explicit@explicit-host:5432/explicitdb",
        db_host="ignored-host",
    )
    assert "explicit-host" in settings.database_url


def test_invalid_log_level_raises():
    with pytest.raises(ValidationError):
        Settings(log_level="NOT_A_LEVEL")


def test_invalid_log_format_raises():
    with pytest.raises(ValidationError):
        Settings(log_format="xml")


def test_invalid_db_port_raises():
    with pytest.raises(ValidationError):
        Settings(db_port=99999)


def test_invalid_database_url_scheme_raises():
    with pytest.raises(ValidationError):
        Settings(database_url="mysql://user:pw@host:3306/db")


def test_empty_app_name_raises():
    with pytest.raises(ValidationError):
        Settings(app_name="   ")
