"""
Conftest de `tests/integration/cognitive/` (E3.6.1d).

Os testes de guarda de downgrade executam Alembic dentro do processo do
pytest, e `alembic/env.py` chama `fileConfig(...)` com o padrão
`disable_existing_loggers=True`. Sem isolamento, isso desliga os
loggers da aplicação e os testes E1/E2 de logging coletados depois
falham — dependendo apenas da ordem de coleta.

A fixture abaixo é `autouse` para todo este diretório em vez de local
aos dois arquivos de guarda: qualquer teste cognitivo de integração
pode passar a exercitar migrações no futuro, e a garantia não deve
depender de alguém lembrar de aplicá-la. O custo é uma fotografia de
atributos por teste.

Escopo: exclusivamente `tests/**`. Nada aqui altera produção, Alembic
ou o logging real da aplicação.
"""

import pytest

from tests.helpers.logging_state import preserved_logging_state


@pytest.fixture(autouse=True)
def isolate_process_logging_state():
    """Restaura o estado global de logging ao fim de cada teste deste
    diretório, inclusive quando o teste falha ou levanta a exceção
    semântica esperada das migrações-guarda."""
    with preserved_logging_state():
        yield
