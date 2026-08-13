"""
AccessibilityManager — LIB-06, transições de `AccessibilityState` de
um `CognitiveObject`.

**Escopo deliberadamente restrito** (decisão registrada, não Stop
Condition): o Domain Model Draft (`E3_DOMAIN_MODEL_DRAFT.md`, §4) é
explícito — "a máquina de transição de estados completa (quem pode
mover o quê, sob qual autoridade) é escopo de `E4` (políticas de
memória) — E3 apenas define e persiste o enum e valida que a
transição para `CAUSALLY_EXTINCT` sempre tem um evento causal
associado, nunca é o valor default nem um efeito colateral de query."

Portanto, `AccessibilityManager`:

- **não** restringe qual estado pode transicionar para qual (matriz
  completa de autoridade é `E4`, não antecipada aqui);
- garante apenas que `CAUSALLY_EXTINCT` nunca é o default (já
  estrutural desde E3.1 — `default=AccessibilityState.ACTIVE`) e nunca
  é atingido sem uma justificativa explícita.

**Limitação documentada**: a exigência formal do Draft — "sempre tem
um evento causal associado" — depende de `CausalHistoryEvent`, que é
`E3.9` (ainda não implementado). Como proxy interino, honesto e
genuinamente aplicável hoje, a transição para `CAUSALLY_EXTINCT` exige
um `reason` não-vazio — não é o mesmo que um evento causal
referenciado formalmente, mas garante que a transição nunca é
silenciosa. Ver `E3_6_LIB06_PROVENANCE_ACCESSIBILITY.md`.
"""

from app.cognitive.errors.exceptions import AccessibilityInvalidTransitionError
from app.cognitive.models.cognitive_object import CognitiveObject
from app.cognitive.models.enums import AccessibilityState
from app.cognitive.repositories.object_repository import ObjectRepository


class AccessibilityManager:
    """Único caminho sancionado para alterar `AccessibilityState` de
    um `CognitiveObject` — nunca um efeito colateral de outra
    operação/consulta.

    Depende apenas de `ObjectRepository` — reaproveita
    `refresh_for_update` (E3.3.1) como defesa razoável contra
    concorrência (nenhum invariante formal do tipo "no máximo 1"
    existe para `AccessibilityState` nesta fase — diferente de CLID/
    CURRENT — mas a mesma técnica evita anomalias de leitura-decide-
    escreve sem custo adicional relevante).
    """

    def __init__(self, object_repository: ObjectRepository) -> None:
        self._objects = object_repository

    def get_state(self, obj: CognitiveObject) -> AccessibilityState:
        """Leitura simples do estado atual."""
        return obj.accessibility

    def transition(
        self,
        obj: CognitiveObject,
        target_state: AccessibilityState,
        *,
        reason: str | None = None,
    ) -> CognitiveObject:
        """Transiciona `obj.accessibility` para `target_state`.

        Idempotente: `target_state == obj.accessibility` é um no-op
        (não bloqueia, não exige `reason`).

        `target_state == CAUSALLY_EXTINCT` exige `reason` não-vazio —
        `AccessibilityInvalidTransitionError` (`PIA-8018`) caso
        contrário. Nenhuma outra transição é restrita nesta fase (ver
        docstring do módulo — a matriz completa de autoridade é `E4`).

        Não commita — `flush()` implícito via `ObjectRepository.update()`;
        commit permanece do chamador via `UnitOfWork`.
        """
        self._objects.refresh_for_update(obj)

        if target_state == obj.accessibility:
            return obj

        if target_state == AccessibilityState.CAUSALLY_EXTINCT and not reason:
            raise AccessibilityInvalidTransitionError(coid=obj.id)

        obj.accessibility = target_state
        return self._objects.update(obj)

    def assert_accessible(self, obj: CognitiveObject) -> None:
        """Levanta `ValueError` se `obj` não estiver em um estado
        operacionalmente acessível (`ACTIVE`/`LATENT`) — validação de
        leitura simples, sem efeito colateral. `ValueError` (não um
        `PIA-8xxx` novo) por ser uma checagem de precondição de
        chamador, mesma convenção já usada para argumentos inválidos
        em outros módulos (`CoidManager.generate_unique`,
        `VersionManager.derive`)."""
        if obj.accessibility not in (AccessibilityState.ACTIVE, AccessibilityState.LATENT):
            raise ValueError(
                f"CognitiveObject {obj.id} não está acessível "
                f"(accessibility={obj.accessibility})."
            )
