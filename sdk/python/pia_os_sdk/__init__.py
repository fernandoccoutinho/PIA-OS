"""
`pia-os-sdk` — SDK de REPRESENTAÇÃO do PIA-OS (E6.3).

```text
SDK_SOURCE_OF_TRUTH = FALSE
OPENAPI_SOURCE_OF_TRUTH = TRUE
E6_3 = REPRESENTATION_ONLY_SDK
```

O SDK representa as rotas que existem no OpenAPI autorizado da
Chain107-R1. Não inventa endpoint, não recalcula ciência, não normaliza
PIAP, não decide sobre erro e não tenta de novo. Quem decide é o
servidor; o cliente transporta.
"""

from pia_os_sdk.client import DEFAULT_TIMEOUT_SECONDS, PiaClient
from pia_os_sdk.errors import PiaApiError, PiaSdkError, PiaTransportError
from pia_os_sdk.models import OPENAPI_SNAPSHOT_SHA256

__version__ = "0.1.0"

__all__ = [
    "DEFAULT_TIMEOUT_SECONDS",
    "OPENAPI_SNAPSHOT_SHA256",
    "PiaApiError",
    "PiaClient",
    "PiaSdkError",
    "PiaTransportError",
    "__version__",
]
