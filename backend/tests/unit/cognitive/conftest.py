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
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.cognitive.models.cognitive_object import CognitiveObject
from app.cognitive.models.lineage_edge import LineageEdge
from app.cognitive.models.relationship import Relationship
from app.cognitive.models.transformation_record import TransformationRecord
from app.database.base import Base

_COGNITIVE_TABLES = [
    CognitiveObject.__table__,
    LineageEdge.__table__,
    TransformationRecord.__table__,
    Relationship.__table__,
]


@pytest.fixture
def cognitive_sqlite_engine():
    engine = create_engine("sqlite:///:memory:")

    # SQLite não impõe foreign keys por padrão (diferente de
    # PostgreSQL, usado em produção) — precisa ser habilitado por
    # conexão. Necessário a partir de E3.3 para que os testes de FK de
    # `LineageEdge` (parent_coid/child_coid -> cognitive_objects.id)
    # sejam realistas.
    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine, tables=_COGNITIVE_TABLES)
    yield engine
    Base.metadata.drop_all(engine, tables=_COGNITIVE_TABLES)
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
