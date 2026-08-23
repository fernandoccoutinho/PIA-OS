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
