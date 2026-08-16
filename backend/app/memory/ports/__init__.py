"""
Portas estruturais da camada de memória (`app/memory`).

Uma porta declara a **forma** de algo que a E4 consome mas não
implementa — hoje, o writer de patrimônio da E3. Existem porque
`app/memory` nunca importa `app.cognitive`, e a inversão de dependência
é o que permite compor os dois lados sem atravessar essa fronteira.

Nada aqui contém regra de negócio: uma porta que decidisse algo seria
uma segunda fonte da verdade sobre patrimônio, que é exatamente o que a
arquitetura congelada não admite.
"""

from app.memory.ports.accessibility import (
    AccessibilityTransitionPort,
    CausalEventView,
    CausalEvidencePort,
    CausalHistoryView,
    CognitiveSubjectPort,
)
from app.memory.ports.consolidation import (
    MultiInputTransformationPort,
    MultiInputTransformationReceiptPort,
)
from app.memory.ports.retrieval import CognitiveObjectView, CognitiveSearchPort

__all__ = [
    "AccessibilityTransitionPort",
    "CausalEventView",
    "CausalEvidencePort",
    "CausalHistoryView",
    "CognitiveObjectView",
    "CognitiveSubjectPort",
    "CognitiveSearchPort",
    "MultiInputTransformationPort",
    "MultiInputTransformationReceiptPort",
]
