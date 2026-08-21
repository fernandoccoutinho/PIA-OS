"""Isolamento do estado global de logging nos testes de migração E5.l.

O Alembic usa ``fileConfig`` com ``disable_existing_loggers=True``. Como os
testes deste diretório exercitam upgrade e downgrade dentro do processo do
pytest, cada teste deve devolver o logging ao estado observado na entrada.
"""

import pytest

from tests.helpers.logging_state import preserved_logging_state


@pytest.fixture(autouse=True)
def isolate_process_logging_state():
    """Impede que a execução real do Alembic contamine testes posteriores."""
    with preserved_logging_state():
        yield
