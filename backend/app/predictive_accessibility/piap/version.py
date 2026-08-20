"""
Política de compatibilidade de versão do contrato PIAP (`E5.a`).

```text
VERSION_POLICY = EXPLICIT_ALLOWLIST
FAIL_OPEN = FORBIDDEN
NEWER_VERSION != COMPATIBLE_BY_DEFAULT
OLDER_VERSION != READABLE_BY_DEFAULT
```

Compatibilidade é decidida por **lista literal**, nunca por comparação de
ordem. Inferir que a versão maior é compatível é a forma silenciosa de
fail-open, e uma versão menor não é automaticamente legível só por ser
menor.

Precedente medido: `SynchronizationManager._validate_envelope` (E3)
rejeita formato ou versão desconhecidos **antes** de qualquer escrita,
com a justificativa de que um pacote ilegível não pode aplicar nada.
"""

from app.predictive_accessibility.errors.exceptions import PiapUnsupportedVersionError
from app.predictive_accessibility.piap.enums import PiapContractVersion

SUPPORTED_VERSIONS: tuple[PiapContractVersion, ...] = (PiapContractVersion.V1_0,)
"""Allowlist literal. Acrescentar versão é decisão de etapa, não de runtime."""


def require_supported_version(value: object) -> PiapContractVersion:
    """Devolve a versão quando ela está na allowlist; falha fechada se não.

    Aceita apenas um membro de `PiapContractVersion`. Uma `str` com o
    mesmo texto **não** é aceita aqui: a conversão de texto para membro
    pertence ao desserializador, que é a única fronteira onde texto entra
    no sistema. Aceitar as duas formas em todo lugar tornaria impossível
    dizer onde a conversão aconteceu.

    ```text
    STRING_EQUIVALENT != ENUM_MEMBER_OUTSIDE_DESERIALIZER
    ```
    """
    if not isinstance(value, PiapContractVersion):
        raise PiapUnsupportedVersionError(
            "contract_version deve ser PiapContractVersion, recebido " f"{type(value).__name__}"
        )
    if value not in SUPPORTED_VERSIONS:
        raise PiapUnsupportedVersionError(
            f"versão de contrato PIAP não suportada: {value.value!r}; "
            f"suportadas: {[v.value for v in SUPPORTED_VERSIONS]}"
        )
    return value
