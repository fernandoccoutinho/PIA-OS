"""
Vocabulários fechados da orquestração (`MAI-001 R1` §5 e §6).

Os ciclos de vida são **congelados pelo MAI** e por isso aparecem aqui
inteiros. Declarar o vocabulário não é o mesmo que executá-lo:

```text
DECLARED_VOCABULARY != EXECUTABLE_TRANSITION
DECLARED_VOCABULARY != EXECUTABLE_MODE
```

A E7.1 produz apenas o subconjunto de transições que lhe pertence
(`E7_1_IMPLEMENTED_*` abaixo). Amputar o enum para "só o que a E7.1 faz"
obrigaria uma migração de vocabulário na E7.2 e faria o banco esquecer
que os outros estados existem; declarar tudo e executar pouco é a
alternativa honesta, e é verificada por guarda estática.
"""

from enum import StrEnum


class ScheduleState(StrEnum):
    """`DRAFT -> ACTIVE -> {PAUSED, COMPLETED, CANCELLED, STOPPED}`."""

    DRAFT = "draft"
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    STOPPED = "stopped"


TERMINAL_SCHEDULE_STATES: frozenset[ScheduleState] = frozenset(
    {ScheduleState.COMPLETED, ScheduleState.CANCELLED, ScheduleState.STOPPED}
)
"""Terminais segundo o MAI §6. `PAUSED` **não** é terminal: exige ação humana."""


class StepState(StrEnum):
    """`PENDING -> DISPATCHED -> AWAITING_RETURN -> {RETURNED, REJECTED, FAILED, CANCELLED}`."""

    PENDING = "pending"
    DISPATCHED = "dispatched"
    AWAITING_RETURN = "awaiting_return"
    RETURNED = "returned"
    REJECTED = "rejected"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AttemptState(StrEnum):
    """`OPEN -> {CLOSED_OK, CLOSED_REJECTED, CLOSED_TIMEOUT, CLOSED_CANCELLED}`."""

    OPEN = "open"
    CLOSED_OK = "closed_ok"
    CLOSED_REJECTED = "closed_rejected"
    CLOSED_TIMEOUT = "closed_timeout"
    CLOSED_CANCELLED = "closed_cancelled"


class HandoffMode(StrEnum):
    """Modo de execução — eixo independente da composição (MAI §4)."""

    MANUAL_HANDOFF = "manual_handoff"
    SUPERVISED_AUTOMATIC_HANDOFF = "supervised_automatic_handoff"
    RESTRICTED_AUTOMATIC_CONTINUATION = "restricted_automatic_continuation"


EXECUTABLE_HANDOFF_MODES: frozenset[HandoffMode] = frozenset({HandoffMode.MANUAL_HANDOFF})
"""`D2 = MANUAL`. Os outros dois modos exigem conector e gate — E7.2/E7.3.

Gravar um Schedule declarando modo automático hoje registraria uma
capacidade inexistente. O escritor recusa; o vocabulário permanece.
"""


class CommandOperation(StrEnum):
    """Operações sob idempotência de comando na E7.1.

    A composição `(technical_principal_ref, operation, command_key)` do
    addendum só é verificável com **mais de uma** operação: com uma só,
    "outra operação não colide" seria uma afirmação sem experimento.
    """

    CREATE_SCHEDULE = "orchestration.create_schedule"
    SEAL_HANDOFF = "orchestration.seal_handoff"
    EXPORT_HANDOFF = "orchestration.export_handoff"
    IMPORT_RETURN = "orchestration.import_return"
    GRANT_DELEGATION = "orchestration.grant_delegation"
    REVOKE_DELEGATION = "orchestration.revoke_delegation"
    CONTROL_SCHEDULE = "orchestration.control_schedule"
    ISSUE_AUDIT_OPINION = "orchestration.issue_audit_opinion"


E7_1_IMPLEMENTED_SCHEDULE_TRANSITIONS: frozenset[tuple[ScheduleState, ScheduleState]] = frozenset(
    {(ScheduleState.DRAFT, ScheduleState.ACTIVE)}
)
"""Única transição de Schedule que a E7.1 executa.

`PAUSED`, `COMPLETED`, `CANCELLED` e `STOPPED` dependem de avanço,
cancelamento cooperativo ou Stop Condition — todos da E7.3.
"""

E7_1_IMPLEMENTED_STEP_TRANSITIONS: frozenset[tuple[StepState, StepState]] = frozenset()
"""Nenhuma. Selar **não** despacha.

```text
SEALED != DISPATCHED
```

`DISPATCHED` significa que o envelope atravessou a fronteira, e transporte
é E7.2. Manter a etapa em `PENDING` é também o que torna possível o
resultado binário exigido: dois selamentos do mesmo conteúdo.
"""

E7_1_IMPLEMENTED_ATTEMPT_TRANSITIONS: frozenset[tuple[AttemptState, AttemptState]] = frozenset()
"""Nenhuma. A tentativa nasce `OPEN` e só fecha com um retorno — E7.2."""


class HandoffResultStatus(StrEnum):
    """Veredito sobre um retorno importado (`E7.2`).

    ```text
    RESULT_STATUS != STEP_STATE
    RESULT_REJECTED != RESULT_DISCARDED
    ```

    Duas palavras, e nenhuma delas é estado de etapa. Um retorno rejeitado
    fecha a tentativa e **mantém** a etapa em `AWAITING_RETURN`: usar
    `StepState.REJECTED` aqui obrigaria, no retry, uma transição reversa
    `REJECTED -> DISPATCHED` que o MAI não congelou.
    """

    VALIDATED = "validated"
    REJECTED = "rejected"


E7_2_IMPLEMENTED_STEP_TRANSITIONS: frozenset[tuple[StepState, StepState]] = frozenset(
    {
        (StepState.PENDING, StepState.DISPATCHED),
        (StepState.DISPATCHED, StepState.AWAITING_RETURN),
        (StepState.AWAITING_RETURN, StepState.RETURNED),
    }
)
"""Transições de etapa que a E7.2 executa — e apenas estas.

A E7.1 não executava nenhuma (`SEALED != DISPATCHED`). A E7.2 traz o
transporte manual, então `DISPATCHED` e `AWAITING_RETURN` passam a ter
produtor real. `REJECTED`, `FAILED` e `CANCELLED` continuam sem produtor:
pertencem a decisão terminal e a cancelamento, que são E7.3.
"""

E7_2_IMPLEMENTED_ATTEMPT_TRANSITIONS: frozenset[tuple[AttemptState, AttemptState]] = frozenset(
    {
        (AttemptState.OPEN, AttemptState.CLOSED_OK),
        (AttemptState.OPEN, AttemptState.CLOSED_REJECTED),
    }
)
"""`CLOSED_TIMEOUT` e `CLOSED_CANCELLED` seguem sem produtor — E7.3."""


# --- E7.3: delegação, controle, observação e parecer ------------------------


class DelegationState(StrEnum):
    """`ACTIVE -> CONSUMED | REVOKED | EXPIRED`. Terminal não volta.

    ```text
    TERMINAL -> ANY_OTHER_STATE = FORBIDDEN
    EXPIRED = MATERIALIZED_SYNCHRONOUSLY_UNDER_LOCK
    ```

    `EXPIRED` não exige worker: é materializado na avaliação e no grant,
    sob o lock que já é tomado. Um sweeper em segundo plano seria um
    processo que este programa não tem, e declará-lo faria a expiração
    parecer garantida por algo inexistente.
    """

    ACTIVE = "active"
    CONSUMED = "consumed"
    REVOKED = "revoked"
    EXPIRED = "expired"


TERMINAL_DELEGATION_STATES: frozenset[DelegationState] = frozenset(
    {DelegationState.CONSUMED, DelegationState.REVOKED, DelegationState.EXPIRED}
)


class ControlEventKind(StrEnum):
    """Vocabulário fechado dos eventos de controle."""

    PAUSED = "paused"
    RESUMED = "resumed"
    STOPPED = "stopped"
    CANCELLED = "cancelled"
    COMPLETED = "completed"


class ControlReasonCode(StrEnum):
    """Por que o evento ocorreu. Sem texto livre.

    Texto livre num registro de controle vira o lugar onde alguém escreve
    o que não cabia em nenhum campo — inclusive conteúdo bruto.
    """

    OPERATOR_REQUESTED = "operator_requested"
    DELEGATION_MISSING = "delegation_missing"
    DELEGATION_EXPIRED = "delegation_expired"
    DELEGATION_CONTENT_CHANGED = "delegation_content_changed"
    HUMAN_GATE_UNAVAILABLE = "human_gate_unavailable"
    STOP_CONDITION_DECLARED = "stop_condition_declared"
    ALL_STEPS_RETURNED = "all_steps_returned"


class StopConditionCategory(StrEnum):
    """As dez categorias do MAI. Só com `STOP_CONDITION_DECLARED`."""

    MISSING_AUTHORITY = "missing_authority"
    SCOPE_OR_IMPACT_CHANGE = "scope_or_impact_change"
    PROVIDER_OR_TOOL_SWITCH = "provider_or_tool_switch"
    COST_QUOTA_OR_DURATION_LIMIT = "cost_quota_or_duration_limit"
    SECRET_OR_PRIVACY_RISK = "secret_or_privacy_risk"
    ARTIFACT_IDENTITY_MISMATCH = "artifact_identity_mismatch"
    MANDATORY_GATE_FAILED = "mandatory_gate_failed"
    MATERIAL_AUDIT_FINDING = "material_audit_finding"
    EXTERNAL_EFFECT_REQUESTED = "external_effect_requested"
    PROVENANCE_OR_ISOLATION_FAILURE = "provenance_or_isolation_failure"


class ObservationKind(StrEnum):
    """`D10 = OBSERVED_ONLY`. Um produtor real, nada preventivo."""

    DECLARED_PROVIDER_SWITCH = "declared_provider_switch"


class AuditOpinionKind(StrEnum):
    """Vocabulário de parecer. `PASS_FINAL` **não** existe aqui.

    ```text
    AI_SELF_PASS_FINAL = FORBIDDEN
    ```

    A ausência é imposta três vezes — enum, matriz e `CHECK` no banco —
    porque um parecer de execução que pudesse declarar aprovação final
    tornaria a auditoria independente decorativa.
    """

    CONCUR = "concur"
    DISSENT = "dissent"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"
    OUT_OF_SCOPE = "out_of_scope"


class AuditReasonCode(StrEnum):
    """Motivos admitidos, um por opinião (matriz abaixo)."""

    CONTRACT_CONFORMS = "contract_conforms"
    CONTRACT_NONCONFORMITY = "contract_nonconformity"
    EVIDENCE_MISSING = "evidence_missing"
    SCOPE_EXCLUDED = "scope_excluded"


AUDIT_OPINION_REASON_MATRIX: dict[AuditOpinionKind, frozenset[AuditReasonCode]] = {
    AuditOpinionKind.CONCUR: frozenset({AuditReasonCode.CONTRACT_CONFORMS}),
    AuditOpinionKind.DISSENT: frozenset({AuditReasonCode.CONTRACT_NONCONFORMITY}),
    AuditOpinionKind.INSUFFICIENT_EVIDENCE: frozenset({AuditReasonCode.EVIDENCE_MISSING}),
    AuditOpinionKind.OUT_OF_SCOPE: frozenset({AuditReasonCode.SCOPE_EXCLUDED}),
}
"""Opinião e motivo têm de concordar.

Um parecer `concur` justificado por `contract_nonconformity` seria uma
linha que contradiz a si mesma, e nenhuma leitura posterior saberia em
qual metade acreditar.
"""


class GateReasonCode(StrEnum):
    """Resposta da porta de autorização. Enum, não string livre."""

    AUTHORIZED = "authorized"
    HUMAN_AUTHORITY_UNAVAILABLE = "human_authority_unavailable"


E7_3_IMPLEMENTED_SCHEDULE_TRANSITIONS: frozenset[tuple[ScheduleState, ScheduleState]] = frozenset(
    {
        (ScheduleState.ACTIVE, ScheduleState.PAUSED),
        (ScheduleState.PAUSED, ScheduleState.ACTIVE),
        (ScheduleState.ACTIVE, ScheduleState.STOPPED),
        (ScheduleState.PAUSED, ScheduleState.STOPPED),
        (ScheduleState.ACTIVE, ScheduleState.CANCELLED),
        (ScheduleState.PAUSED, ScheduleState.CANCELLED),
        (ScheduleState.ACTIVE, ScheduleState.COMPLETED),
    }
)

E7_3_IMPLEMENTED_STEP_TRANSITIONS: frozenset[tuple[StepState, StepState]] = frozenset(
    {
        (StepState.PENDING, StepState.CANCELLED),
        (StepState.AWAITING_RETURN, StepState.CANCELLED),
    }
)

E7_3_IMPLEMENTED_ATTEMPT_TRANSITIONS: frozenset[tuple[AttemptState, AttemptState]] = frozenset(
    {(AttemptState.OPEN, AttemptState.CLOSED_CANCELLED)}
)

STATES_WITHOUT_PRODUCER_AFTER_E7_3: frozenset[str] = frozenset(
    {StepState.FAILED.value, StepState.REJECTED.value, AttemptState.CLOSED_TIMEOUT.value}
)
"""Continuam sem produtor, e é declarado.

`CLOSED_TIMEOUT` exigiria worker; `FAILED` e `REJECTED` de etapa exigiriam
decisão terminal sobre a etapa, que ninguém autorizou. Vocabulário não é
capacidade.
"""
