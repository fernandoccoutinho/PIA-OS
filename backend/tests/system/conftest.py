"""
Conftest de `tests/system/` (`E4.9.9.d`).

Mesma proteção de `tests/integration/cognitive/conftest.py` (E3.6.1d) e
de `tests/integration/memory/conftest.py` (E4.1), e pela mesma razão
**medida**: a validação prática executa Alembic dentro do processo do
pytest, e `alembic/env.py` chama `fileConfig(...)` com o padrão
`disable_existing_loggers=True`. Sem isolamento, isso desliga os
loggers da aplicação e quebra doze testes E1/E2 coletados depois —
número que esta fatia mediu antes de acrescentar o arquivo.

```text
GLOBAL_LOGGING_STATE = PROCESS_WIDE
TEST_ORDER != TEST_INDEPENDENCE
```

`autouse` para todo o diretório pela mesma razão de lá: a garantia não
deve depender de alguém lembrar de aplicá-la ao próximo teste que
exercitar migrações.
"""

import pytest

from tests.helpers.logging_state import preserved_logging_state


@pytest.fixture(autouse=True)
def isolate_process_logging_state():
    """Restaura o estado global de logging ao fim de cada teste deste
    diretório, inclusive quando o teste falha."""
    with preserved_logging_state():
        yield
