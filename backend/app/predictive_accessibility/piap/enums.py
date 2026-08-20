"""
Vocabulários fechados do PIAP (`E5.a`).

Todos são `StrEnum`, como `AccessibilityState` e `RevisionStatus` da E3 —
o precedente que permite satisfação tipada através de fronteira sem
importar o enum do outro lado.

Não existe `ProvenanceKind` aqui. Não há taxonomia autorizada de tipos de
fonte, e congelar uma imporia uma ontologia a fontes que ainda não
existem. `ProvenanceKind` é value object de token opaco em
`envelope.py`.

```text
CLOSED_VOCABULARY != INVENTED_TAXONOMY
```
"""

from enum import StrEnum


class PiapContractVersion(StrEnum):
    """Versões de contrato PIAP conhecidas.

    O valor não é snake_case porque não é um token de vocabulário: é a
    versão do contrato, e `"1.0"` é a forma que atravessa a serialização.
    """

    V1_0 = "1.0"


class TemporalAvailability(StrEnum):
    """Disponibilidade do sinal no instante de referência declarado.

    `UNKNOWN` é resultado legítimo, não falha. Uma fonte que não declara
    disponibilidade não deve ser lida como disponível.

    ```text
    UNKNOWN_AVAILABILITY != AVAILABLE
    ```
    """

    AVAILABLE_AT_REFERENCE_TIME = "available_at_reference_time"
    UNAVAILABLE_AT_REFERENCE_TIME = "unavailable_at_reference_time"
    UNKNOWN = "unknown"


class AuthorityStatus(StrEnum):
    """Status de autoridade **transportado**, nunca concedido pela E5.

    Os nomes dizem `ASSERTED_` de propósito: o envelope carrega o que a
    fonte afirma, e afirmar não é verificar.

    ```text
    E5_VALIDATES_BUT_DOES_NOT_GRANT_APPROVAL = TRUE
    ASSERTED_AUTHORIZED != VERIFIED_AUTHORIZATION
    ```
    """

    ASSERTED_AUTHORIZED = "asserted_authorized"
    ASSERTED_NOT_AUTHORIZED = "asserted_not_authorized"
    UNKNOWN = "unknown"


class ApprovalValidationOutcome(StrEnum):
    """Resultado **tipado** da validação de aprovação.

    Os sete desfechos não-`VALID` são informação, não falha de execução:
    `MISSING` e `EXPIRED` impedem promoção, limite material e rota
    `ROBUST` sem que nada tenha dado errado no sistema.

    ```text
    TYPED_NEGATIVE_OUTCOME != EXECUTION_FAILURE
    MISSING_EXPIRED_MISMATCHED_OR_OUT_OF_SCOPE_APPROVAL = TYPED_VALIDATION_OUTCOME
    ```
    """

    VALID = "valid"
    MISSING = "missing"
    NOT_AUTHORIZED = "not_authorized"
    EXPIRED = "expired"
    VERSION_MISMATCH = "version_mismatch"
    OUT_OF_SCOPE = "out_of_scope"
    JURISDICTION_MISMATCH = "jurisdiction_mismatch"
    BINDING_MISMATCH = "binding_mismatch"


class BoundObjectKind(StrEnum):
    """A que uma aprovação se vincula.

    O envelope transporta a **referência** e o vínculo; nunca o objeto
    aprovado.

    ```text
    PIAP_DUPLICATES_THE_APPROVED_OBJECT = FALSE
    ```
    """

    PROPOSED_BOUND = "proposed_bound"
    PROMOTION_CANDIDATE = "promotion_candidate"
