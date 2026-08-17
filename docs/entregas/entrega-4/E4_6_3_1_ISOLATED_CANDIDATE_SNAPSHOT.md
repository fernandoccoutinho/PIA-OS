# E4_6_3_1_ISOLATED_CANDIDATE_SNAPSHOT

**Módulo:** E4.6.3.1 — corretivo de fronteira de objetos no gate de recuperação
**Origem:** auditoria independente da cadeia 68, achado bloqueante **A1**
**Baseline:** `PATCH_CHAIN = 68` · HEAD `18ee1c20ad22…` ✓ ·
PARENT `f5a380366ffc…` ✓ · TREE `135ba3d8a221…` ✓ ·
PATCH_ID `0702ff09117f…` ✓ · bundle SHA-256 `2a7b26e1…b6748` ✓ ·
migration head `7b2e4c9a15df` ✓ · árvore limpa ✓

Baseline reproduzida com PostgreSQL 16 real, banco recriado:
**2423 passed / 1 skipped / 0 failed**, RAW **2056 / 368**.

---

## 1. O defeito, reproduzido antes de escrever

A E4.6.3 entregava ao gate a **própria instância** devolvida pela
Search:

```python
candidate_gate.allows(objeto)   # cadeia 68
```

Executei a prova adversarial descrita pela auditoria contra a cadeia 68,
com o `MemoryRetrievalManager` real:

```text
COID que a Search devolveu (antes)  : f81bc648-0575-42e1-bccb-30777c2beaa6
COID fabricado pelo gate            : d8f42dbf-5b8f-409e-9dea-7eb203d565f3
COID no ITEM PROJETADO              : d8f42dbf-5b8f-409e-9dea-7eb203d565f3
accessibility no item projetado     : latent

gate recebeu a MESMA instância?     : True
hit da Search foi ALTERADO?         : True
item projetado != COID original?    : True

DEFECT_REPRODUCED = TRUE
```

```text
BOOLEAN RETURN   != IMMUTABLE ARGUMENT
SHARED REFERENCE != STRICTLY REDUCTIVE GATE
```

### 1.1 O erro de raciocínio, nomeado

A E4.6.3 publicou `THE SHAPE OF THE CONTRACT IS THE GUARANTEE`. Isso é
**meio verdadeiro, e o meio que falta era o que importava**: a forma do
contrato governa o que o colaborador pode **devolver**; ela não diz nada
sobre o que ele pode fazer com o que **recebe**. `CognitiveObjectView`
ser um `Protocol` de propriedades somente-leitura protege o código
tipado comum e não torna a instância concreta imutável em runtime.

```text
CONTRACT SHAPE GOVERNS THE RETURN
VALUE ISOLATION GOVERNS THE ARGUMENT
BOTH ARE REQUIRED
```

Em produção o risco é maior que no dublê: o candidato pode ser uma
entidade ORM ligada à `Session`, e sujá-la alcançaria um flush
posterior — contradizendo `DATABASE_WRITES = 0`.

---

## 2. A correção

Uma dataclass privada, `frozen=True, slots=True`, construída **antes** da
chamada, contendo apenas os seis valores do contrato:

```python
@dataclass(frozen=True, slots=True)
class _RetrievalCandidateSnapshot:
    id: uuid.UUID
    clid: uuid.UUID | None
    accessibility: str
    revision_status: str | None
    created_at: datetime
    deleted_at: datetime | None
```

```text
GATE_RECEIVES_SNAPSHOT_NOT_SEARCH_HIT = TRUE
PROJECTION_SOURCE = ORIGINAL_VALIDATED_HIT
SNAPSHOT_MUTATION_EFFECT = NONE_OUTSIDE_GATE
```

Sem payload, conteúdo, `Session`, repositório, relacionamento ORM,
callback, objeto de contexto ou coleção mutável — qualquer um deles
devolveria ao gate um caminho de volta à entidade real.

### 2.1 O que a imutabilidade da cópia **não** garante

`frozen=True` recusa atribuição normal e `slots=True` impede atributo
novo, mas **nenhum dos dois impede `object.__setattr__`** — e não
precisam:

```text
SNAPSHOT IMMUTABILITY != THE GUARANTEE
VALUE ISOLATION       =  THE GUARANTEE
```

A cópia mutada morre ao fim da iteração. Isso é dito explicitamente na
docstring do teste correspondente, para que ninguém leia `frozen=True`
como a fronteira.

### 2.2 Detecção posterior foi rejeitada

Comparar impressões digitais depois da chamada deixaria a mutação
acontecer, o estado da `Session` potencialmente sujo e a restauração
ambígua.

```text
ISOLATION BEFORE THE CALL != DAMAGE DETECTION AFTER IT
```

### 2.3 O diagnóstico cita o COID original

`coid_original` é lido **antes** de construir o snapshot. Ler o `id` da
cópia depois exibiria um identificador que o próprio colaborador pode
ter fabricado — um gate hostil não escolhe o que aparece no erro.

```text
ERROR IDENTITY = ORIGINAL COID, NEVER THE COPY'S
```

---

## 3. Ordem preservada

```text
Governança READ
→ escopo base
→ Search
→ validação do hit ORIGINAL
→ admissibilidade do ORIGINAL
→ duplicata pelo COID ORIGINAL
→ captura dos valores no snapshot
→ gate avalia SOMENTE o snapshot
→ offset
→ projeção a partir do hit ORIGINAL
→ limit e has_more
```

Nada mais mudou. Posição do gate, injeção por chamada, paginação,
fail-closed do retorno e neutralidade semântica foram **aceitos pela
auditoria** e continuam como estavam.

---

## 4. Provas (§7 do prompt)

| # | Exigência | Teste |
|---|---|---|
| 1 | gate recebe instância distinta (`is not`) | `test_e4631_gate_receives_an_instance_distinct_from_the_search_hit`, `test_ri4631_gate_receives_a_snapshot_not_the_orm_entity` |
| 2 | snapshot satisfaz a porta e tem valores iguais | `test_e4631_snapshot_satisfies_the_view_protocol_with_the_original_values` |
| 3 | atribuição normal falha | `test_e4631_snapshot_refuses_normal_assignment_and_new_attributes` |
| 4 | gate adversarial nos 6 campos não altera o hit | `test_e4631_adversarial_gate_cannot_alter_the_search_hit`, `..._cannot_alter_any_projected_field` |
| 5 | nenhum campo projetado é alterado | `test_e4631_adversarial_gate_cannot_alter_any_projected_field` |
| 6 | COID fabricado nunca aparece | `test_e4631_fabricated_coid_never_appears_in_the_result`, `test_ri4631_persisted_state_is_untouched_after_a_hostile_gate` |
| 7 | resultado continua subsequência exata | `test_e4631_result_with_hostile_gate_is_still_a_subsequence_of_the_base_view`, `test_ri4631_...` |
| 8 | entidade ORM real não entra em `session.dirty` | `test_ri4631_hostile_gate_does_not_dirty_the_session` (dirty, new e deleted vazios) |
| 9 | nenhuma escrita, flush ou commit | `test_ri4631_hostile_gate_produces_no_write_and_no_flush` (espião + `flush()` explícito) |
| 10 | fail-closed cita o COID original | `test_e4631_invalid_return_error_cites_the_original_coid`, `..._exception_error_cites_the_original_coid_and_preserves_cause` |
| 11 | duplicata antes do snapshot/gate | `test_e4631_duplicate_is_still_detected_before_the_snapshot` |
| 12 | offset, backfill, limit, `has_more`, ordem | `test_e4631_pagination_still_correct_with_a_mutating_gate` |
| 13 | recusa de governança e escopo seguem invisíveis | `test_e4631_governance_denial_still_hides_everything_from_a_hostile_gate` |
| 14 | chamadas sucessivas sem estado compartilhado | `test_e4631_successive_calls_do_not_share_snapshots`, `..._mutating_the_snapshot_does_not_leak_between_candidates` |
| 15 | regressão reproduz a prova da auditoria | `test_e4631_adversarial_gate_cannot_alter_the_search_hit` — **falha na cadeia 68** |
| — | projeção nunca lê o snapshot | `test_e4631_projection_never_reads_the_snapshot` (AST de `_coletar`) |
| — | snapshot sem referência de volta | `test_e4631_snapshot_carries_no_reference_back_to_the_entity` (`__dict__` ausente por `slots`) |

**O dublê usado é mutável de propósito.** `ObjetoFalso`, usado no resto
do arquivo, é `frozen` — um teste adversarial contra ele não provaria
nada sobre o caso real. `ObjetoMutavel` reproduz a mutabilidade da
entidade ORM.

### 4.1 Classificação empírica contra a cadeia 68

Executada, não afirmada. Os testes novos foram copiados para um clone da
cadeia 68 e rodados lá:

```text
unitários E4.6.3.1   : 12 FALHAM por comportamento, 5 passam nos dois lados
integração E4.6.3.1  :  5 FALHAM por comportamento, 1 passa nos dois lados
```

Os **17 que falham** são prova comportamental do defeito. Os **6 que
passam nos dois lados** são guardas, e é o resultado esperado deles:

```text
test_e4631_snapshot_satisfies_the_view_protocol_with_the_original_values
test_e4631_pagination_still_correct_with_a_mutating_gate
test_e4631_gate_decides_using_the_original_values
test_e4631_governance_denial_still_hides_everything_from_a_hostile_gate
test_e4631_projection_never_reads_the_snapshot
test_ri4631_snapshot_carries_the_real_values_of_the_orm_entity
```

Nenhum `ImportError` ou `AttributeError` foi contabilizado como prova
comportamental: os arquivos coletam nos dois lados, porque o corretivo
não introduziu símbolo público novo.

---

## 5. Escopo

Produção — **um arquivo**:

```text
backend/app/memory/services/retrieval_manager.py   +94 / -4
```

`backend/app/memory/ports/retrieval.py` **não mudou**: a assinatura
pública já aprovada (`allows(candidate) -> bool`) continua idêntica, e o
snapshot satisfaz `CognitiveObjectView` estruturalmente.

Testes e documentação:

```text
backend/tests/unit/memory/test_retrieval.py                    +410
backend/tests/integration/memory/test_retrieval_integration.py +222
docs/entregas/entrega-4/E4_6_3_1_ISOLATED_CANDIDATE_SNAPSHOT.md    (novo)
docs/entregas/entrega-4/EDR_E4_6_3_RETRIEVAL_COMPOSITION_POINT.md  (nota de correção)
docs/entregas/entrega-4/E4_6_3_RETRIEVAL_COMPOSITION_POINT.md      (nota de correção)
```

Os dois documentos da E4.6.3 receberam nota de correção **sem reescrever
história**: o overclaim continua no texto, marcado como tal.

```text
MIGRATION_DELTA = 0   SCHEMA_DELTA = 0
GOVERNANCE_DELTA = 0  E4_8_DELTA = 0   PORT_SIGNATURE_DELTA = 0
NEW_ERROR_CODE = NONE  (NEXT_FREE_ERROR_CODE = PIA-8041)
```

`backend/alembic` e `app/cognitive` permanecem byte a byte idênticos.

---

## 6. Gates medidos

```text
FULL_SUITE       2446 passed / 1 skipped / 0 failed   (baseline 2423)
RAW_SUITE        2073 passed / 374 skipped / 0 failed (baseline 2056/368)
GLOBAL_COVERAGE  99,14%                               (baseline 99,14%)
app/memory/services/retrieval_manager.py 192 statements, 0 missing, 100%
app/memory/ports/retrieval.py             26 statements, 0 missing, 100%
APP_MEMORY 100%   APP_COGNITIVE 100%
RUFF PASS   BLACK PASS (`black --check .`)
MYPY 7 históricos, NEW = 0   DRIFT 5 passed
ALEMBIC single head 7b2e4c9a15df   git diff --check CLEAN
```

**Regressões, delta 0:**

```text
E3 = 732   E4.1 = 40   E4.2 = 42   E4.3 = 255   E4.4 = 74
E4.5 = 187   E4.7 = 240   E4.8 = 146
```

**E4.6 passa de 252 para 275** (unit 219, integração 55, estático 1),
com os 23 casos novos do corretivo. Rodados 3 vezes, sem intermitência.

---

## 7. Observação B1 da auditoria — HEAD simbólico do bundle

Reproduzida:

```text
git clone <bundle> destino
warning: remote HEAD refers to nonexistent ref, unable to checkout
```

Corrigido neste pacote: o bundle passa a publicar `HEAD` além da ref de
branch, e `git clone <bundle> destino` faz checkout direto no commit
publicado, sem aviso. A verificação está na §9.

---

## 8. Achado honesto sobre `frozen=True, slots=True`

Uma dataclass com as duas opções é **recriada** pelo decorador, e o
`__setattr__` gerado guarda referência à classe anterior. Atribuir um
atributo inexistente levanta `TypeError: super(type, obj)...` em vez de
`AttributeError`. O teste aceita as três exceções possíveis, porque o
que importa é **que a atribuição falhe**, não qual exceção o
interpretador escolhe. Registrado aqui para que ninguém leia a
tolerância do teste como afrouxamento.

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

INPUT_CHANNELS_DECLARED                  = NOT_APPLICABLE
COMMAND_ENVELOPE_DECLARED                = NOT_APPLICABLE
VOICE_CONFIDENCE_AND_CORRECTION_DECLARED = NOT_APPLICABLE
REASON = E4.6.3.1 neither captures nor interprets user commands
```

O adendo de entrada por texto e voz do Master v1.3 não é materialmente
aplicável a um corretivo interno de Retrieval. Nenhum suporte artificial
a voz foi acrescentado. O próximo módulo realmente relacionado a
comandos deverá aplicá-lo integralmente.

---

## 10. Placar das Stop Conditions

```text
RETENTION_OPERATION_AUTHORITY_GAP   = CLOSED_FINAL
ERASURE_AUDIT_PRIMITIVE_GAP         = CLOSED_CANDIDATE_BY_AUTHORIZATION
RETENTION_RETRIEVAL_COMPOSITION_GAP = CLOSED_CANDIDATE

ERASURE_TARGET_OWNERSHIP_GAP        = OPEN
LEGAL_ERASURE_CAUSAL_HISTORY_GAP    = OPEN_CONDITIONAL
ON_EXPIRY_ACTION_UNRESOLVED         = OPEN
DESTRUCTIVE_EXECUTION_AUTHORITY_GAP = OPEN
```

---

## 11. Gate

```text
E4_6_3_1_IMPLEMENTATION        = COMPLETE_CANDIDATE
E4_6_3_STRICT_REDUCTION_DEFECT = CLOSED_CANDIDATE
E4_6_3_1_STATUS                = AWAITING_INDEPENDENT_AUDIT
PATCH_CHAIN                    = 69
E4_9_IMPLEMENTATION            = NOT_STARTED
E4_9_READY                     = FALSE
```

`CLOSED_FINAL` não é declarado aqui — depende de nova auditoria
independente.
