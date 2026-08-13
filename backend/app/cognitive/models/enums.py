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
