"""
Exceções de domínio do LIB-01 (CognitiveObject + Object Repository).

Toda exceção de domínio de E3 herda de `PIAOSException` (§17 do módulo
E3.1) — nenhum sistema paralelo de exceptions é criado.
"""

import uuid

from app.cognitive.errors.codes import (
    PIA_8001_IDENTITY_IMMUTABLE,
    PIA_8002_CLID_ALREADY_SET,
)
from app.exceptions.base import PIAOSException


class CognitiveObjectIdentityImmutableError(PIAOSException):
    """O COID (`id`) de um `CognitiveObject` já persistido não pode ser
    reatribuído."""

    error_code = PIA_8001_IDENTITY_IMMUTABLE

    def __init__(self, current_id: uuid.UUID | None, attempted_id: uuid.UUID | None) -> None:
        self.current_id = current_id
        self.attempted_id = attempted_id
        super().__init__(
            message=(
                f"COID {current_id} não pode ser reatribuído para {attempted_id} "
                "— identidade de CognitiveObject é permanente após persistência."
            ),
            detail={"current_id": str(current_id), "attempted_id": str(attempted_id)},
        )


class CognitiveObjectClidAlreadySetError(PIAOSException):
    """O `clid` de um `CognitiveObject` já foi atribuído e não pode ser
    sobrescrito por esta via nesta fase (LIB-03 CLID Manager ainda não
    existe)."""

    error_code = PIA_8002_CLID_ALREADY_SET

    def __init__(
        self,
        coid: uuid.UUID | None,
        current_clid: uuid.UUID,
        attempted_clid: uuid.UUID | None,
    ) -> None:
        self.coid = coid
        self.current_clid = current_clid
        self.attempted_clid = attempted_clid
        super().__init__(
            message=(
                f"CLID de CognitiveObject {coid} já é {current_clid} — não pode ser "
                f"sobrescrito para {attempted_clid} fora do CLID Manager (E3.3)."
            ),
            detail={
                "coid": str(coid),
                "current_clid": str(current_clid),
                "attempted_clid": str(attempted_clid) if attempted_clid else None,
            },
        )
