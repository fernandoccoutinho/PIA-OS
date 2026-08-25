"""
Adapters produtivos das tools transacionais.

```text
NO_METHOD MAY EXIST ONLY IN THE DOUBLES
```

`prealocar_tentativa`, `materializar` e `retorno.importar` foram
inventados por mim para os dublês e não existiam em serviço nenhum.
Este módulo os elimina: tudo passa por
`CommandReceiptService.export_handoff_once` e `import_return_once`,
que são os contratos reais.

## Idempotência é do serviço, não daqui

`export_handoff_once` **deriva** o `request_sha256` da operação e dos
identificadores, reivindica a tripla e só chama o efeito para quem
reivindicou. Replay devolve o mesmo recibo com `replayed=True` e efeito
`None`; mesma chave com pedido materialmente diferente já levanta
conflito lá dentro.

```text
REPLAY -> SAME_RECEIPT · NO_SECOND_EFFECT
DIFFERENT_REQUEST_SAME_KEY -> CONFLICT_AT_THE_SERVICE
```

Por isso o replay reconstrói a resposta a partir do `outcome_ref` do
recibo, nunca de uma exportação inventada — o segundo elemento vem
`None` de propósito, e preencher com um valor fabricado seria afirmar um
despacho que não ocorreu.

```text
INVENTED_EXPORT_ON_REPLAY = ASSERTING_AN_EFFECT_THAT_DID_NOT_RUN
```
"""

import uuid
from dataclasses import dataclass
from typing import Any

from app.orchestration.models.enums import HandoffMode
from app.orchestration.protection.vocabulary import GatePosition, ProtectionOutcome


class HandoffBlockedError(Exception):
    """G2 bloqueou, antes mesmo do claim."""

    def __init__(self, *, gate_position: GatePosition, fingerprint: str) -> None:
        super().__init__(f"handoff bloqueado em {gate_position.value}")
        self.gate_position = gate_position
        self.fingerprint = fingerprint


@dataclass(frozen=True)
class SupervisedHandoffResult:
    attempt_id: uuid.UUID
    handoff_mode: HandoffMode
    replayed: bool

    def __post_init__(self) -> None:
        if self.handoff_mode is not HandoffMode.SUPERVISED_AUTOMATIC_HANDOFF:
            raise ValueError("despacho MCP registra apenas supervised_automatic_handoff")


@dataclass(frozen=True)
class ReturnImportResult:
    attempt_id: uuid.UUID
    accepted: bool
    reason_code: str | None
    replayed: bool


class SupervisedHandoffAdapter:
    """`handoff.export` sobre o serviço transacional real."""

    def __init__(
        self,
        *,
        recibos: Any,
        protecao: Any,
        operacao: Any,
        objetivo_por_step: Any,
    ) -> None:
        self._recibos = recibos
        self._protecao = protecao
        self._operacao = operacao
        self._objetivo = objetivo_por_step

    def exportar(
        self,
        *,
        control_principal_ref: str,
        schedule_id: uuid.UUID,
        step_id: uuid.UUID,
        command_key: str,
    ) -> SupervisedHandoffResult:
        """G2 -> claim -> (G3 -> selo -> transições) -> commit.

        O G2 vem **antes** do claim: reivindicar uma chave para um
        trabalho que a proteção já recusa consumiria a chave à toa.
        O G3 roda dentro do callback, junto do efeito.
        """
        decisao = self._protecao.aplicar(
            objective=self._objetivo(schedule_id=schedule_id, step_id=step_id),
            gate_position=GatePosition.G2,
            principal_ref=control_principal_ref,
            operation=self._operacao,
            schedule_id=schedule_id,
            step_id=step_id,
        )
        if decisao.outcome is not ProtectionOutcome.ALLOWED:
            raise HandoffBlockedError(
                gate_position=GatePosition.G2,
                fingerprint=decisao.decision_fingerprint,
            )

        recibo, saida = self._recibos.export_handoff_once(
            technical_principal_ref=control_principal_ref,
            command_key=command_key,
            schedule_id=schedule_id,
            step_id=step_id,
            sealer_ref=control_principal_ref,
        )

        if saida is None:
            # Replay: o efeito não rodou. A tentativa vem do recibo.
            return SupervisedHandoffResult(
                attempt_id=uuid.UUID(recibo.outcome_ref),
                handoff_mode=HandoffMode.SUPERVISED_AUTOMATIC_HANDOFF,
                replayed=True,
            )

        return SupervisedHandoffResult(
            attempt_id=saida.attempt_id,
            handoff_mode=saida.handoff_mode,
            replayed=recibo.replayed,
        )


class ReturnImportAdapter:
    """`return.import` sobre `import_return_once`."""

    def __init__(self, *, recibos: Any) -> None:
        self._recibos = recibos

    def importar_retorno(
        self,
        *,
        control_principal_ref: str,
        command_key: str,
        schedule_id: uuid.UUID,
        step_id: uuid.UUID,
        attempt_id: uuid.UUID,
        media_type: str,
        content: str,
        declared_output_ref: str | None,
        declared_instance_id: str | None,
        declared_provider_id: str | None,
        declared_model_id: str | None,
    ) -> ReturnImportResult:
        """Monta `RawReturn` e `DeclaredAttribution` tipados.

        O conteúdo bruto não é devolvido nem projetado: sai o veredito.
        `RAW_RETURN -> TRANSIENT` já é garantia do serviço; a tool não a
        desfaz reexibindo o que ele não persiste.

        ```text
        REJECTED_RETURN = PERSISTED_RESULT · NEVER_A_COMMAND
        ```
        """
        from app.orchestration.ports.transport import RawReturn
        from app.orchestration.services.return_validation_service import (
            DeclaredAttribution,
        )

        cru = RawReturn(
            media_type=media_type,
            content=content,
            declared_output_ref=declared_output_ref,
        )
        # `declared_instance_id` e OBRIGATORIO no contrato: a atribuicao
        # sem instancia nao identifica quem respondeu, e
        # SELF_DECLARED != VERIFIED_IDENTITY ja e fraco o bastante sem
        # deixar o campo vazio.
        if not declared_instance_id or not declared_instance_id.strip():
            raise ValueError("declared_instance_id é obrigatório")
        atribuicao = DeclaredAttribution(
            declared_instance_id=declared_instance_id,
            declared_provider_id=declared_provider_id,
            declared_model_id=declared_model_id,
        )

        recibo, saida = self._recibos.import_return_once(
            technical_principal_ref=control_principal_ref,
            command_key=command_key,
            schedule_id=schedule_id,
            step_id=step_id,
            attempt_id=attempt_id,
            raw=cru,
            attribution=atribuicao,
        )

        if saida is None:
            return ReturnImportResult(
                attempt_id=attempt_id,
                accepted=False,
                reason_code="replayed",
                replayed=True,
            )

        # `status` e o veredito do servico. VALIDATED e o UNICO que
        # aceita; qualquer outro valor, presente ou futuro, cai no lado
        # da recusa — nunca no `else` permissivo de um booleano.
        #
        #     ONLY_VALIDATED_ACCEPTS · EVERYTHING_ELSE_REFUSES
        from app.orchestration.models.enums import HandoffResultStatus

        return ReturnImportResult(
            attempt_id=attempt_id,
            accepted=saida.status is HandoffResultStatus.VALIDATED,
            reason_code=saida.status.value,
            replayed=recibo.replayed,
        )
