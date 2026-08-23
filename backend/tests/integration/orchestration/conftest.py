"""
Conftest de `tests/integration/orchestration/` (E7.1).

Mesma proteção — e mesma causa **medida** — de
`tests/integration/security/conftest.py` (E6.2): as provas de round trip
da migration executam Alembic dentro do processo do pytest, e
`alembic/env.py` chama `fileConfig(...)` com `disable_existing_loggers=
True`. Sem isolamento, isso desliga os loggers da aplicação e reprova
testes E1/E2 coletados depois.

```text
GLOBAL_LOGGING_STATE = PROCESS_WIDE
PASS_ISOLATED != FULL_SUITE_PASS
```

O defeito é do diretório NOVO que suja o estado, não dos testes antigos
que o encontram sujo. `autouse` para que a garantia não dependa de alguém
lembrar de aplicá-la ao próximo teste que rodar migração.
"""

import pytest

from tests.helpers.logging_state import preserved_logging_state


@pytest.fixture(autouse=True)
def isolate_process_logging_state():
    """Restaura o estado global de logging ao fim de cada teste, inclusive
    quando o teste falha."""
    with preserved_logging_state():
        yield
