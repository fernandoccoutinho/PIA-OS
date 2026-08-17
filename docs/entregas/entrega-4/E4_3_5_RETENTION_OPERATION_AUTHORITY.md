# E4_3_5_RETENTION_OPERATION_AUTHORITY

**Módulo:** E4.3.5 — corretivo antecedente de governança
**Baseline:** `PATCH_CHAIN = 63` · HEAD `b1273583d723…` ✓ ·
PARENT `a0bdad651ad2…` ✓ · TREE `7315c177d572…` ✓ ·
PATCH_ID `9c1edd327057…` ✓ · bundle SHA-256 `0e90e25d…6e48` ✓ ·
patch SHA-256 `e672da68…e664` ✓ · migration head `7b2e4c9a15df` ✓ ·
`git status` limpo ✓ · suíte **2291 passed / 1 skipped / 0 failed** ✓ ·
RAW **1957 / 335** ✓ · coverage **99,13%** ✓

Trees registrados na baseline:
`cognitive be407b46f679a009e0f7f7e9f01fb784f08dea54`,
`memory 0d8fde26cb3ade0a7e4d3bf49d2af73a7a06f81e`,
`alembic 65a066dea0925edc55ad88e0c774f56b1944254f`,
`entrega-4 39d480b1e45b39da606308855f2901283f1f158b`.

---

## 1. Reprodução da lacuna

Executada contra a baseline, sem adulterar o repositório. Tabela
completa no `EDR_E4_3_5_RETENTION_OPERATION_AUTHORITY.md` §1.

```text
GAP = THE THREE RETENTION AUTHORITIES ARE NOT REPRESENTABLE
```

## 2. Decisão

Três operações distintas, nunca uma genérica:

```text
RETENTION_ASSESSMENT  = "retention_assessment"
RETENTION_DISPOSITION = "retention_disposition"
LEGAL_ERASURE         = "legal_erasure"
```

Justificativa integral no EDR §3 e §4.

## 3. Provas

| Propriedade | Prova |
|---|---|
| curinga histórico não alcança as três | `NOT_APPLICABLE` nas três, em memória e contra PG, com controle positivo `READ → ADMISSIBLE` na mesma policy |
| opt-in explícito concede só a operação citada | as outras duas seguem `NOT_APPLICABLE` |
| autoridade sobre uma não concede as outras | matriz 3×2 completa |
| `READ`/`TRANSFORM`/`ACCESSIBILITY_TRANSITION` não concedem | parametrizado nas três |
| `DENY_OVERRIDES` continua valendo | `ADMIT` + `DENY` na mesma operação → `INADMISSIBLE` |
| vínculo de contexto da E4.3.4 preservado | domínio, ator e propósito casam e deixam de casar |
| payload publicado byte-idêntico | `rules::text` **e** `updated_at` iguais antes/depois |
| policy publicada imutável | mutação ORM direta recusada com `PIA-8028` |
| autoridade nova entra só por nova publicação | v1 curinga `NOT_APPLICABLE`, v2 opt-in `ADMISSIBLE` |
| zero escritas na resolução | espião em `before_cursor_execute`: `INSERT/UPDATE/DELETE = 0` |
| round-trip pelo JSONB | token gravado e devolvido como membro tipado |
| `EMPTY_OPERATIONS_SCOPE_V1` fechado | comparado ao literal; as três fora dele |
| sem ramo especial por operação | AST de `matches()` sem os três tokens |
| sem capacidade de retenção | AST de todo `app/memory`, com limites de palavra |

## 4. Persistência

```text
NEW_PERSISTENT_ENTITY = NO
MIGRATION_REQUIRED = NO
MIGRATION_HEAD = 7b2e4c9a15df (inalterado)
SCHEMA_ORM_DRIFT = 0
```

`to_regclass('public.retention_policies')` devolve `NULL` — verificado
em teste.

## 5. Códigos de erro

```text
NEXT_FREE_ERROR_CODE = PIA-8041 (inalterado)
RESERVED_BY_E4_3_5 = NO
```

Não há caminho de execução novo, logo não há código de erro novo. Falha
de vocabulário continua seguindo os contratos atuais: `ValueError` no
enum, `TypeError` na regra.

## 6. Testes

**E4.3 passa de 177 para 255** (+78), com estes seletores reais:

```text
tests/unit/memory/test_governance.py                        128  (era 69)
tests/unit/memory/test_governance_safety.py                  81  (inalterado)
tests/integration/memory/test_governance_integration.py      46  (era 27)
```

Conferido: `69 + 81 + 27 = 177` na baseline, `128 + 81 + 46 = 255` na
candidata. O crescimento vem em boa parte de `parametrize` sobre as três
operações — não são 78 casos escritos à mão.

### 6.1 Classificação empírica contra a cadeia 63

O arquivo de testes definitivo **não coleta** na baseline: as constantes
de módulo referenciam `CognitiveOperation.RETENTION_ASSESSMENT` e o
`AttributeError` derruba a coleção inteira. Isso **não é prova
comportamental** e não é apresentado como tal (§9.1 do prompt).

A classificação foi obtida com um **stub de caracterização** rodado nas
duas cadeias, contendo o subconjunto formulável na baseline:

| Item | Cadeia 63 | Cadeia 64 | Classe |
|---|---|---|---|
| escopo histórico tem exatamente 7 | PASSA | PASSA | guarda |
| curinga alcança todas as históricas | PASSA | PASSA | guarda |
| nenhuma operação genérica `RETENTION`/`ERASURE` | PASSA | PASSA | guarda |
| nenhum alias no enum | PASSA | PASSA | guarda |
| tokens desconhecidos recusados | PASSA | PASSA | guarda |
| payload antigo byte-idêntico | PASSA | PASSA | guarda |
| token desconhecido no payload levanta | PASSA | PASSA | guarda |
| `matches()` sem ramo por operação | PASSA | PASSA | guarda |
| `app/memory` sem capacidade de retenção | PASSA | PASSA | guarda |
| enum tem 11 membros | **FALHA** | PASSA | contrato |

**Nove passam nos dois lados**, e é o resultado esperado: são guardas de
não-regressão, e o trabalho delas é justamente não mudar. O único item
que muda de resultado muda **por contrato**, não por defeito.

Os testes de autoridade propriamente ditos — opt-in admite, `DENY`
torna inadmissível, curinga devolve `NOT_APPLICABLE`, round-trip no
JSONB — **não são formuláveis na cadeia 63**, porque a autoridade não
existe lá. Essa impossibilidade **é** a lacuna; não é um defeito que
falha.

```text
ABSENT SYMBOL != BEHAVIOURAL DEFECT
NOT FORMULABLE ON BASELINE != TEST THAT FAILED ON BASELINE
```

### 6.2 Um teste existente foi atualizado

`test_gv1_cognitive_operation_vocabulary_is_closed` enumera o
vocabulário literalmente e falhou depois da ampliação — comportamento
correto dele. Foi **atualizado com nota**, não afrouxado nem removido:
continua exaustivo, continua literal, e continua falhando diante de
qualquer membro não declarado ali.

## 7. Resultados

```text
FULL_SUITE       2369 passed / 1 skipped / 0 failed   (baseline 2291)
RAW_SUITE        2016 passed / 354 skipped / 0 failed (baseline 1957/335)
GLOBAL_COVERAGE  99,13%       APP_MEMORY 100%   APP_COGNITIVE 100%
governance_enums.py  53 statements, 0 missing, 100%
RUFF PASS   BLACK PASS (`black --check .`, 24.10.0)
MYPY 7 erros históricos em 3 arquivos, NEW = 0
SCHEMA_ORM_DRIFT 0   ALEMBIC single head 7b2e4c9a15df
```

Regressões, todas delta 0: E3 598, E3.4.2/.1 134, E4.1 40, E4.2 42,
E4.4 74, E4.5 187, E4.6 198, E4.7 240, E4.8 146.

**Nota sobre o RAW.** Passou de `1957/335` para `2016/354`: +59
executados e +19 pulados, somando os +78 novos. Medido diretamente, não
derivado: os +59 são os testes unitários novos (`test_governance.py`
69 → 128) e os +19 são os de integração (27 → 46), pulados sem
`DATABASE_URL` exatamente como os demais de integração. Nenhum número
foi ajustado por aritmética.

## 8. Escopo

Produção — **um arquivo**:

```text
backend/app/memory/models/governance_enums.py    +63 / -1
```

`matches()`, `GovernanceManager`, `GovernanceDecision`,
`GovernanceResolution`, repositórios e schemas **não foram tocados**: o
mecanismo positivo da E4.3.3 já trata membro novo sem código novo.
`backend/app/memory/schemas/governance.py`, que o §6 do prompt
autorizava condicionalmente, não foi necessário — e há teste que trava
essa confinação.

Testes e documentação:

```text
backend/tests/unit/memory/test_governance.py
backend/tests/integration/memory/test_governance_integration.py
docs/entregas/entrega-4/EDR_E4_3_5_RETENTION_OPERATION_AUTHORITY.md
docs/entregas/entrega-4/E4_3_5_RETENTION_OPERATION_AUTHORITY.md
```

Trees protegidos: `cognitive` e `alembic` **inalterados**.

## 9. Compatibilidade SOPHIA / PIA-OS

```text
USER_AUTHORITY_PRESERVED = TRUE
SOPHIA_BRAND_PIA_OS_CODEBASE_PRESERVED = TRUE
AUTOMATION_SCOPE = NONE
PERSISTENCE_BEHAVIOR = NONE
APPROVAL_GATE_IMPLEMENTATION = NONE
OBSERVATION_PREPARATION_EXECUTION_DISTINGUISHED = TRUE
CURRENT_CAPABILITY_NOT_OVERSTATED = TRUE
FROZEN_MODULES_UNCHANGED_EXCEPT_EXPLICIT_E4_3_CORRECTIVE = TRUE
```

Schedule, multi-IA, frontend, conectores e operações remotas:
`NOT_APPLICABLE` — nada neste corretivo os toca.

## 10. Gate

```text
E4_3_5_IMPLEMENTATION = COMPLETE
E4_3_5_STATUS = AWAITING_INDEPENDENT_AUDIT
PATCH_CHAIN = 64
RETENTION_OPERATION_AUTHORITY_GAP = CLOSED_CANDIDATE
E4_9_IMPLEMENTATION = NOT_STARTED
READY_FOR_E4_9 = FALSE
READY_FOR_E4_10 = FALSE
```

As outras seis Stop Conditions da E4.9 permanecem abertas — ver EDR §8.
