import os

import pytest

from app.config.environment import Environment
from app.config.loader import detect_environment, resolve_env_file


@pytest.fixture(autouse=True)
def _clean_environment_var():
    original = {k: os.environ.get(k) for k in ("ENVIRONMENT", "APP_ENV")}
    yield
    for key, value in original.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def test_detect_environment_defaults_to_development(monkeypatch):
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.delenv("APP_ENV", raising=False)
    assert detect_environment() is Environment.DEVELOPMENT


def test_detect_environment_reads_environment_var(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "staging")
    assert detect_environment() is Environment.STAGING


def test_detect_environment_falls_back_to_app_env(monkeypatch):
    monkeypatch.delenv("ENVIRONMENT", raising=False)
    monkeypatch.setenv("APP_ENV", "production")
    assert detect_environment() is Environment.PRODUCTION


def test_resolve_env_file_returns_none_when_nothing_exists(tmp_path):
    result = resolve_env_file(Environment.DEVELOPMENT, root=tmp_path)
    assert result is None


def test_resolve_env_file_prefers_environment_specific_file(tmp_path):
    (tmp_path / ".env").write_text("APP_NAME=default\n")
    (tmp_path / ".env.testing").write_text("APP_NAME=testing-specific\n")
    result = resolve_env_file(Environment.TESTING, root=tmp_path)
    assert result is not None
    assert result.name == ".env.testing"


def test_resolve_env_file_prefers_local_override(tmp_path):
    (tmp_path / ".env.testing").write_text("APP_NAME=testing\n")
    (tmp_path / ".env.testing.local").write_text("APP_NAME=testing-local\n")
    result = resolve_env_file(Environment.TESTING, root=tmp_path)
    assert result is not None
    assert result.name == ".env.testing.local"


def test_resolve_env_file_falls_back_to_default_env(tmp_path):
    (tmp_path / ".env").write_text("APP_NAME=default\n")
    result = resolve_env_file(Environment.PRODUCTION, root=tmp_path)
    assert result is not None
    assert result.name == ".env"
