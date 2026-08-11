"""
Fixtures de configuração — instâncias de `Settings` prontas para testes.
"""

import pytest

from app.config.settings import Settings


@pytest.fixture
def test_settings() -> Settings:
    """Settings com defaults de ambiente de teste (debug ativo, sem
    exigências de produção)."""
    return Settings(environment="testing", debug=True)


@pytest.fixture
def production_settings() -> Settings:
    """Settings com uma configuração de produção válida — útil para
    testar comportamento estrito (headers, CORS, validação) sem
    precisar montar os campos obrigatórios em cada teste."""
    return Settings(
        environment="production",
        debug=False,
        secret_key="a-real-production-secret",
        database_url="postgresql+psycopg://prod_user:prod_pw@prod-host:5432/prod_db",
    )
