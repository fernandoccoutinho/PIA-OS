# E4_3_4_GOVERNANCE_RESOLUTION_CONTEXT_BINDING

**Corretivo antecedente exigido pelo preflight da E4.8.**

Baseline validada: SHA-256 do bundle e do patch ✓ · `bundle verify` ✓ ·
HEAD `15bd6181edc594dd8bc388b299f74d63d8b88691` ✓ ·
PARENT `c60a2b51…` ✓ · TREE `d45d3c05480e356f1f3e2ab7d8736254089a4b65` ✓ ·
PATCH_ID `54274770…` ✓ · `PATCH_CHAIN = 58` ✓ ·
migration head `7b2e4c9a15df` ✓ · `git status` limpo ✓ ·
suíte **2090 passed / 1 skipped / 0 failed** ✓ ·
`cognitive be407b46…` e `alembic 65a066de…` ✓

---

## 1. Reprodução A–E contra a cadeia 58

| # | Fato registrado |
|---|---|
| **A** | sob policy curinga, `resolução(D1) == resolução(D2)` → **True**; campos de contexto: **NENHUM** |
| **B** | governança recebeu `D1`/`ana` e devolveu resolução sem contexto → `SEARCH_CALLS=1`, `MEMBERSHIPS_LIDAS=1`, `search_executed=True` |
| **C** | E4.7 ultrapassou a fidelidade e **leu o sujeito** (`SUJEITO_LIDO=1x`) |
| **D** | `MemoryRetrievalResult(context=C1, resolution de C2)` e `AccessibilityTransitionResult(...)` — **ambos aceitos** |
| **E** | `GovernanceResolution` construiu **sem nenhum argumento contextual**; `GovernanceDecision` com omissão produziu exatamente o mesmo objeto que contexto vazio explícito |

## 2. Contrato adotado

`GovernanceResolution` e `GovernanceDecision` passam a exigir
`context_domain_ids`, `context_actor_ref` e `context_purpose` — sem
defaults. Canonicalização: tupla ordenada, desduplicada, isolada da
coleção original; textos `str` não vazias ou `None`; `TypeError` para
tipo, `ValueError` para branco. Acesso direto tipado, sem reflexão.

`session_id` **não** entra — justificativa completa no EDR.

Todos os três construtores de `GovernanceManager.resolve()` foram
atualizados: o ramo com policy propaga da `GovernanceDecision`;
`_prohibited_resolution` e `_no_policy_resolution` passaram a receber o
`MemoryContext` original.

## 3. Consumidores

`_verificar_fidelidade_da_resolucao` da E4.6 e da E4.7 comparam as três
dimensões, acumulando motivos, **antes** de memberships/Search e antes
de qualquer leitura do sujeito — em todos os outcomes. Diagnósticos
existentes `PIA-8034` e `PIA-8037`; nenhum código novo.

`MemoryRetrievalResult` e `AccessibilityTransitionResult` recusam
construção direta com resolução de outro contexto, pela **mesma** função
pura que os managers usam.

## 4. Testes

| Arquivo | 58 | 59 | Δ |
|---|---|---|---|
| `test_governance_safety.py` | 68 | **81** | +13 |
| `test_retrieval.py` | 152 | **163** | +11 |
| `test_accessibility.py` | 194 | **204** | +10 |
| `test_governance_integration.py` | 21 | **27** | +6 |
| **Total do corretivo** | — | — | **+40** |

M�dulos: E4.3 passou de 151 para **177**; E4.6 de 183 para **194**;
E4.7 de 226 para **236**.

### Classificação obtida por execução contra a cadeia 58

Com stubs de caracterização (os símbolos e campos novos não existem lá,
e o §18 proíbe contar erro de coleta como prova comportamental):

```text
FAILS_ON_CHAIN_58_BY_BEHAVIOR ......... 33
PASSES_ON_BOTH_SIDES_AS_GUARD ......... 8
```

Os 8 guardas verificam o que já funcionava — comparação exata sem
normalização, comportamento preservado com contexto correto, ausência de
`session_id` no contrato — e agora ficam travados contra regressão.

Além disso, a reprodução A–E do §6 foi feita **separadamente**, com
scripts contra a cadeia 58, antes de qualquer alteração.

### Testes existentes: atualizados, não enfraquecidos

229 testes falharam ao tornar os campos obrigatórios — todos por
`TypeError: missing 3 required positional arguments`, nenhum por
comportamento. A correção foi mecânica e está registrada:

- helpers dos três módulos declaram `_CONTEXTO_VAZIO` **explicitamente**,
  em vez de omitir;
- `GovernanceFalso` passou a **ecoar o contexto recebido**, como o
  manager real faz — sem isso, todo teste com domínios falharia a
  fidelidade nova, e falharia **com razão**, porque o dublê estaria
  devolvendo resolução emitida para outro contexto. Testes que **querem**
  a divergência desligam o eco com `eco_contexto=False`;
- o eco só age sobre uma `GovernanceResolution` real, para não atrapalhar
  os testes que injetam propositalmente outro tipo;
- `_prohibited_resolution` no teste de safety passou a receber
  `MemoryContext()`, com nota.

Nenhum teste foi removido ou afrouxado.

## 5. Resultados

```text
FULL_SUITE = 2137 passed / 1 skipped / 0 failed   (baseline: 2090)
RAW_SUITE  = 1839 passed / 299 skipped / 0 failed

E3 = 598/598   E3.4.2/.1 = 134/134   E4.1 = 40/40   E4.2 = 42/42
E4.4 = 74/74   E4.5 = 187/187                       (delta 0)
E4.3 = 177 (era 151)   E4.6 = 194 (era 183)   E4.7 = 236 (era 226)

GLOBAL_COVERAGE = 99,09%   (baseline 99,08% — não decresceu)
APP_COGNITIVE_COVERAGE = 100%    APP_MEMORY_COVERAGE = 100%
RUFF = PASS
BLACK = PASS   (comando: `black --check .`, black 24.10.0)
MYPY_NEW_ERRORS = 0   STATIC_PROOF = PASS
SCHEMA_ORM_DRIFT = 0   ALEMBIC_SINGLE_HEAD = 7b2e4c9a15df
NEW_MIGRATION = NO   NEW_TABLE/COLUMN = NO   NEW_ERROR_CODE = NO
NEXT_FREE_ERROR_CODE = PIA-8039   RESERVED_BY_E4_3_4 = NO
```

Escopo: 6 arquivos de produção (exatamente os do §19), 4 de teste, 2
docs. `app/cognitive`, `alembic`, `models/`, `repositories/`,
`coverage.ini` e `pytest.ini` **intocados**.

## 6. Limitações honestas

- O vínculo é **verificável**, não **inforjável**: um colaborador que
  construísse a resolução diretamente com contexto certo e outcome
  errado passaria pelas comparações. O que se fecha é a classe de
  defeito real, não um modelo de ameaça de adversário interno.
- **O vazamento multidomínio da E4.8 continua aberto.** Este corretivo
  cria a prova contratual; fechá-lo é trabalho da E4.8.
- A comparação de `domain_ids` é de tupla canônica dos dois lados —
  igualdade de conjunto, não de ordem acidental. Se algum consumidor
  futuro passar domínios não canonicalizados, a comparação falhará
  corretamente, mas a mensagem citará ordens diferentes.

```text
E4_3_4_IMPLEMENTATION = COMPLETE
E4_3_FINAL_STATUS = AWAITING_INDEPENDENT_AUDIT
GOVERNANCE_RESOLUTION_CONTEXT_BINDING_GAP = CORRECTED_AWAITING_AUDIT
PATCH_CHAIN = 59

E4_8_IMPLEMENTATION = NOT_STARTED
E4_8_STATUS = BLOCKED_PENDING_E4_3_4_AUDIT
READY_FOR_E4_8 = FALSE
READY_FOR_E4_9 = FALSE
```
