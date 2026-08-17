# E4_9_1_ERASURE_TARGET_CUSTODY_AUTHORIZATION

**Módulo:** E4.9.1 — autorização arquitetural de contrato de alvo e custódia
**Natureza:** **exclusivamente documental**
**Origem:** Tensão B do preflight da E4.9 — `ERASURE_TARGET_OWNERSHIP_GAP`

```text
ERASURE_TARGET_CUSTODY_CONTRACT = AUTHORIZED_NOT_IMPLEMENTED
```

**Baseline:** `PATCH_CHAIN = 69` · HEAD `7df0ff605fec…` ✓ ·
PARENT `18ee1c20ad22…` ✓ · TREE `466f5ace509e…` ✓ ·
PATCH_ID `08f06c00d845…` ✓ · bundle SHA-256 `e5916f64…9896a` ✓ ·
migration head `7b2e4c9a15df` ✓ · clone direto no HEAD ✓ · árvore limpa ✓

Baseline reproduzida com PostgreSQL 16 real, banco recriado:
**2446 passed / 1 skipped / 0 failed**, RAW **2073 / 374**.

Trees registrados na baseline:

```text
backend/app              b8e1eaa729134a1b151fe6045f4bd41cd090a95d
backend/tests            3a7bc98f6b0644c8287888738981128074113677
backend/alembic          65a066dea0925edc55ad88e0c774f56b1944254f
docs/entregas/entrega-4  11ac20964a82f93207e31dcc68c50f0e56720fb4
```

---

## 1. Status normativo

```text
ERASURE_TARGET_CUSTODY_CONTRACT = AUTHORIZED_NOT_IMPLEMENTED
ERASURE_TARGET_RESOLVER         = AUTHORIZED_NOT_IMPLEMENTED
ERASURE_EFFECT_PORT             = AUTHORIZED_NOT_IMPLEMENTED
ERASURE_TARGET_DESCRIPTOR       = AUTHORIZED_NOT_IMPLEMENTED

ARTIFACT_STORAGE                = DEFERRED
EXTERNAL_CONNECTOR_EXECUTION    = NOT_IMPLEMENTED
ERASURE_EXECUTOR                = NONE
AUTHORIZED_EXECUTOR             = NONE
```

```text
ARCHITECTURAL AUTHORIZATION != IMPLEMENTATION
NOTHING IN THIS DELIVERY ERASES ANYTHING
```

Decisão, alternativas rejeitadas, modelo de ameaças e riscos no
`EDR_E4_9_1_ERASURE_TARGET_CUSTODY_CONTRACT.md`.

---

## 2. Evidência da baseline

Colhida no schema e no código da cadeia 69, não presumida:

```text
cognitive_objects: ['clid','accessibility','revision_status',
                    'id','created_at','updated_at','deleted_at']

causal_history_events.payload_ref   VARCHAR(512)   FKs = 0
provenance_records.source_ref       VARCHAR(512)   FKs = 0
provenance_records.evidence_refs    JSON           FKs = 0
transformation_records.input_refs   JSON           FKs = 0
transformation_records.output_refs  JSON           FKs = 0

resolvedor/storage/conector/executor em backend/app: NENHUMA ocorrência
```

---

## 3. Matriz de classes

| Classe | É conteúdo? | Resolvível hoje? | Executável hoje? | Efeito possível hoje |
|---|---|---|---|---|
| `PIA_MANAGED_ARTIFACT` | **sim** | **não** — sem Artifact Storage | **não** | nenhum |
| `AUTHORIZED_CONNECTOR_REFERENT` | **sim** | **não** — sem conector, conta ou capacidade verificada | **não** | nenhum |
| `COGNITIVE_METADATA_RECORD` | **não** | sim (é linha local) | não sob este contrato | remoção de metadado **não é** erasure de conteúdo |
| `UNRESOLVED_OPAQUE_REFERENCE` | **não** | **não**, por definição | **não** | **recusa tipada obrigatória** |

```text
METADATA REMOVAL     != CONTENT ERASURE
UNRESOLVED REFERENCE  = TYPED REFUSAL, NEVER BEST EFFORT
```

Nenhuma das quatro classes tem efeito possível na cadeia 69. As duas
primeiras porque falta mecanismo; a terceira porque tem semântica
própria; a quarta porque a recusa **é** o comportamento correto.

---

## 4. Invariantes autorizados

### 4.1 Custódia

```text
TECHNICAL_CUSTODY != LEGAL_OWNERSHIP
USER_OR_ORGANIZATION_CONTROLS_DESTINATION
PIA_EXECUTES_ONLY_WITH_VERIFIED_CAPABILITY_AND_AUTHORITY
```

O contrato **não decide titularidade jurídica**. Jurisdição, contrato e
obrigação legal são entradas externas futuras.

### 4.2 Descritor transitório

Conteúdo mínimo: classe do alvo; identificador histórico do sujeito;
Workspace/tenant/principal de controle; provedor/namespace; localizador
opaco transitório; capacidade verificada e escopo; instante e
versão/etag quando houver; origem da referência.

Proibido:

```text
conteúdo, trecho, cópia ou derivado reconstruível
segredo, token, credencial ou material de autenticação
persistência automática do localizador
inclusão do localizador no futuro ErasureRecord
log em claro
reutilização entre Workspaces, tenants, contas ou provedores
execução com resolução obsoleta
```

```text
DESCRIPTOR != PATRIMONY  != POLICY  != APPROVAL
DESCRIPTOR != EFFECT     != RECEIPT
```

### 4.3 Duas fronteiras distintas

```text
ErasureTargetResolverPort
  referência + contexto autorizado → descritor verificado OU recusa tipada

ErasureEffectPort
  descritor + autorização destrutiva válida → tentativa material observável
```

```text
REFERENCE          != RESOLVED TARGET
TARGET RESOLUTION  != DELETION AUTHORITY
DELETION AUTHORITY != EFFECT
EFFECT             != ERASURE RECORD
```

**Resolver é observacional**: não apaga, não modifica, não marca nada.

### 4.4 Referências legadas

```text
payload_ref   != ErasureTargetDescriptor
source_ref    != ErasureTargetDescriptor
evidence_refs != ErasureTargetDescriptor
input_refs    != ErasureTargetDescriptor
output_refs   != ErasureTargetDescriptor
COID          != CONTENT LOCATOR
```

Proibido passar qualquer dessas strings a um executor. Elas apenas
**iniciam uma tentativa de resolução**, que pode terminar em recusa.

---

## 5. Critérios de admissão e recusa

Um alvo só chega ao executor se as dez provas da §8 do EDR forem
verdadeiras. Falha em qualquer uma produz **recusa tipada**.

Recusa obrigatória, nomeada:

| Situação | Desfecho |
|---|---|
| referência não resolvida | recusa — `UNRESOLVED_OPAQUE_REFERENCE` |
| alvo é metadado cognitivo | recusa como *erasure de conteúdo* |
| Workspace/tenant divergente da autorização | recusa — cross-tenant |
| capacidade de exclusão não verificada | recusa — sem capacidade |
| resolução obsoleta ou etag divergente | recusa — stale resolution |
| alvo expandido depois da confirmação | recusa — target expansion |
| provedor/namespace fora do escopo da credencial | recusa — credential confusion |

```text
NO BEST EFFORT
NO SILENT PARTIAL ERASURE
FAILURE = TYPED REFUSAL
```

---

## 6. Matriz requisito → documento → verificação

| # | Requisito do prompt | Onde | Verificação |
|---|---|---|---|
| §4.1 | custódia técnica, não jurídica | EDR §2, doc §4.1 | busca por "titularidade jurídica" no texto: só aparece para **negar** a competência |
| §4.2 | classificação fechada de 4 classes | EDR §3, doc §3 | as quatro nomeadas nos dois documentos; nenhuma fundida |
| §4.3 | descritor transitório e proibições | EDR §5, doc §4.2 | 8 elementos e 7 proibições, íntegros nos dois |
| §4.4 | resolução ≠ efeito | EDR §6, doc §4.3 | duas portas nomeadas; "resolver é observacional" explícito |
| §4.5 | 10 critérios de admissão | EDR §8, doc §5 | dez itens, numerados |
| §5 | referências legadas não são capacidades | EDR §9, doc §4.4 | seis linhas `!=` nos dois documentos |
| §6 | A+B preservada, C rejeitada, FK proibida | EDR §10 | vínculo por identificador histórico reafirmado |
| §7 | Master v1.3, texto e voz | EDR §11 | cinco marcadores; E4.9.4 nomeada como destino |
| §9 | modelo de ameaças | EDR §7 | seis ameaças, com o que cada uma exige |
| §9 | fronteiras implementadas × autorizadas | EDR §12 | tabela com 11 linhas |
| §9 | riscos e decisões abertas | EDR §13 | dois riscos declarados + placar |

---

## 7. Arquivos alterados

Exatamente os quatro autorizados, todos `.md`:

```text
docs/entregas/entrega-4/EDR_E4_9_1_ERASURE_TARGET_CUSTODY_CONTRACT.md   (novo)
docs/entregas/entrega-4/E4_9_1_ERASURE_TARGET_CUSTODY_AUTHORIZATION.md  (novo)
docs/entregas/entrega-4/E4_PRIMITIVE_OWNERSHIP.md                        (aditivo)
docs/entregas/entrega-4/E4_DEFERRED_INVENTORY.md                         (aditivo)
```

As duas atualizações são **aditivas e preservam a história**. A cadeia 63
não é reescrita como se já tivesse esta autorização.

```text
PRODUCTION_TREE = IDENTICAL   backend/app     b8e1eaa7…
TEST_TREE       = IDENTICAL   backend/tests   3a7bc98f…
ALEMBIC_TREE    = IDENTICAL   backend/alembic 65a066de…
MIGRATION_DELTA = 0   SCHEMA_DELTA = 0   ENUM_DELTA = 0
NEW_ERROR_CODE  = NONE   (NEXT_FREE_ERROR_CODE = PIA-8041)
```

---

## 8. Gates medidos

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

Idênticos à baseline, como se espera de um patch que não toca código.

---

## 9. Compatibilidade SOPHIA / PIA-OS (Master v1.3)

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
NATURAL_LANGUAGE_REFERENCE != RESOLVED ERASURE TARGET
```

Ao contrário da E4.6.3.1, onde o adendo multicanal era `NOT_APPLICABLE`,
aqui ele **se aplica**: o contrato de alvo é materialmente relacionado a
comandos destrutivos futuros. Nenhum código de voz foi criado; a
implementação material fica com a **E4.9.4**.

---

## 10. Placar das Stop Conditions

```text
RETENTION_OPERATION_AUTHORITY_GAP   = CLOSED_FINAL
RETENTION_RETRIEVAL_COMPOSITION_GAP = CLOSED_FINAL
ERASURE_AUDIT_PRIMITIVE_GAP         = CLOSED_CANDIDATE_BY_AUTHORIZATION
ERASURE_TARGET_OWNERSHIP_GAP        = CLOSED_CANDIDATE_BY_AUTHORIZATION  ← esta

LEGAL_ERASURE_CAUSAL_HISTORY_GAP    = OPEN_CONDITIONAL
ON_EXPIRY_ACTION_UNRESOLVED         = OPEN
DESTRUCTIVE_EXECUTION_AUTHORITY_GAP = OPEN
```

Quatro de sete encaminhadas; três abertas.

---

## 11. Gate

```text
E4_9_1_STATUS                       = COMPLETE_CANDIDATE
E4_9_1_AUDIT                        = AWAITING_INDEPENDENT_AUDIT
PATCH_CHAIN                         = 70
ERASURE_TARGET_CUSTODY_CONTRACT     = AUTHORIZED_NOT_IMPLEMENTED
E4_9_IMPLEMENTATION                 = NOT_STARTED
E4_9_READY                          = FALSE
READY_FOR_E4_10                     = FALSE
```

`CLOSED_FINAL` não é declarado aqui — cabe à auditoria independente.
