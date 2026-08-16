# E4_7_3 — No-Op Boundary & Self-Loop Exclusion

**Corretivo mínimo da candidata E4.7.2 (cadeia 57).**

Baseline validada: SHA-256 dos dois artefatos ✓ · `git bundle verify` ✓ ·
HEAD `c60a2b51c01f8ad0621d151e597098cd08150647` ✓ ·
PARENT `bbc33d52…` ✓ · TREE `4ed03e0ee03b6be217198a26959ae2af6b45e991` ✓ ·
PATCH_ID `166a3cc9…` ✓ · `PATCH_CHAIN = 57` ✓ ·
migration head `7b2e4c9a15df` ✓ · `git status` limpo ✓ ·
suíte **2069 passed / 1 skipped / 0 failed** ✓ ·
`black --check .` PASS ✓ ·
`cognitive be407b46…` e `alembic 65a066de…` ✓

---

## 1. Reprodução, antes de corrigir

| # | Reprodução contra a cadeia 57 |
|---|---|
| **R** | `AccessibilityRule(active → active)` — **aceita** |
| **S** | decisão self-loop aceita nos **três** outcomes (`ADMISSIBLE`, `INADMISSIBLE`, `NOT_APPLICABLE`) |
| **T** | resultado com `state_changed=True` sobre `active → active` — **aceito**, sem que nada mude |
| **U** | recusa local self-loop — **aceita**, embora same-state devesse terminar como no-op |

## 2. Causa-raiz

```text
ONE EXACT EDGE was enforced only as cardinality 1 × 1
CARDINALITY 1 × 1 DOES NOT EXCLUDE A SELF-LOOP
```

A E4.7.2 tornou os desfechos exaustivos, mas não impôs a precondição
comum a **todo** desfecho com decisão:

```text
POLICY DECISION REQUIRES source_state != target_state
```

Sem ela restava um quinto estado semanticamente impossível — o laço
sobre si mesmo, que o manager nunca chega a avaliar porque o no-op é
resolvido sob lock antes da policy.

```text
SAME STATE REQUEST = NO-OP
NO-OP BYPASSES ACCESSIBILITY POLICY
SELF-LOOP DECISION != EXECUTED TRANSITION
STATE_CHANGED REQUIRES SOURCE_STATE != TARGET_STATE
```

## 3. Correção

**`AccessibilityRule`** — depois de canonicalizar as coleções e
confirmar cardinalidade unitária, recusa quando o único token de origem
é igual ao de destino. Uma regra de policy descreve mudança **real**;
uma regra self-loop nunca seria avaliada no caminho canônico, e existir
seria prometer autoridade que nada exerce.

**`AccessibilityDecision`** — recusa `source_state == target_state` para
**qualquer** outcome, inclusive `NOT_APPLICABLE`: mesmo ele afirmaria
que a policy foi consultada sobre uma transição que não existe. O
invariante vive no value object, então vale no construtor direto, em
`dataclasses.replace`, na desserialização de regras publicadas e em
qualquer chamador futuro.

**`AccessibilityTransitionResult`** — **nenhuma guarda própria**. O
invariante da decisão já torna T e U inconstruíveis, e uma segunda
implementação da mesma regra divergiria com o tempo — a lição que a
E4.5.1 pagou ao encontrar duas verificações da mesma coisa. Há teste
provando a não-construtibilidade pelo caminho do resultado.

O único desfecho same-state legítimo permanece intacto:

```text
decision = None
observed_state == requested_target_state
state_changed = FALSE
no_change = TRUE
causal_event_id = None
```

## 4. Compatibilidade de policies publicadas (§7)

Busca executada antes de implementar:

```text
regras self-loop em código/fixtures/seeds ... nenhuma
policies no banco de teste ................. 0 linhas
policies com self-loop persistido .......... nenhuma
```

`STOP CONDITION = PUBLISHED_POLICY_COMPATIBILITY` **não** foi acionada.
Nenhuma versão publicada foi reescrita ou apagada; policies com arestas
reais permanecem byte a byte inalteradas, e não houve migração.

Um payload histórico com self-loop, se existisse, é **recusado na
leitura** — nunca ignorado em silêncio. Silenciar produziria uma policy
que parece restringir e não restringe, o pior desfecho possível, e a
mesma razão pela qual a desserialização da E4.3 recusa token
desconhecido.

## 5. Testes

| Arquivo | Cadeia 57 | Cadeia 58 | Δ |
|---|---|---|---|
| `tests/unit/memory/test_accessibility.py` | 175 | **194** | +19 |
| `tests/integration/memory/test_accessibility_integration.py` | 29 | **31** | +2 |
| `tests/static/test_port_assignment.py` | 1 | **1** | 0 |
| **Total E4.7** | **205** | **226** | **+21** |

Classificação **obtida por execução** contra a cadeia 57:

```text
FALHAM POR COMPORTAMENTO ............ 12
PASSAM NOS DOIS LADOS (guardas) ..... 9
FALHAS POR SÍMBOLO NOVO ............. 0
```

Os 9 guardas verificam o que já funcionava — arestas reais válidas,
no-op canônico sem policy/evidência/writer, serialização determinística,
no-op sem escrita no banco — e agora ficam travados contra regressão.

**Nenhum teste existente precisou ser ajustado:** nenhum dependia de
self-loop, o que é evidência de que a lacuna era realmente residual.

## 6. Resultados

```text
FULL_SUITE = 2090 passed / 1 skipped / 0 failed   (candidata: 2069)
RAW_SUITE  = 1798 passed / 293 skipped / 0 failed

E3 = 598/598   E3.4.2/.1 = 134/134   E4.1 = 40/40   E4.2 = 42/42
E4.3+.3 = 151/151   E4.4 = 74/74   E4.5 = 187/187   E4.6 = 183/183
(todos delta 0)
E4.7 + .1 + .2 + .3 = 226 passed

GLOBAL_COVERAGE = 99,08%   (não reduziu)
APP_COGNITIVE_COVERAGE = 100%    APP_MEMORY_COVERAGE = 100%
RUFF = PASS
BLACK = PASS   (comando: `black --check .`, black 24.10.0)
MYPY_NEW_ERRORS = 0   STATIC_PROOF = PASS
SCHEMA_ORM_DRIFT = 0   ALEMBIC_SINGLE_HEAD = 7b2e4c9a15df

MANAGER MODIFIED = NO   PORT MODIFIED = NO   E3 MODIFIED = NO
NEW MIGRATION/TABLE/COLUMN = NO   NEW ERROR CODE = NO
```

Escopo de produção: **um único arquivo**,
`backend/app/memory/schemas/accessibility.py`. O manager, as portas e o
repositório não precisaram mudar — o invariante pertence ao value
object, e é de lá que ele alcança todos os caminhos.

```text
E4_7_3_IMPLEMENTATION = COMPLETE
E4_7_FINAL_STATUS     = AWAITING_INDEPENDENT_AUDIT
PATCH_CHAIN = 58
E4_8_IMPLEMENTATION = NOT_STARTED
READY_FOR_E4_8 = FALSE
```
