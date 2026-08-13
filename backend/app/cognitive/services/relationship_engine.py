"""
RelationshipEngine — LIB-05, relações semânticas explícitas entre
`CognitiveObject`s.

Responsabilidade única: registrar, classificar, consultar e gerenciar
o ciclo de vida de `Relationship`s — não decide relevância, não
executa busca semântica, não infere causalidade, não chama provider
de IA, não controla commit (§15 do módulo E3.5).

**COUT-PIA** (§4-§5 do módulo): uma `Relationship` declara exatamente
o que seu tipo diz. `RelationshipEngine` nunca deriva de uma relação
declarada: causalidade, equivalência, identidade, superioridade,
verdade, confiança, importância, qualidade, relevância, substituição,
persistência ou acessibilidade. Nenhum `*_score`/`ranking` existe ou
pode ser adicionado — não há caminho de código que produza um.
Relações contraditórias (`A SUPPORTS X`, `B CONTRADICTS X`) coexistem
sem erro — `RelationshipEngine` não resolve conflitos, isso pertence
a fases futuras de governança/arbiter (§22).

**Relationship != Lineage**: `RelationshipEngine` nunca cria
`LineageEdge`, e `ClidManager.inherit()`/`VersionManager` nunca criam
`Relationship` — taxonomias e responsabilidades disjuntas (§3, §29).

**Workspace vs Controlled Asset**: nenhuma promoção automática — só
chamadas explícitas a `create()` produzem uma `Relationship` (§24).
"""

import uuid

from app.cognitive.models.enums import RelationshipType
from app.cognitive.models.relationship import Relationship
from app.cognitive.repositories.relationship_repository import RelationshipRepository


class RelationshipEngine:
    """Cria, classifica, consulta e gerencia o ciclo de vida de
    `Relationship`s.

    Depende apenas de `RelationshipRepository` — não conhece
    `ObjectRepository`/`ClidManager`/`VersionManager` diretamente
    (validação de existência de endpoint é FK no banco, traduzida pelo
    repositório; `RelationshipEngine` não precisa carregar
    `CognitiveObject`s para criar uma relação, mesma economia já
    aplicada a `LineageRepository.add_edge`, que também opera só por
    COID).
    """

    def __init__(self, relationship_repository: RelationshipRepository) -> None:
        self._relationships = relationship_repository

    def create(
        self,
        *,
        source_coid: uuid.UUID,
        target_coid: uuid.UUID,
        relationship_type: RelationshipType,
    ) -> Relationship:
        """Registra uma nova `Relationship` explícita.

        Não commita — `flush()` implícito via
        `RelationshipRepository.add()`; commit permanece do chamador
        via `UnitOfWork`.

        Self-relation é rejeitada globalmente (`RelationshipSelfLinkError`,
        `PIA-8013`) — nenhum dos 5 tipos tem caso de uso legítimo
        identificado para `A -> A` nesta fase (§11 do módulo E3.5).
        Duplicidade é rejeitada conforme a semântica de cada tipo —
        direcionada (tripla exata) ou simétrica (par não ordenado) —
        delegada ao repositório, que normaliza e traduz a violação de
        índice único (`RelationshipDuplicateError`, `PIA-8014`).
        Endpoint inexistente é rejeitado via FK
        (`RelationshipEndpointNotFoundError`, `PIA-8015`).
        """
        return self._relationships.add_relationship(
            source_coid=source_coid, target_coid=target_coid, relationship_type=relationship_type
        )

    def retire(self, relationship: Relationship) -> Relationship:
        """Marca uma `Relationship` como não mais vigente — soft-retire,
        nunca remoção física (`RelationshipRepository.retire`,
        idempotente). O fato histórico de que a relação foi declarada
        nunca é apagado (§12 do módulo E3.5)."""
        return self._relationships.retire(relationship)

    def outgoing(
        self,
        source_coid: uuid.UUID,
        *,
        relationship_type: RelationshipType | None = None,
    ) -> list[Relationship]:
        """Relações vigentes onde `source_coid` é a origem."""
        return self._relationships.outgoing(source_coid, relationship_type=relationship_type)

    def incoming(
        self,
        target_coid: uuid.UUID,
        *,
        relationship_type: RelationshipType | None = None,
    ) -> list[Relationship]:
        """Relações vigentes onde `target_coid` é o destino."""
        return self._relationships.incoming(target_coid, relationship_type=relationship_type)

    def neighbors(self, coid: uuid.UUID) -> list[Relationship]:
        """Relações vigentes (`outgoing` + `incoming`) que tocam
        `coid`, em qualquer direção/tipo — one-hop apenas, sem
        travessia multi-hop (§14 do módulo E3.5)."""
        return self._relationships.neighbors(coid)

    def by_type(self, relationship_type: RelationshipType) -> list[Relationship]:
        """Todas as relações vigentes de um tipo."""
        return self._relationships.by_type(relationship_type)
