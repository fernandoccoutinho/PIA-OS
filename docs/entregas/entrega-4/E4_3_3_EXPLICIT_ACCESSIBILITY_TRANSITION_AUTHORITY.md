# E4_3_3_EXPLICIT_ACCESSIBILITY_TRANSITION_AUTHORITY

**Módulo:** E4.3.3 — corretivo antecedente de governança
**Baseline:** `PATCH_CHAIN = 53` · HEAD `3c3b184b7d81…` ✓ ·
PARENT `50bf7e5ae6eb…` ✓ · TREE `d00e0170f2fa…` ✓ ·
PATCH_ID `3cbcf3febfbf…` ✓ · bundle SHA-256 `b5ee2acc…ef46` ✓ ·
patch SHA-256 `1ce1aeed…a524` ✓ · migration head `4ca61776b982` ✓ ·
`git status` limpo ✓ · suíte **1821 passed / 1 skipped / 0 failed** ✓

Trees registrados na baseline: `cognitive be407b46f679a009e0f7f7e9f01fb784f08dea54`,
`alembic f01a1f812eb11695b9daeb6b1707e6477e9330fa`,
`memory 9579dbd028a78e1b9ffd18c0ed60c0bf1bfbb12e`.

---

## 1. Reprodução da lacuna (§9 do prompt)

Executada contra a baseline, sem adulterar o repositório:

| # | Demonstração | Resultado |
|---|---|---|
| 1 | membros de `CognitiveOperation` | **7** |
| 2 | operação de transição de acessibilidade | **ausente** |
| 3 | `TRANSFORM` significa | "produzir nova versão ou derivação" |
| 4 | `operations=()` casa as sete | **True** para todas |
| 5 | condição de casamento | `if self.operations and operation not in self.operations` — sem fronteira positiva |
| 6 | policy publicada | payload `{"operations": []}`; `update` e `delete` recusados com `PIA-8028` |
| 7 | `NOT_APPLICABLE` concede | `execution_authorized = False` |

```text
DEFECT = WILDCARD AUTHORITY ENVELOPE IS OPEN TO FUTURE ENUM EXPANSION
```

## 2. Causa raiz

O envelope de autoridade do curinga era definido por **ausência de
restrição**, não por um conjunto declarado. Como versões publicadas são
imutáveis, o texto da policy nunca mudaria — mas o significado dela
mudaria sozinho a cada operação nova, concedendo capacidades que ninguém
autorizou.

## 3. Decisão

Escopo **positivo e congelado**, com os sete membros enumerados
literalmente. Detalhes e justificativa no
`EDR_E4_3_3_EXPLICIT_ACCESSIBILITY_TRANSITION_AUTHORITY.md`.

## 4. Provas

| Propriedade | Prova |
|---|---|
| as sete continuam casando o curinga | teste parametrizado, uma por operação |
| a nova **não** casa o curinga | unitário + integração com policy real |
| opt-in `ADMIT` → `ADMISSIBLE` | unitário + `resolve()` contra PostgreSQL |
| opt-in `DENY` → `INADMISSIBLE` | unitário + integração |
| `DENY_OVERRIDES` preservado | unitário |
| policy antiga não reescrita | payload comparado antes/depois de `resolve()`, byte a byte |
| serialização e round-trip | `"accessibility_transition"` exato, determinístico |
| payload histórico vazio | continua `[]` após leitura, e não casa a nova operação |
| autoridade não cruza | `READ` não concede a nova; a nova não concede `READ` |
| sem blacklist, sem `set(CognitiveOperation)` | inspeção AST do **código executável** |

A inspeção é feita sobre o código executável, com docstrings removidas:
elas citam nominalmente `set(CognitiveOperation)` ao explicar por que
**não** derivar o escopo do enum. Mesmo falso positivo que a E4.3.1
corrigiu em `gv16`.

## 5. Persistência

```text
NEW_PERSISTENT_ENTITY = NO   NEW_TABLE = NO
NEW_COLUMN = NO              MIGRATION_REQUIRED = NO
```

`GovernancePolicy.rules` já persiste operações como tokens JSON; o novo
valor cabe sem migração, verificado no PostgreSQL real.

## 6. Códigos de erro

```text
NEXT_FREE_ERROR_CODE = PIA-8035
RESERVED_BY_E4_3_3 = NO
```

Nenhum criado. Os desfechos necessários já existiam.

## 7. Testes

43 novos (36 unitários + 7 integração). E4.3 passou de 108 para 151.

**Classificação obtida por execução**, com cópia temporária dos testes em
que os símbolos novos foram substituídos por equivalentes de
caracterização (o método está registrado aqui porque, sem ele, o módulo
nem coletaria na baseline):

```text
FALHAM NA 53 POR COMPORTAMENTO ...... 10 unitários + 3 integração = 13
PASSAM NOS DOIS LADOS (guardas) ..... 26 unitários + 4 integração = 30
```

Os 13 são exatamente os que exercitam o alcance do curinga e o opt-in
explícito. Os 30 verificam o que já funcionava — as sete operações
históricas, `DENY_OVERRIDES`, imutabilidade da policy, serialização — e
agora ficam travados contra regressão.

**Um teste existente foi atualizado, não removido:**
`test_gv1_cognitive_operation_vocabulary_is_closed` asserava exatamente
sete valores e passa a assear oito, com nota do corretivo. O vocabulário
continua fechado; o que mudou foi seu tamanho.

## 8. Resultados

```text
FULL_SUITE = 1864 passed / 1 skipped / 0 failed   (baseline: 1821)
RAW_SUITE  = 1603 passed / 262 skipped / 0 failed

E3 = 598/598   E3.4.2/.1 = 134/134   E4.1 = 40/40   E4.2 = 42/42
E4.4 = 74/74   E4.5 = 187/187        E4.6 = 183/183   (todos delta 0)
E4.3 + E4.3.1 + E4.3.2 + E4.3.3 = 151 passed (era 108)

GLOBAL_COVERAGE = 98,98%   (não reduziu)
APP_COGNITIVE_COVERAGE = 100%    APP_MEMORY_COVERAGE = 100%
RUFF = PASS   BLACK = PASS   MYPY_NEW_ERRORS = 0
SCHEMA_ORM_DRIFT = 0   MIGRATION_HEAD = 4ca61776b982 (single)
PostgreSQL 16.14 real
```

## 9. Escopo

Produção (2): `models/governance_enums.py`, `schemas/governance.py`.
Testes (2). Docs (3, sendo 2 novos e 1 qualificado).

Nenhuma alteração em `app/cognitive`, `alembic`, E4.7 ou E4.8. Nenhum
model, repository, service, endpoint, tabela, coluna, migração,
`GovernanceOutcome`, `GovernanceEffect`, `CriticalCapability` ou error
code novo.

## 10. Gate

```text
E4_3_3_IMPLEMENTATION = COMPLETE
E4_3_FINAL_STATUS     = AWAITING_INDEPENDENT_AUDIT
GOVERNANCE_OPERATION_GAP = CORRECTED_AWAITING_AUDIT
PATCH_CHAIN = 54

E4_7_IMPLEMENTATION = NOT_STARTED
READY_FOR_E4_7 = FALSE
READY_FOR_E4_8 = FALSE
```

Somente a auditoria independente pode liberar a retomada da E4.7.
