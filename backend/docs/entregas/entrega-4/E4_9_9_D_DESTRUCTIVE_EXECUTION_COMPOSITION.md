# E4.9.9.d — Composição Final da E4.9

`DestructiveExecutionService`, alinhamento textual do identificador de
regra e validação prática em sandbox.

```text
E4_9_9_D = COMPLETE_CANDIDATE
E4_9_INTERNAL_COMPOSITION = COMPLETE_CANDIDATE
E4_9_PRACTICAL_SANDBOX_VALIDATION = COMPLETE_CANDIDATE
PRODUCTION_EFFECT_ADAPTER = NONE
AUTHENTICATOR = NONE
PUBLIC_API = NONE
REAL_USER_FILE_ERASURE = NOT_EXECUTED
E4_9 = AWAITING_FINAL_INDEPENDENT_AUDIT
E4_10 = NOT_STARTED
PASS_FINAL = NOT_DECLARED
```

---

## 1. O que esta fatia faz

Compõe, pela primeira vez, os contratos já aprovados da E4.9:

```text
aprovação persistida
→ re-resolução fresca e observacional
→ comparação com o snapshot aprovado
→ consumo durável e atômico
→ tentativa pela porta de efeito
→ recibo somente após tentativa material observada
```

Até a cadeia 93, `resolve_target`, `consume_once`, `attempt_effect` e
`append_observed` existiam **sem chamador**. Era o estado correto:
compor um escritor de recibo antes de existir resolvedor, aprovação e
efeito criaria um caminho capaz de fabricar recibos de apagamentos que
nunca aconteceram.

```text
INTERNAL_COMPOSITION_COMPLETE != PRODUCTION_DELETION_AVAILABLE
TEST_SANDBOX_EFFECT != PRODUCTION_EFFECT_ADAPTER
```

## 2. Escopo entregue

Produção — três arquivos novos, quatro tocados, uma migration:

```text
NOVO   app/memory/models/destructive_execution_enums.py
NOVO   app/memory/schemas/destructive_execution.py
NOVO   app/memory/services/destructive_execution_service.py
NOVO   alembic/versions/d5b31f7a08c4_...e4_9_9_d.py
TOCADO app/memory/errors/codes.py            PIA-8047, PIA-8048, PIA-8049
TOCADO app/memory/errors/exceptions.py       três exceções tipadas
TOCADO app/memory/models/erasure_record.py   governance_rule_id -> texto
TOCADO app/memory/schemas/erasure_record.py  append e view -> texto
```

Nenhum adaptador concreto, conector, autenticador, endpoint, worker,
scheduler, fila, outbox ou saga. Nenhuma alteração na E3 nem na E4.3.

## 3. Correção de compatibilidade do recibo

```text
OPAQUE_RULE_REFERENCE != UUID
FABRICATED_RULE_IDENTITY = FORBIDDEN
```

`GovernanceResolution.matched_rule_id` é `str` desde a E4.3 e recebe
valores como `"rule-1"`. `ErasureRecordAppend.governance_rule_id` exigia
`UUID`. As três saídas óbvias — converter, sortear, derivar por hash —
inventam uma identidade de regra que não existe. A quarta é esta: o
recibo cita a regra **como a governança a nomeia**.

Migration `d5b31f7a08c4`, sucessora de `a1f7c2d40e93`:

- **upgrade** — `USING governance_rule_id::text` grava a representação
  canônica do UUID existente, byte a byte;
- **downgrade** — mede **antes de qualquer DDL** e recusa alto quando
  existe valor não-UUID.

```text
REFUSE_BEFORE_ALTER, NEVER_MID_MIGRATION
IRREVERSIBLE_BY_DATA != IRREVERSIBLE_BY_SCHEMA
DOWNGRADE_REFUSES_LOUDLY, NEVER_SILENTLY_TRUNCATES
```

A primeira versão derrubava o `CHECK` e só então media; um downgrade
impeditivo deixaria o schema alterado e a migration abortada — estado
que nenhum dos dois lados descreve. `i18` mede tipo de coluna,
constraint, valor do recibo e revisão corrente **depois** da recusa: os
quatro intactos.

## 4. Ordem canônica e o contrato at-most-once

```text
CONSUMPTION_COMMITTED_BEFORE_EFFECT = REQUIRED
FLUSHED_CONSUMPTION != DURABLE_CONSUMPTION
EFFECT_BEFORE_CONSUMPTION_COMMIT = FORBIDDEN
NO_MATERIAL_ATTEMPT -> NO_ERASURE_RECORD
OBSERVED_ATTEMPT -> EXACTLY_ONE_ERASURE_RECORD
EFFECT_EXCEPTION -> UNKNOWN_STATE, NEVER_INVENTED_RECEIPT
REPLAY_WITH_SAME_APPROVAL = REFUSED
CRASH_AFTER_CONSUMPTION_MAY_BURN_APPROVAL = DECLARED
CRASH_DURING_EFFECT_MAY_LEAVE_UNKNOWN_STATE = DECLARED
```

Efeito externo e banco **não** são atomicamente transacionais, e não há
tentativa de fingir que são. O consumo commita antes do efeito porque a
falha aceitável é queimar uma aprovação sem apagar nada; a inaceitável é
apagar e não ter registro de que a autorização foi usada.

As três fases vivem numa única função (`execute`) de propósito:
`commit()` precede `attempt_effect` **lexical e estruturalmente**, e a
guarda `g03` mede a ordem por `(lineno, col_offset)`.

## 5. Três erros tipados, e por que não são um

```text
PIA-8047  porta levantou exceção        estado material DESCONHECIDO
PIA-8048  porta respondeu sobre outro   adaptador INCOERENTE
PIA-8049  efeito observado, recibo não  estado CONHECIDO, evidência ausente
```

Fundi-los apagaria distinções que exigem investigações opostas. Os três
interrompem o lote, preservam a aprovação consumida, preservam os
recibos já confirmados e **não** fabricam recibo para o alvo afetado.

`PIA-8049` foi acrescentado durante a fatia: o resultado agregado só
lista recibos cujo commit próprio terminou, e um `TransactionError` cru
perderia a evidência do que já era fato.

## 6. Achados materiais desta fatia

**A1 — invariante de lote incompleto (defeito meu, pego por teste).**
`PreConsumptionRefusal` exemptava da exigência de `position` apenas
`BATCH_CARDINALITY_MISMATCH`. A composição teria levantado `ValueError`
ao recusar por `GOVERNANCE_PROVENANCE_INCOMPLETE`. Corrigido com
`RAZOES_DE_LOTE` enumerado literalmente; membro novo cai no ramo que
**exige** posição, que é o lado seguro.

**A2 — a checagem de proveniência é segunda camada.** MEDIDO:
`GovernanceResolution` já exige proveniência local completa quando o
desfecho é `ADMISSIBLE`, e a proposta destrutiva exige `ADMISSIBLE`.
Nenhum envelope canônico chega ao serviço com campo ausente.

```text
SECOND_LAYER_UNREACHABLE_BY_CANONICAL_ENVELOPE
UNREACHABLE_TODAY != UNNECESSARY
```

Não removida e não coberta por pragma: alcançada por **subclasse
controlada** (construção legítima, sem `object.__setattr__` nem
monkeypatch), com `s12_1` provando que a primeira camada existe. Mesma
disciplina de `u15`/`u48` na E4.9.9.b.

**A3 — `cast` evitado por estreitamento de tipo.** O predicado booleano
de proveniência deixava os quatro campos `Optional` na montagem do
recibo, e o mypy acusou quatro erros novos. A saída não foi `cast` nem
`type: ignore`: `GovernanceProvenance` é o estreitamento, e ou existe
com os quatro valores, ou a composição recusa antes do efeito.

**A4 — ponto cego do próprio instrumento de caracterização.** A sonda de
referência procurava `ast.Name`, `ast.Attribute` e `ImportFrom` — e
`class X` não é nenhum dos três, então o módulo que **define** o símbolo
não era detectado. `DEFINITION_IS_ALSO_A_REFERENCE`. Corrigido, e a
cadeia 93 foi **re-medida** num clone de `4aa08cd2` com o instrumento já
corrigido: 9/9 preservado, não herdado.

**A5 — guarda por substring acusou a própria prosa.** `g05_1` procurava
`type: ignore` no arquivo inteiro e reprovou a docstring que **explica**
por que o estreitamento existe para não precisar dele. Uma guarda que
proíbe falar do problema é a guarda errada. Passou a ler **tokens**:
só `COMMENT` é supressão. `MENTIONED_IN_PROSE != APPLIED_AS_SUPPRESSION`.

**A6 — `i30` usava passo relativo.** `downgrade("-1")` passou a remover a
migration errada assim que uma sucessora nasceu — o mesmo defeito que a
E4.9.9.a corrigiu em `i21` e que sobreviveu ali. Alvo agora explícito.
`RELATIVE_STEP != NAMED_TARGET`.

**A7 — contaminação de estado de logging.** `tests/system/` executa
Alembic no processo do pytest, e `fileConfig(disable_existing_loggers=
True)` derrubou doze testes E1/E2 coletados depois. `conftest.py` com a
mesma proteção autouse de E3.6.1d e E4.1.

## 7. Guardas envelhecidas — quinze revisadas uma a uma

Onde a guarda exigia **zero** consumidores, passou a exigir
**exatamente os autorizados, nomeados** — mais forte, porque um segundo
consumidor passaria numa versão apenas relaxada com `permitidos`.

Três renomeadas (`GUARD_NAME != GUARD_MEASUREMENT`, décima segunda
ocorrência): de "a fatia d não começou" para a capacidade que de fato
permanece ausente — nenhuma classe de produção implementa
`resolve_target` ou `attempt_effect` com corpo vivo. A guarda da
retenção passou a medir algo que nem mencionava: o serviço **não**
importa `avaliar_retencao`.

```text
RETENTION_ASSESSMENT != DELETION_AUTHORITY
LEGACY_PROTECTION = USER_BINDING, NOT AUTOMATIC_EFFECT
```

## 8. Validação prática — o que ela prova e o que não prova

PostgreSQL real, arquivos reais em `tmp_path`, adaptadores
exclusivamente em `backend/tests/`.

```text
PROVED      composição interna e ordem das garantias
NOT_PROVED  adaptador de produção, autenticador, API, conector
```

`p13` é o caso central de confinamento: o symlink aponta para dentro da
raiz quando o resolvedor o observa e é trocado para fora **entre** a
resolução e o efeito.

```text
RESOLUTION_TIME_CHECK != EFFECT_TIME_CHECK
TOCTOU_CLOSED_AT_THE_MATERIAL_POINT
```

Só a revalidação por `realpath` no instante material fecha a janela.

## 9. Compatibilidade — Master v2.4

### `PIA_OS_SOPHIA_MASTER_COMPATIBILITY` (20)

```text
USER_AUTHORITY_PRESERVED                        OK  aprovação humana é a única autoridade
SOPHIA_BRAND_PIA_OS_CODEBASE_PRESERVED          OK  nenhuma renomeação
MODULE_SCOPE_AND_DEFERRED_CAPABILITIES_DECLARED OK  §2 e §8
SCHEDULE_MODE_DECLARED                          OK  SCHEDULER = NONE
AI_ROLE_AND_STEP_INSTRUCTION_DISTINGUISHED      OK  o modelo não executa nem autoriza
PROVIDER_CONNECTION_METHOD_DECLARED             OK  nenhuma; porta injetada
AUTOMATION_SCOPE_DECLARED                       OK  nenhuma execução automática
APPROVAL_GATES_DECLARED                         OK  consume_once atômico
PERSISTENCE_BEHAVIOR_DECLARED                   OK  §4
MULTI_AI_RESULT_ATTRIBUTION_DECLARED            NOT_APPLICABLE_TO_RUNTIME
DIVERGENCE_PRESERVATION_DECLARED                OK  divergência recusa, não normaliza
CONCURRENT_WORK_ISOLATION_DECLARED              OK  i21
BACKGROUND_EXECUTION_AUTHORIZATION_DECLARED     OK  nenhuma execução em segundo plano
RESOURCE_LIMITS_QUEUE_AND_COST_DECLARED         OK  QUEUE = NONE
REMOTE_RESOURCE_SCOPE_DECLARED                  OK  nenhum recurso remoto
OBSERVATION_PREPARATION_EXECUTION_DISTINGUISHED OK  fases A, B e C
CREDENTIAL_AND_SECRET_BOUNDARY_DECLARED         OK  g12, u46, p17
FAILURE_ROLLBACK_AND_CONCURRENCY_DECLARED       OK  §5
CURRENT_CAPABILITY_NOT_OVERSTATED               OK  §8
FROZEN_MODULES_UNCHANGED                        OK  E3 e E4.3 intactos
```

### `SOPHIA_UX_COMPATIBILITY` (17)

```text
USER_AUTHORITY_PRESERVED                          OK
SCHEDULE_MODE_DECLARED                            OK  nenhum
AUTOMATION_SCOPE_DECLARED                         OK  nenhuma
PERSISTENCE_BEHAVIOR_DECLARED                     OK
PROVIDER_NEUTRALITY_PRESERVED                     OK  capability.operation é opaco
PERSONALIZATION_REVERSIBLE                        NOT_APPLICABLE  sem UX nesta fatia
CONCURRENT_WORK_ISOLATION_DECLARED                OK
BACKGROUND_EXECUTION_AUTHORIZATION_DECLARED       OK  nenhuma
RESOURCE_LIMITS_AND_QUEUE_DECLARED                OK  nenhuma fila
AI_ROLE_CONTROL_DECLARED                          OK
ROLE_AND_STEP_INSTRUCTION_DISTINGUISHED           OK
PIA_SEQUENCE_SUGGESTION_BEHAVIOR_DECLARED         NOT_APPLICABLE
MULTI_AI_RESULT_ATTRIBUTION_DECLARED              NOT_APPLICABLE_TO_RUNTIME
PIA_INTEGRATION_DIVERGENCE_PRESERVATION_DECLARED  OK
POST_RESULT_USER_COMMAND_DECLARED                 NOT_APPLICABLE  sem superfície
RESULT_APPROVAL_AND_PERSISTENCE_DISTINGUISHED     OK  aprovação != recibo
FROZEN_MODULES_UNCHANGED                          OK
```

### Multicanal v1.3 (10)

```text
PIA_OS_INPUT_CHANNELS = TEXT | VOICE                        OK  s35, p11
SAME_COMMAND_ENVELOPE_FOR_ALL_CHANNELS = TRUE               OK
SAME_GOVERNANCE_PIPELINE_FOR_ALL_CHANNELS = TRUE            OK
VOICE_IS_AUTHORITY = FALSE                                  OK
TRANSCRIPTION_IS_COMMAND_CANDIDATE                          OK  não chega à porta
CHANNEL != AUTHORITY                                        OK
DESTRUCTIVE_ACTION_REQUIRES_EXPLICIT_CONFIRMED_INTENT       OK  envelope
DESTRUCTIVE_VOICE_COMMAND_REQUIRES_REVIEW = TRUE            OK  VoiceReviewState
CONFIRMATION_BINDS_ACTION_TARGET_SCOPE_AND_IMPACT = TRUE    OK  binding completo
ASR_ERROR_MUST_NOT_BECOME_CONSENT = TRUE                    OK  fronteira anterior
```

```text
MULTI_AI_HANDOFF_COMPATIBILITY = NOT_APPLICABLE_TO_RUNTIME
E4_INTEGRATION_OF_COUT_P = FORBIDDEN
MOBILE_PROFILE = NOT_DECLARED
```

### Parte III §13 — impacto sobre distinções

Nenhuma distinção é extinta. O recibo preserva `SUCCEEDED`, `FAILED` e
`PARTIAL` separados; não-tentativa e tentativa observada permanecem
tipos disjuntos; recusa pré-consumo, recusa de consumo e relatório são
três desfechos que não colapsam.

```text
DISTINCTION EXTINCTION != HISTORICAL ERASURE
ACCESSIBILITY != EXISTENCE
```

## 10. Riscos declarados

- **(a)** `SUCCEEDED` é escopo controlado confirmado pelo adaptador, e
  **não** prova de desaparecimento em toda réplica, backup ou cache.
- **(b)** A evidência de consumo é representada; quem observa o banco é o
  serviço, e o adaptador recebe a afirmação, não a prova.
- **(c)** `AUTHENTICATOR = NONE`. `IdentityEvidence` continua
  representando e não verificando identidade.
- **(d)** Queda entre o commit do consumo e o efeito queima a aprovação
  sem apagar nada — declarado, não mitigado.
- **(e)** A checagem de proveniência de governança é hoje inalcançável
  por envelope canônico; entra em uso se a E4.3 relaxar.
- **(f)** O confinamento do sandbox é do **adaptador de teste**. Um
  adaptador de produção futuro precisará da própria revalidação no ponto
  material; nada aqui a fornece.
- **(g)** A conversão textual acopla o recibo ao contrato da E4.3: se
  `matched_rule_id` mudar de forma, o recibo herda.
- **(h)** Ausência de achado adicional **não** é prova de ausência de
  defeito.

## 11. O que continua não existindo

```text
PRODUCTION_EFFECT_ADAPTER = NONE
TARGET_RESOLVER_ADAPTER = NONE
AUTHENTICATOR = NONE
PUBLIC_API = NONE
SCHEDULER = NONE
QUEUE = NONE
REAL_USER_FILE_ERASURE = NOT_EXECUTED
```

`PASS_FINAL` pertence à auditoria independente e não é declarado aqui.
