"""
`ErasureEffectPort` — a segunda porta autorizada pela E4.9.1 (`E4.9.9.b`).

```text
ErasureTargetResolverPort
    referência + escopo -> descritor | recusa

ErasureEffectPort
    descritor fresco + evidência de consumo -> não tentado | observado
```

## Duas portas, e a separação importa

A E4.9.1 autorizou duas e exigiu que permanecessem separadas. Resolver um
alvo e apagá-lo são autoridades diferentes:

```text
RESOLUTION != DELETION_AUTHORITY
```

Uma porta única deixaria quem sabe **onde** o objeto está com o poder de
**destruí-lo**. Por isso não há método de resolução aqui, nem método de
efeito lá.

## O port declara fronteira; ele não implementa efeito

```text
ERASURE_EFFECT_ADAPTER = NONE
```

Nenhum adaptador existe, e esta fatia não cria um. Um `Protocol` sem
implementação é o estado correto: a fronteira fica escrita e verificável
antes de qualquer código tocar objeto material.
"""

from typing import Protocol, runtime_checkable

from app.memory.schemas.erasure_effect import (
    ErasureEffectRequest,
    ErasureEffectResult,
)


@runtime_checkable
class ErasureEffectPort(Protocol):
    """Fronteira entre a decisão consumida e o efeito material.

    ## Uma requisição, um resultado disjunto

    ```text
    attempt_effect(request) -> MaterialAttemptNotStarted | ObservedAttemptResult
    ```

    Sem `Session`, unit of work, repositório, callback, logger, storage ou
    cliente externo na assinatura. Um `Session` aqui deixaria o adaptador
    escrever no banco durante o efeito, e a única escrita legítima depois
    de uma tentativa é o recibo — que pertence a outra camada.

    ## Sobre `runtime_checkable`

    ```text
    RUNTIME_CHECKABLE != SIGNATURE_PROOF
    ```

    `isinstance` contra um `Protocol` verifica apenas a **presença** do
    membro, nunca a assinatura. Quem prova a assinatura é o mypy, sobre a
    atribuição estática. O decorador está aqui para conveniência de teste,
    e o EDR registra o limite em vez de deixá-lo implícito.

    ## O que o adaptador futuro terá de decidir

    ```text
    CAPABILITY_OPERATION_SEMANTICS = ADAPTER_BOUNDARY
    ```

    A correspondência entre a operação aprovada e a capacidade concedida
    pelo provedor **não é conhecida** na camada de aplicação:
    `capability.operation` é texto opaco do provedor. O adaptador conhece,
    e devolve `OPERATION_NOT_SUPPORTED` ou
    `CAPABILITY_REFUSED_BEFORE_ATTEMPT` **antes** de qualquer efeito.

    ## Exceção não é desfecho

    ```text
    EXCEPTION != OBSERVED_OUTCOME
    TIMEOUT   != PROOF_OF_NO_EFFECT
    NO_FABRICATED_ERASURE_RECORD_FROM_EXCEPTION
    ```

    Desfecho adverso normal é **valor tipado**. Uma exceção inesperada
    deixa estado ambíguo: a camada superior não pode inferir `FAILED`,
    `PARTIAL` nem `NOT_STARTED` sem observação. Esta fatia documenta a
    fronteira; o tratamento operacional é da E4.9.9.d.
    """

    def attempt_effect(self, request: ErasureEffectRequest) -> ErasureEffectResult:
        """Tenta o efeito material e devolve o que foi observado."""
        ...
