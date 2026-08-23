"""
API mínima da orquestração multi-IA (`E7.2`) — cinco rotas sob `/api/v1`.

```text
ROUTE_AND_AUTH_SAME_COMMIT = TRUE
BUSINESS_ROUTE_WITHOUT_FAIL_CLOSED_AUTH = UNIMPORTABLE
API_GUARD != DOMAIN_GUARANTEE
```

`_assert_every_route_is_protected()` roda **no import**, no precedente da
E6.2: remover a dependency não produz um endpoint aberto, produz um
`ImportError` que derruba a aplicação. Uma guarda que só reprova em teste
permite que a versão insegura exista e rode.

A guarda da rota não é a garantia do domínio. O repositório impõe
principal **e** Schedule declarado em toda leitura e escrita, e continua
impondo se alguém chamar o serviço sem passar por aqui.

```text
control_principal_ref = sealer_ref = technical_principal_ref = str(principal.id)
```

Nunca do cliente. O handler não aceita esses campos, e os DTOs de entrada
recusam campo desconhecido — enviar `control_principal_ref` é 422, não um
201 que ignora silenciosamente.
"""

import inspect
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from app.api.dependencies import get_db_session, require_orchestration_operate_access
from app.api.responses import SuccessResponse
from app.docs.responses import response_401, response_403, response_404, response_422, response_500
from app.docs.tags import TAG_ORCHESTRATION
from app.orchestration.adapters.deny_all_human_gate import DenyAllHumanGate
from app.orchestration.adapters.manual_transport import ManualTransport
from app.orchestration.errors.exceptions import (
    DispatchBlockedError,
    OrchestrationContractViolationError,
)
from app.orchestration.models.enums import CommandOperation
from app.orchestration.ports.transport import RawReturn
from app.orchestration.repositories.orchestration_repository import OrchestrationRepository
from app.orchestration.schemas.envelope import ContextRef, ScheduleDraft, StepDraft
from app.orchestration.services.audit_service import AuditService
from app.orchestration.services.command_receipt_service import CommandReceiptService
from app.orchestration.services.control_service import ControlService
from app.orchestration.services.delegation_service import DelegationService
from app.orchestration.services.handoff_service import HandoffService
from app.orchestration.services.manual_handoff_export_service import (
    DispatchBlocked,
    ManualHandoffExportService,
)
from app.orchestration.services.return_validation_service import (
    DeclaredAttribution,
    ReturnValidationService,
)
from app.orchestration.services.schedule_service import ScheduleService
from app.schemas import orchestration_public as dto
from app.schemas.error import ErrorResponse
from app.security.programmatic_access import ProgrammaticPrincipal

router = APIRouter(tags=[TAG_ORCHESTRATION.name])

GuardedPrincipal = Annotated[ProgrammaticPrincipal, Depends(require_orchestration_operate_access)]
SessionDep = Annotated[Session, Depends(get_db_session)]

_RESPONSE_409: dict[int | str, dict[str, object]] = {
    409: {
        "model": ErrorResponse,
        "description": (
            "Conflito de ciclo de vida ou de idempotência (PIA-8059): estado "
            "incompatível, tentativa já aberta, predecessor não retornado ou "
            "reuso de command_key para outro recurso."
        ),
    }
}
_RESPONSE_429: dict[int | str, dict[str, object]] = {
    429: {
        "model": ErrorResponse,
        "description": "Cota `orchestration_api` esgotada nesta janela (PIA-1008).",
    }
}
_RESPONSE_503: dict[int | str, dict[str, object]] = {
    503: {
        "model": ErrorResponse,
        "description": (
            "Autoridade de cota indisponível (PIA-3002). A chamada é recusada "
            "sem efeito; não é cota excedida."
        ),
    }
}

_ERROS_COMUNS: dict[int | str, dict[str, object]] = {
    **response_401(),
    **response_403(),
    **response_404(),
    **response_422(),
    **_RESPONSE_409,
    **_RESPONSE_429,
    **_RESPONSE_503,
    **response_500(),
}


def _montar(session: Session) -> CommandReceiptService:
    """Compõe os serviços sobre a MESMA sessão injetada.

    Uma sessão por requisição, um commit explícito por handler. Criar uma
    segunda sessão escondida faria o efeito e a cota viverem em transações
    diferentes, e um rollback deixaria metade do trabalho de pé.
    """
    repositorio = OrchestrationRepository(session)
    agendas = ScheduleService(repositorio)
    handoff = HandoffService(repositorio)
    controle = ControlService(repositorio)
    # `DenyAllHumanGate` é o ÚNICO adaptador de gate humano em produção.
    # Um dublê concedente aqui seria bypass reutilizável; ele vive em tests/.
    exportacao = ManualHandoffExportService(
        repositorio, handoff, ManualTransport(), DenyAllHumanGate(), controle
    )
    validacao = ReturnValidationService(repositorio, controle)
    delegacoes = DelegationService(repositorio, handoff)
    auditoria = AuditService(repositorio)
    return CommandReceiptService(
        repositorio,
        agendas,
        handoff,
        exportacao,
        validacao,
        delegacoes,
        controle,
        auditoria,
    )


def _contexto(session: Session) -> tuple[OrchestrationRepository, CommandReceiptService]:
    return OrchestrationRepository(session), _montar(session)


def _para_context_refs(entradas: tuple[dto.ContextRefInput, ...]) -> tuple[ContextRef, ...]:
    return tuple(
        ContextRef(uri=item.uri, sha256=item.sha256, bytes=item.bytes) for item in entradas
    )


def _step_view(etapa: object) -> dto.StepView:
    return dto.StepView(
        step_id=etapa.step_id,  # type: ignore[attr-defined]
        position=etapa.position,  # type: ignore[attr-defined]
        role=etapa.role,  # type: ignore[attr-defined]
        instruction_ref=etapa.instruction_ref,  # type: ignore[attr-defined]
        expected_output_contract=etapa.expected_output_contract,  # type: ignore[attr-defined]
        context_refs=tuple(
            dto.ContextRefView(uri=r.uri, sha256=r.sha256, bytes=r.bytes)
            for r in etapa.context_refs  # type: ignore[attr-defined]
        ),
        constraints=dict(etapa.constraints),  # type: ignore[attr-defined]
        state=etapa.state,  # type: ignore[attr-defined]
    )


def _schedule_view(vista: object) -> dto.ScheduleView:
    return dto.ScheduleView(
        schedule_id=vista.schedule_id,  # type: ignore[attr-defined]
        title=vista.title,  # type: ignore[attr-defined]
        state=vista.state,  # type: ignore[attr-defined]
        execution_mode=vista.execution_mode,  # type: ignore[attr-defined]
        steps=tuple(_step_view(e) for e in vista.steps),  # type: ignore[attr-defined]
    )


@router.post(
    "/schedules",
    response_model=SuccessResponse[dto.ScheduleView],
    status_code=status.HTTP_201_CREATED,
    summary="Criar e ativar um Schedule manual governado",
    responses=_ERROS_COMUNS,
)
def criar_schedule(
    payload: dto.CreateScheduleRequest,
    principal: GuardedPrincipal,
    session: SessionDep,
) -> SuccessResponse[dto.ScheduleView]:
    """Cria e ativa atomicamente. Replay devolve o mesmo Schedule ACTIVE."""
    for etapa in payload.steps:
        if not etapa.contrato_suportado():
            raise OrchestrationContractViolationError(
                message=(
                    "expected_output_contract fora do vocabulário público da E7.2: "
                    f"{etapa.expected_output_contract!r}"
                )
            )
    principal_ref = str(principal.id)
    rascunho = ScheduleDraft(
        title=payload.title,
        steps=tuple(
            StepDraft(
                role=e.role,
                instruction_ref=e.instruction_ref,
                expected_output_contract=e.expected_output_contract,
                context_refs=_para_context_refs(e.context_refs),
                constraints=dict(e.constraints),
            )
            for e in payload.steps
        ),
    )
    repositorio, comandos = _contexto(session)
    try:
        recibo = comandos.create_schedule_once(
            technical_principal_ref=principal_ref,
            command_key=payload.command_key,
            draft=rascunho,
            execution_mode=payload.execution_mode,
        )
        agendas = ScheduleService(repositorio)
        schedule_id = uuid.UUID(recibo.outcome_ref)
        if not recibo.replayed:
            agendas.activate(control_principal_ref=principal_ref, schedule_id=schedule_id)
        vista = agendas.get_schedule(control_principal_ref=principal_ref, schedule_id=schedule_id)
        publica = _schedule_view(vista)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return SuccessResponse[dto.ScheduleView](data=publica)


@router.get(
    "/schedules/{schedule_id}",
    response_model=SuccessResponse[dto.ScheduleView],
    summary="Ler um Schedule sob o principal autenticado",
    responses=_ERROS_COMUNS,
)
def ler_schedule(
    schedule_id: uuid.UUID,
    principal: GuardedPrincipal,
    session: SessionDep,
) -> SuccessResponse[dto.ScheduleView]:
    """Schedule alheio e inexistente produzem o **mesmo** 404.

    Distinguir os dois transformaria a rota em oráculo de enumeração.
    """
    repositorio, _ = _contexto(session)
    vista = ScheduleService(repositorio).get_schedule(
        control_principal_ref=str(principal.id), schedule_id=schedule_id
    )
    return SuccessResponse[dto.ScheduleView](data=_schedule_view(vista))


@router.post(
    "/schedules/{schedule_id}/steps/{step_id}/handoff-export",
    response_model=SuccessResponse[dto.ExportHandoffResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Selar e exportar manualmente um repasse",
    responses=_ERROS_COMUNS,
)
def exportar_handoff(
    schedule_id: uuid.UUID,
    step_id: uuid.UUID,
    payload: dto.ExportHandoffRequest,
    principal: GuardedPrincipal,
    session: SessionDep,
) -> SuccessResponse[dto.ExportHandoffResponse]:
    """Exporta. Não chama IA, não abre rede: quem transporta é a pessoa."""
    principal_ref = str(principal.id)
    repositorio, comandos = _contexto(session)

    # ```text
    # BLOCKED_GATE_PERSISTS_PAUSE_WITH_ZERO_COMMAND_EFFECT
    # ```
    #
    # Fase 1 fora do `try` genérico: quando o gate bloqueia, a pausa e o
    # evento precisam ser COMMITADOS antes do 409. Dentro do bloco que faz
    # `session.rollback()` em qualquer exceção, a gravação seria apagada —
    # exatamente a pausa que a prova precisa observar.
    exportacao = ManualHandoffExportService(
        repositorio,
        HandoffService(repositorio),
        ManualTransport(),
        DenyAllHumanGate(),
        ControlService(repositorio),
    )
    # ```text
    # FASE ZERO = REPLAY
    # REPLAY != NEW_REQUEST
    # ```
    #
    # O replay é resolvido ANTES de qualquer pré-condição de execução nova.
    # Um replay exato encontra a etapa em AWAITING_RETURN com tentativa
    # aberta — estado que o preflight recusa, e com razão, para um pedido
    # NOVO. Confundir os dois quebraria a idempotência exatamente onde ela
    # existe para servir.
    #
    # A verificação é feita DUAS vezes: antes dos locks, para o caminho
    # comum, e depois deles, para fechar a corrida entre duas chamadas
    # idênticas simultâneas. A leitura dupla é preferida a um savepoint
    # porque não cria recibo provisório algum — e um recibo provisório que
    # precisasse desaparecer no bloqueio seria mais uma coisa a provar.
    impressao = _impressao_de_export(schedule_id, step_id, principal_ref)
    replay = _replay_de_export(repositorio, principal_ref, payload.command_key, impressao)

    autorizacao = None
    if replay is None:
        # Locks canônicos ANTES da reverificação: a segunda leitura precisa
        # acontecer com a corrida já serializada. Reverificar depois do
        # preflight inteiro seria tarde — o perdedor da corrida encontraria
        # a etapa em AWAITING_RETURN e a recusaria como pedido novo, quando
        # na verdade é replay.
        if (
            repositorio.lock_schedule(control_principal_ref=principal_ref, schedule_id=schedule_id)
            is None
        ):
            from app.orchestration.errors.exceptions import OrchestrationScopeViolationError

            raise OrchestrationScopeViolationError(
                message="Schedule inexistente sob este principal de controle",
                detail={"schedule_id": str(schedule_id)},
            )
        replay = _replay_de_export(repositorio, principal_ref, payload.command_key, impressao)
    if replay is None:
        autorizacao = exportacao.preflight(
            control_principal_ref=principal_ref, schedule_id=schedule_id, step_id=step_id
        )
        if isinstance(autorizacao, DispatchBlocked):
            try:
                exportacao.register_block(
                    control_principal_ref=principal_ref,
                    schedule_id=schedule_id,
                    step_id=step_id,
                    blocked=autorizacao,
                )
            except DispatchBlockedError:
                session.commit()  # a pausa sobrevive; só então o 409 sobe
                raise
            raise AssertionError("register_block sempre levanta")  # pragma: no cover
    try:
        recibo, saida = comandos.export_handoff_once(
            technical_principal_ref=principal_ref,
            command_key=payload.command_key,
            schedule_id=schedule_id,
            step_id=step_id,
            sealer_ref=principal_ref,
        )
        resposta = _resposta_export(
            repositorio=repositorio,
            principal_ref=principal_ref,
            schedule_id=schedule_id,
            step_id=step_id,
            recibo=recibo,
            saida=saida,
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    return SuccessResponse[dto.ExportHandoffResponse](data=resposta)


@router.post(
    "/schedules/{schedule_id}/steps/{step_id}/handoff-import",
    response_model=SuccessResponse[dto.ImportReturnResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Importar retorno não confiável e registrar veredito",
    responses=_ERROS_COMUNS,
)
def importar_retorno(
    schedule_id: uuid.UUID,
    step_id: uuid.UUID,
    payload: dto.ImportReturnRequest,
    principal: GuardedPrincipal,
    session: SessionDep,
) -> SuccessResponse[dto.ImportReturnResponse]:
    """Retorno rejeitado é **201 com `status=rejected`**, não erro.

    ```text
    RESULT_REJECTED != RESULT_DISCARDED
    AI_OUTPUT != CONTROL_CHANNEL
    ```

    O veredito negativo é o produto da operação. Devolvê-lo como 4xx faria
    o cliente tratá-lo como falha própria e reenviar, e o registro da
    recusa — que é o que a auditoria precisa — se perderia.
    """
    principal_ref = str(principal.id)
    repositorio, comandos = _contexto(session)
    try:
        recibo, saida = comandos.import_return_once(
            technical_principal_ref=principal_ref,
            command_key=payload.command_key,
            schedule_id=schedule_id,
            step_id=step_id,
            attempt_id=payload.attempt_id,
            raw=RawReturn(
                media_type=payload.output.media_type,
                content=payload.output.content,
                declared_output_ref=payload.output.declared_output_ref,
            ),
            attribution=DeclaredAttribution(
                declared_instance_id=payload.attribution.declared_instance_id,
                declared_provider_id=payload.attribution.declared_provider_id,
                declared_model_id=payload.attribution.declared_model_id,
            ),
        )
        resposta = _resposta_import(
            repositorio=repositorio,
            principal_ref=principal_ref,
            schedule_id=schedule_id,
            step_id=step_id,
            attempt_id=payload.attempt_id,
            recibo=recibo,
            saida=saida,
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    return SuccessResponse[dto.ImportReturnResponse](data=resposta)


@router.get(
    "/schedules/{schedule_id}/attempts",
    response_model=SuccessResponse[dto.AttemptListResponse],
    summary="Listar tentativas, resultados e atribuições",
    responses=_ERROS_COMUNS,
)
def listar_tentativas(
    schedule_id: uuid.UUID,
    principal: GuardedPrincipal,
    session: SessionDep,
) -> SuccessResponse[dto.AttemptListResponse]:
    """Nunca devolve conteúdo bruto, credencial ou principal de controle."""
    principal_ref = str(principal.id)
    repositorio, _ = _contexto(session)
    # Escopo: a leitura do Schedule levanta 404 antes de listar qualquer coisa.
    ScheduleService(repositorio).get_schedule(
        control_principal_ref=principal_ref, schedule_id=schedule_id
    )
    itens: list[dto.AttemptView] = []
    for tentativa in repositorio.list_attempts(
        control_principal_ref=principal_ref, schedule_id=schedule_id
    ):
        resultado = repositorio.get_handoff_result(
            control_principal_ref=principal_ref,
            schedule_id=schedule_id,
            attempt_id=tentativa.id,
        )
        atribuicao = repositorio.get_handoff_attribution(
            control_principal_ref=principal_ref,
            schedule_id=schedule_id,
            attempt_id=tentativa.id,
        )
        itens.append(
            dto.AttemptView(
                attempt_id=tentativa.id,
                step_id=tentativa.step_id,
                attempt_number=tentativa.attempt_number,
                envelope_version=tentativa.envelope_version,
                content_sha256=tentativa.content_sha256,
                state=tentativa.state,
                created_at=tentativa.created_at,
                result=_result_view(resultado) if resultado is not None else None,
                attribution=_attribution_view(atribuicao) if atribuicao is not None else None,
            )
        )
    return SuccessResponse[dto.AttemptListResponse](
        data=dto.AttemptListResponse(schedule_id=schedule_id, attempts=tuple(itens))
    )


# --- montagem de respostas -------------------------------------------------


def _result_view(resultado: object) -> dto.ResultView:
    return dto.ResultView(
        status=resultado.status,  # type: ignore[attr-defined]
        expected_output_contract=resultado.expected_output_contract,  # type: ignore[attr-defined]
        output_media_type=resultado.output_media_type,  # type: ignore[attr-defined]
        output_sha256=resultado.output_sha256,  # type: ignore[attr-defined]
        output_bytes=resultado.output_bytes,  # type: ignore[attr-defined]
        declared_output_ref=resultado.declared_output_ref,  # type: ignore[attr-defined]
        validation_codes=tuple(resultado.validation_codes),  # type: ignore[attr-defined]
    )


def _attribution_view(atribuicao: object) -> dto.AttributionView:
    return dto.AttributionView(
        declared_provider_id=atribuicao.declared_provider_id,  # type: ignore[attr-defined]
        declared_model_id=atribuicao.declared_model_id,  # type: ignore[attr-defined]
        declared_instance_id=atribuicao.declared_instance_id,  # type: ignore[attr-defined]
        role=atribuicao.role,  # type: ignore[attr-defined]
        declared_at=atribuicao.declared_at,  # type: ignore[attr-defined]
        self_declared=atribuicao.self_declared,  # type: ignore[attr-defined]
        provenance_record_ref=atribuicao.provenance_record_ref,  # type: ignore[attr-defined]
    )


def _resposta_export(
    *,
    repositorio: OrchestrationRepository,
    principal_ref: str,
    schedule_id: uuid.UUID,
    step_id: uuid.UUID,
    recibo: object,
    saida: object,
) -> dto.ExportHandoffResponse:
    """No replay, reconstrói do que está persistido — nunca inventa efeito.

    ```text
    REPLAY_RESPONSE = PERSISTED_TRUTH
    ```
    """
    attempt_id = uuid.UUID(recibo.outcome_ref)  # type: ignore[attr-defined]
    tentativa = repositorio.get_attempt(
        control_principal_ref=principal_ref, schedule_id=schedule_id, attempt_id=attempt_id
    )
    if tentativa is None or tentativa.step_id != step_id:
        # Mesma chave reutilizada para outro path: recusar em vez de
        # devolver o recurso antigo pelo endpoint novo.
        from app.orchestration.errors.exceptions import OrchestrationLifecycleViolationError

        raise OrchestrationLifecycleViolationError(
            message=(
                "command_key já usada para outro repasse; use chave nova para " "uma tentativa nova"
            ),
            detail={"schedule_id": str(schedule_id), "step_id": str(step_id)},
        )
    recibo_selo = repositorio.get_seal_receipt_by_attempt(
        control_principal_ref=principal_ref, schedule_id=schedule_id, attempt_id=attempt_id
    )
    if recibo_selo is None:  # pragma: no cover - toda tentativa tem recibo
        raise RuntimeError("tentativa sem recibo de selamento")
    etapa = repositorio.get_step(
        control_principal_ref=principal_ref, schedule_id=schedule_id, step_id=step_id
    )
    if etapa is None:  # pragma: no cover - já validado acima
        raise RuntimeError("etapa desapareceu dentro da transação")
    if saida is not None:
        envelope = saida.exported.envelope  # type: ignore[attr-defined]
        envelope_view = dto.EnvelopeView(
            envelope_version=envelope.envelope_version,
            schedule_id=envelope.schedule_id,
            step_id=envelope.step_id,
            role=envelope.role,
            instruction_ref=envelope.instruction_ref,
            context_refs=tuple(
                dto.ContextRefView(uri=r.uri, sha256=r.sha256, bytes=r.bytes)
                for r in envelope.context_refs
            ),
            expected_output_contract=envelope.expected_output_contract,
            constraints=dict(envelope.constraints),
        )
    else:
        from app.orchestration.schemas.envelope import ENVELOPE_VERSION

        envelope_view = dto.EnvelopeView(
            envelope_version=ENVELOPE_VERSION,
            schedule_id=schedule_id,
            step_id=step_id,
            role=etapa.role,
            instruction_ref=etapa.instruction_ref,
            context_refs=tuple(
                dto.ContextRefView(uri=r.uri, sha256=r.sha256, bytes=r.bytes)
                for r in etapa.context_refs
            ),
            expected_output_contract=etapa.expected_output_contract,
            constraints=dict(etapa.constraints),
        )
    return dto.ExportHandoffResponse(
        schedule_id=schedule_id,
        step_id=step_id,
        attempt_id=attempt_id,
        attempt_number=tentativa.attempt_number,
        receipt_id=recibo_selo.id,
        content_sha256=tentativa.content_sha256,
        sealed_at=recibo_selo.sealed_at,
        replayed=recibo.replayed,  # type: ignore[attr-defined]
        step_state=etapa.state,
        attempt_state=tentativa.state,
        envelope=envelope_view,
    )


def _resposta_import(
    *,
    repositorio: OrchestrationRepository,
    principal_ref: str,
    schedule_id: uuid.UUID,
    step_id: uuid.UUID,
    attempt_id: uuid.UUID,
    recibo: object,
    saida: object,
) -> dto.ImportReturnResponse:
    if recibo.outcome_ref != str(attempt_id):  # type: ignore[attr-defined]
        from app.orchestration.errors.exceptions import OrchestrationLifecycleViolationError

        raise OrchestrationLifecycleViolationError(
            message="command_key já usada para outra tentativa; use chave nova",
            detail={"attempt_id": str(attempt_id)},
        )
    resultado = repositorio.get_handoff_result(
        control_principal_ref=principal_ref, schedule_id=schedule_id, attempt_id=attempt_id
    )
    atribuicao = repositorio.get_handoff_attribution(
        control_principal_ref=principal_ref, schedule_id=schedule_id, attempt_id=attempt_id
    )
    if resultado is None or atribuicao is None:  # pragma: no cover - criados juntos
        raise RuntimeError("veredito e atribuição precisam existir juntos")
    tentativa = repositorio.get_attempt(
        control_principal_ref=principal_ref, schedule_id=schedule_id, attempt_id=attempt_id
    )
    etapa = repositorio.get_step(
        control_principal_ref=principal_ref, schedule_id=schedule_id, step_id=step_id
    )
    if tentativa is None or etapa is None:  # pragma: no cover
        raise RuntimeError("tentativa ou etapa ausente dentro da transação")
    del saida
    return dto.ImportReturnResponse(
        schedule_id=schedule_id,
        step_id=step_id,
        attempt_id=attempt_id,
        replayed=recibo.replayed,  # type: ignore[attr-defined]
        step_state=etapa.state,
        attempt_state=tentativa.state,
        result=_result_view(resultado),
        attribution=_attribution_view(atribuicao),
    )


# --- E7.3: governança técnica ----------------------------------------------


@router.post(
    "/schedules/{schedule_id}/steps/{step_id}/delegations",
    response_model=SuccessResponse[dto.GrantDelegationResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Conceder delegação técnica de despacho",
    responses=_ERROS_COMUNS,
)
def conceder_delegacao(
    schedule_id: uuid.UUID,
    step_id: uuid.UUID,
    payload: dto.GrantDelegationRequest,
    principal: GuardedPrincipal,
    session: SessionDep,
) -> SuccessResponse[dto.GrantDelegationResponse]:
    """Delegação **técnica**, nunca aprovação humana.

    ```text
    SERVICE_DELEGATION != HUMAN_APPROVAL
    ```
    """
    principal_ref = str(principal.id)
    repositorio, comandos = _contexto(session)
    try:
        recibo, vista = comandos.grant_delegation_once(
            technical_principal_ref=principal_ref,
            command_key=payload.command_key,
            schedule_id=schedule_id,
            step_id=step_id,
            valid_until=payload.valid_until,
        )
        delegacao = _delegation_view(
            repositorio, principal_ref, schedule_id, uuid.UUID(recibo.outcome_ref)
        )
        resposta = dto.GrantDelegationResponse(replayed=recibo.replayed, delegation=delegacao)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return SuccessResponse[dto.GrantDelegationResponse](data=resposta)


@router.post(
    "/schedules/{schedule_id}/steps/{step_id}/delegations/{delegation_id}/revoke",
    response_model=SuccessResponse[dto.GrantDelegationResponse],
    summary="Revogar delegação técnica",
    responses=_ERROS_COMUNS,
)
def revogar_delegacao(
    schedule_id: uuid.UUID,
    step_id: uuid.UUID,
    delegation_id: uuid.UUID,
    payload: dto.RevokeDelegationRequest,
    principal: GuardedPrincipal,
    session: SessionDep,
) -> SuccessResponse[dto.GrantDelegationResponse]:
    """Revoga a delegação `ACTIVE`; estado terminal não regride.

    ```text
    TERMINAL -> ANY_OTHER_STATE = FORBIDDEN
    ```
    """
    principal_ref = str(principal.id)
    repositorio, comandos = _contexto(session)
    try:
        recibo, _ = comandos.revoke_delegation_once(
            technical_principal_ref=principal_ref,
            command_key=payload.command_key,
            schedule_id=schedule_id,
            step_id=step_id,
            delegation_id=delegation_id,
        )
        delegacao = _delegation_view(repositorio, principal_ref, schedule_id, delegation_id)
        resposta = dto.GrantDelegationResponse(replayed=recibo.replayed, delegation=delegacao)
        session.commit()
    except Exception:
        session.rollback()
        raise
    return SuccessResponse[dto.GrantDelegationResponse](data=resposta)


@router.post(
    "/schedules/{schedule_id}/control-events",
    response_model=SuccessResponse[dto.ControlEventResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Pausar, retomar, parar ou cancelar cooperativamente",
    responses=_ERROS_COMUNS,
)
def registrar_controle(
    schedule_id: uuid.UUID,
    payload: dto.ControlEventRequest,
    principal: GuardedPrincipal,
    session: SessionDep,
) -> SuccessResponse[dto.ControlEventResponse]:
    """`D9 = COOPERATIVE`. Sem hard cancel, sem worker, sem timeout."""
    principal_ref = str(principal.id)
    repositorio, comandos = _contexto(session)
    try:
        recibo, saida = comandos.control_schedule_once(
            technical_principal_ref=principal_ref,
            command_key=payload.command_key,
            schedule_id=schedule_id,
            action=payload.action,
            stop_condition_category=payload.stop_condition_category,
        )
        agenda = ScheduleService(repositorio).get_schedule(
            control_principal_ref=principal_ref, schedule_id=schedule_id
        )
        # Replay fiel: o evento é lido pelo id que o recibo guarda, nunca
        # "o último do Schedule" — que seria a retomada mais recente.
        evento = repositorio.get_control_event(
            control_principal_ref=principal_ref,
            schedule_id=schedule_id,
            event_id=uuid.UUID(recibo.outcome_ref),
        )
        if evento is None:  # pragma: no cover - o efeito sempre grava um
            raise RuntimeError("controle sem evento registrado")
        resposta = dto.ControlEventResponse(
            schedule_id=schedule_id,
            schedule_state=agenda.state,
            replayed=recibo.replayed,
            cancelled_steps=saida.cancelled_steps if saida is not None else 0,
            closed_attempts=saida.closed_attempts if saida is not None else 0,
            event=_control_event_view(evento),
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    return SuccessResponse[dto.ControlEventResponse](data=resposta)


@router.post(
    "/schedules/{schedule_id}/attempts/{attempt_id}/audit-opinions",
    response_model=SuccessResponse[dto.AuditOpinionResponse],
    status_code=status.HTTP_201_CREATED,
    summary="Registrar parecer de auditoria sobre um resultado",
    responses=_ERROS_COMUNS,
)
def registrar_parecer(
    schedule_id: uuid.UUID,
    attempt_id: uuid.UUID,
    payload: dto.AuditOpinionRequest,
    principal: GuardedPrincipal,
    session: SessionDep,
) -> SuccessResponse[dto.AuditOpinionResponse]:
    """Parecer separado. Não altera o artefato auditado.

    ```text
    AUDITOR_WRITE_ON_AUDITED_ARTIFACT = FORBIDDEN
    AI_SELF_PASS_FINAL = FORBIDDEN
    ```
    """
    principal_ref = str(principal.id)
    repositorio, comandos = _contexto(session)
    try:
        recibo, _ = comandos.issue_audit_opinion_once(
            technical_principal_ref=principal_ref,
            command_key=payload.command_key,
            schedule_id=schedule_id,
            attempt_id=attempt_id,
            opinion=payload.opinion,
            reason_codes=tuple(c.value for c in payload.reason_codes),
            auditor_execution_ref=payload.auditor_execution_ref,
        )
        parecer = repositorio.get_audit_opinion(
            control_principal_ref=principal_ref,
            schedule_id=schedule_id,
            opinion_id=uuid.UUID(recibo.outcome_ref),
        )
        if parecer is None:  # pragma: no cover
            raise RuntimeError("parecer sem registro")
        resposta = dto.AuditOpinionResponse(replayed=recibo.replayed, opinion=_audit_view(parecer))
        session.commit()
    except Exception:
        session.rollback()
        raise
    return SuccessResponse[dto.AuditOpinionResponse](data=resposta)


@router.get(
    "/schedules/{schedule_id}/governance",
    response_model=SuccessResponse[dto.GovernanceView],
    summary="Consultar delegações, eventos, observações e pareceres",
    responses=_ERROS_COMUNS,
)
def ler_governanca(
    schedule_id: uuid.UUID,
    principal: GuardedPrincipal,
    session: SessionDep,
) -> SuccessResponse[dto.GovernanceView]:
    """Nunca conteúdo bruto, credencial ou principal de controle."""
    principal_ref = str(principal.id)
    repositorio, _ = _contexto(session)
    agenda = ScheduleService(repositorio).get_schedule(
        control_principal_ref=principal_ref, schedule_id=schedule_id
    )
    return SuccessResponse[dto.GovernanceView](
        data=dto.GovernanceView(
            schedule_id=schedule_id,
            schedule_state=agenda.state,
            delegations=tuple(
                _delegation_view_from(d)
                for d in repositorio.list_delegations(
                    control_principal_ref=principal_ref, schedule_id=schedule_id
                )
            ),
            control_events=tuple(
                _control_event_view(e)
                for e in repositorio.list_control_events(
                    control_principal_ref=principal_ref, schedule_id=schedule_id
                )
            ),
            observations=tuple(
                _observation_view(o)
                for o in repositorio.list_execution_observations(
                    control_principal_ref=principal_ref, schedule_id=schedule_id
                )
            ),
            audit_opinions=tuple(
                _audit_view(p)
                for p in repositorio.list_audit_opinions(
                    control_principal_ref=principal_ref, schedule_id=schedule_id
                )
            ),
        )
    )


def _delegation_view_from(delegacao: object) -> dto.DelegationView:
    return dto.DelegationView(
        delegation_id=delegacao.id,  # type: ignore[attr-defined]
        step_id=delegacao.step_id,  # type: ignore[attr-defined]
        content_sha256=delegacao.content_sha256,  # type: ignore[attr-defined]
        scope=delegacao.scope,  # type: ignore[attr-defined]
        state=delegacao.state,  # type: ignore[attr-defined]
        valid_until=delegacao.valid_until,  # type: ignore[attr-defined]
        consumed_at=delegacao.consumed_at,  # type: ignore[attr-defined]
        consumed_by_attempt_id=delegacao.consumed_by_attempt_id,  # type: ignore[attr-defined]
    )


def _delegation_view(
    repositorio: OrchestrationRepository,
    principal_ref: str,
    schedule_id: uuid.UUID,
    delegation_id: uuid.UUID,
) -> dto.DelegationView:
    delegacao = repositorio.get_delegation(
        control_principal_ref=principal_ref,
        schedule_id=schedule_id,
        delegation_id=delegation_id,
    )
    if delegacao is None:
        from app.orchestration.errors.exceptions import OrchestrationScopeViolationError

        raise OrchestrationScopeViolationError(
            message="delegação inexistente neste Schedule sob este principal",
            detail={"schedule_id": str(schedule_id)},
        )
    return _delegation_view_from(delegacao)


def _control_event_view(evento: object) -> dto.ControlEventView:
    return dto.ControlEventView(
        event_id=evento.id,  # type: ignore[attr-defined]
        step_id=evento.step_id,  # type: ignore[attr-defined]
        event_kind=evento.event_kind,  # type: ignore[attr-defined]
        reason_code=evento.reason_code,  # type: ignore[attr-defined]
        stop_condition_category=evento.stop_condition_category,  # type: ignore[attr-defined]
        occurred_at=evento.occurred_at,  # type: ignore[attr-defined]
    )


def _observation_view(observacao: object) -> dto.ObservationView:
    return dto.ObservationView(
        observation_id=observacao.id,  # type: ignore[attr-defined]
        step_id=observacao.step_id,  # type: ignore[attr-defined]
        observation_kind=observacao.observation_kind,  # type: ignore[attr-defined]
        previous_attempt_id=observacao.previous_attempt_id,  # type: ignore[attr-defined]
        current_attempt_id=observacao.current_attempt_id,  # type: ignore[attr-defined]
        previous_declared_provider_id=(
            observacao.previous_declared_provider_id  # type: ignore[attr-defined]
        ),
        current_declared_provider_id=(
            observacao.current_declared_provider_id  # type: ignore[attr-defined]
        ),
        self_declared=observacao.self_declared,  # type: ignore[attr-defined]
        observed_at=observacao.observed_at,  # type: ignore[attr-defined]
    )


def _audit_view(parecer: object) -> dto.AuditOpinionView:
    return dto.AuditOpinionView(
        opinion_id=parecer.id,  # type: ignore[attr-defined]
        handoff_result_id=parecer.handoff_result_id,  # type: ignore[attr-defined]
        opinion=parecer.opinion,  # type: ignore[attr-defined]
        reason_codes=tuple(parecer.reason_codes),  # type: ignore[attr-defined]
        auditor_execution_ref=parecer.auditor_execution_ref,  # type: ignore[attr-defined]
        issued_at=parecer.issued_at,  # type: ignore[attr-defined]
    )


def _impressao_de_export(schedule_id: uuid.UUID, step_id: uuid.UUID, principal_ref: str) -> str:
    """Impressão digital da requisição de exportação.

    Idêntica à que `export_handoff_once` calcula — se divergirem, um replay
    legítimo seria lido como pedido novo. A duplicação é deliberada e
    verificada por teste; derivá-la de dentro do serviço exigiria expor
    a fase de claim, que é justamente o que a fase zero evita tocar.
    """
    from app.orchestration.services.command_receipt_service import _impressao_digital

    return _impressao_digital(
        {
            "operation": CommandOperation.EXPORT_HANDOFF.value,
            "schedule_id": str(schedule_id),
            "step_id": str(step_id),
            "sealer_ref": principal_ref,
        }
    )


def _replay_de_export(
    repositorio: OrchestrationRepository,
    principal_ref: str,
    command_key: str,
    impressao: str,
) -> object | None:
    """Recibo já persistido para esta tripla, se e somente se for o MESMO pedido.

    ```text
    SAME_COMMAND_KEY + DIFFERENT_REQUEST = CONFLICT
    ```

    Hash divergente é 409 aqui, na fase zero — não mais adiante, quando já
    haveria locks tomados e um preflight avaliado sobre a premissa errada.
    """
    recibo = repositorio.get_command_receipt(
        technical_principal_ref=principal_ref,
        operation=CommandOperation.EXPORT_HANDOFF.value,
        command_key=command_key,
    )
    if recibo is None:
        return None
    if recibo.request_sha256 != impressao:
        from app.orchestration.errors.exceptions import OrchestrationLifecycleViolationError

        raise OrchestrationLifecycleViolationError(
            message="command_key já usada para uma requisição diferente; use chave nova",
            detail={"operation": CommandOperation.EXPORT_HANDOFF.value},
        )
    return recibo


def _assert_every_route_is_protected() -> None:
    """Falha no IMPORT se alguma rota perder a dependency exata.

    Compara por **identidade de objeto**, não por nome: uma função com o
    mesmo nome importada de outro módulo passaria por uma checagem
    textual e não passa por esta.
    """
    desprotegidas: list[str] = []
    for rota in router.routes:
        dependencias = getattr(getattr(rota, "dependant", None), "dependencies", [])
        chamadas = {d.call for d in dependencias}
        assinatura = inspect.signature(rota.endpoint)  # type: ignore[attr-defined]
        for parametro in assinatura.parameters.values():
            metadados = getattr(parametro.annotation, "__metadata__", ())
            for meta in metadados:
                chamada = getattr(meta, "dependency", None)
                if chamada is not None:
                    chamadas.add(chamada)
        if require_orchestration_operate_access not in chamadas:
            desprotegidas.append(getattr(rota, "path", str(rota)))
    if desprotegidas:
        raise ImportError(
            "rota de orquestração sem require_orchestration_operate_access: " f"{desprotegidas}"
        )


_assert_every_route_is_protected()
