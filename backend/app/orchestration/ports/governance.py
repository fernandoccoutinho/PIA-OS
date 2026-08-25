"""
Porta de resolução de Governança (`E7.4-1 B1a`).

```text
PORT_IN_THE_CONSUMER · ADAPTER_WHERE_THE_IMPORT_IS_LEGAL
BRIDGE_BY_DIRECT_IMPORT = FROZEN_GUARD_VIOLATION
```

A E7 precisa da decisão da E4.3 e não pode importar `app.memory`. A porta fica
onde o consumidor está; o adaptador que faz o import legal vive em
`app/services/governance_bridge.py`. Precedente literal: a
`MultiInputTransformationPort` da E4.5 resolveu a mesma tensão do mesmo jeito.

Nada aqui carrega texto livre, conteúdo, instrução, prompt ou segredo. Os
campos textuais da resolução entram no `decision_fingerprint` e **não** na
vista — é o que permite provar a decisão sem arquivar o pedido.

```text
SAFETY_AUDIT_METADATA != DANGEROUS_PAYLOAD_ARCHIVE
HUMAN_PROTECTION_EVENT_CONTENT = NONE
```
"""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable

from app.orchestration.ports.governance_vocabulary import (
    ACCEPTED_BOUNDARY_OUTCOMES,
    BoundaryCapability,
    BoundaryEngagement,
    BoundaryOperation,
    BoundaryOutcome,
)
from app.orchestration.protection.binding import SHA256_LOWER_HEX, GovernanceBinding


def _instante(nome: str, valor: object) -> datetime:
    if not isinstance(valor, datetime):
        raise TypeError(f"{nome} deve ser datetime, recebido {type(valor).__name__}")
    if valor.tzinfo is None or valor.utcoffset() is None:
        raise ValueError(f"{nome} deve ser datetime com fuso")
    return valor


def _hash(nome: str, valor: object) -> str:
    if not isinstance(valor, str) or not SHA256_LOWER_HEX.match(valor):
        raise ValueError(f"{nome} deve ser sha-256 hexadecimal minúsculo de 64 dígitos")
    return valor


@dataclass(frozen=True)
class GovernanceQuery:
    """A pergunta governada, tipada e sem compressão de contexto.

    Os quatro campos de `MemoryContext` atravessam **um a um**. Reduzi-los a
    uma referência opaca faria duas perguntas diferentes produzirem o mesmo
    material de hash — exatamente o defeito que o corretivo E4.3.4 fechou do
    lado da E4 (`CONTEXT BINDING != LOCAL POLICY PROVENANCE`).

    O descritor semântico vem de um produtor autorizado (E8 IAB). Enquanto
    ele não existir, nenhuma composição produtiva monta esta consulta.

    ```text
    MISSING_AUTHORIZED_DESCRIPTOR != AUTHORIZED_EMPTY_DESCRIPTOR
    CLIENT_SUPPLIED_CATEGORY_ANY_PATH = PROHIBITED
    ```
    """

    descriptor_operation: BoundaryOperation
    descriptor_capabilities: frozenset[BoundaryCapability]
    descriptor_engagement: BoundaryEngagement
    binding: GovernanceBinding
    context_domain_ids: tuple[uuid.UUID, ...] = ()
    context_session_id: str | None = None
    context_actor_ref: str | None = None
    context_purpose: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.descriptor_operation, BoundaryOperation):
            raise TypeError("descriptor_operation deve ser um BoundaryOperation")
        if not isinstance(self.descriptor_engagement, BoundaryEngagement):
            raise TypeError("descriptor_engagement deve ser um BoundaryEngagement")
        if not isinstance(self.binding, GovernanceBinding):
            raise TypeError("binding deve ser um GovernanceBinding")

        capacidades = self.descriptor_capabilities
        if isinstance(capacidades, str | bytes) or not isinstance(capacidades, Iterable):
            raise TypeError("descriptor_capabilities deve ser um iterável de BoundaryCapability")
        itens = tuple(capacidades)
        if any(not isinstance(item, BoundaryCapability) for item in itens):
            raise TypeError("descriptor_capabilities aceita apenas BoundaryCapability")
        object.__setattr__(self, "descriptor_capabilities", frozenset(itens))

        dominios = self.context_domain_ids
        if isinstance(dominios, str | bytes) or not isinstance(dominios, Iterable):
            raise TypeError("context_domain_ids deve ser um iterável de uuid.UUID")
        ids = tuple(dominios)
        if any(not isinstance(item, uuid.UUID) for item in ids):
            raise TypeError("context_domain_ids aceita apenas uuid.UUID")
        object.__setattr__(self, "context_domain_ids", ids)

        for campo in ("context_session_id", "context_actor_ref", "context_purpose"):
            valor = getattr(self, campo)
            if valor is None:
                continue
            if not isinstance(valor, str):
                raise TypeError(f"{campo} deve ser str ou None")
            if not valor.strip():
                raise ValueError(f"{campo} não pode ser vazio ou apenas espaços — omita-o")

        if self.descriptor_operation is not self.binding.operation:
            raise ValueError(
                "descriptor_operation e binding.operation descrevem a MESMA operação "
                "governada; divergência é pergunta incoerente, não duas perguntas"
            )


@dataclass(frozen=True)
class GovernanceResolutionView:
    """A resposta, por valor, sem instância ORM e sem texto livre.

    Congelada e hashable. `blocked_capabilities` é **tupla ordenada** e
    preserva cardinalidade: reduzir uma coleção a um elemento inventaria uma
    regra de seleção que ninguém escreveu.

    ```text
    COLLECTION_REDUCED_TO_ONE = INVENTED_SELECTION_RULE
    ```
    """

    outcome: BoundaryOutcome
    capability_engagement: BoundaryEngagement
    boundary_version: int
    classifier_version: str
    decision_fingerprint: str
    binding_sha256: str
    evaluated_at: datetime
    valid_until: datetime
    blocked_capabilities: tuple[BoundaryCapability, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, BoundaryOutcome):
            raise TypeError("outcome deve ser um BoundaryOutcome")
        if self.outcome not in ACCEPTED_BOUNDARY_OUTCOMES:
            raise ValueError(
                f"a ponte não interpreta '{self.outcome.value}' — apenas prohibited e "
                "not_applicable; qualquer outro é indisponibilidade técnica"
            )
        if not isinstance(self.capability_engagement, BoundaryEngagement):
            raise TypeError("capability_engagement deve ser um BoundaryEngagement")

        capacidades = self.blocked_capabilities
        if isinstance(capacidades, str | bytes) or not isinstance(capacidades, Iterable):
            raise TypeError("blocked_capabilities deve ser um iterável de BoundaryCapability")
        itens = tuple(capacidades)
        if any(not isinstance(item, BoundaryCapability) for item in itens):
            raise TypeError("blocked_capabilities aceita apenas BoundaryCapability")
        if len(set(itens)) != len(itens):
            raise ValueError("blocked_capabilities não aceita repetição")
        object.__setattr__(self, "blocked_capabilities", itens)

        if isinstance(self.boundary_version, bool) or not isinstance(self.boundary_version, int):
            raise TypeError("boundary_version deve ser int")
        if self.boundary_version < 1:
            raise ValueError("boundary_version deve ser >= 1")
        if not isinstance(self.classifier_version, str) or not self.classifier_version.strip():
            raise ValueError("classifier_version é obrigatório")

        object.__setattr__(
            self, "decision_fingerprint", _hash("decision_fingerprint", self.decision_fingerprint)
        )
        object.__setattr__(self, "binding_sha256", _hash("binding_sha256", self.binding_sha256))
        object.__setattr__(self, "evaluated_at", _instante("evaluated_at", self.evaluated_at))
        object.__setattr__(self, "valid_until", _instante("valid_until", self.valid_until))
        if self.valid_until < self.evaluated_at:
            raise ValueError("valid_until anterior a evaluated_at — validade inexistente")

        self._validar_coerencia()

    def _validar_coerencia(self) -> None:
        """Espelha a coerência que a própria E4 impõe na resolução.

        `PROHIBITED` sem capacidade é recusa irrecorrível; `NOT_APPLICABLE`
        com capacidade seria proveniência falsa, porque capacidade bloqueada
        é a marca da fronteira. As duas regras estão em
        `GovernanceResolution._validate_coherence`; aqui elas impedem que uma
        vista incoerente exista — nem vinda de um adaptador com defeito, nem
        de um dublê de teste mais frouxo que o real.

        ```text
        FAKE_LOOSER_THAN_REAL = TEST_THAT_PROVES_NOTHING
        ```
        """
        proibido = self.outcome is BoundaryOutcome.PROHIBITED
        if proibido and not self.blocked_capabilities:
            raise ValueError("prohibited exige ao menos uma capacidade bloqueada")
        if not proibido and self.blocked_capabilities:
            raise ValueError(f"{self.outcome.value} não pode carregar capacidades bloqueadas")


@runtime_checkable
class GovernanceResolutionPort(Protocol):
    """Fronteira estrutural: uma pergunta tipada, uma resposta por valor.

    `@runtime_checkable` confere **nomes de membros**, não assinaturas —
    lição do defeito D da E4.7.1 (`RUNTIME_CHECKABLE != STATIC SIGNATURE
    COMPATIBILITY`). A compatibilidade real do adaptador é provada
    estaticamente em `tests/static/test_port_assignment.py`.
    """

    def resolve(self, query: GovernanceQuery) -> GovernanceResolutionView:
        """Resolve a pergunta pelo caminho canônico da Governança E4."""
        ...
