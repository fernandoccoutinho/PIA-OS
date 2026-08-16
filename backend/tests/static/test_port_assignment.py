"""
Prova **estática** de que o `AccessibilityManager` real satisfaz a porta.

Este arquivo não tem asserção de runtime: seu valor é ser verificado pelo
mypy. A atribuição abaixo falha na cadeia 55 — onde a porta declarava
`target_state: str` e o manager real exige `AccessibilityState` — e passa
a partir do corretivo E4.7.1, que tornou a porta genérica sobre o estado.

```text
RUNTIME_CHECKABLE != STATIC SIGNATURE COMPATIBILITY
PORT METHOD NAME != PORT TRUTHFULNESS
```

`isinstance` num `Protocol` `runtime_checkable` confere apenas a
**presença** dos membros. Foi por isso que a candidata passou nos
próprios testes afirmando uma tipagem que não tinha.

Sem `Any`, `cast` ou `type: ignore` — que anulariam a prova.
"""

from app.cognitive.models.causal_history import CausalHistory, CausalHistoryEvent
from app.cognitive.models.cognitive_object import CognitiveObject
from app.cognitive.models.enums import AccessibilityState
from app.cognitive.repositories.causal_history_repository import CausalHistoryRepository
from app.cognitive.repositories.object_repository import ObjectRepository
from app.cognitive.services.accessibility_manager import AccessibilityManager
from app.memory.ports.accessibility import (
    AccessibilityTransitionPort,
    CausalEvidencePort,
    CognitiveSubjectPort,
)


def prova_de_atribuicao_estatica(
    objetos: ObjectRepository,
    historias: CausalHistoryRepository,
) -> None:
    """As três portas, satisfeitas por atribuição verificada pelo mypy."""
    sujeitos: CognitiveSubjectPort[CognitiveObject] = objetos
    transicoes: AccessibilityTransitionPort[CognitiveObject, AccessibilityState] = (
        AccessibilityManager(objetos)
    )
    evidencia: CausalEvidencePort[CausalHistoryEvent, CausalHistory] = historias
    _ = (sujeitos, transicoes, evidencia)


def test_static_port_assignment_module_is_type_checked() -> None:
    """Marcador de runtime: a prova real é o mypy sobre este arquivo."""
    assert prova_de_atribuicao_estatica.__doc__
