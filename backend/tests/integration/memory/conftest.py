"""
Conftest de `tests/integration/memory/` (E4.1).

Mesma proteção de `tests/integration/cognitive/conftest.py` (E3.6.1d):
os testes de guarda de downgrade executam Alembic dentro do processo do
pytest, e `alembic/env.py` chama `fileConfig(...)` com o padrão
`disable_existing_loggers=True` — sem isolamento, isso desliga os
loggers da aplicação e quebra testes E1/E2 de logging coletados depois,
dependendo apenas da ordem de coleta.

A fixture é `autouse` para todo o diretório pela mesma razão de lá: a
garantia não deve depender de alguém lembrar de aplicá-la ao próximo
teste que exercitar migrações.
"""

import pytest

from tests.helpers.logging_state import preserved_logging_state


@pytest.fixture(autouse=True)
def isolate_process_logging_state():
    """Restaura o estado global de logging ao fim de cada teste deste
    diretório, inclusive quando o teste falha ou levanta a exceção
    semântica esperada da migração-guarda."""
    with preserved_logging_state():
        yield
