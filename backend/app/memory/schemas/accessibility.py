"""
Contratos transitórios da política de acessibilidade (`E4.7`).

Três coisas distintas, deliberadamente **não** fundidas:

```text
GovernanceResolution           autoridade geral resolvida (E4.3)
AccessibilityDecision          policy de estado/transição (E4.7)
AccessibilityTransitionResult  efeito observado da execução (E4.7)
```

Fundi-las produziria um objeto que afirma ao mesmo tempo "foi
autorizado", "a policy admite" e "o patrimônio mudou" — três fatos com
fontes diferentes, que podem divergir, e cuja divergência é exatamente o
que o caminho canônico precisa detectar.

Invariantes vivem em `__post_init__`, não em docstring — sexta vez que o
projeto aplica a lição (E4.2.1, E4.3.2, E4.4.1, E3.4.2.1, E4.5.1,
E4.6.1):

```text
frozen=True ALONE != DEEP IMMUTABILITY
```
"""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass

from app.memory.models.governance_enums import GovernanceEffect, GovernanceOutcome
from app.memory.schemas.governance import GovernanceResolution
from app.memory.schemas.memory_context import MemoryContext

ACCESSIBILITY_STATE_TOKENS: frozenset[str] = frozenset(
    {"active", "latent", "inaccessible", "causally_extinct"}
)
"""Vocabulário completo de `AccessibilityState`, **exatamente como a E3
persiste**.

Minúsculos porque a E3.1 mapeia o enum com `values_callable`, gravando o
`.value`. Comparação por igualdade exata — nenhum `lower()`, `upper()`
ou `casefold()`, mesma disciplina congelada na E4.5.1 para `qualifier` e
na E4.6 para os tokens da vista.

    TOKEN BRIDGE != DOMAIN ENUM OWNERSHIP
    E3 REMAINS SOURCE OF TRUTH FOR ACCESSIBILITY STATE

A E4.7 **não** cria um segundo estado nem duplica o enum: ela transporta
o token que a E3 já persiste, para poder falar de estados sem importar
`app.cognitive`.
"""

CAUSALLY_EXTINCT_TOKEN = "causally_extinct"
"""Único destino que exige evidência causal verificada.

    CAUSAL EVENT ID != CAUSAL EVIDENCE UNTIL SUBJECT MEMBERSHIP IS VERIFIED
"""


def _tokens(campo: str, valor: object) -> frozenset[str]:
    """Converte uma coleção de tokens de estado em `frozenset` validado.

    `str` e `bytes` são recusados: ambos são iteráveis, e aceitá-los
    transformaria `"active"` num conjunto de caracteres em vez de erro.
    """
    # `isinstance(..., Iterable)` em vez de `hasattr(valor, "__iter__")`:
    # a E4.6.2 congelou que reflexão não é atalho aceitável, nem em
    # validação defensiva. `str` e `bytes` são iteráveis e continuam
    # recusados — aceitá-los transformaria `"active"` num conjunto de
    # caracteres em vez de erro.
    if isinstance(valor, str | bytes) or not isinstance(valor, Iterable):
        raise TypeError(
            f"{campo} deve ser uma coleção de tokens de estado, " f"recebido {type(valor).__name__}"
        )
    itens = frozenset(valor)
    for item in itens:
        if not isinstance(item, str):
            raise TypeError(f"{campo} aceita apenas str, recebido {type(item).__name__}")
        if item not in ACCESSIBILITY_STATE_TOKENS:
            raise ValueError(
                f"{campo} contém {item!r}, fora do vocabulário da E3 "
                f"{sorted(ACCESSIBILITY_STATE_TOKENS)}"
            )
    if not itens:
        raise ValueError(
            f"{campo} não pode ser vazio — dimensão vazia numa regra de transição "
            "seria curinga silencioso, e o projeto já pagou por isso na E4.3.3"
        )
    return itens


@dataclass(frozen=True)
class AccessibilityRule:
    """Regra mínima de transição: de quais estados, para quais estados.

    **Ator, propósito e domínio não estão aqui**, e a ausência é
    deliberada: essas dimensões pertencem ao `MemoryContext` (E4.2) e à
    Governança (E4.3), que já as avalia. Copiá-las para cá duplicaria o
    motor da E4.3 e criaria duas respostas possíveis para a mesma
    pergunta.

    **Nenhuma dimensão é opcional.** Na E4.3, conjunto vazio significa
    curinga — e a E4.3.3 mostrou o custo disso quando o vocabulário
    cresce. Aqui, `source_states` e `target_states` são obrigatórios e
    não vazios: uma regra de transição precisa dizer *de onde* e *para
    onde*, senão não é uma regra de transição.
    """

    rule_id: str
    effect: GovernanceEffect
    source_states: frozenset[str]
    target_states: frozenset[str]

    def __post_init__(self) -> None:
        if not isinstance(self.rule_id, str):
            raise TypeError(f"rule_id deve ser str, recebido {type(self.rule_id).__name__}")
        if not self.rule_id.strip():
            raise ValueError("rule_id não pode ser vazio")
        if not isinstance(self.effect, GovernanceEffect):
            raise TypeError(
                f"effect deve ser GovernanceEffect, recebido {type(self.effect).__name__}"
            )
        object.__setattr__(self, "source_states", _tokens("source_states", self.source_states))
        object.__setattr__(self, "target_states", _tokens("target_states", self.target_states))

    def matches(self, *, source_state: str, target_state: str) -> bool:
        """A regra se aplica a esta transição?

        Conjunção simples e por igualdade exata. Sem curinga, sem
        normalização.
        """
        return source_state in self.source_states and target_state in self.target_states

    def sort_key(self) -> tuple[str, str]:
        """Ordenação canônica para serialização determinística."""
        return (self.effect.value, self.rule_id)


@dataclass(frozen=True)
class AccessibilityDecision:
    """O que a policy diz sobre uma transição — e por quê.

    Explicável por construção: carrega policy, versão, regra, estado de
    origem e estado-alvo. Uma decisão que não explica seu fundamento
    seria indistinguível de uma opinião.

    Precedência, idêntica à da E4.3 e pelo mesmo motivo:

    ```text
    DENY_OVERRIDES
    NO_MATCH = NOT_APPLICABLE
    NOT_APPLICABLE DOES NOT AUTHORIZE
    ```

    Restrição que some porque outra regra permite não é restrição.
    """

    outcome: GovernanceOutcome
    source_state: str
    target_state: str
    policy_key: str | None = None
    policy_version: int | None = None
    matched_rule_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, GovernanceOutcome):
            raise TypeError(
                f"outcome deve ser GovernanceOutcome, recebido {type(self.outcome).__name__}"
            )
        for campo, valor in (
            ("source_state", self.source_state),
            ("target_state", self.target_state),
        ):
            if not isinstance(valor, str):
                raise TypeError(f"{campo} deve ser str, recebido {type(valor).__name__}")
            if valor not in ACCESSIBILITY_STATE_TOKENS:
                raise ValueError(
                    f"{campo} {valor!r} está fora do vocabulário da E3 "
                    f"{sorted(ACCESSIBILITY_STATE_TOKENS)}"
                )
        if self.outcome is GovernanceOutcome.PROHIBITED:
            raise ValueError(
                "PROHIBITED pertence à fronteira de segurança da plataforma, não a uma "
                "policy local de acessibilidade — a E4.7 não a produz"
            )

        # Identidade de policy é tudo-ou-nada, como na E4.3.2:
        # proveniência parcial parece proveniência.
        identidade = (self.policy_key, self.policy_version)
        if any(x is None for x in identidade) and any(x is not None for x in identidade):
            raise ValueError(
                "policy_key e policy_version são tudo-ou-nada — identidade parcial "
                "parece identidade"
            )
        if self.matched_rule_id is not None and self.policy_key is None:
            raise ValueError("citar uma regra exige citar a policy que a contém")
        if self.outcome is GovernanceOutcome.NOT_APPLICABLE and self.matched_rule_id is not None:
            raise ValueError(
                "NOT_APPLICABLE significa que nenhuma regra se aplicou; citar uma regra "
                "contradiz o desfecho"
            )
        if self.outcome is not GovernanceOutcome.NOT_APPLICABLE and self.matched_rule_id is None:
            raise ValueError(
                f"{self.outcome} nasce de uma regra que casou; sem regra citada a "
                "decisão não é explicável"
            )

    @property
    def is_admissible(self) -> bool:
        """Só `ADMISSIBLE` admite.

        Derivado, nunca armazenado em paralelo: uma cópia poderia
        divergir do `outcome`, e a autoridade é o `outcome`.

            NOT_APPLICABLE DOES NOT AUTHORIZE
        """
        return self.outcome is GovernanceOutcome.ADMISSIBLE


@dataclass(frozen=True)
class AccessibilityTransitionResult:
    """Efeito **observado** de uma solicitação de transição.

    Distinto da decisão: a decisão diz o que a policy admite, este
    objeto diz o que de fato aconteceu no patrimônio — inclusive quando
    nada aconteceu.

    Três desfechos que **não** colapsam:

    ```text
    governança recusou   → decision is None,  no_change False
    alvo == atual        → decision is None,  no_change True
    policy avaliou       → decision presente, no_change False
    ```

    O no-op não consulta a policy: não há transição a admitir, e
    avaliá-la produziria uma admissão — ou uma recusa — sobre algo que
    não vai acontecer.

        NO_CHANGE != POLICY ADMISSION
        NO_CHANGE != POLICY REFUSAL
    """

    coid: uuid.UUID
    context: MemoryContext
    governance_resolution: GovernanceResolution
    decision: AccessibilityDecision | None
    observed_state: str
    state_changed: bool
    no_change: bool = False
    causal_event_id: uuid.UUID | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.coid, uuid.UUID):
            raise TypeError(f"coid deve ser uuid.UUID, recebido {type(self.coid).__name__}")
        if not isinstance(self.context, MemoryContext):
            raise TypeError(
                f"context deve ser MemoryContext, recebido {type(self.context).__name__}"
            )
        if not isinstance(self.governance_resolution, GovernanceResolution):
            raise TypeError(
                "governance_resolution deve ser GovernanceResolution, recebido "
                f"{type(self.governance_resolution).__name__}"
            )
        if self.decision is not None and not isinstance(self.decision, AccessibilityDecision):
            raise TypeError(
                f"decision deve ser AccessibilityDecision ou None, recebido "
                f"{type(self.decision).__name__}"
            )
        if not isinstance(self.observed_state, str):
            raise TypeError(
                f"observed_state deve ser str, recebido {type(self.observed_state).__name__}"
            )
        if self.observed_state not in ACCESSIBILITY_STATE_TOKENS:
            raise ValueError(
                f"observed_state {self.observed_state!r} está fora do vocabulário da E3"
            )
        # Acesso direto, sem `getattr`: a E4.6.2 congelou que reflexão
        # não é atalho aceitável nem em validação defensiva.
        if not isinstance(self.state_changed, bool):
            raise TypeError(
                f"state_changed deve ser bool, recebido {type(self.state_changed).__name__}"
            )
        if not isinstance(self.no_change, bool):
            raise TypeError(f"no_change deve ser bool, recebido {type(self.no_change).__name__}")
        if self.state_changed and self.no_change:
            raise ValueError("state_changed e no_change são mutuamente exclusivos")
        if self.causal_event_id is not None and not isinstance(self.causal_event_id, uuid.UUID):
            raise TypeError(
                "causal_event_id deve ser uuid.UUID ou None, recebido "
                f"{type(self.causal_event_id).__name__}"
            )

        if not self.governance_resolution.execution_authorized:
            if self.decision is not None:
                raise ValueError(
                    "sem autorização de governança a policy sequer é avaliada; carregar "
                    "uma decisão afirmaria uma avaliação que não ocorreu"
                )
            if self.state_changed or self.no_change:
                raise ValueError(
                    "governança não autorizou, então nem escrita nem no-op de policy "
                    "podem ter ocorrido — a recusa é anterior a olhar o sujeito"
                )
        if self.no_change:
            # Same-state não consulta a policy: não há transição a
            # admitir, e avaliá-la produziria uma admissão (ou uma
            # recusa) sobre algo que não vai acontecer.
            #
            #     NO_CHANGE != POLICY ADMISSION
            #     NO_CHANGE != POLICY REFUSAL
            if self.decision is not None:
                raise ValueError("no-op não fabrica decisão de policy: não há mudança a admitir")
            if self.causal_event_id is not None:
                raise ValueError(
                    "no-op não fabrica evidência causal — inclusive para um objeto que "
                    "já está causally_extinct"
                )
        if self.state_changed:
            if self.decision is None or not self.decision.is_admissible:
                raise ValueError(
                    "estado só muda sob decisão ADMISSIBLE — mudança sem admissão é "
                    "escrita sem autoridade"
                )
            if self.observed_state != self.decision.target_state:
                raise ValueError(
                    f"estado observado {self.observed_state!r} difere do alvo autorizado "
                    f"{self.decision.target_state!r} — a pós-condição não confirma a "
                    "transição"
                )
            if (
                self.decision.target_state == CAUSALLY_EXTINCT_TOKEN
                and self.causal_event_id is None
            ):
                raise ValueError(
                    "extinção causal exige evidência causal verificada; sem ela o "
                    "resultado afirmaria uma extinção sem fundamento"
                )

    @property
    def policy_evaluated(self) -> bool:
        """A policy chegou a ser consultada?

        `False` em dois casos distintos, que o resultado mantém
        separados: governança recusou antes de olhar o sujeito, ou o
        alvo já era o estado atual.
        """
        return self.decision is not None
