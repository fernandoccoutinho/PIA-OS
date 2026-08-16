# E4_7_2 — Locked Subject Identity & Result Coherence

**Corretivo da candidata E4.7.1 (cadeia 56).**
Baseline validada: SHA-256 dos dois artefatos ✓ · `bundle verify` ✓ ·
HEAD `bbc33d5253203983356bd9ba250b33e756e73e8a` ✓ ·
PARENT `74c77475…` ✓ · TREE `ff048aef94a8520236e33b1552e8b95cc13de1c0` ✓ ·
PATCH_ID `6cc095a6…` ✓ · `PATCH_CHAIN = 56` ✓ ·
migration head `7b2e4c9a15df` ✓ · `git status` limpo ✓ ·
suíte **2027 passed / 1 skipped / 0 failed** ✓ ·
`cognitive be407b46…` e `alembic 65a066de…` ✓

---

## 1. Reprodução dos defeitos, antes de corrigir

| # | Reprodução contra a cadeia 56 |
|---|---|
| **I** | porta devolve substituto de mesmo COID → `state_changed=True`, `observed_state=latent`, **instância bloqueada continua `active`** |
| **J** | autorizado com `decision=None` e `no_change=False` — aceito |
| **K** | no-op com `observed_state=active` para alvo `latent` — aceito |
| **L** | `requested_target_state=inaccessible` com decisão sobre `latent` — aceito |
| **M** | `policy_key=123`, `policy_version="1"`, `governance_policy_key=456`, `matched_rule_id=789` — todos aceitos |
| **N** | `AccessibilityTransitionResult` sem `evaluated_at` |
| **O** | evidência causal aceita em recusa de policy e em alvo não-causal (o caso no-op já era recusado) |
| **P** | prova estática não chamava `transition()`; integração passava 38 strings literais |
| **Q** | `black --check .` reprova `tests/unit/memory/test_accessibility.py` |

## 2. Causas-raiz

Três, como o §6 antecipou — e a terceira delas é um erro **de processo**,
não de código:

1. **igualdade de COID confundida com identidade da instância
   bloqueada.** Verifiquei `returned.id == coid` e chamei isso de
   fidelidade;
2. **o resultado não era máquina de estados exaustiva.** Impus
   invariantes ponto a ponto em vez de enumerar os desfechos possíveis,
   e toda combinação não prevista passou;
3. **atribuição estática confundida com composição tipada ponta a
   ponta** — e, no caso do **Q**, gate reportado a partir de um comando
   que não era o do gate.

```text
SAME COID != SAME LOCKED INSTANCE
RETURNED REPLACEMENT != VERIFIED WRITE
FROZEN DATACLASS != VALID STATE MACHINE
STATIC ASSIGNMENT != TYPED END-TO-END COMPOSITION
```

### Sobre o Q, sem atenuação

Rodei `black` sobre diretórios específicos e reportei `PASS` a partir
daquele comando, não do `black --check .` que o gate exige. O gate
declarado e o gate executado eram comandos diferentes. Neste patch o
comando do gate é o executado, e está registrado literalmente na seção
de resultados.

---

## 3. Correções

### 3.1 Identidade da instância bloqueada

Verificação por `is`, **adicional** às de UUID da E4.7.1:

```text
locked  is subject     após refresh_for_update
written is locked      após transition
estado confirmado lido da instância BLOQUEADA
```

Substituto de mesmo COID → `PIA-8037`, e a transação fica para o
rollback do chamador. Nenhum auto-reparo.

O comportamento real da E3 é provado contra PostgreSQL: `ai472` confirma
que `refresh_for_update(obj) is obj` e que
`AccessibilityManager.transition(obj, target) is obj`. Se a E3 mudar
isso, é ali que se descobre — em vez de a E4.7 silenciosamente
certificar a aparência devolvida.

### 3.2 Máquina exaustiva do resultado

`evaluated_at` passa a existir no resultado, e `__post_init__` enumera
**quatro** desfechos. Nenhum quinto é construível:

| Desfecho | `decision` | `observed_state` | `state_changed` | `no_change` | `causal_event_id` |
|---|---|---|---|---|---|
| governança recusou | `None` | `None` | `False` | `False` | `None` |
| no-op sob lock | `None` | `== requested_target` | `False` | `True` | `None` |
| policy não admitiu | presente | `== decision.source_state` | `False` | `False` | `None` |
| policy admitiu e escreveu | presente | `== requested_target` | `True` | `False` | obrigatório só para extinção |

Mais os invariantes comuns: `decision.target_state ==
requested_target_state`, `decision.evaluated_at == result.evaluated_at`,
`decision.governance_policy_key == resolution.policy_key`, resolução
sobre `ACCESSIBILITY_TRANSITION`, `evaluated_at` aware e canonicalizado
para UTC.

### 3.3 Identidade tipada da decisão

`policy_key`, `governance_policy_key` e `matched_rule_id`: `str` não
vazias. `policy_version`: `int >= 1` e **não** `bool` — aceitá-lo faria
`True` virar versão 1 em silêncio.

```text
MALFORMED PROVENANCE IS NOT PROVENANCE
```

### 3.4 Tipagem ponta a ponta

`tests/static/test_port_assignment.py` passa a **chamar**
`manager.transition(target_state=AccessibilityState.LATENT, ...)` sobre
uma composição declarada como
`AccessibilityPolicyManager[CognitiveObject, AccessibilityState]`. Os
testes de integração migraram de strings literais para membros reais do
enum; os dublês unitários continuam livres com `StateT=str`.

**Achado durante a correção:** a prova ponta a ponta revelou que o
construtor do manager fixava `CausalEvidencePort[CausalEventView,
CausalHistoryView]`, e o `CausalHistoryRepository` real não satisfazia
isso — os modelos da E3 declaram campos como `Mapped[...]`. Passou a ser
`CausalEvidencePort[object, object]`: **`object` é o tipo topo, não
`Any`**, e o mypy recusa ler qualquer atributo dele, o que torna o
estreitamento por `isinstance` obrigatório em vez de opcional. É a
garantia que se quer.

---

## 4. Testes

| Arquivo | Cadeia 56 | Cadeia 57 | Δ |
|---|---|---|---|
| `tests/unit/memory/test_accessibility.py` | 138 | **175** | +37 |
| `tests/integration/memory/test_accessibility_integration.py` | 24 | **29** | +5 |
| `tests/static/test_port_assignment.py` | 1 | **1** | 0 (fortalecido) |
| **Total** | **163** | **205** | **+42** |

Classificação **obtida por execução** contra a cadeia 56:

```text
FALHAM POR COMPORTAMENTO ............ 35
PASSAM NOS DOIS LADOS (guardas) ..... 2
FALHA ESTÁTICA DE TIPAGEM ........... 1 (prova ponta a ponta)
```

### Três testes que codificavam os defeitos

- `ap16` e `ap18` montavam no-op com `observed_state` diferente do alvo —
  o **defeito K escrito no harness**;
- um teste de hash comparava dois `_resultado()` com COID e `policy_id`
  sorteados, então a diferença de hash vinha daí, não da canonicalização
  que ele pretendia provar.

Corrigidos com nota, não removidos.

---

## 5. Resultados

```text
FULL_SUITE = 2069 passed / 1 skipped / 0 failed   (candidata: 2027)
RAW_SUITE  = 1779 passed / 291 skipped / 0 failed

E3 = 598/598   E3.4.2/.1 = 134/134   E4.1 = 40/40   E4.2 = 42/42
E4.3+.3 = 151/151   E4.4 = 74/74   E4.5 = 187/187   E4.6 = 183/183
(todos delta 0)
E4.7 + .1 + .2 = 205 passed

GLOBAL_COVERAGE = 99,08%   (candidata 99,07% — não reduziu)
APP_COGNITIVE_COVERAGE = 100%    APP_MEMORY_COVERAGE = 100%
RUFF = PASS
BLACK = PASS   (comando executado: `black --check .`, black 24.10.0)
MYPY_NEW_ERRORS = 0
STATIC_END_TO_END_PROOF = PASS
SCHEMA_ORM_DRIFT = 0   ALEMBIC_SINGLE_HEAD = 7b2e4c9a15df
NEW MIGRATION = NO   NEW TABLE/COLUMN = NO   NEW ERROR CODE = NO
E3 MODIFIED = NO   E4.8 STARTED = NO
```

Escopo: `schemas/accessibility.py`,
`services/accessibility_policy_manager.py`, os dois arquivos de teste e
a prova estática, mais este documento — exatamente o §12.
`ports/accessibility.py` **não** precisou mudar.

---

## 6. Limitações remanescentes

Registradas sem prometer garantia inexistente:

- a identidade por `is` prova que a instância bloqueada é a escrita
  **dentro da sessão**; ela não substitui o lock de linha, que continua
  sendo a garantia transacional real;
- a verificação de evidência causal permanece **local ao caminho da
  E4.7**: outro chamador do `AccessibilityManager` continua podendo
  extinguir com um `reason` qualquer. Fechar isso globalmente exige
  corretivo próprio da E3;
- a máquina exaustiva cobre os desfechos do resultado, não a correção
  semântica de uma policy publicada: uma regra mal escrita continua
  sendo uma decisão legítima do administrador.

```text
E4_7_2_IMPLEMENTATION = COMPLETE
E4_7_FINAL_STATUS     = AWAITING_INDEPENDENT_AUDIT
PATCH_CHAIN = 57
E4_8_IMPLEMENTATION = NOT_STARTED
READY_FOR_E4_8 = FALSE
```
