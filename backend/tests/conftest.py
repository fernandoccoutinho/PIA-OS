"""
Conftest raiz da suíte (Módulo 2.10).

Reexporta as fixtures de `tests/fixtures/` — pytest descobre fixtures
por presença no namespace de um `conftest.py` na árvore de diretórios,
então importar aqui as torna disponíveis para todo `tests/unit/` e
`tests/integration/`, sem precisar de um `conftest.py` por subpasta.
"""

from tests.fixtures.application import client, client_no_lifespan  # noqa: F401
from tests.fixtures.database import (  # noqa: F401
    SampleModel,
    sqlite_engine,
    sqlite_session,
    sqlite_session_factory,
)
from tests.fixtures.settings import production_settings, test_settings  # noqa: F401
from tests.fixtures.users import fake_user_payload  # noqa: F401
