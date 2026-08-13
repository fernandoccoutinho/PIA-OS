from app.config.settings import Settings
from app.security.secrets import SecretsManager


def test_get_secret_key_returns_raw_value():
    manager = SecretsManager(Settings(secret_key="minha-chave-secreta"))
    assert manager.get_secret_key() == "minha-chave-secreta"


def test_get_database_url_returns_raw_value():
    url = "postgresql+psycopg://user:pw@host:5432/db"
    manager = SecretsManager(Settings(database_url=url))
    assert manager.get_database_url() == url


def test_masked_secret_key_never_shows_full_value():
    manager = SecretsManager(Settings(secret_key="minha-chave-secreta-longa"))
    masked = manager.get_masked_secret_key()
    assert "minha-chave-secreta-longa" not in masked
    assert masked.endswith("onga")


def test_masked_database_url_never_shows_full_value():
    url = "postgresql+psycopg://user:supersecretpw@host:5432/db"
    manager = SecretsManager(Settings(database_url=url))
    masked = manager.get_masked_database_url()
    assert "supersecretpw" not in masked
