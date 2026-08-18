# EDR E4.9.8.3.1 — Guard Mutation & Audit Evidence Completion

**Natureza:** corretivo **aditivo** de testes e evidência. Não reescreve o EDR
histórico da cadeia 88.
**Baseline:** cadeia 88 (`98156ff8`).

```text
GUARD_PRESENT != GUARD_CAN_FAIL != DEMONSTRATED_BY_MUTANT
MUTANT_REJECTED_BY_PARALLEL_LOGIC != GUARD_CAN_FAIL
COUNTING_ENUM_MEMBERS != DETECTING_AUTOMATIC_BLOCKING
```

```text
PRODUCTION_DELTA = 0
ALEMBIC_DELTA = 0
MIGRATION_DELTA = 0
MISSING_GUARD_MUTANT_DEMONSTRATIONS = 0
PACKAGE_EVIDENCE_OMISSIONS = 0
E4_9_9_A = STILL_BLOCKED
```

---

## 1. O achado, sem atenuação

A auditoria da cadeia 88 não encontrou defeito material no runtime. Bloqueou o
`PASS_FINAL` por lacuna de **evidência**: nove guardas substantivas foram
introduzidas e apenas três vieram com demonstração por mutante.

```text
COVERED     s31 <- s99_11 · s33/default <- s99_9 · s33/anotação <- s99_10
MISSING     s17_1 · s32 · s34 · s35 · s36 · s37 · s38
```

O §7.2 do prompt da E4.9.8.3 exigia demonstração para **cada** guarda nova, e a
Stop Condition 14 impedia concluir sem ela. Escrevi as guardas, escrevi o
requisito, publiquei três demonstrações e declarei a fatia completa.

Isto é exatamente a forma que venho corrigindo desde a E4.9.7 — alegação à
frente da prova —, desta vez sobre a própria disciplina de guardas. E o
agravante é específico: eu havia escrito no EDR da cadeia 88 que "cada guarda
nova vem com demonstração de falha". Não vinha.

---

## 2. Helpers compartilhados, e por quê

Cada demonstração exercita o **mesmo helper de análise** que a guarda usa. A
alternativa — reimplementar a análise no teste — provaria apenas que um mutante
cai numa lógica escrita para o teste, e deixaria a guarda real sem prova.

```text
MUTANT_REJECTED_BY_PARALLEL_LOGIC != GUARD_CAN_FAIL
```

Helpers extraídos (arquivos de teste apenas, nenhuma linha de produção):

```text
_copia_do_materializador      s17_1  <- s99_18
_membros_do_vocabulario       s32    <- s99_12
_valida_protecao_em_runtime   s34    <- s99_13
_inferencias_de_protecao      s35    <- s99_14
_membros_de_enum              s36    <- s99_15
_protecao_usada_como_bloqueio s36    <- s99_15
_persistencia_presente        s37    <- s99_16
_revisoes_de_migration        s37    <- s99_16
_simbolo_definido             s38    <- s99_17
```

---

## 3. Três guardas mediam menos do que o nome prometia

Escrever o mutante revelou fraqueza real. **Corrigi as guardas, não os
mutantes** — enfraquecer a guarda para o mutante passar seria Stop Condition 5.

| Guarda | Fraqueza | Correção |
|---|---|---|
| `s34` | `"raise TypeError" in corpo` aceitaria o `raise` de **qualquer outro campo** | exige o `raise TypeError` no **ramo negativo** do `isinstance` do campo |
| `s37` | comparava só `down_revision == head`; **branch** de revisão anterior escaparia | constrói o grafo `revision -> down_revision` completo |
| `s38` | procurava só `class X`; símbolo como função ou atribuição escaparia | aceita `ClassDef`, `FunctionDef` e atribuição; inclui `consume_once` |

E `s36` ganhou a **terceira prova** exigida pelo §3.5: contar membros de enum
não detecta o uso automático de `PROTECTED` como bloqueio. Um mutante que
escreva `if alvo.legacy_protection_state is LegacyProtectionState.PROTECTED:
raise` não toca enum algum e passaria pela contagem.

---

## 4. Matriz de mutantes

Publicada integralmente em `MATRIZ_MUTANTES_GUARDAS_E4_9_8_3.md`: 21 linhas
relacionando guarda, propriedade, helper, mutante, resultado esperado e
resultado medido. Resumo:

```text
GUARDAS_COBERTAS = 7
DEMONSTRACOES_NOVAS = 7   (s99_12 .. s99_18)
MUTANTES = 21
```

Nenhum mutante é aceito por substring, docstring ou falha de construção — a
Stop Condition 4 do corretivo, e a mesma lição do `INSTRUMENT_VALIDITY_GATE` da
cadeia 88.

---

## 5. Evidências que faltavam no pacote

```text
DIFF_COMPAT_4981_V2_TO_V3.patch        gerado por `diff -u`, completo
DIFF_COMPAT_4982_TO_V2.patch           idem
EXECUCOES_LITERAIS_CHAINS_87_88.txt    stdout literal + EXIT + STDERR_BYTES
RETRATO_ASSINATURAS_CHAINS_87_88.md    recomputado por reflexão em cada cadeia
MATRIZ_MUTANTES_GUARDAS_E4_9_8_3.md    guarda × mutante × medido
```

O retrato lista assinatura, tipo, default, factory, `repr`, `compare`,
classmethods, membros de enum e exports — **28 dataclasses** ao todo nas duas
cadeias, não um resumo do delta permitido. Todo número foi recomputado por
ferramenta.

---

## 6. Escopo negativo — verificado

```text
backend/app/**       BYTE_A_BYTE_IDENTICAL_TO_CHAIN88
backend/alembic/**   BYTE_A_BYTE_IDENTICAL_TO_CHAIN88
```

Arquivos alterados: **dois**, ambos de teste.

Nenhuma guarda existente foi enfraquecida, renomeada ou removida. Nenhum `Any`,
`cast`, `type: ignore`, monkeypatch de autoridade ou `try/except Exception`.

---

## 7. Master Integrado v2.4

A E4.9.8.3 foi implementada sob o prompt **v2.3**; o **v2.4** não altera seu
escopo material. Este corretivo é de teste e evidência apenas.

```text
MULTI_AI_HANDOFF_COMPATIBILITY = NOT_APPLICABLE — test/evidence-only corrective
MULTI_AI_RUNTIME_IMPLEMENTATION = NONE
HANDOFF_ENVELOPE = NOT_IMPLEMENTED
```

### 7.1 `PIA_OS_SOPHIA_MASTER_COMPATIBILITY` — 20 linhas

```text
 1 USER_AUTHORITY_PRESERVED ............... Inalterado; nenhuma linha de
     produção tocada. A proteção continua sendo do usuário.
 2 SOPHIA_BRAND_PIA_OS_CODEBASE_PRESERVED . SIM.
 3 MODULE_SCOPE_AND_DEFERRED_CAPABILITIES . Implementado: 7 demonstrações e 5
     evidências. Diferidos: todos os da cadeia 88, sem alteração.
 4 SCHEDULE_MODE_DECLARED ................. NOT_APPLICABLE.
 5 AI_ROLE_AND_STEP_INSTRUCTION ........... NOT_APPLICABLE.
 6 PROVIDER_CONNECTION_METHOD ............. NOT_APPLICABLE.
 7 AUTOMATION_SCOPE_DECLARED .............. NENHUMA.
 8 APPROVAL_GATES_DECLARED ................ Inalterado. As guardas passam a
     ter prova de que conseguem falhar; o portão em si não mudou.
 9 PERSISTENCE_BEHAVIOR_DECLARED .......... NENHUMA. PRODUCTION_DELTA = 0.
10 MULTI_AI_RESULT_ATTRIBUTION ............ NOT_APPLICABLE.
11 DIVERGENCE_PRESERVATION_DECLARED ....... SIM — s32 passou a medir nomes E
     valores, o que preserva a divergência de token.
12 CONCURRENT_WORK_ISOLATION_DECLARED ..... Inalterado.
13 BACKGROUND_EXECUTION_AUTHORIZATION ..... NOT_APPLICABLE.
14 RESOURCE_LIMITS_QUEUE_AND_COST ......... NOT_APPLICABLE.
15 REMOTE_RESOURCE_SCOPE_DECLARED ......... NENHUM.
16 OBSERVATION_PREPARATION_EXECUTION ...... Inalterado.
17 CREDENTIAL_AND_SECRET_BOUNDARY ......... Inalterado.
18 FAILURE_ROLLBACK_AND_CONCURRENCY ....... Sem escrita.
19 CURRENT_CAPABILITY_NOT_OVERSTATED ...... É a razão do corretivo: "cada
     guarda vem com demonstração" era alegação sem prova em sete casos.
20 FROZEN_MODULES_UNCHANGED ............... app, alembic e cognitive byte a byte.
```

### 7.2 `SOPHIA_UX_COMPATIBILITY` — 17 linhas

```text
 1 USER_AUTHORITY_PRESERVED ......... Inalterado.
 2 SCHEDULE_MODE_DECLARED ........... NOT_APPLICABLE.
 3 AUTOMATION_SCOPE_DECLARED ........ NENHUMA.
 4 PERSISTENCE_BEHAVIOR_DECLARED .... NENHUMA.
 5 PROVIDER_NEUTRALITY_PRESERVED .... SIM.
 6 PERSONALIZATION_REVERSIBLE ....... NOT_APPLICABLE.
 7 CONCURRENT_WORK_ISOLATION ........ Inalterado.
 8 BACKGROUND_EXECUTION_AUTHORIZATION NOT_APPLICABLE.
 9 RESOURCE_LIMITS_AND_QUEUE ........ NOT_APPLICABLE.
10 AI_ROLE_CONTROL_DECLARED ......... NOT_APPLICABLE.
11 ROLE_AND_STEP_INSTRUCTION ........ NOT_APPLICABLE.
12 PIA_SEQUENCE_SUGGESTION_BEHAVIOR . NOT_APPLICABLE.
13 MULTI_AI_RESULT_ATTRIBUTION ...... NOT_APPLICABLE.
14 PIA_INTEGRATION_DIVERGENCE ....... NOT_APPLICABLE.
15 POST_RESULT_USER_COMMAND ......... Inalterado.
16 RESULT_APPROVAL_AND_PERSISTENCE .. Inalterado; nada persiste.
17 FROZEN_MODULES_UNCHANGED ......... SIM.
```

### 7.3 Multicanal v1.3 — 10 marcadores

```text
 1 INPUT_CHANNELS_DECLARED ............ Inalterado.
 2 COMMAND_ENVELOPE_DECLARED .......... Inalterado.
 3 CHANNEL_NORMALIZATION_DECLARED ..... NOT_APPLICABLE.
 4 IDENTITY_CONTEXT_AND_SCOPE ......... Inalterado.
 5 VOICE_CONFIDENCE_AND_CORRECTION .... Inalterado.
 6 CONFIRMATION_POLICY_DECLARED ....... Inalterado.
 7 DESTRUCTIVE_INTENT_BINDING ......... Inalterado; s36 passou a provar que
     PROTECTED não vira bloqueio automático, que é o binding descrito.
 8 GOVERNANCE_PARITY_ACROSS_CHANNELS .. Inalterada; u138 preservado.
 9 AUDIT_AND_RECEIPT_DECLARED ......... NOT_APPLICABLE.
10 CURRENT_CAPABILITY_NOT_OVERSTATED .. SIM.
```

### 7.4 Parte II §12

**Oito obrigações:** diretriz citada; implementado no §2–§4; diferidos os da
cadeia 88; estágios inalterados; autoridade competente é o usuário; sem escrita
não há rollback; compatibilidade por regressão delta zero exceto os dois
seletores autorizados; Stop Condition assumida.

**Onze Stop Conditions:** nenhuma disparou — sem entidade persistente, sem
ownership, sem credencial, sem execução externa, **sem ampliação de
autoridade**, sem provedor, sem sincronização, proveniência preservada, sem
Schedule, sem rollback, congelados byte a byte.

**Onze provas:** `PROVADAS` — nenhuma chamada externa, nenhum acesso fora do
escopo, nenhuma escrita, preservação de origem e ordem, isolamento.
`NOT_APPLICABLE` — rollback, concorrência, recibo, cancelamento, aprovação
prévia. `DEFERRED` — estado obsoleto.

### 7.5 Parte III §13

```text
1 cria distinção?         SIM, mas no plano da PROVA: "guarda existe" e
                          "guarda consegue falhar" passam a ser distinguíveis
2 transforma distinção?   NÃO
3 compara distinções?     NÃO
4 muda acessibilidade?    NÃO
5 afeta persistência?     NÃO
6 altera proveniência?    NÃO
7 altera história causal? NÃO
```

### 7.6 E5 / COUT-P

`E4_INTEGRATION_OF_COUT_P = FORBIDDEN` respeitado.

---

## 8. Gates medidos

```text
COLLECTED        3494                                  (cadeia 88: 3487)
FULL_SUITE       3493 passed / 1 skipped / 0 failed    (cadeia 88: 3486/1/0)
RAW_SUITE        3026 passed / 468 skipped / 0 failed  (cadeia 88: 3019/468/0)
GLOBAL_COVERAGE  99,30%   — não caiu
RUFF PASS   BLACK PASS (391)
MYPY app    7 históricos, NEW = 0
supressões / cast / Any novos: 0
ALEMBIC heads = c8a3f5017e94   ·   backend/alembic sem alteração
git diff --check CLEAN
```

**Onze seletores em delta zero:**

```text
E3 = 732 · E4.1 = 40 · E4.2 = 42 · E4.3 = 255 · E4.4 = 74 · E4.5 = 187
E4.6 = 275 · E4.7 = 240 · E4.8 = 146 · E4.9.5 = 113 · E4.9.6 = 309
```

**Dois seletores, apenas pelos testes autorizados:**

```text
E4.9.7   320 -> 326   (+6: s99_12 a s99_17)
E4.9.8   298 -> 299   (+1: s99_18)
```

Suítes da fatia três vezes, resultado idêntico: **625** testes (eram 618).

**Sete instrumentos canônicos, mesmas contagens da cadeia 88:**

```text
4971 = 0/8 · 4972 = 0/5 · 4973 = 0/9 · 4974 = 0/3
4981_v3 = 0/11 · 4982_v2 = 0/3 · 4983 = 0/8
EXIT=1 · STDERR=0
FIXTURE_CONSTRUCTION_OK = TRUE e PROBES_REACHED = TRUE nos três com gate
```

---

## 9. Riscos e limites

**(a) Demonstração por mutante prova que a guarda distingue dois textos, não
que ela cobre todo defeito possível.** Um mutante que eu não imaginei continua
fora. É o limite intrínseco da técnica, e prefiro escrevê-lo a deixá-lo
implícito.

**(b) Três guardas eram mais fracas do que o EDR da cadeia 88 dizia.** Corrigidas
aqui; o EDR histórico permanece como escrito, e este documento o qualifica.

**(c) Nada disto altera o runtime.** `PRODUCTION_DELTA = 0`. A E4.9.8.3
continua a ser exatamente o que era, agora com a prova que faltava.

---

## 10. Estado

```text
PATCH_CHAIN = 89
MIGRATION_HEAD = c8a3f5017e94 (INALTERADO)
E4_9_8_3_1 = COMPLETE_CANDIDATE
E4_9_8_3 = AWAITING_INDEPENDENT_REAUDIT
MISSING_GUARD_MUTANT_DEMONSTRATIONS = 0
PACKAGE_EVIDENCE_OMISSIONS = 0
E4_9_9_A = STILL_BLOCKED
E4_9_9_B = NOT_STARTED  E4_9_9_C = NOT_STARTED  E4_9_9_D = NOT_STARTED
E4_10 = NOT_STARTED
```

`PASS_FINAL` não é declarado pelo implementador.
