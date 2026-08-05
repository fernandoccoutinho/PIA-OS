from alembic.config import Config
from app.database import migrations


def test_get_alembic_config_points_to_backend_root():
    config = migrations.get_alembic_config()
    assert isinstance(config, Config)
    assert config.get_main_option("script_location").endswith("alembic")


def test_get_alembic_config_uses_active_database_url():
    from app.config.settings import settings

    config = migrations.get_alembic_config()
    assert config.get_main_option("sqlalchemy.url") == settings.database_url


def test_head_revision_is_none_when_no_migrations_exist():
    # Nenhuma migração foi gerada (proposital — Módulo 2.3 não cria
    # tabelas de domínio), então a head deve ser None.
    assert migrations.head_revision() is None
