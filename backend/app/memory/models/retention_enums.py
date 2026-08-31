"""
Vocabulários fechados da retenção (`E4.9.6`).

```text
RETENTION_POLICY != USER_DECISION
EXPIRY != DESTRUCTIVE_CONSENT
```

Três enums, todos `StrEnum` fechados como os da E3 e da E4.3. Dois
deles têm **um único membro**, e isso é deliberado: um enum unitário
transforma qualquer ampliação futura em mudança explícita de contrato,
com EDR, em vez de acréscimo silencioso de um membro numa lista que já
tinha vários.

Onde isso mais importa é em `RetentionExpiryAction`. A E4.9.3 decidiu
que expiração inicia **avaliação**, nunca apagamento, e a auditoria da
cadeia 72 promoveu essa decisão a `CLOSED_FINAL`. Se o enum nascesse
com dois ou três membros "por simetria", acrescentar `DELETE` depois
pareceria natural. Nascendo com um, acrescentar qualquer coisa exige
justificar por que a decisão anterior deixou de valer.
"""

from enum import StrEnum


class RetentionScopeKind(StrEnum):
    """A que patrimônio uma regra se aplica.

    ```text
    ALL_LOCAL_PATRIMONY -> domain_ids VAZIO
    MEMORY_DOMAIN_SET   -> domain_ids NÃO VAZIO
    ```

    `ALL_LOCAL_PATRIMONY` é **explícito** por decisão desta fatia, e
    não um conjunto vazio interpretado como curinga. A E4.3 usa
    vazio-como-curinga em `GovernanceRule`, e ali é adequado — mas ali
    o efeito de uma regra ampla demais é uma permissão ou recusa, que
    o usuário observa. Aqui o efeito é elegibilidade à avaliação de
    **todo** o patrimônio local, e um campo esquecido não deveria
    produzir isso em silêncio.

    ```text
    EMPTY SET != WILDCARD
    ```

    `ALL_LOCAL_PATRIMONY` inclui conceitualmente patrimônio sem
    domínio algum — um `CognitiveObject` fora de toda classificação
    existe plenamente (`ZERO DOMAIN MEMBERSHIP != NONEXISTENCE`,
    congelado na E4.1) e não fica fora de escopo por isso.
    """

    ALL_LOCAL_PATRIMONY = "all_local_patrimony"
    MEMORY_DOMAIN_SET = "memory_domain_set"


class RetentionAnchor(StrEnum):
    """De que instante a idade é contada.

    Um único membro nesta versão, e a razão foi **medida** no preflight
    da E4.9, não presumida:

    ```text
    UPDATED_AT != RETENTION_ANCHOR
    ```

    `created_at` é estável entre transações, através de mutação de
    `accessibility` e de soft delete. `updated_at` **se move** — muda
    por transição de acessibilidade, que não tem relação nenhuma com a
    idade do patrimônio. Ancorar retenção nele faria um objeto
    reclassificado rejuvenescer.

    A armadilha que produziu esta lição também vale registrar: a
    primeira medição foi feita dentro de **uma** transação, e
    `updated_at` "não se moveu" — porque `now()` do PostgreSQL é o
    timestamp de início da transação.
    """

    CREATED_AT = "created_at"


class RetentionExpiryAction(StrEnum):
    """O que acontece quando a idade mínima é ultrapassada.

    Um único membro, e ele **não é destrutivo**:

    ```text
    EXPIRY_TRIGGERS_ASSESSMENT_NOT_DELETION
    NO_AUTOMATIC_ACTION = PRESERVE_AND_REPORT
    ```

    `ASSESS_AND_INFORM` significa: o item torna-se **elegível** a uma
    avaliação futura, que explicará motivo e impacto e pedirá decisão
    humana vinculada ao escopo. Não seleciona, não oculta, não move
    para lixeira, não notifica e não apaga — nada disso existe em
    runtime, e prescrever ação inexistente seria alegar capacidade
    falsa.

    Não existem, nem devem existir sem novo contrato: `DELETE`,
    `ERASE`, `TRASH`, `MARK_INACCESSIBLE`, `ARCHIVE`,
    `NOTIFY_AND_DELETE`, `AUTO_CLEANUP` ou sinônimo.

    ```text
    POLICY_MATCH != DELETION_CANDIDATE_CONFIRMED
    ```
    """

    ASSESS_AND_INFORM = "assess_and_inform"
