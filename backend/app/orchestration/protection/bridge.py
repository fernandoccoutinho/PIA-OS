"""
Ponte de enforcement da Governança — não composta (`E7.4-1 B1a`).

```text
E4_HOLDS_AUTHORITY · E7_APPLIES_THE_DECISION · E8_PRODUCES_THE_DESCRIPTOR
```

A ponte **não** classifica, não pontua, não lê forma e não possui catálogo de
dano. Ela exige uma resolução de Governança **vinculada a esta pergunta**,
traduz o desfecho em desfecho de gate e registra a aplicação de modo
idempotente e append-only.

```text
DUPLICATE_PROTECTION_CATEGORY_OWNER = PROHIBITED
STRUCTURAL_COMPLEXITY_HAS_DECISION_AUTHORITY = NO
TOPIC != CAPABILITY
```

## Ausência nunca vira permissão

```text
MISSING_AUTHORIZED_DESCRIPTOR != AUTHORIZED_EMPTY_DESCRIPTOR
SOFTWARE_FAILURE != HUMAN_HARM_CATEGORY
ABSENCE_OF_EVIDENCE != ABSENCE_OF_DECISION
```

Porta ausente, exceção, tipo errado, binding incompatível ou validade vencida
produzem `PIA-8069` — falha técnica tipada, zero efeito. Nenhuma dessas
situações cria desfecho, categoria, capacidade ou evento. E o caminho
permitido produz `ALLOWED` **registrado**: sem um desfecho positivo durável,
qualquer defeito do gate viraria permissão silenciosa e indistinguível de
"o gate nem rodou".

## Estado desta entrega

```text
PRODUCTION_COMPOSITION_IN_B1A = NO
ROUTER_MODIFIED_IN_B1A = NO
BRIDGE_READY != OPERATIONAL_PROTECTION
```

Nenhum composition root produtivo instancia esta classe. Pausar Schedule e
revogar delegação continuam sendo atos do caminho produtivo (B1b/B2); aqui
eles chegam **declarados** em `ProtectionEffects` e têm sua coerência exigida
antes de qualquer escrita.
"""

from datetime import UTC, datetime

from app.orchestration.errors.exceptions import HumanProtectionGateUnavailableError
from app.orchestration.ports.governance import (
    GovernanceQuery,
    GovernanceResolutionPort,
    GovernanceResolutionView,
)
from app.orchestration.ports.governance_vocabulary import BoundaryOutcome
from app.orchestration.protection.binding import GovernanceBinding
from app.orchestration.protection.decision import (
    HumanProtectionApplication,
    ProtectionEffects,
)
from app.orchestration.protection.fingerprint import calcular_binding_sha256
from app.orchestration.protection.vocabulary import (
    BINDING_ALGO_VERSION,
    FINGERPRINT_ALGO_VERSION,
    PRODUCER_REF,
    GatePosition,
    ProtectionOutcome,
)
from app.orchestration.repositories.human_protection_repository import (
    HumanProtectionRepository,
)

DESFECHO_POR_FRONTEIRA: dict[BoundaryOutcome, ProtectionOutcome] = {
    BoundaryOutcome.PROHIBITED: ProtectionOutcome.BLOCKED,
    BoundaryOutcome.NOT_APPLICABLE: ProtectionOutcome.ALLOWED,
}
"""Mapa **exaustivo e literal** dos desfechos que a ponte interpreta.

Escrito como dicionário, e não como `if/else`: um membro novo em
`BoundaryOutcome` não encontra entrada aqui e cai em `KeyError` convertido em
`PIA-8069`, em vez de escorregar por um `else` que significaria permissão.

```text
UNEXPECTED_OUTCOME_INTERPRETED = FABRICATED_AUTHORITY
```
"""


class HumanProtectionBridge:
    """Exige a decisão vinculada e registra a aplicação do gate."""

    def __init__(
        self, port: GovernanceResolutionPort, repository: HumanProtectionRepository
    ) -> None:
        self._port = port
        self._repository = repository

    # --- decisão ----------------------------------------------------------

    def avaliar(
        self, query: GovernanceQuery, *, moment: datetime | None = None
    ) -> GovernanceResolutionView:
        """Obtém a resolução e prova que ela responde a ESTA pergunta.

        ```text
        RESOLUTION_FOR_ANOTHER_QUESTION = NO_RESOLUTION
        OLD_AUTHORIZATION != CONSENT_TO_A_NEW_CAPABILITY
        ```

        `execution_authorized` sozinho não bastaria, e aqui ele sequer existe:
        o que amarra a resposta à pergunta é o `binding_sha256` recalculado
        sobre os dez campos do binding recebido.
        """
        agora = moment if moment is not None else datetime.now(UTC)
        vista = self._resolver(query)
        self._exigir_vinculo(vista, query.binding)
        self._exigir_validade(vista, agora)
        return vista

    def _resolver(self, query: GovernanceQuery) -> GovernanceResolutionView:
        try:
            vista = self._port.resolve(query)
        except HumanProtectionGateUnavailableError:
            raise
        except Exception as falha:  # noqa: BLE001 - qualquer falha da porta é indisponibilidade
            raise HumanProtectionGateUnavailableError(
                "a porta de governança falhou ao resolver a pergunta"
            ) from falha
        if not isinstance(vista, GovernanceResolutionView):
            raise HumanProtectionGateUnavailableError(
                "a porta devolveu algo que não é uma resolução de governança"
            )
        return vista

    @staticmethod
    def _exigir_vinculo(vista: GovernanceResolutionView, binding: GovernanceBinding) -> None:
        """Quatro condições, nenhuma derivada de outra.

        Derivar o vínculo do próprio dado que se quer autorizar é tautologia,
        e foi o defeito que reprovou a Chain111.
        """
        esperado = calcular_binding_sha256(binding)
        if vista.binding_sha256 != esperado:
            raise HumanProtectionGateUnavailableError(
                "a resolução não está vinculada a esta aplicação do gate"
            )
        if vista.boundary_version != binding.boundary_version:
            raise HumanProtectionGateUnavailableError(
                "versão da fronteira divergente entre a resolução e o binding"
            )
        if vista.classifier_version != binding.classifier_version:
            raise HumanProtectionGateUnavailableError(
                "versão do classificador divergente entre a resolução e o binding"
            )
        if vista.valid_until != binding.valid_until:
            raise HumanProtectionGateUnavailableError(
                "validade divergente entre a resolução e o binding"
            )

    @staticmethod
    def _exigir_validade(vista: GovernanceResolutionView, agora: datetime) -> None:
        if agora > vista.valid_until:
            raise HumanProtectionGateUnavailableError(
                "resolução vencida — decisão expirada não autoriza nem recusa"
            )
        if agora < vista.evaluated_at:
            raise HumanProtectionGateUnavailableError(
                "resolução avaliada no futuro — instante incoerente"
            )

    @staticmethod
    def desfecho(vista: GovernanceResolutionView) -> ProtectionOutcome:
        """Traduz o desfecho da fronteira em desfecho do gate."""
        try:
            return DESFECHO_POR_FRONTEIRA[vista.outcome]
        except KeyError as falha:
            raise HumanProtectionGateUnavailableError(
                f"desfecho '{vista.outcome.value}' não é interpretável pela ponte"
            ) from falha

    # --- aplicação --------------------------------------------------------

    def montar_aplicacao(
        self,
        *,
        vista: GovernanceResolutionView,
        binding: GovernanceBinding,
        efeitos: ProtectionEffects,
    ) -> HumanProtectionApplication:
        """Monta o fato a registrar, sem escrever nada.

        O engajamento só acompanha o bloqueio: num `ALLOWED` não houve
        capacidade a engajar, e registrar uma seria categoria sem produtor.
        """
        desfecho = self.desfecho(vista)
        bloqueado = desfecho is ProtectionOutcome.BLOCKED
        return HumanProtectionApplication(
            control_principal_ref=binding.principal_ref,
            schedule_id=binding.schedule_id,
            step_id=binding.step_id,
            attempt_id=efeitos.attempt_id,
            binding_attempt_id=binding.attempt_id,
            objective_sha256=binding.objective_sha256,
            decision_fingerprint=vista.decision_fingerprint,
            fingerprint_algo_version=FINGERPRINT_ALGO_VERSION,
            binding_sha256=vista.binding_sha256,
            binding_algo_version=BINDING_ALGO_VERSION,
            outcome=desfecho,
            capability_engagement=vista.capability_engagement if bloqueado else None,
            boundary_version=binding.boundary_version,
            classifier_version=binding.classifier_version,
            cognitive_operation=binding.operation,
            gate_position=binding.gate_position,
            producer_ref=PRODUCER_REF,
            pause_applied=efeitos.pause_applied,
            delegations_revoked=efeitos.delegations_revoked,
            blocked_capabilities=vista.blocked_capabilities if bloqueado else (),
        )

    def registrar_aplicacao(
        self,
        *,
        vista: GovernanceResolutionView,
        binding: GovernanceBinding,
        efeitos: ProtectionEffects,
    ) -> HumanProtectionApplication:
        """Registra a aplicação uma única vez por `(fingerprint, gate, binding)`.

        Perdeu a corrida? O `SAVEPOINT` já desfez a tentativa, e o vencedor é
        lido e **comparado integralmente** antes de a operação ser dada por
        satisfeita.
        """
        self._exigir_vinculo(vista, binding)
        aplicacao = self.montar_aplicacao(vista=vista, binding=binding, efeitos=efeitos)
        if self._repository.inserir_se_ausente(aplicacao) is None:
            self._repository.confirmar_vencedor(aplicacao)
        return aplicacao


GATES_SEM_LIGACAO_PRODUTIVA: frozenset[GatePosition] = frozenset(GatePosition)
"""Todas as quatro posições, e nenhuma ligada ao caminho produtivo no B1a.

```text
NO_WIRED_BUT_INACTIVE_CODE · DELIVERY_SEQUENCING != RUNTIME_TOGGLE
```

A constante existe para que a afirmação seja **verificável por teste** em vez
de ficar só na prosa: a guarda estática compara este conjunto com as posições
efetivamente compostas no router, e exige que a interseção seja vazia.
"""
