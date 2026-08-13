"""
Fixtures de `tests/unit/cognitive/` — sessão SQLite em memória usando o
`Base` REAL da aplicação (não uma `DeclarativeBase` paralela), mesmo
padrão de `tests/unit/models/test_mixins.py`/`test_base_model.py`:
`CognitiveObject` é um modelo de domínio real, não um modelo exclusivo
de teste, então registrar sua tabela no `Base` real e criar apenas ela
via `Base.metadata.create_all(..., tables=[...])` é o padrão correto
(diferente de `tests/fixtures/database.py`, que usa uma Base paralela
propositalmente só para `SampleModel`, que não é uma entidade real).
"""

from collections.abc import Generator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.cognitive.models.cognitive_object import CognitiveObject
from app.database.base import Base


@pytest.fixture
def cognitive_sqlite_engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[CognitiveObject.__table__])
    yield engine
    Base.metadata.drop_all(engine, tables=[CognitiveObject.__table__])
    engine.dispose()


@pytest.fixture
def cognitive_sqlite_session_factory(cognitive_sqlite_engine) -> sessionmaker:
    return sessionmaker(
        bind=cognitive_sqlite_engine, autocommit=False, autoflush=False, expire_on_commit=False
    )


@pytest.fixture
def cognitive_session(cognitive_sqlite_session_factory) -> Generator[Session, None, None]:
    session = cognitive_sqlite_session_factory()
    try:
        yield session
    finally:
        session.close()
