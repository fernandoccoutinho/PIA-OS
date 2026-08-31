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

import unicodedata
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

CATEGORIAS_UNICODE_PROIBIDAS = frozenset({"Cc", "Cf", "Zl", "Zp"})
"""Categorias Unicode recusadas em identificador opaco (`E4.9.6.2`).

```text
Cc  Other, Control      U+0000 NUL, U+000A LF, U+007F DEL, U+0085 NEL
Cf  Other, Format       U+200B ZWSP, U+202E RLO, U+FEFF BOM
Zl  Separator, Line     U+2028
Zp  Separator, Paragraph U+2029
```

A E4.9.6.1 recusava `ord(c) < 32 or ord(c) == 127`, que é exatamente
C0 + DEL — cumpriu o contrato que tinha. A auditoria da cadeia 77
mostrou que o **argumento** daquele contrato ("uma chave assim se
apresenta de uma forma em log, de outra em exportação e de uma
terceira numa interface") vale igual para `U+2028` e `U+202E`, e eles
passavam. Isto é endurecimento autorizado, não descumprimento
retroativo.

Categorias de fora desta lista continuam permitidas — letras, números,
marcas, pontuação, símbolos e o espaço comum (`Zs`). Acento e cedilha
não são invisíveis e nunca foram o problema.
"""

CAMPOS_JSON_OBRIGATORIOS = (
    "rule_id",
    "scope_kind",
    "domain_ids",
    "anchor",
    "minimum_age_days",
    "on_expiry_action",
)
"""Os seis campos do JSON canônico de uma regra (`E4.9.6.3`).

Fixados aqui, junto do contrato tipado, e não dentro da desserialização:
é a mesma lista que `RetentionPolicy.serialize_rules` escreve, e mantê-la
em dois lugares é como as fronteiras divergem.
"""


def validar_identificador_opaco(nome: str, valor: object, tamanho: int) -> str:
    """Contrato único de identificador opaco (`E4.9.6.1`, endurecido em `E4.9.6.2`).

    ```text
    VALIDATED OPAQUE KEY != NORMALIZED KEY
    ```

    Recusa tipo errado, vazio, branco, todo caractere das categorias
    Unicode `Cc`/`Cf`/`Zl`/`Zp` e excesso de tamanho. Devolve o valor
    **original**: sem `strip`, sem normalização Unicode, sem `casefold`.

    Não normalizar é parte do contrato, não descuido. Um identificador
    que o sistema altera em silêncio deixa de ser a identidade que o
    chamador declarou, e a policy publicada passaria a responder por
    uma chave que ninguém escreveu. Por isso a inspeção é por
    `unicodedata.category`, que **classifica**, e nunca por
    `unicodedata.normalize`, que **transformaria** — duas sequências
    distintas jamais são fundidas aqui.

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
    for caractere in valor:
        categoria = unicodedata.category(caractere)
        if categoria in CATEGORIAS_UNICODE_PROIBIDAS:
            raise ValueError(
                f"{nome} não pode conter caracteres de controle, formatação ou "
                f"separação invisível — U+{ord(caractere):04X} pertence à "
                f"categoria Unicode {categoria}"
            )
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


def regra_de_json(indice: int, item: object) -> "RetentionRule":
    """Contrato **estrutural** do JSON persistido, e a reconstrução (`E4.9.6.3`).

    ```text
    JSON ITERABLE != CANONICAL JSON ARRAY
    ```

    A E4.9.6.2 verificou que o item era `dict` e que as seis chaves
    existiam, e passou a conversão direto ao construtor de
    `RetentionRule`. Faltava o passo do meio: **a forma de cada campo**.
    A auditoria da cadeia 78 mediu o custo — um `domain_ids` que fosse
    objeto JSON era iterado por Python pelas **chaves**, cada chave
    virava UUID e os valores sumiam em silêncio. JSON estruturalmente
    inválido virava regra válida com significado diferente do gravado.

    Duas camadas, nesta ordem: forma aqui, domínio no construtor de
    `RetentionRule`, que continua sendo a autoridade final sobre
    vocabulário fechado, `minimum_age_days >= 1` e a matriz de escopo.
    Nenhuma substitui a outra.

    Validar a forma antes de converter também é o que remove a
    necessidade de `cast`: cada `isinstance` estreita o tipo para o
    verificador, e o construtor recebe valores já tipados.
    """
    if not isinstance(item, dict):
        raise ValueError(f"regra[{indice}] deve ser um objeto JSON, recebido {type(item).__name__}")

    faltando = [chave for chave in CAMPOS_JSON_OBRIGATORIOS if chave not in item]
    if faltando:
        raise ValueError(f"regra[{indice}] não tem as chaves obrigatórias: {', '.join(faltando)}")

    textos: dict[str, str] = {}
    for campo in ("rule_id", "scope_kind", "anchor", "on_expiry_action"):
        bruto = item[campo]
        if not isinstance(bruto, str):
            raise TypeError(
                f"regra[{indice}].{campo} deve ser str, recebido {type(bruto).__name__}"
            )
        textos[campo] = bruto

    idade = item["minimum_age_days"]
    if isinstance(idade, bool) or not isinstance(idade, int):
        raise TypeError(
            f"regra[{indice}].minimum_age_days deve ser int, " f"recebido {type(idade).__name__}"
        )

    # `list` EXATA. `dict` é o caso reproduzido pela auditoria; `str`,
    # `tuple` e `set` também são iteráveis e produziriam conversão
    # plausível a partir de algo que o formato canônico nunca gravou.
    dominios = item["domain_ids"]
    if not isinstance(dominios, list):
        raise TypeError(
            f"regra[{indice}].domain_ids deve ser uma lista JSON, "
            f"recebido {type(dominios).__name__}"
        )
    convertidos: list[uuid.UUID] = []
    for posicao, bruto_id in enumerate(dominios):
        if not isinstance(bruto_id, str):
            raise TypeError(
                f"regra[{indice}].domain_ids[{posicao}] deve ser str, "
                f"recebido {type(bruto_id).__name__}"
            )
        try:
            convertidos.append(uuid.UUID(bruto_id))
        except ValueError as exc:
            raise ValueError(
                f"regra[{indice}].domain_ids[{posicao}] não é um UUID válido: " f"{bruto_id!r}"
            ) from exc

    try:
        escopo = RetentionScopeKind(textos["scope_kind"])
        ancora = RetentionAnchor(textos["anchor"])
        acao = RetentionExpiryAction(textos["on_expiry_action"])
    except ValueError as exc:
        raise ValueError(f"regra[{indice}]: {exc}") from exc

    return RetentionRule(
        rule_id=textos["rule_id"],
        scope_kind=escopo,
        domain_ids=frozenset(convertidos),
        anchor=ancora,
        minimum_age_days=idade,
        on_expiry_action=acao,
    )


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


def validar_regras_retencao(nome: str, valor: object) -> tuple[RetentionRule, ...]:
    """Contrato **único** da coleção de regras (`E4.9.6.2`).

    ```text
    TYPE DECORATOR BOUNDARY != ORM ASSIGNMENT BOUNDARY
    ```

    A E4.9.6.1 pôs o congelamento no tipo da coluna, e o tipo da coluna
    só atua em `process_bind_param` e `process_result_value`. Um objeto
    construído em Python e nunca gravado nem carregado não atravessa
    nenhuma das duas: `RetentionPolicy(rules=[{...}])` guardava
    `list[dict]` mutável, e `typed_rules` devolvia dicionários sob
    anotação de `RetentionRule`. Esta função é a fronteira que faltava,
    e é a MESMA usada pela atribuição do ORM, pelo bind e pela leitura
    defensiva — uma só, para que não voltem a divergir.

    Exige `tuple` exata. `list` é recusada de propósito: aceitá-la
    reintroduziria uma coleção mutável como representação pública
    legítima, e converter em silêncio faria a violação parecer válida —
    mesma disciplina da E4.6.2, que recusou converter `Iterable` em
    `Sequence`.

    Devolve a **mesma** tupla, sem reordenar: a ordem canônica é
    imposta na serialização, e reordenar aqui faria o valor observado
    divergir do valor declarado pelo chamador.
    """
    if not isinstance(valor, tuple):
        raise TypeError(
            f"{nome} deve ser tuple[RetentionRule, ...], recebido "
            f"{type(valor).__name__} — coleção mutável não é representação "
            f"pública admissível de uma policy publicada"
        )
    if not valor:
        raise ValueError(
            "uma versão de RetentionPolicy exige ao menos uma regra — "
            "policy sem regra não expressa retenção alguma"
        )
    for indice, item in enumerate(valor):
        if not isinstance(item, RetentionRule):
            raise TypeError(
                f"{nome}[{indice}] deve ser RetentionRule, recebido " f"{type(item).__name__}"
            )

    ids = [regra.rule_id for regra in valor]
    duplicados = sorted({rid for rid in ids if ids.count(rid) > 1})
    if duplicados:
        raise ValueError(
            f"rule_id duplicado na mesma versão: {', '.join(duplicados)} — "
            "duplicata torna o fundamento da avaliação ambíguo"
        )
    return valor
