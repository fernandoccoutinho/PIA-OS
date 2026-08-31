"""
Vocabulários fechados do ciclo de vida da aprovação persistida (`E4.9.9.a`).

```text
PERSISTED_APPROVAL != AUTHENTICATED_USER
PERSISTED_APPROVAL != EXECUTION
APPROVAL_RECORD    != ERASURE_RECORD
CONSUMED_APPROVAL  != OBSERVED_ERASURE_ATTEMPT
```

Três `StrEnum` fechados. Ampliar exige EDR.
"""

from enum import StrEnum


class ApprovalLifecycleState(StrEnum):
    """Estado de utilizabilidade da aprovação — três membros, nenhum a mais.

    ```text
    ACTIVE | CONSUMED | REVOKED
    ```

    **Não existe `EXPIRED`.** Expiração é condição **derivada** de
    `expires_at`, avaliada contra o relógio do banco no instante da
    decisão. Um estado persistido exigiria alguém para escrevê-lo —
    scheduler, worker ou job —, e nada disso é autorizado nesta fatia.
    Pior: entre o vencimento real e a passagem do scheduler, a linha diria
    `ACTIVE` sobre uma aprovação já vencida.

    ```text
    EXPIRY_IS_DERIVED_NOT_STORED
    ```

    **Não existem estados de execução.** Nem `EXECUTING`, `SUCCEEDED`,
    `FAILED`, `PARTIAL` ou `RECEIPTED`. O que aconteceu materialmente
    pertence a `ErasureRecord`, e a E4.9.0 já proibiu desfecho em
    andamento naquele modelo. Repetir a distinção aqui não é redundância:
    é a mesma fronteira vista do outro lado.
    """

    ACTIVE = "active"
    """Ainda utilizável, se não estiver vencida no instante da decisão."""

    CONSUMED = "consumed"
    """Usada uma vez. Terminal — nenhuma transição parte daqui."""

    REVOKED = "revoked"
    """Retirada antes do uso. Terminal.

    ```text
    CONSUMED_BEFORE_REVOCATION -> REVOCATION_CANNOT_UNDO_CONSUMPTION
    ```

    Revogar depois do consumo **não** desfaz nada — e esta fatia sequer
    executa, então não há efeito futuro a impedir.
    """

    @property
    def is_terminal(self) -> bool:
        """Estado do qual nenhuma transição parte."""
        return self is not ApprovalLifecycleState.ACTIVE


class GovernanceItemKind(StrEnum):
    """Qual campo de tupla da `GovernanceResolution` o item representa.

    ```text
    JSON_STORAGE = FORBIDDEN
    GOVERNANCE_ORDER = PRESERVED
    ```

    `GovernanceResolution` tem seis campos de **tupla ordenada**, e o
    contrato da E4.9.8 exige a resolução **exata** para reconstruir a
    proposta — reconstruir a partir de referências obrigaria a inventar os
    demais campos, que é o que o §3.3 proíbe.

    Guardá-los em JSON reabriria a fronteira que a E4.9.6 fechou em três
    corretivos. Guardá-los em seis tabelas seria oito tabelas ao todo.
    Este vocabulário permite **uma** tabela-filha ordenada, com
    `position` preservando a ordem e `UNIQUE(record, kind, position)`.

    Cada membro declara o tipo do valor que carrega, e o `CHECK` do banco
    é condicionado ao `kind` — nada de coluna textual polimórfica.
    """

    DOMAIN_ID = "domain_id"
    """`context_domain_ids` — valor em `value_uuid`."""

    BLOCKED_CAPABILITY = "blocked_capability"
    """`blocked_capabilities` — valor em `value_enum`, vocabulário
    `CriticalCapability`."""

    ADMISSIBLE_ALTERNATIVE = "admissible_alternative"
    """`admissible_alternatives` — valor em `value_text`."""

    CONSTRAINT = "constraint"
    """`constraints` — valor em `value_text`."""

    DECLARED_PRESERVATION = "declared_preservation"
    """`declared_preservations` — valor em `value_text`."""

    DECLARED_LOSS = "declared_loss"
    """`declared_losses` — valor em `value_text`."""

    @property
    def coluna_de_valor(self) -> str:
        """Qual das três colunas mutuamente exclusivas carrega o valor."""
        if self is GovernanceItemKind.DOMAIN_ID:
            return "value_uuid"
        if self is GovernanceItemKind.BLOCKED_CAPABILITY:
            return "value_enum"
        return "value_text"


class ApprovalUsageRefusalReason(StrEnum):
    """Por que uma tentativa de consumo ou revogação **não** procedeu.

    ```text
    REFUSAL_REASON != FREE_TEXT_DIAGNOSTIC
    BOOLEAN_OUTCOME = FORBIDDEN
    ```

    Vocabulário fechado, pela mesma razão de `ApprovalBlockerKind` na
    E4.9.8: diagnóstico textual livre é canal de confidencialidade, e a
    auditoria da E4.9.7.2 mediu um aceitando o próprio localizador.

    Um `bool` também não serve — `False` não distingue "expirada" de
    "binding divergente", e a segunda hipótese é um sinal que ninguém
    deveria perder.

    ## Sobre a origem destes motivos

    O comando de consumo é **um único `UPDATE` condicional**. Quando ele
    devolve zero linhas, o motivo vem de uma releitura **diagnóstica**,
    que jamais converte derrota em sucesso: se a releitura mostrar
    `ACTIVE` e não vencida, o desfecho é `LOST_CONCURRENT_RACE`, porque
    outra sessão venceu entre o `UPDATE` e a leitura.
    """

    NOT_FOUND = "not_found"
    ALREADY_CONSUMED = "already_consumed"
    REVOKED = "revoked"
    EXPIRED = "expired"
    BINDING_MISMATCH = "binding_mismatch"
    """O binding esperado não corresponde ao persistido."""

    PERSISTED_ROW_INVALID = "persisted_row_invalid"
    """A linha existe mas não reconstrói contrato válido."""

    LOST_CONCURRENT_RACE = "lost_concurrent_race"
    """Outra sessão venceu; a linha ainda parecia utilizável na releitura."""
