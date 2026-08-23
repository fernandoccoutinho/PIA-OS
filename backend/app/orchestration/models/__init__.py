"""
Modelos ORM da orquestração (`E7.1`).

Importar este pacote registra as cinco tabelas em `Base.metadata`. É o
mesmo papel de `app.memory.models` e `app.cognitive.models`, e é por isso
que `alembic/env.py` o importa: sem o registro, `autogenerate` não veria
as tabelas e a guarda de drift compararia contra um metadata incompleto.
"""

from app.orchestration.models.attempt import HandoffAttempt
from app.orchestration.models.command_receipt import CommandReceipt
from app.orchestration.models.enums import (
    AttemptState,
    CommandOperation,
    HandoffMode,
    HandoffResultStatus,
    ScheduleState,
    StepState,
)
from app.orchestration.models.handoff_attribution import HandoffAttribution
from app.orchestration.models.handoff_result import HandoffResult
from app.orchestration.models.schedule import Schedule
from app.orchestration.models.seal_receipt import SealReceipt
from app.orchestration.models.step import ScheduleStep

__all__ = [
    "AttemptState",
    "CommandOperation",
    "CommandReceipt",
    "HandoffAttempt",
    "HandoffAttribution",
    "HandoffMode",
    "HandoffResult",
    "HandoffResultStatus",
    "Schedule",
    "ScheduleState",
    "ScheduleStep",
    "SealReceipt",
    "StepState",
]
