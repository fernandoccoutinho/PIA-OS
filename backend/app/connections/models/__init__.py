"""
Modelos ORM do kernel de conexões (`E7.4-1`).

Importar este pacote registra as nove tabelas em `Base.metadata`. Mesmo
papel de `app.orchestration.models`, e a mesma razão para `alembic/env.py`
importá-lo: sem o registro, a guarda de drift compararia contra um
metadata incompleto e o `autogenerate` não veria as tabelas.

```text
KERNEL_NÃO_IMPORTA_MCP
```

Nada aqui importa transporte, rede, credencial ou adaptador. Remover um
adaptador no futuro não pode quebrar o kernel, e a única forma de
garantir isso é o kernel nunca ter dependido dele.
"""

from app.connections.models.capability import (
    CapabilitySnapshot,
    EntitlementClaim,
    EvaluationEvidence,
)
from app.connections.models.catalog import (
    AccessProvider,
    ModelFamily,
    ModelRelease,
    ProviderFamily,
)
from app.connections.models.connection_execution_receipt import ConnectionExecutionReceipt
from app.connections.models.connection_profile import ConnectionProfile
from app.connections.models.enums import (
    AVAILABLE_CONNECTION_METHODS,
    BASELINE_METHOD_STATE,
    TERMINAL_CONNECTION_STATES,
    CapabilitySource,
    ConnectionMethod,
    ConnectionState,
    EntitlementOrigin,
    EntitlementState,
    EvidenceCategory,
    GenericEndpointType,
    ModelAttestationLevel,
    SelectionMode,
)

__all__ = [
    "AVAILABLE_CONNECTION_METHODS",
    "BASELINE_METHOD_STATE",
    "TERMINAL_CONNECTION_STATES",
    "AccessProvider",
    "CapabilitySnapshot",
    "CapabilitySource",
    "ConnectionExecutionReceipt",
    "ConnectionMethod",
    "ConnectionProfile",
    "ConnectionState",
    "EntitlementClaim",
    "EntitlementOrigin",
    "EntitlementState",
    "EvaluationEvidence",
    "EvidenceCategory",
    "GenericEndpointType",
    "ModelAttestationLevel",
    "ModelFamily",
    "ModelRelease",
    "ProviderFamily",
    "SelectionMode",
]
