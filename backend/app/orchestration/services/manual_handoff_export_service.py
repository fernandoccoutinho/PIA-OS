"""
`ManualHandoffExportService` — produtor único de `ExportedHandoff` (`E7.2`).

```text
SEALED != DISPATCHED
EXPORT = SEAL + TRANSPORT + TRANSITIONS
```

A E7.1 selava e parava: a etapa continuava `PENDING` porque nada havia
atravessado fronteira alguma. A E7.2 traz o transporte manual, e por isso
`DISPATCHED` e `AWAITING_RETURN` finalmente têm produtor.

O `seal_step` da E7.1 **não** foi rebatizado. Ele continua significando o
que significava; este serviço o compõe e acrescenta o que é seu. Mudar o
sentido do método antigo faria toda a evidência da E7.1 passar a descrever
outra coisa.

```text
LOCK_ORDER = Schedule -> Step(s) -> Attempt
ONE_OPEN_ATTEMPT_PER_STEP = TRUE
REJECTED_RESULT BLOCKS ADVANCE
```
"""

import uuid
from dataclasses import dataclass

from app.orchestration.errors.exceptions import (
    DispatchBlockedError,
    OrchestrationLifecycleViolationError,
    OrchestrationScopeViolationError,
)
from app.orchestration.models.enums import (
    EXECUTABLE_HANDOFF_MODES,
    AttemptState,
    ControlReasonCode,
    GateReasonCode,
    ScheduleState,
    StepState,
)
from app.orchestration.ports.gate import GateAuthorizationPort
from app.orchestration.ports.transport import ExportedHandoff, HandoffTransportPort
from app.orchestration.repositories.orchestration_repository import OrchestrationRepository
from app.orchestration.schemas.envelope import (
    ENVELOPE_VERSION,
    GATE_SCOPE_DISPATCH,
    EnvelopeContent,
    gate_requirement,
)
from app.orchestration.services.control_service import ControlService
from app.orchestration.services.handoff_service import HandoffService


@dataclass(frozen=True)
class DispatchAuthorized:
    """Preflight aprovado. Congelado, e produzido **só** pelo preflight.

    ```text
    NO_PUBLIC_OBJECT_ACCEPTS_AN_INVENTED_AUTHORIZED_FLAG
    ```

    Não existe construtor público que receba `authorized=True` de um
    chamador: o objeto só nasce de `_preflight()`, e o caminho autorizado
    revalida o vínculo no `UPDATE` condicional antes de qualquer efeito.
    """

    content_sha256: str
    delegation_id: uuid.UUID | None
    first_dispatch: bool


@dataclass(frozen=True)
class DispatchBlocked:
    """Preflight recusado, com o motivo tipado que vira evento."""

    reason_code: ControlReasonCode
    content_sha256: str | None


@dataclass(frozen=True)
class ExportOutcome:
    """O que uma exportação produz. Congelado e sem instância ORM."""

    exported: ExportedHandoff
    step_state: StepState
    attempt_state: AttemptState


class ManualHandoffExportService:
    """Sela, abre tentativa, transporta manualmente e move a etapa."""

    def __init__(
        self,
        repository: OrchestrationRepository,
        handoff_service: HandoffService,
        transport: HandoffTransportPort,
        human_gate: GateAuthorizationPort | None = None,
        control_service: ControlService | None = None,
    ) -> None:
        self._repository = repository
        self._handoff_service = handoff_service
        self._transport = transport
        self._human_gate = human_gate
        self._control_service = control_service

    # --- fase 1: preflight sob locks ---------------------------------------

    def preflight(
        self,
        *,
        control_principal_ref: str,
        schedule_id: uuid.UUID,
        step_id: uuid.UUID,
    ) -> DispatchAuthorized | DispatchBlocked:
        """Avalia tudo **antes** de qualquer linha ser criada.

        ```text
        GUARD_BEFORE_ROW_CREATION != GUARD_BEFORE_EFFECT
        LOCK_ORDER = Schedule -> Step(s) -> Attempt(s)
        ```

        `seal_step_for_export()` cria Attempt e SealReceipt. Avaliar depois
        dele faria uma recusa depender de rollback em vez de não ter
        escrito nada — e a diferença aparece em id consumido, em log e em
        qualquer réplica.
        """
        agenda = self._repository.lock_schedule(
            control_principal_ref=control_principal_ref, schedule_id=schedule_id
        )
        if agenda is None:
            raise OrchestrationScopeViolationError(
                message="Schedule inexistente sob este principal de controle",
                detail={"schedule_id": str(schedule_id)},
            )
        if agenda.state in (ScheduleState.STOPPED, ScheduleState.CANCELLED):
            # Terminal recusa SEM nova escrita: registrar de novo o que já
            # está registrado inflaria o histórico a cada tentativa.
            raise OrchestrationLifecycleViolationError(
                message=f"Schedule {agenda.state.value} não despacha",
                detail={"current_state": agenda.state.value},
            )
        if agenda.state is ScheduleState.PAUSED:
            raise OrchestrationLifecycleViolationError(
                message="Schedule PAUSED exige retomada explícita antes de exportar",
                detail={"current_state": agenda.state.value},
            )
        if agenda.state is not ScheduleState.ACTIVE:
            raise OrchestrationLifecycleViolationError(
                message=f"exportação exige Schedule ACTIVE; estado atual {agenda.state.value}",
                detail={"current_state": agenda.state.value},
            )
        if agenda.execution_mode not in EXECUTABLE_HANDOFF_MODES:
            raise OrchestrationLifecycleViolationError(
                message=f"modo {agenda.execution_mode.value!r} não é executável nesta entrega",
                detail={"execution_mode": agenda.execution_mode.value},
            )

        etapa = self._repository.lock_step(
            control_principal_ref=control_principal_ref,
            schedule_id=schedule_id,
            step_id=step_id,
        )
        if etapa is None:
            raise OrchestrationScopeViolationError(
                message="etapa inexistente neste Schedule sob este principal",
                detail={"schedule_id": str(schedule_id), "step_id": str(step_id)},
            )
        if etapa.state is StepState.CANCELLED:
            raise OrchestrationLifecycleViolationError(
                message="etapa cancelada não despacha",
                detail={"current_state": etapa.state.value},
            )
        pendentes = self._repository.list_unreturned_predecessors(
            control_principal_ref=control_principal_ref,
            schedule_id=schedule_id,
            position=etapa.position,
        )
        if pendentes:
            raise OrchestrationLifecycleViolationError(
                message=(
                    "exportação exige todas as posições anteriores RETURNED; "
                    f"pendentes: {pendentes}"
                ),
                detail={"position": etapa.position, "unreturned_positions": pendentes},
            )
        aberta = self._repository.get_open_attempt(
            control_principal_ref=control_principal_ref,
            schedule_id=schedule_id,
            step_id=step_id,
        )
        if aberta is not None:
            raise OrchestrationLifecycleViolationError(
                message="já existe tentativa OPEN nesta etapa; importe ou rejeite antes",
                detail={"open_attempt_id": str(aberta.id)},
            )
        if etapa.state not in (StepState.PENDING, StepState.AWAITING_RETURN):
            raise OrchestrationLifecycleViolationError(
                message=f"exportação não admite etapa em {etapa.state.value}",
                detail={"current_state": etapa.state.value},
            )

        conteudo = self._handoff_service.build_envelope_content(
            control_principal_ref=control_principal_ref,
            schedule_id=schedule_id,
            step_id=step_id,
        )
        hash_corrente = conteudo.content_sha256()
        primeira = etapa.state is StepState.PENDING

        exigencia = gate_requirement(tuple(etapa.constraints))
        if exigencia is None:
            # Ausência de marcador = retrocompatível. Nenhuma delegação é
            # exigida, e nada de novo é gravado.
            return DispatchAuthorized(
                content_sha256=hash_corrente, delegation_id=None, first_dispatch=primeira
            )

        if exigencia.requires_human:
            porta = self._human_gate
            decisao = (
                porta.authorize(
                    gate_scope=exigencia.scope,
                    schedule_id=schedule_id,
                    step_id=step_id,
                    content_sha256=hash_corrente,
                )
                if porta is not None
                else None
            )
            if decisao is None or not decisao.granted:
                return DispatchBlocked(
                    reason_code=ControlReasonCode.HUMAN_GATE_UNAVAILABLE,
                    content_sha256=hash_corrente,
                )
            if decisao.reason_code is not GateReasonCode.AUTHORIZED:  # pragma: no cover
                return DispatchBlocked(
                    reason_code=ControlReasonCode.HUMAN_GATE_UNAVAILABLE,
                    content_sha256=hash_corrente,
                )

        self._repository.expire_stale_delegations(
            control_principal_ref=control_principal_ref,
            schedule_id=schedule_id,
            step_id=step_id,
        )
        delegacao = self._repository.get_active_delegation(
            control_principal_ref=control_principal_ref,
            schedule_id=schedule_id,
            step_id=step_id,
            scope=exigencia.scope,
        )
        if delegacao is None:
            return DispatchBlocked(
                reason_code=ControlReasonCode.DELEGATION_MISSING,
                content_sha256=hash_corrente,
            )
        if delegacao.content_sha256 != hash_corrente:
            # ```text
            # CONTENT_HASH_CHANGED -> INVALID
            # ```
            return DispatchBlocked(
                reason_code=ControlReasonCode.DELEGATION_CONTENT_CHANGED,
                content_sha256=hash_corrente,
            )
        return DispatchAuthorized(
            content_sha256=hash_corrente,
            delegation_id=delegacao.id,
            first_dispatch=primeira,
        )

    def register_block(
        self,
        *,
        control_principal_ref: str,
        schedule_id: uuid.UUID,
        step_id: uuid.UUID,
        blocked: DispatchBlocked,
    ) -> None:
        """Persiste `ACTIVE -> PAUSED` e o evento, e então recusa.

        ```text
        BLOCKED_GATE_PERSISTS_PAUSE_WITH_ZERO_COMMAND_EFFECT
        ```

        A pausa é gravada **antes** da exceção, e o handler commita antes
        de responder 409. Levantar primeiro faria o `rollback` genérico
        apagar exatamente a pausa que a prova precisa observar.
        """
        if self._control_service is not None:
            self._control_service.register_pause(
                control_principal_ref=control_principal_ref,
                schedule_id=schedule_id,
                step_id=step_id,
                reason_code=blocked.reason_code,
            )
        raise DispatchBlockedError(
            message=f"despacho bloqueado: {blocked.reason_code.value}",
            detail={
                "schedule_id": str(schedule_id),
                "step_id": str(step_id),
                "reason_code": blocked.reason_code.value,
            },
        )

    def export_step(
        self,
        *,
        attempt_id: uuid.UUID,
        control_principal_ref: str,
        schedule_id: uuid.UUID,
        step_id: uuid.UUID,
        sealer_ref: str,
        authorization: DispatchAuthorized | None = None,
    ) -> ExportOutcome:
        """Exporta uma etapa, na ordem de locks e sob todas as pré-condições.

        As duas transições ocorrem na mesma transação e o estado confirmado
        ao cliente é `AWAITING_RETURN`: `DISPATCHED` é um instante, não um
        lugar onde o sistema descansa. Persistir a parada intermediária
        criaria um estado que ninguém consegue observar e do qual ninguém
        sabe sair.
        """
        # Fase 2. A autorização vem da fase 1; se o chamador não a
        # forneceu, ela é refeita aqui — nunca presumida.
        autorizacao = authorization
        if autorizacao is None:
            resultado = self.preflight(
                control_principal_ref=control_principal_ref,
                schedule_id=schedule_id,
                step_id=step_id,
            )
            if isinstance(resultado, DispatchBlocked):
                self.register_block(
                    control_principal_ref=control_principal_ref,
                    schedule_id=schedule_id,
                    step_id=step_id,
                    blocked=resultado,
                )
                raise AssertionError("register_block sempre levanta")  # pragma: no cover
            autorizacao = resultado

        etapa = self._repository.lock_step(
            control_principal_ref=control_principal_ref,
            schedule_id=schedule_id,
            step_id=step_id,
        )
        if etapa is None:  # pragma: no cover - o preflight já resolveu o escopo
            raise OrchestrationScopeViolationError(
                message="etapa inexistente neste Schedule sob este principal",
                detail={"schedule_id": str(schedule_id), "step_id": str(step_id)},
            )
        primeira_exportacao = autorizacao.first_dispatch

        # ```text
        # CLAIM_BEFORE_ALLOWED_EFFECT = TRUE
        # DELEGATION_CONSUMPTION = ATOMIC + SINGLE_USE + HASH_BOUND
        # ```
        #
        # O consumo vem ANTES da Attempt e na MESMA transação: a FK
        # composta é `DEFERRABLE INITIALLY DEFERRED`, então o commit só
        # passa se a Attempt correspondente tiver sido criada. Falha de
        # transporte reverte os dois.
        #
        # O `UPDATE` condicional revalida `state='active'`, a validade e o
        # `content_sha256` — a autorização recebida é ponto de partida, e
        # nunca substitui a revalidação no ponto material.
        if autorizacao.delegation_id is not None:
            consumida = self._repository.consume_delegation(
                control_principal_ref=control_principal_ref,
                schedule_id=schedule_id,
                step_id=step_id,
                delegation_id=autorizacao.delegation_id,
                content_sha256=autorizacao.content_sha256,
                scope=GATE_SCOPE_DISPATCH,
                attempt_id=attempt_id,
            )
            if not consumida:
                raise DispatchBlockedError(
                    message="delegação deixou de ser consumível entre o preflight e o efeito",
                    detail={
                        "schedule_id": str(schedule_id),
                        "step_id": str(step_id),
                        "delegation_id": str(autorizacao.delegation_id),
                    },
                )

        selado = self._handoff_service.seal_step_for_export(
            attempt_id=attempt_id,
            control_principal_ref=control_principal_ref,
            schedule_id=schedule_id,
            step_id=step_id,
            sealer_ref=sealer_ref,
        )

        envelope = EnvelopeContent(
            envelope_version=ENVELOPE_VERSION,
            schedule_id=schedule_id,
            step_id=step_id,
            role=etapa.role,
            instruction_ref=etapa.instruction_ref,
            context_refs=tuple(etapa.context_refs),
            expected_output_contract=etapa.expected_output_contract,
            constraints=tuple(etapa.constraints),
        )
        repasse = ExportedHandoff(
            schedule_id=schedule_id,
            step_id=step_id,
            attempt_id=selado.attempt_id,
            attempt_number=selado.attempt_number,
            receipt_id=selado.receipt_id,
            content_sha256=selado.content_sha256,
            sealed_at=selado.sealed_at,
            envelope=envelope,
        )
        entregue = self._transport.export(repasse)

        if primeira_exportacao:
            self._repository.set_step_state(
                control_principal_ref=control_principal_ref,
                schedule_id=schedule_id,
                step_id=step_id,
                state=StepState.DISPATCHED,
            )
        self._repository.set_step_state(
            control_principal_ref=control_principal_ref,
            schedule_id=schedule_id,
            step_id=step_id,
            state=StepState.AWAITING_RETURN,
        )
        return ExportOutcome(
            exported=entregue,
            step_state=StepState.AWAITING_RETURN,
            attempt_state=AttemptState.OPEN,
        )
