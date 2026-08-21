"""
Metadados de autoridade transportados pelo PIAP (`E5.a`).

```text
PIAP_TRANSPORTS_APPROVAL_REFERENCE_AND_BINDING = TRUE
PIAP_DUPLICATES_THE_APPROVED_OBJECT = FALSE
E5_VALIDATES_BUT_DOES_NOT_GRANT_APPROVAL = TRUE
```

## Uma única fonte de verdade para o status

`AuthorityContext.status` é o **único** lugar onde o status vive.
`ApprovalBinding` carrega referência, versão, escopo, expiração,
jurisdição e vínculo — e nenhum status próprio. Dois campos de status em
objetos diferentes permitiriam a combinação incoerente, e nenhuma
validação de campo isolado a pegaria.

```text
PARALLEL_AUTHORITY_STATUS = FORBIDDEN
```

## O que esta camada não faz

Não concede aprovação, não renova, não busca fonte externa e não altera o
contexto recebido. `validate_approval` é função pura: dado o mesmo
contexto e os mesmos parâmetros, devolve sempre o mesmo membro de
`ApprovalValidationOutcome`.
"""

import unicodedata
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

from app.predictive_accessibility.piap.capacity import (
    MAX_APPROVAL_SCOPE_ITEMS,
    MAX_PIAP_VERSION_NUMBER,
)
from app.predictive_accessibility.piap.enums import (
    ApprovalValidationOutcome,
    AuthorityStatus,
    BoundObjectKind,
)

MAX_REF_LENGTH = 255
"""Mesmo limite de referência opaca já usado em `E4.11`."""

CATEGORIAS_UNICODE_PROIBIDAS = frozenset({"Cc", "Cf", "Zl", "Zp"})
"""Controle, formatação e separação invisível.

Repertório reafirmado aqui, e não importado de `app.memory`: a fronteira
veda esse import na produção da E5. O valor é o mesmo que a E4.9.6.2 e a
E4.11 fixaram, e cada guarda estática o fixa no seu lugar.
"""


def validar_referencia_opaca(nome: str, valor: object, tamanho: int = MAX_REF_LENGTH) -> str:
    """Referência textual opaca, sem caractere invisível e sem transformação.

    Inspeciona por `unicodedata.category`, que **classifica**, e nunca por
    `normalize`, que transformaria. Duas sequências Unicode distintas
    jamais são fundidas aqui — o mesmo que a E4.9.7.3 pagou para aprender.

    ```text
    SILENT_NORMALIZATION = FORBIDDEN
    ```
    """
    if not isinstance(valor, str):
        raise TypeError(f"{nome} deve ser str, recebido {type(valor).__name__}")
    if not valor.strip():
        raise ValueError(f"{nome} não pode ser vazio ou apenas espaços")
    if len(valor) > tamanho:
        raise ValueError(f"{nome} excede {tamanho} caracteres")
    for caractere in valor:
        categoria = unicodedata.category(caractere)
        if categoria in CATEGORIAS_UNICODE_PROIBIDAS:
            raise ValueError(
                f"{nome} não pode conter caracteres de controle, formatação ou "
                f"separação invisível — U+{ord(caractere):04X} pertence à "
                f"categoria Unicode {categoria}"
            )
    return valor


def validar_inteiro_positivo(nome: str, valor: object) -> int:
    """Versão inteira dentro do domínio fechado `1..MAX_PIAP_VERSION_NUMBER`.

    `bool` é subclasse de `int` em Python, e `True` passaria por um
    `isinstance(valor, int)` ingênuo. Uma versão de aprovação igual a
    `True` seria lida como `1` e ninguém veria o erro.

    O domínio é fechado **dos dois lados**. Antes havia apenas piso: uma
    versão podia ser qualquer inteiro positivo, inclusive um que nenhum
    campo `Integer` da plataforma consegue armazenar, e inclusive um com
    dígitos suficientes para o parser JSON recusar antes que esta camada
    o visse.

    ```text
    UNBOUNDED_POSITIVE_VERSION = TRANSPORTED_PROMISE_THE_PLATFORM_CANNOT_KEEP
    ```
    """
    if isinstance(valor, bool) or not isinstance(valor, int):
        raise TypeError(f"{nome} deve ser int, recebido {type(valor).__name__}")
    if valor < 1:
        raise ValueError(f"{nome} deve ser >= 1, recebido {valor}")
    if valor > MAX_PIAP_VERSION_NUMBER:
        raise ValueError(
            f"{nome} excede MAX_PIAP_VERSION_NUMBER: recebido {valor}, "
            f"permitido no máximo {MAX_PIAP_VERSION_NUMBER}"
        )
    return valor


def canonizar_instante(nome: str, valor: object) -> datetime:
    """Exige instante ciente e canonicaliza para UTC.

    ```text
    NAIVE_INSTANT = MACHINE_DEPENDENT_RECORD
    ```

    Instantes iguais declarados em fusos diferentes precisam produzir a
    mesma igualdade estrutural — mesma disciplina de `ComplianceReport` e
    de `ValidatedExperienceAppend`.
    """
    if not isinstance(valor, datetime):
        raise TypeError(f"{nome} deve ser datetime, recebido {type(valor).__name__}")
    if valor.tzinfo is None or valor.tzinfo.utcoffset(valor) is None:
        raise ValueError(
            f"{nome} deve ser timezone-aware: um instante ingênuo daria registro "
            "dependente do fuso da máquina"
        )
    return valor.astimezone(UTC)


def validar_escopo(nome: str, valor: object) -> tuple[str, ...]:
    """Escopo não vazio, sem duplicata e **já** em ordem canônica.

    Não ordena e não deduplica: rejeita. Um escopo que o sistema reordena
    em silêncio deixa de ser o que o chamador declarou, e a diferença
    entre `("read",)` e `("read", "read")` importa quando alguém audita o
    que foi aprovado.

    ```text
    SILENT_REORDER_OR_DEDUP = FORBIDDEN
    ```

    A cardinalidade é verificada **antes** de validar item a item, porque
    `validar_referencia_opaca` percorre cada caractere de cada item
    chamando `unicodedata.category`. Contar primeiro custa uma comparação
    de inteiro; validar primeiro custa a varredura inteira de um escopo
    que já se sabe inadmissível.

    ```text
    CARDINALITY_CHECK_BEFORE_EXPENSIVE_PER_ITEM_VALIDATION = TRUE
    ```
    """
    if not isinstance(valor, tuple):
        raise TypeError(f"{nome} deve ser tuple, recebido {type(valor).__name__}")
    if not valor:
        raise ValueError(f"{nome} não pode ser vazio")
    if len(valor) > MAX_APPROVAL_SCOPE_ITEMS:
        raise ValueError(
            f"{nome} excede MAX_APPROVAL_SCOPE_ITEMS: recebido {len(valor)} itens, "
            f"permitido no máximo {MAX_APPROVAL_SCOPE_ITEMS}"
        )
    itens = tuple(validar_referencia_opaca(f"{nome}[{i}]", v) for i, v in enumerate(valor))
    if len(set(itens)) != len(itens):
        raise ValueError(f"{nome} contém entrada duplicada")
    if list(itens) != sorted(itens):
        raise ValueError(
            f"{nome} deve chegar em ordem canônica; a camada rejeita em vez de "
            "reordenar, porque reordenar mudaria o que foi declarado"
        )
    return itens


@dataclass(frozen=True)
class BoundObjectRef:
    """A que a aprovação se vincula — referência, nunca o objeto.

    Vive neste módulo, e não em `envelope.py`, para que `authority.py`
    não precise importar o envelope: o vínculo é conceito de autoridade,
    e a direção única de import evita ciclo.
    """

    kind: BoundObjectKind
    ref: uuid.UUID

    def __post_init__(self) -> None:
        if not isinstance(self.kind, BoundObjectKind):
            raise TypeError(f"kind deve ser BoundObjectKind, recebido {type(self.kind).__name__}")
        if not isinstance(self.ref, uuid.UUID):
            raise TypeError(f"ref deve ser uuid.UUID, recebido {type(self.ref).__name__}")


@dataclass(frozen=True)
class ApprovalBinding:
    """Referência a uma aprovação externa, e o vínculo dela com um objeto.

    Não existe `approval_status` aqui — ver a nota do módulo. O status
    pertence a `AuthorityContext`.

    `approval_reference` é redigido no `repr` pelo mesmo motivo de
    `AttributedValidator.validator_ref` na E4.11: uma referência de
    aprovação se apresenta de uma forma em log e de outra numa interface.
    """

    approval_reference: str = field(repr=False)
    approval_version: int
    approval_scope: tuple[str, ...]
    approval_expiry: datetime | None
    approval_jurisdiction: str | None
    bound_to: BoundObjectRef

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "approval_reference",
            validar_referencia_opaca("approval_reference", self.approval_reference),
        )
        object.__setattr__(
            self,
            "approval_version",
            validar_inteiro_positivo("approval_version", self.approval_version),
        )
        object.__setattr__(
            self, "approval_scope", validar_escopo("approval_scope", self.approval_scope)
        )
        if self.approval_expiry is not None:
            object.__setattr__(
                self,
                "approval_expiry",
                canonizar_instante("approval_expiry", self.approval_expiry),
            )
        if self.approval_jurisdiction is not None:
            object.__setattr__(
                self,
                "approval_jurisdiction",
                validar_referencia_opaca("approval_jurisdiction", self.approval_jurisdiction),
            )
        if not isinstance(self.bound_to, BoundObjectRef):
            raise TypeError(
                f"bound_to deve ser BoundObjectRef, recebido {type(self.bound_to).__name__}"
            )


@dataclass(frozen=True)
class AuthorityContext:
    """Status de autoridade transportado, e o vínculo de aprovação opcional.

    Estados impossíveis por construção:

    ```text
    ASSERTED_AUTHORIZED sem approval        -> erro
    approval ausente com ASSERTED_AUTHORIZED -> erro
    UNKNOWN com approval presente            -> erro
    ```

    `ASSERTED_NOT_AUTHORIZED` admite as duas formas: uma negativa pode vir
    acompanhada da referência que a sustenta, ou sem ela.
    """

    status: AuthorityStatus
    approval: ApprovalBinding | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, AuthorityStatus):
            raise TypeError(
                f"status deve ser AuthorityStatus, recebido {type(self.status).__name__}"
            )
        if self.approval is not None and not isinstance(self.approval, ApprovalBinding):
            raise TypeError(
                f"approval deve ser ApprovalBinding ou None, recebido "
                f"{type(self.approval).__name__}"
            )
        if self.status is AuthorityStatus.ASSERTED_AUTHORIZED and self.approval is None:
            raise ValueError(
                "ASSERTED_AUTHORIZED exige ApprovalBinding: autoridade afirmada sem "
                "referência não é verificável, e não verificável não é autoridade"
            )
        if self.status is AuthorityStatus.UNKNOWN and self.approval is not None:
            raise ValueError(
                "UNKNOWN não admite ApprovalBinding: carregar um vínculo e declarar "
                "status desconhecido são afirmações incompatíveis"
            )


def validate_approval(
    context: AuthorityContext,
    *,
    at: datetime,
    expected_version: int,
    required_scope: tuple[str, ...],
    expected_jurisdiction: str | None,
    expected_binding: BoundObjectRef,
) -> ApprovalValidationOutcome:
    """Valida a aprovação transportada. Não concede, não renova, não consulta.

    Função **pura**: não altera `context`, não toca estado externo e não
    tem efeito colateral. Devolve um membro de
    `ApprovalValidationOutcome`; nenhum desfecho negativo vira exceção.

    ```text
    NEGATIVE_APPROVAL_OUTCOME != EXCEPTION
    APPROVAL_VALIDATION_FAILURE != AUTHORIZATION_TO_INVENT_APPROVAL
    ```

    ## Precedência determinística

    Com vários defeitos simultâneos, o primeiro da lista vence. A ordem
    não é arbitrária: vai do mais estrutural ao mais circunstancial, de
    modo que o desfecho reportado seja o mais informativo sobre a causa.

    ```text
    1 approval ausente                        -> MISSING
    2 status != ASSERTED_AUTHORIZED           -> NOT_AUTHORIZED
    3 bound_to divergente                     -> BINDING_MISMATCH
    4 approval_version divergente             -> VERSION_MISMATCH
    5 jurisdição esperada divergente/ausente  -> JURISDICTION_MISMATCH
    6 required_scope não contido              -> OUT_OF_SCOPE
    7 approval_expiry <= at                   -> EXPIRED
    8 restante                                -> VALID
    ```

    Uma aprovação vinculada ao objeto errado é problema mais grave do que
    uma expirada, e por isso `BINDING_MISMATCH` precede `EXPIRED`.

    `expected_jurisdiction is None` significa que a jurisdição não é
    exigida — e não que a aprovação precise ser sem jurisdição.
    `approval_expiry is None` significa aprovação sem expiração, não
    expirada.
    """
    if not isinstance(context, AuthorityContext):
        raise TypeError(f"context deve ser AuthorityContext, recebido {type(context).__name__}")
    instante = canonizar_instante("at", at)
    esperada = validar_inteiro_positivo("expected_version", expected_version)
    escopo_exigido = validar_escopo("required_scope", required_scope)
    if expected_jurisdiction is not None:
        expected_jurisdiction = validar_referencia_opaca(
            "expected_jurisdiction", expected_jurisdiction
        )
    if not isinstance(expected_binding, BoundObjectRef):
        raise TypeError(
            f"expected_binding deve ser BoundObjectRef, recebido "
            f"{type(expected_binding).__name__}"
        )

    approval = context.approval
    if approval is None:
        return ApprovalValidationOutcome.MISSING
    if context.status is not AuthorityStatus.ASSERTED_AUTHORIZED:
        return ApprovalValidationOutcome.NOT_AUTHORIZED
    if approval.bound_to != expected_binding:
        return ApprovalValidationOutcome.BINDING_MISMATCH
    if approval.approval_version != esperada:
        return ApprovalValidationOutcome.VERSION_MISMATCH
    if (
        expected_jurisdiction is not None
        and approval.approval_jurisdiction != expected_jurisdiction
    ):
        return ApprovalValidationOutcome.JURISDICTION_MISMATCH
    if not set(escopo_exigido).issubset(approval.approval_scope):
        return ApprovalValidationOutcome.OUT_OF_SCOPE
    if approval.approval_expiry is not None and approval.approval_expiry <= instante:
        return ApprovalValidationOutcome.EXPIRED
    return ApprovalValidationOutcome.VALID
