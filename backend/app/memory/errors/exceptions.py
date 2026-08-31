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
    PIA_8042_RETENTION_POLICY_VERSION_EXISTS,
    PIA_8043_RETENTION_POLICY_IMMUTABLE,
    PIA_8044_APPROVAL_RECORD_NOT_USABLE,
    PIA_8045_APPROVAL_RECORD_IMMUTABLE,
    PIA_8046_APPROVAL_RECORD_PERSISTED_ROW_INVALID,
    PIA_8047_DESTRUCTIVE_EXECUTION_UNKNOWN_MATERIAL_STATE,
    PIA_8048_DESTRUCTIVE_EXECUTION_ADAPTER_CONTRACT_VIOLATION,
    PIA_8049_ERASURE_RECEIPT_NOT_PERSISTED,
    PIA_8050_VALIDATED_EXPERIENCE_CONFLICT,
    PIA_8051_VALIDATED_EXPERIENCE_IMMUTABLE,
)
from app.memory.models.approval_lifecycle_enums import ApprovalUsageRefusalReason
from app.memory.models.destructive_execution_enums import AdapterContractViolation
from app.memory.models.erasure_enums import ErasureOutcome
from app.memory.schemas.destructive_execution import PartialExecutionEvidence


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


class RetentionPolicyVersionExistsError(PIAOSException):
    """`UNIQUE(policy_key, version)` recusou a publicação (`E4.9.6`)."""

    error_code = PIA_8042_RETENTION_POLICY_VERSION_EXISTS

    def __init__(self, policy_key: str, version: int) -> None:
        self.policy_key = policy_key
        self.version = version
        super().__init__(
            message=(
                f"RetentionPolicy '{policy_key}' versão {version} já existe — "
                "publique a próxima versão; sobrescrever apagaria a regra que "
                "fundamentou avaliações passadas."
            ),
            detail={"policy_key": policy_key, "version": version},
        )


class RetentionPolicyImmutableError(PIAOSException):
    """Uma versão publicada não pode ser alterada nem removida (`E4.9.6`)."""

    error_code = PIA_8043_RETENTION_POLICY_IMMUTABLE

    def __init__(self, policy_id: uuid.UUID | None, operation: str) -> None:
        self.policy_id = policy_id
        self.operation = operation
        super().__init__(
            message=(
                f"RetentionPolicy {policy_id} é imutável — operação '{operation}' "
                "recusada; publique uma nova versão."
            ),
            detail={"policy_id": str(policy_id) if policy_id else None, "operation": operation},
        )


class ApprovalRecordNotUsableError(PIAOSException):
    """A aprovação não pôde ser consumida ou revogada (`E4.9.9.a`).

    ```text
    BOOLEAN_OUTCOME = FORBIDDEN
    ```

    O motivo é um vocabulário fechado. Distinguir "expirada" de "binding
    divergente" importa: a primeira é rotina, a segunda é sinal de que
    alguém pediu consumo com um contexto que não corresponde ao aprovado.
    """

    error_code = PIA_8044_APPROVAL_RECORD_NOT_USABLE

    def __init__(self, approval_id: uuid.UUID, reason: ApprovalUsageRefusalReason) -> None:
        self.approval_id = approval_id
        self.reason = reason
        super().__init__(
            message=(f"Aprovação {approval_id} não utilizável — motivo " f"'{reason.value}'."),
            detail={"approval_id": str(approval_id), "reason": reason.value},
        )


class ApprovalRecordImmutableError(PIAOSException):
    """Binding de aprovação não se reescreve e a trilha não se apaga
    (`E4.9.9.a`).

    ```text
    APPROVAL_TRAIL_IS_PERMANENT
    ```

    A trigger no PostgreSQL recusa antes de chegar aqui, e é a única
    camada que continua valendo em SQL bruto.
    """

    error_code = PIA_8045_APPROVAL_RECORD_IMMUTABLE

    def __init__(self, approval_id: uuid.UUID | None, operation: str) -> None:
        self.approval_id = approval_id
        self.operation = operation
        super().__init__(
            message=(
                f"ApprovalRecord {approval_id} é imutável — operação " f"'{operation}' recusada."
            ),
            detail={
                "approval_id": str(approval_id) if approval_id else None,
                "operation": operation,
            },
        )


class ApprovalRecordPersistedRowInvalidError(PIAOSException):
    """A linha persistida não reconstrói contrato válido (`E4.9.9.a`).

    ```text
    INVALID_ROW != USABLE_APPROVAL
    ```

    Falha controlada. Tolerar a linha produziria uma aprovação que os
    construtores públicos jamais teriam aceitado.
    """

    error_code = PIA_8046_APPROVAL_RECORD_PERSISTED_ROW_INVALID

    def __init__(self, approval_id: uuid.UUID, campo: str, causa: str) -> None:
        self.approval_id = approval_id
        self.campo = campo
        self.causa = causa
        super().__init__(
            message=(
                f"Linha persistida da aprovação {approval_id} é inválida no campo "
                f"'{campo}': {causa}"
            ),
            detail={"approval_id": str(approval_id), "field": campo, "cause": causa},
        )


class DestructiveExecutionUnknownMaterialStateError(PIAOSException):
    """A porta de efeito falhou e o estado material ficou ambíguo (`E4.9.9.d`).

    ```text
    EFFECT_EXCEPTION -> UNKNOWN_STATE, NEVER_INVENTED_RECEIPT
    CRASH_DURING_EFFECT_MAY_LEAVE_UNKNOWN_STATE = DECLARED
    ```

    Exceção, e não valor de retorno, porque um desfecho ignorável faria o
    caso mais grave passar como rotina. Carrega a evidência do que já era
    fato antes da ambiguidade — nunca uma inferência sobre o alvo em que
    ela ocorreu.

    A aprovação **permanece consumida**: o contrato é at-most-once, e
    reabri-la autorizaria segunda tentativa sobre estado desconhecido.
    """

    error_code = PIA_8047_DESTRUCTIVE_EXECUTION_UNKNOWN_MATERIAL_STATE

    def __init__(self, evidence: "PartialExecutionEvidence") -> None:
        if not isinstance(evidence, PartialExecutionEvidence):
            raise TypeError(
                "a evidência parcial é obrigatória e tipada — sem ela, o "
                "chamador não sabe o que já era fato quando o estado ficou ambíguo"
            )
        self.evidence = evidence
        super().__init__(
            message=(
                f"Estado material desconhecido na posição {evidence.failed_position} "
                f"do lote da aprovação {evidence.approval_id} — a porta de efeito "
                "levantou exceção e nenhum desfecho pode ser inferido."
            ),
            detail={
                "approval_id": str(evidence.approval_id),
                "failed_position": evidence.failed_position,
                "subject_coid": str(evidence.subject_coid),
                "attempts_observed": evidence.attempts_observed,
                "receipts_persisted": evidence.receipts_persisted,
                "targets_not_attempted": evidence.targets_not_attempted,
            },
        )


class DestructiveExecutionAdapterContractViolationError(PIAOSException):
    """O resultado da porta não corresponde ao pedido (`E4.9.9.d`).

    ```text
    RETURNED_RESULT != FACT_UNTIL_BOUND_TO_THE_REQUEST
    ```

    Distinta de `DestructiveExecutionUnknownMaterialStateError`: lá a
    porta falhou, aqui ela respondeu sobre outra aprovação, outro sujeito
    ou outra classe. Registrar o recibo mesmo assim gravaria o apagamento
    de um objeto a partir da observação de outro.
    """

    error_code = PIA_8048_DESTRUCTIVE_EXECUTION_ADAPTER_CONTRACT_VIOLATION

    def __init__(
        self,
        violation: AdapterContractViolation,
        evidence: "PartialExecutionEvidence",
    ) -> None:
        if not isinstance(violation, AdapterContractViolation):
            raise TypeError(
                "violation deve ser um AdapterContractViolation — texto livre "
                "não distingue as três incoerências possíveis"
            )
        if not isinstance(evidence, PartialExecutionEvidence):
            raise TypeError("a evidência parcial é obrigatória e tipada")
        self.violation = violation
        self.evidence = evidence
        super().__init__(
            message=(
                f"Adaptador de efeito devolveu resultado incoerente "
                f"('{violation.value}') na posição {evidence.failed_position} do "
                f"lote da aprovação {evidence.approval_id}."
            ),
            detail={
                "approval_id": str(evidence.approval_id),
                "violation": violation.value,
                "failed_position": evidence.failed_position,
                "subject_coid": str(evidence.subject_coid),
                "attempts_observed": evidence.attempts_observed,
                "receipts_persisted": evidence.receipts_persisted,
            },
        )


class ErasureReceiptNotPersistedError(PIAOSException):
    """O efeito foi observado e o recibo não commitou (`E4.9.9.d`).

    ```text
    NEVER_CLAIM_A_RECEIPT_THAT_DID_NOT_COMMIT
    NEVER_UNDO_AN_OBSERVED_EFFECT_ON_PAPER
    ```

    O desfecho observado entra na mensagem porque é **fato**: a tentativa
    material ocorreu e alguém a observou. O que não ocorreu foi a
    gravação do recibo, e nenhum `TargetAttempted` é construído — o
    resultado agregado só lista recibos cujo commit próprio terminou.
    """

    error_code = PIA_8049_ERASURE_RECEIPT_NOT_PERSISTED

    def __init__(
        self,
        outcome: ErasureOutcome,
        evidence: "PartialExecutionEvidence",
    ) -> None:
        if not isinstance(outcome, ErasureOutcome):
            raise TypeError("outcome deve ser um ErasureOutcome — a fonte única é a da E4.9.5")
        if not isinstance(evidence, PartialExecutionEvidence):
            raise TypeError("a evidência parcial é obrigatória e tipada")
        self.outcome = outcome
        self.evidence = evidence
        super().__init__(
            message=(
                f"Efeito observado ('{outcome.value}') na posição "
                f"{evidence.failed_position} do lote da aprovação "
                f"{evidence.approval_id}, mas o recibo não foi persistido."
            ),
            detail={
                "approval_id": str(evidence.approval_id),
                "observed_outcome": outcome.value,
                "failed_position": evidence.failed_position,
                "subject_coid": str(evidence.subject_coid),
                "attempts_observed": evidence.attempts_observed,
                "receipts_persisted": evidence.receipts_persisted,
            },
        )


class ValidatedExperienceConflictError(PIAOSException):
    """Mesmo `experience_id`, conteúdo canônico divergente (`E4.11`).

    ```text
    ZERO_OVERWRITE
    ```

    Nenhuma escrita ocorre: o registro existente permanece exatamente
    como estava, e quem chamou fica sabendo que a identidade já
    descreve outra validação.
    """

    error_code = PIA_8050_VALIDATED_EXPERIENCE_CONFLICT

    def __init__(self, experience_id: uuid.UUID, diverging_fields: tuple[str, ...]) -> None:
        if not isinstance(experience_id, uuid.UUID):
            raise TypeError("experience_id deve ser UUID")
        if not isinstance(diverging_fields, tuple) or not diverging_fields:
            raise ValueError(
                "diverging_fields deve ser uma tupla não vazia — um conflito que "
                "não diz o que divergiu não é acionável"
            )
        self.experience_id = experience_id
        self.diverging_fields = diverging_fields
        super().__init__(
            message=(
                f"A experiência validada {experience_id} já existe com conteúdo "
                f"diferente; nada foi sobrescrito."
            ),
            detail={
                "experience_id": str(experience_id),
                "diverging_fields": list(diverging_fields),
            },
        )


class ValidatedExperienceImmutableError(PIAOSException):
    """Tentativa de alterar ou remover um registro já persistido (`E4.11`).

    ```text
    APPEND_ONLY_IN_THREE_LAYERS
    ```
    """

    error_code = PIA_8051_VALIDATED_EXPERIENCE_IMMUTABLE

    def __init__(self, operation: str) -> None:
        if not isinstance(operation, str) or not operation.strip():
            raise ValueError("operation deve ser texto não vazio")
        self.operation = operation
        super().__init__(
            message=(f"validated_experiences é append-only: '{operation}' recusado."),
            detail={"operation": operation},
        )
