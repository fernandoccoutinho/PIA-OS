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

MAX_KEY_LENGTH = 256
"""Teto de `policy_key` e `governance_policy_key`, medido em caracteres."""


def validar_identificador_opaco(nome: str, valor: object, tamanho: int) -> str:
    """Contrato único de identificador opaco (`E4.9.6.1`).

    ```text
    VALIDATED OPAQUE KEY != NORMALIZED KEY
    ```

    Recusa tipo errado, vazio, branco, **todo** C0 (`U+0000..U+001F`) e
    DEL (`U+007F`), e excesso de tamanho. Devolve o valor **original**:
    sem `strip`, sem normalização Unicode, sem `casefold`.

    Não normalizar é parte do contrato, não descuido. Um identificador
    que o sistema altera em silêncio deixa de ser a identidade que o
    chamador declarou, e a policy publicada passaria a responder por
    uma chave que ninguém escreveu.

    A E4.9.6 validava controle apenas em `rule_id`, e a auditoria
    reproduziu o buraco: `strip()` sozinho aceita `"ret\nembedded"`,
    porque há conteúdo não branco em volta da quebra. Uma chave assim
    se apresenta de uma forma em log, de outra em exportação e de uma
    terceira numa interface.
    """
    if not isinstance(valor, str):
        raise TypeError(f"{nome} deve ser str, recebido {type(valor).__name__}")
    if not valor.strip():
        raise ValueError(f"{nome} não pode ser vazio ou apenas espaços")
    if any(ord(c) < 32 or ord(c) == 127 for c in valor):
        raise ValueError(f"{nome} não pode conter caracteres de controle (C0 ou DEL)")
    if len(valor) > tamanho:
        raise ValueError(f"{nome} excede {tamanho} caracteres")
    return valor


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
        validar_identificador_opaco("rule_id", self.rule_id, MAX_RULE_ID_LENGTH)

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
