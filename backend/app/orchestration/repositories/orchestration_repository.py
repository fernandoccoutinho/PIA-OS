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

## Corretivo R1 (Chain111)

A Chain110 impunha o vínculo apenas nos **cinco** métodos de leitura de
Schedule e Step. Os caminhos de tentativa e de recibo — numerar, criar
tentativa, criar recibo, ler recibo e gravar estado — recebiam
identidades já resolvidas e confiavam em quem chamava.

```text
SCOPED_READ_PATH != SCOPED_WRITE_PATH
CALLER_RESOLVED_ID != AUTHORIZED_ID
```

Um `attempt_id` ou `step_id` é opaco, mas não é secreto: quem o obtiver
por qualquer via passava a operar sobre o trabalho de outro principal
sem que o repositório notasse. O vínculo agora é imposto em **todo**
caminho que leia ou altere `Schedule`, `Step`, `HandoffAttempt` ou
`SealReceipt`, e um gate estático exaustivo classifica cada método
público — nenhum método novo escapa por omissão.

Caminho de escrita não devolve `None` em caso de escopo alheio: levanta
`OrchestrationScopeViolationError`. Devolver `None` num escritor
convidaria o chamador a tratar recusa como ausência.

## Corretivo R2 (Chain112)

O vínculo por dono estava certo e era **insuficiente**. Tentativa e
recibo derivavam o Schedule da própria linha e conferiam só o
proprietário, de modo que um principal dono de A e de B pedia contexto
de A e recebia material de B.

```text
OWNER_BINDING != SCHEDULE_BINDING
DERIVED_SCHEDULE != CALLER_EXPECTED_SCHEDULE
```

Todo caminho de `HandoffAttempt`/`SealReceipt` passa a exigir
`schedule_id` do chamador e a impor as quatro condições juntas:
identidade da tentativa, tentativa dentro do Schedule, Schedule
declarado e dono do Schedule. Nenhuma delas é derivada de outra —
derivar é justamente o que produziu este defeito.
"""

import uuid
from datetime import datetime
from typing import cast

import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.orchestration.errors.exceptions import (
    GovernanceRecordImmutableError,
    HandoffRecordImmutableError,
    OrchestrationScopeViolationError,
    SealReceiptImmutableError,
)
from app.orchestration.models.attempt import HandoffAttempt
from app.orchestration.models.audit_opinion import AuditOpinion
from app.orchestration.models.command_receipt import CommandReceipt
from app.orchestration.models.control_event import OrchestrationControlEvent
from app.orchestration.models.enums import (
    AttemptState,
    AuditOpinionKind,
    ControlEventKind,
    ControlReasonCode,
    DelegationState,
    HandoffMode,
    HandoffResultStatus,
    ObservationKind,
    ScheduleState,
    StepState,
    StopConditionCategory,
)
from app.orchestration.models.execution_observation import ExecutionObservation
from app.orchestration.models.handoff_attribution import HandoffAttribution
from app.orchestration.models.handoff_result import HandoffResult
from app.orchestration.models.schedule import Schedule
from app.orchestration.models.seal_receipt import SealReceipt
from app.orchestration.models.service_delegation import ServiceDelegation
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

    def set_schedule_state(
        self, *, control_principal_ref: str, schedule_id: uuid.UUID, state: ScheduleState
    ) -> Schedule:
        """Grava um estado já decidido pelo serviço, sob escopo e sob lock.

        Recebe `schedule_id` em vez da instância: aceitar a linha pronta
        deixava a autorização a cargo de quem a carregou. Reresolver aqui
        custa uma consulta na mesma transação — a linha já está no mapa de
        identidade e continua bloqueada — e fecha o caminho.
        """
        agenda = self.lock_schedule(
            control_principal_ref=control_principal_ref, schedule_id=schedule_id
        )
        if agenda is None:
            raise OrchestrationScopeViolationError(
                message="Schedule inexistente sob este principal de controle",
                detail={"schedule_id": str(schedule_id)},
            )
        agenda.state = state
        self._session.flush()
        return agenda

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

    def next_attempt_number(
        self, *, control_principal_ref: str, schedule_id: uuid.UUID, step_id: uuid.UUID
    ) -> int:
        """Próximo número de tentativa, com a etapa bloqueada e sob escopo.

        Sem o lock, dois selamentos concorrentes da mesma etapa leriam o
        mesmo máximo e um deles morreria na unicidade — a numeração seria
        correta por acidente de constraint, não por construção.

        O `FOR UPDATE` recai sobre `schedule_steps`; o `JOIN` com
        `schedules` entra como `EXISTS` para que o lock não se espalhe
        para a linha do Schedule, que a numeração não precisa bloquear.
        """
        etapa = self._session.execute(
            sa.select(ScheduleStep.id)
            .where(
                ScheduleStep.id == step_id,
                ScheduleStep.schedule_id == schedule_id,
                sa.exists().where(
                    Schedule.id == schedule_id,
                    Schedule.control_principal_ref == control_principal_ref,
                ),
            )
            .with_for_update()
        ).one_or_none()
        if etapa is None:
            raise OrchestrationScopeViolationError(
                message="etapa inexistente neste Schedule sob este principal",
                detail={"schedule_id": str(schedule_id), "step_id": str(step_id)},
            )
        maximo = self._session.execute(
            sa.select(sa.func.coalesce(sa.func.max(HandoffAttempt.attempt_number), 0)).where(
                HandoffAttempt.step_id == step_id
            )
        ).scalar_one()
        return int(maximo) + 1

    def create_attempt(
        self,
        *,
        control_principal_ref: str,
        attempt_id: uuid.UUID,
        schedule_id: uuid.UUID,
        step_id: uuid.UUID,
        attempt_number: int,
        envelope_version: str,
        content_sha256: str,
    ) -> HandoffAttempt:
        """Abre a tentativa **depois** de provar etapa, Schedule e dono.

        A prova é feita aqui e reforçada no banco pela chave estrangeira
        composta `(step_id, schedule_id)` da migration corretiva: mesmo
        que este método fosse contornado, `Schedule A + Step B` não entra.
        """
        if (
            self.get_step(
                control_principal_ref=control_principal_ref,
                schedule_id=schedule_id,
                step_id=step_id,
            )
            is None
        ):
            raise OrchestrationScopeViolationError(
                message="etapa inexistente neste Schedule sob este principal",
                detail={"schedule_id": str(schedule_id), "step_id": str(step_id)},
            )
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
        control_principal_ref: str,
        schedule_id: uuid.UUID,
        attempt_id: uuid.UUID,
        content_sha256: str,
        sealed_at: datetime,
        sealer_ref: str,
    ) -> SealReceipt:
        """Emite o recibo só para tentativa deste Schedule e deste dono."""
        if (
            self._attempt_under_scope(
                control_principal_ref=control_principal_ref,
                schedule_id=schedule_id,
                attempt_id=attempt_id,
            )
            is None
        ):
            raise OrchestrationScopeViolationError(
                message="tentativa inexistente neste Schedule sob este principal",
                detail={"schedule_id": str(schedule_id), "attempt_id": str(attempt_id)},
            )
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

    def _attempt_under_scope(
        self, *, control_principal_ref: str, schedule_id: uuid.UUID, attempt_id: uuid.UUID
    ) -> uuid.UUID | None:
        """Identidade da tentativa se ela pertencer ao Schedule **e** ao dono.

        ```text
        OWNER_BINDING != SCHEDULE_BINDING
        DERIVED_SCHEDULE != CALLER_EXPECTED_SCHEDULE
        ```

        Corretivo R2: a versão anterior derivava o Schedule da própria
        tentativa e conferia só o dono. Um principal que possui A e B
        pedia contexto de A e recebia tentativa de B — o predicado
        respondia "é seu", que não é a pergunta. A pergunta é "é seu **e**
        é deste trabalho".

        As quatro condições valem juntas; nenhuma é derivada de outra.
        """
        return self._session.scalars(
            sa.select(HandoffAttempt.id)
            .join(Schedule, Schedule.id == HandoffAttempt.schedule_id)
            .where(
                HandoffAttempt.id == attempt_id,
                HandoffAttempt.schedule_id == schedule_id,
                Schedule.id == schedule_id,
                Schedule.control_principal_ref == control_principal_ref,
            )
        ).one_or_none()

    def get_attempt(
        self, *, control_principal_ref: str, schedule_id: uuid.UUID, attempt_id: uuid.UUID
    ) -> HandoffAttempt | None:
        """Tentativa **deste** Schedule e **deste** dono. `None` caso contrário."""
        return self._session.scalars(
            sa.select(HandoffAttempt)
            .join(Schedule, Schedule.id == HandoffAttempt.schedule_id)
            .where(
                HandoffAttempt.id == attempt_id,
                HandoffAttempt.schedule_id == schedule_id,
                Schedule.id == schedule_id,
                Schedule.control_principal_ref == control_principal_ref,
            )
        ).one_or_none()

    def get_seal_receipt_by_attempt(
        self, *, control_principal_ref: str, schedule_id: uuid.UUID, attempt_id: uuid.UUID
    ) -> SealReceipt | None:
        """Recibo de uma tentativa deste Schedule e deste dono.

        ```text
        OPAQUE_ID != SECRET_ID
        OWNER_BINDING != SCHEDULE_BINDING
        ```

        A Chain110 não atravessava o Schedule: um `attempt_id` vazado
        virava chave de leitura do trabalho alheio. A Chain111 passou a
        atravessar, mas derivando o Schedule da tentativa — bastava ser
        dono dos dois trabalhos para ler o do contexto errado. Aqui o
        Schedule é o que o chamador declarou, não o que a linha diz.
        """
        return self._session.scalars(
            sa.select(SealReceipt)
            .join(HandoffAttempt, HandoffAttempt.id == SealReceipt.attempt_id)
            .join(Schedule, Schedule.id == HandoffAttempt.schedule_id)
            .where(
                SealReceipt.attempt_id == attempt_id,
                HandoffAttempt.schedule_id == schedule_id,
                Schedule.id == schedule_id,
                Schedule.control_principal_ref == control_principal_ref,
            )
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
        request_sha256: str | None = None,
    ) -> tuple[CommandReceipt, bool]:
        """Reivindica a tripla e devolve `(recibo, reivindicado_agora)`.

        `ON CONFLICT ... DO UPDATE` e não `DO NOTHING`: com `DO NOTHING` o
        segundo chamador concorrente **não** bloqueia, o `RETURNING` vem
        vazio e o `SELECT` seguinte não enxerga a linha ainda não
        commitada — a resposta correta viraria "recibo inexistente". O
        `DO UPDATE` toma o lock da linha em conflito e libera o segundo
        chamador só depois do commit do primeiro. É o mesmo idioma
        atômico do `consume_quota()` da E6.2.

        A distinção entre inserir e recuperar sai da **identidade do
        recibo proposto**: o `id` devolvido só pode ser igual ao UUID que
        esta chamada gerou se foi ela que inseriu a linha.

        ```text
        CLAIM_DETECTION_BY_RECEIPT_IDENTITY = TRUE
        CLAIM_DETECTION_BY_OUTCOME_REF = BROKEN
        ```

        Corretivo R1 (Chain114): a versão anterior comparava
        `outcome_ref`, o que funcionava enquanto todo comando propunha um
        UUID recém-gerado. `IMPORT_RETURN` quebrou essa premissa ao
        propor o `attempt_id` que o **chamador** enviou: no replay exato o
        recibo existente tem exatamente o mesmo valor, e a comparação
        classificava uma recuperação como inserção — o efeito rodava de
        novo. Identidade do recibo não depende do que o comando decide
        pôr em `outcome_ref`.
        """
        receipt_id = uuid.uuid4()
        instrucao = sa.text(
            """
            INSERT INTO command_receipts
                (id, technical_principal_ref, operation, command_key, outcome_ref,
                 request_sha256, created_at, updated_at)
            VALUES (
                :receipt_id,
                :technical_principal_ref,
                :operation,
                :command_key,
                :outcome_ref,
                :request_sha256,
                now(),
                now()
            )
            ON CONFLICT (technical_principal_ref, operation, command_key)
            DO UPDATE SET updated_at = command_receipts.updated_at
            RETURNING id, outcome_ref, request_sha256
            """
        )
        linha = self._session.execute(
            instrucao,
            {
                "receipt_id": receipt_id,
                "technical_principal_ref": technical_principal_ref,
                "operation": operation,
                "command_key": command_key,
                "outcome_ref": proposed_outcome_ref,
                "request_sha256": request_sha256,
            },
        ).one()
        reivindicado = linha.id == receipt_id
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

    # --- E7.2: transporte, veredito e atribuição ---------------------------
    #
    # Todo método abaixo recebe control_principal_ref E o schedule_id
    # DECLARADO pelo chamador, e impõe os dois.
    #
    # ```text
    # OWNER_BINDING != SCHEDULE_BINDING
    # DERIVED_SCHEDULE != CALLER_DECLARED_SCHEDULE
    # NO_AUTHORIZATION_DERIVED_FROM_THE_AUTHORIZED_OBJECT
    # ```

    def lock_step(
        self, *, control_principal_ref: str, schedule_id: uuid.UUID, step_id: uuid.UUID
    ) -> ScheduleStep | None:
        """Etapa bloqueada sob escopo. Segundo elo da ordem de locks.

        ```text
        LOCK_ORDER = Schedule -> Step(s) -> Attempt
        ```

        Ordem fixa e sempre a mesma porque duas transações que travam os
        mesmos recursos em ordens opostas produzem deadlock — e deadlock
        sob decisão de ciclo de vida apareceria como falha intermitente
        de negócio.
        """
        return self._session.scalars(
            sa.select(ScheduleStep)
            .join(Schedule, Schedule.id == ScheduleStep.schedule_id)
            .where(
                ScheduleStep.id == step_id,
                ScheduleStep.schedule_id == schedule_id,
                Schedule.id == schedule_id,
                Schedule.control_principal_ref == control_principal_ref,
            )
            .with_for_update(of=ScheduleStep)
        ).one_or_none()

    def set_step_state(
        self,
        *,
        control_principal_ref: str,
        schedule_id: uuid.UUID,
        step_id: uuid.UUID,
        state: StepState,
    ) -> ScheduleStep:
        """Grava estado de etapa já decidido pelo serviço, sob escopo e lock."""
        etapa = self.lock_step(
            control_principal_ref=control_principal_ref,
            schedule_id=schedule_id,
            step_id=step_id,
        )
        if etapa is None:
            raise OrchestrationScopeViolationError(
                message="etapa inexistente neste Schedule sob este principal",
                detail={"schedule_id": str(schedule_id), "step_id": str(step_id)},
            )
        etapa.state = state
        self._session.flush()
        return etapa

    def lock_attempt(
        self, *, control_principal_ref: str, schedule_id: uuid.UUID, attempt_id: uuid.UUID
    ) -> HandoffAttempt | None:
        """Tentativa bloqueada sob escopo. Terceiro elo da ordem de locks."""
        return self._session.scalars(
            sa.select(HandoffAttempt)
            .join(Schedule, Schedule.id == HandoffAttempt.schedule_id)
            .where(
                HandoffAttempt.id == attempt_id,
                HandoffAttempt.schedule_id == schedule_id,
                Schedule.id == schedule_id,
                Schedule.control_principal_ref == control_principal_ref,
            )
            .with_for_update(of=HandoffAttempt)
        ).one_or_none()

    def set_attempt_state(
        self,
        *,
        control_principal_ref: str,
        schedule_id: uuid.UUID,
        attempt_id: uuid.UUID,
        state: AttemptState,
    ) -> HandoffAttempt:
        tentativa = self.lock_attempt(
            control_principal_ref=control_principal_ref,
            schedule_id=schedule_id,
            attempt_id=attempt_id,
        )
        if tentativa is None:
            raise OrchestrationScopeViolationError(
                message="tentativa inexistente neste Schedule sob este principal",
                detail={"schedule_id": str(schedule_id), "attempt_id": str(attempt_id)},
            )
        tentativa.state = state
        self._session.flush()
        return tentativa

    def get_open_attempt(
        self, *, control_principal_ref: str, schedule_id: uuid.UUID, step_id: uuid.UUID
    ) -> HandoffAttempt | None:
        """Tentativa `OPEN` da etapa, se houver. No máximo uma, por índice."""
        return self._session.scalars(
            sa.select(HandoffAttempt)
            .join(Schedule, Schedule.id == HandoffAttempt.schedule_id)
            .where(
                HandoffAttempt.step_id == step_id,
                HandoffAttempt.schedule_id == schedule_id,
                HandoffAttempt.state == AttemptState.OPEN,
                Schedule.id == schedule_id,
                Schedule.control_principal_ref == control_principal_ref,
            )
        ).one_or_none()

    def list_unreturned_predecessors(
        self, *, control_principal_ref: str, schedule_id: uuid.UUID, position: int
    ) -> list[int]:
        """Posições anteriores que ainda não estão `RETURNED`.

        ```text
        REJECTED_RESULT BLOCKS ADVANCE
        ```

        É isto que impede o cliente de pular a etapa recusada chamando
        direto o endpoint da próxima: sem a checagem, "bloqueia avanço"
        valeria apenas para quem seguisse a ordem por educação.
        """
        return [
            linha[0]
            for linha in self._session.execute(
                sa.select(ScheduleStep.position)
                .join(Schedule, Schedule.id == ScheduleStep.schedule_id)
                .where(
                    ScheduleStep.schedule_id == schedule_id,
                    ScheduleStep.position < position,
                    ScheduleStep.state != StepState.RETURNED,
                    Schedule.id == schedule_id,
                    Schedule.control_principal_ref == control_principal_ref,
                )
                .order_by(ScheduleStep.position.asc())
            ).all()
        ]

    def create_handoff_result(
        self,
        *,
        control_principal_ref: str,
        schedule_id: uuid.UUID,
        attempt_id: uuid.UUID,
        status: HandoffResultStatus,
        expected_output_contract: str,
        output_media_type: str,
        output_sha256: str,
        output_bytes: int,
        declared_output_ref: str | None,
        validation_codes: tuple[str, ...],
    ) -> HandoffResult:
        """Veredito de uma tentativa deste Schedule e deste dono."""
        if (
            self._attempt_under_scope(
                control_principal_ref=control_principal_ref,
                schedule_id=schedule_id,
                attempt_id=attempt_id,
            )
            is None
        ):
            raise OrchestrationScopeViolationError(
                message="tentativa inexistente neste Schedule sob este principal",
                detail={"schedule_id": str(schedule_id), "attempt_id": str(attempt_id)},
            )
        resultado = HandoffResult(
            attempt_id=attempt_id,
            status=status,
            expected_output_contract=expected_output_contract,
            output_media_type=output_media_type,
            output_sha256=output_sha256,
            output_bytes=output_bytes,
            declared_output_ref=declared_output_ref,
            validation_codes=validation_codes,
        )
        self._session.add(resultado)
        self._session.flush()
        return resultado

    def create_handoff_attribution(
        self,
        *,
        control_principal_ref: str,
        schedule_id: uuid.UUID,
        attempt_id: uuid.UUID,
        role: str,
        declared_provider_id: str | None,
        declared_model_id: str | None,
        declared_instance_id: str,
        declared_at: datetime,
    ) -> HandoffAttribution:
        """Atribuição declarada. `provenance_record_ref` fica `NULL`.

        ```text
        E7_WRITES_PROVENANCE = FALSE
        ```

        A coluna sequer é parâmetro deste método: não há como preenchê-la
        por descuido de chamador, porque não existe caminho para isso.
        """
        if (
            self._attempt_under_scope(
                control_principal_ref=control_principal_ref,
                schedule_id=schedule_id,
                attempt_id=attempt_id,
            )
            is None
        ):
            raise OrchestrationScopeViolationError(
                message="tentativa inexistente neste Schedule sob este principal",
                detail={"schedule_id": str(schedule_id), "attempt_id": str(attempt_id)},
            )
        atribuicao = HandoffAttribution(
            attempt_id=attempt_id,
            role=role,
            declared_provider_id=declared_provider_id,
            declared_model_id=declared_model_id,
            declared_instance_id=declared_instance_id,
            declared_at=declared_at,
            self_declared=True,
        )
        self._session.add(atribuicao)
        self._session.flush()
        return atribuicao

    def get_handoff_result(
        self, *, control_principal_ref: str, schedule_id: uuid.UUID, attempt_id: uuid.UUID
    ) -> HandoffResult | None:
        return self._session.scalars(
            sa.select(HandoffResult)
            .join(HandoffAttempt, HandoffAttempt.id == HandoffResult.attempt_id)
            .join(Schedule, Schedule.id == HandoffAttempt.schedule_id)
            .where(
                HandoffResult.attempt_id == attempt_id,
                HandoffAttempt.schedule_id == schedule_id,
                Schedule.id == schedule_id,
                Schedule.control_principal_ref == control_principal_ref,
            )
        ).one_or_none()

    def get_handoff_attribution(
        self, *, control_principal_ref: str, schedule_id: uuid.UUID, attempt_id: uuid.UUID
    ) -> HandoffAttribution | None:
        return self._session.scalars(
            sa.select(HandoffAttribution)
            .join(HandoffAttempt, HandoffAttempt.id == HandoffAttribution.attempt_id)
            .join(Schedule, Schedule.id == HandoffAttempt.schedule_id)
            .where(
                HandoffAttribution.attempt_id == attempt_id,
                HandoffAttempt.schedule_id == schedule_id,
                Schedule.id == schedule_id,
                Schedule.control_principal_ref == control_principal_ref,
            )
        ).one_or_none()

    def update_handoff_record(self, *, record_id: uuid.UUID) -> None:
        """Recusa explícita — segunda camada do append-only da E7.2."""
        raise HandoffRecordImmutableError(
            message="veredito e atribuição são append-only: UPDATE recusado",
            detail={"record_id": str(record_id)},
        )

    def delete_handoff_record(self, *, record_id: uuid.UUID) -> None:
        """Recusa explícita — segunda camada do append-only da E7.2."""
        raise HandoffRecordImmutableError(
            message="veredito e atribuição são append-only: DELETE recusado",
            detail={"record_id": str(record_id)},
        )

    # --- E7.3: delegação, controle, observação e parecer --------------------
    #
    # ```text
    # NO_AUTHORIZATION_DERIVED_FROM_THE_AUTHORIZED_OBJECT
    # ```
    #
    # Todo método recebe `control_principal_ref` E o `schedule_id` declarado
    # pelo chamador, como no corretivo R2 da E7.2.

    def expire_stale_delegations(
        self, *, control_principal_ref: str, schedule_id: uuid.UUID, step_id: uuid.UUID
    ) -> int:
        """Materializa `ACTIVE` vencida como `EXPIRED`, sob o lock corrente.

        ```text
        EXPIRY_SWEEPER = NOT_IMPLEMENTED
        EXPIRED = MATERIALIZED_SYNCHRONOUSLY
        ```

        Sem isto, o índice parcial aprisionaria a Step: uma delegação
        vencida continuaria `active` no banco e impediria conceder outra.
        """
        if (
            self.get_step(
                control_principal_ref=control_principal_ref,
                schedule_id=schedule_id,
                step_id=step_id,
            )
            is None
        ):
            raise OrchestrationScopeViolationError(
                message="etapa inexistente neste Schedule sob este principal",
                detail={"schedule_id": str(schedule_id), "step_id": str(step_id)},
            )
        resultado = self._session.execute(
            sa.text(
                "UPDATE service_delegations SET state = 'expired' "
                "WHERE schedule_id = :s AND step_id = :p "
                "AND state = 'active' AND valid_until <= now()"
            ),
            {"s": schedule_id, "p": step_id},
        )
        self._session.flush()
        return int(cast("sa.CursorResult[object]", resultado).rowcount or 0)

    def revoke_active_delegations(
        self,
        *,
        control_principal_ref: str,
        schedule_id: uuid.UUID,
        step_id: uuid.UUID,
        scope: str,
    ) -> int:
        """Revoga a `ACTIVE` corrente antes de conceder binding novo."""
        if (
            self.get_step(
                control_principal_ref=control_principal_ref,
                schedule_id=schedule_id,
                step_id=step_id,
            )
            is None
        ):
            raise OrchestrationScopeViolationError(
                message="etapa inexistente neste Schedule sob este principal",
                detail={"schedule_id": str(schedule_id), "step_id": str(step_id)},
            )
        resultado = self._session.execute(
            sa.text(
                "UPDATE service_delegations SET state = 'revoked' "
                "WHERE schedule_id = :s AND step_id = :p AND scope = :c AND state = 'active'"
            ),
            {"s": schedule_id, "p": step_id, "c": scope},
        )
        self._session.flush()
        return int(cast("sa.CursorResult[object]", resultado).rowcount or 0)

    def create_delegation(
        self,
        *,
        control_principal_ref: str,
        delegation_id: uuid.UUID,
        schedule_id: uuid.UUID,
        step_id: uuid.UUID,
        content_sha256: str,
        scope: str,
        granted_by_principal_ref: str,
        valid_until: datetime,
    ) -> ServiceDelegation:
        if (
            self.get_step(
                control_principal_ref=control_principal_ref,
                schedule_id=schedule_id,
                step_id=step_id,
            )
            is None
        ):
            raise OrchestrationScopeViolationError(
                message="etapa inexistente neste Schedule sob este principal",
                detail={"schedule_id": str(schedule_id), "step_id": str(step_id)},
            )
        delegacao = ServiceDelegation(
            id=delegation_id,
            schedule_id=schedule_id,
            step_id=step_id,
            content_sha256=content_sha256,
            scope=scope,
            granted_by_principal_ref=granted_by_principal_ref,
            valid_until=valid_until,
            state=DelegationState.ACTIVE,
        )
        self._session.add(delegacao)
        self._session.flush()
        return delegacao

    def get_active_delegation(
        self,
        *,
        control_principal_ref: str,
        schedule_id: uuid.UUID,
        step_id: uuid.UUID,
        scope: str,
    ) -> ServiceDelegation | None:
        """Delegação `ACTIVE` da trinca, bloqueada. Não consome."""
        return self._session.scalars(
            sa.select(ServiceDelegation)
            .join(Schedule, Schedule.id == ServiceDelegation.schedule_id)
            .where(
                ServiceDelegation.schedule_id == schedule_id,
                ServiceDelegation.step_id == step_id,
                ServiceDelegation.scope == scope,
                ServiceDelegation.state == DelegationState.ACTIVE,
                Schedule.id == schedule_id,
                Schedule.control_principal_ref == control_principal_ref,
            )
            .with_for_update(of=ServiceDelegation)
        ).one_or_none()

    def get_delegation(
        self, *, control_principal_ref: str, schedule_id: uuid.UUID, delegation_id: uuid.UUID
    ) -> ServiceDelegation | None:
        return self._session.scalars(
            sa.select(ServiceDelegation)
            .join(Schedule, Schedule.id == ServiceDelegation.schedule_id)
            .where(
                ServiceDelegation.id == delegation_id,
                ServiceDelegation.schedule_id == schedule_id,
                Schedule.id == schedule_id,
                Schedule.control_principal_ref == control_principal_ref,
            )
        ).one_or_none()

    def consume_delegation(
        self,
        *,
        control_principal_ref: str,
        schedule_id: uuid.UUID,
        step_id: uuid.UUID,
        delegation_id: uuid.UUID,
        content_sha256: str,
        scope: str,
        attempt_id: uuid.UUID,
    ) -> bool:
        """Consumo atômico e de uso único, revalidando **todo** o vínculo.

        ```text
        DELEGATION_CONSUMPTION = ATOMIC + SINGLE_USE + HASH_BOUND
        ```

        O `UPDATE` condicional é a garantia: `state='active'`,
        `valid_until > now()` e o `content_sha256` entram na cláusula, de
        modo que dois despachos concorrentes não conseguem consumir a mesma
        linha e conteúdo alterado simplesmente não casa.

        Zero linhas afetadas é recusa — não erro de servidor.
        """
        if (
            self.get_step(
                control_principal_ref=control_principal_ref,
                schedule_id=schedule_id,
                step_id=step_id,
            )
            is None
        ):
            raise OrchestrationScopeViolationError(
                message="etapa inexistente neste Schedule sob este principal",
                detail={"schedule_id": str(schedule_id), "step_id": str(step_id)},
            )
        resultado = self._session.execute(
            sa.text(
                "UPDATE service_delegations "
                "SET state = 'consumed', consumed_at = now(), consumed_by_attempt_id = :a "
                "WHERE id = :d AND schedule_id = :s AND step_id = :p AND scope = :c "
                "AND content_sha256 = :h AND state = 'active' AND valid_until > now()"
            ),
            {
                "a": attempt_id,
                "d": delegation_id,
                "s": schedule_id,
                "p": step_id,
                "c": scope,
                "h": content_sha256,
            },
        )
        self._session.flush()
        return bool(cast("sa.CursorResult[object]", resultado).rowcount)

    def list_delegations(
        self, *, control_principal_ref: str, schedule_id: uuid.UUID
    ) -> list[ServiceDelegation]:
        return list(
            self._session.scalars(
                sa.select(ServiceDelegation)
                .join(Schedule, Schedule.id == ServiceDelegation.schedule_id)
                .where(
                    ServiceDelegation.schedule_id == schedule_id,
                    Schedule.id == schedule_id,
                    Schedule.control_principal_ref == control_principal_ref,
                )
                .order_by(ServiceDelegation.created_at.asc(), ServiceDelegation.id.asc())
            ).all()
        )

    def create_control_event(
        self,
        *,
        event_id: uuid.UUID,
        control_principal_ref: str,
        schedule_id: uuid.UUID,
        step_id: uuid.UUID | None,
        event_kind: ControlEventKind,
        reason_code: ControlReasonCode,
        stop_condition_category: StopConditionCategory | None,
        declared_by_principal_ref: str,
        occurred_at: datetime,
    ) -> OrchestrationControlEvent:
        if (
            self.get_schedule(control_principal_ref=control_principal_ref, schedule_id=schedule_id)
            is None
        ):
            raise OrchestrationScopeViolationError(
                message="Schedule inexistente sob este principal de controle",
                detail={"schedule_id": str(schedule_id)},
            )
        evento = OrchestrationControlEvent(
            id=event_id,
            schedule_id=schedule_id,
            step_id=step_id,
            event_kind=event_kind,
            reason_code=reason_code,
            stop_condition_category=stop_condition_category,
            declared_by_principal_ref=declared_by_principal_ref,
            occurred_at=occurred_at,
        )
        self._session.add(evento)
        self._session.flush()
        return evento

    def list_control_events(
        self, *, control_principal_ref: str, schedule_id: uuid.UUID
    ) -> list[OrchestrationControlEvent]:
        return list(
            self._session.scalars(
                sa.select(OrchestrationControlEvent)
                .join(Schedule, Schedule.id == OrchestrationControlEvent.schedule_id)
                .where(
                    OrchestrationControlEvent.schedule_id == schedule_id,
                    Schedule.id == schedule_id,
                    Schedule.control_principal_ref == control_principal_ref,
                )
                .order_by(
                    OrchestrationControlEvent.occurred_at.asc(),
                    OrchestrationControlEvent.id.asc(),
                )
            ).all()
        )

    def count_open_pause_events(
        self, *, control_principal_ref: str, schedule_id: uuid.UUID, reason_code: ControlReasonCode
    ) -> int:
        """Pausas já registradas desde a última retomada.

        Serve à regra "repetir enquanto PAUSED não duplica evento": uma
        segunda tentativa bloqueada pelo mesmo motivo não grava de novo.
        """
        ultimo_resume = (
            sa.select(sa.func.max(OrchestrationControlEvent.occurred_at))
            .where(
                OrchestrationControlEvent.schedule_id == schedule_id,
                OrchestrationControlEvent.event_kind == ControlEventKind.RESUMED,
            )
            .scalar_subquery()
        )
        return int(
            self._session.execute(
                sa.select(sa.func.count())
                .select_from(OrchestrationControlEvent)
                .join(Schedule, Schedule.id == OrchestrationControlEvent.schedule_id)
                .where(
                    OrchestrationControlEvent.schedule_id == schedule_id,
                    OrchestrationControlEvent.event_kind == ControlEventKind.PAUSED,
                    OrchestrationControlEvent.reason_code == reason_code,
                    sa.or_(
                        ultimo_resume.is_(None),
                        OrchestrationControlEvent.occurred_at > ultimo_resume,
                    ),
                    Schedule.control_principal_ref == control_principal_ref,
                )
            ).scalar_one()
        )

    def list_open_attempts_of_schedule(
        self, *, control_principal_ref: str, schedule_id: uuid.UUID
    ) -> list[HandoffAttempt]:
        """Tentativas `OPEN` do trabalho, em ordem estável."""
        return list(
            self._session.scalars(
                sa.select(HandoffAttempt)
                .join(Schedule, Schedule.id == HandoffAttempt.schedule_id)
                .where(
                    HandoffAttempt.schedule_id == schedule_id,
                    HandoffAttempt.state == AttemptState.OPEN,
                    Schedule.id == schedule_id,
                    Schedule.control_principal_ref == control_principal_ref,
                )
                .order_by(HandoffAttempt.created_at.asc(), HandoffAttempt.id.asc())
                .with_for_update(of=HandoffAttempt)
            ).all()
        )

    def all_steps_returned(self, *, control_principal_ref: str, schedule_id: uuid.UUID) -> bool:
        """Todas as etapas em `RETURNED`? Base da conclusão do Schedule."""
        pendentes = self._session.execute(
            sa.select(sa.func.count())
            .select_from(ScheduleStep)
            .join(Schedule, Schedule.id == ScheduleStep.schedule_id)
            .where(
                ScheduleStep.schedule_id == schedule_id,
                ScheduleStep.state != StepState.RETURNED,
                Schedule.control_principal_ref == control_principal_ref,
            )
        ).scalar_one()
        return int(pendentes) == 0

    def get_last_attribution_before(
        self,
        *,
        control_principal_ref: str,
        schedule_id: uuid.UUID,
        step_id: uuid.UUID,
        attempt_id: uuid.UUID,
    ) -> HandoffAttribution | None:
        """Atribuição da tentativa anterior da mesma etapa.

        Base da observação de troca de provedor. A ordem é por
        `created_at` da tentativa, e o corte exclui a tentativa atual.
        """
        atual = self._session.scalars(
            sa.select(HandoffAttempt.created_at).where(HandoffAttempt.id == attempt_id)
        ).one_or_none()
        if atual is None:
            return None
        return self._session.scalars(
            sa.select(HandoffAttribution)
            .join(HandoffAttempt, HandoffAttempt.id == HandoffAttribution.attempt_id)
            .join(Schedule, Schedule.id == HandoffAttempt.schedule_id)
            .where(
                HandoffAttempt.step_id == step_id,
                HandoffAttempt.schedule_id == schedule_id,
                HandoffAttempt.id != attempt_id,
                HandoffAttempt.created_at <= atual,
                Schedule.control_principal_ref == control_principal_ref,
            )
            .order_by(HandoffAttempt.created_at.desc(), HandoffAttempt.id.desc())
            .limit(1)
        ).one_or_none()

    def create_execution_observation(
        self,
        *,
        control_principal_ref: str,
        schedule_id: uuid.UUID,
        step_id: uuid.UUID,
        observation_kind: ObservationKind,
        previous_attempt_id: uuid.UUID,
        current_attempt_id: uuid.UUID,
        previous_declared_provider_id: str | None,
        current_declared_provider_id: str | None,
        observed_at: datetime,
    ) -> ExecutionObservation:
        if (
            self.get_step(
                control_principal_ref=control_principal_ref,
                schedule_id=schedule_id,
                step_id=step_id,
            )
            is None
        ):
            raise OrchestrationScopeViolationError(
                message="etapa inexistente neste Schedule sob este principal",
                detail={"schedule_id": str(schedule_id), "step_id": str(step_id)},
            )
        observacao = ExecutionObservation(
            schedule_id=schedule_id,
            step_id=step_id,
            observation_kind=observation_kind,
            previous_attempt_id=previous_attempt_id,
            current_attempt_id=current_attempt_id,
            previous_declared_provider_id=previous_declared_provider_id,
            current_declared_provider_id=current_declared_provider_id,
            self_declared=True,
            observed_at=observed_at,
        )
        self._session.add(observacao)
        self._session.flush()
        return observacao

    def list_execution_observations(
        self, *, control_principal_ref: str, schedule_id: uuid.UUID
    ) -> list[ExecutionObservation]:
        return list(
            self._session.scalars(
                sa.select(ExecutionObservation)
                .join(Schedule, Schedule.id == ExecutionObservation.schedule_id)
                .where(
                    ExecutionObservation.schedule_id == schedule_id,
                    Schedule.id == schedule_id,
                    Schedule.control_principal_ref == control_principal_ref,
                )
                .order_by(ExecutionObservation.observed_at.asc(), ExecutionObservation.id.asc())
            ).all()
        )

    def get_result_for_audit(
        self, *, control_principal_ref: str, schedule_id: uuid.UUID, attempt_id: uuid.UUID
    ) -> HandoffResult | None:
        """Resolve o resultado por join até Attempt e Schedule declarados."""
        return self.get_handoff_result(
            control_principal_ref=control_principal_ref,
            schedule_id=schedule_id,
            attempt_id=attempt_id,
        )

    def create_audit_opinion(
        self,
        *,
        opinion_id: uuid.UUID,
        control_principal_ref: str,
        schedule_id: uuid.UUID,
        handoff_result_id: uuid.UUID,
        opinion: AuditOpinionKind,
        reason_codes: tuple[str, ...],
        auditor_execution_ref: str,
        issued_by_principal_ref: str,
        issued_at: datetime,
    ) -> AuditOpinion:
        """Única escrita permitida à execução auditora.

        ```text
        AUDITOR_WRITE_ON_AUDITED_ARTIFACT = FORBIDDEN
        ```
        """
        pertence = self._session.scalars(
            sa.select(HandoffResult.id)
            .join(HandoffAttempt, HandoffAttempt.id == HandoffResult.attempt_id)
            .join(Schedule, Schedule.id == HandoffAttempt.schedule_id)
            .where(
                HandoffResult.id == handoff_result_id,
                HandoffAttempt.schedule_id == schedule_id,
                Schedule.id == schedule_id,
                Schedule.control_principal_ref == control_principal_ref,
            )
        ).one_or_none()
        if pertence is None:
            raise OrchestrationScopeViolationError(
                message="resultado inexistente neste Schedule sob este principal",
                detail={"schedule_id": str(schedule_id), "result_id": str(handoff_result_id)},
            )
        parecer = AuditOpinion(
            id=opinion_id,
            handoff_result_id=handoff_result_id,
            opinion=opinion,
            reason_codes=reason_codes,
            auditor_execution_ref=auditor_execution_ref,
            issued_by_principal_ref=issued_by_principal_ref,
            issued_at=issued_at,
        )
        self._session.add(parecer)
        self._session.flush()
        return parecer

    def list_audit_opinions(
        self, *, control_principal_ref: str, schedule_id: uuid.UUID
    ) -> list[AuditOpinion]:
        return list(
            self._session.scalars(
                sa.select(AuditOpinion)
                .join(HandoffResult, HandoffResult.id == AuditOpinion.handoff_result_id)
                .join(HandoffAttempt, HandoffAttempt.id == HandoffResult.attempt_id)
                .join(Schedule, Schedule.id == HandoffAttempt.schedule_id)
                .where(
                    HandoffAttempt.schedule_id == schedule_id,
                    Schedule.id == schedule_id,
                    Schedule.control_principal_ref == control_principal_ref,
                )
                .order_by(AuditOpinion.issued_at.asc(), AuditOpinion.id.asc())
            ).all()
        )

    def update_governance_record(self, *, record_id: uuid.UUID) -> None:
        """Recusa explícita — evento, observação e parecer são append-only."""
        raise GovernanceRecordImmutableError(
            message="registro de governança é append-only: UPDATE recusado",
            detail={"record_id": str(record_id)},
        )

    def delete_governance_record(self, *, record_id: uuid.UUID) -> None:
        """Recusa explícita — inclui delegação, que não é deletável."""
        raise GovernanceRecordImmutableError(
            message="registro de governança é append-only: DELETE recusado",
            detail={"record_id": str(record_id)},
        )

    def get_control_event(
        self, *, control_principal_ref: str, schedule_id: uuid.UUID, event_id: uuid.UUID
    ) -> OrchestrationControlEvent | None:
        """O evento EXATO, por id — base do replay fiel.

        ```text
        REPLAY_RETURNS_THE_ORIGINAL_RECORD
        ```

        Devolver "o último evento do Schedule" faria o replay de uma pausa
        responder com a retomada que veio depois. O recibo guarda o id, e
        é por ele que se lê.
        """
        return self._session.scalars(
            sa.select(OrchestrationControlEvent)
            .join(Schedule, Schedule.id == OrchestrationControlEvent.schedule_id)
            .where(
                OrchestrationControlEvent.id == event_id,
                OrchestrationControlEvent.schedule_id == schedule_id,
                Schedule.id == schedule_id,
                Schedule.control_principal_ref == control_principal_ref,
            )
        ).one_or_none()

    def get_audit_opinion(
        self, *, control_principal_ref: str, schedule_id: uuid.UUID, opinion_id: uuid.UUID
    ) -> AuditOpinion | None:
        """O parecer EXATO, por id. Um `dissent` não pode virar `concur`."""
        return self._session.scalars(
            sa.select(AuditOpinion)
            .join(HandoffResult, HandoffResult.id == AuditOpinion.handoff_result_id)
            .join(HandoffAttempt, HandoffAttempt.id == HandoffResult.attempt_id)
            .join(Schedule, Schedule.id == HandoffAttempt.schedule_id)
            .where(
                AuditOpinion.id == opinion_id,
                HandoffAttempt.schedule_id == schedule_id,
                Schedule.id == schedule_id,
                Schedule.control_principal_ref == control_principal_ref,
            )
        ).one_or_none()
