"""
Vocabulários fechados do registro de experiência validada (`E4.11`).

```text
ERROR      != AUTOMATIC_LEARNING
SUCCESS    != AUTOMATIC_LEARNING
REPETITION != AUTOMATIC_LEARNING
```

A E4.11 encerra em `VALIDATION RECORD`. Nada aqui expressa seleção,
peso, prioridade, generalização ou recomendação — e a ausência é
estrutural, não estilística: um enum de "grau" ou "confiança" seria o
primeiro degrau do motor de aprendizado proibido.

Nenhum membro `UNKNOWN`, `OTHER` ou `ERROR`. Um coringa absorveria em
silêncio o caso que ninguém previu, e o caso que ninguém previu é
exatamente o que precisa aparecer.
"""

from enum import StrEnum


class ExperienceSubjectKind(StrEnum):
    """Sobre o que a experiência foi validada.

    ```text
    SAME_UUID_DIFFERENT_UNIVERSE
    ```

    Dois membros, e o discriminador é indispensável: o identificador de
    um `CognitiveObject` e o de um `CausalHistoryEvent` são ambos
    `uuid.UUID`, e sem dizer qual é qual o mesmo valor apontaria para
    dois universos diferentes.
    """

    COGNITIVE_OBJECT = "cognitive_object"
    """O sujeito é um objeto do patrimônio, identificado pelo COID."""

    CAUSAL_EVENT = "causal_event"
    """O sujeito é um evento causal — a experiência **é** o evento.

    Não existe `experience_ref` separado de `subject_ref`: criar um
    terceiro ponteiro faria dois campos disputarem o mesmo papel, e
    nada diria qual deles é o fato.
    """


class ValidatorKind(StrEnum):
    """Que espécie de validador é atribuída ao registro.

    ```text
    ORIGIN_ATTRIBUTED    = YES
    ORIGIN_AUTHENTICATED = NO
    ```

    Atribuição, nunca autenticação. Não existe autenticador na cadeia
    95, e um campo que sugerisse identidade comprovada afirmaria uma
    garantia que o sistema não tem.
    """

    HUMAN = "human"
    AGENT = "agent"
    SYSTEM = "system"


class EvidenceKind(StrEnum):
    """Que espécie de artefato fundamenta a validação.

    Fechada nas quatro primitivas E3 que existem e são referenciáveis
    por identidade. Um membro para artefato inexistente prometeria uma
    evidência que nada sustenta.
    """

    COGNITIVE_OBJECT = "cognitive_object"
    CAUSAL_EVENT = "causal_event"
    PROVENANCE_RECORD = "provenance_record"
    TRANSFORMATION_RECORD = "transformation_record"


class CriterionOriginKind(StrEnum):
    """De onde vem o critério contra o qual se validou.

    O critério precisa ser reproduzível: quem lê o registro meses depois
    tem de saber onde procurá-lo. `DECLARED` é o caso em que o critério
    foi enunciado pelo próprio validador no ato — legítimo, e
    deliberadamente distinto de um critério publicado, que outra pessoa
    pode consultar.
    """

    PUBLISHED = "published"
    DECLARED = "declared"
