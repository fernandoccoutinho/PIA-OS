"""
Fixtures de banco de dados compartilhadas — camada `tests/fixtures/`
(Módulo 2.10). Antes viviam em `app/tests/conftest.py`; movidas para cá
como parte da reorganização, sem alterar comportamento.

`SampleModel` é um modelo ORM exclusivo de teste (não é uma entidade do
domínio do PIA-OS) — existe apenas para validar `BaseRepository` e
`UnitOfWork` de forma independente de qualquer módulo de negócio futuro.

Os testes de repositório/UoW usam SQLite em memória (não o PostgreSQL do
Módulo 2.1) justamente para não exigir um banco real no ambiente de CI/
sandbox — são testes de infraestrutura genérica, não de integração com
PostgreSQL especificamente (essa cobertura é responsabilidade dos testes
de `engine.py`/`health.py`, que apontam para o `DATABASE_URL` real).
"""

from collections.abc import Generator

import pytest
from sqlalchemy import Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


# Base declarativa SEPARADA de `app.database.base.Base` de propósito: se
# usássemos o Base real da aplicação, esta tabela de teste apareceria no
# metadata consultado pelo `alembic revision --autogenerate`, gerando uma
# migração indesejada para uma tabela que só existe nos testes.
class _TestBase(DeclarativeBase):
    pass


class SampleModel(_TestBase):
    """Modelo ORM de uso exclusivo dos testes de infraestrutura."""

    __tablename__ = "test_sample_model"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)


@pytest.fixture
def sqlite_engine():
    engine = create_engine("sqlite:///:memory:")
    _TestBase.metadata.create_all(engine, tables=[SampleModel.__table__])
    yield engine
    _TestBase.metadata.drop_all(engine, tables=[SampleModel.__table__])
    engine.dispose()


@pytest.fixture
def sqlite_session_factory(sqlite_engine) -> sessionmaker:
    return sessionmaker(
        bind=sqlite_engine, autocommit=False, autoflush=False, expire_on_commit=False
    )


@pytest.fixture
def sqlite_session(sqlite_session_factory) -> Generator[Session, None, None]:
    session = sqlite_session_factory()
    try:
        yield session
    finally:
        session.close()
