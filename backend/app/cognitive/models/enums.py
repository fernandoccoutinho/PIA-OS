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
