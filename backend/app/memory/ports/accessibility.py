"""
Portas estruturais para a transição de acessibilidade sancionada da E3
(`E4.7`).

`app/memory` nunca importa `app.cognitive` — fronteira verificada por
`G17` (E3.12) e `MD6` (E4.1). Precedente: as portas da E4.5
(`consolidation.py`) e da E4.6 (`retrieval.py`).

## Três portas, três responsabilidades

```text
CognitiveSubjectPort           resolver e BLOQUEAR a linha do sujeito
AccessibilityTransitionPort    ler estado e delegar a escrita ao manager E3
CausalEvidencePort             verificar que um evento pertence ao sujeito
```

Separadas porque são satisfeitas por objetos diferentes da E3 —
`ObjectRepository`, `AccessibilityManager` e `CausalHistoryRepository` —
e fundi-las obrigaria o compositor a inventar um adapter.

## Sujeito opaco

`SubjectT` é um `TypeVar` sem limite: o `CognitiveObject` atravessa a
E4.7 **sem ser inspecionado**. A E4.7 nunca lê um campo dele
diretamente; obtém o estado por `AccessibilityTransitionPort.get_state()`
e entrega o mesmo objeto de volta ao manager sancionado. Isso mantém a
E3 como dona do patrimônio:

    E3 REMAINS SOURCE OF TRUTH FOR ACCESSIBILITY STATE

## Estados: genéricos, não textuais

**Corretivo E4.7.1.** A versão anterior declarava `target_state: str`, e
o `AccessibilityManager` real exige `AccessibilityState`. Retorno
covariante não torna parâmetro covariante: a porta **não** era satisfeita
por atribuição estática, e `isinstance` com `runtime_checkable` não
revelava isso porque confere apenas nomes de membros.

    RUNTIME_CHECKABLE != STATIC SIGNATURE COMPATIBILITY
    PORT METHOD NAME != PORT TRUTHFULNESS

`StateT` resolve isso: a porta é genérica sobre o estado real, e a
conformidade é provada por atribuição verificada pelo mypy — não por
presença de método.

Sem `Any`, `cast`, `type: ignore`, reflexão, `getattr`, `hasattr`,
`importlib`, registry ou `sys.modules`.

## O lock é parte do contrato

`CognitiveSubjectPort.lock_for_update()` existe porque a autorização
depende do estado de origem, e um estado lido **sem** lock pode mudar
antes da escrita:

    PRE-LOCK SOURCE STATE != AUTHORIZED WRITE PRECONDITION
    POLICY(ACTIVE → TARGET) != POLICY(ANY CURRENT STATE → TARGET)
    LAST-WRITE-WINS != VALID TRANSITION

O `ObjectRepository.refresh_for_update()` da E3 emite
`SELECT ... FOR UPDATE` e mantém a linha bloqueada **até o fim da
transação** — por isso o estado observado depois dele é o mesmo que o
manager verá ao escrever, desde que tudo aconteça na mesma `Session`.
"""

import uuid
from typing import Protocol, TypeVar, runtime_checkable

SubjectT = TypeVar("SubjectT")
"""Sujeito cognitivo, **opaco** para a E4.7.

Sem limite de tipo de propósito: a E4.7 transporta o objeto entre as
portas sem nunca inspecioná-lo. Dar-lhe um limite exigiria descrever
campos do patrimônio aqui, e a descrição divergiria da E3 com o tempo.
"""


EventT_co = TypeVar("EventT_co", covariant=True)
"""Evento causal da E3, **opaco** para a porta.

Genérico pelo mesmo motivo que `SubjectT`: os modelos da E3 declaram
seus campos como `Mapped[...]`, e um `Protocol` que prometesse
`id: uuid.UUID` **não** seria satisfeito por atribuição estática — o
mypy compara a anotação declarada, não o que o descritor devolve em
runtime.

A E4.7 recebe o objeto opaco e o estreita com `isinstance` contra
`CausalEventView`, que é `runtime_checkable`. O `isinstance` **tipa** o
objeto para o mypy, então a leitura dos campos é verificada
estaticamente — sem `Any`, `cast` ou reflexão.
"""

HistoryT_co = TypeVar("HistoryT_co", covariant=True)
"""História causal da E3, opaca — ver `EventT_co`.

Covariante porque a porta apenas **produz** esses objetos: uma
implementação que devolva um tipo mais específico continua utilizável
onde se espera o mais geral.
"""

StateT = TypeVar("StateT", bound=str)
"""Estado de acessibilidade **real** da E3.

`bound=str` porque `AccessibilityState` é `StrEnum` — a ligação aceita o
enum real e mantém a porta satisfeita **por atribuição estática**, não
apenas por presença de membros.

A E4.7 recebe e repassa o estado real; o token textual serve para policy,
log, decisão e resultado, e nunca é convertido em pseudo-enum.

    TOKEN BRIDGE != DOMAIN ENUM OWNERSHIP
"""


@runtime_checkable
class SubjectIdentityView(Protocol):
    """Identidade observável de um sujeito cognitivo (corretivo E4.7.1).

    O sujeito continua genérico e opaco quanto ao **conteúdo**, mas a
    E4.7 precisa poder confirmar que o objeto devolvido por cada porta é
    o que foi pedido:

        REQUESTED ID != RETURNED ID
        PORT RETURN != TRUSTED FACT UNTIL FIDELITY IS VERIFIED

    Sem esta view, uma porta podia devolver o sujeito B para um pedido
    sobre A, e a E4.7 escrevia em B enquanto o resultado citava A.
    """

    @property
    def id(self) -> uuid.UUID:
        """COID do sujeito."""


@runtime_checkable
class CognitiveSubjectPort(Protocol[SubjectT]):
    """Resolve o sujeito pelo COID e adquire o lock de linha.

    Satisfeita estruturalmente por `ObjectRepository` (E3.1).
    """

    def get_by_id(self, entity_id: object, *, include_deleted: bool = False) -> SubjectT | None:
        """Sujeito com este COID, ou `None`.

        `include_deleted=True` é o caminho da E4.7: um objeto com
        exclusão lógica **existe** e é sujeito legítimo de uma decisão
        de acessibilidade.

            SOFT_DELETED != NEVER EXISTED
        """
        ...  # pragma: no cover - corpo de stub de Protocol, nunca executado

    def refresh_for_update(self, entity: SubjectT) -> SubjectT:
        """`SELECT ... FOR UPDATE`: bloqueia a linha e recarrega o estado.

        O lock permanece até commit/rollback da `UnitOfWork` do
        chamador. É esta propriedade que torna o estado observado
        depois daqui uma precondição válida para a escrita.
        """
        ...  # pragma: no cover - corpo de stub de Protocol, nunca executado


@runtime_checkable
class AccessibilityTransitionPort(Protocol[SubjectT, StateT]):
    """Lê o estado e delega a escrita ao manager sancionado da E3.

    Satisfeita estruturalmente por `AccessibilityManager` (E3.6).

    A E4.7 **não** reimplementa a transição: não há segundo writer, nem
    SQL paralelo. A porta existe para invocar o caminho da E3, não para
    substituí-lo.
    """

    def get_state(self, obj: SubjectT) -> StateT:
        """Estado **real** do sujeito, como a E3 o expõe."""
        ...  # pragma: no cover - corpo de stub de Protocol, nunca executado

    def transition(
        self, obj: SubjectT, target_state: StateT, *, reason: str | None = None
    ) -> SubjectT:
        """Escreve o estado-alvo pelo manager sancionado.

        Idempotente na E3: alvo igual ao atual é no-op. `reason`
        não-vazio continua exigido para `causally_extinct` — a E4.7 o
        fornece **além** de verificar a evidência causal, sem substituir
        uma exigência pela outra.
        """
        ...  # pragma: no cover - corpo de stub de Protocol, nunca executado


@runtime_checkable
class CausalEventView(Protocol):
    """Forma mínima de um `CausalHistoryEvent`, para verificar
    pertencimento.

    Somente-leitura por construção. A E4.7 lê apenas a identidade do
    evento e a da história a que ele pertence — nunca tipo, ator,
    payload ou predecessor, que não são da sua conta.
    """

    @property
    def id(self) -> uuid.UUID:
        """Identidade do evento."""

    @property
    def history_id(self) -> uuid.UUID:
        """História causal a que o evento pertence."""


@runtime_checkable
class CausalHistoryView(Protocol):
    """Forma mínima de uma `CausalHistory`."""

    @property
    def id(self) -> uuid.UUID:
        """Identidade da história."""

    @property
    def subject_coid(self) -> uuid.UUID:
        """COID do sujeito da história."""


@runtime_checkable
class CausalEvidencePort(Protocol[EventT_co, HistoryT_co]):
    """Verifica que um evento causal pertence à história do sujeito.

    Satisfeita estruturalmente por `CausalHistoryRepository` (E3.9).

    **Somente leitura.** A E4.7 verifica evidência; nunca a cria, altera
    ou infere:

        MISSING EVIDENCE != AUTHORIZATION TO FABRICATE HISTORY
        CAUSAL EVENT ID != CAUSAL EVIDENCE UNTIL SUBJECT MEMBERSHIP IS VERIFIED
    """

    def get_event(self, event_id: uuid.UUID) -> EventT_co | None:
        """Evento causal com este id, ou `None`."""
        ...  # pragma: no cover - corpo de stub de Protocol, nunca executado

    def get_by_subject(self, subject_coid: uuid.UUID) -> HistoryT_co | None:
        """História causal deste sujeito, ou `None`.

        O par `get_event` + `get_by_subject` é o que permite confirmar
        pertencimento sem que a E4.7 leia campos do modelo da E3: basta
        comparar a identidade da história do evento com a identidade da
        história do sujeito.
        """
        ...  # pragma: no cover - corpo de stub de Protocol, nunca executado
