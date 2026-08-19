"""
`ErasureRecord` — recibo persistente de apagamento observado (`E4.9.5`).

```text
ErasureRecord != CausalHistoryEvent
ErasureRecord != ApprovalRecord
ErasureRecord != RetentionPolicy
ErasureRecord != QueueItem
ErasureRecord != ProposedAction
```

Esta é a **primeira fatia de runtime** da E4.9: o lugar onde um futuro
orquestrador registrará o efeito observado de uma tentativa real. Ela
não apaga, não resolve alvo, não autentica, não aprova e não executa.

```text
ERASURE_RECORD_PERSISTENCE != ERASURE_EXECUTION
ERASURE_RECORD_PERSISTENCE != DELETION_AUTHORITY
ERASURE_RECORD_PERSISTENCE != RETENTION_POLICY
```

## Por que não existe estado "em andamento"

A E4.9.0 proibiu `PENDING`, `PROPOSED`, `APPROVED` e `SCHEDULED` como
desfechos. Se `completed_at` fosse nullable, um registro sem ele seria
um `PENDING` disfarçado — a mesma coisa proibida, com outro nome, e
sem nenhuma coluna que a delatasse. Por isso a coluna é **NOT NULL**:

```text
NO_RECORD_BEFORE_OBSERVED_ATTEMPT
NO_SUCCEEDED_WITHOUT_OBSERVED_EFFECT
```

Um recibo só nasce depois que alguém observou o que aconteceu.

## Por que o sujeito não tem FK

```text
SUBJECT_LINK = HISTORICAL_IDENTIFIER_NOT_FK
```

O recibo prova que **algo que existia** foi apagado. Uma FK para
`cognitive_objects` faria o recibo depender da sobrevivência do
sujeito, e um `ON DELETE CASCADE` — ou mesmo um `NO ACTION` que
impedisse a remoção — inverteria o propósito: ou o recibo some junto
com o que ele registra, ou ele impede a própria operação que
registra. `subject_identifier` é identidade **histórica**, string
opaca, deliberadamente sem integridade referencial.

O mesmo vale para aprovação, resolução, executor e retenção: são
referências de auditoria, não capacidades.

## O que este modelo não pode guardar

Não há coluna JSON genérica, `metadata`, `details`, `payload`,
`message`, `description` ou qualquer campo livre. Isso é estrutural,
não uma regra de uso: um campo livre acabaria recebendo o trecho
"só para contexto", e o recibo do apagamento viraria o último lugar
onde o conteúdo apagado sobreviveu.

```text
IF THE RECEIPT CAN RECOMPOSE THE CONTENT, IT IS CONTENT
```
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, Enum, Index, Integer, String, Uuid, event
from sqlalchemy.orm import Mapped, mapped_column

from app.memory.models.erasure_enums import ErasureOutcome, ErasureTargetClass
from app.models.base_model import BaseModel

MAX_IDENTIFIER_LENGTH = 256
"""Teto das strings opacas de identidade e referência.

Limite existe para que a coluna não vire depósito: 256 caracteres
acomodam qualquer identificador ou token de escopo razoável e não
acomodam um trecho de documento.
"""

MAX_FAILURE_CODE_LENGTH = 64
"""Teto do código de falha — é um código, não uma narrativa."""


class ErasureRecord(BaseModel):
    """Recibo imutável de uma tentativa de apagamento observada.

    Append-only em **três camadas**, e as três são necessárias:

    1. eventos de mapper (`before_update` / `before_delete`), que
       pegam a mutação feita por fora do repositório — defeito que a
       E4.3.1 reproduziu de verdade;
    2. `ErasureRecordRepository`, que recusa `update` e `delete`;
    3. trigger no PostgreSQL, que recusa `UPDATE` e `DELETE` **mesmo
       em SQL bruto**, fora do ORM.

    A terceira camada é nova no projeto. Até aqui, `GovernancePolicy` e
    `AccessibilityPolicy` diziam honestamente que o caminho SQL direto
    continuava possível. Para um recibo de apagamento essa honestidade
    não basta: o registro que prova o que foi destruído é justamente o
    que alguém teria motivo para reescrever.
    """

    __tablename__ = "erasure_records"

    subject_identifier: Mapped[str] = mapped_column(
        String(MAX_IDENTIFIER_LENGTH), nullable=False, index=True
    )
    """Identidade histórica do sujeito — string opaca, **sem FK**.

    Não é localizador. Não resolve. Não é capacidade. Ver o cabeçalho
    do módulo para a razão de não haver integridade referencial.
    """

    target_class: Mapped[ErasureTargetClass] = mapped_column(
        Enum(
            *(c.value for c in ErasureTargetClass),
            name="erasure_target_class",
            native_enum=False,
            length=32,
        ),
        nullable=False,
    )
    """Classe do alvo conforme classificada na tentativa (E4.9.1).

    Registrar `UNRESOLVED_OPAQUE_REFERENCE` é legítimo e informativo:
    significa que houve tentativa e o alvo não pôde ser resolvido.
    """

    scope_token: Mapped[str] = mapped_column(String(MAX_IDENTIFIER_LENGTH), nullable=False)
    """Token operacional do escopo da tentativa.

    Vocabulário operacional declarado pelo chamador, **nunca
    localizador**. A E4.9.2 classificou hash usável como chave de
    relocalização como *alvo do apagamento*, não rastro; um
    `scope_token` que permitisse reencontrar o conteúdo reintroduziria
    no recibo exatamente o que o erasure deveria ter eliminado.

    ```text
    SCOPE_TOKEN != LOCATOR
    SCOPE_TOKEN != CONTENT_HASH
    ```
    """

    outcome: Mapped[ErasureOutcome] = mapped_column(
        Enum(
            *(o.value for o in ErasureOutcome),
            name="erasure_outcome",
            native_enum=False,
            length=16,
        ),
        nullable=False,
        index=True,
    )
    """Desfecho observado. Nunca intenção — ver `ErasureOutcome`."""

    retention_policy_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(), nullable=True, default=None
    )
    """`id` da `RetentionPolicy` aplicável, **sem FK**.

    Nullable porque a E4.9.0 diz "quando aplicável", e porque
    `RetentionPolicy` **não existe** nesta fatia: `to_regclass` devolve
    `NULL`. Criar FK para tabela inexistente seria impossível; criá-la
    depois só é admissível se não ameaçar o caráter histórico do
    recibo.
    """

    retention_policy_key: Mapped[str | None] = mapped_column(
        String(MAX_IDENTIFIER_LENGTH), nullable=True, default=None
    )
    """Identidade lógica da policy de retenção, estável entre versões."""

    retention_policy_version: Mapped[int | None] = mapped_column(
        Integer, nullable=True, default=None
    )
    """Versão da policy de retenção que efetivamente valeu."""

    governance_policy_id: Mapped[uuid.UUID] = mapped_column(Uuid(), nullable=False)
    """`id` da versão de `GovernancePolicy` que fundamentou a decisão.

    Obrigatório e **sem FK**, por escolha desta fatia: o recibo precisa
    continuar legível mesmo que a linha da policy seja um dia removida
    por outra via. Uma FK com cascade destruiria o recibo junto com a
    policy; uma FK restritiva faria o recibo bloquear a manutenção da
    policy. Identidade histórica não tem esse dilema.
    """

    governance_policy_key: Mapped[str] = mapped_column(
        String(MAX_IDENTIFIER_LENGTH), nullable=False
    )
    """`policy_key` da governança — identidade lógica citada."""

    governance_policy_version: Mapped[int] = mapped_column(Integer, nullable=False)
    """Versão da governança que efetivamente avaliou a operação."""

    governance_rule_id: Mapped[str] = mapped_column(String(MAX_IDENTIFIER_LENGTH), nullable=False)
    """Regra específica dentro da versão citada — **texto opaco**.

    ```text
    OPAQUE_RULE_REFERENCE != UUID
    FABRICATED_RULE_IDENTITY = FORBIDDEN
    ```

    **Era `Uuid()` até a E4.9.9.d, e a correção foi medida, não estética.**
    A fonte deste valor é `GovernanceResolution.matched_rule_id`, que é
    `str | None` desde a E4.3 e recebe valores como `"rule-1"` em todo o
    projeto. A coluna exigia `UUID`, e as três saídas possíveis eram
    converter, sortear ou derivar por hash — as três inventam uma
    identidade de regra que não existe.

    A quarta saída é esta: o recibo cita a regra **como a governança a
    nomeia**. Alinhar o recibo ao contrato canônico preserva a citação
    byte a byte; alinhar a governança ao recibo quebraria a E4.3, que
    esta fatia não pode tocar.
    """

    governance_resolution_ref: Mapped[str] = mapped_column(
        String(MAX_IDENTIFIER_LENGTH), nullable=False
    )
    """Referência opaca à `GovernanceResolution` aplicada.

    Referência de auditoria, não conteúdo e não capacidade.
    """

    approval_ref: Mapped[str] = mapped_column(String(MAX_IDENTIFIER_LENGTH), nullable=False)
    """Referência opaca à aprovação humana que autorizou a tentativa.

    ```text
    APPROVAL_RECORD != ERASURE_RECORD
    ```

    São registros separados porque respondem a perguntas diferentes —
    "quem autorizou o quê" e "o que de fato aconteceu". Fundi-los
    perderia o estado *autorizado mas não executado*, que é
    exatamente o que se audita depois de uma falha (E4.9.4).

    Nunca contém credencial, token bruto, fator ou segredo.
    """

    executor_ref: Mapped[str] = mapped_column(String(MAX_IDENTIFIER_LENGTH), nullable=False)
    """Referência opaca ao executor verificado que realizou a tentativa.

    Nenhum executor existe nesta fatia. A coluna registra quem terá
    executado, quando houver — e o adaptador de efeito nunca é o
    modelo de IA.
    """

    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    """Instante em que a tentativa material começou — timezone-aware."""

    completed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    """Instante em que o resultado foi **observado** — timezone-aware.

    NOT NULL por decisão desta fatia, inclusive para `FAILED` e
    `PARTIAL`: sem isso, um registro sem `completed_at` seria um
    `PENDING` disfarçado.
    """

    failure_code: Mapped[str | None] = mapped_column(
        String(MAX_FAILURE_CODE_LENGTH), nullable=True, default=None
    )
    """Código curto da falha — obrigatório em `FAILED` e `PARTIAL`,
    proibido em `SUCCEEDED`.

    Um `SUCCEEDED` com código de falha e um `PARTIAL` sem ele são,
    cada um à sua maneira, um recibo que não descreve o que houve.
    """

    __table_args__ = (
        CheckConstraint(
            "length(btrim(subject_identifier)) > 0",
            name="ck_erasure_records_subject_identifier_not_blank",
        ),
        CheckConstraint(
            "length(btrim(scope_token)) > 0",
            name="ck_erasure_records_scope_token_not_blank",
        ),
        CheckConstraint(
            "length(btrim(governance_policy_key)) > 0",
            name="ck_erasure_records_governance_policy_key_not_blank",
        ),
        CheckConstraint(
            "length(btrim(governance_rule_id)) > 0",
            name="ck_erasure_records_governance_rule_id_not_blank",
        ),
        CheckConstraint(
            "length(btrim(governance_resolution_ref)) > 0",
            name="ck_erasure_records_governance_resolution_ref_not_blank",
        ),
        CheckConstraint(
            "length(btrim(approval_ref)) > 0",
            name="ck_erasure_records_approval_ref_not_blank",
        ),
        CheckConstraint(
            "length(btrim(executor_ref)) > 0",
            name="ck_erasure_records_executor_ref_not_blank",
        ),
        CheckConstraint(
            "governance_policy_version >= 1",
            name="ck_erasure_records_governance_version_positive",
        ),
        CheckConstraint(
            "retention_policy_version IS NULL OR retention_policy_version >= 1",
            name="ck_erasure_records_retention_version_positive",
        ),
        CheckConstraint(
            "(retention_policy_id IS NULL AND retention_policy_key IS NULL "
            "AND retention_policy_version IS NULL) OR "
            "(retention_policy_id IS NOT NULL AND retention_policy_key IS NOT NULL "
            "AND length(btrim(retention_policy_key)) > 0 "
            "AND retention_policy_version IS NOT NULL)",
            name="ck_erasure_records_retention_trio_all_or_none",
        ),
        CheckConstraint(
            "outcome IN ('succeeded', 'failed', 'partial')",
            name="ck_erasure_records_outcome_vocabulary",
        ),
        CheckConstraint(
            "target_class IN ('pia_managed_artifact', 'authorized_connector_referent', "
            "'cognitive_metadata_record', 'unresolved_opaque_reference')",
            name="ck_erasure_records_target_class_vocabulary",
        ),
        CheckConstraint(
            "completed_at >= attempted_at",
            name="ck_erasure_records_completed_after_attempted",
        ),
        CheckConstraint(
            "(outcome = 'succeeded' AND failure_code IS NULL) OR "
            "(outcome IN ('failed', 'partial') AND failure_code IS NOT NULL "
            "AND length(btrim(failure_code)) > 0)",
            name="ck_erasure_records_failure_code_matches_outcome",
        ),
        Index("ix_erasure_records_approval_ref", "approval_ref"),
        Index("ix_erasure_records_attempted_at_id", "attempted_at", "id"),
    )
    """Catorze `CHECK` e dois índices.

    Dois deles — `outcome_vocabulary` e `target_class_vocabulary` —
    vão **além** do padrão herdado do projeto, e a razão foi medida:
    `Enum(..., native_enum=False)` no SQLAlchemy 2.x tem
    `create_constraint=False` por padrão, então a coluna vira `VARCHAR`
    **sem** verificação no banco. `cognitive_objects.accessibility`
    confirma isso: zero `CHECK` naquela tabela.

    Para os enums da E3 isso é aceitável — o ORM é o único escritor.
    Aqui não é: a trigger existe justamente porque este registro pode
    ser alvo de SQL bruto, e sem estes dois `CHECK` um `INSERT` direto
    poderia gravar `outcome = 'pending'` — exatamente o
    `FORBIDDEN_OUTCOME` que a E4.9.0 proibiu.

    As constraints repetem, no banco, invariantes que os schemas já
    validam antes — defesa em profundidade, como em toda a E3/E4. A
    diferença aqui é que o banco é a **única** camada que continua
    valendo quando alguém escreve por SQL bruto, e este é o registro
    que mais convida a isso.

    O índice composto `(attempted_at, id)` existe para a paginação
    determinística do repositório: ordenar só por `attempted_at`
    empataria entre recibos do mesmo instante, e a página seguinte
    poderia repetir ou pular linhas.
    """


@event.listens_for(ErasureRecord, "before_update")
def _reject_erasure_record_update(
    mapper: object, connection: object, target: ErasureRecord
) -> None:
    """Rejeita qualquer `UPDATE` — o recibo é append-only.

    Camada 1 de 3. Pega a mutação feita **por fora** do repositório:
    carregar o objeto, mutar o atributo e chamar `commit()` contorna
    qualquer override de método, e a E4.3.1 reproduziu exatamente esse
    defeito.
    """
    from app.memory.errors.exceptions import ErasureRecordImmutableError

    raise ErasureRecordImmutableError(target.id, operation="update")


@event.listens_for(ErasureRecord, "before_delete")
def _reject_erasure_record_delete(
    mapper: object, connection: object, target: ErasureRecord
) -> None:
    """Rejeita qualquer `DELETE` — ver `_reject_erasure_record_update`.

    Apagar o recibo de um apagamento é a forma mais direta de tornar
    uma destruição inauditável.
    """
    from app.memory.errors.exceptions import ErasureRecordImmutableError

    raise ErasureRecordImmutableError(target.id, operation="delete")
