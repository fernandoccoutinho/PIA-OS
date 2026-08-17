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
    PIA_8032_CONSOLIDATION_VERIFICATION_FAILED,
    PIA_8033_RETRIEVAL_DUPLICATE_COID,
    PIA_8034_RETRIEVAL_CONTRACT_VIOLATION,
    PIA_8035_ACCESSIBILITY_POLICY_VERSION_EXISTS,
    PIA_8036_ACCESSIBILITY_POLICY_IMMUTABLE,
    PIA_8037_ACCESSIBILITY_TRANSITION_CONTRACT_VIOLATION,
    PIA_8038_ACCESSIBILITY_SUBJECT_NOT_FOUND,
    PIA_8039_ISOLATION_SCOPE_REQUIRED,
    PIA_8040_ISOLATION_CONTRACT_VIOLATION,
    PIA_8041_ERASURE_RECORD_IMMUTABLE,
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


class ConsolidationVerificationError(PIAOSException):
    """A verificação de pós-condição da consolidação falhou (`E4.5`).

    Levantada quando o recibo da porta E3 e o `PersistenceAssessment`
    da E4.4 discordam sobre o alvo. Carrega os motivos **todos de uma
    vez**: uma divergência raramente vem sozinha, e reportar a primeira
    obrigaria a auditoria a descobrir as demais uma execução por vez.

    Não repara, não apaga, não compensa. Sobe para que o rollback do
    chamador desfaça a consolidação inteira.
    """

    error_code = PIA_8032_CONSOLIDATION_VERIFICATION_FAILED

    def __init__(self, target_coid: uuid.UUID, reasons: tuple[str, ...]) -> None:
        self.target_coid = target_coid
        self.reasons = reasons
        super().__init__(
            message=(
                f"verificação de consolidação falhou para o alvo {target_coid}: "
                + "; ".join(reasons)
            ),
            detail={"target_coid": str(target_coid), "reasons": list(reasons)},
        )


class RetrievalDuplicateCoidError(PIAOSException):
    """A composição da vista produziu o mesmo COID mais de uma vez (`E4.6`).

    Diagnóstico explícito em vez de escolha silenciosa: a E4.6 não elege
    qual ocorrência apresentar.
    """

    error_code = PIA_8033_RETRIEVAL_DUPLICATE_COID

    def __init__(self, coid: uuid.UUID) -> None:
        self.coid = coid
        super().__init__(
            message=(
                f"COID {coid} apareceu mais de uma vez na composição da vista "
                "admissível — defeito de composição, não duplicação legítima"
            ),
            detail={"coid": str(coid)},
        )


class RetrievalContractViolationError(PIAOSException):
    """Pós-condição do Retrieval violada (`E4.6.1`).

    Carrega **todos** os motivos detectados, não o primeiro: uma
    resposta incoerente raramente diverge num só ponto, e reportar
    apenas o primeiro obrigaria a auditoria a descobrir os demais uma
    execução por vez.
    """

    error_code = PIA_8034_RETRIEVAL_CONTRACT_VIOLATION

    def __init__(self, reasons: tuple[str, ...]) -> None:
        self.reasons = reasons
        super().__init__(
            message="contrato do Retrieval violado: " + "; ".join(reasons),
            detail={"reasons": list(reasons)},
        )


class AccessibilityPolicyVersionExistsError(PIAOSException):
    """Já existe versão publicada com este `(policy_key, version)` (E4.7)."""

    error_code = PIA_8035_ACCESSIBILITY_POLICY_VERSION_EXISTS

    def __init__(self, policy_key: str, version: int) -> None:
        self.policy_key = policy_key
        self.version = version
        super().__init__(
            message=(
                f"AccessibilityPolicy {policy_key!r} versão {version} já existe — "
                "versões publicadas são imutáveis; publique uma versão nova"
            ),
            detail={"policy_key": policy_key, "version": version},
        )


class AccessibilityPolicyImmutableError(PIAOSException):
    """`UPDATE`/`DELETE` recusado numa versão publicada (E4.7)."""

    error_code = PIA_8036_ACCESSIBILITY_POLICY_IMMUTABLE

    def __init__(self, policy_id: uuid.UUID, *, operation: str) -> None:
        self.policy_id = policy_id
        self.operation = operation
        super().__init__(
            message=(
                f"{operation} recusado: AccessibilityPolicy {policy_id} já foi publicada "
                "e é imutável"
            ),
            detail={"policy_id": str(policy_id), "operation": operation},
        )


class AccessibilityTransitionContractViolationError(PIAOSException):
    """Pós-condição da transição de acessibilidade violada (E4.7).

    Carrega **todos** os motivos detectados: uma resposta incoerente
    raramente diverge num só ponto, e reportar apenas o primeiro
    obrigaria a auditoria a descobrir os demais uma execução por vez.
    """

    error_code = PIA_8037_ACCESSIBILITY_TRANSITION_CONTRACT_VIOLATION

    def __init__(self, reasons: tuple[str, ...]) -> None:
        self.reasons = reasons
        super().__init__(
            message="contrato de transição de acessibilidade violado: " + "; ".join(reasons),
            detail={"reasons": list(reasons)},
        )


class AccessibilitySubjectNotFoundError(PIAOSException):
    """Não existe `CognitiveObject` com o COID informado (E4.7)."""

    error_code = PIA_8038_ACCESSIBILITY_SUBJECT_NOT_FOUND

    def __init__(self, coid: uuid.UUID) -> None:
        self.coid = coid
        super().__init__(
            message=f"nenhum CognitiveObject com COID {coid}",
            detail={"coid": str(coid)},
        )


class IsolationScopeRequiredError(PIAOSException):
    """Pedido de recuperação isolada sem domínio explícito (E4.8)."""

    error_code = PIA_8039_ISOLATION_SCOPE_REQUIRED

    def __init__(self) -> None:
        super().__init__(
            message=(
                "recuperação isolada exige escopo de domínio explícito — um contexto "
                "sem domínio não é 'todos os domínios isolados', e tratá-lo assim "
                "seria a expansão de escopo que o isolamento impede"
            ),
            detail={"required": "context.domain_ids"},
        )


class IsolationContractViolationError(PIAOSException):
    """Fronteira do isolamento violada (E4.8).

    Carrega **todos** os motivos detectados: uma composição incoerente
    raramente diverge num só ponto, e reportar apenas o primeiro
    obrigaria a auditoria a descobrir os demais uma execução por vez.
    """

    error_code = PIA_8040_ISOLATION_CONTRACT_VIOLATION

    def __init__(self, reasons: tuple[str, ...]) -> None:
        self.reasons = reasons
        super().__init__(
            message="contrato de isolamento violado: " + "; ".join(reasons),
            detail={"reasons": list(reasons)},
        )


class ErasureRecordImmutableError(PIAOSException):
    """Um recibo de apagamento não pode ser alterado nem removido (`E4.9.5`).

    Levantada pelos eventos de mapper e pelo repositório. A terceira
    camada — a trigger no PostgreSQL — recusa antes de chegar aqui, e
    é a única que continua valendo em SQL bruto.

    Não existe correção de recibo. Ele registra o que foi observado
    numa tentativa material; observação nova é registro novo.

    ```text
    ERASING THE RECEIPT OF AN ERASURE = MAKING DESTRUCTION UNAUDITABLE
    ```
    """

    error_code = PIA_8041_ERASURE_RECORD_IMMUTABLE

    def __init__(self, record_id: uuid.UUID | None, operation: str) -> None:
        self.record_id = record_id
        self.operation = operation
        super().__init__(
            message=(
                f"ErasureRecord {record_id} é imutável — operação '{operation}' "
                "recusada; um recibo registra o que foi observado e não se reescreve."
            ),
            detail={"record_id": str(record_id) if record_id else None, "operation": operation},
        )
