"""
Contratos transitórios do isolamento cognitivo (`E4.8`).

```text
ISOLATION = NON-EXPANSION OF AN EXPLICIT CONTEXTUAL DOMAIN SCOPE

ISOLATION DOES NOT GRANT AUTHORITY
ISOLATION DOES NOT CREATE EXISTENCE
ISOLATION DOES NOT CHANGE PERSISTENCE
ISOLATION DOES NOT CHANGE ACCESSIBILITY
ISOLATION DOES NOT CHANGE RELEVANCE
ISOLATION DOES NOT REWRITE PATRIMONY
```

Dois value objects, deliberadamente separados:

- `DomainIsolationDecision` — a autoridade resolvida para **um**
  domínio declarado;
- `MemoryIsolationResult` — o desfecho do pedido inteiro.

Fundi-los faria um único objeto afirmar ao mesmo tempo "este domínio foi
autorizado" e "o pedido foi executado", que são fatos de origens
diferentes e que precisam poder divergir para serem verificáveis.

Invariantes vivem em `__post_init__`, não em docstring — sétima vez que
o projeto aplica a lição (E4.2.1, E4.3.2, E4.4.1, E3.4.2.1, E4.5.1,
E4.6.1, E4.7.1):

```text
frozen=True ALONE != DEEP IMMUTABILITY
```
"""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime

from app.memory.models.governance_enums import CognitiveOperation, GovernanceOutcome
from app.memory.schemas.governance import GovernanceResolution
from app.memory.schemas.memory_context import MemoryContext
from app.memory.schemas.retrieval import MemoryRetrievalResult


@dataclass(frozen=True)
class DomainIsolationDecision:
    """Autoridade resolvida para **um** domínio declarado.

    Uma decisão por domínio, e cada uma carrega a resolução íntegra —
    sem reclassificação. A E4.8 não reinterpreta o desfecho da
    governança: ela o transporta e decide, a partir do conjunto, se o
    pedido inteiro prossegue.

        FULL-CONTEXT INTERSECTION MATCH
        != AUTHORITY OVER EVERY DOMAIN IN THE UNION
    """

    domain_id: uuid.UUID
    resolution: GovernanceResolution

    def __post_init__(self) -> None:
        if not isinstance(self.domain_id, uuid.UUID):
            raise TypeError(
                f"domain_id deve ser uuid.UUID, recebido {type(self.domain_id).__name__}"
            )
        if not isinstance(self.resolution, GovernanceResolution):
            raise TypeError(
                "resolution deve ser GovernanceResolution, recebido "
                f"{type(self.resolution).__name__}"
            )
        if self.resolution.operation is not CognitiveOperation.READ:
            raise ValueError(
                f"a resolução é sobre {self.resolution.operation}; o isolamento da "
                "E4.8 é caminho de leitura e usa CognitiveOperation.READ"
            )
        # A resolução tem de ter sido emitida para o SINGLETON deste
        # domínio — não para o conjunto declarado, não para outro
        # domínio. É o que a E4.3.4 tornou verificável.
        #
        #     EXPLICIT MULTI-DOMAIN ISOLATED SCOPE
        #     = EVERY DECLARED DOMAIN INDIVIDUALLY AUTHORIZED
        if self.resolution.context_domain_ids != (self.domain_id,):
            raise ValueError(
                f"a decisão é sobre o domínio {self.domain_id}, mas a resolução foi "
                f"emitida para {[str(d) for d in self.resolution.context_domain_ids]} — "
                "uma regra que casou o conjunto não autoriza cada domínio "
                "individualmente"
            )

    @property
    def authorized(self) -> bool:
        """Somente autorização de execução autoriza.

        Derivado, nunca armazenado em paralelo: uma cópia poderia
        divergir da resolução, e a autoridade é a resolução.

            NOT_APPLICABLE DOES NOT AUTHORIZE
            INADMISSIBLE != NONEXISTENT
            PROHIBITED IS NOT OVERRIDABLE
        """
        return self.resolution.execution_authorized

    @property
    def outcome(self) -> GovernanceOutcome:
        """Desfecho da governança, sem reclassificação."""
        return self.resolution.outcome


@dataclass(frozen=True)
class MemoryIsolationResult:
    """Desfecho de um pedido de recuperação isolada.

    Preserva o contexto **original** — a união explícita que o usuário
    declarou — e uma decisão por domínio, em ordem canônica.

    ```text
    todos os domínios autorizados  → retrieval presente
    algum domínio não autorizado   → retrieval None, recusa atômica
    ```

    Recusa e vista autorizada vazia **não colapsam**: a primeira tem
    `retrieval is None`, a segunda tem um `MemoryRetrievalResult` sem
    itens. Nenhum campo expõe contagem total, snapshot de memberships ou
    evidência de existência sob recusa.

        NOT_RETRIEVED != FORGOTTEN
        INACCESSIBLE  != NONEXISTENT
    """

    context: MemoryContext
    decisions: tuple[DomainIsolationDecision, ...]
    evaluated_at: datetime
    retrieval: MemoryRetrievalResult | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.context, MemoryContext):
            raise TypeError(
                f"context deve ser MemoryContext, recebido {type(self.context).__name__}"
            )
        if not self.context.domain_ids:
            raise ValueError(
                "o isolamento exige escopo explícito: um contexto sem domínio não é "
                "'todos os domínios isolados'"
            )
        if not isinstance(self.evaluated_at, datetime):
            raise TypeError(
                f"evaluated_at deve ser datetime, recebido {type(self.evaluated_at).__name__}"
            )
        if self.evaluated_at.tzinfo is None:
            raise ValueError(
                "evaluated_at deve ser timezone-aware — um instante ingênuo tornaria a "
                "vigência dependente do fuso da máquina"
            )

        if isinstance(self.decisions, str | bytes) or not isinstance(self.decisions, Iterable):
            raise TypeError(
                "decisions deve ser uma coleção de DomainIsolationDecision, recebido "
                f"{type(self.decisions).__name__}"
            )
        decisoes = tuple(self.decisions)
        for item in decisoes:
            if not isinstance(item, DomainIsolationDecision):
                raise TypeError(
                    "decisions aceita apenas DomainIsolationDecision, recebido "
                    f"{type(item).__name__}"
                )
        # Congelada defensivamente: `frozen` protege a referência, não o
        # conteúdo — a lição que a E4.2.1 abriu e que se repetiu até a
        # E4.7.1.
        object.__setattr__(self, "decisions", decisoes)

        declarados = self.context.domain_ids
        decididos = tuple(d.domain_id for d in decisoes)
        if len(set(decididos)) != len(decididos):
            raise ValueError(
                "há mais de uma decisão para o mesmo domínio; duas respostas para a "
                "mesma pergunta tornam a autoridade ambígua"
            )
        if decididos != tuple(sorted(declarados)):
            raise ValueError(
                f"as decisões cobrem {[str(d) for d in decididos]}, mas o contexto "
                f"declara {[str(d) for d in sorted(declarados)]} — uma decisão por "
                "domínio declarado, em ordem canônica, sem faltas nem extras"
            )

        if self.retrieval is not None and not isinstance(self.retrieval, MemoryRetrievalResult):
            raise TypeError(
                "retrieval deve ser MemoryRetrievalResult ou None, recebido "
                f"{type(self.retrieval).__name__}"
            )

        todos_autorizados = all(d.authorized for d in decisoes)
        if not todos_autorizados:
            # Recusa atômica: o pedido multidomínio não é executado
            # parcialmente, e o contexto não é estreitado em silêncio.
            #
            #     PARTIAL AUTHORITY != AUTHORITY TO REWRITE REQUESTED SCOPE
            if self.retrieval is not None:
                raise ValueError(
                    "algum domínio declarado não foi autorizado; executar a Retrieval "
                    "responderia a uma pergunta diferente da que foi feita"
                )
            return

        if self.retrieval is None:
            raise ValueError(
                "todos os domínios foram autorizados, então a Retrieval foi executada; "
                "um resultado ausente aqui afirmaria autoridade sem efeito"
            )
        # A vista tem de ser sobre o contexto ORIGINAL, com a paginação
        # solicitada — não sobre um contexto reescrito.
        #
        #     VALIDATION CONFIRMS
        #     ISOLATION DOES NOT REWRITE USER CONTEXT
        if self.retrieval.context != self.context:
            raise ValueError(
                "o resultado da Retrieval cita um contexto diferente do solicitado; o "
                "isolamento não reescreve a perspectiva do usuário"
            )
        if not self.retrieval.search_executed:
            raise ValueError(
                "com todos os domínios autorizados a Retrieval executa; uma vista não "
                "executada descreveria uma recusa que não houve"
            )

    @property
    def authorized(self) -> bool:
        """Todos os domínios declarados foram individualmente
        autorizados?"""
        return all(d.authorized for d in self.decisions)

    @property
    def refused_domain_ids(self) -> tuple[uuid.UUID, ...]:
        """Domínios cuja autoridade não foi concedida.

        Informa **quais domínios do próprio pedido** não foram
        autorizados — o usuário os declarou, então não há revelação de
        patrimônio alheio aqui. Nenhuma contagem, membership ou
        evidência de existência é exposta.
        """
        return tuple(d.domain_id for d in self.decisions if not d.authorized)
