"""
`HumanProtectionApplication` — o fato que o evento registra (`E7.4-1 B1a`).

Um gate, numa posição, aplicando uma decisão a um objetivo. Congelado,
hashable, sem instância ORM, sem texto livre e sem conteúdo do usuário.

```text
HUMAN_PROTECTION_EVENT_CONTENT = NONE
SAFETY_AUDIT_METADATA != DANGEROUS_PAYLOAD_ARCHIVE
```

## Efeitos: recebidos, nunca inventados

O B1a entrega a ponte **não composta**. Pausar Schedule e revogar delegação
são atos do caminho produtivo (B1b/B2), e a ponte não os executa aqui. O que
ela faz é **exigir a coerência**: um bloqueio fora de G1 sem pausa aplicada é
recusado antes de qualquer escrita, porque um evento assim afirmaria que o
fluxo seguiu depois de uma recusa.

```text
EFFECT_DECLARED_BY_THE_CALLER · COHERENCE_ENFORCED_BY_THE_VALUE_OBJECT
G1 avalia antes de existir Schedule pausável -> pause_applied = false
```

## Camadas de garantia (Master Parte III §15.2)

```text
APPLICATION_LEVEL  invariantes de LINHA, aqui
DB_LEVEL           os mesmos como CHECK, mais as FKs
DB_LEVEL           coerência ENTRE tabelas, nos constraint triggers diferidos
```

A coerência pai/filha (bloqueio exige capacidade, não-bloqueio não tem
nenhuma, ordinais `0..n-1`) **não** é reimplementada em código: ela é avaliada
no `COMMIT` pelos gatilhos, e duplicá-la aqui criaria duas fontes de verdade
que divergem — o defeito que a E4.5.1 já pagou uma vez.
"""

import dataclasses
import re
import uuid
from dataclasses import dataclass

from app.orchestration.ports.governance_vocabulary import (
    BoundaryCapability,
    BoundaryEngagement,
    BoundaryOperation,
)
from app.orchestration.protection.vocabulary import (
    BINDING_ALGO_VERSION,
    FINGERPRINT_ALGO_VERSION,
    PRODUCER_REF,
    GatePosition,
    ProtectionOutcome,
)

_SHA256 = re.compile(r"^[0-9a-f]{64}$")

_ENGAGEMENTS_QUE_BLOQUEIAM = frozenset(
    {BoundaryEngagement.OPERATIONAL_ENABLEMENT, BoundaryEngagement.UNSPECIFIED}
)
"""Os dois engajamentos que a fronteira da E4 recusa.

Enumerados, não derivados por exclusão: um membro novo em
`BoundaryEngagement` deve nascer fora desta lista até que alguém decida o
contrário, e não entrar nela por omissão.
"""


@dataclass(frozen=True)
class ProtectionEffects:
    """O que o chamador já executou quando pede o registro.

    Existe como tipo próprio para que a chamada não seja uma dupla de
    booleanos posicionais: `pause_applied` e `delegations_revoked` descrevem
    fatos diferentes, e trocá-los de lugar tem de ser impossível, não
    improvável.
    """

    pause_applied: bool = False
    delegations_revoked: int = 0
    attempt_id: uuid.UUID | None = None
    """Tentativa **materializada**, distinta do `attempt_id` prealocado do
    binding. Só existe quando G3 permitiu e a tentativa foi criada;
    bloqueio e revisão nunca fabricam tentativa."""

    def __post_init__(self) -> None:
        if not isinstance(self.pause_applied, bool):
            raise TypeError("pause_applied deve ser bool")
        if isinstance(self.delegations_revoked, bool) or not isinstance(
            self.delegations_revoked, int
        ):
            raise TypeError("delegations_revoked deve ser int")
        if self.delegations_revoked < 0:
            raise ValueError("delegations_revoked não pode ser negativo")
        if self.attempt_id is not None and not isinstance(self.attempt_id, uuid.UUID):
            raise TypeError("attempt_id deve ser uuid.UUID ou None")


@dataclass(frozen=True)
class HumanProtectionApplication:
    """Os dezenove campos imutáveis da aplicação, mais as capacidades.

    A ordem dos campos é a do evento persistido. `blocked_capabilities` fica
    por último e **fora** da comparação integral do vencedor de uma corrida,
    porque ela vive na tabela filha e é lida à parte.
    """

    control_principal_ref: str
    schedule_id: uuid.UUID | None
    step_id: uuid.UUID | None
    attempt_id: uuid.UUID | None
    binding_attempt_id: uuid.UUID | None
    objective_sha256: str
    decision_fingerprint: str
    fingerprint_algo_version: str
    binding_sha256: str
    binding_algo_version: str
    outcome: ProtectionOutcome
    capability_engagement: BoundaryEngagement | None
    boundary_version: int
    classifier_version: str
    cognitive_operation: BoundaryOperation
    gate_position: GatePosition
    producer_ref: str
    pause_applied: bool
    delegations_revoked: int
    blocked_capabilities: tuple[BoundaryCapability, ...] = ()

    def __post_init__(self) -> None:
        self._validar_tipos()
        self._validar_versoes_e_hashes()
        self._validar_posicao()
        self._validar_desfecho()

    # --- validação --------------------------------------------------------

    def _validar_tipos(self) -> None:
        if not isinstance(self.outcome, ProtectionOutcome):
            raise TypeError("outcome deve ser um ProtectionOutcome")
        if not isinstance(self.gate_position, GatePosition):
            raise TypeError("gate_position deve ser um GatePosition")
        if not isinstance(self.cognitive_operation, BoundaryOperation):
            raise TypeError("cognitive_operation deve ser um BoundaryOperation")
        if self.capability_engagement is not None and not isinstance(
            self.capability_engagement, BoundaryEngagement
        ):
            raise TypeError("capability_engagement deve ser um BoundaryEngagement ou None")
        if (
            not isinstance(self.control_principal_ref, str)
            or not self.control_principal_ref.strip()
        ):
            raise ValueError("control_principal_ref é obrigatório")
        if not isinstance(self.classifier_version, str) or not self.classifier_version.strip():
            raise ValueError("classifier_version é obrigatório")
        for campo in ("schedule_id", "step_id", "attempt_id", "binding_attempt_id"):
            valor = getattr(self, campo)
            if valor is not None and not isinstance(valor, uuid.UUID):
                raise TypeError(f"{campo} deve ser uuid.UUID ou None")
        if not isinstance(self.pause_applied, bool):
            raise TypeError("pause_applied deve ser bool")
        if isinstance(self.delegations_revoked, bool) or not isinstance(
            self.delegations_revoked, int
        ):
            raise TypeError("delegations_revoked deve ser int")
        if self.delegations_revoked < 0:
            raise ValueError("delegations_revoked não pode ser negativo")
        if isinstance(self.boundary_version, bool) or not isinstance(self.boundary_version, int):
            raise TypeError("boundary_version deve ser int")
        if self.boundary_version < 1:
            raise ValueError("boundary_version deve ser >= 1")

        capacidades = tuple(self.blocked_capabilities)
        if any(not isinstance(item, BoundaryCapability) for item in capacidades):
            raise TypeError("blocked_capabilities aceita apenas BoundaryCapability")
        if len(set(capacidades)) != len(capacidades):
            raise ValueError("blocked_capabilities não aceita repetição")
        object.__setattr__(self, "blocked_capabilities", capacidades)

    def _validar_versoes_e_hashes(self) -> None:
        for campo in ("objective_sha256", "decision_fingerprint", "binding_sha256"):
            valor = getattr(self, campo)
            if not isinstance(valor, str) or not _SHA256.match(valor):
                raise ValueError(f"{campo} deve ser sha-256 hexadecimal minúsculo de 64 dígitos")
        if self.fingerprint_algo_version != FINGERPRINT_ALGO_VERSION:
            raise ValueError("fingerprint_algo_version desconhecida")
        if self.binding_algo_version != BINDING_ALGO_VERSION:
            raise ValueError("binding_algo_version desconhecida")
        if self.producer_ref != PRODUCER_REF:
            raise ValueError("producer_ref não é o produtor autorizado desta ponte")

    def _validar_posicao(self) -> None:
        e_g1 = self.gate_position is GatePosition.G1
        if e_g1 and (self.schedule_id is not None or self.step_id is not None):
            raise ValueError("g1 registra schedule_id e step_id nulos")
        if not e_g1 and (self.schedule_id is None or self.step_id is None):
            raise ValueError(f"{self.gate_position.value} exige schedule_id e step_id")
        if e_g1 and self.pause_applied:
            raise ValueError("g1 não pausa — não há Schedule pausável antes da criação")

        e_g3 = self.gate_position is GatePosition.G3
        if e_g3 and self.binding_attempt_id is None:
            raise ValueError("g3 exige binding_attempt_id prealocado")
        if not e_g3 and self.binding_attempt_id is not None:
            raise ValueError("somente g3 carrega binding_attempt_id")

    def _validar_desfecho(self) -> None:
        """Amarra desfecho, efeito e tentativa.

        Uma tentativa materializada só existe quando G3 permitiu, e ela é
        obrigatoriamente **a mesma** que entrou no binding: se a submissão
        mudou, o binding mudou, e reaproveitar a tentativa anterior seria a
        prova velha que o R10.1-C1 fechou.

        ```text
        G3_APPLICATION_WITHOUT_ATTEMPT_ID = STALE_ATTEMPT_PROOF
        ```
        """
        permitido = self.outcome is ProtectionOutcome.ALLOWED
        bloqueado = self.outcome is ProtectionOutcome.BLOCKED
        g3_permitido = self.gate_position is GatePosition.G3 and permitido

        if self.attempt_id is not None:
            if not g3_permitido:
                raise ValueError("somente g3 permitido materializa tentativa")
            if self.attempt_id != self.binding_attempt_id:
                raise ValueError("attempt_id materializada diverge da tentativa do binding")
        elif g3_permitido:
            raise ValueError("g3 permitido exige tentativa materializada")

        if permitido and (self.pause_applied or self.delegations_revoked):
            raise ValueError("allowed não pausa nem revoga — o fluxo seguiu")
        if permitido and self.capability_engagement is not None:
            raise ValueError(
                "allowed não carrega engajamento de capacidade — não houve capacidade "
                "a engajar, e registrar uma seria categoria sem produtor"
            )

        if bloqueado:
            if self.capability_engagement not in _ENGAGEMENTS_QUE_BLOQUEIAM:
                raise ValueError(
                    "bloqueio exige engajamento operacional ou não especificado — "
                    "analítico e preventivo não habilitam capacidade"
                )
            if self.gate_position is not GatePosition.G1 and not self.pause_applied:
                raise ValueError(
                    "bloqueio fora de g1 exige pausa aplicada — sem ela o evento "
                    "afirmaria que o trabalho seguiu depois da recusa"
                )
        else:
            if self.delegations_revoked:
                raise ValueError("somente bloqueio revoga delegação")
            if self.outcome is ProtectionOutcome.REVIEW_REQUIRED:
                raise ValueError(
                    "review_required não possui produtor autorizado em v1 — "
                    "a fronteira da E4 é binária"
                )


CAMPOS_IMUTAVEIS_DA_APLICACAO: tuple[str, ...] = tuple(
    campo.name
    for campo in dataclasses.fields(HumanProtectionApplication)
    if campo.name != "blocked_capabilities"
)
"""Os campos comparados integralmente contra o vencedor de uma corrida.

Derivados do dataclass, nunca escritos à mão:

```text
HAND_WRITTEN_COUNT = COUNT_THAT_DRIFTS
WINNER_VERIFIED_BY_CAPABILITIES_ONLY = UNVERIFIED_APPLICATION
```
"""
