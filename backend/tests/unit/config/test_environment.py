import pytest

from app.config.environment import Environment, is_production_like, parse_environment


def test_parse_environment_accepts_lowercase():
    assert parse_environment("production") is Environment.PRODUCTION


def test_parse_environment_is_case_insensitive():
    assert parse_environment("PRODUCTION") is Environment.PRODUCTION
    assert parse_environment("  Staging  ") is Environment.STAGING


def test_parse_environment_rejects_unknown_value():
    with pytest.raises(ValueError, match="inválido"):
        parse_environment("nao-existe")


def test_is_production_like():
    assert is_production_like(Environment.PRODUCTION) is True
    assert is_production_like(Environment.STAGING) is True
    assert is_production_like(Environment.DEVELOPMENT) is False
    assert is_production_like(Environment.TESTING) is False


def test_all_four_environments_exist():
    values = {e.value for e in Environment}
    assert values == {"development", "testing", "staging", "production"}
