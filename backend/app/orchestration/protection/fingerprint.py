"""
Identidades versionadas da decisão e da aplicação (`E7.4-1 B1a`).

```text
decision_fingerprint = identidade da DECISÃO
binding_sha256       = identidade da APLICAÇÃO, por gate e por tentativa
```

Canonicalização única para os dois:

```text
JSON com chaves ordenadas · UTF-8 · sem espaços · enums por VALOR ·
UUID minúsculo · tuplas na ordem original · None explícito
```

Este módulo **não lê relógio, ambiente nem banco** — mesma disciplina de
`schemas/envelope.py` (`e71b14`). Um hash que dependesse do instante em que é
calculado não identificaria coisa alguma.

## Por que nenhuma lista de campos é escrita à mão

```text
HAND_WRITTEN_COUNT = COUNT_THAT_DRIFTS
COUNT_DERIVED_FROM_HANDWRITTEN_LIST != SCHEMA_DERIVED_MANIFEST
```

`binding_sha256` deriva os dez campos de `dataclasses.fields(GovernanceBinding)`,
e o `decision_fingerprint` recebe um mapa cujo conteúdo o adaptador deriva de
`dataclasses.fields(GovernanceResolution)`. Um campo novo na E4 entra no hash
sozinho; um campo removido some sozinho. Nenhum dos dois depende de alguém
lembrar de editar uma lista paralela.
"""

import dataclasses
import hashlib
import json
import uuid
from collections.abc import Mapping, Sequence, Set
from datetime import UTC, datetime
from enum import Enum

from app.orchestration.protection.binding import GovernanceBinding
from app.orchestration.protection.vocabulary import (
    BINDING_ALGO_VERSION,
    FINGERPRINT_ALGO_VERSION,
)

_ALGO_KEY = "__algo_version__"
"""A versão do algoritmo entra **no material hasheado**.

Guardá-la só na coluna deixaria dois algoritmos capazes de produzir o mesmo
digest para entradas diferentes, e a coluna seria uma etiqueta sobre um valor
que não a conhece.
"""


def _canonico(valor: object) -> object:
    """Reduz um valor a algo que `json.dumps` serializa deterministicamente.

    `Enum` vira `.value`, `UUID` vira texto minúsculo, `datetime` é
    normalizado para UTC antes do ISO — dois instantes iguais escritos em
    fusos diferentes precisam produzir o mesmo digest, e `isoformat()` cru
    produziria dois. Sequências preservam a ordem (ela carrega intenção);
    conjuntos são ordenados pela própria forma canônica, porque um conjunto
    não tem ordem para preservar.
    """
    if isinstance(valor, Enum):
        return _canonico(valor.value)
    if valor is None or isinstance(valor, bool | int | float | str):
        return valor
    if isinstance(valor, uuid.UUID):
        return str(valor).lower()
    if isinstance(valor, datetime):
        if valor.tzinfo is None or valor.utcoffset() is None:
            raise ValueError("datetime sem fuso não é canonicalizável")
        return valor.astimezone(UTC).isoformat()
    if isinstance(valor, Mapping):
        return {str(chave): _canonico(item) for chave, item in valor.items()}
    if isinstance(valor, Set):
        return sorted(
            (_canonico(item) for item in valor),
            key=lambda item: json.dumps(item, sort_keys=True, ensure_ascii=False),
        )
    if isinstance(valor, Sequence):
        return [_canonico(item) for item in valor]
    raise TypeError(f"valor não canonicalizável: {type(valor).__name__}")


def serializar_canonicamente(campos: Mapping[str, object]) -> bytes:
    """JSON canônico em UTF-8, sem espaços e com chaves ordenadas."""
    return json.dumps(
        _canonico(dict(campos)),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def _digest(campos: Mapping[str, object], versao: str) -> str:
    if _ALGO_KEY in campos:
        raise ValueError(f"{_ALGO_KEY} é reservado à versão do algoritmo")
    material = dict(campos)
    material[_ALGO_KEY] = versao
    return hashlib.sha256(serializar_canonicamente(material)).hexdigest()


def calcular_decision_fingerprint(campos: Mapping[str, object]) -> str:
    """Identidade da decisão, sobre a resolução INTEIRA mais a evidência.

    Não inclui gate, Schedule, etapa nem tentativa: a mesma decisão aplicada
    em duas posições tem **um** fingerprint e **dois** bindings — é assim que
    se prova que a classificação ocorreu uma vez por snapshot e foi
    reutilizada, em vez de recalculada quatro vezes.

    ```text
    MESMA DECISÃO -> MESMO decision_fingerprint
    GATES DIFERENTES -> binding_sha256 DIFERENTES
    ```
    """
    if not campos:
        raise ValueError("decision_fingerprint exige as entradas da resolução")
    return _digest(campos, FINGERPRINT_ALGO_VERSION)


def campos_do_binding(binding: GovernanceBinding) -> dict[str, object]:
    """Os dez campos, extraídos do próprio dataclass congelado."""
    return {campo.name: getattr(binding, campo.name) for campo in dataclasses.fields(binding)}


def calcular_binding_sha256(binding: GovernanceBinding) -> str:
    """Identidade da aplicação: todos os dez campos, sem exceção."""
    return _digest(campos_do_binding(binding), BINDING_ALGO_VERSION)
