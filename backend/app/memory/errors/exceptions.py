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
from collections.abc import Iterable

from app.exceptions.base import PIAOSException
from app.memory.errors.codes import (
    PIA_8023_MEMORY_DOMAIN_NOT_FOUND,
    PIA_8024_MEMORY_DOMAIN_MEMBERSHIP_DUPLICATE,
    PIA_8025_MEMORY_DOMAIN_MEMBERSHIP_OBJECT_NOT_FOUND,
    PIA_8026_CONTEXT_UNKNOWN_DOMAIN_REFERENCE,
    PIA_8027_GOVERNANCE_POLICY_VERSION_EXISTS,
    PIA_8028_GOVERNANCE_POLICY_IMMUTABLE,
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


class ContextUnknownDomainReferenceError(PIAOSException):
    """Um `MemoryContext` referencia `MemoryDomain`(s) inexistente(s).

    Carrega o **conjunto** de ids desconhecidos, e não apenas o
    primeiro: um contexto pode declarar vários domínios, e reportar um
    por vez forçaria o chamador a N tentativas para descobrir N
    referências ruins.

    Distinção preservada (E4.2 §35): domínio ausente **não** é objeto
    cognitivo ausente. São diagnósticos diferentes e não se mascaram.
    """

    error_code = PIA_8026_CONTEXT_UNKNOWN_DOMAIN_REFERENCE

    def __init__(self, unknown_domain_ids: Iterable[uuid.UUID]) -> None:
        self.unknown_domain_ids = tuple(sorted(set(unknown_domain_ids), key=str))
        listados = ", ".join(str(d) for d in self.unknown_domain_ids)
        super().__init__(
            message=f"MemoryContext referencia domínio(s) inexistente(s): {listados}.",
            detail={"unknown_domain_ids": [str(d) for d in self.unknown_domain_ids]},
        )


class GovernancePolicyVersionExistsError(PIAOSException):
    """Tentativa de recriar uma versão já publicada (E4.3).

    Versões são imutáveis. Sobrescrever apagaria em silêncio a policy
    que fundamentou decisões passadas, e a pergunta "qual versão valia
    quando isto foi decidido?" deixaria de ter resposta.
    """

    error_code = PIA_8027_GOVERNANCE_POLICY_VERSION_EXISTS

    def __init__(self, policy_key: str, version: int) -> None:
        self.policy_key = policy_key
        self.version = version
        super().__init__(
            message=(
                f"A versão {version} da policy '{policy_key}' já existe e é imutável — "
                "crie uma versão nova."
            ),
            detail={"policy_key": policy_key, "version": version},
        )


class GovernancePolicyImmutableError(PIAOSException):
    """Uma versão publicada não pode ser alterada nem removida (E4.3.1).

    Mudança semântica cria versão nova. Sobrescrever apagaria a policy
    que fundamentou decisões passadas, e a pergunta "sob qual regra
    isto foi decidido?" deixaria de ter resposta.
    """

    error_code = PIA_8028_GOVERNANCE_POLICY_IMMUTABLE

    def __init__(self, policy_id: uuid.UUID | None, operation: str) -> None:
        self.policy_id = policy_id
        self.operation = operation
        super().__init__(
            message=(
                f"GovernancePolicy {policy_id} é imutável — operação '{operation}' "
                "recusada; publique uma nova versão."
            ),
            detail={"policy_id": str(policy_id) if policy_id else None, "operation": operation},
        )
