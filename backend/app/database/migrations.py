"""
Wrapper programático sobre o Alembic.

Não substitui a CLI (`alembic revision`, `alembic upgrade`) — apenas
expõe as mesmas operações como funções Python, para uso em scripts,
tarefas de CI/CD ou (futuramente) um endpoint administrativo. A fonte de
verdade da configuração continua sendo `alembic.ini` + `alembic/env.py`.

Ver `docs/DATABASE.md` para o processo completo de migração.
"""

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from app.config.settings import settings
from app.utils.logger import get_logger

logger = get_logger("app.database.migrations")

_BACKEND_ROOT = Path(__file__).resolve().parents[2]


def get_alembic_config() -> Config:
    """Constrói a `Config` do Alembic apontando para a `DATABASE_URL` ativa."""
    config = Config(str(_BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(_BACKEND_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", settings.database_url)
    return config


def current_revision() -> str | None:
    """Retorna a revisão atualmente aplicada ao banco (None se nenhuma)."""
    from app.database.engine import engine

    with engine.connect() as connection:
        context = MigrationContext.configure(connection)
        return context.get_current_revision()


def head_revision() -> str | None:
    """Retorna a revisão mais recente disponível nos scripts de migração."""
    config = get_alembic_config()
    script = ScriptDirectory.from_config(config)
    return script.get_current_head()


def has_pending_migrations() -> bool:
    """True se a revisão do banco estiver atrás da head dos scripts."""
    return current_revision() != head_revision()


def upgrade(revision: str = "head") -> None:
    """Aplica migrações pendentes até `revision` (padrão: a mais recente)."""
    logger.info("migration_upgrade_started", extra={"target_revision": revision})
    command.upgrade(get_alembic_config(), revision)
    logger.info("migration_upgrade_completed", extra={"target_revision": revision})


def downgrade(revision: str) -> None:
    """Reverte migrações até `revision` (ex.: '-1' para a anterior)."""
    logger.warning("migration_downgrade_started", extra={"target_revision": revision})
    command.downgrade(get_alembic_config(), revision)
    logger.warning("migration_downgrade_completed", extra={"target_revision": revision})


def generate_revision(message: str, *, autogenerate: bool = True) -> None:
    """Gera um novo script de migração (equivalente a `alembic revision`)."""
    logger.info("migration_revision_generated", extra={"message": message})
    command.revision(get_alembic_config(), message=message, autogenerate=autogenerate)
