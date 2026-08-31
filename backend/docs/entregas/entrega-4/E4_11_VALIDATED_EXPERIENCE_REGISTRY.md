# E4.11 — Validated Experience Registry

Registro persistente e imutável de que uma experiência foi validada:
sobre o quê, com que resultado, por quem, contra qual critério, com qual
lastro, quando e de qual origem.

```text
E4_11 = COMPLETE_CANDIDATE
LEARNING_ENGINE = NONE
REPAIR_IMPLEMENTED = NO
SELECTION = NONE
TRANSPORT_IMPLEMENTED = NO
E4_12 = NOT_STARTED
PASS_FINAL = NOT_DECLARED
```

---

## 1. Onde a fatia começa e onde ela termina

```text
VARIATION
  -> EXPERIENCE
  -> EVIDENCE
  -> VALIDATION          <- a E4.11 encerra AQUI
  -> SELECTION
  -> POSSIBLE_PERSISTENCE
  -> CONTROLLED_IMPROVEMENT
```

O teste que decide tudo, congelado no `E4_ARCHITECTURE_FREEZE` §19:

```text
IF REMOVING THE RECORD CHANGES SYSTEM BEHAVIOR
THEN IT IS A LEARNING ENGINE
```

Remover uma linha desta tabela apaga **evidência auditável**. Não muda
nenhuma decisão, porque nenhum módulo de produção chama ou ramifica
sobre o registro — e isso é medido, não prometido.

```text
ERROR      != AUTOMATIC_LEARNING
SUCCESS    != AUTOMATIC_LEARNING
REPETITION != AUTOMATIC_LEARNING
```

## 2. Escopo entregue

```text
NOVO   app/memory/models/validated_experience_enums.py
NOVO   app/memory/schemas/validated_experience.py
NOVO   app/memory/models/validated_experience.py
NOVO   app/memory/repositories/validated_experience_repository.py
NOVO   alembic/versions/e7c25a91f4b3_..._e4_11.py
TOCADO app/memory/errors/codes.py         PIA-8050, PIA-8051
TOCADO app/memory/errors/exceptions.py    duas exceções tipadas
TOCADO app/memory/models/__init__.py      reexport
```

Nenhum arquivo de E3 ou de E4.1–E4.10 alterado. Nenhum autenticador,
API, worker, fila, scheduler ou conector.

## 3. O vínculo em seis partes

```text
subject_ref + outcome_observed + validated_by
            + criterion_ref + evidence_refs + validated_at
```

Separados, cada elemento é um dado solto: um resultado sem critério não
diz contra o quê foi validado, e um validador sem instante não diz
quando. Todos obrigatórios, nenhum com default.

**`subject_ref` é união fechada de dois membros.** `SAME_UUID_DIFFERENT_
UNIVERSE`: o identificador de um `CognitiveObject` e o de um
`CausalHistoryEvent` são ambos `uuid.UUID`, e sem discriminador o mesmo
valor apontaria para dois universos. Não existe `experience_ref`
separado — o evento causal **é** a experiência, e um terceiro ponteiro
faria dois campos disputarem o mesmo papel.

**`outcome_token` é gramática fechada, não enum universal.** Minúsculas
ASCII, dígitos e três separadores; sem espaço, sem maiúscula, sem
acento. Um campo que aceita frase vira campo de julgamento. O token é
lido **contra** o `criterion_ref` e não constitui ontologia: congelar
`PRODUCED/NOT_PRODUCED/INTERRUPTED/DIVERGED` imporia uma taxonomia a
experiências que ainda não existem.

**`primary_evidence_ref` precisa estar em `evidence_refs`**, e o lastro
não pode ser vazio — `EXPERIENCE -> EVIDENCE -> VALIDATION`. Um registro
validado sem evidência contradiz a própria natureza.

**`evidence_refs[i].ref` é `uuid.UUID`, não texto.** `UUID_HAS_NOWHERE_
TO_PUT_A_URL`: a garantia `NO_LOCATOR · NO_CONTENT · NO_CREDENTIAL` é do
tipo, não de vigilância. **Sem FK** — uma FK exigiria que o alvo exista
*neste* banco, e quebraria evidência sobre objeto já removido.

**`validated_by` é atribuição, jamais autenticação.** Não existe
autenticador na cadeia 95; não há coluna `verified`, `signature` ou
`authenticated`, e a ausência é o que impede a alegação falsa. A
referência do validador não aparece em `repr`/`str`.

## 4. Idempotência por identidade

```text
REPLAY_SAME_ID + SAME_CANONICAL_PAYLOAD      -> devolve o existente
REPLAY_SAME_ID + DIFFERENT_CANONICAL_PAYLOAD -> PIA-8050, zero overwrite
DIFFERENT_ID   + SAME_VALUES                 -> permitido
```

A terceira linha é decisão medida: **repetição pode ser evidência**.
Duas validações do mesmo sujeito, contra o mesmo critério, pelo mesmo
validador, em instantes diferentes, são dois fatos — uma constraint
semântica de unicidade apagaria a distinção que a repetição constitui.
Por isso não existe `UNIQUE` sobre sujeito/critério/validador.

Replay idêntico **não é erro** e não tem código: repetir a mesma chamada
com a mesma identidade e o mesmo conteúdo é a definição de idempotência.

Duas rotas resolvem o replay: a leitura prévia cobre o sequencial, e o
`IntegrityError` cobre o **concorrente** — duas sessões que passaram
juntas pela leitura. Sem a segunda, a corrida apareceria como erro de
banco cru em vez de idempotência.

## 5. Append-only em três camadas

```text
1. value object congelado
2. repositório recusa update / delete / soft_delete / bulk_*
3. trigger PostgreSQL BEFORE UPDATE OR DELETE
```

A E3 declara explicitamente que **não** impõe append-only no banco para
`ProvenanceRecord` — nenhuma trigger. O precedente forte é o da E4.9.5,
e é o que esta tabela segue: SQL arbitrário fora do repositório também é
recusado.

`soft_delete` também é recusado: `SOFT_DELETE_IS_STILL_A_WRITE`. Uma
evidência que some de uma leitura auditável não é append-only.

## 6. Decisão de portabilidade

```text
VALIDATED_EXPERIENCE_PORTABILITY = PORTABLE_WITH_ORIGIN_ATTRIBUTION
TRANSPORT_IMPLEMENTED            = NO
TRANSPORT                        = DEFERRED
ORIGIN_ATTRIBUTED                = YES
ORIGIN_AUTHENTICATED             = NO
ORIGIN_LOCALITY_PERSISTED        = NO
```

Fecha a questão aberta do `E4_SYNC_BOUNDARY` §7.

**Por que a atribuição não podia esperar.** A tabela é append-only, e
atribuição de origem não se retrofita: acrescentar a coluna depois
deixaria as linhas antigas em `NULL`, e `ORIGIN_UNKNOWN != LOCAL_ORIGIN`
— evidência alheia viraria própria por omissão, o colapso que `COUT-P3`
proíbe. `origin_ref` é obrigatório desde a primeira linha.

**Por que localidade não é persistida.** "Local" é relativo a quem lê. Um
registro local hoje é importado amanhã, e um booleano persistido passaria
a mentir depois da travessia.

**Por que o transporte não veio junto.** MEDIDO: o que viaja no sync é o
que está em `SECTION_BY_TABLE`, um dicionário literal em
`app/cognitive/schemas/synchronization.py`; `ordered_tables()` filtra
`Base.metadata.sorted_tables` por ele. Criar a tabela **não** a faz
viajar, e registrá-la ali seria alterar E3 congelada. A decisão de
portabilidade é do contrato; o transporte é de uma autorização futura.

## 7. Erros tipados

```text
PIA-8050  ValidatedExperienceConflictError    mesma identidade, conteúdo divergente
PIA-8051  ValidatedExperienceImmutableError   update / delete / soft_delete
```

Dois, e não três: replay idêntico não é erro, e reservar um código sem
condição material distinta seria ocupar espaço do catálogo por simetria.

## 8. Correção da auditoria independente — candidato `d81cc73d` rejeitado

O primeiro candidato da cadeia 96, `d81cc73d7ec926d98276a60c0afbeef501d8b723`,
foi **rejeitado** pela auditoria independente com quatro achados. Ele
não é apagado desta história: foi corrigido por `git commit --amend`,
sem criar cadeia 97, e permanece nomeado aqui.

```text
INVALID_CANDIDATE_AMEND != EDIT_PUBLISHED_HISTORY
```

### A1 — o repositório desfazia a transação do chamador

**Causa.** O caminho concorrente de `append()` capturava `IntegrityError`
e chamava `Session.rollback()`. O repositório declara que a
`UnitOfWork` é dona da transação, e um rollback integral desfaz também
escritas anteriores e não relacionadas do chamador.

**Prova anterior.** `UNRELATED_ROWS_AFTER_INTEGRITY_PATH = 0` — uma
escrita feita antes do append desaparecia.

**Correção.** O INSERT tentativo passou a viver num `SAVEPOINT`
(`Session.begin_nested`), que desfaz **apenas a si mesmo**.

```text
SAVEPOINT_SCOPE != TRANSACTION_SCOPE
ANY_INTEGRITY_ERROR != IDENTITY_COLLISION
```

`_e_colisao_de_identidade` exige `sqlstate 23505` **e** o nome da chave
primária; qualquer outra violação sobe como erro real, porque mascarar
incoerência numa tabela append-only a tornaria permanente. Quando o
snapshot não enxerga a linha vencedora — típico de `REPEATABLE READ` —
o sinal é propagado para o chamador repetir numa transação nova. Nenhum
`commit()` e nenhum `rollback()` de sessão restaram no repositório.

**Prova posterior.** `i31` e `i32` medem que a escrita não relacionada
sobrevive ao replay idêntico e ao conflito; `i33` alcança a rota do
savepoint por subclasse controlada e confirma a linha vencedora; `i34`
observa a sessão e prova zero `commit`/`rollback`; `i29` prova a
propagação sob `REPEATABLE READ` com a escrita anterior intacta. Guarda
`g09` e mutante bilateral `g99_9` distinguem `begin_nested` de
`rollback`.

### A2 — `TRUNCATE` contornava o append-only

**Causa.** A migration protegia apenas `BEFORE UPDATE OR DELETE … FOR
EACH ROW`. No PostgreSQL, `TRUNCATE` não dispara trigger de linha e
exige trigger própria, que só existe em `FOR EACH STATEMENT`.

```text
ROW_TRIGGER_DOES_NOT_SEE_TRUNCATE
```

**Prova anterior.** `TRUNCATE validated_experiences` aceito — a tabela
append-only inteira apagável sem encontrar recusa.

**Correção.** Segunda trigger `BEFORE TRUNCATE … FOR EACH STATEMENT`,
reutilizando a mesma função de recusa (`TG_OP` já nomeia a operação
tentada). O downgrade remove as **duas** triggers antes da função, e
continua recusando antes de qualquer DDL quando há dados.

**Prova posterior.** `i35` mede as três operações recusadas com linhas e
schema intactos; `i36` exige exatamente os dois gatilhos; `g10` lê a
estrutura do comando SQL e `g99_10` tem um mutante por operação
removida.

Não se alega proteção contra superusuário que desabilite triggers
deliberadamente. A garantia é contra SQL normal fora do repositório.

### A3 — `evidence_refs` era um canal `JSONB` aberto

**Causa.** O domínio validava o lastro; a coluna impunha só `NOT NULL`.

```text
APP_TYPED_BOUNDARY != DATABASE_INTEGRITY
JSONB_NOT_NULL     != CLOSED_EVIDENCE_SCHEMA
```

**Prova anterior.** SQL bruto persistia array vazio e
`[{"kind":"x","ref":"nao-uuid","url":"http://…","credential":"…"}]`.
Numa tabela append-only, a linha ficaria permanente.

**Correção.** Função `IMMUTABLE`
`validated_experience_evidence_is_canonical`, chamada por `CHECK` — que
não aceita subconsulta —, impondo os nove invariantes: array, não
vazio, elemento objeto, **chaves exatamente** `kind` e `ref`,
vocabulário fechado, UUID canônico, sem duplicata, ordem canônica e
evidência primária presente no conjunto. A ordem estritamente crescente
cobre duplicata e ordenação de uma vez. Recusa, nunca normaliza em
silêncio; nenhum campo extra é descartado.

**Prova posterior.** `i37` recusa treze payloads inválidos por SQL bruto
com zero linhas em cada caso; `i38` aceita o canônico. `g11` exige os
nove invariantes e `g99_11` tem mutante para não-vazio, chaves exatas e
vínculo da primária.

### A4 — a consulta por critério perdia `criterion_origin`

**Causa.** `list_by_criterion()` e o índice usavam apenas chave e
versão, misturando critérios `PUBLISHED` e `DECLARED` de mesma
chave/versão.

```text
PARTIAL_REFERENCE_QUERY != EXACT_CRITERION_BINDING
```

**Correção.** A assinatura passou a receber a `CriterionReference`
**integral** — e não três argumentos soltos, porque o tipo garante que
as três dimensões viajam juntas e nenhum chamador omite a origem por
engano. O índice acompanha o filtro.

**Prova posterior.** `i05_1` mostra duas linhas coexistindo e cada
consulta devolvendo só a sua origem; `i05_2` recusa referência parcial;
`g12` mede as três dimensões no filtro e `g99_12` tem mutante por
dimensão faltante.

### Correção do instrumento de caracterização

A sonda `DB_IMMUTABILITY_NOT_ENFORCED` aceitava
`CREATE TRIGGER` + `BEFORE UPDATE OR DELETE` e produziu um falso `0/9`
apesar do escape por `TRUNCATE`. Ela passou a exigir as três operações,
lendo a **estrutura** do comando — `BEFORE`, `ON <tabela>` e as
operações entre as duas —, e reproduz o defeito no candidato rejeitado.
A contagem de sondas permanece nove.

### Dois defeitos meus, encontrados durante a correção

As provas do A1 gravavam `MemoryDomain` sem limpar, e isso bloqueava o
downgrade de `memory_domains`: dez testes de round trip da E3 e da E4.1
reprovaram. Removo apenas as linhas com o prefixo dos meus testes.

E `validated_experiences` fora incluída em `_E4_TABLES` do `pi13`, lista
que também alimenta a fixture de `TRUNCATE` — agora corretamente
recusado.

```text
APPEND_ONLY_TABLE != TRUNCATABLE_FIXTURE_TABLE
```

Separei numa constante própria. Desativar a trigger para limpar seria
contornar o que ela existe para provar.

---

## 9. Achados da implementação

**A1 — o candidato de comparação não podia entrar na sessão.** A
primeira versão chamava `session.expunge` sobre um objeto **transitório**
que nunca fora adicionado, e o SQLAlchemy recusou. A correção não foi
adicioná-lo: foi reconhecer que verificar conflito não pode tocar a
sessão. `ZERO_OVERWRITE` começa por não escrever nem para comparar.

**A2 — `created_at` sem `server_default` na migration.** O `TimestampMixin`
delega os carimbos ao banco (`server_default=func.now()`), e a migration
declarava as colunas apenas `NOT NULL`. O INSERT quebrava com
`NotNullViolation` — defeito meu, pego no primeiro append real.

**A3 — a guarda de consumo não podia exigir zero imports.** Model, schema
e repositório importam o contrato porque **são** a fronteira. Exigir zero
imports mediria a existência da fatia, não o risco. A guarda passou a
medir `AUTHORIZED_CONSUMERS` explícitos e
`BEHAVIORAL_CONSUMERS_OUTSIDE_BOUNDARY = 0`, por chamada e por
ramificação — `IMPORT != BEHAVIOR`.

**A4 — a limpeza dos testes precisou desativar a trigger.** A trigger
recusa `DELETE` inclusive para o `TRUNCATE` de fixture. Uso
`session_replication_role = replica`, escopado à sessão do teste, e
declaro: é mecanismo de teste, não de produção — a garantia continua
medida em `i13`, com SQL arbitrário recusado.

## 10. Compatibilidade — Master v2.4

### `PIA_OS_SOPHIA_MASTER_COMPATIBILITY`

```text
USER_AUTHORITY_PRESERVED                        PASS  registro não decide nada
SOPHIA_BRAND_PIA_OS_CODEBASE_PRESERVED          PASS
MODULE_SCOPE_AND_DEFERRED_CAPABILITIES_DECLARED PASS  §2, §6 e §10
SCHEDULE_MODE_DECLARED                          PASS  nenhum scheduler criado
AI_ROLE_AND_STEP_INSTRUCTION_DISTINGUISHED      PASS  o modelo não valida
PROVIDER_CONNECTION_METHOD_DECLARED             PASS  nenhum conector criado
AUTOMATION_SCOPE_DECLARED                       PASS  nenhum registro automático
APPROVAL_GATES_DECLARED                         PASS  não consome aprovação
PERSISTENCE_BEHAVIOR_DECLARED                   PASS  persistência do REGISTRO,
                                                      distinta de persistência de
                                                      mudança comportamental
MULTI_AI_RESULT_ATTRIBUTION_DECLARED            PASS  validated_by + origin_ref
DIVERGENCE_PRESERVATION_DECLARED                PASS  conflito explícito, sem vencedor
CONCURRENT_WORK_ISOLATION_DECLARED              PASS  provado em duas sessões
BACKGROUND_EXECUTION_AUTHORIZATION_DECLARED     PASS  nenhum worker criado
RESOURCE_LIMITS_QUEUE_AND_COST_DECLARED         PASS  nenhuma fila criada
REMOTE_RESOURCE_SCOPE_DECLARED                  PASS  nenhum recurso remoto
OBSERVATION_PREPARATION_EXECUTION_DISTINGUISHED PASS  registro é observação
CREDENTIAL_AND_SECRET_BOUNDARY_DECLARED         PASS  evidência é UUID
FAILURE_ROLLBACK_AND_CONCURRENCY_DECLARED       PASS  §4
CURRENT_CAPABILITY_NOT_OVERSTATED               PASS  transporte declarado ausente
FROZEN_MODULES_UNCHANGED                        PASS  E3 e E4.1-E4.10 intactas
```

### `SOPHIA_UX_COMPATIBILITY`

```text
USER_AUTHORITY_PRESERVED                          PASS
SCHEDULE_MODE_DECLARED                            PASS  nenhum, e nenhum será criado
AUTOMATION_SCOPE_DECLARED                         PASS  nenhuma automação
PERSISTENCE_BEHAVIOR_DECLARED                     PASS  registro, não comportamento
PROVIDER_NEUTRALITY_PRESERVED                     PASS  nenhum provedor citado
PERSONALIZATION_REVERSIBLE                        NOT_APPLICABLE  sem UX, e nenhuma
                                                  será criada
CONCURRENT_WORK_ISOLATION_DECLARED                PASS
BACKGROUND_EXECUTION_AUTHORIZATION_DECLARED       PASS  nenhuma
RESOURCE_LIMITS_AND_QUEUE_DECLARED                PASS  nenhuma fila
AI_ROLE_CONTROL_DECLARED                          NOT_APPLICABLE  sem superfície
ROLE_AND_STEP_INSTRUCTION_DISTINGUISHED           NOT_APPLICABLE  sem superfície
PIA_SEQUENCE_SUGGESTION_BEHAVIOR_DECLARED         NOT_APPLICABLE  nenhuma sugestão
MULTI_AI_RESULT_ATTRIBUTION_DECLARED              PASS  atribuição sem autenticação
PIA_INTEGRATION_DIVERGENCE_PRESERVATION_DECLARED  PASS
POST_RESULT_USER_COMMAND_DECLARED                 NOT_APPLICABLE  sem superfície
RESULT_APPROVAL_AND_PERSISTENCE_DISTINGUISHED     PASS  validar != selecionar
FROZEN_MODULES_UNCHANGED                          PASS
```

### Parte III §13 — impacto sobre distinções

Nenhuma distinção é extinta. Repetição permanece distinguível de replay;
atribuição permanece distinguível de autenticação; validação permanece
distinguível de seleção.

```text
DISTINCTION EXTINCTION != HISTORICAL ERASURE
```

## 11. Riscos declarados

- **(a)** `validated_by` e `origin_ref` são **atribuídos**. Nada os
  verifica, e o registro não afirma que verifica.
- **(b)** O `outcome_token` só significa alguma coisa lido contra o
  critério; um critério mal identificado torna o token inútil, e o
  registro não pode impedir isso.
- **(c)** Sem FK, uma referência pode apontar para identidade que não
  existe neste banco — decisão consciente, e o preço da evidência sobre
  objeto removido.
- **(d)** O transporte não existe. Um registro importado por meio não
  previsto não passaria por nenhuma garantia desta fatia.
- **(e)** A tabela cresce sem política de retenção própria; retenção de
  evidência é questão da E4.9 e não foi estendida aqui.
- **(f)** A tabela é append-only inclusive contra `TRUNCATE`; um resíduo
  nela reprova todo teste de round trip de migration do projeto. Nenhum
  teste deixa linha para trás, mas um banco sujo reprova a suíte.
- **(g)** A recusa de `UPDATE`/`DELETE`/`TRUNCATE` vale contra SQL
  normal. Superusuário que desabilite triggers deliberadamente não é
  coberto, e isso não é alegado.
- **(h)** Ausência de achado adicional não é prova de ausência de
  defeito.

## 12. O que continua não existindo

```text
LEARNING_ENGINE = NONE
SELECTION = NONE
RANKING = NONE · SCORE = NONE · RECOMMENDATION = NONE
AUTOMATIC_PROMOTION = NONE
BEHAVIORAL_CONSUMER = NONE
TRANSPORT = DEFERRED
PUBLIC_API = NONE · SCHEDULER = NONE · QUEUE = NONE
AUTHENTICATOR = NONE
```

A E4.11 entrega a estrutura de registro e **nada** que a consuma.

`PASS_FINAL` pertence à auditoria independente e não é declarado aqui.
