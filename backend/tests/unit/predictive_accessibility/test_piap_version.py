"""
Política de versão do contrato PIAP (`E5.a`).

```text
VERSION_POLICY = EXPLICIT_ALLOWLIST
FAIL_OPEN = FORBIDDEN
```
"""

import pytest

from app.predictive_accessibility.errors.codes import PIA_8052_PIAP_UNSUPPORTED_VERSION
from app.predictive_accessibility.errors.exceptions import PiapUnsupportedVersionError
from app.predictive_accessibility.piap.enums import PiapContractVersion
from app.predictive_accessibility.piap.version import (
    SUPPORTED_VERSIONS,
    require_supported_version,
)

pytestmark = pytest.mark.unit


def test_allowlist_contem_apenas_v1_0() -> None:
    assert SUPPORTED_VERSIONS == (PiapContractVersion.V1_0,)
    assert PiapContractVersion.V1_0.value == "1.0"


def test_versao_suportada_atravessa() -> None:
    assert require_supported_version(PiapContractVersion.V1_0) is PiapContractVersion.V1_0


@pytest.mark.parametrize("valor", ["1.0", "0.9", "2.0", "1", 1.0, None, object()])
def test_valor_fora_do_enum_falha_fechada(valor: object) -> None:
    """String equivalente também falha: a conversão pertence ao desserializador."""
    with pytest.raises(PiapUnsupportedVersionError, match="deve ser PiapContractVersion"):
        require_supported_version(valor)


def test_membro_do_enum_fora_da_allowlist_falha_fechada(monkeypatch: pytest.MonkeyPatch) -> None:
    """O segundo caminho de recusa: membro válido, allowlist vazia.

    Existe para que a mensagem de \"não suportada\" seja exercitada, e não
    apenas a de tipo errado. Uma versão futura entra no enum antes de
    entrar na allowlist, e é exatamente esse intervalo que este teste
    cobre.
    """
    monkeypatch.setattr("app.predictive_accessibility.piap.version.SUPPORTED_VERSIONS", ())
    with pytest.raises(PiapUnsupportedVersionError, match="não suportada"):
        require_supported_version(PiapContractVersion.V1_0)


def test_codigo_de_erro_e_o_da_camada() -> None:
    with pytest.raises(PiapUnsupportedVersionError) as erro:
        require_supported_version("2.0")
    assert erro.value.error_code is PIA_8052_PIAP_UNSUPPORTED_VERSION
    assert erro.value.error_code.code == "PIA-8052"


def test_allowlist_e_tuple_imutavel() -> None:
    assert isinstance(SUPPORTED_VERSIONS, tuple)
