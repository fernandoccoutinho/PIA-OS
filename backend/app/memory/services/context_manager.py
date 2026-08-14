"""
`ContextManager` — construção e validação de perspectivas (E4.2).

O que este serviço faz: constrói `MemoryContext` canônico, valida que
os domínios referenciados existem, e deriva variantes explícitas.

O que ele **não** faz, e a lista importa tanto quanto a anterior:

```
CONTEXT DESCRIBES
GOVERNANCE DECIDES ADMISSIBILITY
```

- não decide `allow`/`deny`/`can`/`authorize` — Governança é E4.3;
- não executa busca, `top_k`, ranking ou recuperação — Retrieval é
  E4.6;
- não avalia nem transiciona `AccessibilityState` — E4.7;
- não infere persistência (E4.4) nem relevância;
- não cria membership, `ProvenanceRecord` ou `CausalHistoryEvent`;
- não calcula score de espécie alguma.

A ausência dessas capacidades é verificada por teste (CT18, CT19,
CT20), não apenas declarada aqui.

**Zero escritas.** Construir contexto é puro; validar referências é
leitura. Nenhum caminho deste módulo emite `INSERT`, `UPDATE`,
`DELETE` ou `TRUNCATE`, e isso é provado por censo mais listener de
cursor (`DB1`), a mesma técnica de `SX3` (E3.8) e `IA2` (E3.10).
"""

import uuid
from collections.abc import Iterable

from app.memory.errors.exceptions import ContextUnknownDomainReferenceError
from app.memory.repositories.memory_domain_repository import MemoryDomainRepository
from app.memory.schemas.memory_context import MemoryContext


class ContextManager:
    """Construção, validação e derivação de `MemoryContext`.

    O repositório é opcional de propósito: `MemoryContext` é um objeto
    de valor e é construtível **sem banco algum** (`build`). Só a
    validação de referências precisa ler, e quem não a quiser não
    paga por ela.
    """

    def __init__(self, domain_repository: MemoryDomainRepository | None = None) -> None:
        self._domains = domain_repository

    def build(
        self,
        *,
        domain_ids: Iterable[uuid.UUID] | None = None,
        session_id: str | None = None,
        actor_ref: str | None = None,
        purpose: str | None = None,
    ) -> MemoryContext:
        """Constrói um contexto canônico, **sem** acesso ao banco.

        Determinístico: a mesma entrada produz um contexto
        estruturalmente igual, e a ordem dos `domain_ids` não importa.
        """
        return MemoryContext.build(
            domain_ids=domain_ids,
            session_id=session_id,
            actor_ref=actor_ref,
            purpose=purpose,
        )

    def build_validated(
        self,
        *,
        domain_ids: Iterable[uuid.UUID] | None = None,
        session_id: str | None = None,
        actor_ref: str | None = None,
        purpose: str | None = None,
    ) -> MemoryContext:
        """Constrói e valida as referências de domínio numa só chamada.

        Conveniência sobre `build` + `validate`, sem semântica nova.
        """
        contexto = self.build(
            domain_ids=domain_ids,
            session_id=session_id,
            actor_ref=actor_ref,
            purpose=purpose,
        )
        self.validate(contexto)
        return contexto

    def validate(self, context: MemoryContext) -> MemoryContext:
        """Confirma que todo domínio declarado existe.

        Levanta `ContextUnknownDomainReferenceError` (`PIA-8026`) com o
        **conjunto** de ids desconhecidos — reportar um por vez faria o
        chamador descobrir N referências ruins em N tentativas.

        Duas coisas que esta validação deliberadamente **não** faz:

        - não copia nenhum dado do domínio para dentro do contexto; a
          referência continua sendo uma referência, e `MemoryDomain`
          continua sendo fonte da verdade sobre si mesmo;
        - não conclui nada sobre patrimônio. Um domínio ausente é um
          domínio ausente:

              missing domain != cognitive patrimony missing

        Devolve o próprio contexto para permitir encadeamento. Nada é
        alterado — o objeto é imutável.
        """
        if not context.domain_ids:
            return context
        if self._domains is None:
            raise ValueError(
                "validate() exige um MemoryDomainRepository — construa o "
                "ContextManager com um, ou use build() sem validação"
            )

        desconhecidos = [
            domain_id
            for domain_id in context.domain_ids
            if not self._domains.exists_domain(domain_id)
        ]
        if desconhecidos:
            raise ContextUnknownDomainReferenceError(desconhecidos)
        return context

    def derive(
        self,
        context: MemoryContext,
        *,
        domain_ids: Iterable[uuid.UUID] | None = None,
        session_id: str | None = None,
        actor_ref: str | None = None,
        purpose: str | None = None,
    ) -> MemoryContext:
        """Deriva uma variante explícita; o contexto base fica intacto.

        Perspectiva nova é objeto novo. Nenhuma mutação silenciosa —
        é o que permite auditar depois sob qual perspectiva cada
        decisão foi tomada.
        """
        return context.derive(
            domain_ids=domain_ids,
            session_id=session_id,
            actor_ref=actor_ref,
            purpose=purpose,
        )

    @staticmethod
    def equivalent(first: MemoryContext, second: MemoryContext) -> bool:
        """Comparação **estrutural** entre dois contextos.

        Delega à igualdade do `frozen dataclass`. Como `build()`
        canonicaliza `domain_ids`, dois contextos que diferem apenas
        na ordem em que os domínios foram informados são equivalentes
        — e devem ser, porque ordem de digitação não é semântica.
        """
        return first == second
