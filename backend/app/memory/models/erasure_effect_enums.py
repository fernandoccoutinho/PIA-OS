"""
Vocabulário fechado da fronteira de efeito destrutivo (`E4.9.9.b`).

```text
APPROVAL   != CONSUMPTION
CONSUMPTION != EFFECT
EFFECT      != ERASURE_RECORD
NO_MATERIAL_ATTEMPT -> NO_ERASURE_RECORD
```
"""

from enum import StrEnum


class MaterialAttemptRefusalReason(StrEnum):
    """Por que **nenhuma tentativa material começou** (`E4.9.9.b`).

    ```text
    NOT_STARTED != FAILED
    NOT_STARTED != PARTIAL
    ```

    Quatro membros, e a escolha do vocabulário é deliberada: cada um é um
    fato observado **na fronteira de efeito**, por quem ia tentar e não
    tentou.

    ## Por que não repetir as recusas anteriores

    `TargetResolutionRefusalReason` descreve por que um alvo não foi
    resolvido; `ApprovalUsageRefusalReason`, por que uma aprovação não
    pôde ser usada. Ambas pertencem a etapas que já terminaram quando
    esta fronteira é alcançada — a requisição de efeito só existe com
    descritor resolvido e evidência de consumo.

    Copiá-las para cá inflaria o enum sem acrescentar distinção alguma, e
    faria a fronteira de efeito parecer capaz de observar coisas que ela
    não observa.

    ## Sem membro genérico

    Nem `UNKNOWN`, nem `OTHER`, nem `ERROR`. Uma exceção inesperada do
    adaptador **não** é nenhum destes motivos: é estado ambíguo, e a
    E4.9.9.d decidirá o que fazer com ele.

    ```text
    EXCEPTION != OBSERVED_OUTCOME
    TIMEOUT   != PROOF_OF_NO_EFFECT
    ```
    """

    ADAPTER_UNAVAILABLE = "adapter_unavailable"
    """Não há adaptador capaz de atender a requisição.

    É o estado de todo o sistema hoje: `ERASURE_EFFECT_ADAPTER = NONE`.
    """

    OPERATION_NOT_SUPPORTED = "operation_not_supported"
    """O adaptador conhece o provedor e a operação aprovada não é
    suportada por ele.

    ```text
    CAPABILITY_OPERATION_SEMANTICS = ADAPTER_BOUNDARY
    ```

    Este motivo existe porque a correspondência entre a operação aprovada
    e a capacidade concedida pelo provedor **não é conhecida nesta
    camada** — `capability.operation` é texto opaco do provedor, e não há
    contrato canônico que o traduza. Quem sabe é o adaptador, e é ele quem
    devolve esta recusa antes de qualquer efeito.
    """

    CAPABILITY_REFUSED_BEFORE_ATTEMPT = "capability_refused_before_attempt"
    """O provedor recusou a capacidade antes de a tentativa começar.

    Distinto de `OPERATION_NOT_SUPPORTED`: ali a operação não existe para
    aquele adaptador; aqui existe, e a credencial ou o escopo concedido
    não a alcança.
    """

    PROVIDER_PRECONDITION_REFUSED = "provider_precondition_refused"
    """Uma precondição do provedor não foi satisfeita antes da tentativa.

    Objeto sob retenção do lado do provedor, bucket com política de
    imutabilidade, versão travada. O adaptador observou a recusa **antes**
    de qualquer escrita — e por isso ainda é não-tentativa.
    """


class EffectAttemptStage(StrEnum):
    """O que a fronteira observou: nada começou, ou algo foi tentado.

    ```text
    NOT_STARTED | MATERIAL_ATTEMPT_OBSERVED
    ```

    ```text
    DISJOINT_RESULT_TYPE = SOURCE_OF_TRUTH
    STAGE = DERIVED_TAG_ONLY
    ```

    Existe para tornar a disjunção **legível na própria instância**, sem
    obrigar quem lê a inspecionar o tipo. Nunca é argumento de construtor:
    é `@property` constante em cada classe, fora de `dataclasses.fields`
    e fora de `__init__`.

    Se fosse campo, seria possível construir um resultado cujo estágio
    contradissesse a própria classe — uma não-tentativa marcada como
    observada, ou o inverso —, e a etiqueta passaria a competir com o tipo
    pela verdade.

    Deliberadamente **não** entra em `ErasureOutcome`: colocar
    `NOT_STARTED` lá o tornaria elegível a recibo, e a E4.9.0 fechou o
    recibo para o que foi materialmente observado.

    ```text
    NOT_STARTED not in ErasureOutcome
    NOT_STARTED -> NO_ERASURE_RECORD
    ```
    """

    NOT_STARTED = "not_started"
    MATERIAL_ATTEMPT_OBSERVED = "material_attempt_observed"
