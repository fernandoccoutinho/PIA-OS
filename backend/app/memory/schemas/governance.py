"""
Regras e decisões de governança — value objects tipados (E4.3).

A forma de `rules` **não** foi congelada pela E4.0, e a Stop Condition
12 nomeia o risco: escolher motor de policy por conveniência
tecnológica. OPA/Rego, Cedar, DSL própria e JSON arbitrário ficam
fora — não por serem ruins, mas porque escolher a ferramenta antes de
saber quais decisões precisam ser expressas é deixar a ferramenta
definir a semântica.

A representação adotada é **tipada, mínima e determinística**: uma
regra declara a que se aplica (conjunção de dimensões) e o que
resulta. Sem negação, sem operadores aninhados, sem expressões —
porque nada nos requisitos pede isso, e cada construto a mais seria
um motor inventado por antecipação. Quando E4.6/E4.7/E4.9 mostrarem
falta de expressividade, ela entra com o caso de uso na mão; o
caminho inverso não tem volta.
"""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from app.memory.models.governance_enums import (
    CognitiveOperation,
    GovernanceEffect,
    GovernanceOutcome,
)


def _frozen_strings(name: str, value: object) -> frozenset[str]:
    """Normaliza um conjunto de textos, rejeitando branco e tipo errado.

    Mesma disciplina de `MemoryContext` após `E4.2.1`: os invariantes
    valem em toda construção, e valor inválido (`ValueError`) e tipo
    inválido (`TypeError`) permanecem diagnósticos distintos.
    """
    if isinstance(value, str | bytes) or not isinstance(value, Iterable):
        raise TypeError(f"{name} deve ser um iterável de str, recebido {type(value).__name__}")
    itens = tuple(value)
    if any(not isinstance(item, str) for item in itens):
        raise TypeError(f"{name} aceita apenas str")
    if any(not item.strip() for item in itens):
        raise ValueError(f"{name} não aceita entradas vazias ou apenas espaços")
    return frozenset(itens)


@dataclass(frozen=True)
class GovernanceRule:
    """Uma regra: a que se aplica, e o que resulta.

    Cada dimensão é um conjunto; **dimensão vazia significa "não
    restringe por esta dimensão"**, não "não casa com nada". A
    aplicabilidade é a **conjunção** das dimensões informadas.

    A escolha do vazio-como-curinga é o que permite escrever
    "qualquer ator, no domínio D, para leitura" sem enumerar atores —
    e é determinística: `matches()` não tem ramo implícito.
    """

    rule_id: str
    """Identificador estável, citado na decisão como fundamento.

    Estável é o ponto: é ele que permite responder, meses depois, qual
    regra fundamentou uma decisão registrada em outro lugar.
    """

    effect: GovernanceEffect
    operations: frozenset[CognitiveOperation] = field(default_factory=frozenset)
    domain_ids: frozenset[uuid.UUID] = field(default_factory=frozenset)
    actor_refs: frozenset[str] = field(default_factory=frozenset)
    purposes: frozenset[str] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        """Impõe os invariantes em **toda** construção pública.

        Lição direta de `E4.2.1`: `frozen=True` protege a referência,
        não o conteúdo, e invariantes que vivem só num construtor de
        conveniência são contornáveis pelo construtor direto. Aqui
        eles vivem no único ponto por onde tudo passa.
        """
        if not isinstance(self.rule_id, str):
            raise TypeError(f"rule_id deve ser str, recebido {type(self.rule_id).__name__}")
        if not self.rule_id.strip():
            raise ValueError("rule_id não pode ser vazio ou apenas espaços")
        if not isinstance(self.effect, GovernanceEffect):
            raise TypeError("effect deve ser um GovernanceEffect")

        operacoes = self.operations
        if isinstance(operacoes, str | bytes) or not isinstance(operacoes, Iterable):
            raise TypeError("operations deve ser um iterável de CognitiveOperation")
        itens = tuple(operacoes)
        if any(not isinstance(item, CognitiveOperation) for item in itens):
            raise TypeError("operations aceita apenas CognitiveOperation")
        object.__setattr__(self, "operations", frozenset(itens))

        dominios = self.domain_ids
        if isinstance(dominios, str | bytes) or not isinstance(dominios, Iterable):
            raise TypeError("domain_ids deve ser um iterável de uuid.UUID")
        ids = tuple(dominios)
        if any(not isinstance(item, uuid.UUID) for item in ids):
            raise TypeError("domain_ids aceita apenas uuid.UUID")
        object.__setattr__(self, "domain_ids", frozenset(ids))

        object.__setattr__(self, "actor_refs", _frozen_strings("actor_refs", self.actor_refs))
        object.__setattr__(self, "purposes", _frozen_strings("purposes", self.purposes))

    def matches(
        self,
        *,
        operation: CognitiveOperation,
        domain_ids: frozenset[uuid.UUID],
        actor_ref: str | None,
        purpose: str | None,
    ) -> bool:
        """A regra se aplica a esta operação neste contexto?

        Conjunção das dimensões declaradas. Duas decisões que merecem
        registro:

        - **domínios casam por interseção**, não por igualdade: um
          contexto que declara `{D1, D2}` casa com uma regra sobre
          `{D1}`. Exigir igualdade tornaria as regras inutilizáveis
          para qualquer contexto multi-domínio, e a E4.2 congelou que
          contexto apenas *declara* o conjunto;
        - **dimensão ausente no contexto não casa com regra que a
          restringe**: uma regra sobre `actor_refs={"ana"}` não se
          aplica a um contexto sem `actor_ref`. O contrário faria
          ausência de informação valer como informação — e a ausência
          de ator é exatamente o caso em que não se deve concluir
          nada.
        """
        if self.operations and operation not in self.operations:
            return False
        if self.domain_ids and not (self.domain_ids & domain_ids):
            return False
        if self.actor_refs and (actor_ref is None or actor_ref not in self.actor_refs):
            return False
        return not (self.purposes and (purpose is None or purpose not in self.purposes))

    def sort_key(self) -> tuple[str, str]:
        """Chave de ordenação canônica — determinismo da avaliação.

        Ordena por efeito e depois por `rule_id`, o que torna a regra
        citada como fundamento reproduzível entre execuções e entre
        instâncias.
        """
        return (self.effect.value, self.rule_id)


@dataclass(frozen=True)
class GovernanceDecision:
    """Resultado explicável de uma avaliação. **Não persistido.**

    Value object transitório, como `IntegrityFinding` (E3.10) e
    `SyncReport` (E3.11), e pela mesma razão: uma decisão é resultado
    **datado** de uma avaliação contra uma **versão** de policy.
    Persisti-la criaria a tentação de tratá-la como fato estabelecido,
    quando ela é derivável de novo a qualquer momento a partir da
    policy e do contexto.

    A decisão carrega o que a torna auditável: qual policy, qual
    versão, qual operação, quais dimensões do contexto e qual regra
    fundamentou.
    """

    outcome: GovernanceOutcome
    operation: CognitiveOperation
    policy_key: str
    policy_version: int
    policy_id: uuid.UUID
    context_domain_ids: tuple[uuid.UUID, ...] = ()
    context_actor_ref: str | None = None
    context_purpose: str | None = None
    matched_rule_id: str | None = None
    """Regra que fundamentou o resultado.

    `None` quando o resultado é `NOT_APPLICABLE` — e a ausência aqui é
    informativa, não uma lacuna: significa literalmente que nenhuma
    regra da versão avaliada se aplicava.
    """

    reason: str = ""
    """Fundamento em texto, para quem lê o resultado sem o código à
    mão. Descritivo; nunca é o que a máquina consome."""

    @property
    def is_admissible(self) -> bool:
        """Somente `ADMISSIBLE` admite.

        `NOT_APPLICABLE` **não concede** — ausência de regra não é
        permissão. A propriedade existe justamente para que nenhum
        chamador precise reimplementar essa distinção e errar nela.
        """
        return self.outcome is GovernanceOutcome.ADMISSIBLE

    @property
    def implies_nonexistence(self) -> bool:
        """Sempre `False`, e existe para dizer isso explicitamente.

        ```
        DENIED       != NONEXISTENT
        INACCESSIBLE != NONEXISTENT
        ```

        Uma decisão negativa afirma que a operação não é admissível
        naquele contexto — nada sobre o patrimônio existir. Deixar
        isso implícito seria confiar em que todo consumidor futuro
        chegue sozinho à mesma conclusão.
        """
        return False


@dataclass(frozen=True)
class GovernanceResolution:
    """Resolução completa: fronteira de plataforma + policy local.

    Imutável e **transitória**, como `GovernanceDecision`,
    `IntegrityFinding` (E3.10) e `SyncReport` (E3.11).

    `declared_preservations` e `declared_losses` reaproveitam
    deliberadamente o vocabulário de `TransformationRecord` (E3.4):
    quando algo é bloqueado, declarar **o que se preservou e o que se
    perdeu** é a mesma disciplina que a E3 aplica a transformações —
    uma resolução que não declara perda afirma não ter perdido nada, o
    que é quase sempre falso.

    A resolução registra as **capacidades** bloqueadas, do vocabulário
    fechado, e nunca o conteúdo do pedido: o corretivo exige tanto
    oferecer alternativa quanto não conservar detalhe operacional
    nocivo desnecessário.
    """

    outcome: GovernanceOutcome
    operation: CognitiveOperation
    safety_boundary_version: int
    safety_rationale: str = ""
    blocked_capabilities: tuple[Any, ...] = ()
    preserved_intent: str | None = None
    admissible_alternatives: tuple[str, ...] = ()
    constraints: tuple[str, ...] = ()
    declared_preservations: tuple[str, ...] = ()
    declared_losses: tuple[str, ...] = ()
    policy_key: str | None = None
    policy_version: int | None = None
    policy_id: uuid.UUID | None = None
    matched_rule_id: str | None = None
    policy_rationale: str = ""

    @property
    def execution_authorized(self) -> bool:
        """`True` **somente** em `ADMISSIBLE`.

        Nem `NOT_APPLICABLE`, nem `PROHIBITED`, nem a existência de
        alternativas autorizam coisa alguma:

            REDIRECTION != AUTHORIZATION

        Oferecer um caminho seguro não libera o caminho recusado, e a
        propriedade existe para que nenhum chamador precise
        reimplementar essa distinção e errar nela.
        """
        return self.outcome is GovernanceOutcome.ADMISSIBLE

    @property
    def prohibited_by_platform(self) -> bool:
        """Recusado pela fronteira — irreversível por policy local."""
        return self.outcome is GovernanceOutcome.PROHIBITED

    @property
    def implies_nonexistence(self) -> bool:
        """Sempre `False`, dito explicitamente.

        ```
        DENIED       != NONEXISTENT
        PROHIBITED   != NONEXISTENT
        ```
        """
        return False
