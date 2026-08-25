"""
Adaptador E7 → E4 da porta de governança (`E7.4-1 B1a`).

```text
PORT_IN_THE_CONSUMER · ADAPTER_WHERE_THE_IMPORT_IS_LEGAL
E7_STATIC_GUARDS = UNCHANGED
```

Este é o **único** módulo do caminho que importa `app.memory`. Ele fica fora
de `app/orchestration/` e fora do router justamente porque as guardas
congeladas `e71b02` e `e72b10` proíbem esse import nos dois lugares — e a
saída correta nunca foi abrir exceção numa guarda.

## Estado desta entrega

```text
PRODUCTION_COMPOSITION_IN_B1A = NO
ADAPTER_INJECTED_IN_PRODUCTION = NO
```

O adaptador existe, compila e é testável por injeção. Nenhum composition root
produtivo o instancia; quem o compõe é a B1b, depois do `PASS_FINAL` da E8
IAB, que é quem produz o descritor semântico autorizado.

## O que ele não faz

Não classifica, não interpreta texto e não repassa `stated_intent`: a
finalidade declarada é registro na E4, nunca prova, e mandá-la atravessar a
fronteira só arriscaria conteúdo do usuário numa camada que se comprometeu a
não guardá-lo.

```text
CLAIMED PURPOSE != PROVEN PURPOSE
HUMAN_PROTECTION_EVENT_CONTENT = NONE
```

`policy_key = None` **sempre**: só a fronteira de plataforma decide aqui, e a
policy local continua governando o que é dela por outros caminhos.
"""

import dataclasses
from datetime import UTC, datetime

from app.memory.models.governance_enums import (
    CapabilityEngagement,
    CognitiveOperation,
    CriticalCapability,
    GovernanceOutcome,
)
from app.memory.schemas.governance import GovernanceResolution
from app.memory.schemas.memory_context import MemoryContext
from app.memory.services.governance_manager import GovernanceManager
from app.memory.services.platform_safety_boundary import CapabilityDescriptor
from app.orchestration.errors.exceptions import HumanProtectionGateUnavailableError
from app.orchestration.ports.governance import GovernanceQuery, GovernanceResolutionView
from app.orchestration.ports.governance_vocabulary import (
    ACCEPTED_BOUNDARY_OUTCOMES,
    BoundaryCapability,
    BoundaryOutcome,
)
from app.orchestration.protection.fingerprint import (
    calcular_binding_sha256,
    calcular_decision_fingerprint,
)
from app.orchestration.protection.vocabulary import RETENTION_POLICY_ID

CAMPOS_DA_RESOLUCAO: tuple[str, ...] = tuple(
    campo.name for campo in dataclasses.fields(GovernanceResolution)
)
"""Os campos de `GovernanceResolution`, derivados do dataclass da E4.

```text
HAND_WRITTEN_COUNT = COUNT_THAT_DRIFTS
COUNT_DERIVED_FROM_HANDWRITTEN_LIST != SCHEMA_DERIVED_MANIFEST
```

Um campo novo na E4 entra no `decision_fingerprint` sozinho; um campo
removido some sozinho. Nenhuma lista paralela envelhece em silêncio, e o
manifesto do teste é derivado da mesma fonte.
"""

CAMPO_DA_EVIDENCIA = "classifier_version"
"""A identidade do produtor semântico entra no fingerprint junto da resolução.

Sem ela, duas classificações diferentes que chegassem ao mesmo desfecho
produziriam o mesmo digest — e a decisão deixaria de identificar quem a
produziu.
"""

if CAMPO_DA_EVIDENCIA in CAMPOS_DA_RESOLUCAO:  # pragma: no cover - guarda de colisão
    raise RuntimeError(
        f"a E4 passou a declarar '{CAMPO_DA_EVIDENCIA}' em GovernanceResolution; "
        "acrescentá-lo ao fingerprint sobrescreveria o campo da E4 em silêncio"
    )


class GovernanceResolutionAdapter:
    """Traduz a pergunta da E7 e devolve a decisão da E4 por valor.

    Satisfaz `GovernanceResolutionPort` estruturalmente; a compatibilidade
    estática de assinatura é provada em `tests/static/test_port_assignment.py`,
    porque `@runtime_checkable` confere apenas nomes de membros
    (`RUNTIME_CHECKABLE != STATIC SIGNATURE COMPATIBILITY`, defeito D da
    E4.7.1).
    """

    def __init__(
        self, governance_manager: GovernanceManager, *, momento: datetime | None = None
    ) -> None:
        self._governance = governance_manager
        self._momento = momento
        """Instante fixo, opcional. `None` significa "leia o relógio agora".

        Existe para que o instante da avaliação seja **injetável**: um arnês
        que fixa `valid_until` e deixa o adaptador ler o relógio por conta
        própria abre uma janela entre os dois, e a prova passa a depender do
        momento em que roda.

        ```text
        MULTIPLE_CLOCK_READS = FLAKY_BY_CONSTRUCTION
        ONE_INSTANT_INJECTED = TEMPORAL_CONTRACT_PROVED
        ```

        Em produção fica `None`: o parâmetro não é interruptor de
        comportamento, é ponto de injeção do relógio.
        """

    def resolve(self, query: GovernanceQuery) -> GovernanceResolutionView:
        """Caminho canônico: descritor tipado -> `GovernanceManager.resolve()`."""
        avaliado_em = self._momento if self._momento is not None else datetime.now(UTC)
        resolucao = self._resolver(query, avaliado_em)
        desfecho = self._desfecho(resolucao)

        return GovernanceResolutionView(
            outcome=desfecho,
            blocked_capabilities=tuple(
                BoundaryCapability(capacidade.value)
                for capacidade in resolucao.blocked_capabilities
            ),
            capability_engagement=query.descriptor_engagement,
            boundary_version=resolucao.safety_boundary_version,
            classifier_version=query.binding.classifier_version,
            decision_fingerprint=self.calcular_fingerprint(
                resolucao, classifier_version=query.binding.classifier_version
            ),
            binding_sha256=calcular_binding_sha256(query.binding),
            evaluated_at=avaliado_em,
            valid_until=query.binding.valid_until,
        )

    # --- tradução ---------------------------------------------------------

    def _resolver(self, query: GovernanceQuery, momento: datetime) -> GovernanceResolution:
        descritor = CapabilityDescriptor(
            operation=CognitiveOperation(query.descriptor_operation.value),
            capabilities=frozenset(
                CriticalCapability(capacidade.value) for capacidade in query.descriptor_capabilities
            ),
            engagement=CapabilityEngagement(query.descriptor_engagement.value),
        )
        contexto = MemoryContext(
            domain_ids=query.context_domain_ids,
            session_id=query.context_session_id,
            actor_ref=query.context_actor_ref,
            purpose=query.context_purpose,
        )
        try:
            resolucao = self._governance.resolve(
                descriptor=descritor, context=contexto, policy_key=None, moment=momento
            )
        except HumanProtectionGateUnavailableError:
            raise
        except Exception as falha:  # noqa: BLE001 - qualquer falha da E4 é indisponibilidade
            raise HumanProtectionGateUnavailableError(
                "a governança não pôde produzir uma resolução para esta pergunta"
            ) from falha
        if not isinstance(resolucao, GovernanceResolution):
            raise HumanProtectionGateUnavailableError(
                "a governança devolveu algo que não é uma resolução"
            )
        return resolucao

    @staticmethod
    def _desfecho(resolucao: GovernanceResolution) -> BoundaryOutcome:
        """Só `PROHIBITED` e `NOT_APPLICABLE` são interpretados.

        Com `policy_key=None` a policy local sequer é consultada, então os
        outros dois desfechos não podem ocorrer — e é exatamente por isso que
        a chegada de um deles é indisponibilidade técnica, e não um `else`
        mudo que viraria permissão.
        """
        if not isinstance(resolucao.outcome, GovernanceOutcome):
            raise HumanProtectionGateUnavailableError("desfecho da governança não é tipado")
        desfecho = BoundaryOutcome(resolucao.outcome.value)
        if desfecho not in ACCEPTED_BOUNDARY_OUTCOMES:
            raise HumanProtectionGateUnavailableError(
                f"desfecho inesperado '{desfecho.value}' com policy_key=None"
            )
        return desfecho

    # --- identidade da decisão --------------------------------------------

    @staticmethod
    def calcular_fingerprint(resolucao: GovernanceResolution, *, classifier_version: str) -> str:
        """Fingerprint sobre a resolução INTEIRA mais a identidade da evidência.

        Os campos textuais da resolução entram aqui — e **não** na vista nem
        no evento. É o que permite provar a decisão sem arquivar o pedido.

        ```text
        SAFETY_AUDIT_METADATA != DANGEROUS_PAYLOAD_ARCHIVE
        ```
        """
        entradas: dict[str, object] = {
            campo: getattr(resolucao, campo) for campo in CAMPOS_DA_RESOLUCAO
        }
        entradas[CAMPO_DA_EVIDENCIA] = classifier_version
        return calcular_decision_fingerprint(entradas)


RETENTION_POLICY_DECLARADA = RETENTION_POLICY_ID
"""Política declarada da evidência, sem executor nesta entrega.

```text
EXPIRACAO_DO_EVENTO = NOT_IMPLEMENTED · EXPIRY_EXECUTOR = E4.9.PEA-0
§20.6_RETENTION_COMPLIANCE = NOT_SATISFIED_BY_E7_4_1_ALONE
```
"""
