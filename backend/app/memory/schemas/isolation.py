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
from app.memory.schemas.governance import (
    GovernanceResolution,
    resolucao_vincula_contexto,
)
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


def _identidade_local(
    resolution: GovernanceResolution,
) -> tuple[str, int, uuid.UUID] | None:
    """Identidade **exata** da policy local que fundamentou a resolução.

        (policy_key, policy_version, policy_id)

    `None` quando a policy local não foi consultada — `PROHIBITED` e
    `NOT_APPLICABLE` por ausência de versão vigente. Os três campos são
    tudo-ou-nada pelos invariantes congelados da E4.3.2, então basta
    testar um para saber se há proveniência.

    `matched_rule_id` **não** entra: regras diferentes podem casar em
    domínios diferentes da mesma versão de policy, e usá-lo como
    identidade recusaria composições legítimas.

        SAME POLICY KEY != SAME POLICY VERSION
        MATCHED RULE != POLICY IDENTITY
    """
    chave = resolution.policy_key
    versao = resolution.policy_version
    identificador = resolution.policy_id
    if chave is None or versao is None or identificador is None:
        return None
    return (chave, versao, identificador)


def verificar_coerencia_resultado_isolado(
    *,
    context: MemoryContext,
    decisions: tuple["DomainIsolationDecision", ...],
    retrieval: MemoryRetrievalResult | None,
    apenas_decisoes: bool = False,
) -> tuple[str, ...]:
    """Motivos pelos quais o desfecho isolado **não** é coerente.

    Tupla vazia significa coerência confirmada.

    Implementação **única** (corretivo E4.8.1), usada por
    `MemoryIsolationResult.__post_init__` — que a converte em
    `ValueError` — e pelo `MemoryIsolationManager`, que a converte em
    `PIA-8040` antes de construir o value object. Duas cópias da mesma
    regra divergem com o tempo: E4.5.1, E4.6.1 e E4.7.2 já pagaram por
    isso.

    A E4.8 provava escopo e não provava autoridade:

        SCOPE NON-EXPANSION WITHOUT AUTHORITY FIDELITY = INCOMPLETE ISOLATION
        SAME DOMAIN != SAME CONTEXT
        DOMAIN BINDING ALONE != CONTEXT BINDING
        ONE REQUEST != MULTIPLE AUTHORITY PROVENANCES

    `apenas_decisoes=True` verifica **só** o que depende das decisões,
    para que o manager possa recusar identidades divergentes **antes**
    de ler memberships — patrimônio não se toca sob autoridade
    incoerente. Nesse modo a ausência de `retrieval` não é motivo,
    porque a Retrieval ainda não foi executada.
    """
    motivos: list[str] = []

    # 1. Cada decisão foi emitida para o singleton daquele domínio E
    #    para o ator e o propósito do contexto ORIGINAL. A E4.3.4 tornou
    #    isso verificável; aqui se usa a MESMA função, não uma cópia.
    for decisao in decisions:
        divergencias = resolucao_vincula_contexto(
            decisao.resolution,
            domain_ids=(decisao.domain_id,),
            actor_ref=context.actor_ref,
            purpose=context.purpose,
        )
        motivos.extend(
            f"decisão do domínio {decisao.domain_id}: {motivo}" for motivo in divergencias
        )

    # 2. Um pedido, uma autoridade local. Decisoes que carregam
    #    proveniência local têm de citar a MESMA identidade — mesmo
    #    `policy_key` e mesmo `moment` não bastam se as versões diferem.
    identidades = {
        ident for ident in (_identidade_local(d.resolution) for d in decisions) if ident is not None
    }
    if len(identidades) > 1:
        legiveis = sorted(f"{k}@v{v}/{i}" for k, v, i in identidades)
        motivos.append(
            "as decisões citam identidades de policy local diferentes "
            f"({', '.join(legiveis)}); um pedido é avaliado sob uma autoridade"
        )

    if apenas_decisoes:
        return tuple(motivos)

    if not all(d.authorized for d in decisions):
        # Recusa atômica: o pedido multidomínio não é executado
        # parcialmente, e o contexto não é estreitado em silêncio.
        #
        #     PARTIAL AUTHORITY != AUTHORITY TO REWRITE REQUESTED SCOPE
        if retrieval is not None:
            motivos.append(
                "algum domínio declarado não foi autorizado; executar a Retrieval "
                "responderia a uma pergunta diferente da que foi feita"
            )
        return tuple(motivos)

    if retrieval is None:
        motivos.append(
            "todos os domínios foram autorizados, então a Retrieval foi executada; "
            "um resultado ausente aqui afirmaria autoridade sem efeito"
        )
        return tuple(motivos)

    # 3. A vista é sobre o contexto ORIGINAL, executada e autorizada.
    #
    #     VALIDATION CONFIRMS
    #     ISOLATION DOES NOT REWRITE USER CONTEXT
    if retrieval.context != context:
        motivos.append(
            "o resultado da Retrieval cita um contexto diferente do solicitado; o "
            "isolamento não reescreve a perspectiva do usuário"
        )
    if not retrieval.search_executed:
        motivos.append(
            "com todos os domínios autorizados a Retrieval executa; uma vista não "
            "executada descreveria uma recusa que não houve"
        )
    if not retrieval.governance_resolution.execution_authorized:
        motivos.append(
            "a Retrieval devolveu uma resolução que não autoriza execução, embora "
            "todas as decisões de domínio tenham autorizado"
        )

    # 4. A autoridade que a Retrieval declara é a MESMA das decisões.
    identidade_retrieval = _identidade_local(retrieval.governance_resolution)
    if identidades:
        esperada = next(iter(identidades))
        if identidade_retrieval is None:
            motivos.append(
                "a Retrieval não cita proveniência local, mas as decisões foram "
                f"fundamentadas em {esperada[0]}@v{esperada[1]}"
            )
        elif identidade_retrieval != esperada:
            motivos.append(
                "a Retrieval foi autorizada por "
                f"{identidade_retrieval[0]}@v{identidade_retrieval[1]}/"
                f"{identidade_retrieval[2]}, e as decisões por "
                f"{esperada[0]}@v{esperada[1]}/{esperada[2]}"
            )

    return tuple(motivos)


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

        motivos = verificar_coerencia_resultado_isolado(
            context=self.context, decisions=decisoes, retrieval=self.retrieval
        )
        if motivos:
            raise ValueError("; ".join(motivos))

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
