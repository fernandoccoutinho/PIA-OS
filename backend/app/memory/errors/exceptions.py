"""
Exceções de domínio da camada de memória (E4.1).

Toda exceção herda de `PIAOSException`, como em E3 — nenhum sistema
paralelo de exceptions é criado.

Nota sobre o que **não** é exceção aqui: "objeto com zero domínios" é
resultado válido e retorna lista vazia. Um COID fora de todo domínio
existe plenamente (`ZERO DOMAIN MEMBERSHIP != NONEXISTENCE`), e tratar
ausência de classificação como erro seria exatamente a inferência que
este módulo existe para proibir.
"""

import uuid

from app.exceptions.base import PIAOSException
from app.memory.errors.codes import (
    PIA_8023_MEMORY_DOMAIN_NOT_FOUND,
    PIA_8024_MEMORY_DOMAIN_MEMBERSHIP_DUPLICATE,
    PIA_8025_MEMORY_DOMAIN_MEMBERSHIP_OBJECT_NOT_FOUND,
)


class MemoryDomainNotFoundError(PIAOSException):
    """O `MemoryDomain` referenciado não existe (E4.1)."""

    error_code = PIA_8023_MEMORY_DOMAIN_NOT_FOUND

    def __init__(self, domain_id: uuid.UUID) -> None:
        self.domain_id = domain_id
        super().__init__(
            message=f"MemoryDomain {domain_id} não existe.",
            detail={"domain_id": str(domain_id)},
        )


class MemoryDomainMembershipDuplicateError(PIAOSException):
    """O par `(domain_id, coid)` já está registrado (E4.1)."""

    error_code = PIA_8024_MEMORY_DOMAIN_MEMBERSHIP_DUPLICATE

    def __init__(self, domain_id: uuid.UUID, coid: uuid.UUID) -> None:
        self.domain_id = domain_id
        self.coid = coid
        super().__init__(
            message=f"O COID {coid} já pertence ao MemoryDomain {domain_id}.",
            detail={"domain_id": str(domain_id), "coid": str(coid)},
        )


class MemoryDomainMembershipObjectNotFoundError(PIAOSException):
    """O `CognitiveObject` referenciado pelo `coid` não existe (E4.1).

    Levantado a partir da violação de FK que resta depois de o domínio
    já ter sido confirmado — ver `MemoryDomainMembershipRepository`.
    """

    error_code = PIA_8025_MEMORY_DOMAIN_MEMBERSHIP_OBJECT_NOT_FOUND

    def __init__(self, coid: uuid.UUID) -> None:
        self.coid = coid
        super().__init__(
            message=f"Nenhum CognitiveObject com COID {coid}.",
            detail={"coid": str(coid)},
        )
