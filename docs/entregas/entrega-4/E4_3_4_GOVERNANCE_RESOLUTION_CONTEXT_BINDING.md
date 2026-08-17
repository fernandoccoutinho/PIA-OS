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

Módulos: E4.3 passou de 151 para **177**; E4.6 de 183 para **194**;
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

---

## 7. Corretivo E4.3.4.1 — Consumer Integration Proof

**Patch 60.** A auditoria independente aprovou o **código de produção**
da E4.3.4, mas não fechou o gate: duas provas PostgreSQL exigidas pelo
próprio prompt canônico não haviam sido implementadas.

### O que faltava, e é falha minha

O §15 do prompt da E4.3.4 exigia, com managers reais:

```text
8.  wrapper adultera somente o contexto da resolucao APOS a chamada real,
    e a E4.6 recusa antes da Search
10. o mesmo para a E4.7, antes de ler ou bloquear o sujeito
```

Reproduzido antes de alterar qualquer coisa:

```text
test_governance_integration.py     9 ocorrencias de prova E4.3.4
test_retrieval_integration.py      0
test_accessibility_integration.py  0
```

Provei o vinculo com dubles unitarios e com o `GovernanceManager` real
**no modulo de governanca**, e tratei isso como suficiente. Nao era:
duble de governanca nao prova que o consumidor real recusa antes de
tocar patrimonio.

### O que este patch acrescenta

Um wrapper por consumidor que **chama o `GovernanceManager` real**,
guarda a resolucao devolvida e troca exatamente uma dimensao contextual
por `dataclasses.replace()`. Nada de outcome, policy, operacao ou versao
fabricados — o cenario que importa e uma autorizacao legitima emitida
sob outra pergunta.

**E4.6** — tres casos parametrizados (`context_domain_ids`,
`context_actor_ref`, `context_purpose`):

```text
exception = RetrievalContractViolationError   code = PIA-8034
governanca real consultada = 1x, outcome ADMISSIBLE, policy_key correta
Search calls = 0      membership reads = 0      database writes = 0
```

**E4.7** — os mesmos tres casos, com espioes em cinco pontos:

```text
exception = AccessibilityTransitionContractViolationError   code = PIA-8037
get_by_id = 0   refresh_for_update = 0   get_state = 0
AccessibilityPolicy.effective_version_at = 0   get_event = 0
database writes = 0   estado e censo do sujeito inalterados
```

Cada arquivo ganhou tambem um **controle positivo**: o mesmo wrapper em
modo fiel, provando que ele nao invalida a composicao por si so — a E4.6
recupera normalmente e a E4.7 transiciona de fato.

### Classificacao contra a cadeia 59

```text
PASSES_ON_BOTH_SIDES_AS_GUARD ......... 8
FAILS_ON_CHAIN_59_BY_BEHAVIOR ......... 0
```

Os 8 passam nos dois lados, e isso e o resultado **esperado**: a
producao da E4.3.4 ja estava correta. O objetivo era fechar evidencia
faltante, nao fabricar um defeito.

### Divergencia registrada — encoding corrompido na cadeia 59

Ao editar este documento, descobri que a versao publicada no patch 59
continha **um byte invalido em UTF-8**: `M\xb3dulos` onde deveria estar
`Módulos`. A corrupcao entrou pelo heredoc com que escrevi o arquivo, e
passou despercebida porque nenhum gate valida encoding de documentacao.

Varri `docs/**/*.md` e `backend/**/*.py`: era o **unico** arquivo
afetado. Corrigido neste patch, que e o caminho legitimo — o patch 59
permanece imutavel.

### Resultados

```text
FULL_SUITE = 2145 passed / 1 skipped / 0 failed   (candidata: 2137)
RAW_SUITE  = 1839 passed / 307 skipped / 0 failed
E4.6 = 198 (era 194)   E4.7 = 240 (era 236)   demais delta 0

PRODUCTION_DIFF = 0
GLOBAL_COVERAGE = 99,09%   (inalterado)
APP_MEMORY = 100%   APP_COGNITIVE = 100%
RUFF = PASS   BLACK = PASS (`black --check .`, black 24.10.0)
MYPY_NEW_ERRORS = 0   ALEMBIC_SINGLE_HEAD = 7b2e4c9a15df
NEW_ERROR_CODE = NO   NEW_MIGRATION = NO
```

Escopo: dois arquivos de teste e este documento. Nenhum arquivo de
producao foi tocado — confirmado por `git status --porcelain
backend/app/` vazio e por `app/memory` tree identico ao da cadeia 59.

```text
E4_3_4_PRODUCTION = UNCHANGED
E4_3_4_1_INTEGRATION_PROOF = COMPLETE
PATCH_CHAIN = 60
```
