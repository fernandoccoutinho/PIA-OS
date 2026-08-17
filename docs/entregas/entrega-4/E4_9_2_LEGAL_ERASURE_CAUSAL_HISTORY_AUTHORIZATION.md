# E4_9_2_LEGAL_ERASURE_CAUSAL_HISTORY_AUTHORIZATION

**Módulo:** E4.9.2 — autorização do caminho normal de legal erasure
**Natureza:** **exclusivamente documental**
**Origem:** Tensão C do preflight da E4.9 —
`LEGAL_ERASURE_CAUSAL_HISTORY_GAP`, deferida desde a E4.0 como a questão
arquitetural mais difícil da entrega

```text
NORMAL_REFERENT_ERASURE_PRESERVES_CAUSAL_HISTORY = AUTHORIZED_NOT_IMPLEMENTED
```

**Baseline:** `PATCH_CHAIN = 70` · HEAD `c4050501c6fe…` ✓ ·
PARENT `7df0ff605fec…` ✓ · TREE `a9203ac51bb9…` ✓ ·
PATCH_ID `eab225441d74…` ✓ · bundle SHA-256 `40b188f4…074ba` ✓ ·
migration head `7b2e4c9a15df` ✓ · clone direto no HEAD ✓ · árvore limpa ✓

Baseline reproduzida com PostgreSQL 16 real, banco recriado:
**2446 passed / 1 skipped / 0 failed**, RAW **2073 / 374**.

Trees registrados na baseline:

```text
backend/app              b8e1eaa729134a1b151fe6045f4bd41cd090a95d
backend/tests            3a7bc98f6b0644c8287888738981128074113677
backend/alembic          65a066dea0925edc55ad88e0c774f56b1944254f
docs/entregas/entrega-4  247d5dc1f2113b101127cbbf0707aef60ac9de34
```

---

## 1. Status normativo

```text
NORMAL_REFERENT_ERASURE_PRESERVES_CAUSAL_HISTORY = AUTHORIZED_NOT_IMPLEMENTED
EXCEPTIONAL_CAUSAL_RECORD_ERASURE                = DEFERRED_STOP_CONDITION

ERASURE_RECORD           = AUTHORIZED_NOT_IMPLEMENTED  (E4.9.0)
ERASURE_TARGET_CONTRACT  = AUTHORIZED_NOT_IMPLEMENTED  (E4.9.1)
ARTIFACT_STORAGE         = DEFERRED
ERASURE_EXECUTOR         = NONE
AI_MODEL_NEVER_EXECUTES_ERASURE
```

```text
ARCHITECTURAL AUTHORIZATION != IMPLEMENTATION
NOTHING IN THIS DELIVERY ERASES ANYTHING
```

Decisão, alternativas, modelo de riscos e a exceção delimitada estão no
`EDR_E4_9_2_LEGAL_ERASURE_CAUSAL_HISTORY.md`.

---

## 2. Evidência verificada na baseline

```text
causal_histories.subject_coid              -> cognitive_objects     ON DELETE NO ACTION
causal_history_events.history_id           -> causal_histories      ON DELETE NO ACTION
causal_history_events.predecessor_event_id -> causal_history_events ON DELETE NO ACTION
causal_history_events.actor_ref            -> provenance_records    ON DELETE NO ACTION

CausalHistoryRepository.update / delete / update_event / delete_event  → RECUSAM
CausalEventType = ['created', 'transformed', 'compared', 'accessed']
to_regclass('public.retention_policies') = NULL
to_regclass('public.erasure_records')    = NULL
```

Nenhum `CASCADE`; nenhuma primitiva de retenção ou erasure existe em
runtime.

---

## 3. Matriz alvo → efeito → história → registro → estado

| Alvo | Efeito autorizado | História causal | `ErasureRecord` | Estado resultante |
|---|---|---|---|---|
| `PIA_MANAGED_ARTIFACT` | apagar bytes sob custódia + cópias/caches/réplicas/derivados controlados | **preservada** | append após tentativa observada | `SUCCEEDED` se todo o escopo controlado confirmado |
| `AUTHORIZED_CONNECTOR_REFERENT` | **solicitar** exclusão ao provedor e observar a confirmação | **preservada** | append após tentativa observada | tipicamente `PARTIAL` — confirmação de terceiro não prova desaparecimento universal |
| `COGNITIVE_METADATA_RECORD` | **nenhum** neste caminho | **preservada** | não se aplica | recusa: metadado não é conteúdo |
| `UNRESOLVED_OPAQUE_REFERENCE` | **nenhum** | **preservada** | não se aplica | **recusa tipada** |
| registro causal / identificador histórico | **nenhum** | intocada | não se aplica | **exceção da §5 — Stop Condition** |

```text
HISTORY SURVIVES != CONTENT SURVIVES
KNOWN ERASED     != NEVER EXISTED
```

---

## 4. Critérios do caminho normal

Aplicável quando a obrigação alcança **conteúdo/referente verificável**,
e não o registro causal.

```text
ERASE REFERENT
PRESERVE CognitiveObject identity/metadata required by causal structure
PRESERVE CausalHistory
PRESERVE CausalHistoryEvent
PRESERVE lineage/provenance/transformation/relationship structure
APPEND ErasureRecord only after a real observed attempt
```

Proibido: cascade, hard delete, mutação retroativa, fabricação de evento
causal, mutação de `payload_ref` ou de qualquer ref da E3.

**O rastro só é admissível se for irreversível.** Entram no escopo do
efeito, quando sob controle verificável: cópia integral, trecho
suficiente, thumbnail reversível, cache, réplica, embedding reversível,
hash usável como chave de relocalização e qualquer derivado suficiente
para recompor o original.

```text
STRUCTURAL CONSEQUENCE MAY SURVIVE
RECONSTRUCTIBLE DERIVATIVE = ERASURE TARGET
```

**Referências históricas** permanecem imutáveis e opacas: nunca vão a um
executor, não recriam descritor sem nova resolução, uma resolução
posterior observa a ausência e **jamais** restaura por fallback/cache, e
a interface não as oferece como link funcional.

```text
DANGLING REFERENCE != BROKEN SYSTEM
DANGLING REFERENCE  = HONEST RECORD THAT SOMETHING WAS ERASED
```

---

## 5. Critérios da exceção

```text
NORMAL_REFERENT_ERASURE           = AUTHORIZED_PATH
EXCEPTIONAL_CAUSAL_RECORD_ERASURE = STOP_CONDITION
```

Dispara se a obrigação exigir remover ou alterar: `CognitiveObject`
necessário como sujeito; `CausalHistory` ou `CausalHistoryEvent`;
COID/CLID ou outro identificador histórico; `payload_ref`/referência
histórica **porque a própria string é dado protegido**; ou lineage,
provenance, transformation e relationship necessários ao rastro.

Comportamento obrigatório: não usar o fluxo normal, não fazer cascade,
não falsificar evento, não sobrescrever referência, não alegar
cumprimento parcial como completo — **interromper com exceção tipada** e
exigir EDR jurídico-arquitetural próprio.

`CLOSED_CANDIDATE_CONDITIONAL` significa que o **caminho normal** está
decidido, não que toda obrigação possível foi resolvida.

---

## 6. Ordem, atomicidade e fidelidade do resultado

```text
validated destructive authority
→ fresh target resolution
→ material effect attempt
→ observe provider/local outcome
→ append ErasureRecord
→ expose truthful receipt
```

Storage externo e banco local **não** formam transação atômica. Não se
alega rollback de apagamento irreversível; efeito ocorrido com registro
falho **não** vira sucesso limpo nem repetição cega — o estado
recuperável/auditável é contrato da **E4.9.4**.

```text
SUCCEEDED = all in-scope controlled reconstructible instances were confirmed erased
PARTIAL   = at least one effect occurred and at least one in-scope instance remains,
            is unverified, or is controlled only by a third party confirmation
FAILED    = no intended erasure effect was confirmed
```

```text
USER_OR_AUTHORIZED_ORGANIZATION_DECIDES
AI_MODEL_NEVER_EXECUTES_ERASURE
EXPIRY_TRIGGERS_ASSESSMENT_NOT_DELETION
ERASURE_EFFECT_REQUIRES_CONFIRMED_AUTHORITY
```

---

## 7. Matriz requisito → documento → verificação

| # | Requisito do prompt | Onde | Verificação |
|---|---|---|---|
| §2.3 | FKs, `ON DELETE`, imutabilidade e enum verificados no schema real | EDR §1 | quatro FKs `NO ACTION`, quatro métodos que recusam, enum de 4 valores — todos consultados no banco |
| §4.1 | caminho normal: referente apagado, história preservada | EDR §3, doc §4 | seis linhas do bloco `ERASE/PRESERVE/APPEND`, íntegras nos dois |
| §4.1 | rastro irreversível; derivados no escopo | EDR §3.2, doc §4 | sete formas de derivado enumeradas |
| §4.2 | referências históricas após o efeito | EDR §4, doc §4 | cinco restrições; proibição de mutar refs da E3 |
| §4.3 | `CausalHistoryEvent` × `ErasureRecord` | EDR §5 | oito propriedades do registro; três linhas `!=` |
| §4.4 | atomicidade impossível e fidelidade | EDR §6, doc §6 | ordem de seis passos; três definições de outcome; quatro marcadores de autoridade |
| §4.5 | exceção delimitada | EDR §7, doc §5 | cinco gatilhos; seis proibições; `DEFERRED_STOP_CONDITION` |
| §5 | impacto no Retrieval | EDR §8 | três linhas `!=`; gate segue por chamada |
| §6 | texto e voz | EDR §9 | cinco marcadores; cinco itens que a interface deve separar; E4.9.4 nomeada |
| §8 | riscos e decisões abertas | EDR §10 | três riscos nomeados + placar |

---

## 8. Arquivos alterados

Exatamente os quatro autorizados, todos `.md`:

```text
docs/entregas/entrega-4/EDR_E4_9_2_LEGAL_ERASURE_CAUSAL_HISTORY.md              (novo)
docs/entregas/entrega-4/E4_9_2_LEGAL_ERASURE_CAUSAL_HISTORY_AUTHORIZATION.md    (novo)
docs/entregas/entrega-4/E4_GOVERNANCE_BOUNDARIES.md                              (aditivo)
docs/entregas/entrega-4/E4_DEFERRED_INVENTORY.md                                 (aditivo)
```

As duas atualizações são **aditivas**: o §6.2 do
`E4_GOVERNANCE_BOUNDARIES.md`, que registrou a tensão em 2026 e listou
as três direções candidatas, permanece **íntegro**. A nota nova diz o
que foi decidido e o que continua aberto, sem reescrever o relato.

```text
PRODUCTION_TREE = IDENTICAL   backend/app     b8e1eaa7…
TEST_TREE       = IDENTICAL   backend/tests   3a7bc98f…
ALEMBIC_TREE    = IDENTICAL   backend/alembic 65a066de…
MIGRATION_DELTA = 0   SCHEMA_DELTA = 0   ENUM_DELTA = 0
NEW_ERROR_CODE  = NONE   (NEXT_FREE_ERROR_CODE = PIA-8041)
```

---

## 9. Gates medidos

```text
FULL_SUITE       2446 passed / 1 skipped / 0 failed
RAW_SUITE        2073 passed / 374 skipped / 0 failed
GLOBAL_COVERAGE  99,14%   APP_MEMORY 100%   APP_COGNITIVE 100%
RUFF PASS   BLACK PASS (`black --check .`)
MYPY 7 históricos, NEW = 0   DRIFT 5 passed
ALEMBIC single head 7b2e4c9a15df   git diff --check CLEAN
```

**Regressões, delta 0:**

```text
E3 = 732   E4.1 = 40   E4.2 = 42   E4.3 = 255   E4.4 = 74
E4.5 = 187   E4.6 = 275   E4.7 = 240   E4.8 = 146
```

---

## 10. Compatibilidade SOPHIA / PIA-OS (Master v1.3)

```text
USER_AUTHORITY_PRESERVED = TRUE
SOPHIA_BRAND_PIA_OS_CODEBASE_PRESERVED = TRUE
AUTOMATION_SCOPE = NONE
PERSISTENCE_BEHAVIOR = NONE
APPROVAL_GATE_IMPLEMENTATION = NONE
OBSERVATION_PREPARATION_EXECUTION_DISTINGUISHED = TRUE
CURRENT_CAPABILITY_NOT_OVERSTATED = TRUE
FROZEN_MODULES_UNCHANGED = TRUE

PIA_OS_INPUT_CHANNELS = TEXT | VOICE
SAME_COMMAND_ENVELOPE_FOR_ALL_CHANNELS = TRUE
VOICE_IS_AUTHORITY = FALSE
TRANSCRIPTION_IS_COMMAND_CANDIDATE
AMBIGUOUS_ERASURE_SCOPE = NO_EXECUTION
```

Nenhum código de voz ou interface foi criado; a materialização fica com
a **E4.9.4**.

---

## 11. Placar das Stop Conditions

```text
RETENTION_OPERATION_AUTHORITY_GAP   = CLOSED_FINAL
RETENTION_RETRIEVAL_COMPOSITION_GAP = CLOSED_FINAL
ERASURE_AUDIT_PRIMITIVE_GAP         = CLOSED_CANDIDATE_BY_AUTHORIZATION
ERASURE_TARGET_OWNERSHIP_GAP        = CLOSED_CANDIDATE_BY_AUTHORIZATION
LEGAL_ERASURE_CAUSAL_HISTORY_GAP    = CLOSED_CANDIDATE_CONDITIONAL   ← esta

ON_EXPIRY_ACTION_UNRESOLVED         = OPEN
DESTRUCTIVE_EXECUTION_AUTHORITY_GAP = OPEN

EXCEPTIONAL_CAUSAL_RECORD_ERASURE   = DEFERRED_STOP_CONDITION (por desenho)
```

Cinco de sete encaminhadas; duas abertas, mais a exceção deferida.

---

## 12. Gate

```text
E4_9_2_STATUS       = COMPLETE_CANDIDATE
E4_9_2_AUDIT        = AWAITING_INDEPENDENT_AUDIT
PATCH_CHAIN         = 71
E4_9_IMPLEMENTATION = NOT_STARTED
E4_9_READY          = FALSE
READY_FOR_E4_10     = FALSE
```

`CLOSED_FINAL` não é declarado aqui — cabe à auditoria independente.
