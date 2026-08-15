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

from app.memory.ports.consolidation import (
    MultiInputTransformationPort,
    MultiInputTransformationReceiptPort,
)

__all__ = [
    "MultiInputTransformationPort",
    "MultiInputTransformationReceiptPort",
]
