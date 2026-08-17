"""
`MemoryIsolationManager` — E4.8.

Impede que uma operação executada sob escopo explícito obtenha
patrimônio de outro escopo apenas porque o PIA-OS possui ambos.

```text
AN AGENT WORKING IN DOMAIN A
DOES NOT AUTOMATICALLY GAIN ACCESS TO DOMAIN B
MERELY BECAUSE PIA-OS POSSESSES BOTH
```

## O vazamento que este módulo fecha

Duas semânticas corretas isoladamente produzem uma lacuna quando
combinadas:

1. `GovernanceRule.matches()` casa domínios por **interseção**;
2. a E4.6 interpreta contexto multidomínio como **união** das
   memberships.

Logo, uma policy que admite `READ` apenas em `D1` casa o contexto
`{D1, D2}` — e a vista inclui patrimônio exclusivo de `D2`. Reproduzido
contra o banco real antes de escrever este módulo.

```text
FULL-CONTEXT INTERSECTION MATCH != AUTHORITY OVER EVERY DOMAIN IN THE UNION
```

A E4.8 fecha isso **sem** alterar a semântica geral da E4.3 e **sem**
reimplementar a E4.6.

## Caminho canônico

```text
1. validar o pedido; escopo vazio → PIA-8039, antes de tudo
2. ContextManager.validate + fidelidade pedido↔contexto
3. instante único
4. resolver READ para cada domínio SINGLETON, verificando o vínculo
5. se algum não autoriza: recusa ATÔMICA, sem memberships e sem Retrieval
6. snapshot da união das memberships AUTORIZADAS
7. UMA chamada à E4.6, com o contexto ORIGINAL
8. pós-condição: coids devolvidos ⊆ snapshot
9. resultado imutável
```

## Fronteiras

Não cria `Session` nem `UnitOfWork`, não commita, não escreve. Não chama
`SearchEngine` diretamente, não recompõe paginação, não reimplementa
filtros de acessibilidade nem projeção. Não cria evento causal por
leitura, não pontua, não ranqueia, não aprende.

```text
ISOLATION_PERSISTENCE = TRANSIENT
DATABASE_WRITES = 0
ISOLATION DOES NOT GRANT AUTHORITY
ISOLATION DOES NOT CREATE EXISTENCE
```

Sem estado mutável de instância: cada chamada carrega o seu próprio
escopo.

```text
PARALLEL WORKLOADS MUST NOT SHARE MUTABLE ISOLATION STATE
```
"""

import uuid
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Generic

from app.memory.errors.exceptions import (
    IsolationContractViolationError,
    IsolationScopeRequiredError,
)
from app.memory.models.governance_enums import CognitiveOperation
from app.memory.ports.isolation import (
    ContextValidationPort,
    CriteriaT_contra,
    DomainMembershipPort,
    GovernanceResolutionPort,
    IsolatedRetrievalPort,
    MembershipView,
)
from app.memory.schemas.governance import GovernanceResolution, resolucao_vincula_contexto
from app.memory.schemas.isolation import DomainIsolationDecision, MemoryIsolationResult
from app.memory.schemas.memory_context import MemoryContext
from app.memory.schemas.retrieval import DEFAULT_LIMIT, MemoryRetrievalResult
from app.memory.services.platform_safety_boundary import CapabilityDescriptor
from app.utils.logger import get_logger

logger = get_logger("app.memory.services.memory_isolation_manager")


class MemoryIsolationManager(Generic[CriteriaT_contra]):
    """Compositor transitório de recuperação isolada por domínio."""

    def __init__(
        self,
        retrieval_port: IsolatedRetrievalPort[CriteriaT_contra],
        governance_port: GovernanceResolutionPort,
        context_port: ContextValidationPort,
        membership_port: DomainMembershipPort[object],
    ) -> None:
        self._retrieval = retrieval_port
        self._governance = governance_port
        self._context = context_port
        self._memberships = membership_port

    def retrieve_isolated(
        self,
        *,
        context: MemoryContext,
        descriptor: CapabilityDescriptor,
        criteria: CriteriaT_contra,
        policy_key: str | None = None,
        moment: datetime | None = None,
        limit: int = DEFAULT_LIMIT,
        offset: int = 0,
    ) -> MemoryIsolationResult:
        """Recupera patrimônio sob escopo de domínio explícito e isolado.

        A regra que este método impõe:

            EXPLICIT MULTI-DOMAIN ISOLATED SCOPE
            = EVERY DECLARED DOMAIN INDIVIDUALLY AUTHORIZED

        Não aceita "uma regra casou algum domínio" como autorização do
        conjunto inteiro.
        """
        self._validar_argumentos(
            context=context,
            descriptor=descriptor,
            policy_key=policy_key,
            limit=limit,
            offset=offset,
        )

        confirmado = self._context.validate(context)
        self._verificar_fidelidade_do_contexto(context, confirmado)

        # Um instante para a operação inteira: uma mudança de versão de
        # policy entre resoluções produziria escopo composto por
        # autoridades de instantes diferentes.
        #
        #     ONE OPERATION = ONE EVALUATION INSTANT
        instante = self._instante_unico(moment)

        decisoes = tuple(
            self._decidir_dominio(
                domain_id=domain_id,
                original=context,
                descriptor=descriptor,
                policy_key=policy_key,
                moment=instante,
            )
            for domain_id in sorted(context.domain_ids)
        )

        if not all(d.authorized for d in decisoes):
            # Recusa atômica. Nenhuma membership é lida, nenhuma
            # Retrieval é executada, e o contexto NÃO é estreitado
            # removendo os domínios recusados — isso responderia a uma
            # pergunta diferente da que o usuário fez.
            #
            #     PARTIAL AUTHORITY != AUTHORITY TO REWRITE REQUESTED SCOPE
            logger.info(
                "isolated_retrieval_denied",
                extra={
                    "declared_domains": len(context.domain_ids),
                    "refused_domains": len([d for d in decisoes if not d.authorized]),
                },
            )
            return MemoryIsolationResult(context=context, decisions=decisoes, evaluated_at=instante)

        # Snapshot capturado SOMENTE depois da autoridade, e uma vez.
        # Garantia conservadora no instante observado: sem lock de
        # escrita, sem promessa de isolamento serializável.
        autorizado = self._snapshot_autorizado(decisoes)

        resultado = self._retrieval.retrieve(
            context=context,
            descriptor=descriptor,
            criteria=criteria,
            policy_key=policy_key,
            moment=instante,
            limit=limit,
            offset=offset,
        )
        self._verificar_resultado(
            resultado,
            context=context,
            limit=limit,
            offset=offset,
            autorizado=autorizado,
        )

        logger.info(
            "isolated_retrieval_executed",
            extra={
                "declared_domains": len(context.domain_ids),
                "returned": len(resultado.items),
            },
        )
        return MemoryIsolationResult(
            context=context,
            decisions=decisoes,
            evaluated_at=instante,
            retrieval=resultado,
        )

    # --- Validação do pedido -------------------------------------------

    @staticmethod
    def _validar_argumentos(
        *,
        context: object,
        descriptor: object,
        policy_key: object,
        limit: object,
        offset: object,
    ) -> None:
        """Tipos e precondições, antes de tocar em qualquer colaborador."""
        if not isinstance(context, MemoryContext):
            raise TypeError(f"context deve ser MemoryContext, recebido {type(context).__name__}")
        if not isinstance(descriptor, CapabilityDescriptor):
            raise TypeError(
                "descriptor deve ser CapabilityDescriptor, recebido " f"{type(descriptor).__name__}"
            )
        if descriptor.operation is not CognitiveOperation.READ:
            raise ValueError(
                "o isolamento da E4.8 é caminho de leitura e usa "
                f"CognitiveOperation.READ; recebido {descriptor.operation}"
            )
        if policy_key is not None and not isinstance(policy_key, str):
            raise TypeError(
                f"policy_key deve ser str ou None, recebido {type(policy_key).__name__}"
            )
        for nome, valor in (("limit", limit), ("offset", offset)):
            if not isinstance(valor, int) or isinstance(valor, bool):
                raise TypeError(f"{nome} deve ser int, recebido {type(valor).__name__}")
        # Escopo explícito é PRECONDIÇÃO — verificada antes de
        # governança, memberships e Retrieval.
        #
        #     EMPTY DOMAIN SCOPE IS NOT AN ISOLATION BOUNDARY
        if not context.domain_ids:
            raise IsolationScopeRequiredError

    @staticmethod
    def _verificar_fidelidade_do_contexto(solicitado: MemoryContext, confirmado: object) -> None:
        """O validador confirma a perspectiva; não a reescreve.

        CONTEXT VALIDATION != CONTEXT SUBSTITUTION
        """
        if not isinstance(confirmado, MemoryContext):
            raise IsolationContractViolationError(
                (
                    "ContextManager.validate devolveu "
                    f"{type(confirmado).__name__}, não MemoryContext",
                )
            )
        if confirmado != solicitado:
            raise IsolationContractViolationError(
                (
                    "ContextManager.validate devolveu contexto diferente do "
                    "solicitado — validação não substitui a perspectiva pedida",
                )
            )

    @staticmethod
    def _instante_unico(moment: datetime | None) -> datetime:
        """Um instante de decisão para a operação inteira."""
        if moment is None:
            return datetime.now(UTC)
        if not isinstance(moment, datetime):
            raise TypeError(f"moment deve ser datetime ou None, recebido {type(moment).__name__}")
        if moment.tzinfo is None:
            raise ValueError(
                "moment deve ser timezone-aware — um instante ingênuo tornaria a "
                "vigência dependente do fuso da máquina"
            )
        return moment.astimezone(UTC)

    # --- Autoridade domínio a domínio ----------------------------------

    def _decidir_dominio(
        self,
        *,
        domain_id: uuid.UUID,
        original: MemoryContext,
        descriptor: CapabilityDescriptor,
        policy_key: str | None,
        moment: datetime,
    ) -> DomainIsolationDecision:
        """Resolve `READ` para um domínio, sob perspectiva singleton.

        O singleton serve **apenas** para perguntar à governança sobre
        aquele domínio: preserva `session_id`, `actor_ref` e `purpose`
        exatamente, e o contexto original é o único que segue para a
        Retrieval.
        """
        singleton = self._context.derive(
            original,
            domain_ids=(domain_id,),
            session_id=original.session_id,
            actor_ref=original.actor_ref,
            purpose=original.purpose,
        )
        if not isinstance(singleton, MemoryContext):
            raise IsolationContractViolationError(
                (
                    "ContextManager.derive devolveu "
                    f"{type(singleton).__name__}, não MemoryContext",
                )
            )
        motivos = self._divergencias_do_singleton(singleton, original, domain_id)
        if motivos:
            raise IsolationContractViolationError(tuple(motivos))

        resolucao = self._governance.resolve(
            descriptor=descriptor,
            context=singleton,
            policy_key=policy_key,
            moment=moment,
        )
        self._verificar_fidelidade_da_resolucao(
            resolucao, singleton=singleton, descriptor=descriptor, policy_key=policy_key
        )
        return DomainIsolationDecision(domain_id=domain_id, resolution=resolucao)

    @staticmethod
    def _divergencias_do_singleton(
        singleton: MemoryContext, original: MemoryContext, domain_id: uuid.UUID
    ) -> list[str]:
        """O singleton troca o escopo e **nada mais**."""
        motivos: list[str] = []
        if singleton.domain_ids != (domain_id,):
            motivos.append(
                f"o contexto singleton declara "
                f"{[str(d) for d in singleton.domain_ids]}, e não apenas {domain_id}"
            )
        for nome, derivado, esperado in (
            ("session_id", singleton.session_id, original.session_id),
            ("actor_ref", singleton.actor_ref, original.actor_ref),
            ("purpose", singleton.purpose, original.purpose),
        ):
            if derivado != esperado:
                motivos.append(
                    f"o singleton alterou {nome}: {derivado!r} em vez de {esperado!r} — "
                    "derivar o escopo não reescreve a perspectiva do usuário"
                )
        return motivos

    @staticmethod
    def _verificar_fidelidade_da_resolucao(
        resolucao: object,
        *,
        singleton: MemoryContext,
        descriptor: CapabilityDescriptor,
        policy_key: str | None,
    ) -> None:
        """A autorização tem de ser sobre **este** singleton.

        Usa a função compartilhada da E4.3.4 — não uma cópia da
        comparação, que divergiria com o tempo — e não consulta o
        repositório de policy para "confirmar" a resolução.

            REQUESTED CONTEXT MUST EQUAL RESOLVED CONTEXT
        """
        if not isinstance(resolucao, GovernanceResolution):
            raise IsolationContractViolationError(
                (
                    "GovernanceManager.resolve devolveu "
                    f"{type(resolucao).__name__}, não GovernanceResolution",
                )
            )
        motivos: list[str] = []
        if resolucao.operation is not CognitiveOperation.READ:
            motivos.append(
                f"a resolução é sobre {resolucao.operation}, e o isolamento resolve "
                "CognitiveOperation.READ"
            )
        if resolucao.operation is not descriptor.operation:
            motivos.append(
                f"operação resolvida ({resolucao.operation}) difere da solicitada "
                f"({descriptor.operation})"
            )
        if resolucao.policy_key is not None and resolucao.policy_key != policy_key:
            motivos.append(
                f"policy resolvida {resolucao.policy_key!r} difere da solicitada " f"{policy_key!r}"
            )
        motivos.extend(
            resolucao_vincula_contexto(
                resolucao,
                domain_ids=singleton.domain_ids,
                actor_ref=singleton.actor_ref,
                purpose=singleton.purpose,
            )
        )
        if motivos:
            raise IsolationContractViolationError(tuple(motivos))

    # --- Snapshot e pós-condição ---------------------------------------

    def _snapshot_autorizado(
        self, decisoes: tuple[DomainIsolationDecision, ...]
    ) -> frozenset[uuid.UUID]:
        """União imutável das memberships dos domínios autorizados.

        Capturada **uma vez**, depois da autoridade. A garantia é a do
        instante observado: nenhum lock de escrita é adquirido e nenhum
        isolamento serializável é prometido.
        """
        uniao: set[uuid.UUID] = set()
        for decisao in decisoes:
            bruto = self._memberships.list_memberships_of_domain(decisao.domain_id)
            # `Sequence`, não `Iterable`: um generator seria consumido
            # aqui e depois compararia vazio. A E4.6.2 fechou essa mesma
            # classe de defeito.
            if isinstance(bruto, str | bytes) or not isinstance(bruto, Sequence):
                raise IsolationContractViolationError(
                    (
                        "list_memberships_of_domain devolveu "
                        f"{type(bruto).__name__}, e o contrato da porta declara "
                        "Sequence",
                    )
                )
            for item in bruto:
                # `isinstance` contra um Protocol runtime_checkable
                # **tipa** o objeto para o mypy: a leitura dos campos
                # abaixo é verificada estaticamente, sem reflexão.
                if not isinstance(item, MembershipView):
                    raise IsolationContractViolationError(
                        (
                            "a porta devolveu um objeto sem os campos de uma "
                            f"membership ({type(item).__name__})",
                        )
                    )
                if item.domain_id != decisao.domain_id:
                    raise IsolationContractViolationError(
                        (
                            f"membership devolvida para o domínio {item.domain_id}, "
                            f"mas foi pedida a do domínio {decisao.domain_id}",
                        )
                    )
                if not isinstance(item.coid, uuid.UUID):
                    raise IsolationContractViolationError(
                        (
                            "membership com coid do tipo "
                            f"{type(item.coid).__name__}, não uuid.UUID",
                        )
                    )
                uniao.add(item.coid)
        return frozenset(uniao)

    @staticmethod
    def _verificar_resultado(
        resultado: object,
        *,
        context: MemoryContext,
        limit: int,
        offset: int,
        autorizado: frozenset[uuid.UUID],
    ) -> None:
        """Fidelidade da vista e **não expansão** do escopo.

        Um COID fora do snapshot é violação de contrato — nunca um item
        a filtrar em silêncio:

            LEAK DETECTED != AUTHORIZATION TO SILENTLY FILTER
            AUTO_DESTRUCTIVE_REPAIR = FORBIDDEN

        Item que também pertence a um domínio **não solicitado** não é
        contaminado: ele está no snapshot por um domínio autorizado, e
        isso basta.
        """
        if not isinstance(resultado, MemoryRetrievalResult):
            raise IsolationContractViolationError(
                (
                    "MemoryRetrievalManager.retrieve devolveu "
                    f"{type(resultado).__name__}, não MemoryRetrievalResult",
                )
            )
        motivos: list[str] = []
        if resultado.context != context:
            motivos.append("o resultado da Retrieval cita um contexto diferente do solicitado")
        if resultado.limit != limit or resultado.offset != offset:
            motivos.append(
                f"paginação devolvida (limit={resultado.limit}, "
                f"offset={resultado.offset}) difere da solicitada (limit={limit}, "
                f"offset={offset})"
            )
        fora = tuple(coid for coid in resultado.coids if coid not in autorizado)
        if fora:
            motivos.append(
                f"a vista devolveu {len(fora)} objeto(s) fora da união de memberships "
                f"dos domínios autorizados, começando por {fora[0]} — expansão de "
                "escopo não é filtrada em silêncio"
            )
        if motivos:
            raise IsolationContractViolationError(tuple(motivos))
