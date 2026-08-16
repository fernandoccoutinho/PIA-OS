# E4_7_ACCESSIBILITY_POLICY

**Módulo:** E4.7 — Accessibility Policy
**Baseline:** `PATCH_CHAIN = 54` · HEAD `9002327beeba…` ✓ ·
PARENT `3c3b184b7d81…` ✓ · TREE `10d5678fd40b…` ✓ ·
PATCH_ID `1d848851c5af…` ✓ · bundle SHA-256 `d3a91879…721a` ✓ ·
patch SHA-256 `1f4182d2…3407` ✓ · migration head `4ca61776b982` ✓ ·
`git status` limpo ✓ · suíte **1864 passed / 1 skipped / 0 failed** ✓
**Patch:** `e4-7-accessibility-policy.patch` (55º)

Trees protegidos registrados na baseline:
`cognitive be407b46f679a009e0f7f7e9f01fb784f08dea54`,
`alembic f01a1f812eb11695b9daeb6b1707e6477e9330fa`.

---

## 1. Preflight — Tensões A–E

### A. Autoridade explícita (revalidada, não reaberta)

Confirmado no código da baseline 54: `ACCESSIBILITY_TRANSITION` existe
com token `"accessibility_transition"`; `TRANSFORM` permanece distinto;
`EMPTY_OPERATIONS_SCOPE_V1` tem literalmente as sete operações
históricas; policy antiga com `operations=()` **não** alcança a nova
operação; opt-in explícito produz `ADMISSIBLE`/`INADMISSIBLE`;
`DENY_OVERRIDES` intacto; versões publicadas não foram reescritas.

```text
GOVERNANCE_OPERATION_GAP = CORRECTED_BY_E4_3_3
AUTHORITY STILL REQUIRES EXPLICIT POLICY OPT_IN
PERMISSION != EXECUTION
```

### B. Evidência causal para `CAUSALLY_EXTINCT`

Fechada por porta estrutural: `CausalEvidencePort.get_event()` +
`get_by_subject()`, e comparação da identidade da história. O evento é
**verificado**, nunca criado, alterado ou inferido.

**Alcance declarado com honestidade:** a garantia é **local ao caminho
da E4.7**. O `AccessibilityManager` da E3 continua exigindo apenas
`reason` não-vazio de qualquer outro chamador — **não** afirmo que o
invariante global da E3 foi retroativamente fechado. Fechá-lo
globalmente exigiria corretivo próprio da E3.

`reason` continua obrigatório: a E4.7 **complementa** a exigência da E3,
não a substitui.

### C. Fronteira tipada E3/E4

Três portas, satisfeitas estruturalmente pelos objetos reais —
verificado por `isinstance`, não presumido:

| Porta | Satisfeita por |
|---|---|
| `CognitiveSubjectPort` | `ObjectRepository` (E3.1) |
| `AccessibilityTransitionPort` | `AccessibilityManager` (E3.6) |
| `CausalEvidencePort` | `CausalHistoryRepository` (E3.9) |
| `CausalEventView` / `CausalHistoryView` | `CausalHistoryEvent` / `CausalHistory` |

`SubjectT` é `TypeVar` sem limite: o `CognitiveObject` atravessa a E4.7
**opaco**, sem nunca ter um campo lido. `AccessibilityState` é `StrEnum`,
então tokens viajam como `str` com satisfação covariante e **tipada**.

```text
TOKEN BRIDGE != DOMAIN ENUM OWNERSHIP
E3 REMAINS SOURCE OF TRUTH FOR ACCESSIBILITY STATE
```

Sem `Any`, `cast`, `type: ignore`, reflexão, `getattr`, `hasattr`,
`vars`, `__dict__`, `importlib`, registry, `sys.modules`, SQL paralelo
ou adapter novo em `app.cognitive` — verificado por inspeção AST do
código executável.

### D. Atomicidade — a tensão central, fechada e provada

O problema: se a policy for avaliada sobre um estado lido **sem** lock,
outra transação pode mudá-lo antes da escrita; o manager da E3
recarregaria o novo valor e escreveria o destino sem reavaliar a regra.

```text
PRE-LOCK SOURCE STATE != AUTHORIZED WRITE PRECONDITION
POLICY(ACTIVE → TARGET) != POLICY(ANY CURRENT STATE → TARGET)
LAST-WRITE-WINS != VALID TRANSITION
```

A solução usa **apenas contratos sancionados**:

```text
get_by_id(include_deleted=True)   resolve o sujeito
refresh_for_update(...)           SELECT ... FOR UPDATE — LOCK
get_state(...)                    estado de origem, JÁ sob lock
avaliar policy                    sobre esse estado
transition(...)                   mesma Session, lock ainda válido
```

`refresh_for_update()` mantém a linha bloqueada **até commit/rollback**
da `UnitOfWork` do chamador. O `refresh_for_update()` interno do manager
da E3 reencontra a linha já bloqueada pela própria transação, e o estado
não pôde mudar entre a avaliação e a escrita.

Provado antes de escrever código, e depois por teste de integração
(`ai17`): duas transações concorrentes pedindo destinos diferentes a
partir de `active` — exatamente uma escreve, e a outra observa o estado
**já commitado**, resultando em `NOT_APPLICABLE`. Nenhuma escrita
autorizada sobre a transição errada, nenhum last-write-wins.

**Nenhuma modificação na E3.**

### E. No-op, soft delete e ausência

Governança é resolvida **antes** de ler o sujeito, inclusive para
same-state: consultar o patrimônio sob recusa já revelaria se o objeto
existe e em que estado está.

Sob lock, `target == current` é `NO_CHANGE` — e a policy **nem é
consultada**:

```text
NO_CHANGE != POLICY ADMISSION
NO_CHANGE != POLICY REFUSAL
```

Não há escrita, evento causal, decisão ou história. Um objeto já
`CAUSALLY_EXTINCT` que receba o mesmo alvo não fabrica nova evidência.

Soft delete não é inexistência e não é revertido; `deleted_at` nunca é
tocado. Objeto realmente ausente tem diagnóstico próprio (`PIA-8038`),
distinto de qualquer desfecho de policy.

---

## 2. Modelo de autoridade — e por que não duplica a Governança

A E4.7 **não decide autoridade**. Ela pergunta à E4.3, pelo caminho
canônico `resolve()`, e só então aplica a política de estado.

```text
GOVERNANCE DECIDES AUTHORITY
ACCESSIBILITY POLICY APPLIES UNDER GOVERNANCE AUTHORITY
ACCESSIBILITY POLICY DOES NOT INVENT AUTHORITY
```

A regra de acessibilidade é deliberadamente **mínima**: `rule_id`,
`effect`, `source_states`, `target_states`. **Ator, propósito e domínio
não estão nela** — pertencem ao `MemoryContext` (E4.2) e à Governança
(E4.3), que já os avalia. Copiá-los para cá duplicaria o motor da E4.3 e
criaria duas respostas possíveis para a mesma pergunta.

**Nenhuma dimensão é opcional.** Diferente da E4.3, onde conjunto vazio
é curinga, aqui `source_states` e `target_states` são obrigatórios e não
vazios — a E4.3.3 mostrou o custo de curinga quando o vocabulário cresce,
e uma regra de transição que não diz *de onde* e *para onde* não é uma
regra de transição.

Precedência idêntica à da E4.3, pelo mesmo motivo:

```text
DENY_OVERRIDES
NO_MATCH = NOT_APPLICABLE
NOT_APPLICABLE DOES NOT AUTHORIZE
```

---

## 3. Persistência

`AccessibilityPolicy`: `policy_key` (identidade lógica) + `version`
(identidade de registro), `governance_policy_key`, `rules` em JSONB,
janela `[effective_from, effective_until)`.

`governance_policy_key` é **texto, sem FK**: a autoridade é resolvida
pela versão vigente, e uma FK congelaria a autoridade numa versão que
pode ter sido sucedida.

Imutabilidade em três camadas: `UNIQUE(policy_key, version)`, override de
`update`/`delete`/`delete_by_id`, e eventos de mapper — a terceira porque
a E4.3.1 reproduziu o defeito **contornando** o repositório.

```text
ACCESSIBILITY_POLICY_PORTABLE = FALSE
ACCESSIBILITY_POLICY_SYNC = NONE
NENHUMA FK/COID/CLID/LINHAGEM/PROVENIÊNCIA/HISTÓRIA
```

Migração `7b2e4c9a15df` sobre `4ca61776b982`, single head, upgrade e
downgrade reais, com guarda `CONDITIONALLY_REVERSIBLE` embutida no
próprio `downgrade()` — como em E3.9, E4.1 e E4.3.

Nenhuma coluna nova em `CognitiveObject`: o estado continua sendo da E3,
e a E4.7 não cria um segundo lugar onde ele viva.

---

## 4. Códigos de erro

| Código | Uso | Categoria |
|---|---|---|
| `PIA-8035` | versão de policy já existente | `VALIDATION` |
| `PIA-8036` | versão publicada imutável | `VALIDATION` |
| `PIA-8037` | violação de contrato da transição | `SYSTEM` |
| `PIA-8038` | sujeito inexistente | `VALIDATION` |

Todos com chamador real e teste. Negativa normal de policy **não** é
exceção — é resultado explicável. Próximo livre: `PIA-8039`.

---

## 5. Testes

| Arquivo | Testes |
|---|---|
| `tests/unit/memory/test_accessibility.py` | **100** |
| `tests/integration/memory/test_accessibility_integration.py` | **24** |
| **Total E4.7** | **124** |

### Classificação honesta

A E4.7 não existia na cadeia 54. Executei os dois arquivos contra ela: a
coleta **falha inteira**, com `ModuleNotFoundError`.

```text
FALHAM POR DEFEITO CORRIGIDO ......................... 0
FALHAM APENAS PORQUE O MÓDULO NÃO EXISTIA ............ 124
```

Nenhum teste é apresentado como provador de defeito, porque nenhum o é.

Por **inspeção** — não por execução, já que a coleta não chega a rodar —
são guardas de regressão: `ai19` (drift), `ai20` (migration head),
`ai21` (ausência de coluna nova), `ap49` (G17/MD6), `ap52` (vocabulário
igual ao enum da E3) e `ap53` (ordens de import). Registro a diferença
entre inspeção e execução em vez de apresentá-las como equivalentes.

### Quatro defeitos meus, corrigidos

**(a)** O no-op consultava a policy antes de detectar `target ==
current`, produzindo `NOT_APPLICABLE` onde o §8.5 exige `NO_CHANGE` sem
fabricar admissão. Reestruturei: o no-op é detectado sob lock e **antes**
da avaliação, e o resultado passou a ter `no_change` como campo próprio,
mantendo os três desfechos distintos.

**(b)** Usei `getattr`/`hasattr` em validação defensiva — exatamente o
que a E4.6.2 acabou de proibir. Substituí por acesso direto e
`isinstance(..., Iterable)`.

**(c)** Li atributos ORM **fora** da `UnitOfWork` num teste de
integração (`DetachedInstanceError`) — mesma lição da E4.5.

**(d)** Um teste passava a string direto para o helper `_regra`, que a
embrulhava em `frozenset(...)` antes de o value object ser chamado; o
teste provaria outra coisa. Passou a construir a regra diretamente.

### Guardas atualizados, não enfraquecidos

Quatro guardas de módulos anteriores afirmavam migration head
`4ca61776b982` e o conjunto exato de tabelas de memória. A E4.7 cria
tabela e migração **autorizadas pelo §14**, então eles foram atualizados
com nota explícita. Continuam exigindo conjunto **exato** e head
**único** — o que protegem é a ausência de branching e de tabela não
declarada, não a imobilidade do schema entre módulos.

---

## 6. `SOPHIA_UX_COMPATIBILITY`

```text
USER_AUTHORITY_PRESERVED
SCHEDULE_MODE = NOT_APPLICABLE
AUTOMATION_SCOPE = ACCESSIBILITY_POLICY_AND_SANCTIONED_TRANSITION_ONLY
PERSISTENCE_BEHAVIOR = LOCAL_VERSIONED_POLICY_PLUS_EXPLICIT_STATE_TRANSITION
PROVIDER_NEUTRALITY_PRESERVED
PERSONALIZATION = NOT_APPLICABLE
CONCURRENT_WORKSPACES = NOT_APPLICABLE
BACKGROUND_EXECUTION = NOT_APPLICABLE
RESOURCE_LIMITS = NOT_APPLICABLE
USER_DEFINED_AI_ROLES = NOT_APPLICABLE
PIA_SUGGESTED_AI_SEQUENCE = NOT_APPLICABLE
SEPARATE_AI_RESULTS = NOT_APPLICABLE
PIA_INTEGRATION_PRESERVES_DIVERGENCE = NOT_APPLICABLE
USER_POST_RESULT_TEXT_OR_VOICE_COMMAND = NOT_APPLICABLE
EXPLICIT_CONFIRMATION_BEFORE_DERIVED_PERSISTENCE = PRESERVED
FROZEN_MODULES_UNCHANGED
```

Nenhum front-end, tela, Scheduler, orquestração multi-IA, conector ou
escrita em diretório local.

---

## 7. Relação com a E4.6

```text
RETRIEVAL READS STATE
ACCESSIBILITY POLICY GOVERNS TRANSITION
READING STATE != AUTHORIZING STATE CHANGE
```

A E4.6 **não foi modificada** — apenas o guarda de migration head e o de
tabelas, pelo motivo declarado acima. Paginação, Search, filtros e
resultados permanecem intocados.

---

## 8. Resultados

```text
FULL_SUITE = 1988 passed / 1 skipped / 0 failed   (baseline: 1864)
RAW_SUITE  = 1703 passed / 286 skipped / 0 failed

E3 = 598/598   E3.4.2/.1 = 134/134   E4.1 = 40/40   E4.2 = 42/42
E4.3+.3 = 151/151   E4.4 = 74/74   E4.5 = 187/187   E4.6 = 183/183
(todos delta 0)
E4.7 = 124 passed

GLOBAL_COVERAGE = 99,06%   (baseline 98,98% — não decresceu)
APP_COGNITIVE_COVERAGE = 100%    APP_MEMORY_COVERAGE = 100%
RUFF = PASS   BLACK = PASS   MYPY_NEW_ERRORS = 0
git diff --check = limpo   SCHEMA_ORM_DRIFT = 0
MIGRATION_HEAD = 7b2e4c9a15df (single, sobre 4ca61776b982)
PostgreSQL 16.14 real
```

Trees protegidos byte a byte:
`backend/app/cognitive = be407b46f679a009e0f7f7e9f01fb784f08dea54`,
`backend/alembic` mudou apenas pela migração nova e autorizada.

---

## 9. Stop Conditions

```text
STOP_CONDITIONS = NONE
```

Nenhuma das 20 do §10 ocorreu. Em particular: E3 intocada; E4.3.3
presente e não reparada; curinga não alcança a nova operação; nenhum
import de `app.cognitive` em produção E4; composição tipada demonstrada;
estado de origem avaliado **sob** o lock que protege a escrita; evidência
causal verificada; nada de causalidade, proveniência ou história criada;
E4.6 não alterada em substância; nenhuma DSL; nenhum score; policy local
e fora do Sync; E4.8/E4.9/front-end não iniciados; single head; sem
redução de cobertura; nenhuma autorização derivada de ator presente;
nenhuma transição disparada por Search, Retrieval ou background.

---

## 10. Gate

```text
E4_7_IMPLEMENTATION = COMPLETE
E4_7_FINAL_STATUS   = AWAITING_INDEPENDENT_AUDIT
PATCH_CHAIN = 55

E4_8_IMPLEMENTATION = NOT_STARTED
READY_FOR_E4_8      = FALSE
```

O implementador não declara `PASS FINAL`. E4.8 não é iniciada.
