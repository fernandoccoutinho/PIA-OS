# E4_6_3_RETRIEVAL_COMPOSITION_POINT

**Módulo:** E4.6.3 — corretivo antecedente de composição na recuperação
**Baseline:** `PATCH_CHAIN = 67` · HEAD `f5a380366ffc…` ✓ ·
PARENT `52e3fe819c39…` ✓ · TREE `071173ed7869…` ✓ ·
PATCH_ID `3143e5aed4a9…` ✓ · bundle SHA-256 `af41d93c…a50ee` ✓ ·
migration head `7b2e4c9a15df` ✓ · `git status` limpo ✓

Baseline reproduzida contra PostgreSQL 16 real, com banco recriado:
**2369 passed / 1 skipped / 0 failed**, RAW **2016 / 354**.

Trees registrados na baseline:

```text
backend/app              8af1cab3a78fda4dbdbbcf693b9889d150a99dc2
backend/tests            39bb30899fd4b941d3e74d832b733201dbe1ab73
backend/alembic          65a066dea0925edc55ad88e0c774f56b1944254f
docs/entregas/entrega-4  73f830433f4847c5be64a570f88a0473814bc09d
```

---

## 1. O que esta entrega faz

Fecha, como candidato, a Tensão G do preflight da E4.9:

```text
RETENTION_RETRIEVAL_COMPOSITION_GAP = CLOSED_CANDIDATE
```

Um ponto de composição **tipado, por chamada e estritamente redutor** no
fluxo de `MemoryRetrievalManager`. A decisão, as alternativas rejeitadas
e a fronteira com a E4.9 estão no
`EDR_E4_6_3_RETRIEVAL_COMPOSITION_POINT.md`.

```text
COMPOSITION POINT != RETENTION DECISION
E4.6 IS NOT RETENTION-AWARE
```

Não foram criados: retenção, forgetting, apagamento, `ErasureRecord`,
executor destrutivo, cron, worker, endpoint, operação de governança,
tabela, migração ou código de erro.

---

## 2. Matriz requisito → código → teste

| # | Requisito (§3 e §6 do prompt) | Código | Teste |
|---|---|---|---|
| 1 | `None` preserva comportamento e assinatura | `retrieve(..., candidate_gate=None)` | `test_e463_none_preserves_behaviour_and_pagination`, `..._gate_is_keyword_only_and_optional`, `test_ri463_none_gate_reproduces_the_baseline_result` |
| 2 | gate que aprova todos preserva ordem, conteúdo e paginação | `_coletar` | `test_e463_gate_that_approves_all_preserves_order_content_and_pagination` |
| 3 | rejeição causa backfill até completar a página | laço `while len(admissiveis) <= limit` + `continue` | `test_e463_rejected_candidates_are_backfilled_until_the_page_is_full`, `test_ri463_backfill_crosses_real_search_batches` |
| 4 | rejeitar todos → vazio, `has_more=False` | idem | `test_e463_gate_that_rejects_all_returns_empty_and_has_more_false` |
| 5 | `offset` aplicado **depois** do gate | ordem em `_coletar` | `test_e463_offset_is_applied_after_the_gate`, `test_ri463_offset_and_has_more_count_only_approved_candidates` |
| 6 | `has_more` conta só aprovados | `has_more = len(admissiveis) > limit` | `test_e463_has_more_counts_only_approved_candidates` |
| 7 | gate nunca chamado sob recusa de governança | `return` antecipado em `retrieve` | `test_e463_gate_is_never_called_under_governance_denial` (3 outcomes), `test_ri463_gate_never_sees_candidates_denied_by_governance` |
| 8 | gate não vê candidato fora do escopo base | gate após `_admissivel` | `test_e463_gate_never_sees_candidates_outside_the_base_scope`, `test_ri463_...` |
| 9 | hit malformado falha **antes** do gate | `_validar_hit` antes | `test_e463_malformed_hit_fails_before_the_gate` |
| 10 | duplicata falha antes do gate, mesmo se seria rejeitada | `vistos` antes | `test_e463_duplicate_fails_before_the_gate_even_if_it_would_reject_it` |
| 11 | retorno não-`bool` falha tipadamente | `_gate_aprova`, `type(...) is not bool` | `test_e463_non_bool_gate_result_fails_typed` (9 casos), `test_ri463_...` (4 casos), controle positivo `..._exact_bool_is_accepted` |
| 12 | exceção do gate falha tipadamente e preserva causa | `raise ... from exc` | `test_e463_gate_exception_fails_typed_and_preserves_cause`, `..._not_converted_into_an_empty_view`, `test_ri463_...` |
| 13 | gates distintos em chamadas sucessivas não compartilham estado | parâmetro, nunca atributo | `test_e463_successive_calls_with_different_gates_do_not_share_state`, `..._gate_is_not_stored_on_the_manager`, `test_ri463_...` |
| 14 | gate não acrescenta nem reordena | forma do `Protocol` | `test_e463_gate_cannot_add_or_reorder_because_of_the_signature`, `..._result_is_always_a_subsequence_of_the_ungated_result` (6 cenários) |
| 15 | sem regressão em isolamento, governança e chamadas à Search | — | `test_e463_search_call_count_is_unchanged...`, `..._does_not_duplicate_search_or_governance_calls`, `test_ri463_isolation_e48_is_unaffected...` |
| 16 | conformidade estática do `Protocol` e cobertura | `tests/static/test_retrieval_gate_port.py` | prova por mypy + `test_e463_real_gate_satisfies_the_protocol_at_runtime`, `..._port_is_exported_by_the_public_ports_package` |
| — | neutralidade semântica (§5) | — | `test_e463_gate_protocol_carries_no_retention_semantics` (AST), `..._manager_does_not_import_retention_or_erasure` |
| — | rejeição é transitória e não escreve | — | `test_e463_rejection_is_transitory_and_writes_nothing`, `test_ri463_rejection_writes_nothing_and_is_transitory` (espião de escritas = 0 + estado persistido conferido) |

---

## 3. Arquivos alterados

Produção — três arquivos, e só onde indispensável:

```text
backend/app/memory/ports/retrieval.py               +69  / -0
backend/app/memory/ports/__init__.py                 +6  / -1
backend/app/memory/services/retrieval_manager.py    +89  / -4
```

Testes:

```text
backend/tests/unit/memory/test_retrieval.py                    +452 / -1
backend/tests/integration/memory/test_retrieval_integration.py +380 / -0
backend/tests/static/test_retrieval_gate_port.py               (arquivo novo)
```

Documentação:

```text
docs/entregas/entrega-4/EDR_E4_6_3_RETRIEVAL_COMPOSITION_POINT.md
docs/entregas/entrega-4/E4_6_3_RETRIEVAL_COMPOSITION_POINT.md
```

```text
MIGRATION_DELTA = 0     SCHEMA_DELTA = 0
GOVERNANCE_DELTA = 0    E4_8_DELTA = 0
NEW_ERROR_CODE = NONE   (NEXT_FREE_ERROR_CODE = PIA-8041, inalterado)
```

`backend/alembic` permanece byte a byte idêntico.

---

## 4. Gates medidos

Coletados, não copiados:

```text
FULL_SUITE       2423 passed / 1 skipped / 0 failed   (baseline 2369)
RAW_SUITE        2056 passed / 368 skipped / 0 failed (baseline 2016/354)
GLOBAL_COVERAGE  99,14%                               (baseline 99,13%)
APP_MEMORY 100%   APP_COGNITIVE 100%
app/memory/ports/retrieval.py            26 statements, 0 missing, 100%
app/memory/services/retrieval_manager.py 179 statements, 0 missing, 100%
RUFF PASS   BLACK PASS (`black --check .`, 24.10.0)
MYPY 7 erros históricos em 3 arquivos, NEW = 0
SCHEMA_ORM_DRIFT 0   ALEMBIC single head 7b2e4c9a15df
git diff --check CLEAN
```

**Regressões por módulo, delta 0:**

```text
E3 = 732   E4.1 = 40   E4.2 = 42   E4.3 = 255   E4.4 = 74
E4.5 = 187   E4.7 = 240   E4.8 = 146
```

**E4.6 passa de 198 para 252**, com estes seletores reais:

```text
tests/unit/memory/test_retrieval.py                        202  (era 163)
tests/integration/memory/test_retrieval_integration.py      49  (era 35)
tests/static/test_retrieval_gate_port.py                     1  (novo)
```

Testes novos: **53** — 39 unitários (`-k e463`) e 14 de integração
(`-k ri463`), mais 1 estático. `39 + 14 = 53`; com o estático, `54`
casos novos e `198 + 54 = 252`. Executados 3 vezes seguidas, sem
intermitência.

**Nota sobre o RAW.** `2016/354` → `2056/368`: +40 executados e +14
pulados. Os 14 pulados são os de integração da E4.6.3, que exigem
PostgreSQL; os +40 são os 39 unitários mais o estático. Medido, não
derivado por subtração.

---

## 5. Limitações e achados honestos

**Bypass por chamada direta.** Quem chamar `retrieve()` sem gate obtém a
vista base. É correto nesta etapa e está justificado no EDR §8 — fechar
o caminho canônico de forgetting é obrigação de composição da E4.9.

**Três correções minhas durante a implementação**, registradas porque
mudam a leitura dos números:

1. Cinco testes de integração assumiam que a ordem canônica era a ordem
   de criação. **Não é.** Os objetos de teste nascem na mesma transação,
   então `created_at` é idêntico — o `now()` do PostgreSQL é o instante
   de **início da transação** — e o desempate canônico cai em `id ASC`,
   UUID aleatório. Passariam por sorte. A ordem passou a ser derivada de
   uma chamada sem gate (`_ordem_canonica`), com o motivo documentado no
   helper. Mesma lição da E3.4.2.1.
2. A prova estática falhou com atribuição direta
   `CognitiveObject → CognitiveObjectView`, pelo motivo já registrado na
   E4.7.1: os modelos da E3 declaram `Mapped[...]` e o mypy compara a
   anotação declarada. Saída sem `Any`, `cast` ou `type: ignore`:
   narrowing por `isinstance`, que tipa o objeto para o mypy.
3. A prova estática do gate estava em
   `tests/static/test_port_assignment.py`, e isso levou o seletor da
   **E4.7 de 240 para 241** — um módulo congelado mudando de número sem
   ter mudado de comportamento. Movida para arquivo próprio; E4.7 voltou
   a 240.

```text
FROZEN MODULE COUNT != NEIGHBOURING FILE
```

**Custo por candidato.** O gate é consultado uma vez por candidato
admissível, dentro do laço de coleta. Um gate caro multiplica o custo —
troca conhecida, responsabilidade de quem o fornece.

---

## 6. Compatibilidade SOPHIA / PIA-OS

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

Consequência prospectiva, sem inflar: a Biblioteca Cognitiva ainda
**não** distingue *não recuperado* de *esquecido*, porque nada de
retenção existe. Este corretivo apenas torna a distinção construível
mais tarde, sem duplicar Search nem mentir na paginação.

Schedule, multi-IA, frontend, conectores e operações remotas:
`NOT_APPLICABLE`.

---

## 7. Placar das Stop Conditions

```text
RETENTION_OPERATION_AUTHORITY_GAP   = CLOSED_FINAL
ERASURE_AUDIT_PRIMITIVE_GAP         = CLOSED_CANDIDATE_BY_AUTHORIZATION
RETENTION_RETRIEVAL_COMPOSITION_GAP = CLOSED_CANDIDATE   ← esta entrega

ERASURE_TARGET_OWNERSHIP_GAP        = OPEN
LEGAL_ERASURE_CAUSAL_HISTORY_GAP    = OPEN_CONDITIONAL
ON_EXPIRY_ACTION_UNRESOLVED         = OPEN
DESTRUCTIVE_EXECUTION_AUTHORITY_GAP = OPEN
```

Três de sete encaminhadas, quatro abertas.

---

## 8. Gate

```text
E4_6_3_IMPLEMENTATION = COMPLETE_CANDIDATE
E4_6_3_STATUS = AWAITING_INDEPENDENT_AUDIT
PATCH_CHAIN = 68
E4_9_IMPLEMENTATION = NOT_STARTED
E4_9_READY = FALSE
READY_FOR_E4_10 = FALSE
```

`CLOSED_FINAL` não é declarado aqui — cabe à auditoria independente.
