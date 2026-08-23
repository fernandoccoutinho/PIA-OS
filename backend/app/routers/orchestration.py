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
from app.orchestration.adapters.manual_transport import ManualTransport
from app.orchestration.errors.exceptions import OrchestrationContractViolationError
from app.orchestration.ports.transport import RawReturn
from app.orchestration.repositories.orchestration_repository import OrchestrationRepository
from app.orchestration.schemas.envelope import ContextRef, ScheduleDraft, StepDraft
from app.orchestration.services.command_receipt_service import CommandReceiptService
from app.orchestration.services.handoff_service import HandoffService
from app.orchestration.services.manual_handoff_export_service import ManualHandoffExportService
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
    exportacao = ManualHandoffExportService(repositorio, handoff, ManualTransport())
    validacao = ReturnValidationService(repositorio)
    return CommandReceiptService(repositorio, agendas, handoff, exportacao, validacao)


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
