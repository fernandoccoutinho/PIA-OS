# EDR E4.9.9.c.1 — Correção consolidada das invariantes do avaliador

**Natureza:** corretivo pós-auditoria de **dois defeitos materiais** na
fronteira pública. **Baseline:** cadeia 92 (`66696129`). **Saída:** cadeia 93.

```text
COLLECTION_TYPE_CHECK != CANONICAL_COLLECTION_VALIDATION
UNIQUE_RULE_ID_REQUIRED_BEFORE_DICTIONARY_INDEXING
CORRECT_FACTORY_OUTPUT != SAFE_PUBLIC_RESULT_CONSTRUCTOR
PUBLIC_RESULT_CONSTRUCTOR_ENFORCES_DECISION_MATRIX
```

```text
E4_9_9_C_1 = COMPLETE_CANDIDATE
E4_9_9_C   = AWAITING_INDEPENDENT_REAUDIT
E4_9_9_D   = NOT_STARTED
MIGRATION_DELTA = 0   API_DELTA = 0   EFFECT_DELTA = 0
PASS_FINAL = NOT_DECLARED
```

---

## 1. A1 — a coleção de regras contornava o validador canônico

`avaliar_retencao` verificava `isinstance(rules, tuple)` e o tipo de cada
item, e eu apresentei isso como validação da coleção.

```text
COLLECTION_TYPE_CHECK != CANONICAL_COLLECTION_VALIDATION
```

`validar_regras_retencao` é o contrato **único** desde a E4.9.6.2 e recusa
`rule_id` duplicado. O avaliador **precisa** disso, porque indexa
vencimentos por `rule_id`:

```python
vencimentos = {regra.rule_id: due_at ...}
```

Com duplicata, o dicionário sobrescreve, e a **ordem de declaração** passa
a mudar a decisão. Reproduzido na cadeia 92:

```text
(365 dias, 30 dias) mesmo rule_id, aos 60 dias -> ASSESS_AND_INFORM
(30 dias, 365 dias) mesmo rule_id, aos 60 dias -> NOT_YET_DUE
ORDER_CHANGES_DECISION = True
```

Violava simultaneamente três invariantes que eu havia declarado:

```text
DUPLICATE_RULE_ID = FORBIDDEN
SHORT_RULE_MUST_NOT_NEUTRALIZE_LONG_RULE
RULE_ORDER_MUST_NOT_CHANGE_DECISION
```

### 1.1 Correção

```text
NON_EMPTY_RULES → CANONICAL_VALIDATOR
EMPTY_RULES     → OUT_OF_SCOPE
```

`validar_regras_retencao` é **reutilizada**, não copiada — duas fontes da
mesma regra divergiriam na primeira mudança. `s15` prova que a lógica de
unicidade não foi reimplementada.

A coleção vazia é tratada antes: é legítima e significa `OUT_OF_SCOPE`,
enquanto o validador canônico exige regra. Ausência de regra continua sem
virar elegibilidade nem erro (`u39`).

Na cadeia 93 as duas ordens falham com o **mesmo** erro de domínio, antes
de qualquer cálculo de prazo (`u37`):

```text
DUPLICATE_ORDER_OUTCOMES = ['REFUSED', 'REFUSED']
ORDER_CHANGES_DECISION = False
NOMINAL_PATH_PRESERVED = True
```

### 1.2 Por que meus testes não pegaram

`u14` alegava que a ordem não altera o resultado — verdade **com
`rule_id` distintos**, o único caso que exercitei. A duplicata é
exatamente onde o dicionário perde uma entrada, e nunca a construí.

```text
TESTED_CASE != TESTED_PROPERTY
```

`s11` também: provei que uso `max` e não `min`, o que é verdade. Mas
`max` sobre um dicionário que já perdeu uma entrada não é o máximo das
regras aplicáveis — a guarda media a **função** certa sobre a **coleção**
errada.

---

## 2. A2 — o construtor público aceitava estados impossíveis

```text
CORRECT_FACTORY_OUTPUT != SAFE_PUBLIC_RESULT_CONSTRUCTOR
```

A função de avaliação produzia resultados corretos, e eu tratei isso como
prova de que o contrato era coerente. O construtor **direto** aceitava,
entre outros, `ASSESS_AND_INFORM` sem fundamento algum, `OUT_OF_SCOPE`
**com** fundamento, `rule_id` não textual, prazo no lado temporal errado
e identificadores duplicados. Objetos assim pareciam resultados válidos.

É a nona vez que o projeto aplica a lição de que invariante em fábrica é
contornável pelo construtor direto — e desta vez fui eu quem a esqueceu,
no mesmo módulo cuja docstring de `RetentionRule` a enuncia.

### 2.1 A matriz, imposta no construtor

| Decisão | `applicable` | `due` | `effective_due_at` | `next_due_at` | temporal |
|---|---|---|---|---|---|
| `POLICY_NOT_EFFECTIVE` | `()` | `()` | `None` | `None` | — |
| `OUT_OF_SCOPE` | `()` | `()` | `None` | `None` | — |
| `PRESERVE_LEGACY_PROTECTED` | `≠ ()` | `⊆ applicable` | `≠ None` | `None` | **nenhuma** |
| `NOT_YET_DUE` | `≠ ()` | `⊆ applicable` | `≠ None` | `= effective` | `effective > evaluated` |
| `ASSESS_AND_INFORM` | `≠ ()` | `= applicable` | `≠ None` | `None` | `effective ≤ evaluated` |

Duas células merecem registro:

**`PRESERVE_LEGACY_PROTECTED` não impõe relação temporal.** Item
protegido pode estar antes **ou** depois do prazo, e a proteção vale nos
dois casos. Exigir uma relação aqui inventaria regra que a E4.9.8.3 não
estabeleceu (`u43`).

**`ASSESS_AND_INFORM` exige `due == applicable`.** Como o prazo efetivo é
o **máximo**, vencê-lo implica que todas as aplicáveis venceram
individualmente. Um objeto com `due ⊂ applicable` nesta decisão seria
aritmeticamente impossível.

### 2.2 Identificadores

Cada item das duas tuplas passa pelo **mesmo** `validar_identificador_opaco`
já usado por `rule_id` — não um paralelo mais frouxo (`s17`). Sem
duplicata, sem `set`, sem normalização, ordem preservada.

### 2.3 O ramo final ficou explícito

`ASSESS_AND_INFORM` era o `else` implícito, e `s16` — que exige as cinco
decisões citadas — falhou por isso. Tornei o ramo explícito em vez de
afrouxar a guarda: a matriz ficou legível e a guarda voltou a medir o que
promete.

---

## 3. Garantias por camada

| Garantia | Camada | Prova |
|---|---|---|
| duplicata recusada nas duas ordens | `APPLICATION_LEVEL` | `u36`, `u37` |
| validador canônico reutilizado, não copiado | `AUDIT_LEVEL` | `s14`, `s15`, `s99_3` |
| `rules=()` continua `OUT_OF_SCOPE` | `APPLICATION_LEVEL` | `u39` |
| ordem declarada preservada | `APPLICATION_LEVEL` | `u40` |
| matriz das cinco no construtor público | `APPLICATION_LEVEL` | `u42`, `u44` |
| cobertura das cinco decisões na matriz | `AUDIT_LEVEL` | `s16`, `s99_4` |
| ids opacos, únicos, ordenados | `APPLICATION_LEVEL` | `u45`, `u46` |
| `replace` revalida | `APPLICATION_LEVEL` | `u47` |
| caminho nominal 30/365 inalterado | `APPLICATION_LEVEL` | `u41` |
| ausência de scheduler, efeito, consumidor | `AUDIT_LEVEL` | `s01`–`s13` |

Nenhuma recebeu `CLOSED` por declaração documental.

---

## 4. Master Integrado v2.4

### 4.1 `PIA_OS_SOPHIA_MASTER_COMPATIBILITY` — 20 linhas

```text
 1 USER_AUTHORITY_PRESERVED ....... REFORÇADO: a ordem de declaração das
     regras deixa de alterar o que se informa ao usuário.
 2 SOPHIA_BRAND_PIA_OS_CODEBASE ... SIM.
 3 MODULE_SCOPE_AND_DEFERRED ...... Corretivo confinado aos dois defeitos.
     Diferidos: todos os da E4.9.9.c.
 4 SCHEDULE_MODE_DECLARED ......... NOT_APPLICABLE.
 5 AI_ROLE_AND_STEP_INSTRUCTION ... NOT_APPLICABLE.
 6 PROVIDER_CONNECTION_METHOD ..... NOT_APPLICABLE.
 7 AUTOMATION_SCOPE_DECLARED ...... NENHUMA.
 8 APPROVAL_GATES_DECLARED ........ Inalterado.
 9 PERSISTENCE_BEHAVIOR_DECLARED .. NENHUMA. MIGRATION_DELTA = 0.
10 MULTI_AI_RESULT_ATTRIBUTION .... NOT_APPLICABLE.
11 DIVERGENCE_PRESERVATION ........ REFORÇADO: ordem preservada após a
     validação canônica; sem set, sem normalização de identificador.
12 CONCURRENT_WORK_ISOLATION ...... Inalterado.
13 BACKGROUND_EXECUTION ........... NOT_APPLICABLE.
14 RESOURCE_LIMITS_QUEUE_AND_COST . NOT_APPLICABLE.
15 REMOTE_RESOURCE_SCOPE .......... NENHUM.
16 OBSERVATION_PREPARATION_EXEC ... Segue pura observação.
17 CREDENTIAL_AND_SECRET_BOUNDARY . Inalterado.
18 FAILURE_ROLLBACK_AND_CONCURRENCY Sem escrita.
19 CURRENT_CAPABILITY_NOT_OVERSTATED É a linha deste corretivo: verificação
     de tipo NÃO é validação de coleção, e fábrica correta NÃO é construtor
     seguro.
20 FROZEN_MODULES_UNCHANGED ....... E3, E4.3, Alembic e enums intocados.
```

### 4.2 `SOPHIA_UX_COMPATIBILITY` — 17 linhas

```text
 1 USER_AUTHORITY_PRESERVED ......... REFORÇADO.
 2 SCHEDULE_MODE_DECLARED ........... NOT_APPLICABLE.
 3 AUTOMATION_SCOPE_DECLARED ........ NENHUMA.
 4 PERSISTENCE_BEHAVIOR_DECLARED .... NENHUMA.
 5 PROVIDER_NEUTRALITY_PRESERVED .... SIM.
 6 PERSONALIZATION_REVERSIBLE ....... NOT_APPLICABLE.
 7 CONCURRENT_WORK_ISOLATION ........ Inalterado.
 8 BACKGROUND_EXECUTION ............. NOT_APPLICABLE.
 9 RESOURCE_LIMITS_AND_QUEUE ........ NOT_APPLICABLE.
10 AI_ROLE_CONTROL_DECLARED ......... NOT_APPLICABLE.
11 ROLE_AND_STEP_INSTRUCTION ........ NOT_APPLICABLE.
12 PIA_SEQUENCE_SUGGESTION .......... REFORÇADO: sugestão informada não pode
     depender da ordem de escrita da policy.
13 MULTI_AI_RESULT_ATTRIBUTION ...... NOT_APPLICABLE.
14 PIA_INTEGRATION_DIVERGENCE ....... NOT_APPLICABLE.
15 POST_RESULT_USER_COMMAND ......... Inalterado.
16 RESULT_APPROVAL_AND_PERSISTENCE .. Inalterado.
17 FROZEN_MODULES_UNCHANGED ......... SIM.
```

### 4.3 Multicanal v1.3 — 10 marcadores

```text
 1 INPUT_CHANNELS_DECLARED ........ Inalterado.
 2 COMMAND_ENVELOPE_DECLARED ...... Inalterado.
 3 CHANNEL_NORMALIZATION .......... NOT_APPLICABLE.
 4 IDENTITY_CONTEXT_AND_SCOPE ..... Inalterado.
 5 VOICE_CONFIDENCE_AND_CORRECTION  NOT_APPLICABLE.
 6 CONFIRMATION_POLICY_DECLARED ... Inalterado.
 7 DESTRUCTIVE_INTENT_BINDING ..... NOT_APPLICABLE.
 8 GOVERNANCE_PARITY_ACROSS_CHANNELS SIM, por construção — sem campo de canal.
 9 AUDIT_AND_RECEIPT_DECLARED ..... NOT_APPLICABLE.
10 CURRENT_CAPABILITY_NOT_OVERSTATED SIM.
```

### 4.4 Parte II §12

**Oito obrigações** cumpridas: diretriz citada; implementado nos §1–§2;
diferidos inalterados; estágios separados; autoridade é o usuário; sem
escrita não há rollback; compatibilidade por regressão delta zero; Stop
Condition assumida.

**Onze Stop Conditions:** nenhuma disparou — corretivo que apenas
**restringe**, sem entidade persistente, migration, enum novo, efeito,
consumidor, credencial ou acesso externo.

**Onze provas:** `PROVADAS` — nenhuma chamada externa, nenhuma escrita,
ordem preservada, isolamento. `NOT_APPLICABLE` — rollback, concorrência,
recibo, cancelamento, aprovação. `DEFERRED` — estado obsoleto do alvo.

### 4.5 Parte III §13

```text
1 cria distinção?         NÃO — RESTAURA uma que eu alegava existir
2 transforma distinção?   NÃO
3 compara distinções?     NÃO
4 muda acessibilidade?    NÃO
5 afeta persistência?     NÃO
6 altera proveniência?    NÃO
7 altera história causal? NÃO
```

### 4.6 Parte III §19 e E5/COUT-P

```text
MULTI_AI_HANDOFF_COMPATIBILITY = NOT_APPLICABLE
REASON = internal invariant corrective; no AI-to-AI runtime handoff
E4_INTEGRATION_OF_COUT_P = FORBIDDEN
```

---

## 5. Gates medidos

```text
COLLECTED        3773                                  (cadeia 92: 3730)
FULL_SUITE       3772 passed / 1 skipped / 0 failed    (cadeia 92: 3729/1/0)
RAW_SUITE        3270 passed / 503 skipped / 0 failed  (cadeia 92: 3227/503/0)
GLOBAL_COVERAGE  99,31%  — subiu (cadeia 92: 99,30%)
  retention_assessment_enums.py    12/12    100%
  retention_evaluator.py         131/131    100%
RUFF PASS   BLACK PASS (407)
MYPY app    7 históricos, NEW = 0
ALEMBIC heads = a1f7c2d40e93 — INALTERADO
backend/alembic 3b1cd66e… byte a byte
git diff --check CLEAN
```

**Seletores em delta zero:**

```text
E3 = 732 · E4.3 = 255 · E4.9.6 = 309 · E4.9.7 = 326 · E4.9.8 = 299
E4.9.9.a = 85 · E4.9.9.b = 90
```

**Fatia E4.9.9.c = 104** (era 61), três execuções idênticas.

**Onze caracterizações**, `EXIT=1`, `stderr=0`. A nova é bilateral:

```text
cadeia 92   8/8   EXIT=0   ORDER_CHANGES_DECISION = True
cadeia 93   0/8   EXIT=1   ORDER_CHANGES_DECISION = False
                           NOMINAL_PATH_PRESERVED = True
```

Mutante do gate de validade: fixture inválida produz
`INSTRUMENT_INVALID = FIXTURE_CONSTRUCTION_FAILED` com `EXIT=2`, nunca
`NOT_REPRODUCED`.

---

## 6. Riscos e limites

**(a) A matriz cobre as cinco decisões de hoje.** Um membro novo cairia no
ramo explícito de erro, e não em silêncio — mas alterar o enum é proibido
nesta fatia e exigiria EDR próprio.

**(b) A validação canônica é a da E4.9.6.2.** Se ela mudar, este avaliador
herda a mudança — que é o efeito pretendido de reutilizar em vez de
copiar, e também o risco de acoplamento. Registrado nos dois sentidos.

**(c) Nada mais foi corrigido.** O prompt proíbe corrigir problema não
demonstrado, e não procurei outros. A ausência de achado adicional aqui
**não** é prova de ausência de defeito.

---

## 7. Estado

```text
PATCH_CHAIN = 93
MIGRATION_HEAD = a1f7c2d40e93 (INALTERADO)
E4_9_9_C_1 = COMPLETE_CANDIDATE
E4_9_9_C   = AWAITING_INDEPENDENT_REAUDIT
RETENTION_EVALUATOR = IMPLEMENTED
SCHEDULER = NONE   DISPOSITION = NONE   PERSISTENCE = NONE
E4_9_9_D = NOT_STARTED   E4_10 = NOT_STARTED
E4_9_READY = FALSE
PASS_FINAL = NOT_DECLARED
```
