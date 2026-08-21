# E3_FINAL_MANIFEST — Entrega 3 (Biblioteca Cognitiva PIA-OS)

Manifest consolidado, gerado por inspeção do repositório real em
`E3.12`. Entrada para auditoria independente.

`FINAL_HEAD` e `FINAL_TREE` são registrados no relatório da E3.12.1,
porque só existem depois do commit do patch 35.

```
BASELINE_HEAD = 7de327a80ae3f72a3683141a8e88eeca49f9f80c
PATCH_CHAIN   = 33 patches
              + 34: e3-12-e3-final-integration-gate.patch
              + 35: e3-12-1-final-reproducibility-corrective.patch
BRANCH        = audit/e3-final-validation
```

> **E3.12.1** — os 6 scripts de `backend/deploy/scripts/` passaram de
> `100644` para `100755` no estado final. Conteúdo byte-identical
> (6/6 sha256 preservados, blobs git inalterados); a baseline **não**
> foi reescrita e continua registrando `100644`. Nenhum `chmod` manual
> é necessário após o clone. A evidência de testes normativa é
> `E3_12_1_CANONICAL_TEST_RESULT` (ver
> `E3_12_E3_FINAL_INTEGRATION_GATE.md` §11); contagens anteriores são
> HISTORICAL / SUPERSEDED.

---

## 1. Migration manifest (§42)

Cadeia linear, single-head, 13 revisões. Nenhuma migração publicada foi
editada nesta entrega.

| # | Revision | Down revision | Módulo | Propósito | Reversibilidade | Guard |
|---|---|---|---|---|---|---|
| 1 | `257dc8c23ab1` | *(base)* | E3.1 / LIB-01 | cria `cognitive_objects` | REVERSIBLE | — |
| 2 | `4f56e1a4936c` | `257dc8c23ab1` | E3.3 / LIB-03 | cria `lineage_edges` | REVERSIBLE | — |
| 3 | `f3e7e2b98ce3` | `4f56e1a4936c` | E3.4.0 | `revision_status` em `cognitive_objects` | REVERSIBLE | — |
| 4 | `2832894b5cb2` | `f3e7e2b98ce3` | E3.4 / LIB-04 | cria `transformation_records` | REVERSIBLE | — |
| 5 | `4f8fa05e036c` | `2832894b5cb2` | E3.4.1 | índice único parcial `one current per clid` | REVERSIBLE | — |
| 6 | `2826ce7fa4dc` | `4f8fa05e036c` | E3.5 / LIB-05 | cria `relationships` | REVERSIBLE | — |
| 7 | `63d205dec996` | `2826ce7fa4dc` | E3.5.1 | unicidade ativa + ordem canônica simétrica | REVERSIBLE | — |
| 8 | `f11551e97026` | `63d205dec996` | E3.5.2 | guarda de downgrade (relationships) | CONDITIONALLY_REVERSIBLE | **SIM** |
| 9 | `e2c89ee3aa59` | `f11551e97026` | E3.6 / LIB-06 | cria `provenance_records` | REVERSIBLE | — |
| 10 | `6bf0c0eb0c2e` | `e2c89ee3aa59` | E3.6.1 | `trace_id` em `provenance_records` | REVERSIBLE | — |
| 11 | `0460b6556563` | `6bf0c0eb0c2e` | E3.6.1 | guarda de downgrade (provenance) | CONDITIONALLY_REVERSIBLE | **SIM** |
| 12 | `b7c41d0e92a5` | `0460b6556563` | E3.7 / LIB-07 | 4 índices estruturais | REVERSIBLE | — |
| 13 | `c9a3f61b74d2` | `b7c41d0e92a5` | E3.9 / LIB-09 | cria tabelas de história causal | CONDITIONALLY_REVERSIBLE | **SIM** (embutida) |

**Verificado em execução real (PostgreSQL 16.14):**

- banco vazio: `head → base → head` completo — PASS;
- com história presente: downgrade **bloqueado**
  (`SEMANTICALLY_BLOCKED`), cadeia intacta em `c9a3f61b74d2`;
- `compare_metadata(ORM, schema real)` = **0 diffs**.

Princípio protegido: `HISTORICAL_PRESERVATION > DOWNGRADE_CONVENIENCE`
e `SCHEMA_REVERSIBILITY != HISTORICAL_ERASURE`. A reversibilidade
condicional é honesta: a migração é reversível **enquanto não houver
história a destruir**, e diz isso em vez de fingir reversibilidade
plena.

---

## 2. Error code manifest (§43)

### 2.1 Exceções de domínio — `PIA-8xxx`

22 códigos, **contíguos** `PIA-8001`–`PIA-8022`, **zero duplicatas**
(verificado sobre as definições reais, não sobre menções em docstring).
Próximo livre: **`PIA-8023`**.

| Código | Nome | Origem |
|---|---|---|
| PIA-8001 | `IDENTITY_IMMUTABLE` | E3.1 |
| PIA-8002 | `CLID_ALREADY_SET` | E3.1 |
| PIA-8003 | `COID_INVALID` | E3.2 |
| PIA-8004 | `COID_COLLISION` | E3.2 |
| PIA-8005 | `CLID_INVALID` | E3.3 |
| PIA-8006 | `LINEAGE_SELF_LINK` | E3.3 |
| PIA-8007 | `LINEAGE_DUPLICATE_EDGE` | E3.3 |
| PIA-8008 | `LINEAGE_ENDPOINT_NOT_FOUND` | E3.3 |
| PIA-8009 | `LINEAGE_EDGE_IMMUTABLE` | E3.3 |
| PIA-8010 | `TRANSFORMATION_RECORD_IMMUTABLE` | E3.4 |
| PIA-8011 | `REVISION_STATUS_INVALID_TRANSITION` | E3.4 |
| PIA-8012 | `REVISION_CURRENT_UNIQUENESS_VIOLATION` | E3.4.1 |
| PIA-8013 | `RELATIONSHIP_SELF_LINK` | E3.5 |
| PIA-8014 | `RELATIONSHIP_DUPLICATE` | E3.5 |
| PIA-8015 | `RELATIONSHIP_ENDPOINT_NOT_FOUND` | E3.5 |
| PIA-8016 | `RELATIONSHIP_IMMUTABLE` | E3.5 |
| PIA-8017 | `PROVENANCE_RECORD_IMMUTABLE` | E3.6 |
| PIA-8018 | `ACCESSIBILITY_INVALID_TRANSITION` | E3.6 |
| PIA-8019 | `SEARCH_CRITERIA_INVALID` | E3.8 |
| PIA-8020 | `CAUSAL_HISTORY_IMMUTABLE` | E3.9 |
| PIA-8021 | `CAUSAL_EVENT_SELF_PREDECESSOR` | E3.9 |
| PIA-8022 | `SYNC_PACKAGE_INVALID` | E3.11 |

### 2.2 Códigos diagnósticos de Integrity — `INTEGRITY-*`

**Deliberadamente fora** do catálogo `PIA-8xxx`: um ciclo encontrado é
**resultado válido de auditoria**, não exceção. Nenhum finding é
tratado como exceção; nenhuma exceção é tratada como finding.

| Código | Categoria |
|---|---|
| `INTEGRITY-LIN-001/002/003` | lineage: ciclo, self-link, endpoint pendente |
| `INTEGRITY-REL-001..004` | relationship: self-link, simétrica não-canônica, duplicata ativa, endpoint pendente |
| `INTEGRITY-VER-001` | múltiplos CURRENT por CLID |
| `INTEGRITY-TRF-001` | `actor_ref` de transformação pendente |
| `INTEGRITY-IDN-001` | vocabulário de acessibilidade inválido |
| `INTEGRITY-PRV-001` | `coid` de proveniência pendente |
| `INTEGRITY-CAU-001..004` | causal: ciclo, auto-predecessor, múltiplas histórias por sujeito, referência pendente |

### 2.3 Resultados de Synchronization

`SyncStatus` (`applied` / `conflict`), `SyncReport`, `SyncConflict` —
**estruturas transitórias, não persistidas, não códigos de erro**.
Conflito é resultado, não exceção; só pacote malformado ou
causalmente inválido levanta `PIA-8022`.

---

## 3. File / module manifest (§44)

### 3.1 `app/cognitive/` — 6.444 linhas

```
models/          causal_history.py  cognitive_object.py  enums.py
                 lineage_edge.py  provenance_record.py  relationship.py
                 transformation_record.py                              (7)

repositories/    causal_history_repository.py  index_repository.py
                 integrity_repository.py  lineage_repository.py
                 object_repository.py  provenance_repository.py
                 relationship_repository.py  search_repository.py
                 sync_repository.py  transformation_repository.py     (10)

services/        accessibility_manager.py  causal_history_manager.py
                 clid_manager.py  coid_manager.py  index_manager.py
                 integrity_manager.py  provenance_manager.py
                 relationship_engine.py  search_engine.py
                 synchronization_manager.py  version_manager.py       (11)

schemas/         cognitive_object.py  integrity.py  search_criteria.py
                 synchronization.py                                    (4)

errors/          codes.py  exceptions.py                               (2)
```

### 3.2 Testes cognitivos — 42 arquivos

```
tests/unit/cognitive/          errors, models (6), repositories (5),
                               schemas, services (12), multi_ai_readiness
tests/integration/cognitive/   14 arquivos, incluindo o novo
                               test_e3_12_final_integration_gate.py
```

### 3.3 Migrations — 13 arquivos em `alembic/versions/`

### 3.4 Documentação — 21 arquivos em `docs/entregas/entrega-3/`

Incluindo, desta entrega: `E3_12_E3_FINAL_INTEGRATION_GATE.md`,
`E3_FINAL_MANIFEST.md`, `E3_FINAL_MANIFEST.json`.

---

## 4. Fronteira de segurança (§45)

A E3 **não** introduziu:

```
ACL engine              = NONE
secrets persistence     = NONE
provider credentials    = NONE
arbitrary code execution= NONE   (sem eval/exec/os.system/subprocess)
filesystem traversal    = NONE
cloud credentials       = NONE
```

Verificado por teste executável (G19). Segurança/ACL detalhada
permanece entrega futura.

---

## 5. Fronteira de payload (§25)

```
TRANSCRIPT_AUTO_STORAGE = NONE
ARTIFACT_STORAGE        = DEFERRED
```

Nenhuma coluna do domínio armazena prompt, completion, transcript,
raciocínio oculto ou payload de provider (verificado contra
`Base.metadata` real, em G16). `payload_ref`, `evidence_refs` e
`source_ref` são **referências textuais**; conteúdo externo nunca é
copiado — nem pelo domínio, nem pelo pacote de sincronização.

---

## 6. Neutralidade de provider (§14)

```
PROVIDER_NEUTRAL_DOMAIN = PASS
```

- nenhum import de SDK de fornecedor em `app/`;
- nenhum ramo lógico condicionado a `provider_id == "<nome>"`;
- patrimônios de provider A, provider B e **sem provider algum**
  atravessam persistência, proveniência, busca, integridade e
  sincronização pelo mesmo caminho de código;
- `provider_id` e `model_id` `NULL` continuam válidos por contrato.

Providers são **dados**, nunca estrutura.

---

## 7. Estado de congelamento

```
E3.12_IMPLEMENTATION_GATE   = PASS
E3.12.1_IMPLEMENTATION_GATE = PASS
E3_FINAL_FREEZE             = PENDING_INDEPENDENT_AUDIT
GATE_E3_TO_E4               = PENDING
READY_FOR_E4                = FALSE
```
