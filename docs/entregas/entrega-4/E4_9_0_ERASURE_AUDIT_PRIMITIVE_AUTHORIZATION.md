# E4_9_0_ERASURE_AUDIT_PRIMITIVE_AUTHORIZATION

**Módulo:** E4.9.0 — corretivo arquitetural antecedente, **somente documental**
**Baseline:** `PATCH_CHAIN = 64` · HEAD `f274e99c47f7…` ✓ ·
PARENT `b1273583d723…` ✓ · TREE `55791f737742…` ✓ ·
PATCH_ID `eb03d46ef6dc…` ✓ · bundle SHA-256 `14a01360…79ea3` ✓ ·
migration head `7b2e4c9a15df` ✓ · `git status` limpo ✓

Baseline reproduzida contra PostgreSQL 16 real, com banco recriado:
**2369 passed / 1 skipped / 0 failed**, E4.3 **255/255**.

Trees registrados na baseline:

```text
backend/app              c055d5b79de841d4792eb2374f0b7cf806bd9663
backend/tests            39bb30899fd4b941d3e74d832b733201dbe1ab73
backend/alembic          65a066dea0925edc55ad88e0c774f56b1944254f
docs/entregas/entrega-4  a507e9f0a8df162c6604accc204c79faf5ced3a4
```

---

## 1. O que esta etapa faz, e o que não faz

Fecha por **autorização** a lacuna da Tensão D do preflight da E4.9:

```text
STOP_CONDITION = ERASURE_AUDIT_PRIMITIVE_GAP
```

```text
ARCHITECTURAL AUTHORIZATION != IMPLEMENTATION
ERASURE_RECORD = AUTHORIZED_NOT_IMPLEMENTED
```

Nenhum `.py`, teste, migração, tabela, enum, serviço ou repositório foi
criado ou alterado. A decisão está no
`EDR_E4_9_0_ERASURE_AUDIT_PRIMITIVE.md`; este documento registra o
enquadramento, as verificações e o que continua aberto.

---

## 2. Matriz — `ErasureRecord` não colapsa nada

Cinco conceitos que precisam permanecer separados, e o que cada um
responde:

| Conceito | Pergunta que responde | Onde vive | Persistido | Momento |
|---|---|---|---|---|
| `RetentionPolicy` | o que se aplica, sob qual versão | E4.9 (não implementada) | sim, versionada | configuração vigente |
| avaliação de retenção | este sujeito expirou, neste instante | E4.9 (não implementada) | **não** — resultado datado | avaliação |
| proposta de disposição | o que se propõe fazer | contrato inexistente | **não** | proposta |
| aprovação | quem autorizou, verificavelmente | **não existe em nenhuma camada** | — | autorização |
| `ErasureRecord` | o que foi **tentado** e o que foi **observado** | E4.9, autorizado aqui | sim, append-only | depois do efeito |

O par que mais convida ao colapso é o último: um sistema apressado
gravaria o recibo no momento da decisão, e passaria a afirmar
apagamentos que nunca ocorreram.

```text
POLICY SAYS WHAT APPLIES != ACTION HAPPENED
DECISION                 != EFFECT
RECORD                   != PROOF WITHOUT OBSERVED EFFECT
```

Por isso `PENDING`, `PROPOSED`, `APPROVED` e `SCHEDULED` ficam **fora**
do vocabulário de `outcome`, que admite apenas `SUCCEEDED`, `FAILED` e
`PARTIAL` — e sempre após tentativa real.

---

## 3. Opções A / B / C

| | A — apagar referente | B — `ErasureRecord` | C — apagar registro causal |
|---|---|---|---|
| Alcança conteúdo real | sim | não (é registro) | sim, destruindo o rastro |
| Preserva história causal | sim | sim | **não** |
| Distingue removido de nunca-existiu | com a referência marcada | **é a função dela** | não |
| Implementável na cadeia 64 | **não** — sem storage, porta ou credencial | **não** — só autorizada aqui | **não**, e rejeitada |
| Status | direção autorizada, não executável | `AUTHORIZED_NOT_IMPLEMENTED` | `NOT_AUTHORIZED` |

```text
AUTHORIZED_DIRECTION = A + B
OPTION_C = REJECTED_FOR_NORMAL_FLOW
```

Justificativa integral no EDR §7.

---

## 4. Metadados

Autorizados conceitualmente: EDR §5. Proibidos: EDR §5.1.

A regra que governa a lista de proibições em uma frase: **o registro não
pode conter nada que permita reconstruir ou relocalizar o que foi
apagado.** O identificador histórico do sujeito é a única exceção, e
existe justamente para sustentar a distinção que o contrato exige.

```text
HISTORICAL SUBJECT IDENTIFIER != LIVE CONTENT LOCATOR
```

Os nomes de campo são **contrato conceitual**, não autorização de
migração literal. Tipos, nullability, cardinalidade e constraints serão
decididos pela etapa que implementar, contra os contratos então
vigentes.

---

## 5. `CausalHistory`

```text
CAUSAL_HISTORY    = PRESERVED
CAUSAL_EVENT_TYPE = UNCHANGED
ERASURE_RECORD SUBJECT LINK = HISTORICAL IDENTIFIER, NOT CASCADING FK
```

Razões no EDR §6. A decisiva, em uma frase: um registro amarrado ao
sujeito por FK pode ser destruído pelo próprio efeito que deveria
provar.

---

## 6. Stop Conditions

```text
RETENTION_OPERATION_AUTHORITY_GAP   = CLOSED_FINAL
ERASURE_AUDIT_PRIMITIVE_GAP         = CLOSED_CANDIDATE_BY_AUTHORIZATION

ERASURE_TARGET_OWNERSHIP_GAP        = OPEN
LEGAL_ERASURE_CAUSAL_HISTORY_GAP    = OPEN_CONDITIONAL
ON_EXPIRY_ACTION_UNRESOLVED         = OPEN
RETENTION_RETRIEVAL_COMPOSITION_GAP = OPEN
DESTRUCTIVE_EXECUTION_AUTHORITY_GAP = OPEN
```

Duas das sete fechadas, cinco abertas. A E4.9 continua bloqueada.

---

## 7. Verificações documentais (§11 do prompt)

| # | Verificação | Resultado |
|---|---|---|
| 1 | termos normativos consistentes nos quatro documentos | conferido |
| 2 | `ErasureRecord` aparece como `AUTHORIZED_NOT_IMPLEMENTED` | nos quatro |
| 3 | nenhuma frase alega que o PIA-OS já apaga conteúdo | conferido |
| 4 | nenhuma frase diz que registro é prova sem efeito observado | conferido |
| 5 | nenhuma FK destrutiva prescrita | conferido |
| 6 | `OPTION_C` permanece não autorizada | conferido |
| 7 | as demais Stop Conditions continuam abertas | conferido |
| 8 | imprecisão da E4.3.5 corrigida | **NÃO CUMPRIDO — ver §8** |

---

## 8. O item 8 do §11 não pôde ser cumprido

A frase a corrigir — "quem executa é a E4.9" — existe em **um único
lugar**, a docstring de `RETENTION_DISPOSITION` em
`backend/app/memory/models/governance_enums.py`. Ela **não** aparece nos
documentos da E4.3.5, que já usam formulação neutra.

Corrigi-la exigiria editar produção, e três seções deste mesmo prompt o
proíbem: §9 (não alterar `.py`), §12 (`PRODUCTION_TREE = IDENTICAL`) e
§14.11 (alterar tree de produção é Stop Condition).

Optei por **não editar** e registrar. O texto neutro proposto e a
formulação normativa que passa a prevalecer estão no EDR §11:

```text
AUTHORIZED_EXECUTOR = NONE
```

A substituição exige um corretivo próprio de uma linha — `E4.3.5.1`,
docstring apenas — que o titular precisa autorizar, porque altera o tree
de produção. É decisão de autoridade, não do implementador.

---

## 9. Escopo desta entrega

Criados:

```text
docs/entregas/entrega-4/EDR_E4_9_0_ERASURE_AUDIT_PRIMITIVE.md
docs/entregas/entrega-4/E4_9_0_ERASURE_AUDIT_PRIMITIVE_AUTHORIZATION.md
```

Atualizados pontualmente:

```text
docs/entregas/entrega-4/E4_PRIMITIVE_OWNERSHIP.md
docs/entregas/entrega-4/E4_DEFERRED_INVENTORY.md
```

```text
PRODUCTION_TREE = IDENTICAL   backend/app     c055d5b7…
TEST_TREE       = IDENTICAL   backend/tests   39bb3089…
ALEMBIC_TREE    = IDENTICAL   backend/alembic 65a066de…
```

Nenhum `.py` tocado. Nenhuma migração. Nenhum código de erro novo —
`NEXT_FREE_ERROR_CODE = PIA-8041`, inalterado.

---

## 10. Gates

```text
FULL_SUITE       2369 passed / 1 skipped / 0 failed
RAW_SUITE        2016 passed / 354 skipped / 0 failed
GLOBAL_COVERAGE  99,13%   APP_MEMORY 100%   APP_COGNITIVE 100%
RUFF PASS   BLACK PASS (`black --check .`, 24.10.0)
MYPY 7 históricos, NEW = 0   SCHEMA_ORM_DRIFT 0
ALEMBIC single head 7b2e4c9a15df   git diff --check CLEAN
E4.3 255/255
```

Idênticos à baseline, como se espera de um patch que não toca código.

---

## 11. Compatibilidade SOPHIA / PIA-OS

```text
USER_AUTHORITY_PRESERVED = TRUE
SOPHIA_BRAND_PIA_OS_CODEBASE_PRESERVED = TRUE
AUTOMATION_SCOPE = NONE
PERSISTENCE_BEHAVIOR = NONE
APPROVAL_GATE_IMPLEMENTATION = NONE
OBSERVATION_PREPARATION_EXECUTION_DISTINGUISHED = TRUE
CURRENT_CAPABILITY_NOT_OVERSTATED = TRUE
FROZEN_MODULES_UNCHANGED = TRUE
```

Schedule, multi-IA, frontend, conectores e operações remotas:
`NOT_APPLICABLE`.

---

## 12. Gate

```text
E4_9_0_IMPLEMENTATION = DOCUMENTAL_AUTHORIZATION_COMPLETE
E4_9_0_STATUS = AWAITING_INDEPENDENT_AUDIT
PATCH_CHAIN = 65
ERASURE_RECORD = AUTHORIZED_NOT_IMPLEMENTED
E4_9_IMPLEMENTATION = NOT_STARTED
READY_FOR_E4_9 = FALSE
READY_FOR_E4_10 = FALSE
```
