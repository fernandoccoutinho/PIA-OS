"""
Fábrica de sessões e gerenciamento seguro de transações.

Expõe:
- `SessionLocal` / `AsyncSessionLocal`: fábricas de sessão (sync / async).
- `get_db` / `get_async_db`: dependencies do FastAPI (injeção por request).
- `session_scope`: context manager para uso fora de uma requisição HTTP
  (scripts, tarefas em background), com commit/rollback automáticos.

`engine` e `check_database_connection` são reexportados aqui por
compatibilidade com código das Entregas 2.1/2.2 (`app.database.session`
continua sendo um import válido).
"""

from collections.abc import AsyncGenerator, Generator
from contextlib import asynccontextmanager, contextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import Session, sessionmaker

from app.database.engine import async_engine, engine
from app.database.health import check_database_connection
from app.utils.logger import get_logger

logger = get_logger("app.database")

__all__ = [
    "AsyncSessionLocal",
    "SessionLocal",
    "async_engine",
    "check_database_connection",
    "engine",
    "get_async_db",
    "get_db",
    "session_scope",
]

SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
)


def get_db() -> Generator[Session, None, None]:
    """Dependency do FastAPI (sync): entrega uma sessão por requisição.

    Não faz commit automático — a camada que usa a sessão decide quando
    commitar (ver `app.repositories.unit_of_work.UnitOfWork` para o padrão
    recomendado). Em caso de exceção durante a requisição, reverte a
    sessão antes de fechá-la, para nunca deixar uma transação pendurada.
    """
    db = SessionLocal()
    try:
        yield db
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


async def get_async_db() -> AsyncGenerator[AsyncSession, None]:
    """Dependency do FastAPI (async) — preparada para uso futuro.

    Nenhum endpoint atual é async-first; esta dependency existe para que
    módulos futuros que precisem de I/O assíncrono não exijam retrabalho
    na camada de sessão. Mesma política de rollback-em-erro do `get_db`.
    """
    async with AsyncSessionLocal() as db:
        try:
            yield db
        except Exception:
            await db.rollback()
            raise


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    """Context manager transacional para uso fora do ciclo de request/response.

    Commita ao sair sem exceção; faz rollback automático em caso de erro;
    sempre fecha a sessão. Uso típico: scripts, tarefas agendadas.

        with session_scope() as db:
            ...  # commit automático ao final do bloco
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        logger.error("database_transaction_rolled_back")
        raise
    finally:
        db.close()


@asynccontextmanager
async def async_session_scope() -> AsyncGenerator[AsyncSession, None]:
    """Equivalente assíncrono de `session_scope` — preparado para uso futuro."""
    db = AsyncSessionLocal()
    try:
        yield db
        await db.commit()
    except Exception:
        await db.rollback()
        logger.error("database_transaction_rolled_back")
        raise
    finally:
        await db.close()
