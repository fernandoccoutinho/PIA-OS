"""
Vocabulário de fronteira da porta de governança (`E7.4-1 B1a`).

```text
E7_HOLDS_LITERALS · E4_HOLDS_AUTHORITY · THE_PROOF_HOLDS_THEM_EQUAL
DUPLICATE_PROTECTION_CATEGORY_OWNER = PROHIBITED
```

A E7 **não** pode importar `app.memory` — `e71b02` e `e72b10` medem isso por
AST, e a segunda varre também o router e o DTO. A saída não é afrouxar a
guarda: é declarar aqui o mesmo vocabulário **por valor**, e provar a
paridade por teste contra os enums reais da E4.

O que isso NÃO é: um segundo catálogo de dano humano. A autoridade normativa
continua sendo a fronteira de plataforma da E4.3; estes literais são a forma
que a pergunta e a resposta assumem ao atravessar a fronteira de pacote.
Ampliar `CriticalCapability` continua exigindo EDR na E4, e a prova de
paridade reprova qualquer divergência antes que ela vire comportamento.

```text
CANONICAL_BLOCKED_CAPABILITY = E4.CriticalCapability
VOCABULARY_COPY_WITHOUT_PARITY_PROOF = SECOND_SOURCE_OF_TRUTH
```
"""

from enum import StrEnum


class BoundaryOperation(StrEnum):
    """Espelho de `app.memory.models.governance_enums.CognitiveOperation`.

    Todos os onze membros estão presentes porque a paridade é medida como
    igualdade de conjuntos: uma cópia parcial passaria numa comparação de
    subconjunto e esconderia exatamente a divergência que a prova existe
    para achar.

    A E7.4-1 usa **apenas** `EXPOSE` em G1..G4 (decisão do titular,
    `SC-HP-25 = CLOSED`); os demais membros existem para a paridade, não
    como caminho executável.

    ```text
    DECLARED_VOCABULARY != EXECUTABLE_TRANSITION
    ```
    """

    READ = "read"
    REFERENCE = "reference"
    DERIVE = "derive"
    TRANSFORM = "transform"
    EXPOSE = "expose"
    SYNCHRONIZE = "synchronize"
    CONSOLIDATE = "consolidate"
    ACCESSIBILITY_TRANSITION = "accessibility_transition"
    RETENTION_ASSESSMENT = "retention_assessment"
    RETENTION_DISPOSITION = "retention_disposition"
    LEGAL_ERASURE = "legal_erasure"


class BoundaryCapability(StrEnum):
    """Espelho de `CriticalCapability` — capacidades, não temas.

    ```text
    TOPIC != CAPABILITY
    ```
    """

    CHILD_SEXUAL_EXPLOITATION = "child_sexual_exploitation"
    MINOR_TARGETING_FOR_EXPLOITATION = "minor_targeting_for_exploitation"
    WEAPON_OF_MASS_DESTRUCTION_ENABLEMENT = "weapon_of_mass_destruction_enablement"
    CATASTROPHIC_HARM_ENABLEMENT = "catastrophic_harm_enablement"


class BoundaryEngagement(StrEnum):
    """Espelho de `CapabilityEngagement`.

    É esta dimensão, e não o assunto, que separa o que a plataforma recusa
    do que ela deixa a governança local decidir.

    ```text
    ANALYTICAL != OPERATIONAL_ENABLEMENT
    PREVENTIVE != OPERATIONAL_ENABLEMENT
    ```
    """

    OPERATIONAL_ENABLEMENT = "operational_enablement"
    ANALYTICAL = "analytical"
    PREVENTIVE = "preventive"
    UNSPECIFIED = "unspecified"


class BoundaryOutcome(StrEnum):
    """Espelho de `GovernanceOutcome` — **quatro** valores, não dois.

    A ponte chama sempre com `policy_key=None`, de modo que só
    `PROHIBITED` e `NOT_APPLICABLE` podem ocorrer. Os outros dois existem
    aqui para que a chegada de um deles seja **reconhecível** e recusada
    como indisponibilidade técnica, em vez de cair num `else` mudo.

    ```text
    ADMISSIBLE ou INADMISSIBLE chegando pela porta -> PIA-8069
    UNEXPECTED_OUTCOME_INTERPRETED = FABRICATED_AUTHORITY
    ```
    """

    ADMISSIBLE = "admissible"
    INADMISSIBLE = "inadmissible"
    NOT_APPLICABLE = "not_applicable"
    PROHIBITED = "prohibited"


ACCEPTED_BOUNDARY_OUTCOMES = frozenset({BoundaryOutcome.PROHIBITED, BoundaryOutcome.NOT_APPLICABLE})
"""Os únicos desfechos que a ponte interpreta.

Enumerados literalmente, e não derivados por exclusão: `set(BoundaryOutcome)
- {…}` faria um membro novo do enum entrar aqui por omissão — o mesmo
defeito que `EMPTY_OPERATIONS_SCOPE_V1` corrigiu na E4.3.3.
"""

BRIDGE_COGNITIVE_OPERATION = BoundaryOperation.EXPOSE
"""Operação governada de G1..G4 (`SC-HP-25 = CLOSED`)."""
