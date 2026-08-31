"""
`MemoryRetrievalManager` — E4.6.

Compositor **transitório** de uma vista admissível do patrimônio
cognitivo persistido:

```text
Memory(Context) = Admissible_Context(Persistent(CognitivePatrimony))
```

Compõe `MemoryDomain` (E4.1), `MemoryContext` (E4.2), Governance (E4.3),
`AccessibilityState` (E3.6) e Search (E3.8), e produz uma
`ADMISSIBLE MEMORY VIEW`.

## O que ele não é

```text
RETRIEVAL != GOVERNANCE   RETRIEVAL != SEARCH     RETRIEVAL != MEMORY
RETRIEVAL != STORAGE      RETRIEVAL != RANKING    RETRIEVAL != EXISTENCE
NOT RETRIEVED != FORGOTTEN
NO RESULT     != NEVER EXISTED
DENIED        != EMPTY RESULT
```

A E3 permanece a única fonte da verdade do patrimônio. Nada aqui pontua,
ranqueia, ordena por relevância, desduplica por equivalência, usa
embedding, vector DB, busca semântica ou textual. A ordenação canônica
da E3 (`created_at ASC, id ASC`) é **ordem**, não ranking.

Nada é privilegiado em silêncio: nem `CURRENT` sobre `SUPERSEDED`, nem
consolidação sobre suas fontes, nem objeto com CLID sobre objeto sem
CLID, nem objeto com evidência de continuidade sobre objeto sem ela.

```text
MISSING CONTINUITY EVIDENCE != RETRIEVAL INADMISSIBILITY
```

## Somente leitura

```text
DATABASE_WRITES = 0    MIGRATION_REQUIRED = NO
NEW_PERSISTENT_ENTITY = NO
```

Sem `commit()`, `flush()` ou `session.add()`. Sem cache persistente,
saved search, query history, transcript, evento causal ou registro de
aprendizado — erro de busca não é aprendizado, e resultado vazio não é
experiência validada.
"""

import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from typing import Generic, TypeVar

from app.memory.errors.exceptions import (
    RetrievalContractViolationError,
    RetrievalDuplicateCoidError,
)
from app.memory.models.governance_enums import CognitiveOperation
from app.memory.ports.retrieval import (
    CognitiveObjectView,
    CognitiveSearchPort,
    RetrievalCandidateGatePort,
)
from app.memory.repositories.memory_domain_membership_repository import (
    MemoryDomainMembershipRepository,
)
from app.memory.schemas.governance import (
    GovernanceResolution,
    resolucao_vincula_contexto,
)
from app.memory.schemas.memory_context import MemoryContext
from app.memory.schemas.retrieval import (
    DEFAULT_LIMIT,
    KNOWN_ACCESSIBILITY_TOKENS,
    KNOWN_REVISION_TOKENS,
    MAX_LIMIT,
    RETRIEVABLE_ACCESSIBILITY_TOKENS,
    MemoryRetrievalResult,
    RetrievedMemoryItem,
)
from app.memory.services.context_manager import ContextManager
from app.memory.services.governance_manager import GovernanceManager
from app.memory.services.platform_safety_boundary import CapabilityDescriptor
from app.utils.logger import get_logger

logger = get_logger("app.memory.services.retrieval_manager")

CriteriaT = TypeVar("CriteriaT")

SEARCH_BATCH_SIZE = 100
"""Tamanho do lote lido da Search da E3 a cada passagem.

A paginação da **vista** não pode ser delegada ao `limit`/`offset` da
Search: entre os candidatos brutos há objetos que os filtros contextuais
descartam, então aplicar `limit` antes de filtrar produziria páginas
incompletas, buracos entre páginas e `has_more` errado. Os lotes existem
para que os filtros incidam antes da paginação, sem materializar todo o
patrimônio de uma vez.
"""


@dataclass(frozen=True, slots=True)
class _RetrievalCandidateSnapshot:
    """Cópia **por valor** do candidato, entregue ao `candidate_gate`.

    ## Por que existe (corretivo E4.6.3.1)

    A E4.6.3 entregava ao gate a **própria instância** devolvida pela
    Search. `CognitiveObjectView` é um `Protocol` de propriedades
    somente-leitura, o que protege o código tipado comum — e **não**
    torna o objeto concreto imutável em runtime. A auditoria
    independente executou um gate que fez `object.__setattr__` no
    candidato antes de devolver `True`, e o COID fabricado saiu no
    resultado projetado.

    ```text
    BOOLEAN RETURN   != IMMUTABLE ARGUMENT
    SHARED REFERENCE != STRICTLY REDUCTIVE GATE
    ```

    Em produção o risco é maior: o candidato pode ser uma entidade ORM
    ligada à `Session`, e sujá-la alcançaria um flush posterior,
    contradizendo `DATABASE_WRITES = 0`.

    ## O que garante

    O gate recebe **isto**, nunca o hit. Um gate hostil que use
    `object.__setattr__` contra a cópia altera apenas a cópia, que morre
    ao fim da iteração.

    ```text
    GATE_RECEIVES_SNAPSHOT_NOT_SEARCH_HIT = TRUE
    PROJECTION_SOURCE = ORIGINAL_VALIDATED_HIT
    SNAPSHOT_MUTATION_EFFECT = NONE_OUTSIDE_GATE
    ```

    `frozen=True` recusa atribuição normal; `slots=True` impede que um
    colaborador acrescente atributos novos. Nenhum dos dois impede
    `object.__setattr__` — e não precisam: o **isolamento por valor** é
    a fronteira, não a imutabilidade da cópia.

    ## O que NÃO carrega

    Somente os seis valores do contrato, todos imutáveis. Sem payload,
    conteúdo, `Session`, repositório, relacionamento ORM, callback,
    objeto de contexto ou coleção mutável — qualquer um deles devolveria
    ao gate um caminho de volta à entidade real, que é exatamente o que
    este corretivo fecha.

    **Detecção posterior foi rejeitada.** Comparar impressões digitais
    depois da chamada deixaria a mutação acontecer, o estado da Session
    potencialmente sujo e a restauração ambígua.

        ISOLATION BEFORE THE CALL != DAMAGE DETECTION AFTER IT
    """

    id: uuid.UUID
    clid: uuid.UUID | None
    accessibility: str
    revision_status: str | None
    created_at: datetime
    deleted_at: datetime | None

    @staticmethod
    def de(objeto: CognitiveObjectView) -> "_RetrievalCandidateSnapshot":
        """Captura os valores do hit **já validado e admitido**."""
        return _RetrievalCandidateSnapshot(
            id=objeto.id,
            clid=objeto.clid,
            accessibility=objeto.accessibility,
            revision_status=objeto.revision_status,
            created_at=objeto.created_at,
            deleted_at=objeto.deleted_at,
        )


@dataclass(frozen=True)
class _Escopo:
    """Recorte contextual de domínios, resolvido uma única vez.

    `coids is None` significa "contexto sem domínios declarados" — que
    é diferente de "nenhum COID no escopo". Colapsar os dois faria um
    contexto sem recorte devolver vista vazia.
    """

    coids: frozenset[uuid.UUID] | None

    def admite(self, coid: uuid.UUID) -> bool:
        return self.coids is None or coid in self.coids


class MemoryRetrievalManager(Generic[CriteriaT]):
    """Produz a vista admissível para um `MemoryContext`.

    Genérico sobre os critérios de busca: o vocabulário continua sendo o
    da E3.8 (`coid`, `clid`, `accessibility`, `revision_status`,
    `trace_id`, `created_from`, `created_until`, `include_deleted`) e a
    E4.6 não o amplia nem o reimplementa. Os critérios atravessam este
    módulo **opacos**, do chamador até a porta.

    Não cria `Session` nem `UnitOfWork`, não commita, não escreve.
    """

    def __init__(
        self,
        search_port: CognitiveSearchPort[CriteriaT],
        governance_manager: GovernanceManager,
        context_manager: ContextManager,
        membership_repository: MemoryDomainMembershipRepository,
    ) -> None:
        self._search = search_port
        self._governance = governance_manager
        self._context = context_manager
        self._memberships = membership_repository

    def retrieve(
        self,
        *,
        context: MemoryContext,
        descriptor: CapabilityDescriptor,
        criteria: CriteriaT,
        policy_key: str | None = None,
        moment: datetime | None = None,
        limit: int = DEFAULT_LIMIT,
        offset: int = 0,
        candidate_gate: RetrievalCandidateGatePort | None = None,
    ) -> MemoryRetrievalResult:
        """Vista admissível do patrimônio para este contexto.

        Ordem canônica da operação:

        ```text
        1. validar argumentos e o MemoryContext
        2. exigir CognitiveOperation.READ
        3. resolver Governance pelo caminho canônico
        4. se não autorizado: resultado explícito, SEM Search
        5. escopo contextual de domínios
        6. Search em lotes determinísticos
        7. filtros de admissibilidade
        8. candidate_gate, quando fornecido (E4.6.3)
        9. paginação DEPOIS dos filtros e do gate
        10. projeção em value objects
        ```

        **Governança precede qualquer toque no patrimônio** — e também a
        leitura de memberships destinada a compor a vista. Sob recusa,
        nem a Search corre nem as memberships são carregadas: a
        quantidade de objetos, ou o fato de existirem, já seria
        informação vazada.

            POLICY ABSENCE != ADMISSION
            NOT_APPLICABLE != ADMISSIBLE
            INADMISSIBLE   != EMPTY SEARCH
            PROHIBITED     != LOCAL DENIAL

        `candidate_gate` é **por chamada e nunca armazenado** (E4.6.3):
        não vira atributo, singleton ou contexto implícito, então duas
        chamadas consecutivas ao mesmo manager podem usar gates distintos
        sem interferência. Com `None`, o comportamento é o da cadeia 67,
        byte a byte.

            GATE IS AN ARGUMENT, NOT STATE
            COMPOSITION POINT != RETENTION DECISION
        """
        self._validar_paginacao(limit=limit, offset=offset)
        self._validar_descritor(descriptor)
        self._validar_contexto(context)

        # A validação de que os `domain_ids` existem usa o contrato já
        # existente da E4.2, e pode preceder a resolução: domínio
        # desconhecido é erro do pedido, não vista vazia.
        confirmado = self._context.validate(context)
        self._verificar_fidelidade_do_contexto(context, confirmado)

        # O contexto que segue é o **do pedido**, não o devolvido pelo
        # validador. Mesmo estruturalmente igual, usar o objeto original
        # deixa claro quem é a autoridade sobre a perspectiva:
        #
        #     VALIDATOR CONFIRMS
        #     VALIDATOR DOES NOT REWRITE
        contexto = context

        resolution = self._governance.resolve(
            descriptor=descriptor,
            context=contexto,
            policy_key=policy_key,
            moment=moment,
        )
        self._verificar_fidelidade_da_resolucao(
            resolution, descriptor=descriptor, policy_key=policy_key, context=contexto
        )

        if not resolution.execution_authorized:
            logger.info(
                "memory_retrieval_denied",
                extra={
                    "outcome": str(resolution.outcome),
                    "policy_key": policy_key,
                    "domain_count": len(contexto.domain_ids),
                },
            )
            return MemoryRetrievalResult(
                context=contexto,
                governance_resolution=resolution,
                items=(),
                search_executed=False,
                limit=limit,
                offset=offset,
                has_more=None,
            )

        escopo = self._resolver_escopo(contexto)
        itens, has_more = self._coletar(
            criteria, escopo, limit=limit, offset=offset, candidate_gate=candidate_gate
        )

        logger.info(
            "memory_retrieval_executed",
            extra={
                "policy_key": policy_key,
                "domain_count": len(contexto.domain_ids),
                "item_count": len(itens),
                "has_more": has_more,
                "limit": limit,
                "offset": offset,
            },
        )

        return MemoryRetrievalResult(
            context=contexto,
            governance_resolution=resolution,
            items=itens,
            search_executed=True,
            limit=limit,
            offset=offset,
            has_more=has_more,
        )

    # --- Validação -----------------------------------------------------

    @staticmethod
    def _validar_paginacao(*, limit: int, offset: int) -> None:
        for campo, valor in (("limit", limit), ("offset", offset)):
            if not isinstance(valor, int) or isinstance(valor, bool):
                raise TypeError(f"{campo} deve ser int, recebido {type(valor).__name__}")
        if limit < 1:
            raise ValueError("limit deve ser >= 1")
        if limit > MAX_LIMIT:
            raise ValueError(f"limit não pode exceder MAX_LIMIT ({MAX_LIMIT}): {limit}")
        if offset < 0:
            raise ValueError("offset não pode ser negativo")

    @staticmethod
    def _validar_descritor(descriptor: CapabilityDescriptor) -> None:
        """Só `READ` chega ao Retrieval.

        A verificação acontece **antes** da resolução e antes da Search:
        um descritor de `TRANSFORM` ou `CONSOLIDATE` submetido aqui não é
        um pedido de leitura que a governança deva julgar, é um pedido
        endereçado ao módulo errado.

            PERMISSION TO READ != PERMISSION TO ANYTHING ELSE
        """
        if not isinstance(descriptor, CapabilityDescriptor):
            raise TypeError(
                "descriptor deve ser CapabilityDescriptor, recebido " f"{type(descriptor).__name__}"
            )
        if descriptor.operation is not CognitiveOperation.READ:
            raise ValueError(
                f"E4.6 executa apenas CognitiveOperation.READ; recebido " f"{descriptor.operation}"
            )

    @staticmethod
    def _validar_contexto(context: object) -> None:
        """O argumento público precisa ser um `MemoryContext` de fato.

        Sem esta checagem, um tipo errado só falharia lá adiante com
        `AttributeError` ao tocar `domain_ids` — diagnóstico obscuro para
        um erro trivial do chamador (corretivo E4.6.1).
        """
        if not isinstance(context, MemoryContext):
            raise TypeError(f"context deve ser MemoryContext, recebido {type(context).__name__}")

    @staticmethod
    def _verificar_fidelidade_do_contexto(solicitado: MemoryContext, confirmado: object) -> None:
        """O validador confirma a perspectiva; não a reescreve.

        `ContextManager.validate()` existe para dizer se os `domain_ids`
        declarados existem. Devolver um contexto **diferente** — outro
        ator, outro propósito, outros domínios — trocaria em silêncio a
        perspectiva que o chamador escolheu, e a vista resultante
        responderia a uma pergunta que ninguém fez.

            CONTEXT VALIDATION != CONTEXT SUBSTITUTION
            USER CONTEXT = AUTHORITATIVE REQUEST

        A comparação é a igualdade estrutural do value object da E4.2,
        que já é `frozen` e canônico.
        """
        if not isinstance(confirmado, MemoryContext):
            raise RetrievalContractViolationError(
                (
                    "ContextManager.validate devolveu "
                    f"{type(confirmado).__name__}, não MemoryContext",
                )
            )
        if confirmado != solicitado:
            raise RetrievalContractViolationError(
                (
                    "ContextManager.validate devolveu um contexto diferente do "
                    "solicitado — validação não substitui a perspectiva pedida",
                )
            )

    @staticmethod
    def _verificar_fidelidade_da_resolucao(
        resolution: object,
        *,
        descriptor: CapabilityDescriptor,
        policy_key: str | None,
        context: MemoryContext,
    ) -> None:
        """A autorização tem de ser sobre **este** pedido.

        `execution_authorized` sozinho não diz qual operação nem qual
        policy produziram a autorização — era essa a lacuna da E4.6.
        Uma resolução de `TRANSFORM`, ou de outra policy, é decisão de
        outra autoridade sobre outra pergunta:

            AUTHORIZATION TO TRANSFORM != AUTHORIZATION TO READ
            REQUESTED POLICY           != RESOLVED POLICY

        Acumula todos os motivos antes de levantar. Nada é normalizado:
        nomes de policy são comparados por igualdade exata.

        A identidade de policy só é exigida quando a resolução a carrega.
        `PROHIBITED` nunca carrega proveniência local — a fronteira
        decide antes de a policy ser consultada — e `NOT_APPLICABLE` pode
        não carregá-la quando nenhuma versão vigente existe. Exigi-la
        nesses casos recusaria recusas legítimas.
        """
        if not isinstance(resolution, GovernanceResolution):
            raise RetrievalContractViolationError(
                (
                    "GovernanceManager.resolve devolveu "
                    f"{type(resolution).__name__}, não GovernanceResolution",
                )
            )

        motivos: list[str] = []
        if resolution.operation is not CognitiveOperation.READ:
            motivos.append(
                f"a resolução é sobre {resolution.operation}, e a E4.6 executa apenas "
                "CognitiveOperation.READ"
            )
        if resolution.operation is not descriptor.operation:
            motivos.append(
                f"operação resolvida ({resolution.operation}) difere da solicitada "
                f"({descriptor.operation})"
            )
        if resolution.policy_key is not None and resolution.policy_key != policy_key:
            motivos.append(
                f"policy resolvida {resolution.policy_key!r} difere da solicitada "
                f"{policy_key!r}"
            )
        # Vínculo com o contexto avaliado (corretivo E4.3.4). Verificar
        # operação e policy não dizia SOB QUAL PERGUNTA a autorização
        # foi emitida: uma resolução produzida para outro domínio, ator
        # ou propósito era indetectável.
        #
        #     REQUESTED CONTEXT MUST EQUAL RESOLVED CONTEXT
        #
        # Vale em TODOS os outcomes, inclusive PROHIBITED e
        # NOT_APPLICABLE, e antes de memberships e Search.
        motivos.extend(
            resolucao_vincula_contexto(
                resolution,
                domain_ids=context.domain_ids,
                actor_ref=context.actor_ref,
                purpose=context.purpose,
            )
        )
        if motivos:
            raise RetrievalContractViolationError(tuple(motivos))

    # --- Escopo contextual ---------------------------------------------

    def _resolver_escopo(self, contexto: MemoryContext) -> _Escopo:
        """Recorte de domínios do contexto, como **união**.

        ```text
        MULTI_DOMAIN_CONTEXT = UNION OF DECLARED DOMAIN MEMBERSHIPS
        scope(D1, D2) = members(D1) ∪ members(D2)
        ```

        O contexto declara um conjunto de **perspectivas**, não uma
        conjunção de requisitos: exigir pertencimento simultâneo a todos
        os domínios introduziria uma interseção restritiva que o contrato
        não indica — e a governança já casa domínios por interseção, que
        é outra decisão, sobre outra coisa.

        Um COID em vários domínios declarados entra uma única vez: a
        união é de conjuntos, e membership não duplica objeto.

        Contexto sem domínios não aplica filtro algum — objeto com zero
        domínios continua existindo e aparece aqui, o que é coerente com
        `ZERO DOMAIN MEMBERSHIP != NONEXISTENCE` (E4.1).

        Limitação declarada: o escopo é materializado uma vez, com uma
        consulta por domínio declarado, e cresce com o total de membros
        desses domínios. Uma versão incremental exigiria consulta por
        candidato — troca de custo, não de semântica.
        """
        if not contexto.domain_ids:
            return _Escopo(coids=None)

        coids: set[uuid.UUID] = set()
        for domain_id in contexto.domain_ids:
            for membership in self._memberships.list_memberships_of_domain(domain_id):
                coids.add(membership.coid)
        return _Escopo(coids=frozenset(coids))

    # --- Coleta paginada ------------------------------------------------

    def _coletar(
        self,
        criteria: CriteriaT,
        escopo: _Escopo,
        *,
        limit: int,
        offset: int,
        candidate_gate: RetrievalCandidateGatePort | None = None,
    ) -> tuple[tuple[RetrievedMemoryItem, ...], bool]:
        """Lê a Search em lotes e pagina **depois** dos filtros.

        `offset` é descartado sobre itens **já admissíveis**, nunca sobre
        o conjunto bruto. Coleta `limit + 1` para derivar `has_more` sem
        precisar de contagem total — apurar o total contextual exigiria
        varrer todos os candidatos, e `has_more` basta nesta etapa.

        A ordem é a canônica da E3 e nada aqui reordena.

        O `candidate_gate` (E4.6.3) entra **depois** da validação de
        forma, da admissibilidade base e da duplicata, e **antes** do
        `offset`. A posição não é arbitrária: o gate não pode esconder
        violação de contrato nem duplicata da Search, e `offset`,
        `limit` e `has_more` precisam contar apenas o que o gate
        aprovou — senão a paginação descreveria uma página que não é a
        devolvida. Como o laço continua enquanto faltam aprovados, uma
        rejeição gera **backfill**, não buraco.
        """
        admissiveis: list[RetrievedMemoryItem] = []
        vistos: set[uuid.UUID] = set()
        descartados = 0
        posicao = 0

        while len(admissiveis) <= limit:
            bruto = self._search.search(criteria, limit=SEARCH_BATCH_SIZE, offset=posicao)
            # `CognitiveSearchPort` declara `Sequence`, e a diferença é
            # semântica, não formal: uma `Sequence` tem **ordem**, e a
            # ordem da Search da E3 é o contrato determinístico do qual a
            # paginação depende.
            #
            #     SEQUENCE != ARBITRARY ITERABLE
            #     UNORDERED COLLECTION != DETERMINISTIC SEARCH RESULT
            #
            # `str` e `bytes` são `Sequence` e continuam inválidos: são
            # sequências de caracteres, não de objetos cognitivos.
            #
            # Nada é convertido nem reordenado aqui. Fazer `list(bruto)`
            # de um generator faria a violação parecer válida, e ordenar
            # um `set` fabricaria uma ordem que a Search não produziu —
            # nos dois casos a E4.6 estaria escondendo o defeito da porta
            # em vez de reportá-lo.
            if isinstance(bruto, str | bytes) or not isinstance(bruto, Sequence):
                raise RetrievalContractViolationError(
                    (
                        f"a porta de Search devolveu {type(bruto).__name__}, que não é "
                        "uma Sequence — a ordem determinística da E3 é parte do contrato",
                    )
                )
            lote = bruto
            if not lote:
                break
            posicao += len(lote)

            for objeto in lote:
                # A forma é validada ANTES do filtro. Filtrar primeiro
                # faria um hit malformado sair como "não casou", e a
                # violação viraria ausência legítima:
                #
                #     PORT CONTRACT VIOLATION != EMPTY VIEW
                #     MALFORMED EVIDENCE      != NO MATCH
                self._validar_hit(objeto)
                if not self._admissivel(objeto, escopo):
                    continue
                if objeto.id in vistos:
                    raise RetrievalDuplicateCoidError(objeto.id)
                vistos.add(objeto.id)

                # O gate é consultado sobre um candidato que a autoridade
                # já admitiu, e só pode retirá-lo DESTA resposta:
                #
                #     GATE REDUCES A RESPONSE
                #     NOT RETURNED IN THIS RESPONSE != FORGOTTEN
                #
                # `continue` (e não `break`) porque o laço precisa seguir
                # preenchendo a página: rejeitar não pode encurtá-la.
                if candidate_gate is not None and not self._gate_aprova(candidate_gate, objeto):
                    continue

                if descartados < offset:
                    descartados += 1
                    continue

                admissiveis.append(self._projetar(objeto))
                if len(admissiveis) > limit:
                    break

            if len(lote) < SEARCH_BATCH_SIZE:
                break

        has_more = len(admissiveis) > limit
        return tuple(admissiveis[:limit]), has_more

    @staticmethod
    def _gate_aprova(
        candidate_gate: RetrievalCandidateGatePort, objeto: CognitiveObjectView
    ) -> bool:
        """Consulta o gate **fail-closed**, sobre uma cópia isolada.

        O colaborador recebe um `_RetrievalCandidateSnapshot`, nunca o
        hit da Search (corretivo E4.6.3.1):

        ```text
        GATE_RECEIVES_SNAPSHOT_NOT_SEARCH_HIT = TRUE
        ```

        Duas falhas possíveis do colaborador, e nenhuma delas pode virar
        decisão silenciosa sobre a vista:

        ```text
        INVALID GATE RESULT  != EXCLUSION
        INVALID GATE RESULT  != INCLUSION
        COLLABORATOR FAILURE != EMPTY VIEW
        ```

        **Tipo exato.** `type(...) is bool` e não `isinstance`, porque
        `bool` é subclasse de `int` e `isinstance(1, int)` não separaria
        `True` de `1`. Coagir com `bool(...)` seria pior ainda: um gate
        que devolvesse `None` por engano excluiria tudo, e a vista
        vazia pareceria legítima.

        **Exceção.** Propagar a exceção crua faria uma falha do
        colaborador atravessar a fronteira sem código PIA; engoli-la
        faria o objeto entrar ou sair sem que ninguém decidisse. A causa
        é preservada em `__cause__`.

        **O diagnóstico cita o COID do hit ORIGINAL**, lido antes da
        chamada. Ler o `id` da cópia depois exibiria um identificador
        que o próprio colaborador pode ter fabricado.

            ERROR IDENTITY = ORIGINAL COID, NEVER THE COPY'S
        """
        coid_original = objeto.id
        snapshot = _RetrievalCandidateSnapshot.de(objeto)
        try:
            resultado = candidate_gate.allows(snapshot)
        except Exception as exc:
            raise RetrievalContractViolationError(
                (
                    f"o candidate_gate levantou {type(exc).__name__} ao avaliar o "
                    f"candidato {coid_original} — falha de colaborador não é decisão "
                    "sobre a vista",
                )
            ) from exc
        if type(resultado) is not bool:
            raise RetrievalContractViolationError(
                (
                    f"o candidate_gate devolveu {type(resultado).__name__} ao avaliar "
                    f"o candidato {coid_original}; o contrato exige bool exato — valor "
                    "truthy/falsy não é resposta",
                )
            )
        return resultado

    @staticmethod
    def _validar_hit(objeto: CognitiveObjectView) -> None:
        """Confere que o candidato satisfaz o contrato da porta.

        ```text
        id              = uuid.UUID
        clid            = uuid.UUID | None
        accessibility   = str, no vocabulário da E3
        revision_status = str | None, no vocabulário da E3
        created_at      = datetime
        deleted_at      = datetime | None
        ```

        Token desconhecido é **violação**, não objeto a excluir: excluí-lo
        em silêncio esconderia que a E3 mudou o vocabulário sob os pés da
        E4.6, e a vista continuaria parecendo correta.

        Nada é normalizado — sem `lower()`, `upper()`, `casefold()` ou
        coerção. Mesma disciplina congelada na E4.5.1 para `qualifier`.

        **Acesso tipado direto, sem reflexão** (corretivo E4.6.2). A
        versão anterior usava `hasattr`/`getattr`, contrariando o
        contrato que a própria porta declara — documentação e código
        executável se contradiziam. Os campos são lidos pelo nome, como
        `CognitiveObjectView` os declara, e um objeto que não os ofereça
        levanta `AttributeError`, convertido aqui em diagnóstico
        explícito.

        Custo declarado da mudança: `AttributeError` interrompe na
        **primeira** ausência, então um hit sem vários campos reporta um
        motivo, não todos. Mantê-los todos exigiria a reflexão que o
        contrato proíbe; entre reportar menos e violar o contrato,
        reporta-se menos.
        """
        try:
            identidade = objeto.id
            continuidade = objeto.clid
            acessibilidade = objeto.accessibility
            revisao = objeto.revision_status
            criado_em = objeto.created_at
            apagado_em = objeto.deleted_at
        except AttributeError as exc:
            raise RetrievalContractViolationError(
                (f"hit não satisfaz CognitiveObjectView: {exc}",)
            ) from exc

        motivos: list[str] = []

        if not isinstance(identidade, uuid.UUID):
            motivos.append(f"id deve ser uuid.UUID, recebido {type(identidade).__name__}")
        if continuidade is not None and not isinstance(continuidade, uuid.UUID):
            motivos.append(
                f"clid deve ser uuid.UUID ou None, recebido {type(continuidade).__name__}"
            )

        if not isinstance(acessibilidade, str):
            motivos.append(f"accessibility deve ser str, recebido {type(acessibilidade).__name__}")
        elif acessibilidade not in KNOWN_ACCESSIBILITY_TOKENS:
            motivos.append(
                f"accessibility {acessibilidade!r} não pertence ao vocabulário da E3 "
                f"{sorted(KNOWN_ACCESSIBILITY_TOKENS)}"
            )

        if revisao is not None:
            if not isinstance(revisao, str):
                motivos.append(
                    f"revision_status deve ser str ou None, recebido {type(revisao).__name__}"
                )
            elif revisao not in KNOWN_REVISION_TOKENS:
                motivos.append(
                    f"revision_status {revisao!r} não pertence ao vocabulário da E3 "
                    f"{sorted(KNOWN_REVISION_TOKENS)}"
                )

        if not isinstance(criado_em, datetime):
            motivos.append(f"created_at deve ser datetime, recebido {type(criado_em).__name__}")
        if apagado_em is not None and not isinstance(apagado_em, datetime):
            motivos.append(
                f"deleted_at deve ser datetime ou None, recebido {type(apagado_em).__name__}"
            )

        if motivos:
            raise RetrievalContractViolationError(tuple(motivos))

    @staticmethod
    def _admissivel(objeto: CognitiveObjectView, escopo: _Escopo) -> bool:
        """Filtros da vista admissível, na ordem congelada.

        1. **soft-deleted fora**, sempre. O filtro é defensivo: mesmo que
           um critério traga `include_deleted=True`, auditoria histórica
           pertence aos caminhos próprios da E3/E4.4, não a esta vista.
        2. **`ACTIVE`/`LATENT`**, seguindo o contrato de
           `assert_accessible()` da E3. `INACCESSIBLE` e
           `CAUSALLY_EXTINCT` permanecem íntegros no banco e apenas não
           são apresentados.
        3. **recorte de domínio**, quando o contexto declarou algum.

        Nada aqui transiciona estado, reativa objeto ou infere extinção —
        isso é E4.7, que a E4.6 não antecipa e da qual não depende.
        """
        if objeto.deleted_at is not None:
            return False
        if objeto.accessibility not in RETRIEVABLE_ACCESSIBILITY_TOKENS:
            return False
        return escopo.admite(objeto.id)

    @staticmethod
    def _projetar(objeto: CognitiveObjectView) -> RetrievedMemoryItem:
        """Projeta fatos já existentes. Nenhuma instância ORM escapa.

        `str(...)` sobre os tokens de enum devolve o valor estável que a
        E3 persiste, sem importar o enum — `AccessibilityState` e
        `RevisionStatus` são `StrEnum`.
        """
        return RetrievedMemoryItem(
            coid=objeto.id,
            clid=objeto.clid,
            accessibility=str(objeto.accessibility),
            revision_status=None if objeto.revision_status is None else str(objeto.revision_status),
            created_at=objeto.created_at,
        )


__all__ = [
    "DEFAULT_LIMIT",
    "MAX_LIMIT",
    "SEARCH_BATCH_SIZE",
    "CognitiveOperation",
    "GovernanceResolution",
    "MemoryRetrievalManager",
    "RetrievalCandidateGatePort",
]
