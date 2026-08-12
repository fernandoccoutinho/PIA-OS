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


def pytest_collection_modifyitems(config, items):
    """Aplica os markers `unit`/`integration` (declarados em pytest.ini)
    automaticamente, com base na pasta de cada teste, em vez de exigir
    que cada arquivo declare `pytestmark` manualmente. Sem isto, os
    markers existiam apenas na configuração e `pytest -m unit` /
    `pytest -m integration` não selecionavam nenhum teste.

    `tests/test_infrastructure.py` (testes da própria infra de testes —
    factories/helpers/fixtures, sem TestClient nem múltiplas camadas)
    é tratado como unit pelo mesmo critério usado no resto da suíte.
    """
    for item in items:
        path = str(item.fspath)
        if "/tests/integration/" in path:
            item.add_marker("integration")
        elif "/tests/unit/" in path or path.endswith("/tests/test_infrastructure.py"):
            item.add_marker("unit")
