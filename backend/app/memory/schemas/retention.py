"""
Regra de retenção — value object tipado (`E4.9.6`).

A E4.0 chamou isto de `scope_spec` + `duration_spec` +
`on_expiry_action` e deixou a forma em aberto. Esta fatia fecha a
forma **com tipos**, seguindo o precedente de `GovernanceRule`: nada
de JSON arbitrário como contrato de domínio, nada de motor de policy
escolhido por conveniência.

A regra é deliberadamente pobre. Não filtra por tamanho, extensão,
pasta, uso recente, conversa, projeto, legado ou estado de validação —
e não porque essas dimensões sejam irrelevantes, mas porque os
schemas que as sustentariam **não existem**. Uma regra que citasse
`VALIDATED_CURRENT` hoje citaria algo que o `RevisionStatus` não tem.

```text
RETENTION_POLICY != USER_DECISION
POLICY_MATCH != DELETION_CANDIDATE_CONFIRMED
```

Uma regra que "casa" com um item torna esse item elegível a uma
avaliação futura. Não o seleciona, não o marca e não o condena.
"""

import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field

from app.memory.models.retention_enums import (
    RetentionAnchor,
    RetentionExpiryAction,
    RetentionScopeKind,
)

MAX_RULE_ID_LENGTH = 256
"""Teto do `rule_id`, alinhado ao limite das strings opacas da E4.9.5.

Um identificador de regra não precisa de mais que isso, e um campo sem
teto vira, com o tempo, o lugar onde alguém escreve uma explicação.
"""


def _inteiro_real(nome: str, valor: object) -> int:
    """Exige `int` verdadeiro — `bool` é recusado.

    `bool` é subclasse de `int` em Python, então `isinstance(True, int)`
    é `True` e `minimum_age_days=True` viraria silenciosamente **um
    dia**. A mesma armadilha já apareceu na E4.6.3, onde o gate usava
    `type(x) is not bool` justamente por isso.
    """
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise TypeError(f"{nome} deve ser int, recebido {type(valor).__name__}")
    return valor


@dataclass(frozen=True)
class RetentionRule:
    """A que patrimônio se aplica, a partir de quando, e o que resulta.

    Invariantes vivem em `__post_init__`, não em docstring — oitava vez
    que o projeto aplica a lição (E4.2.1, E4.3.2, E4.4.1, E3.4.2.1,
    E4.5.1, E4.6.1, E4.7.1, E4.8):

    ```text
    frozen=True ALONE != DEEP IMMUTABILITY
    ```

    `frozen=True` protege a referência, não o conteúdo, e invariantes
    que vivem só num construtor de conveniência são contornáveis pelo
    construtor direto.
    """

    rule_id: str
    """Identificador estável, citado como fundamento de uma avaliação futura."""

    scope_kind: RetentionScopeKind
    """`ALL_LOCAL_PATRIMONY` ou `MEMORY_DOMAIN_SET` — nunca inferido."""

    minimum_age_days: int
    """Idade mínima, em dias, contada a partir da âncora. Sempre `>= 1`.

    Zero seria "expira ao nascer", que não é retenção — é ausência de
    retenção com aparência de regra.
    """

    domain_ids: frozenset[uuid.UUID] = field(default_factory=frozenset)
    """Domínios do escopo. Vazio **exige** `ALL_LOCAL_PATRIMONY`.

    Escopo **declarativo**: nesta fatia não há FK e não há consulta a
    `MemoryDomain`. Persistir a policy não é avaliar patrimônio, e
    verificar existência de domínio aqui faria a publicação depender
    de um estado que a avaliação futura reconsultará de qualquer forma.
    """

    anchor: RetentionAnchor = RetentionAnchor.CREATED_AT
    """Sempre `CREATED_AT` nesta versão — ver `RetentionAnchor`."""

    on_expiry_action: RetentionExpiryAction = RetentionExpiryAction.ASSESS_AND_INFORM
    """Sempre `ASSESS_AND_INFORM`. Expirar inicia avaliação, não exclusão."""

    def __post_init__(self) -> None:
        """Impõe os invariantes em **toda** construção pública."""
        if not isinstance(self.rule_id, str):
            raise TypeError(f"rule_id deve ser str, recebido {type(self.rule_id).__name__}")
        if not self.rule_id.strip():
            raise ValueError("rule_id não pode ser vazio ou apenas espaços")
        if any(ord(c) < 32 or ord(c) == 127 for c in self.rule_id):
            raise ValueError("rule_id não pode conter caracteres de controle")
        if len(self.rule_id) > MAX_RULE_ID_LENGTH:
            raise ValueError(f"rule_id excede {MAX_RULE_ID_LENGTH} caracteres")

        if not isinstance(self.scope_kind, RetentionScopeKind):
            raise TypeError("scope_kind deve ser um RetentionScopeKind")
        if not isinstance(self.anchor, RetentionAnchor):
            raise TypeError("anchor deve ser um RetentionAnchor")
        if not isinstance(self.on_expiry_action, RetentionExpiryAction):
            raise TypeError("on_expiry_action deve ser um RetentionExpiryAction")

        idade = _inteiro_real("minimum_age_days", self.minimum_age_days)
        if idade < 1:
            raise ValueError("minimum_age_days deve ser >= 1")

        dominios = self.domain_ids
        if isinstance(dominios, str | bytes) or not isinstance(dominios, Iterable):
            raise TypeError("domain_ids deve ser um iterável de UUID")
        itens = tuple(dominios)
        if any(not isinstance(item, uuid.UUID) for item in itens):
            raise TypeError("domain_ids aceita apenas UUID")
        object.__setattr__(self, "domain_ids", frozenset(itens))

        # A matriz de escopo é explícita nos dois sentidos. Só proibir
        # o vazio em MEMORY_DOMAIN_SET deixaria passar uma regra
        # ALL_LOCAL_PATRIMONY com domínios listados — que pareceria
        # restrita e não seria.
        if self.scope_kind is RetentionScopeKind.ALL_LOCAL_PATRIMONY and self.domain_ids:
            raise ValueError(
                "ALL_LOCAL_PATRIMONY não aceita domain_ids — o escopo já é todo o "
                "patrimônio local; listar domínios sugeriria uma restrição inexistente"
            )
        if self.scope_kind is RetentionScopeKind.MEMORY_DOMAIN_SET and not self.domain_ids:
            raise ValueError(
                "MEMORY_DOMAIN_SET exige domain_ids não vazio — conjunto vazio não é "
                "curinga (EMPTY SET != WILDCARD)"
            )

    def sort_key(self) -> tuple[str, str, int]:
        """Chave canônica de ordenação, para serialização determinística."""
        return (self.rule_id, self.scope_kind.value, self.minimum_age_days)
