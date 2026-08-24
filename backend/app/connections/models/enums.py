"""
Vocabulários fechados do kernel de conexões (`E7.4-1`).

```text
ENUM_OR_REGISTRY != AVAILABLE
FAMÍLIA != RELEASE != PROVEDOR_DE_ACESSO != CONEXÃO
DECLARED_VOCABULARY != EXECUTABLE_METHOD
```

Declarar um método **não** o torna disponível. Os oito métodos existem
aqui inteiros porque amputar o enum obrigaria migração de vocabulário a
cada adaptador novo e faria o banco esquecer que os outros existem — o
mesmo precedente de `app/orchestration/models/enums.py`.

O que separa declaração de disponibilidade é `ConnectionState`, e o que
impede que a separação dependa de disciplina de chamador é o `CHECK` no
banco: só `MANUAL_HANDOFF` pode estar `AVAILABLE` nesta entrega.
"""

from enum import StrEnum


class ConnectionMethod(StrEnum):
    """Os oito métodos de conexão reconhecidos pelo kernel.

    Nenhum deles é a API técnica da E6: aquela é a **autoridade** que
    todos atravessam, não um nono método.
    """

    MANUAL_HANDOFF = "manual_handoff"
    PROVIDER_NATIVE_MCP_INBOUND = "provider_native_mcp_inbound"
    DIRECT_PROVIDER_API = "direct_provider_api"
    PROVIDER_NATIVE_AGENT_BRIDGE = "provider_native_agent_bridge"
    ENTERPRISE_GATEWAY_OR_BROKER = "enterprise_gateway_or_broker"
    LOCAL_MODEL_ADAPTER = "local_model_adapter"
    BROWSER_ASSISTED_HANDOFF = "browser_assisted_handoff"
    WATCHED_INBOX_OUTBOX = "watched_inbox_outbox"


class ConnectionState(StrEnum):
    """Ciclo de vida do estado de uma conexão.

    ```text
    DECLARED -> PREFLIGHT_REQUIRED -> IMPLEMENTED_PENDING_AUDIT -> AVAILABLE
    AVAILABLE <-> DEGRADED                (saúde recuperável)
    qualquer -> REVOKED                   (terminal por ato)
    qualquer -> UNSUPPORTED               (terminal por decisão)
    ```

    `DEGRADED` é o estado honesto de "responde, mas não como prometido":
    capacidade reduzida, TTL vencido, schema divergente. Ele **não** vira
    substituição silenciosa.
    """

    DECLARED = "declared"
    PREFLIGHT_REQUIRED = "preflight_required"
    IMPLEMENTED_PENDING_AUDIT = "implemented_pending_audit"
    AVAILABLE = "available"
    DEGRADED = "degraded"
    REVOKED = "revoked"
    UNSUPPORTED = "unsupported"


TERMINAL_CONNECTION_STATES: frozenset[ConnectionState] = frozenset(
    {ConnectionState.REVOKED, ConnectionState.UNSUPPORTED}
)
"""Terminais. `DEGRADED` **não** é terminal — é recuperável por design."""


AVAILABLE_CONNECTION_METHODS: frozenset[ConnectionMethod] = frozenset(
    {ConnectionMethod.MANUAL_HANDOFF}
)
"""Único método que pode estar `AVAILABLE` nesta entrega.

```text
ENUM_OR_REGISTRY != AVAILABLE
```

Medido, não escolhido: `MANUAL_HANDOFF` é o único método com transporte
provado em produção desde a Chain113. O `CHECK`
`ck_connection_profiles_available_method` impõe o mesmo no banco, porque
uma regra que só existe em Python é convenção.
"""


BASELINE_METHOD_STATE: dict[ConnectionMethod, ConnectionState] = {
    ConnectionMethod.MANUAL_HANDOFF: ConnectionState.AVAILABLE,
    ConnectionMethod.PROVIDER_NATIVE_MCP_INBOUND: ConnectionState.PREFLIGHT_REQUIRED,
    ConnectionMethod.DIRECT_PROVIDER_API: ConnectionState.DECLARED,
    ConnectionMethod.PROVIDER_NATIVE_AGENT_BRIDGE: ConnectionState.DECLARED,
    ConnectionMethod.ENTERPRISE_GATEWAY_OR_BROKER: ConnectionState.DECLARED,
    ConnectionMethod.LOCAL_MODEL_ADAPTER: ConnectionState.DECLARED,
    ConnectionMethod.BROWSER_ASSISTED_HANDOFF: ConnectionState.DECLARED,
    ConnectionMethod.WATCHED_INBOX_OUTBOX: ConnectionState.DECLARED,
}
"""Estado com que cada método **nasce**.

`BROWSER_ASSISTED_HANDOFF` é `DECLARED`, e não `UNSUPPORTED`: é um fluxo
humano assistido, com dono na E8.

```text
FLUXO_HUMANO_ASSISTIDO != SCRAPING
UNSUPPORTED É DECISÃO DE NÃO FAZER, NÃO ATALHO PARA "PARECE ARRISCADO"
```
"""


E7_4_1_IMPLEMENTED_CONNECTION_TRANSITIONS: frozenset[tuple[ConnectionState, ConnectionState]] = (
    frozenset()
)
"""Nenhuma. A E7.4-1 **cria** perfis no estado de nascimento e não os move.

Revogação, degradação por drift e promoção pertencem à E7.4-3. Declarar
o vocabulário inteiro e executar nenhuma transição é a alternativa
honesta a amputar o enum.
"""


class ModelAttestationLevel(StrEnum):
    """Quão forte é a evidência sobre o modelo que de fato respondeu.

    ```text
    REQUESTED_MODEL != OBSERVED_MODEL
    GATEWAY_OPACO -> observed = NULL e atestação `unknown`, jamais um palpite
    ```
    """

    ATTESTED = "attested"
    SELF_DECLARED = "self_declared"
    UNKNOWN = "unknown"


class EntitlementOrigin(StrEnum):
    """De onde veio a alegação de direito de uso.

    ```text
    USER_DECLARED -> OFFICIALLY_DISCOVERED = PROIBIDO (mutação)
    USER_DECLARED -> SUPERSEDED BY OFFICIALLY_DISCOVERED = OBRIGATÓRIO (sucessão)
    ```
    """

    USER_DECLARED = "user_declared"
    OFFICIALLY_DISCOVERED = "officially_discovered"


class EntitlementState(StrEnum):
    """Ciclo de vida monotônico de uma alegação.

    ```text
    IMMUTABLE_PAYLOAD + MONOTONIC_LIFECYCLE
    ACTIVE -> SUPERSEDED
    ```

    Deliberadamente **não** chamado de append-only: o payload e a origem
    são imutáveis, mas o estado avança — que é coisa diferente de uma
    tabela onde nenhuma coluna muda. Chamar isso de append-only faria a
    palavra deixar de significar o que significa em `seal_receipts`.
    """

    ACTIVE = "active"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"
    REVOKED = "revoked"
    NOT_CONFIRMED = "not_confirmed"


E7_4_1_IMPLEMENTED_ENTITLEMENT_TRANSITIONS: frozenset[tuple[EntitlementState, EntitlementState]] = (
    frozenset({(EntitlementState.ACTIVE, EntitlementState.SUPERSEDED)})
)
"""A única transição com produtor nesta entrega."""

ENTITLEMENT_STATES_WITHOUT_PRODUCER_AFTER_E7_4_1: frozenset[str] = frozenset(
    {
        EntitlementState.EXPIRED.value,
        EntitlementState.REVOKED.value,
        EntitlementState.NOT_CONFIRMED.value,
    }
)
"""Declarados e sem produtor. Vocabulário não é capacidade."""


class GenericEndpointType(StrEnum):
    """Tipos genéricos reconhecidos.

    ```text
    Compatibilidade de protocolo prova PROTOCOLO.
    Não prova operador, marca, modelo nem entitlement.
    ```
    """

    GENERIC_MCP_SERVER = "generic_mcp_server"
    OPENAI_COMPATIBLE_ENDPOINT = "openai_compatible_endpoint"
    ANTHROPIC_COMPATIBLE_ENDPOINT = "anthropic_compatible_endpoint"
    LOCAL_INFERENCE_ENDPOINT = "local_inference_endpoint"
    ATTRIBUTED_MULTI_MODEL_GATEWAY = "attributed_multi_model_gateway"
    OPAQUE_MULTI_MODEL_AGGREGATOR = "opaque_multi_model_aggregator"
    EXTERNAL_EVALUATION_SOURCE = "external_evaluation_source"
    SCIENTIFIC_EVIDENCE_SOURCE = "scientific_evidence_source"
    TOOL_OR_APPLICATION_INTEGRATION = "tool_or_application_integration"


class EvidenceCategory(StrEnum):
    """Categoria de uma evidência externa de avaliação.

    ```text
    BENCHMARK NÃO SOBREPÕE AUTORIDADE
    ```

    Evidência é registrada e exibida; nunca seleciona conexão. A ausência
    de qualquer campo de ranking, score agregado ou ordenação preferencial
    nesta camada é o que torna a regra estrutural em vez de verificada.
    """

    EXTERNAL_EVALUATION = "external_evaluation"
    SCIENTIFIC_REFERENCE = "scientific_reference"
    OPERATOR_ANNOUNCEMENT = "operator_announcement"


class CapabilitySource(StrEnum):
    """De onde veio um snapshot de capacidade.

    ```text
    fonte oficial > cache dentro do TTL > cache vencido (DEGRADED) > nada
    NUNCA: varredura de portas, processos ou arquivos locais
    ```

    Não existe membro para varredura, e essa ausência é a mitigação: um
    produtor de varredura não teria como rotular o que produziu.
    """

    OFFICIAL_DISCOVERY = "official_discovery"
    USER_DECLARED_ENDPOINT = "user_declared_endpoint"
    EXECUTION_OBSERVED = "execution_observed"


class SelectionMode(StrEnum):
    """Como uma conexão é escolhida.

    ```text
    SUGESTÃO != EXECUÇÃO
    DELEGAÇÃO != CARTA_BRANCA
    ```
    """

    MANUAL_SELECTION = "manual_selection"
    ASSISTED_SELECTION = "assisted_selection"
    DELEGATED_SELECTION_WITH_REVOCABLE_USER_POLICY = (
        "delegated_selection_with_revocable_user_policy"
    )


EXECUTING_SELECTION_MODES: frozenset[SelectionMode] = frozenset({SelectionMode.MANUAL_SELECTION})
"""Único modo que executa sem confirmação posterior nesta entrega.

`ASSISTED_SELECTION` produz sugestão e para; `DELEGATED_...` depende de
política expressa e revogável, que é E7.4-3.
"""
