"""
Vocabulários fechados da fronteira de conformidade (`E4.10`).

```text
INTEGRITY   = estado × invariantes estruturais
GOVERNANCE  = ação × permissão
COMPLIANCE  = estado/ação × policy
```

A distinção Integridade/Conformidade é a que mais facilmente se perde,
e o `E4_GOVERNANCE_BOUNDARIES` §3 a fixa com um exemplo que decide tudo:
um ciclo causal é falha de **integridade** — seria falha em qualquer
instalação do PIA-OS; um objeto avaliado contra uma política específica
é conformidade — outra instalação, com outra política, não teria falha
alguma.

Daí decorre o que estes enums fazem e o que recusam:

```text
COMPLIANCE != INTEGRITY
COMPLIANCE != GOVERNANCE_DECISION
COMPLIANCE != REPAIR
COMPLIANCE != LEARNING
REPAIR_IMPLEMENTED = NO
```

Nenhum membro `UNKNOWN`, `OTHER` ou `ERROR`. Um coringa absorveria em
silêncio o caso que ninguém previu, e o caso que ninguém previu é
exatamente o que precisa aparecer.
"""

from enum import StrEnum


class ComplianceOutcome(StrEnum):
    """Os quatro desfechos disjuntos de uma avaliação de conformidade.

    ```text
    NO_POLICY                != COMPLIANT
    INSUFFICIENT_INFORMATION != COMPLIANT
    ```

    Três não bastariam. Sem `INSUFFICIENT_INFORMATION`, a falta de
    observação cairia em `COMPLIANT` ou em `VIOLATION_CONFIRMED`, e as
    duas seriam afirmações que ninguém observou — o mesmo erro que a
    E4.9.9.c evitou ao separar `NO_POLICY` de `ELIGIBLE`.
    """

    COMPLIANT = "compliant"
    """A política se aplicava, foi avaliada e nada a viola.

    Nunca significa "o patrimônio é verdadeiro sobre a realidade": a
    E3.10 já congelou `INTERNALLY_CONSISTENT != TRUE_ABOUT_REALITY`, e
    conformidade é ainda mais estreita — vale para **uma** versão de
    **uma** política, no instante avaliado.
    """

    POLICY_NOT_APPLICABLE = "policy_not_applicable"
    """A política não alcança o sujeito, ou não vigorava no instante.

    Não é conformidade e não autoriza nada — `NOT_APPLICABLE DOES NOT
    AUTHORIZE`, herdado literalmente da E4.3 e da E4.7.
    """

    INSUFFICIENT_INFORMATION = "insufficient_information"
    """Faltou observação para decidir.

    Condição da **observação**, não do sujeito. É por isso que não gera
    finding: um finding afirmaria que há algo errado com o objeto,
    quando o que falta é dado sobre ele.
    """

    VIOLATION_CONFIRMED = "violation_confirmed"
    """Ao menos uma violação localizada, com evidência.

    Diagnóstico, nunca comando: `COMPLIANCE != REPAIR`.
    """


class PolicyKind(StrEnum):
    """Qual família de política foi avaliada.

    Fechada nas três que existem persistidas e versionadas na cadeia 94.
    Um membro para família inexistente prometeria uma avaliação que
    nenhuma regra sustenta.
    """

    GOVERNANCE = "governance"
    ACCESSIBILITY = "accessibility"
    RETENTION = "retention"


class ComplianceSubjectKind(StrEnum):
    """O que está sendo avaliado.

    ```text
    GOVERNANCE    <-> GOVERNED_OPERATION
    ACCESSIBILITY <-> ACCESSIBILITY_TRANSITION
    RETENTION     <-> RETENTION_CANDIDATE
    ```

    Exatamente três, em correspondência biunívoca com `PolicyKind`. Um
    membro genérico de objeto cognitivo não teria observação nem
    semântica correspondente — seria um sujeito sobre o qual nenhuma
    das três matrizes sabe responder, e a avaliação teria de inventar
    um desfecho.
    """

    GOVERNED_OPERATION = "governed_operation"
    ACCESSIBILITY_TRANSITION = "accessibility_transition"
    RETENTION_CANDIDATE = "retention_candidate"


class ObservedOperationState(StrEnum):
    """O que **aconteceu** com a operação governada.

    ```text
    PRESCRIPTION != FACT
    ADMISSION    != OBLIGATION_TO_EXECUTE
    ```

    Enum próprio, e não `GovernanceEffect`: aquele expressa o que a
    política **prescreve** (`ADMIT`/`DENY`), e reaproveitá-lo para
    descrever o observado faria prescrição e fato compartilharem o
    mesmo tipo — a confusão exata que esta fronteira existe para
    impedir.

    `NOT_OBSERVED` é membro, e não `None`: um booleano ou uma ausência
    implícita não distinguiriam *não executou* de *ninguém olhou*.
    """

    EXECUTED = "executed"
    NOT_EXECUTED = "not_executed"
    NOT_OBSERVED = "not_observed"


class CausalEvidencePresence(StrEnum):
    """Se a evidência causal exigida foi observada.

    `causally_extinct` é o único destino que exige evidência causal
    verificada (E4.7). `ABSENT` é fato observado — alguém procurou e não
    havia; `NOT_OBSERVED` é ausência de observação, e leva a
    insuficiência, nunca a violação.
    """

    PRESENT = "present"
    ABSENT = "absent"
    NOT_OBSERVED = "not_observed"


class AssessmentInformationState(StrEnum):
    """Se a avaliação e a informação exigidas após elegibilidade ocorreram.

    ```text
    MINIMUM_AGE      = PRESERVATION_FLOOR
    MINIMUM_AGE     != DELETION_DEADLINE
    ASSESS_AND_INFORM != DELETE
    ```

    `minimum_age_days` é prazo **mínimo de preservação**. Passar dele
    não viola nada: torna o item elegível a ser avaliado e informado. O
    que a política exige a partir daí é a avaliação — e `ABSENT`
    significa que ela foi procurada e confirmadamente não existe.
    """

    PRESENT = "present"
    ABSENT = "absent"
    NOT_OBSERVED = "not_observed"


class PolicyWindowState(StrEnum):
    """Posição do instante avaliado na janela de vigência da política.

    Janela de início **inclusivo** e fim **exclusivo**, idêntica à que a
    E4.9.9.c congelou — duas leituras diferentes da mesma janela dariam
    dois desfechos para o mesmo fato.
    """

    EFFECTIVE = "effective"
    BEFORE_WINDOW = "before_window"
    AFTER_WINDOW = "after_window"


class MissingObservation(StrEnum):
    """O que faltou observar — vocabulário fechado, nunca texto livre.

    A razão da insuficiência precisa ser consumível por máquina: quem
    recebe o relatório tem de saber **o que ir buscar** para conseguir
    uma resposta, e uma frase em português não diz isso a um programa.
    """

    ANCHOR_TIMESTAMP = "anchor_timestamp"
    DECLARED_SOURCE_STATE = "declared_source_state"
    OBSERVED_OPERATION_STATE = "observed_operation_state"
    CAUSAL_EVIDENCE = "causal_evidence"
    ASSESSMENT_INFORMATION = "assessment_information"


class ComplianceCode(StrEnum):
    """Códigos diagnósticos de conformidade.

    ```text
    FINDING  = OBSERVATION
    FINDING != EXCEPTION
    ```

    Deliberadamente **fora** do catálogo `PIA-8xxx`, pela mesma razão
    que a E3.10 manteve `INTEGRITY-*` separado: uma violação encontrada
    é resultado válido da avaliação, não falha de execução. Exceções
    continuam reservadas ao que impede a avaliação de acontecer.
    """

    GOVERNANCE_OPERATION_EXECUTED_AGAINST_DENY = "COMPLIANCE-GOV-001"
    """Operação executada contra regra que a negava."""

    GOVERNANCE_OPERATION_EXECUTED_WITHOUT_RULE = "COMPLIANCE-GOV-002"
    """Operação executada sob política vigente que não a alcança.

    Distinto de `GOV-001` e a distinção é material: lá havia regra e ela
    dizia não; aqui não havia regra alguma. `NO_MATCH = NOT_APPLICABLE`
    vale para a **decisão** de governança; para conformidade, executar
    sob política vigente sem regra aplicável é fato que merece ser
    visto — sem que isso o transforme em negação retroativa.
    """

    ACCESSIBILITY_TRANSITION_AGAINST_DENY = "COMPLIANCE-ACC-001"
    """Transição observada contra regra `DENY` da versão avaliada."""

    ACCESSIBILITY_EXTINCTION_WITHOUT_EVIDENCE = "COMPLIANCE-ACC-002"
    """Extinção causal observada sem a evidência que a autoriza."""

    ACCESSIBILITY_TRANSITION_WITHOUT_RULE = "COMPLIANCE-ACC-003"
    """Transição observada sem regra aplicável na versão vigente."""

    RETENTION_ASSESSMENT_INFORMATION_ABSENT = "COMPLIANCE-RET-001"
    """Elegibilidade alcançada e a avaliação exigida está ausente.

    ```text
    AGE >= MINIMUM_AGE != VIOLATION_BY_PERMANENCE
    ```

    Não significa "retido além do prazo". Significa que a política
    exigia avaliar e informar a partir da elegibilidade, e a informação
    foi procurada e confirmadamente não existe.
    """
