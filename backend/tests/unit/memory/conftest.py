"""
Fixtures de `tests/unit/memory/` — sessão SQLite em memória usando o
`Base` REAL da aplicação, mesmo padrão de `tests/unit/cognitive/`.

Nota deliberada sobre o que este conftest importa: ele **importa
`app.cognitive`**, e isso é correto. A proibição de importar
`app.cognitive` vale para `app/memory/` (código de produção), onde ela
mantém a fronteira E3/E4 estrutural — e é verificada pelo gate `G17` da
E3.12, que varre exclusivamente `backend/app/`.

Os testes ficam fora de `app/` e precisam do modelo cognitivo real por
uma razão específica: a FK `memory_domain_memberships.coid →
cognitive_objects.id` só é exercitável de verdade se a tabela existir.
Testar a fronteira sem criar a tabela do outro lado provaria menos, não
mais.
"""

from collections.abc import Generator

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from app.cognitive.models.cognitive_object import CognitiveObject
from app.database.base import Base
from app.memory.models.governance_policy import GovernancePolicy
from app.memory.models.memory_domain import MemoryDomain
from app.memory.models.memory_domain_membership import MemoryDomainMembership

_MEMORY_TABLES = [
    CognitiveObject.__table__,
    MemoryDomain.__table__,
    MemoryDomainMembership.__table__,
    GovernancePolicy.__table__,
]


@pytest.fixture
def memory_sqlite_engine():
    engine = create_engine("sqlite:///:memory:")

    # SQLite não impõe foreign keys por padrão — precisa ser habilitado
    # por conexão. Sem isto, os testes de FK deste módulo (COID
    # inexistente, domínio inexistente) passariam por acidente, o que
    # seria pior do que não tê-los.
    @event.listens_for(engine, "connect")
    def _enable_sqlite_foreign_keys(dbapi_connection, connection_record):  # noqa: ANN001
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    Base.metadata.create_all(engine, tables=_MEMORY_TABLES)
    yield engine
    Base.metadata.drop_all(engine, tables=_MEMORY_TABLES)
    engine.dispose()


@pytest.fixture
def memory_sqlite_session_factory(memory_sqlite_engine) -> sessionmaker:
    return sessionmaker(
        bind=memory_sqlite_engine, autocommit=False, autoflush=False, expire_on_commit=False
    )


@pytest.fixture
def memory_session(memory_sqlite_session_factory) -> Generator[Session, None, None]:
    session = memory_sqlite_session_factory()
    try:
        yield session
    finally:
        session.close()
