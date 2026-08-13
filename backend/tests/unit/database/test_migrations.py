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


def test_head_revision_returns_the_latest_migration_script_revision():
    # Correção E3.1/LIB-01: este teste antes assumia "nenhuma migração
    # existe" (verdade só até o Módulo 2.3, que não cria tabelas de
    # domínio). A primeira migração real do projeto nasceu em E3.1
    # (`cognitive_objects`, revisão 257dc8c23ab1) — o teste agora
    # valida o contrato real da função (retorna a head dos scripts
    # existentes), não mais um estado transitório do repositório.
    head = migrations.head_revision()
    assert head is not None
    assert isinstance(head, str)
    assert len(head) > 0


def test_head_revision_is_none_for_an_empty_script_directory(tmp_path, monkeypatch):
    """Cobre o contrato original (`None` quando não há scripts de
    migração) de forma isolada do estado real do repositório — usa um
    `script_location` vazio via `tmp_path`, em vez de depender de o
    projeto não ter nenhuma migração gerada (o que deixou de ser
    verdade a partir de E3.1)."""
    empty_alembic_dir = tmp_path / "alembic"
    empty_versions_dir = empty_alembic_dir / "versions"
    empty_versions_dir.mkdir(parents=True)

    def _fake_get_alembic_config():
        from alembic.config import Config

        config = Config()
        config.set_main_option("script_location", str(empty_alembic_dir))
        return config

    monkeypatch.setattr(migrations, "get_alembic_config", _fake_get_alembic_config)
    assert migrations.head_revision() is None
