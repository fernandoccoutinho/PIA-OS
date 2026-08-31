# E4 — Manifesto Final da Entrega 4

Inventário da Entrega 4 no fechamento da cadeia 97. Representa a mesma
informação de `E4_FINAL_MANIFEST.json`, e a coerência entre os dois é
verificada por guarda automática (`test_m16`), não por revisão manual.

```text
CHAIN            97
PARENT_CHAIN     96
MIGRATION_HEAD   e7c25a91f4b3
PRODUCTION_DELTA NONE
MIGRATION_DELTA  NONE
```

Vocabulário fechado de status:

```text
IMPLEMENTED · CONTRACT_ONLY · DEFERRED
FORBIDDEN · NOT_APPLICABLE · FUTURE_STOP_CONDITION
```

`CONTRACT_ONLY` nunca é apresentado como `IMPLEMENTED`. Um contrato
entregue sem adaptador é uma fronteira declarada, não uma capacidade.

---

## 1. Fatias

| Fatia | Nome | Status |
|---|---|---|
| `E4.0` | Architecture Contract Freeze | IMPLEMENTED |
| `E4.1` | Memory Domain Foundation | IMPLEMENTED |
| `E4.2` | Context Manager | IMPLEMENTED |
| `E4.3` | Governance Policy | IMPLEMENTED |
| `E4.4` | Persistence Manager | IMPLEMENTED |
| `E4.5` | Consolidation Manager | IMPLEMENTED |
| `E4.6` | Retrieval Manager | IMPLEMENTED |
| `E4.7` | Accessibility Policy Manager | IMPLEMENTED |
| `E4.8` | Memory Isolation | IMPLEMENTED |
| `E4.9` | Retention, Approval and Destructive Execution | IMPLEMENTED |
| `E4.10` | Compliance Boundary | IMPLEMENTED |
| `E4.11` | Validated Experience Registry | IMPLEMENTED |
| `E4.12` | Final Integration Gate | IMPLEMENTED |

## 2. Tabelas

| Tabela | Fatia | Append-only |
|---|---|---|
| `memory_domains` | E4.1 | não |
| `memory_domain_memberships` | E4.1 | não |
| `governance_policies` | E4.3 | não |
| `accessibility_policies` | E4.7 | não |
| `retention_policies` | E4.9.6 | não |
| `erasure_records` | E4.9.5 | **sim** |
| `approval_records` | E4.9.9.a | **sim** |
| `approval_record_targets` | E4.9.9.a | **sim** |
| `approval_record_governance_items` | E4.9.9.a | **sim** |
| `validated_experiences` | E4.11 | **sim**, inclusive contra `TRUNCATE` |

Cabeça do Alembic: `e7c25a91f4b3`. A E4.12 **não** cria migration.

## 3. Códigos de erro

```text
FAIXA OCUPADA   PIA-8000 .. PIA-8051
PRÓXIMO LIVRE   PIA-8052
ACRESCENTADOS PELA E4.12   0
```

## 4. APIs públicas deliberadas

| API | Status | Nota |
|---|---|---|
| `GOVERNANCE_RESOLVE` | IMPLEMENTED | decide admissibilidade, nunca verdade |
| `ACCESSIBILITY_TRANSITION` | IMPLEMENTED | muda alcançabilidade, nunca existência |
| `RETENTION_ASSESSMENT` | IMPLEMENTED | informa, nunca autoriza exclusão |
| `DESTRUCTIVE_EXECUTION` | IMPLEMENTED | exige aprovação humana consumida |
| `COMPLIANCE_EVALUATION` | IMPLEMENTED | diagnóstico transitório, zero writes |
| `VALIDATED_EXPERIENCE_APPEND` | IMPLEMENTED | append-only, sem autoridade |
| `REMOTE_HTTP_API` | NOT_APPLICABLE | nenhuma superfície remota nesta entrega |

## 5. Fronteiras sem adaptador

| Fronteira | Status |
|---|---|
| `ErasureEffectPort` | CONTRACT_ONLY |
| `ErasureTargetResolverPort` | CONTRACT_ONLY |
| `AUTHENTICATOR` | NOT_APPLICABLE |

```text
INTERNAL_COMPOSITION_COMPLETE != PRODUCTION_DELETION_AVAILABLE
```

## 6. Inventário final de deferidos

| Item | Status | Declaração |
|---|---|---|
| `VALIDATED_EXPERIENCE_TRANSPORT` | DEFERRED | contrato de portabilidade e atribuição de origem **entregues**; transporte não implementado — exigiria alterar `SECTION_BY_TABLE` na E3 congelada |
| `EXCEPTIONAL_CAUSAL_RECORD_ERASURE` | FUTURE_STOP_CONDITION | permanece adiado; só vira bloqueio se um requisito futuro depender dele |
| `COUT_P_V1_2` | DEFERRED | Predictive Accessibility é candidato **exclusivo da E5**; nada implementado na E4. `DEFERRED_CANDIDATE != FUTURE_STOP_CONDITION` — nada na E4 depende dele, logo ele não bloqueia nem poderia bloquear esta entrega |
| `DOC_ROOTS_UNIFICATION` | DEFERRED | as duas raízes documentais permanecem separadas |
| `VALIDATED_BY_AUTHENTICATION` | NOT_APPLICABLE | atribuição sem autenticação, declarada e não alegada |
| `MATERIAL_EFFECT_ADAPTERS` | CONTRACT_ONLY | apenas contratos e dublês confinados a `backend/tests/` |

```text
ACTIVE_STOP_CONDITION = NONE
```

Nenhum dos itens acima bloqueia a E4.12: são deferidos **já
declarados**, e o gate final não depende de nenhum deles hoje.

## 7. Capacidades proibidas — ausentes

```text
LEARNING_ENGINE                 FORBIDDEN · ausente
AUTOMATIC_SELECTION             FORBIDDEN · ausente
SCORE_OR_RANKING                FORBIDDEN · ausente
AUTOMATIC_PROMOTION             FORBIDDEN · ausente
BACKGROUND_WORKER               FORBIDDEN · ausente
SCHEDULER                       FORBIDDEN · ausente
QUEUE                           FORBIDDEN · ausente
PROVIDER_SDK                    FORBIDDEN · ausente
PRODUCTION_DESTRUCTIVE_ADAPTER  FORBIDDEN · ausente
```

## 8. Freeze efetivo da E3

```text
COMMIT ORIGINAL       014455f93bf7433232a945062e2024d536f7a004
ÁRVORE ORIGINAL       f32780bc37c45bc495aed000898354a7d71c8b1b
COMMIT EFETIVO        b4e61a4702a4428dd1dea7464efe09a180bf797c
ÁRVORE EFETIVA        be407b46f679a009e0f7f7e9f01fb784f08dea54
MODIFICADA DEPOIS     NÃO
```

Delta autorizado — **E3.4.2 + E3.4.2.1**, três modificados e dois
adicionados:

| Status | Modo | Caminho |
|---|---|---|
| M | 100644 | `backend/app/cognitive/errors/__init__.py` |
| M | 100644 | `backend/app/cognitive/errors/codes.py` |
| M | 100644 | `backend/app/cognitive/errors/exceptions.py` |
| A | 100644 | `backend/app/cognitive/schemas/multi_input_transformation.py` |
| A | 100644 | `backend/app/cognitive/services/multi_input_transformation_manager.py` |

```text
INSERTION_STATS != PATH_STATUS
```

Uma leitura por estatística de inserções concluiria que nada
pré-existente foi tocado. Três arquivos **foram** modificados, e a
guarda compara caminho, status, modo e blob dos dois lados.

## 9. Raízes documentais

```text
ROOT_DOCS_E4      = HISTORICAL_ARCHITECTURE_AND_EDRS
BACKEND_DOCS_E4   = CHECKED_DELIVERY_EDRS_AND_FINAL_MANIFEST
DOC_ROOTS_UNIFIED = NO
```

`docs/entregas/entrega-4/` guarda a arquitetura congelada e os EDRs
históricos, e **não** é coberta pelo checker de consistência.
`backend/docs/entregas/entrega-4/` guarda os EDRs de entrega e este
manifesto, e é coberta. A divergência é histórica, declarada, e não foi
unificada nesta fatia.

## 10. Caracterizações

```text
HISTÓRICAS   14, copiadas byte a byte e reexecutadas em zero
E4.12        reproduce_e412_final_gate_gaps.py — 14 sondas
TOTAL        15 instrumentos no pacote
```

## 10.1 Candidatos rejeitados

```text
afe2c5ec  local, NÃO publicado — reprovou a própria caracterização (4/12)
938c553a  publicado, REJEITADO pela auditoria independente com sete achados
          estatística medida: 7 arquivos, 2252 inserções
```

Nenhum é apagado desta história. `PATCH_CHAIN` permanece **97**;
`CHAIN_98 = NOT_CREATED`.

## 11. Estado final

```text
E4_9                      = FROZEN
E4_10                     = FROZEN
E4_11                     = FROZEN
E4_12_IMPLEMENTATION_GATE = PASS
E4_FINAL_FREEZE           = PENDING_INDEPENDENT_AUDIT
GATE_E4_TO_E5             = PENDING
READY_FOR_E5              = FALSE
E5                        = NOT_STARTED
PASS_FINAL                = NOT_DECLARED
```

`PASS_FINAL` pertence exclusivamente à auditoria independente e não é
declarado aqui.
