"""Fixtures compartilhadas entre os testes."""

import pytest
from fastapi.testclient import TestClient

from pia_os.config import Settings
from pia_os.main import create_app


@pytest.fixture
def settings() -> Settings:
    """Configurações isoladas para o ambiente de teste."""
    return Settings(environment="test", debug=True)


@pytest.fixture
def client(settings: Settings) -> TestClient:
    """Cliente HTTP de teste apontando para uma app recém-criada."""
    app = create_app(settings=settings)
    return TestClient(app)
