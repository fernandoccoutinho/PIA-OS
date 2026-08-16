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
from datetime import UTC, datetime

from app.memory.models.governance_enums import (
    CognitiveOperation,
    GovernanceEffect,
    GovernanceOutcome,
)
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
    if len(itens) != 1:
        # Corretivo E4.7.1: exatamente UMA aresta por regra.
        #
        # A versão anterior aceitava conjuntos, e uma única regra com
        # duas origens e dois destinos autorizava quatro transições —
        # um produto cartesiano que ninguém declarou.
        #
        #     ONE TRANSITION RULE = ONE EXACT EDGE
        #
        # Vazio continua recusado pelo mesmo motivo de antes: dimensão
        # vazia seria curinga silencioso, e a E4.3.3 mostrou o custo
        # disso. O nome plural do campo é mantido apenas por
        # compatibilidade com o JSON já publicado.
        raise ValueError(
            f"{campo} deve conter exatamente um token, recebido {len(itens)}: "
            f"{sorted(itens)} — uma regra descreve UMA aresta de transição, e "
            "conjuntos produziriam um produto cartesiano não declarado"
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
    evaluated_at: datetime
    policy_key: str | None = None
    policy_version: int | None = None
    governance_policy_key: str | None = None
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
        if not isinstance(self.evaluated_at, datetime):
            raise TypeError(
                f"evaluated_at deve ser datetime, recebido {type(self.evaluated_at).__name__}"
            )
        if self.evaluated_at.tzinfo is None:
            raise ValueError(
                "evaluated_at deve ser timezone-aware: um instante ingênuo daria "
                "resultado dependente do fuso da máquina"
            )
        # Canonicalizado para UTC: dois instantes iguais em fusos
        # diferentes precisam produzir a mesma decisão, com o mesmo hash.
        object.__setattr__(self, "evaluated_at", self.evaluated_at.astimezone(UTC))
        if self.outcome is GovernanceOutcome.PROHIBITED:
            raise ValueError(
                "PROHIBITED pertence à fronteira de segurança da plataforma, não a uma "
                "policy local de acessibilidade — a E4.7 não a produz"
            )

        # Forma antes de presença (corretivo E4.7.2): o teste
        # tudo-ou-nada verificava se os campos estavam presentes, não se
        # eram utilizáveis. `policy_key=123` passava.
        #
        #     MALFORMED PROVENANCE IS NOT PROVENANCE
        for nome, bruto in (
            ("policy_key", self.policy_key),
            ("governance_policy_key", self.governance_policy_key),
            ("matched_rule_id", self.matched_rule_id),
        ):
            if bruto is None:
                continue
            if not isinstance(bruto, str):
                raise TypeError(f"{nome} deve ser str, recebido {type(bruto).__name__}")
            if not bruto.strip():
                raise ValueError(f"{nome}, quando presente, não pode ser vazio")
        if self.policy_version is not None:
            # `bool` é subclasse de `int`; aceitá-lo faria `True` virar
            # versão 1 em silêncio.
            if not isinstance(self.policy_version, int) or isinstance(self.policy_version, bool):
                raise TypeError(
                    "policy_version deve ser int, recebido " f"{type(self.policy_version).__name__}"
                )
            if self.policy_version < 1:
                raise ValueError("policy_version deve ser >= 1")

        # Identidade de policy é tudo-ou-nada, como na E4.3.2:
        # proveniência parcial parece proveniência. A partir do
        # corretivo E4.7.1, `governance_policy_key` entra nessa
        # identidade: uma decisão que não diz sob qual autoridade
        # operou não é explicável.
        identidade = (self.policy_key, self.policy_version, self.governance_policy_key)
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
    requested_target_state: str
    observed_state: str | None
    state_changed: bool
    evaluated_at: datetime
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
        if not isinstance(self.requested_target_state, str):
            raise TypeError(
                "requested_target_state deve ser str, recebido "
                f"{type(self.requested_target_state).__name__}"
            )
        if self.requested_target_state not in ACCESSIBILITY_STATE_TOKENS:
            raise ValueError(
                f"requested_target_state {self.requested_target_state!r} está fora do "
                "vocabulário da E3"
            )
        # `observed_state` é `None` quando NENHUMA observação ocorreu
        # (corretivo E4.7.1). A versão anterior preenchia com o alvo
        # pedido sob recusa de governança, afirmando um estado que
        # ninguém leu:
        #
        #     TARGET STATE != OBSERVED STATE
        #     OBSERVED STATE REQUIRES AN OBSERVATION
        if self.observed_state is not None:
            if not isinstance(self.observed_state, str):
                raise TypeError(
                    "observed_state deve ser str ou None, recebido "
                    f"{type(self.observed_state).__name__}"
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

        if not isinstance(self.evaluated_at, datetime):
            raise TypeError(
                f"evaluated_at deve ser datetime, recebido {type(self.evaluated_at).__name__}"
            )
        if self.evaluated_at.tzinfo is None:
            raise ValueError("evaluated_at deve ser timezone-aware")
        object.__setattr__(self, "evaluated_at", self.evaluated_at.astimezone(UTC))

        if self.governance_resolution.operation is not CognitiveOperation.ACCESSIBILITY_TRANSITION:
            raise ValueError(
                f"a resolução é sobre {self.governance_resolution.operation}; um "
                "resultado de transição de acessibilidade exige autoridade sobre "
                "ACCESSIBILITY_TRANSITION"
            )

        if self.decision is not None:
            if self.decision.target_state != self.requested_target_state:
                raise ValueError(
                    f"a decisão autoriza {self.decision.target_state!r}, mas o pedido "
                    f"é sobre {self.requested_target_state!r} — apresentar uma como "
                    "resposta à outra troca o objeto da autorização"
                )
            if self.decision.evaluated_at != self.evaluated_at:
                raise ValueError(
                    "decisão e resultado citam instantes diferentes; uma operação tem "
                    "UM instante de avaliação"
                )
            if (
                self.decision.governance_policy_key is not None
                and self.decision.governance_policy_key != self.governance_resolution.policy_key
            ):
                raise ValueError(
                    f"a decisão operou sob {self.decision.governance_policy_key!r}, mas "
                    f"a autoridade resolvida é {self.governance_resolution.policy_key!r}"
                )

        self._validar_desfecho()

    def _validar_desfecho(self) -> None:
        """Máquina de estados **exaustiva** (corretivo E4.7.2).

        A versão anterior impunha invariantes ponto a ponto, e toda
        combinação não prevista passava: autorizado sem decisão nem
        no-op, no-op contradizendo o alvo, evidência causal num desfecho
        que não a usou.

            FROZEN DATACLASS != VALID STATE MACHINE
            RESULT OBJECT MUST NOT REPRESENT AN IMPOSSIBLE HISTORY

        São exatamente **quatro** desfechos possíveis. Nenhum quinto é
        construível.
        """
        autorizado = self.governance_resolution.execution_authorized

        # 1. Governança recusou — nada foi lido, nada foi avaliado.
        if not autorizado:
            if self.decision is not None:
                raise ValueError(
                    "sem autorização de governança a policy sequer é avaliada; carregar "
                    "uma decisão afirmaria uma avaliação que não ocorreu"
                )
            if self.observed_state is not None:
                raise ValueError(
                    "sob recusa de governança o sujeito não é lido; um observed_state "
                    "afirmaria uma observação que não ocorreu"
                )
            if self.state_changed or self.no_change:
                raise ValueError(
                    "governança não autorizou, então nem escrita nem no-op podem ter "
                    "ocorrido — a recusa é anterior a olhar o sujeito"
                )
            if self.causal_event_id is not None:
                raise ValueError(
                    "recusa de governança não consulta evidência causal; citá-la "
                    "apresentaria uma evidência real como fundamento de uma operação "
                    "à qual ela não pertence"
                )
            return

        if self.observed_state is None:
            raise ValueError(
                "com governança autorizada o sujeito é lido sob lock, então "
                "observed_state não pode ser None"
            )

        # 2. No-op sob lock — a policy não é consultada.
        if self.no_change:
            if self.decision is not None:
                raise ValueError("no-op não fabrica decisão de policy: não há mudança a admitir")
            if self.observed_state != self.requested_target_state:
                raise ValueError(
                    f"no-op significa que o estado observado ({self.observed_state!r}) "
                    f"já é o alvo pedido ({self.requested_target_state!r})"
                )
            if self.causal_event_id is not None:
                raise ValueError(
                    "no-op não fabrica evidência causal — inclusive para um objeto que "
                    "já está causally_extinct"
                )
            return

        # Autorizado, sem no-op: a policy TEM de ter sido avaliada. Era
        # esta lacuna que permitia um resultado autorizado sem desfecho
        # semântico algum.
        if self.decision is None:
            raise ValueError(
                "resultado autorizado sem decisão só é possível como no-op; sem "
                "no_change, a policy foi necessariamente avaliada"
            )

        # 3. Policy avaliou e não admitiu — nenhuma escrita.
        if not self.decision.is_admissible:
            if self.state_changed:
                raise ValueError(
                    "estado só muda sob decisão ADMISSIBLE — mudança sem admissão é "
                    "escrita sem autoridade"
                )
            if self.observed_state != self.decision.source_state:
                raise ValueError(
                    f"sem escrita, o estado observado ({self.observed_state!r}) é o de "
                    f"origem da decisão ({self.decision.source_state!r})"
                )
            if self.causal_event_id is not None:
                raise ValueError(
                    "recusa da policy não verifica evidência causal; citá-la seria "
                    "apresentá-la como fundamento de uma operação que não ocorreu"
                )
            return

        # 4. Policy admitiu e a E3 escreveu.
        if not self.state_changed:
            raise ValueError(
                "decisão ADMISSIBLE sem no-op descreve uma escrita; state_changed=False "
                "afirmaria autorização sem efeito"
            )
        if self.observed_state != self.requested_target_state:
            raise ValueError(
                f"estado observado {self.observed_state!r} difere do alvo autorizado "
                f"{self.requested_target_state!r} — a pós-condição não confirma a "
                "transição"
            )
        if self.requested_target_state == CAUSALLY_EXTINCT_TOKEN:
            if self.causal_event_id is None:
                raise ValueError(
                    "extinção causal exige evidência causal verificada; sem ela o "
                    "resultado afirmaria uma extinção sem fundamento"
                )
        elif self.causal_event_id is not None:
            raise ValueError(
                f"o alvo {self.requested_target_state!r} não é extinção causal; citar "
                "evidência causal aqui a apresentaria como fundamento de uma operação "
                "à qual ela não pertence"
            )

    @property
    def policy_evaluated(self) -> bool:
        """A policy chegou a ser consultada?

        `False` em dois casos distintos, que o resultado mantém
        separados: governança recusou antes de olhar o sujeito, ou o
        alvo já era o estado atual.
        """
        return self.decision is not None
