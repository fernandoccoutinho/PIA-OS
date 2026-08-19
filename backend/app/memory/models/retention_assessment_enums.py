"""
Vocabulário fechado da avaliação de retenção (`E4.9.9.c`).

```text
ASSESSMENT_ELIGIBILITY != DELETION_DECISION
EVALUATION             != DISPOSITION
NO_POLICY              != ELIGIBLE
```
"""

from enum import StrEnum


class RetentionAssessmentDecision(StrEnum):
    """O que a avaliação de retenção conclui — cinco membros, nenhum a mais.

    Nenhum membro sugere apagar, mover, agendar ou dispor. A avaliação
    **informa**; a decisão continua sendo do usuário, pelo caminho de
    aprovação da E4.9.8.

    ## Precedência, e por que ela é ordenada assim

    ```text
    1. POLICY_NOT_EFFECTIVE        a regra sequer vale hoje
    2. OUT_OF_SCOPE                nenhuma regra fala deste item
    3. PRESERVE_LEGACY_PROTECTED   o titular pediu para preservar
    4. NOT_YET_DUE                 vale, alcança, mas ainda não venceu
    5. ASSESS_AND_INFORM           venceu o MAIOR prazo aplicável
    ```

    A ordem não é arbitrária. Cada degrau responde a uma pergunta que só
    faz sentido depois da anterior: perguntar se venceu antes de saber se
    a policy vigora produziria vencimento sob regra que não vale;
    perguntar sobre prazo antes da proteção de legado produziria
    "elegível" para item que o titular pediu para preservar.
    """

    POLICY_NOT_EFFECTIVE = "policy_not_effective"
    """A policy não vigora no instante avaliado.

    Janela `[effective_from, effective_until)` — início inclusivo, fim
    **exclusivo**. Uma policy que terminou não avalia nada, e uma que
    ainda não começou também não.
    """

    OUT_OF_SCOPE = "out_of_scope"
    """Nenhuma regra vigente alcança este candidato.

    ```text
    NO_APPLICABLE_RULE != NOT_YET_DUE
    NO_POLICY          != ELIGIBLE
    ```

    Distinto de `NOT_YET_DUE` de propósito. Colapsá-los faria "nenhuma
    regra fala deste item" parecer "ainda não venceu", e a segunda
    leitura sugere que um dia vencerá — o que seria falso e induziria
    quem lê a esperar por uma elegibilidade que não vem.
    """

    PRESERVE_LEGACY_PROTECTED = "preserve_legacy_protected"
    """O candidato está protegido como legado.

    ```text
    LEGACY_PROTECTION_OVERRIDES_RETENTION_ELIGIBILITY
    ```

    Vem **antes** do prazo: proteção de legado é escolha do titular, e
    prazo cumprido não a revoga. Retenção vencida sobre item protegido
    não produz elegibilidade — produz esta decisão, que diz exatamente o
    que está acontecendo.

    A E4.9.8.3 tornou este estado vinculável justamente para que ele
    fosse observável aqui.
    """

    NOT_YET_DUE = "not_yet_due"
    """Há regra vigente e aplicável, mas o maior prazo ainda não venceu.

    O resultado carrega `next_due_at`, para que quem informa o usuário
    saiba **quando** a situação muda.
    """

    ASSESS_AND_INFORM = "assess_and_inform"
    """Venceu o maior prazo aplicável — inicia-se **avaliação**.

    ```text
    ASSESS_AND_INFORM != DELETE
    ASSESS_AND_INFORM != MOVE_TO_TRASH
    ASSESS_AND_INFORM != SCHEDULE_DISPOSITION
    ```

    O nome é o mesmo de `RetentionExpiryAction`, que tem **um único
    membro** desde a E4.9.6 — e é essa unicidade que prova que
    vencimento nunca dispôs de nada. Esta fatia não pode ampliá-la.
    """
