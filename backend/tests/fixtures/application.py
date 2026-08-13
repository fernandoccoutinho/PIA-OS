"""
Fixtures de aplicação — cliente HTTP para testes de integração.

`client` usa `TestClient` como context manager de propósito — sem isso,
os eventos de startup/shutdown (`app.core.lifespan`) nunca disparam (foi
exatamente essa lacuna que baixou a cobertura de `lifespan.py` durante a
reorganização deste módulo — ver `tests/integration/api/test_application_lifespan.py`).

Disponibilizada para uso em testes de integração novos — os já existentes
que criam `TestClient(app)` diretamente no módulo continuam funcionando
sem alteração (não foram retroativamente migrados para esta fixture,
para não arriscar uma regressão numa suíte que já estava verde).
"""

from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient

from main import app as fastapi_app


@pytest.fixture
def client() -> Generator[TestClient, None, None]:
    """Cliente HTTP com o ciclo de vida da aplicação real ativado."""
    with TestClient(fastapi_app) as test_client:
        yield test_client


@pytest.fixture
def client_no_lifespan() -> TestClient:
    """Cliente sem `with` — não dispara startup/shutdown. Útil quando o
    teste quer isolar o comportamento de um endpoint da inicialização da
    aplicação (mais rápido, sem efeitos colaterais de logging de startup)."""
    return TestClient(fastapi_app)
