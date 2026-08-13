"""
Enums estruturais mínimos da Biblioteca Cognitiva.

`AccessibilityState` pertence funcionalmente a `E3.6` (Metadata Manager
+ Provenance + Accessibility) — nenhuma política de transição de estado
é implementada aqui. Este módulo define apenas os 4 valores porque
`CognitiveObject` (propriedade de `E3.1`) já exige o campo em seu
contrato (`E3_DOMAIN_MODEL_DRAFT.md`, seção "0. CognitiveObject") — é
a referência estrutural explicitamente permitida por essa exceção
("salvo referência estrutural expressamente exigida pelo Domain
Model"). `E3.6` é dona da elaboração completa (regras de transição,
serviço que valida quem pode mover o quê) — este módulo não antecipa
nada disso.
"""

from enum import StrEnum


class AccessibilityState(StrEnum):
    """Estado de acessibilidade de um `CognitiveObject`.

    `CAUSALLY_EXTINCT` nunca é inferido pela ausência de um objeto no
    contexto atual — essa regra (E3_DOMAIN_MODEL_DRAFT.md, §4) é uma
    invariante de todo o sistema, não apenas de E3.6, e por isso nenhum
    código em `app.cognitive` (nem fora dele) deve tratar "não
    encontrado" como equivalente a este valor.
    """

    ACTIVE = "active"
    LATENT = "latent"
    INACCESSIBLE = "inaccessible"
    CAUSALLY_EXTINCT = "causally_extinct"


class LineageRelation(StrEnum):
    """Natureza de uma `LineageEdge` — taxonomia já congelada em
    `E3_DOMAIN_MODEL_DRAFT.md`, seção "8. LineageEdge" (E3.3/LIB-03 é
    a proprietária). Os 6 valores são usados como estão — nenhum foi
    adicionado nem removido.

    `PARENT`/`CHILD` existem no vocabulário para uso futuro de módulos
    que optem por armazenamento simétrico de relação (uma edge
    explícita em cada direção); `LineageEdge` de E3.3 usa
    armazenamento direcionado único (`parent_coid`/`child_coid` como
    colunas já codificam a direção — ver `lineage_edge.py`), então as
    edges que E3.3 cria usam predominantemente `DERIVED_FROM` como
    relação padrão de continuidade, não `PARENT`/`CHILD` como valor de
    `relation_type`. `TRANSFORMED_FROM` fica disponível para quando
    `E3.4` (`TransformationRecord`) precisar dele.
    """

    PARENT = "parent"
    CHILD = "child"
    BRANCH = "branch"
    MERGE = "merge"
    DERIVED_FROM = "derived_from"
    TRANSFORMED_FROM = "transformed_from"


class RevisionStatus(StrEnum):
    """Status de revisão controlada de um `CognitiveObject`
    (correção E3.4.0) — distinto de `AccessibilityState` (§7 do
    prompt corretivo: uma revisão `SUPERSEDED` pode continuar
    `ACTIVE` para auditoria; os dois campos são independentes).

    `None` (o campo é nullable em `CognitiveObject`) significa "não
    participa de uma cadeia de revisão controlada" — o caso comum
    para objetos de `DERIVATION`/workspace, que nunca tocam este
    campo. Apenas objetos passados por `VersionManager.revise()`
    recebem um valor aqui.

    Somente os dois estados mínimos necessários — `ARCHIVED`,
    `DELETED`, `EXPIRED`, `RETIRED`, `OBSOLETE` (ou equivalentes) não
    são implementados nesta fase (§6 do prompt corretivo); política de
    retenção/arquivamento físico pertence a módulos futuros.
    """

    CURRENT = "current"
    SUPERSEDED = "superseded"


class TransformationKind(StrEnum):
    """Distingue `REVISION` de `DERIVATION` em um `TransformationRecord`
    (correção E3.4.0) — campo obrigatório, ao lado de `operation_type`
    (que permanece livre/aberto, ex.: "summarize", "revise").

    `DERIVATION`: novo objeto derivado de outro, sem suceder o source
    — `source` permanece a representação vigente do que quer que ele
    represente (`VersionManager.derive()`).

    `REVISION`: nova revisão controlada do MESMO patrimônio lógico —
    `target` torna-se `RevisionStatus.CURRENT`, `source` (se era
    `CURRENT`, ou implicitamente se nunca teve status) torna-se
    `RevisionStatus.SUPERSEDED` (`VersionManager.revise()`).
    """

    REVISION = "revision"
    DERIVATION = "derivation"


class RelationshipType(StrEnum):
    """Tipos de relação semântica explícita entre `CognitiveObject`s
    (`E3.5`/`LIB-05`) — distinta de `LineageRelation` (histórico de
    derivação/continuidade). Taxonomia mínima justificável pelos
    exemplos conceituais do próprio módulo E3.5 — não uma ontologia
    extensa; `CAUSES` deliberadamente não incluído (nenhum requisito
    explícito de causalidade declarada nesta fase).

    Cada tipo tem direcionalidade fixa (ver
    `RelationshipType.directionality`): todos são `DIRECTED`, exceto
    `RELATED_TO`, que é `SYMMETRIC`.
    """

    RELATED_TO = "related_to"
    REFERENCES = "references"
    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    DEPENDS_ON = "depends_on"

    @property
    def is_symmetric(self) -> bool:
        """`True` apenas para `RELATED_TO` — os demais são
        direcionados (`A REFERENCES B` não implica `B REFERENCES A`)."""
        return self is RelationshipType.RELATED_TO
