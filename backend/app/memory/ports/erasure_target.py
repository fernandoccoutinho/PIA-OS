"""
Porta observacional de resolução de alvo (`E4.9.7`).

```text
referência + escopo declarado -> descritor verificado | recusa tipada
```

Uma porta declara a **forma** de algo que a E4 consome e não implementa.
Aqui o que não existe é o adaptador: não há storage, conector, executor
nem credencial em lugar algum do repositório, e esta fatia não os cria.

## Uma porta, não duas

A E4.9.1 autorizou **duas** portas e exigiu que permanecessem separadas:

```text
ErasureTargetResolverPort   referência -> descritor | recusa      (esta fatia)
ErasureEffectPort           descritor + autorização -> tentativa  (fatia futura)
```

`ErasureEffectPort` **não** é materializada aqui, e a ausência é
deliberada. Declarar a fronteira de efeito junto da de resolução
convidaria a compor as duas no mesmo consumidor, e a separação existe
justamente porque resolver não pode ter efeito colateral: se tivesse,
uma consulta exploratória já seria uma ação destrutiva parcial, e nenhuma
aprovação posterior a desfaria.

```text
RESOLUTION_IS_OBSERVATIONAL = TRUE
TARGET_RESOLUTION != DELETION_AUTHORITY
```

## O que a assinatura não recebe

Nem `Session`, nem `UnitOfWork`, nem repositório, nem `ErasureRecord`,
nem aprovação, nem executor, nem callback de efeito. Não é convenção: é
a garantia. Um resolvedor que recebesse sessão poderia escrever, e
nenhuma docstring impediria — a recusa vive no tipo, e uma guarda
estática prova que os nomes proibidos não aparecem no módulo.
"""

from typing import Protocol, runtime_checkable

from app.memory.schemas.erasure_target import (
    ErasureTargetReference,
    TargetResolutionResult,
)


@runtime_checkable
class ErasureTargetResolverPort(Protocol):
    """Classifica e resolve uma referência, sem produzir efeito.

    `runtime_checkable` segue o precedente da E4.5 e da E4.7 — e com a
    ressalva que a E4.7.1 pagou para aprender:

    ```text
    RUNTIME_CHECKABLE != STATIC SIGNATURE COMPATIBILITY
    ```

    `isinstance` confere apenas **nomes de membros**. A compatibilidade
    de assinatura é provada estaticamente, por atribuição verificada pelo
    mypy num teste próprio, e não por `isinstance` sozinho.
    """

    def resolve_target(self, reference: ErasureTargetReference) -> TargetResolutionResult:
        """Devolve descritor verificado **ou** recusa tipada.

        Não levanta exceção como resultado normal de não resolução: a
        recusa é um valor, e o chamador a distingue do sucesso por
        `isinstance`, sem `Any` nem `cast`.

        O implementador **não pode** apagar, marcar, mover, persistir,
        registrar recibo ou alterar a referência. Um adaptador que
        escrevesse durante a resolução violaria
        `RESOLUTION_IS_OBSERVATIONAL` mesmo satisfazendo este `Protocol`,
        e é por isso que a fatia entrega também um dublê observacional
        nos testes, que mede escritas e chamadas externas em zero.
        """
        ...  # pragma: no cover - corpo de Protocol, nunca executado
