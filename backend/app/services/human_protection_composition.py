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

GATES_DO_B2: frozenset[GatePosition] = frozenset({GatePosition.G1, GatePosition.G4})
"""Posições que o B2 ativa. Enumerado pela mesma razão de `GATES_DO_B1B`."""

GATES_ATIVOS: frozenset[GatePosition] = frozenset(
    {GatePosition.G1, GatePosition.G2, GatePosition.G3, GatePosition.G4}
)
"""União explícita, escrita membro a membro.

Não é `GATES_DO_B1B | GATES_DO_B2` nem `frozenset(GatePosition)`: as duas
formas fariam uma posição futura entrar sozinha em algum dos lados. Aqui,
acrescentar uma posição exige escrevê-la aqui **e** no bloco que a aplica.
"""

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


class DelegationRevocationPort(Protocol):
    """Revoga delegações quando G4 bloqueia. Devolve quantas revogou."""

    def revoke(self, *, schedule_id: uuid.UUID, reason_fingerprint: str) -> int:
        """Revoga e conta. Levantar exceção é resposta legítima."""
        ...


class WorkResumePort(Protocol):
    """Retoma o trabalho suspenso, e **só** sob decisão nova que permita."""

    def resume(self, *, schedule_id: uuid.UUID, decision_fingerprint: str) -> None:
        """Reativa o Schedule. Levantar exceção é resposta legítima."""
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
        revocation_port: "DelegationRevocationPort | None" = None,
        resume_port: "WorkResumePort | None" = None,
    ) -> None:
        if isinstance(boundary_version, bool) or not isinstance(boundary_version, int):
            raise TypeError("boundary_version deve ser int")
        if boundary_version < 1:
            raise ValueError("boundary_version deve ser >= 1")
        self._broker = broker
        self._bridge = bridge
        self._boundary_version = boundary_version
        self._pause = pause_port
        self._revocation = revocation_port
        self._resume = resume_port

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
        if gate_position not in GATES_ATIVOS:
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
            efeitos_finais = self._efeitos_do_bloqueio(
                binding=binding, vista=vista, efeitos=efeitos_finais
            )

        return self._bridge.registrar_aplicacao(
            vista=vista,
            binding=binding,
            efeitos=efeitos_finais,
            moment=moment,
        )

    def _efeitos_do_bloqueio(
        self,
        *,
        binding: GovernanceBinding,
        vista: GovernanceResolutionView,
        efeitos: ProtectionEffects,
    ) -> ProtectionEffects:
        """Efeitos do bloqueio, por posição.

        ```text
        G1 -> recusar a criacao; NAO ha Schedule a pausar
        G2/G3 -> suspender o trabalho
        G4 -> suspender E revogar a delegacao pedida
        ```

        G1 é o único que não pausa, e o invariante do evento o exige: um
        `pause_applied` em G1 afirmaria que algo foi suspenso antes de
        existir. Recusar a criação já é o efeito inteiro.
        """
        if binding.gate_position is GatePosition.G1:
            return ProtectionEffects(
                pause_applied=False,
                delegations_revoked=efeitos.delegations_revoked,
            )

        pausados = self._pausar(binding=binding, vista=vista, efeitos=efeitos)

        if binding.gate_position is not GatePosition.G4:
            return pausados

        revogadas = self._revogar(binding=binding, vista=vista)
        return ProtectionEffects(
            pause_applied=pausados.pause_applied,
            delegations_revoked=max(revogadas, pausados.delegations_revoked),
        )

    def _revogar(self, *, binding: GovernanceBinding, vista: GovernanceResolutionView) -> int:
        """Revoga a delegação recusada em G4.

        Falha de revogação é recusa, não bloqueio parcial: uma delegação
        concedida sobrevivendo a um G4 bloqueado seria a autoridade que o
        gate acabou de negar, viva.

        ```text
        FAILED_REVOCATION != SILENT_BLOCK
        ```
        """
        if self._revocation is None:
            raise HumanProtectionGateUnavailableError(
                "g4 bloqueado exige porta de revogação de delegação"
            )
        if binding.schedule_id is None:
            raise HumanProtectionGateUnavailableError("g4 exige schedule cuja delegação revogar")
        try:
            revogadas = self._revocation.revoke(
                schedule_id=binding.schedule_id,
                reason_fingerprint=vista.decision_fingerprint,
            )
        except Exception as falha:
            raise HumanProtectionGateUnavailableError(
                f"a delegação não pôde ser revogada após o bloqueio: {falha}"
            ) from falha
        if isinstance(revogadas, bool) or not isinstance(revogadas, int) or revogadas < 0:
            raise HumanProtectionGateUnavailableError(
                "a porta de revogação devolveu contagem não utilizável"
            )
        return revogadas

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

    def retomar(
        self,
        *,
        objective: str,
        gate_position: GatePosition,
        principal_ref: str,
        operation: CognitiveOperation,
        schedule_id: uuid.UUID,
        step_id: uuid.UUID,
        moment: datetime | None = None,
    ) -> HumanProtectionApplication:
        """Retoma trabalho suspenso — **somente** sob decisão nova que permita.

        A retomada não é o desfazer do bloqueio: é uma decisão nova, com
        descritor novo, sobre o mesmo objetivo. Reativar sob a autorização
        anterior seria exatamente a prova velha que o programa recusa.

        ```text
        RESUME_UNDER_THE_OLD_DECISION = STALE_AUTHORIZATION
        NEW_DESCRIPTOR · NEW_BINDING · NEW_DECISION
        ```

        Se a decisão nova bloquear de novo, a pausa é reaplicada e nada é
        retomado: bloqueio que retoma seria a recusa se autoconcedendo.
        """
        if self._resume is None:
            raise HumanProtectionGateUnavailableError("retomada exige porta de retomada composta")
        if gate_position is GatePosition.G1:
            raise HumanProtectionGateUnavailableError(
                "g1 não retoma — não houve trabalho suspenso antes da criação"
            )

        aplicacao = self.aplicar(
            objective=objective,
            gate_position=gate_position,
            principal_ref=principal_ref,
            operation=operation,
            schedule_id=schedule_id,
            step_id=step_id,
            moment=moment,
        )
        if aplicacao.outcome is not ProtectionOutcome.ALLOWED:
            return aplicacao

        try:
            self._resume.resume(
                schedule_id=schedule_id,
                decision_fingerprint=aplicacao.decision_fingerprint,
            )
        except Exception as falha:
            raise HumanProtectionGateUnavailableError(
                f"o trabalho não pôde ser retomado: {falha}"
            ) from falha
        return aplicacao

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
