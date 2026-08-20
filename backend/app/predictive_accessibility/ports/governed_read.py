"""
Porta de leitura governada da E4, vista pela E5 (`E5.a`).

```text
E5_CONSUMES_E4_ACCESSIBLE_CONTEXT_READ_ONLY = TRUE
E5_MEMORY_WRITER = FORBIDDEN
PIAP_WRITES_E4_STATE = FALSE
```

## Estrutural, não nominal

Precedente medido: `app/memory/ports/retrieval.py`. A porta declara
apenas a **forma** de que a E5 precisa, e é satisfeita pelo
`MemoryRetrievalManager` real sem que este saiba da sua existência. A
produção da E5 não importa `app.memory` nem `app.cognitive`.

```text
COUPLING_BY_SHAPE != NOMINAL_IMPORT
```

## O que esta porta NÃO faz

Não constrói descritor da E4, não resolve governança e não reimplementa a
verificação de `CognitiveOperation.READ`. Essa verificação pertence ao
`MemoryRetrievalManager`, que já a faz no descritor **e** na resolução;
reimplementá-la aqui criaria uma segunda fonte de verdade sobre a mesma
regra.

```text
E5_A_DECLARA_A_PORTA
E5_A_NAO_REIMPLEMENTA_A_GOVERNANCA_DA_E4
NO_OBJECT_IS_WRITTEN_BY_BOTH_LAYERS = TRUE
```

O teste de integração desta etapa prova, contra o manager real, que
`READ` admite o caminho governado e que qualquer outra operação é
rejeitada antes da Search.
"""

from typing import Protocol, TypeVar, runtime_checkable


@runtime_checkable
class RetrievalResultView(Protocol):
    """Forma mínima do resultado de uma leitura governada.

    Somente leitura por construção: todos os membros são propriedades, e
    a E5 não tem nada que escrever num resultado da E4.

    `search_executed` é o membro que importa mais, e por isso está aqui:
    recusa e resultado vazio são coisas diferentes, e a E4.6 fixou essa
    distinção deliberadamente.

    ```text
    DENIED != EMPTY_RESULT
    ```

    Deliberadamente **não** declara contagem: registrar quantos itens uma
    recusa encontrou afirmaria que a busca ocorreu.
    """

    @property
    def search_executed(self) -> bool:
        """`False` quando a governança não autorizou — a busca não correu."""

    @property
    def has_more(self) -> bool | None:
        """`None` numa recusa: não há \"mais nada\" a afirmar sobre o que não correu."""


ContextT_contra = TypeVar("ContextT_contra", contravariant=True)
"""Contexto de memória da E4, tratado como **opaco** pela E5."""

DescriptorT_contra = TypeVar("DescriptorT_contra", contravariant=True)
"""Descritor de capacidade da E4, tratado como **opaco** pela E5.

Contravariante porque a porta apenas o repassa. A E5.a não o constrói:
quem chama traz o descritor já formado, e a E4 o julga.
"""

CriteriaT_contra = TypeVar("CriteriaT_contra", contravariant=True)
"""Critérios de busca da E3.8, atravessando sem serem inspecionados."""

ResultT_co = TypeVar("ResultT_co", bound=RetrievalResultView, covariant=True)
"""Resultado, covariante: um resultado mais específico serve onde se espera um mais geral."""


@runtime_checkable
class GovernedReadPort(Protocol[ContextT_contra, DescriptorT_contra, CriteriaT_contra, ResultT_co]):
    """Leitura governada do patrimônio, somente leitura.

    A assinatura cobre o subconjunto chamável de
    `MemoryRetrievalManager.retrieve`. Os parâmetros opcionais do manager
    — política, instante, paginação e portão de candidatos — não entram
    aqui: a porta declara o mínimo de que a E5 precisa, e um implementador
    pode oferecer mais.

    Todos os parâmetros são keyword-only, como no manager real.
    """

    def retrieve(
        self,
        *,
        context: ContextT_contra,
        descriptor: DescriptorT_contra,
        criteria: CriteriaT_contra,
    ) -> ResultT_co:
        """Vista admissível do patrimônio para este contexto, ou a recusa."""
