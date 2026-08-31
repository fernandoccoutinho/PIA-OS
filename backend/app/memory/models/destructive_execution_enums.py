"""
Vocabulários fechados da composição destrutiva final (`E4.9.9.d`).

```text
RESOLUTION   != DELETION_AUTHORITY
APPROVAL     != CONSUMPTION
CONSUMPTION  != EFFECT
EFFECT       != ERASURE_RECORD
```

Três enums, e cada um responde a uma pergunta que os outros não
respondem sem mentir:

- `PreConsumptionRefusalReason` — por que o lote parou **antes** de
  qualquer escrita;
- `SnapshotDivergenceField` — qual dos sete campos do binding divergiu
  entre o snapshot aprovado e a re-resolução fresca;
- `AdapterContractViolation` — em que o resultado devolvido pela porta
  de efeito deixou de corresponder ao que foi pedido.

Nenhum deles tem `UNKNOWN`, `OTHER` ou `ERROR`. Um membro-coringa
absorveria em silêncio o caso que ninguém previu, e o caso que ninguém
previu é exatamente o que precisa aparecer.
"""

from enum import StrEnum


class PreConsumptionRefusalReason(StrEnum):
    """Por que a execução parou antes de consumir a aprovação.

    ```text
    PRE_CONSUMPTION_REFUSAL -> NO_CONSUMPTION, NO_EFFECT, NO_RECEIPT
    ```

    Todas as recusas desta família são **inócuas**: nada foi escrito,
    nada foi tentado, a aprovação continua ativa e utilizável. É isso
    que as distingue de `ApprovalConsumptionRefusal`, onde o consumo foi
    tentado, e do relatório, onde ele ocorreu.
    """

    BATCH_CARDINALITY_MISMATCH = "batch_cardinality_mismatch"
    """A tupla de referências não tem o mesmo tamanho do lote aprovado.

    Não é caso de borda: executar sobre um subconjunto silencioso
    alcançaria menos alvos do que o usuário confirmou, e sobre um
    superconjunto alcançaria mais.
    """

    REFERENCE_DOES_NOT_MATCH_APPROVED_TARGET = "reference_does_not_match_approved_target"
    """A referência na posição *i* não descreve o alvo aprovado em *i*.

    A ordem faz parte do binding desde a E4.9.8. Reordenar por
    conveniência mudaria o que foi confirmado.
    """

    DUPLICATE_SUBJECT_IN_BATCH = "duplicate_subject_in_batch"
    """O mesmo sujeito aparece duas vezes nas referências.

    Duplicata tornaria ambíguo quantas tentativas materiais um único
    alvo recebeu — e o recibo é por tentativa.
    """

    TARGET_RESOLUTION_REFUSED = "target_resolution_refused"
    """A porta de resolução devolveu recusa tipada para algum alvo.

    A recusa de **um** invalida o lote inteiro: um lote parcialmente
    resolvível não é o lote que foi aprovado.
    """

    FRESH_SNAPSHOT_DIVERGED = "fresh_snapshot_diverged"
    """A re-resolução fresca não é estruturalmente igual ao aprovado.

    ```text
    FRESH_DESCRIPTOR != APPROVED_SNAPSHOT -> NO_CONSUMPTION
    ```
    """

    GOVERNANCE_PROVENANCE_INCOMPLETE = "governance_provenance_incomplete"
    """Falta alguma das quatro fontes de governança do recibo.

    `policy_id`, `policy_key`, `policy_version` e `matched_rule_id` são
    opcionais no tipo da E4.3 e **obrigatórios** aqui. Completar com
    default fabricaria proveniência: o recibo citaria uma regra que
    ninguém aplicou.
    """


class SnapshotDivergenceField(StrEnum):
    """Qual campo do binding divergiu — nome do campo, nunca o valor.

    ```text
    FIELD_NAME_IS_SAFE · FIELD_VALUE_IS_NOT
    ```

    Os sete campos que `SafeTargetSnapshot` compara. Transportar o valor
    divergente devolveria ao chamador o `version_etag` ou a custódia
    observados agora — informação que a recusa não precisa e que a
    E4.9.7.3 gastou um corretivo para tirar das representações.
    """

    TARGET_CLASS = "target_class"
    SUBJECT_COID = "subject_coid"
    CONTROL_SCOPE = "control_scope"
    CUSTODY_NAMESPACE = "custody_namespace"
    ORIGIN = "origin"
    LEGACY_PROTECTION_STATE = "legacy_protection_state"
    VERSION_ETAG = "version_etag"


class AdapterContractViolation(StrEnum):
    """Em que o resultado da porta de efeito não corresponde ao pedido.

    ```text
    RETURNED_RESULT != FACT_UNTIL_BOUND_TO_THE_REQUEST
    ```

    A E4.5.2 aprendeu isto do outro lado: recibo e banco concordavam
    entre si enquanto ambos descreviam outra operação. Aqui a lição é a
    mesma — um resultado que cita outra aprovação, outro sujeito ou
    outra classe não descreve o que foi pedido, e aceitá-lo registraria
    o apagamento de um objeto a partir da observação de outro.
    """

    APPROVAL_MISMATCH = "approval_mismatch"
    SUBJECT_MISMATCH = "subject_mismatch"
    TARGET_CLASS_MISMATCH = "target_class_mismatch"
