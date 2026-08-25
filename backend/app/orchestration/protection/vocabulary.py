"""
Vocabulário próprio da proteção humana (`E7.4-1 B1a`).

Diferente de `ports/governance_vocabulary.py`: aquele espelha a E4 e é
provado por paridade; este descreve coisas que só a E7 possui — a posição do
gate no fluxo e o desfecho da **aplicação** da decisão.

```text
DECISION_IS_ABOUT_AN_OBJECTIVE · APPLICATION_IS_ABOUT_A_GATE
RISK_ANALYSIS_OUTCOME != GATE_EXECUTION_STATE
```
"""

from enum import StrEnum


class GatePosition(StrEnum):
    """Onde o gate é aplicado no fluxo da orquestração.

    ```text
    G1 criação/ativação do Schedule
    G2 preflight, antes do claim
    G3 exportação da etapa, sob o lock final
    G4 concessão de delegação
    ```

    O B1a entrega o vocabulário e o schema; **nenhuma** posição está
    ligada ao caminho produtivo (`ROUTER_MODIFIED_IN_B1A = NO`). B1b ativa
    G2/G3 e B2 ativa G1/G4.
    """

    G1 = "g1"
    G2 = "g2"
    G3 = "g3"
    G4 = "g4"


class ProtectionOutcome(StrEnum):
    """Desfecho da aplicação do gate.

    ```text
    PROHIBITED     -> BLOCKED
    NOT_APPLICABLE -> ALLOWED
    ```

    `REVIEW_REQUIRED` permanece no vocabulário e **sem produtor** em v1: a
    fronteira da E4 é binária, e um descritor inconclusivo é capacidade
    futura da E8. Declarar o membro não o torna alcançável.

    ```text
    REVIEW_REQUIRED_PRODUCER_IN_v1 = NONE
    DECLARED_VOCABULARY != EXECUTABLE_TRANSITION
    ```

    `ALLOWED` não é omissão: ele **prova que o gate rodou**. Sem um
    desfecho positivo registrado, qualquer defeito do gate viraria
    permissão silenciosa.

    ```text
    ABSENCE_OF_EVIDENCE != ABSENCE_OF_DECISION
    ```
    """

    ALLOWED = "allowed"
    BLOCKED = "blocked"
    REVIEW_REQUIRED = "review_required"


PRODUCER_REF = "orchestration.protection.bridge.v1"
"""Único produtor aceito do evento, imposto por `CHECK` no PostgreSQL."""

FINGERPRINT_ALGO_VERSION = "1"
"""Versão do algoritmo de `decision_fingerprint`."""

BINDING_ALGO_VERSION = "1"
"""Versão do algoritmo de `binding_sha256`.

Versionado à parte do fingerprint de propósito: identidade da decisão e
identidade da aplicação podem evoluir em ritmos diferentes, e um único
número esconderia qual das duas mudou.
"""

RETENTION_POLICY_ID = "human_protection_evidence_v1"
"""Política declarada da evidência (Master v2.9.12 §7).

```text
MINIMUM_AGE_DAYS = 365 · EXPIRY_EXECUTOR = E4.9.PEA-0
EXPIRACAO_DO_EVENTO = NOT_IMPLEMENTED
§20.6_RETENTION_COMPLIANCE = NOT_SATISFIED_BY_E7_4_1_ALONE
```

Constante **declarativa**: nada na E7.4-1 apaga evento. Enquanto a
E4.9.PEA-0 não existir, a evidência permanece por mais tempo — o que não
autoriza apagamento por processo comum nem reduz o append-only.
"""

RETENTION_MINIMUM_AGE_DAYS = 365
"""Horizonte mínimo declarado, sem executor nesta entrega."""
