"""
`avaliar_conformidade` — avaliação **pura** de conformidade (`E4.10`).

```text
COMPLIANCE  = estado/ação × policy
COMPLIANCE != INTEGRITY
COMPLIANCE != GOVERNANCE_DECISION
COMPLIANCE != REPAIR
COMPLIANCE != LEARNING
REPAIR_IMPLEMENTED = NO
```

Detecta, descreve, cita a política e a versão, apresenta evidência. Não
decide acesso, não altera patrimônio, não altera vistas, não altera
políticas, não executa retenção nem apagamento, não consome aprovação
destrutiva, não chama o executor destrutivo, não aprende e não repara.

## Função, não classe

Sem estado, sem `__init__`, sem sessão, sem repositório — precedente
literal de `avaliar_retencao`. Um manager com `__init__(session)`
convidaria a consultar o banco lá dentro, e ler patrimônio não é
responsabilidade desta fronteira: tudo entra por argumento.

## O relógio é injetado, e é obrigatório

```text
CLOCK_INJECTED = REQUIRED
```

`datetime.now()` interno tornaria a função impura e o teste dependente
do relógio da máquina. Sem default, porque um default seria `now()`
disfarçado.

## Recusa em vez de negação retroativa

Governança decide **antes**; conformidade constata **depois**. Que uma
operação não tivesse regra que a admitisse não a torna negada
retroativamente — mas é fato observável, e `COMPLIANCE-GOV-002` existe
para que ele seja visto sem ser convertido em negação.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime

from app.core.error_codes import ErrorSeverity
from app.memory.models.compliance_enums import (
    AssessmentInformationState,
    CausalEvidencePresence,
    ComplianceCode,
    ComplianceOutcome,
    ComplianceSubjectKind,
    MissingObservation,
    ObservedOperationState,
    PolicyKind,
    PolicyWindowState,
)
from app.memory.models.governance_enums import CognitiveOperation, GovernanceEffect
from app.memory.models.retention_assessment_enums import RetentionAssessmentDecision
from app.memory.models.target_resolution_enums import LegacyProtectionState
from app.memory.schemas.accessibility import ACCESSIBILITY_STATE_TOKENS, AccessibilityRule
from app.memory.schemas.compliance import (
    SUJEITO_POR_POLITICA,
    ComplianceFinding,
    ComplianceReport,
    ComplianceSubjectRef,
    PolicyReference,
    ReportEvidence,
)
from app.memory.schemas.governance import GovernanceRule
from app.memory.schemas.retention import RetentionRule
from app.memory.services.retention_evaluator import RetentionCandidate, avaliar_retencao

CAUSALMENTE_EXTINTO = "causally_extinct"

FAMILIA_DE_REGRA: dict[PolicyKind, type] = {
    PolicyKind.GOVERNANCE: GovernanceRule,
    PolicyKind.ACCESSIBILITY: AccessibilityRule,
    PolicyKind.RETENTION: RetentionRule,
}
"""Qual família de regra cada política admite.

Enumerada literalmente. Uma política de acessibilidade cujas regras
fossem de governança avaliaria dimensões que a E4.7 deliberadamente
manteve fora dela — e produziria uma segunda resposta para a pergunta
que a E4.3 já responde.
"""


def _validar_instante(nome: str, valor: object) -> datetime:
    if not isinstance(valor, datetime):
        raise TypeError(f"{nome} deve ser datetime, recebido {type(valor).__name__}")
    if valor.tzinfo is None:
        raise ValueError(
            f"{nome} deve ser timezone-aware: um instante ingênuo daria resultado "
            "dependente do fuso da máquina"
        )
    return valor


@dataclass(frozen=True)
class ComplianceSubject:
    """O que foi avaliado — entrada, não projeção.

    `domain_id` é opcional no tipo e **obrigatório** para retenção: o
    alcance de uma regra de retenção pode depender do conjunto de
    domínios, e avaliar sem ele produziria um `OUT_OF_SCOPE` que apenas
    reflete a ausência do dado.
    """

    kind: ComplianceSubjectKind
    subject_coid: uuid.UUID
    domain_id: uuid.UUID | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.kind, ComplianceSubjectKind):
            raise TypeError(
                f"kind deve ser um ComplianceSubjectKind, recebido " f"{type(self.kind).__name__}"
            )
        if not isinstance(self.subject_coid, uuid.UUID):
            raise TypeError("subject_coid deve ser UUID")
        if self.domain_id is not None and not isinstance(self.domain_id, uuid.UUID):
            raise TypeError("domain_id deve ser UUID ou None")
        if self.kind is ComplianceSubjectKind.RETENTION_CANDIDATE and self.domain_id is None:
            raise ValueError(
                "candidato de retenção exige domain_id — o alcance de uma regra pode "
                "depender do domínio, e avaliar sem ele produziria um fora-de-escopo "
                "que apenas reflete a ausência do dado"
            )

    def to_ref(self) -> ComplianceSubjectRef:
        """Projeção segura para o relatório."""
        return ComplianceSubjectRef(
            kind=self.kind, subject_coid=self.subject_coid, domain_id=self.domain_id
        )


@dataclass(frozen=True)
class EvaluatedPolicy:
    """A política avaliada, com suas regras e janela de vigência.

    A janela é de início **inclusivo** e fim **exclusivo**, idêntica à
    da E4.9.9.c. Duas leituras da mesma janela dariam dois desfechos
    para o mesmo fato.
    """

    kind: PolicyKind
    policy_id: uuid.UUID
    policy_key: str
    policy_version: int
    effective_from: datetime
    effective_until: datetime | None
    rules: tuple[GovernanceRule | AccessibilityRule | RetentionRule, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.kind, PolicyKind):
            raise TypeError(f"kind deve ser um PolicyKind, recebido {type(self.kind).__name__}")
        if not isinstance(self.policy_id, uuid.UUID):
            raise TypeError("policy_id deve ser UUID")
        if not isinstance(self.policy_key, str) or not self.policy_key.strip():
            raise ValueError("policy_key deve ser texto não vazio")
        if isinstance(self.policy_version, bool) or not isinstance(self.policy_version, int):
            raise TypeError("policy_version deve ser int")
        if self.policy_version < 1:
            raise ValueError("policy_version deve ser >= 1")

        _validar_instante("effective_from", self.effective_from)
        if self.effective_until is not None:
            _validar_instante("effective_until", self.effective_until)
            if self.effective_until <= self.effective_from:
                raise ValueError(
                    "effective_until deve ser posterior a effective_from — janela "
                    "vazia ou invertida não é janela"
                )

        if not isinstance(self.rules, tuple):
            raise TypeError("rules deve ser tuple — `list` perderia imutabilidade")
        esperada = FAMILIA_DE_REGRA[self.kind]
        identificadores: set[str] = set()
        for indice, regra in enumerate(self.rules):
            if not isinstance(regra, esperada):
                raise TypeError(
                    f"rules[{indice}] é {type(regra).__name__} e a política "
                    f"{self.kind.value} admite apenas {esperada.__name__} — misturar "
                    "famílias avaliaria dimensões que a política não tem"
                )
            if regra.rule_id in identificadores:
                raise ValueError(
                    f"rule_id repetido: {regra.rule_id!r} — a ordem de declaração "
                    "passaria a mudar o resultado"
                )
            identificadores.add(regra.rule_id)

    def to_ref(self) -> PolicyReference:
        return PolicyReference(
            kind=self.kind,
            policy_id=self.policy_id,
            policy_key=self.policy_key,
            policy_version=self.policy_version,
        )

    def window_at(self, instante: datetime) -> PolicyWindowState:
        if instante < self.effective_from:
            return PolicyWindowState.BEFORE_WINDOW
        if self.effective_until is not None and instante >= self.effective_until:
            return PolicyWindowState.AFTER_WINDOW
        return PolicyWindowState.EFFECTIVE


@dataclass(frozen=True)
class GovernedOperationObservation:
    """O que se observou sobre uma operação governada.

    ```text
    PRESCRIPTION != FACT
    ADMISSION    != OBLIGATION_TO_EXECUTE
    ```

    `observed_state` é `ObservedOperationState`, não `GovernanceEffect`:
    aquele diz o que a política prescreve, este diz o que aconteceu.
    """

    operation: CognitiveOperation
    observed_state: ObservedOperationState
    actor_ref: str | None = None
    purpose: str | None = None
    domain_ids: tuple[uuid.UUID, ...] = field(default=())

    def __post_init__(self) -> None:
        if not isinstance(self.operation, CognitiveOperation):
            raise TypeError("operation deve ser um CognitiveOperation")
        if not isinstance(self.observed_state, ObservedOperationState):
            raise TypeError(
                "observed_state deve ser um ObservedOperationState — `bool` não "
                "distinguiria 'não executou' de 'ninguém olhou'"
            )
        for nome, valor in (("actor_ref", self.actor_ref), ("purpose", self.purpose)):
            if valor is not None and not isinstance(valor, str):
                raise TypeError(f"{nome} deve ser str ou None")
        if not isinstance(self.domain_ids, tuple):
            raise TypeError("domain_ids deve ser tuple")
        for indice, identificador in enumerate(self.domain_ids):
            if not isinstance(identificador, uuid.UUID):
                raise TypeError(f"domain_ids[{indice}] deve ser UUID")


@dataclass(frozen=True)
class AccessibilityStateObservation:
    """A transição de acessibilidade observada.

    A aresta é **exata**: `declared_source → current_state`. Avaliar só
    o estado de destino perderia de qual estado se veio, que é
    justamente o que a regra da E4.7 restringe.
    """

    current_state: str
    declared_source: str | None = None
    causal_evidence: CausalEvidencePresence = CausalEvidencePresence.NOT_OBSERVED

    def __post_init__(self) -> None:
        if not isinstance(self.current_state, str):
            raise TypeError("current_state deve ser str")
        if self.current_state not in ACCESSIBILITY_STATE_TOKENS:
            raise ValueError(
                f"current_state {self.current_state!r} está fora do vocabulário da E3 "
                f"{sorted(ACCESSIBILITY_STATE_TOKENS)}"
            )
        if self.declared_source is not None:
            if not isinstance(self.declared_source, str):
                raise TypeError("declared_source deve ser str ou None")
            if self.declared_source not in ACCESSIBILITY_STATE_TOKENS:
                raise ValueError(
                    f"declared_source {self.declared_source!r} está fora do "
                    f"vocabulário da E3 {sorted(ACCESSIBILITY_STATE_TOKENS)}"
                )
        if not isinstance(self.causal_evidence, CausalEvidencePresence):
            raise TypeError("causal_evidence deve ser um CausalEvidencePresence")


@dataclass(frozen=True)
class RetentionAgeObservation:
    """O que se observou sobre um candidato de retenção.

    `assessment_information` responde à pergunta que a política de fato
    faz depois da elegibilidade: a avaliação exigida aconteceu?

    ```text
    AGE >= MINIMUM_AGE != VIOLATION_BY_PERMANENCE
    ASSESS_AND_INFORM  != DELETE
    ```
    """

    anchor_at: datetime | None
    legacy_protection_state: LegacyProtectionState
    assessment_information: AssessmentInformationState = AssessmentInformationState.NOT_OBSERVED

    def __post_init__(self) -> None:
        if self.anchor_at is not None:
            _validar_instante("anchor_at", self.anchor_at)
        if not isinstance(self.legacy_protection_state, LegacyProtectionState):
            raise TypeError("legacy_protection_state deve ser um LegacyProtectionState")
        if not isinstance(self.assessment_information, AssessmentInformationState):
            raise TypeError("assessment_information deve ser um AssessmentInformationState")


ComplianceObservation = (
    GovernedOperationObservation | AccessibilityStateObservation | RetentionAgeObservation
)
"""União **fechada** das observações admitidas.

Uma por família de política, em correspondência imposta pelo construtor
da avaliação. Não há observação genérica: uma seria avaliável por
qualquer política, e nenhuma das três matrizes saberia respondê-la.
"""

OBSERVACAO_POR_POLITICA: dict[PolicyKind, type] = {
    PolicyKind.GOVERNANCE: GovernedOperationObservation,
    PolicyKind.ACCESSIBILITY: AccessibilityStateObservation,
    PolicyKind.RETENTION: RetentionAgeObservation,
}


def avaliar_conformidade(
    *,
    subject: ComplianceSubject,
    policy: EvaluatedPolicy,
    observation: ComplianceObservation,
    evaluated_at: datetime,
) -> ComplianceReport:
    """Avalia **um** sujeito contra **uma** versão de **uma** política.

    Função pura: mesma entrada, mesma saída, sem relógio interno, sem
    I/O, sem escrita, sem commit, sem efeito.

    ## Precedência comum às três famílias

    ```text
    1. janela de vigência          -> POLICY_NOT_APPLICABLE
    2. observação faltante         -> INSUFFICIENT_INFORMATION
    3. alcance das regras          -> POLICY_NOT_APPLICABLE
    4. semântica da família        -> COMPLIANT | VIOLATION_CONFIRMED
    ```

    A janela vem primeiro porque uma política que não vigorava não tem
    o que dizer sobre o fato — nem sequer que faltou observá-lo.
    """
    _validar_instante("evaluated_at", evaluated_at)
    if not isinstance(subject, ComplianceSubject):
        raise TypeError("subject deve ser um ComplianceSubject")
    if not isinstance(policy, EvaluatedPolicy):
        raise TypeError("policy deve ser um EvaluatedPolicy")

    esperado = SUJEITO_POR_POLITICA[policy.kind]
    if subject.kind is not esperado:
        raise ValueError(
            f"política {policy.kind.value} avalia sujeito {esperado.value}, recebido "
            f"{subject.kind.value}"
        )
    esperada = OBSERVACAO_POR_POLITICA[policy.kind]
    if not isinstance(observation, esperada):
        raise TypeError(
            f"política {policy.kind.value} exige {esperada.__name__}, recebido "
            f"{type(observation).__name__}"
        )
    janela = policy.window_at(evaluated_at)
    if janela is not PolicyWindowState.EFFECTIVE:
        return _relatorio(
            ComplianceOutcome.POLICY_NOT_APPLICABLE, subject, policy, evaluated_at, janela
        )

    if isinstance(observation, GovernedOperationObservation):
        return _avaliar_governanca(subject, policy, observation, evaluated_at)
    if isinstance(observation, AccessibilityStateObservation):
        return _avaliar_acessibilidade(subject, policy, observation, evaluated_at)
    return _avaliar_retencao(subject, policy, observation, evaluated_at)


# ----------------------------------------------------------------------
# Governança — ação observada × permissão declarada
# ----------------------------------------------------------------------


def _avaliar_governanca(
    subject: ComplianceSubject,
    policy: EvaluatedPolicy,
    observation: GovernedOperationObservation,
    evaluated_at: datetime,
) -> ComplianceReport:
    """Matriz da família `GOVERNANCE`.

    ```text
    DENY  + EXECUTED                 -> COMPLIANCE-GOV-001
    vigente sem regra + EXECUTED     -> COMPLIANCE-GOV-002
    DENY  + NOT_EXECUTED             -> COMPLIANT
    ADMIT + EXECUTED | NOT_EXECUTED  -> COMPLIANT
    só ADMIT   + NOT_OBSERVED        -> COMPLIANT
    algum DENY + NOT_OBSERVED        -> INSUFFICIENT_INFORMATION
    sem regra  + NOT_OBSERVED        -> INSUFFICIENT_INFORMATION
    ```

    `ADMIT + NOT_EXECUTED` é conforme, e a linha é deliberada:
    **admissão é permissão, não obrigação de executar**. Tratar o não
    uso de uma permissão como desvio transformaria a política num
    agendador.

    ## Por que as regras são resolvidas ANTES de tratar a não observação

    ```text
    MISSING_OBSERVATION_MATTERS_ONLY_WHERE_IT_CHANGES_THE_RESULT
    ```

    A primeira versão devolvia `INSUFFICIENT_INFORMATION` para toda
    `NOT_OBSERVED`, antes mesmo de saber quais regras alcançavam a
    operação. Mas quando **todas** as regras aplicáveis admitem, os dois
    estados possíveis — executado e não executado — são conformes, e a
    observação que falta não muda o desfecho. Declarar insuficiência ali
    pediria um dado que não decide nada.

    Onde alguma regra nega, a observação decide: executado é violação,
    não executado é conforme. E sem regra aplicável ela também decide,
    porque executado produz `GOV-002` e não executado é
    `POLICY_NOT_APPLICABLE`. Nesses dois casos a insuficiência é real.
    """
    aplicaveis = tuple(
        regra
        for regra in policy.rules
        if isinstance(regra, GovernanceRule)
        and regra.matches(
            operation=observation.operation,
            domain_ids=frozenset(observation.domain_ids),
            actor_ref=observation.actor_ref,
            purpose=observation.purpose,
        )
    )
    negacoes = tuple(regra for regra in aplicaveis if regra.effect is GovernanceEffect.DENY)
    identificadores = tuple(sorted(regra.rule_id for regra in aplicaveis))

    if observation.observed_state is ObservedOperationState.NOT_OBSERVED:
        if aplicaveis and not negacoes:
            return _relatorio(
                ComplianceOutcome.COMPLIANT,
                subject,
                policy,
                evaluated_at,
                PolicyWindowState.EFFECTIVE,
                regras=identificadores,
            )
        return _relatorio(
            ComplianceOutcome.INSUFFICIENT_INFORMATION,
            subject,
            policy,
            evaluated_at,
            PolicyWindowState.EFFECTIVE,
            faltantes=(MissingObservation.OBSERVED_OPERATION_STATE,),
        )

    executou = observation.observed_state is ObservedOperationState.EXECUTED

    if not aplicaveis:
        # `NO_MATCH = NOT_APPLICABLE` decide a AUTORIZAÇÃO na E4.3. Aqui
        # o fato já ocorreu sob política vigente, e vê-lo não o converte
        # em negação retroativa — por isso código próprio.
        if executou:
            return _relatorio_com_violacao(
                subject,
                policy,
                evaluated_at,
                ComplianceCode.GOVERNANCE_OPERATION_EXECUTED_WITHOUT_RULE,
                ErrorSeverity.WARNING,
                regras=(),
            )
        return _relatorio(
            ComplianceOutcome.POLICY_NOT_APPLICABLE,
            subject,
            policy,
            evaluated_at,
            PolicyWindowState.EFFECTIVE,
        )

    if negacoes and executou:
        # DENY_OVERRIDES, idêntico à E4.3: uma restrição que some porque
        # outra regra permite não é restrição.
        return _relatorio_com_violacao(
            subject,
            policy,
            evaluated_at,
            ComplianceCode.GOVERNANCE_OPERATION_EXECUTED_AGAINST_DENY,
            ErrorSeverity.ERROR,
            regras=tuple(sorted(regra.rule_id for regra in negacoes)),
        )
    return _relatorio(
        ComplianceOutcome.COMPLIANT,
        subject,
        policy,
        evaluated_at,
        PolicyWindowState.EFFECTIVE,
        regras=identificadores,
    )


# ----------------------------------------------------------------------
# Acessibilidade — aresta exata observada × transição permitida
# ----------------------------------------------------------------------


def _avaliar_acessibilidade(
    subject: ComplianceSubject,
    policy: EvaluatedPolicy,
    observation: AccessibilityStateObservation,
    evaluated_at: datetime,
) -> ComplianceReport:
    """Matriz da família `ACCESSIBILITY`.

    ```text
    declared_source ausente                    -> INSUFFICIENT_INFORMATION
    extinção + evidência NOT_OBSERVED          -> INSUFFICIENT_INFORMATION
    extinção + evidência ABSENT                -> COMPLIANCE-ACC-002
    aresta com DENY                            -> COMPLIANCE-ACC-001
    aresta sem regra aplicável                 -> COMPLIANCE-ACC-003
    aresta com ALLOW                           -> COMPLIANT
    ```

    A insuficiência precede a violação: sem origem declarada não há
    aresta, e sem aresta não há o que comparar. Concluir conformidade
    nesse estado seria afirmar o que ninguém observou.
    """
    # O estreitamento é ESTRUTURAL, não um `cast`: os dois ramos de
    # insuficiência retornam, e só depois deles `origem` é `str`.
    extinto = observation.current_state == CAUSALMENTE_EXTINTO
    sem_evidencia = extinto and (observation.causal_evidence is CausalEvidencePresence.NOT_OBSERVED)
    origem = observation.declared_source
    if origem is None:
        faltantes: tuple[MissingObservation, ...] = (MissingObservation.DECLARED_SOURCE_STATE,)
        if sem_evidencia:
            faltantes += (MissingObservation.CAUSAL_EVIDENCE,)
        return _relatorio(
            ComplianceOutcome.INSUFFICIENT_INFORMATION,
            subject,
            policy,
            evaluated_at,
            PolicyWindowState.EFFECTIVE,
            faltantes=faltantes,
        )
    if sem_evidencia:
        return _relatorio(
            ComplianceOutcome.INSUFFICIENT_INFORMATION,
            subject,
            policy,
            evaluated_at,
            PolicyWindowState.EFFECTIVE,
            faltantes=(MissingObservation.CAUSAL_EVIDENCE,),
        )

    if extinto and observation.causal_evidence is CausalEvidencePresence.ABSENT:
        return _relatorio_com_violacao(
            subject,
            policy,
            evaluated_at,
            ComplianceCode.ACCESSIBILITY_EXTINCTION_WITHOUT_EVIDENCE,
            ErrorSeverity.CRITICAL,
            regras=(),
        )

    aplicaveis = tuple(
        regra
        for regra in policy.rules
        if isinstance(regra, AccessibilityRule)
        and regra.matches(source_state=origem, target_state=observation.current_state)
    )
    if not aplicaveis:
        return _relatorio_com_violacao(
            subject,
            policy,
            evaluated_at,
            ComplianceCode.ACCESSIBILITY_TRANSITION_WITHOUT_RULE,
            ErrorSeverity.WARNING,
            regras=(),
        )

    negacoes = tuple(regra for regra in aplicaveis if regra.effect is GovernanceEffect.DENY)
    if negacoes:
        return _relatorio_com_violacao(
            subject,
            policy,
            evaluated_at,
            ComplianceCode.ACCESSIBILITY_TRANSITION_AGAINST_DENY,
            ErrorSeverity.ERROR,
            regras=tuple(sorted(regra.rule_id for regra in negacoes)),
        )
    return _relatorio(
        ComplianceOutcome.COMPLIANT,
        subject,
        policy,
        evaluated_at,
        PolicyWindowState.EFFECTIVE,
        regras=tuple(sorted(regra.rule_id for regra in aplicaveis)),
    )


# ----------------------------------------------------------------------
# Retenção — elegibilidade consumida, nunca recalculada
# ----------------------------------------------------------------------


def _avaliar_retencao(
    subject: ComplianceSubject,
    policy: EvaluatedPolicy,
    observation: RetentionAgeObservation,
    evaluated_at: datetime,
) -> ComplianceReport:
    """Matriz da família `RETENTION`.

    ```text
    POLICY_NOT_EFFECTIVE | OUT_OF_SCOPE   -> POLICY_NOT_APPLICABLE
    PRESERVE_LEGACY_PROTECTED | NOT_YET_DUE -> COMPLIANT
    ASSESS_AND_INFORM + PRESENT           -> COMPLIANT
    ASSESS_AND_INFORM + ABSENT            -> COMPLIANCE-RET-001
    ASSESS_AND_INFORM + NOT_OBSERVED      -> INSUFFICIENT_INFORMATION
    anchor_at ausente                     -> INSUFFICIENT_INFORMATION
    ```

    O cálculo de elegibilidade **não é reimplementado**: `avaliar_
    retencao` é a fonte única desde a E4.9.9.c, e reproduzir aqui a
    regra do máximo dos vencimentos criaria duas respostas possíveis
    para a mesma pergunta — que é exatamente o que a E4.7 evitou ao não
    copiar as dimensões da E4.3.
    """
    if observation.anchor_at is None:
        return _relatorio(
            ComplianceOutcome.INSUFFICIENT_INFORMATION,
            subject,
            policy,
            evaluated_at,
            PolicyWindowState.EFFECTIVE,
            faltantes=(MissingObservation.ANCHOR_TIMESTAMP,),
        )

    dominio = subject.domain_id
    if dominio is None:
        raise ValueError(
            "candidato de retenção sem domain_id — o construtor de ComplianceSubject "
            "já recusa este estado, e a segunda camada existe para que uma futura "
            "flexibilização daquele contrato não passe em silêncio por aqui"
        )
    regras = tuple(regra for regra in policy.rules if isinstance(regra, RetentionRule))
    avaliacao = avaliar_retencao(
        candidate=RetentionCandidate(
            subject_coid=subject.subject_coid,
            domain_id=dominio,
            created_at=observation.anchor_at,
            legacy_protection_state=observation.legacy_protection_state,
        ),
        rules=regras,
        policy_effective_from=policy.effective_from,
        policy_effective_until=policy.effective_until,
        evaluated_at=evaluated_at,
    )
    aplicaveis = tuple(sorted(avaliacao.applicable_rule_ids))

    if avaliacao.decision in (
        RetentionAssessmentDecision.POLICY_NOT_EFFECTIVE,
        RetentionAssessmentDecision.OUT_OF_SCOPE,
    ):
        return _relatorio(
            ComplianceOutcome.POLICY_NOT_APPLICABLE,
            subject,
            policy,
            evaluated_at,
            PolicyWindowState.EFFECTIVE,
        )

    if avaliacao.decision in (
        RetentionAssessmentDecision.PRESERVE_LEGACY_PROTECTED,
        RetentionAssessmentDecision.NOT_YET_DUE,
    ):
        return _relatorio(
            ComplianceOutcome.COMPLIANT,
            subject,
            policy,
            evaluated_at,
            PolicyWindowState.EFFECTIVE,
            regras=aplicaveis,
        )

    if observation.assessment_information is AssessmentInformationState.NOT_OBSERVED:
        return _relatorio(
            ComplianceOutcome.INSUFFICIENT_INFORMATION,
            subject,
            policy,
            evaluated_at,
            PolicyWindowState.EFFECTIVE,
            faltantes=(MissingObservation.ASSESSMENT_INFORMATION,),
        )
    if observation.assessment_information is AssessmentInformationState.ABSENT:
        return _relatorio_com_violacao(
            subject,
            policy,
            evaluated_at,
            ComplianceCode.RETENTION_ASSESSMENT_INFORMATION_ABSENT,
            ErrorSeverity.WARNING,
            regras=tuple(sorted(avaliacao.due_rule_ids)),
        )
    return _relatorio(
        ComplianceOutcome.COMPLIANT,
        subject,
        policy,
        evaluated_at,
        PolicyWindowState.EFFECTIVE,
        regras=aplicaveis,
    )


# ----------------------------------------------------------------------
# Montagem do relatório
# ----------------------------------------------------------------------


def _relatorio(
    desfecho: ComplianceOutcome,
    subject: ComplianceSubject,
    policy: EvaluatedPolicy,
    evaluated_at: datetime,
    janela: PolicyWindowState,
    *,
    regras: tuple[str, ...] = (),
    faltantes: tuple[MissingObservation, ...] = (),
) -> ComplianceReport:
    """Monta um relatório sem finding. Os invariantes vivem no tipo."""
    return ComplianceReport(
        outcome=desfecho,
        subject_ref=subject.to_ref(),
        policy_ref=policy.to_ref(),
        policy_version=policy.policy_version,
        evaluated_at=evaluated_at,
        evidence=ReportEvidence(
            policy_window=janela,
            applicable_rule_ids=regras,
            missing_observations=faltantes,
        ),
    )


def _relatorio_com_violacao(
    subject: ComplianceSubject,
    policy: EvaluatedPolicy,
    evaluated_at: datetime,
    codigo: ComplianceCode,
    severidade: ErrorSeverity,
    *,
    regras: tuple[str, ...],
) -> ComplianceReport:
    """Monta um relatório com **um** finding vinculado a esta avaliação."""
    referencia = policy.to_ref()
    sujeito = subject.to_ref()
    finding = ComplianceFinding(
        code=codigo,
        severity=severidade,
        subject_ref=sujeito,
        policy_ref=referencia,
        policy_version=policy.policy_version,
        evaluated_at=evaluated_at,
        matched_rule_ids=regras,
    )
    return ComplianceReport(
        outcome=ComplianceOutcome.VIOLATION_CONFIRMED,
        subject_ref=sujeito,
        policy_ref=referencia,
        policy_version=policy.policy_version,
        evaluated_at=evaluated_at,
        evidence=ReportEvidence(
            policy_window=PolicyWindowState.EFFECTIVE, applicable_rule_ids=regras
        ),
        findings=(finding,),
    )
