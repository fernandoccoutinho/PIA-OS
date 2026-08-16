"""
Prova **estática** da composição real da E4.7, ponta a ponta.

Este arquivo quase não tem asserção de runtime: seu valor é ser
verificado pelo mypy.

## O que a candidata 55 provava — e por que não bastava

A E4.7 original afirmava tipagem estática e provava com `isinstance`,
que confere apenas **nomes de membros**:

```text
RUNTIME_CHECKABLE != STATIC SIGNATURE COMPATIBILITY
```

A E4.7.1 corrigiu isso com atribuição verificada. Mas atribuir não é
chamar:

```text
STATIC ASSIGNMENT != TYPED END-TO-END COMPOSITION
```

## O que este arquivo prova agora (corretivo E4.7.2)

1. as três portas são satisfeitas pelos objetos reais da E3, por
   **atribuição**;
2. o `AccessibilityPolicyManager` real é construível como
   `AccessibilityPolicyManager[CognitiveObject, AccessibilityState]`;
3. `transition()` é **chamado** com um membro real de
   `AccessibilityState`, e o resultado tem o tipo declarado.

Sem `Any`, `cast`, `type: ignore` ou reflexão — qualquer um deles
anularia a prova.
"""

import uuid
from datetime import datetime

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
from app.memory.repositories.accessibility_policy_repository import (
    AccessibilityPolicyRepository,
)
from app.memory.schemas.accessibility import AccessibilityTransitionResult
from app.memory.schemas.memory_context import MemoryContext
from app.memory.services.accessibility_policy_manager import AccessibilityPolicyManager
from app.memory.services.context_manager import ContextManager
from app.memory.services.governance_manager import GovernanceManager
from app.memory.services.platform_safety_boundary import CapabilityDescriptor


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


def prova_de_composicao_e_chamada_tipada(
    objetos: ObjectRepository,
    historias: CausalHistoryRepository,
    policies: AccessibilityPolicyRepository,
    governanca: GovernanceManager,
    contexto: ContextManager,
    coid: uuid.UUID,
    descritor: CapabilityDescriptor,
    momento: datetime,
) -> AccessibilityTransitionResult:
    """A composição real, tipada, com chamada usando o enum verdadeiro.

    `AccessibilityState.LATENT` — não a string `"latent"`. Se a porta
    voltasse a declarar `target_state: str`, esta chamada continuaria
    válida e a prova não valeria nada; é a parametrização explícita por
    `AccessibilityState` que a torna significativa.
    """
    manager: AccessibilityPolicyManager[CognitiveObject, AccessibilityState] = (
        AccessibilityPolicyManager(
            objetos,
            AccessibilityManager(objetos),
            historias,
            policies,
            governanca,
            contexto,
        )
    )
    return manager.transition(
        coid=coid,
        target_state=AccessibilityState.LATENT,
        context=MemoryContext(),
        descriptor=descritor,
        governance_policy_key="g",
        accessibility_policy_key="a",
        moment=momento,
    )


def test_static_port_assignment_module_is_type_checked() -> None:
    """Marcador de runtime: a prova real é o mypy sobre este arquivo."""
    assert prova_de_atribuicao_estatica.__doc__
    assert prova_de_composicao_e_chamada_tipada.__doc__
