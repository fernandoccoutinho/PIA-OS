"""
Composição do gate de proteção humana (`E7.4-1 B1b`).

```text
E8_PRODUCES_THE_DESCRIPTOR · E7_CONSUMES_AND_ENFORCES
COMPOSITION_ROOT_LIVES_WHERE_THE_IMPORT_IS_LEGAL
```

Este módulo é o composition root que faltava. Ele mora em `app/services/`,
ao lado de `governance_bridge.py`, pelo mesmo motivo: importa **os dois
lados** — `app.authorization` (E8, que fala o vocabulário canônico da E4) e
`app.orchestration` (E7, que fala o espelho por valor) — e nenhum dos dois
pode importar o outro sem quebrar as guardas `e71b02` e `e72b10`.

## Tradução por valor, nunca por identidade

O descritor da E8 chega tipado nos enums canônicos; a E7 fala `Boundary*`.
A travessia é **pelo `.value`**, membro a membro, e falha ruidosamente
quando um valor não existe do outro lado:

```text
VALUE_MIRROR_PROVEN != IMPORT_SHARED
UNKNOWN_VALUE_AT_THE_BORDER = TECHNICAL_UNAVAILABILITY
```

Um `KeyError` silencioso aqui viraria capacidade não traduzida — isto é,
capacidade crítica que atravessa a fronteira como conjunto vazio. Por isso
toda falha de tradução é `HumanProtectionGateUnavailableError`, jamais um
`continue`.

## Ordem: decidir antes de qualquer efeito

```text
PROHIBITED -> BLOCKED antes de qualquer efeito
ALLOWED    -> segue, e o ALLOWED fica registrado
```

`aplicar()` resolve, exige o vínculo, registra a aplicação e **só então**
devolve o desfecho ao chamador. Um bloqueio registrado depois do efeito
seria auditoria de um dano já causado.
"""

import uuid
from datetime import datetime
from typing import Protocol

from app.authorization.broker import (
    IntentAuthorizationBroker,
    IntentAuthorizationUnavailableError,
)
from app.authorization.descriptor import AuthorizedCapabilityDescriptor
from app.memory.models.governance_enums import CognitiveOperation
from app.orchestration.errors.exceptions import HumanProtectionGateUnavailableError
from app.orchestration.ports.governance import GovernanceQuery, GovernanceResolutionView
from app.orchestration.ports.governance_vocabulary import (
    BoundaryCapability,
    BoundaryEngagement,
    BoundaryOperation,
)
from app.orchestration.protection.binding import GovernanceBinding
from app.orchestration.protection.bridge import HumanProtectionBridge
from app.orchestration.protection.decision import HumanProtectionApplication, ProtectionEffects
from app.orchestration.protection.vocabulary import GatePosition, ProtectionOutcome

GATES_DO_B1B: frozenset[GatePosition] = frozenset({GatePosition.G2, GatePosition.G3})
"""Posições que esta entrega ativa. G1 e G4 são do B2.

Enumerado, e não derivado de `GatePosition`: derivar faria a chegada de uma
posição futura ativá-la sozinha, sem ninguém escrever o caminho que a aplica
— exatamente o defeito que `EMPTY_OPERATIONS_SCOPE_V1` evita do outro lado.

```text
NEW_GATE_POSITION_DEFAULT = EXPLICIT_OPT_IN_REQUIRED
```
"""


def traduzir_operacao(operation: CognitiveOperation) -> BoundaryOperation:
    """Canônico -> espelho, por valor."""
    try:
        return BoundaryOperation(operation.value)
    except ValueError as falha:
        raise HumanProtectionGateUnavailableError(
            f"operação '{operation.value}' não existe no espelho da E7"
        ) from falha


def traduzir_engajamento(engagement: object) -> BoundaryEngagement:
    """Canônico -> espelho, por valor."""
    valor = getattr(engagement, "value", None)
    if not isinstance(valor, str):
        raise HumanProtectionGateUnavailableError("engajamento não é tipado")
    try:
        return BoundaryEngagement(valor)
    except ValueError as falha:
        raise HumanProtectionGateUnavailableError(
            f"engajamento '{valor}' não existe no espelho da E7"
        ) from falha


def traduzir_capacidades(capabilities: frozenset) -> frozenset[BoundaryCapability]:  # type: ignore[type-arg]
    """Canônico -> espelho, por valor, **membro a membro**.

    Nenhuma capacidade é descartada em silêncio: uma que não exista do outro
    lado interrompe a travessia.
    """
    traduzidas: set[BoundaryCapability] = set()
    for capacidade in capabilities:
        valor = getattr(capacidade, "value", None)
        if not isinstance(valor, str):
            raise HumanProtectionGateUnavailableError("capacidade não é tipada")
        try:
            traduzidas.add(BoundaryCapability(valor))
        except ValueError as falha:
            raise HumanProtectionGateUnavailableError(
                f"capacidade '{valor}' não existe no espelho da E7 — "
                "capacidade não traduzida jamais vira conjunto vazio"
            ) from falha
    return frozenset(traduzidas)


class WorkPausePort(Protocol):
    """Suspende o trabalho quando o gate bloqueia.

    Existe porque o invariante do evento exige: bloqueio fora de G1 sem
    pausa aplicada afirmaria que o trabalho seguiu depois da recusa.

    ```text
    BLOCKED_WITHOUT_PAUSE = RECORD_THAT_CONTRADICTS_ITSELF
    ```

    Em G1 não há o que pausar — o Schedule ainda não existe, e recusar a
    criação já é o efeito inteiro.
    """

    def pause(self, *, schedule_id: uuid.UUID, reason_fingerprint: str) -> None:
        """Suspende o Schedule. Levantar exceção é resposta legítima."""
        ...


class HumanProtectionComposition:
    """Compõe E8 -> tradução -> ponte -> registro, numa posição de gate."""

    def __init__(
        self,
        *,
        broker: IntentAuthorizationBroker,
        bridge: HumanProtectionBridge,
        boundary_version: int,
        pause_port: WorkPausePort,
    ) -> None:
        if isinstance(boundary_version, bool) or not isinstance(boundary_version, int):
            raise TypeError("boundary_version deve ser int")
        if boundary_version < 1:
            raise ValueError("boundary_version deve ser >= 1")
        self._broker = broker
        self._bridge = bridge
        self._boundary_version = boundary_version
        self._pause = pause_port

    def aplicar(
        self,
        *,
        objective: str,
        gate_position: GatePosition,
        principal_ref: str,
        operation: CognitiveOperation,
        schedule_id: uuid.UUID | None = None,
        step_id: uuid.UUID | None = None,
        attempt_id: uuid.UUID | None = None,
        efeitos: ProtectionEffects | None = None,
        moment: datetime | None = None,
    ) -> HumanProtectionApplication:
        """Aplica o gate e devolve o fato registrado.

        `attempt_id` no binding é o da tentativa **prealocada** — o G3 roda
        sob o lock final e precisa amarrar a decisão à tentativa que vai
        exportar, não a uma criada depois.
        """
        if gate_position not in GATES_DO_B1B:
            raise HumanProtectionGateUnavailableError(
                f"posição '{gate_position.value}' não é ativada por esta composição"
            )

        descritor = self._descritor(objective=objective, operation=operation, moment=moment)

        try:
            binding = GovernanceBinding(
                operation=traduzir_operacao(descritor.operation),
                principal_ref=principal_ref,
                schedule_id=schedule_id,
                step_id=step_id,
                attempt_id=attempt_id,
                objective_sha256=descritor.objective_sha256,
                gate_position=gate_position,
                boundary_version=self._boundary_version,
                classifier_version=descritor.classifier_version,
                valid_until=descritor.valid_until,
            )
        except (TypeError, ValueError) as falha:
            # Incoerencia entre posicao e referencias e indisponibilidade
            # tecnica, nunca excecao crua atravessando o composition root:
            # quem chama trata um tipo so, e o tratamento correto e recusar.
            raise HumanProtectionGateUnavailableError(
                f"binding incoerente para {gate_position.value}: {falha}"
            ) from falha

        query = GovernanceQuery(
            descriptor_operation=binding.operation,
            descriptor_capabilities=traduzir_capacidades(descritor.capabilities),
            descriptor_engagement=traduzir_engajamento(descritor.engagement),
            binding=binding,
        )

        vista = self._bridge.avaliar(query, moment=moment)
        # Estatico na ponte: o desfecho e funcao da vista, nao estado do
        # objeto injetado. Chamar pela classe mantem a traducao unica.
        bloqueado = HumanProtectionBridge.desfecho(vista) is ProtectionOutcome.BLOCKED

        efeitos_finais = (
            efeitos if efeitos is not None else ProtectionEffects(attempt_id=attempt_id)
        )
        if bloqueado:
            efeitos_finais = self._pausar(binding=binding, vista=vista, efeitos=efeitos_finais)

        return self._bridge.registrar_aplicacao(
            vista=vista,
            binding=binding,
            efeitos=efeitos_finais,
            moment=moment,
        )

    def _pausar(
        self,
        *,
        binding: GovernanceBinding,
        vista: GovernanceResolutionView,
        efeitos: ProtectionEffects,
    ) -> ProtectionEffects:
        """Suspende antes de registrar, e recusa se a suspensão falhar.

        ```text
        PAUSE_BEFORE_THE_RECORD · FAILED_PAUSE != SILENT_BLOCK
        ```

        Uma pausa que falha e mesmo assim registra `pause_applied=True`
        seria evidência fabricada do efeito mais importante do bloqueio.
        """
        if efeitos.pause_applied:
            return efeitos
        if binding.schedule_id is None:
            raise HumanProtectionGateUnavailableError(
                "bloqueio fora de g1 exige schedule a suspender"
            )
        try:
            self._pause.pause(
                schedule_id=binding.schedule_id,
                reason_fingerprint=vista.decision_fingerprint,
            )
        except Exception as falha:
            raise HumanProtectionGateUnavailableError(
                f"o trabalho não pôde ser suspenso após o bloqueio: {falha}"
            ) from falha
        # ``attempt_id`` cai fora dos efeitos do bloqueio: so um G3
        # PERMITIDO materializa tentativa. A prealocada continua provada
        # pelo ``binding_attempt_id``, que amarra a decisao a ela.
        #
        #     BLOCKED_AT_G3 -> NO_ATTEMPT_MATERIALIZED
        return ProtectionEffects(
            pause_applied=True,
            delegations_revoked=efeitos.delegations_revoked,
        )

    def permite(self, aplicacao: HumanProtectionApplication) -> bool:
        """`ALLOWED` é o único desfecho que deixa seguir.

        `REVIEW_REQUIRED` continua sem produtor, e se um dia tiver, cair no
        `else` de um booleano o transformaria em permissão. Aqui ele não
        permite.
        """
        return aplicacao.outcome is ProtectionOutcome.ALLOWED

    def _descritor(
        self,
        *,
        objective: str,
        operation: CognitiveOperation,
        moment: datetime | None,
    ) -> AuthorizedCapabilityDescriptor:
        """Descritor da E8, ou indisponibilidade técnica.

        ```text
        MISSING_DESCRIPTOR != NOT_APPLICABLE
        ```
        """
        try:
            return self._broker.authorize(objective=objective, operation=operation, moment=moment)
        except IntentAuthorizationUnavailableError as falha:
            raise HumanProtectionGateUnavailableError(
                f"a E8 não produziu descritor autorizado: {falha.reason}"
            ) from falha


def resolucao_permite(vista: GovernanceResolutionView) -> bool:
    """Atalho de leitura para quem só precisa do desfecho da fronteira."""
    return HumanProtectionBridge.desfecho(vista) is ProtectionOutcome.ALLOWED
