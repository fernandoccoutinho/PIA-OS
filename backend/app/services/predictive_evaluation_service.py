"""
Serviço de aplicação da E6.2 — compõe E6.1 e E5, sem regra científica.

```text
SERVICE_CONTAINS_SCIENCE = FORBIDDEN
RECONFIGURATION_INSTRUCTION = ALWAYS_NONE
REPOSITORY = NO_WRITE
EXTERNAL_EXECUTION = NONE
```

A cadeia é fixa e curta:

```text
PUBLIC_DTO
  -> E6.1 to_internal_request
  -> E5 predictive_evaluate_and_reconfigure_batch (instruções None)
  -> E5 predictive_route_batch
  -> E6.1 to_public_response
```

Montar desfecho à mão em vez de chamar a E5 seria copiar ciência para a
borda, onde ela não é auditada. O serviço orquestra e traduz; não decide.
"""

import uuid
from datetime import UTC, datetime

from app.exceptions.validation import ValidationException
from app.predictive_accessibility.batch import PredictiveReadyEvaluationItem
from app.predictive_accessibility.coordinator import (
    predictive_evaluate_and_reconfigure_batch,
    predictive_route_batch,
)
from app.predictive_accessibility.reconfiguration import (
    PredictiveReconfigurationAppendResult,
    PredictiveReconfigurationEvent,
)
from app.schemas import predictive_evaluation as dto
from app.services.predictive_evaluation_mapping import (
    PublicContractMappingError,
    to_internal_request,
    to_public_response,
)

# Instante usado apenas quando o lote não contém nenhum item `ready`. Um
# lote assim é composto só de `upstream_unavailable`, que curto-circuita
# antes de qualquer avaliação temporal — o valor não pode influenciar o
# resultado, e o teste `somente unavailable é determinístico` prova isso.
_NO_READY_ITEM_INSTANT = datetime(1970, 1, 1, tzinfo=UTC)

MIXED_AT_DETAIL = (
    "todos os itens 'ready' do lote devem compartilhar o mesmo "
    "evaluation_context.at; instantes divergentes produziriam um roteamento "
    "que nenhum relógio único explica"
)


class NoWriteReconfigurationRepository:
    """Porta E5.l que explode se tocada. A E6 não escreve, não lê, não promove.

    Um repositório que silenciosamente não faz nada esconderia uma chamada
    indevida; este a transforma em falha ruidosa no teste.
    """

    class Violation(RuntimeError):
        """A E6.2 tocou a persistência de reconfiguração — defeito, não caso."""

    def get(self, event_id: uuid.UUID) -> PredictiveReconfigurationEvent | None:
        raise self.Violation(f"E6.2 não consulta eventos de reconfiguração (get {event_id})")

    def current(self, subject_key: str) -> PredictiveReconfigurationEvent | None:
        raise self.Violation(f"E6.2 não consulta estado corrente (current {subject_key})")

    def append(
        self, event: PredictiveReconfigurationEvent
    ) -> PredictiveReconfigurationAppendResult:
        raise self.Violation("E6.2 não escreve em predictive_reconfiguration_events")


def _shared_instant(canonica: object) -> datetime:
    """Instante único do lote, extraído dos próprios itens `ready`.

    Preferir o `at` do contexto a um relógio de servidor mantém a avaliação
    reproduzível: a mesma requisição produz a mesma resposta, independente
    de quando chega.
    """
    itens = getattr(canonica, "items", ())
    instantes = {
        item.context.at for item in itens if isinstance(item, PredictiveReadyEvaluationItem)
    }
    if not instantes:
        return _NO_READY_ITEM_INSTANT
    if len(instantes) > 1:
        raise ValidationException(detail=MIXED_AT_DETAIL)
    return instantes.pop()


def evaluate_and_route(
    request: dto.PublicEvaluationRequest,
) -> dto.PublicEvaluationResponse:
    """Executa a cadeia canônica e devolve a resposta pública da E6.1.

    Erros de contrato público viram `ValidationException` (422/PIA-2001) —
    um `ValueError` cru escapando daqui viraria 500 e trataria erro do
    cliente como falha do servidor.
    """
    try:
        canonica, governadas = to_internal_request(request)
    except PublicContractMappingError as exc:
        raise ValidationException(detail=str(exc)) from exc
    except ValueError as exc:
        raise ValidationException(detail=str(exc)) from exc

    momento = _shared_instant(canonica)
    instrucoes = tuple(None for _ in canonica.items)

    coordenado = predictive_evaluate_and_reconfigure_batch(
        canonica, instrucoes, NoWriteReconfigurationRepository()
    )
    roteamento = predictive_route_batch(coordenado, governadas, at=momento)

    try:
        return to_public_response(coordenado.evaluation, roteamento)
    except PublicContractMappingError as exc:  # pragma: no cover - defesa de contrato
        raise ValidationException(detail=str(exc)) from exc
