"""
Único caminho de leitura/escrita das cinco tabelas da orquestração.

```text
PERSISTENCE_ONLY_THROUGH_REPOSITORY = TRUE
RAW_SQL_IN_SERVICE = FORBIDDEN
SESSION_OUTSIDE_REPOSITORY = FORBIDDEN
CROSS_PRINCIPAL_SCHEDULE_READ = FORBIDDEN
```

Toda consulta e toda mutação de Schedule recebem `control_principal_ref`
e filtram por ele. O escopo mora **aqui**, e não numa camada acima, pela
mesma razão que a E6.2 moveu `canonical_scopes()` para dentro de
`create_principal()`: uma garantia que depende de quem chama vale apenas
para quem passa por aquele caminho.

```text
CALLER_VALIDATION != WRITER_INVARIANT
```
"""

import uuid
from datetime import datetime

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.orchestration.errors.exceptions import SealReceiptImmutableError
from app.orchestration.models.attempt import HandoffAttempt
from app.orchestration.models.command_receipt import CommandReceipt
from app.orchestration.models.enums import AttemptState, HandoffMode, ScheduleState, StepState
from app.orchestration.models.schedule import Schedule
from app.orchestration.models.seal_receipt import SealReceipt
from app.orchestration.models.step import ScheduleStep
from app.orchestration.schemas.envelope import StepDraft


class OrchestrationRepository:
    """Persistência da E7.1. Não decide nada — apenas grava e lê sob escopo."""

    def __init__(self, session: Session) -> None:
        self._session = session

    # --- relógio -----------------------------------------------------------

    def database_now(self) -> datetime:
        """Instante do PostgreSQL — nunca `datetime.now()` da aplicação.

        `sealed_at` sai daqui. Precedente medido: `database_now()` da E6.2.
        """
        momento = self._session.execute(sa.select(sa.func.now())).scalar_one()
        if not isinstance(momento, datetime):  # pragma: no cover - defesa de tipo
            raise TypeError("now() do banco não retornou datetime")
        return momento

    # --- schedules ---------------------------------------------------------

    def create_schedule(
        self,
        *,
        schedule_id: uuid.UUID,
        control_principal_ref: str,
        title: str,
        execution_mode: HandoffMode,
        steps: tuple[StepDraft, ...],
    ) -> Schedule:
        """Cria o trabalho e suas etapas na mesma transação.

        A identidade vem do chamador (precedente da E4.11): a idempotência
        de comando propõe o `outcome_ref` antes de reivindicar a chave, e
        para isso precisa conhecer o id do efeito de antemão.
        """
        agenda = Schedule(
            id=schedule_id,
            title=title,
            state=ScheduleState.DRAFT,
            execution_mode=execution_mode,
            control_principal_ref=control_principal_ref,
        )
        self._session.add(agenda)
        for posicao, rascunho in enumerate(steps, start=1):
            self._session.add(
                ScheduleStep(
                    schedule_id=schedule_id,
                    position=posicao,
                    role=rascunho.role,
                    instruction_ref=rascunho.instruction_ref,
                    context_refs=rascunho.context_refs,
                    expected_output_contract=rascunho.expected_output_contract,
                    constraints=rascunho.constraints,
                    state=StepState.PENDING,
                )
            )
        self._session.flush()
        return agenda

    def get_schedule(
        self, *, control_principal_ref: str, schedule_id: uuid.UUID
    ) -> Schedule | None:
        """Escopado. `None` quando o trabalho é de outro principal."""
        return self._session.scalars(
            sa.select(Schedule).where(
                Schedule.id == schedule_id,
                Schedule.control_principal_ref == control_principal_ref,
            )
        ).one_or_none()

    def lock_schedule(
        self, *, control_principal_ref: str, schedule_id: uuid.UUID
    ) -> Schedule | None:
        """Como `get_schedule`, com `SELECT ... FOR UPDATE`.

        O lock é tomado **antes** de avaliar o estado, para que o estado
        observado seja o mesmo que a transição escreve — precedente da
        E4.7 (`refresh_for_update` mantém o lock até commit/rollback).
        """
        return self._session.scalars(
            sa.select(Schedule)
            .where(
                Schedule.id == schedule_id,
                Schedule.control_principal_ref == control_principal_ref,
            )
            .with_for_update()
        ).one_or_none()

    def set_schedule_state(self, *, schedule: Schedule, state: ScheduleState) -> Schedule:
        """Grava um estado já decidido pelo serviço, sobre a linha bloqueada."""
        schedule.state = state
        self._session.flush()
        return schedule

    def list_steps(
        self, *, control_principal_ref: str, schedule_id: uuid.UUID
    ) -> list[ScheduleStep]:
        """Etapas em ordem de posição, escopadas pelo principal de controle."""
        return list(
            self._session.scalars(
                sa.select(ScheduleStep)
                .join(Schedule, Schedule.id == ScheduleStep.schedule_id)
                .where(
                    ScheduleStep.schedule_id == schedule_id,
                    Schedule.control_principal_ref == control_principal_ref,
                )
                .order_by(ScheduleStep.position.asc(), ScheduleStep.id.asc())
            ).all()
        )

    def get_step(
        self, *, control_principal_ref: str, schedule_id: uuid.UUID, step_id: uuid.UUID
    ) -> ScheduleStep | None:
        return self._session.scalars(
            sa.select(ScheduleStep)
            .join(Schedule, Schedule.id == ScheduleStep.schedule_id)
            .where(
                ScheduleStep.id == step_id,
                ScheduleStep.schedule_id == schedule_id,
                Schedule.control_principal_ref == control_principal_ref,
            )
        ).one_or_none()

    # --- tentativas e recibos ----------------------------------------------

    def next_attempt_number(self, *, step_id: uuid.UUID) -> int:
        """Próximo número de tentativa, com a etapa bloqueada.

        Sem o lock, dois selamentos concorrentes da mesma etapa leriam o
        mesmo máximo e um deles morreria na unicidade — a numeração seria
        correta por acidente de constraint, não por construção.
        """
        self._session.execute(
            sa.select(ScheduleStep.id).where(ScheduleStep.id == step_id).with_for_update()
        ).one()
        maximo = self._session.execute(
            sa.select(sa.func.coalesce(sa.func.max(HandoffAttempt.attempt_number), 0)).where(
                HandoffAttempt.step_id == step_id
            )
        ).scalar_one()
        return int(maximo) + 1

    def create_attempt(
        self,
        *,
        attempt_id: uuid.UUID,
        schedule_id: uuid.UUID,
        step_id: uuid.UUID,
        attempt_number: int,
        envelope_version: str,
        content_sha256: str,
    ) -> HandoffAttempt:
        tentativa = HandoffAttempt(
            id=attempt_id,
            schedule_id=schedule_id,
            step_id=step_id,
            attempt_number=attempt_number,
            envelope_version=envelope_version,
            content_sha256=content_sha256,
            state=AttemptState.OPEN,
        )
        self._session.add(tentativa)
        self._session.flush()
        return tentativa

    def create_seal_receipt(
        self,
        *,
        attempt_id: uuid.UUID,
        content_sha256: str,
        sealed_at: datetime,
        sealer_ref: str,
    ) -> SealReceipt:
        recibo = SealReceipt(
            attempt_id=attempt_id,
            content_sha256=content_sha256,
            sealed_at=sealed_at,
            sealer_ref=sealer_ref,
        )
        self._session.add(recibo)
        self._session.flush()
        return recibo

    def update_seal_receipt(self, *, receipt: SealReceipt) -> None:
        """Recusa explícita — segunda das três camadas de append-only."""
        raise SealReceiptImmutableError(
            message="recibo de selamento é append-only: UPDATE recusado",
            detail={"receipt_id": str(receipt.id)},
        )

    def delete_seal_receipt(self, *, receipt: SealReceipt) -> None:
        """Recusa explícita — segunda das três camadas de append-only."""
        raise SealReceiptImmutableError(
            message="recibo de selamento é append-only: DELETE recusado",
            detail={"receipt_id": str(receipt.id)},
        )

    def get_seal_receipt_by_attempt(self, *, attempt_id: uuid.UUID) -> SealReceipt | None:
        return self._session.scalars(
            sa.select(SealReceipt).where(SealReceipt.attempt_id == attempt_id)
        ).one_or_none()

    def list_attempts(
        self,
        *,
        control_principal_ref: str,
        schedule_id: uuid.UUID,
        step_id: uuid.UUID | None = None,
    ) -> list[HandoffAttempt]:
        """Tentativas do trabalho, escopadas. Ordem canônica do repositório."""
        consulta = (
            sa.select(HandoffAttempt)
            .join(Schedule, Schedule.id == HandoffAttempt.schedule_id)
            .where(
                HandoffAttempt.schedule_id == schedule_id,
                Schedule.control_principal_ref == control_principal_ref,
            )
        )
        if step_id is not None:
            consulta = consulta.where(HandoffAttempt.step_id == step_id)
        return list(
            self._session.scalars(
                consulta.order_by(HandoffAttempt.created_at.asc(), HandoffAttempt.id.asc())
            ).all()
        )

    # --- idempotência de comando -------------------------------------------

    def claim_command(
        self,
        *,
        technical_principal_ref: str,
        operation: str,
        command_key: str,
        proposed_outcome_ref: str,
    ) -> tuple[CommandReceipt, bool]:
        """Reivindica a tripla e devolve `(recibo, reivindicado_agora)`.

        `ON CONFLICT ... DO UPDATE` e não `DO NOTHING`: com `DO NOTHING` o
        segundo chamador concorrente **não** bloqueia, o `RETURNING` vem
        vazio e o `SELECT` seguinte não enxerga a linha ainda não
        commitada — a resposta correta viraria "recibo inexistente". O
        `DO UPDATE` toma o lock da linha em conflito e libera o segundo
        chamador só depois do commit do primeiro. É o mesmo idioma
        atômico do `consume_quota()` da E6.2.

        A distinção entre inserir e recuperar sai do próprio
        `outcome_ref`: ele carrega um UUID recém-gerado, então o valor
        devolvido só pode ser igual ao proposto se foi esta chamada que
        inseriu a linha. Não depende de coluna de sistema.
        """
        instrucao = sa.text(
            """
            INSERT INTO command_receipts
                (id, technical_principal_ref, operation, command_key, outcome_ref,
                 created_at, updated_at)
            VALUES (
                :receipt_id,
                :technical_principal_ref,
                :operation,
                :command_key,
                :outcome_ref,
                now(),
                now()
            )
            ON CONFLICT (technical_principal_ref, operation, command_key)
            DO UPDATE SET updated_at = command_receipts.updated_at
            RETURNING id, outcome_ref
            """
        )
        linha = self._session.execute(
            instrucao,
            {
                "receipt_id": uuid.uuid4(),
                "technical_principal_ref": technical_principal_ref,
                "operation": operation,
                "command_key": command_key,
                "outcome_ref": proposed_outcome_ref,
            },
        ).one()
        reivindicado = str(linha.outcome_ref) == proposed_outcome_ref
        recibo = self._session.get(CommandReceipt, linha.id)
        if recibo is None:  # pragma: no cover - RETURNING garante a linha
            raise RuntimeError("recibo de comando desapareceu logo após o INSERT")
        self._session.refresh(recibo)
        return recibo, reivindicado

    def get_command_receipt(
        self, *, technical_principal_ref: str, operation: str, command_key: str
    ) -> CommandReceipt | None:
        return self._session.scalars(
            sa.select(CommandReceipt).where(
                CommandReceipt.technical_principal_ref == technical_principal_ref,
                CommandReceipt.operation == operation,
                CommandReceipt.command_key == command_key,
            )
        ).one_or_none()
