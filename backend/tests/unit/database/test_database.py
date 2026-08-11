from app.database.base import Base
from app.database.engine import _async_database_url, async_engine, engine
from app.database.session import AsyncSessionLocal, SessionLocal


def test_engine_is_configured():
    assert engine is not None
    assert str(engine.url).startswith("postgresql")


def test_async_engine_is_configured():
    assert async_engine is not None
    assert "asyncpg" in str(async_engine.url)


def test_async_url_derivation_from_psycopg():
    assert _async_database_url("postgresql+psycopg://u:p@h:5432/d") == (
        "postgresql+asyncpg://u:p@h:5432/d"
    )


def test_async_url_derivation_is_idempotent_for_asyncpg():
    url = "postgresql+asyncpg://u:p@h:5432/d"
    assert _async_database_url(url) == url


def test_session_factory_creates_session():
    session = SessionLocal()
    try:
        assert session.is_active
    finally:
        session.close()


def test_async_session_factory_is_configured():
    assert AsyncSessionLocal is not None


def test_declarative_base_exists():
    assert hasattr(Base, "metadata")


def test_engine_pool_settings_are_applied():
    from app.config.settings import settings

    assert engine.pool.size() == settings.database_pool_size
    assert engine.pool._recycle == settings.database_pool_recycle
