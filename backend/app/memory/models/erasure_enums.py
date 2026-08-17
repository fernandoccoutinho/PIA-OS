"""
Vocabulários fechados do recibo de apagamento (`E4.9.5`).

```text
ErasureOutcome      = o que foi OBSERVADO, nunca o que foi pretendido
ErasureTargetClass  = o que foi CLASSIFICADO, nunca o que é permitido
```

Ambos são `StrEnum` fechados, como os enums de domínio da E3
(`AccessibilityState`, `CausalEventType`) e da E4.3
(`CognitiveOperation`): ampliar exige EDR.

A razão de serem fechados aqui é mais forte do que a de costume. Um
vocabulário aberto de resultado admitiria, por acréscimo silencioso,
exatamente os estados que a E4.9.0 proibiu — `PENDING`, `PROPOSED`,
`APPROVED`, `SCHEDULED`. Nenhum deles descreve um efeito observado;
todos descrevem uma intenção, e um recibo que registre intenção deixa
de ser recibo.
"""

from enum import StrEnum


class ErasureOutcome(StrEnum):
    """Desfecho **observado** de uma tentativa material de apagamento.

    Três membros, e nenhum quarto:

    ```text
    NO_RECORD_BEFORE_OBSERVED_ATTEMPT
    PENDING / PROPOSED / APPROVED / SCHEDULED = FORBIDDEN_OUTCOMES
    ```

    A semântica é a congelada pela E4.9.2, conservadora por desenho:

    - `SUCCEEDED` — todo o escopo controlado foi confirmado como
      apagado. Não significa "os bytes sumiram em toda parte": para
      alvo em provedor externo, significa que o provedor confirmou.
    - `PARTIAL` — basta **uma** instância remanescente, não verificada
      ou confirmada apenas por terceiro. Apresentar `PARTIAL` como
      sucesso mentiria no momento em que o usuário mais precisa da
      verdade.
    - `FAILED` — nenhum efeito pretendido foi confirmado.

    Aprovar não é executar, e executar não é ter registrado:

    ```text
    APPROVAL != EXECUTION != RECEIPT
    ```
    """

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    PARTIAL = "partial"


class ErasureTargetClass(StrEnum):
    """Classe do alvo tal como **classificada** na tentativa (E4.9.1).

    Registra o que foi tentado, não o que é admissível. As quatro
    classes são as da E4.9.1, e duas delas **não podem ser conteúdo**:

    - `PIA_MANAGED_ARTIFACT` e `AUTHORIZED_CONNECTOR_REFERENT` — as
      duas únicas que podem ser conteúdo apagável;
    - `COGNITIVE_METADATA_RECORD` — remover isto não é legal erasure;
    - `UNRESOLVED_OPAQUE_REFERENCE` — recusa tipada obrigatória,
      nunca best effort.

    Um futuro orquestrador deve recusar as duas últimas antes de
    tentar qualquer efeito. Esta fatia não decide e não executa: ela
    apenas consegue registrar, com fidelidade, o que uma tentativa
    real disse ter classificado.

    ```text
    CLASSIFICATION IS RECORDABLE != CLASSIFICATION IS ERASABLE
    ```
    """

    PIA_MANAGED_ARTIFACT = "pia_managed_artifact"
    AUTHORIZED_CONNECTOR_REFERENT = "authorized_connector_referent"
    COGNITIVE_METADATA_RECORD = "cognitive_metadata_record"
    UNRESOLVED_OPAQUE_REFERENCE = "unresolved_opaque_reference"
