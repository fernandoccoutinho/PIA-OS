"""
Factories de dados de teste — geração de instâncias de modelos ORM.

Nenhum modelo de domínio existe ainda no PIA-OS — a factory abaixo
gera instâncias de `SampleModel` (o modelo de teste genérico usado pela
suíte de persistência/ORM desde os Módulos 2.3-2.4). O padrão (contador
incremental para garantir valores únicos entre chamadas) é o que
factories de modelos de domínio futuros devem seguir.
"""

import itertools

from tests.fixtures.database import SampleModel

_name_counter = itertools.count(1)


def make_sample_model(**overrides: object) -> SampleModel:
    """Cria uma `SampleModel` com um `name` único por padrão — qualquer
    campo pode ser sobrescrito via kwargs.

        make_sample_model()                  # name="sample-1", "sample-2", ...
        make_sample_model(name="específico")  # sobrescreve o default
    """
    defaults: dict[str, object] = {"name": f"sample-{next(_name_counter)}"}
    defaults.update(overrides)
    return SampleModel(**defaults)


def make_sample_models(count: int, **overrides: object) -> list[SampleModel]:
    """Cria `count` instâncias de `SampleModel`, cada uma com `name`
    único (a menos que `name` seja explicitamente sobrescrito, caso em
    que todas compartilham o mesmo valor — usar com cuidado)."""
    return [make_sample_model(**overrides) for _ in range(count)]
