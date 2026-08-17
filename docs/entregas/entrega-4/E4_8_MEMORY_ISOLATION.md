# E4_8_MEMORY_ISOLATION

**Módulo:** E4.8 — Memory Isolation
**Baseline:** `PATCH_CHAIN = 60` · HEAD `1192a6a916a8…` ✓ ·
PARENT `553579d8…` ✓ · TREE `f569f01c65eb…` ✓ ·
PATCH_ID `80ddb376…` ✓ · bundle SHA-256 `d263f45b…59dd` ✓ ·
patch SHA-256 `9317a08c…f9c2` ✓ · migration head `7b2e4c9a15df` ✓ ·
`git status` limpo ✓ · suíte **2145 passed / 1 skipped / 0 failed** ✓ ·
trees `cognitive be407b46…` e `alembic 65a066de…` ✓

---

## 1. Registro de ausência documental

O `PIA_OS_SOPHIA_CANONICAL_MASTER_v1.0.md` (SHA-256 `48aca702…5000a`),
citado no §5 do prompt, **não foi fornecido**. Conforme o próprio §5,
apliquei integralmente o resumo normativo autocontido do §13 e registro
a ausência. Isso não bloqueou o módulo nem autorizou inventar
funcionalidade de produto.

## 2. Reprodução do risco — refeita na cadeia 60

Não presumi que o comportamento persistia após a E4.3.4/.1:

```text
7. resolução (D1,D2) → admissible, authorized=True, rule="so-d1"
8. vista     (D1,D2) → A (de D1)=True | B (de D2)=True   ← RISCO PERSISTE
9. controle    (D1)  → A=True | B=False
```

A E4.3.4/.1 criou a prova contratual, mas não alterou `interseção +
união`. O vazamento era idêntico ao observado na cadeia 58.

## 3. Tensões A–F

| # | Resultado |
|---|---|
| **A** | Viável — `ContextManager.derive()` aceita as quatro dimensões; singleton preserva ator, propósito e sessão |
| **B** | **Revalidada no código**, não presumida — ver §3.1 |
| **C** | Escopo vazio recusado como precondição (`PIA-8039`), sem alterar E4.2 nem E4.6 |
| **D** | Snapshot conservador no instante observado, sem lock de escrita |
| **E** | Uma única chamada à E4.6, com contexto original e paginação repassada |
| **F** | Quatro portas satisfeitas por atribuição estática pelos objetos reais |

### 3.1 Tensão B — os seis pontos verificados

```text
1. context_domain_ids / context_actor_ref / context_purpose SEM default
   em GovernanceDecision E em GovernanceResolution ...................... ✓
2. canonicalizados (tuple) e profundamente imutáveis (hashable) ......... ✓
3. propagados nos quatro outcomes (4 construtores) ...................... ✓
4. session_id continua fora do vínculo ................................. ✓
5. resolucao_vincula_contexto() é a implementação compartilhada ......... ✓
6. E4.6/E4.7 recusam resolução adulterada antes do patrimônio ........... ✓
```

A E4.8 **usa** a função compartilhada — não copia a comparação, não
acessa o repositório de policy para "confirmar" a resolução, e não
confia porque o manager concreto normalmente devolve o contexto certo.
Há prova com porta adulterada que chama o manager real e substitui uma
dimensão por `dataclasses.replace()`.

## 4. Arquitetura

```text
validar pedido; escopo vazio → PIA-8039, antes de qualquer colaborador
ContextManager.validate + fidelidade pedido↔contexto
instante único (UTC)
resolver READ por singleton, verificando o vínculo
qualquer NOT_APPLICABLE / INADMISSIBLE / PROHIBITED → recusa ATÔMICA
snapshot da união das memberships AUTORIZADAS (uma vez, depois da autoridade)
UMA chamada à E4.6, com o contexto ORIGINAL
pós-condição: coids ⊆ snapshot → senão PIA-8040, sem filtrar
```

Dois value objects congelados: `DomainIsolationDecision` (uma por
domínio, exigindo resolução singleton) e `MemoryIsolationResult` (com os
dez invariantes do §9.5).

`MemoryIsolationManager` não tem estado mutável de instância — provado
comparando `__dict__` antes e depois de uma chamada.

## 5. Diagnósticos

| Código | Uso | Categoria |
|---|---|---|
| `PIA-8039` | pedido isolado sem domínio explícito | `VALIDATION` / 400 |
| `PIA-8040` | desacordo entre pedido, contexto, resoluções, snapshot e vista | `SYSTEM` / 500 |

Ambos com chamador real e teste. `INADMISSIBLE`, `NOT_APPLICABLE` e
`PROHIBITED` são **resultados válidos de autoridade**, nunca exceção.
Próximo livre: `PIA-8041`.

## 6. Testes

| Arquivo | Testes |
|---|---|
| `tests/unit/memory/test_memory_isolation.py` | **86** |
| `tests/integration/memory/test_memory_isolation_integration.py` | **20** |
| `tests/static/test_isolation_ports.py` | **1** |
| **Total E4.8** | **107** |

### Classificação honesta contra a cadeia 60

```text
FAILS_ONLY_BY_NEW_SYMBOL_OR_IMPORT ......... 106
FAILS_ON_CHAIN_60_BY_BEHAVIOR .............. 0
STATIC_ONLY_GUARD .......................... 1
```

A E4.8 não existia na cadeia 60, então a coleta falha inteira com
`ModuleNotFoundError`. **Nenhum teste é apresentado como prova
comportamental**, porque nenhum o é.

**Limitação registrada sobre a prova estática:** executei
`tests/static/test_isolation_ports.py` contra a cadeia 60 esperando
falha de tipagem, e o mypy reportou **zero erros** — porque
`pyproject.toml` define `ignore_missing_imports = true`, e o módulo
ausente vira `Any` em silêncio. A prova é válida **na cadeia 61**, onde
verifica atribuição e chamada tipada com os tipos reais; ela não serve
como discriminante entre as cadeias. Registro isso em vez de apresentar
"passa nos dois lados" como se fosse evidência.

### Defeitos meus, corrigidos durante o trabalho

**(a)** A porta declarava `domain_ids: object` em `derive()`; parâmetro
é posição **contravariante**, então alargá-lo fez a satisfação estática
falhar. Corrigido para a assinatura real — o mypy apontou.

**(b)** Escrevi `_dominios_canonicos()` e nunca o usei. Código morto
revelado pela exigência de 100% de cobertura; removido em vez de coberto
com teste artificial.

**(c)** Dois guardas estruturais usavam substring solta: `"add("` pegava
`uniao.add(coid)` (um `set` em memória, não escrita), e `"acl"` casava
dentro de `collections.abc`. Passaram a comparar por **palavra
inteira**, e o guarda de escrita passou a procurar `session.add` /
`session.delete` / SQL.

**(d)** Um guarda proibia `context_domain_ids !=` no código executável
para provar uso da função compartilhada — mas isso pegava a comparação
legítima de `DomainIsolationDecision`, que verifica o **singleton**, uma
coisa diferente. Precisei o guarda para o que importa: o manager não
comparar `context_actor_ref`/`context_purpose` por conta própria.

## 7. Resultados

```text
FULL_SUITE = 2251 passed / 1 skipped / 0 failed   (baseline: 2145)
RAW_SUITE  = 1925 passed / 327 skipped / 0 failed

E3 = 598/598   E3.4.2/.1 = 134/134   E4.1 = 40/40   E4.2 = 42/42
E4.3 = 177/177   E4.4 = 74/74   E4.5 = 187/187   E4.6 = 198/198
E4.7 = 240/240   (todos delta 0)
E4.8 = 107

GLOBAL_COVERAGE = 99,13%   (baseline 99,09% — não decresceu)
APP_COGNITIVE_COVERAGE = 100%    APP_MEMORY_COVERAGE = 100%
RUFF = PASS
BLACK = PASS   (comando executado: `black --check .`, black 24.10.0)
MYPY_NEW_ERRORS = 0   STATIC_PORT_PROOF = PASS
SCHEMA_ORM_DRIFT = 0   ALEMBIC_SINGLE_HEAD = 7b2e4c9a15df
NEW_TABLE = NO   NEW_COLUMN = NO   NEW_MODEL = NO   NEW_MIGRATION = NO
DATABASE_WRITES_DURING_ISOLATION = 0
APP_COGNITIVE_MODIFIED = NO
```

Os arquivos novos rodaram **5×** seguidas sem instabilidade.

## 8. Compatibilidade prospectiva

```text
PIA_OS_SOPHIA_MASTER_COMPATIBILITY
├── USER_AUTHORITY_PRESERVED = TRUE
├── SOPHIA_BRAND_PIA_OS_CODEBASE_PRESERVED = TRUE
├── MODULE_SCOPE_AND_DEFERRED_CAPABILITIES_DECLARED = TRUE
├── SCHEDULE_MODE_DECLARED = NOT_APPLICABLE
├── AI_ROLE_AND_STEP_INSTRUCTION_DISTINGUISHED = NOT_APPLICABLE
├── PROVIDER_CONNECTION_METHOD_DECLARED = NOT_APPLICABLE
├── AUTOMATION_SCOPE_DECLARED = READ_ONLY_ISOLATION_COMPOSITION
├── APPROVAL_GATES_DECLARED = NOT_APPLICABLE
├── PERSISTENCE_BEHAVIOR_DECLARED = TRANSIENT_NO_WRITES
├── MULTI_AI_RESULT_ATTRIBUTION_DECLARED = NOT_APPLICABLE
├── DIVERGENCE_PRESERVATION_DECLARED = TRUE
├── CONCURRENT_WORK_ISOLATION_DECLARED = CALL_LOCAL_NO_SHARED_MUTABLE_STATE
├── BACKGROUND_EXECUTION_AUTHORIZATION_DECLARED = NOT_APPLICABLE
├── RESOURCE_LIMITS_QUEUE_AND_COST_DECLARED = NOT_APPLICABLE
├── REMOTE_RESOURCE_SCOPE_DECLARED = NOT_APPLICABLE
├── OBSERVATION_PREPARATION_EXECUTION_DISTINGUISHED = READ_PATH_ONLY
├── CREDENTIAL_AND_SECRET_BOUNDARY_DECLARED = NOT_APPLICABLE
├── FAILURE_ROLLBACK_AND_CONCURRENCY_DECLARED = NO_WRITES_AND_CONSERVATIVE_SNAPSHOT
├── CURRENT_CAPABILITY_NOT_OVERSTATED = TRUE
└── FROZEN_MODULES_UNCHANGED = TRUE
```

Nenhum código foi criado apenas para alterar um `NOT_APPLICABLE`. Há
teste provando que `Workspace`, `Schedule`, `Workstream` e
`RemoteResource` não foram antecipados.

## 9. Limitações declaradas

```text
ISOLATION GUARANTEE = APPLICATION-LEVEL, EXPLICIT-SCOPE, READ-PATH
RLS GUARANTEE = NONE
AUTHENTICATION GUARANTEE = NONE
CONFIDENTIALITY AT REST/IN TRANSIT = OUT OF SCOPE
GLOBAL GUARANTEE OUTSIDE THE E4.8 PATH = NONE
```

- Chamadas diretas a repositórios ou à E4.6 **não** foram impedidas.
  Quem chamar a E4.6 diretamente com contexto multidomínio continuará
  obtendo a união — a E4.8 é o caminho isolado, não um guarda global.
- O snapshot garante o **instante observado**; uma membership criada
  concorrentemente produziria, no pior caso, `PIA-8040` — recusa
  conservadora, nunca vazamento.
- `actor_ref` é descritor, não credencial; `session_id` não é fronteira
  de segurança.
- A prova estática não discrimina entre as cadeias 60 e 61, por causa de
  `ignore_missing_imports` (§6).

## 10. Stop Conditions

```text
STOP_CONDITIONS = NONE
```

Nenhuma das 18 ocorreu. Em particular: E3, E4.1, E4.3, E4.6 e E4.7 não
foram alteradas; nenhuma tabela, coluna, model ou migração; nenhum RLS,
owner, ACL, tenant ou autenticação; nenhuma hierarquia de domínio;
Search nunca chamada diretamente; paginação não recomposta; sem `Any`,
reflexão ou import de `app.cognitive` em produção; sem lock de escrita;
`session_id` e `actor_ref` não viraram autoridade; contexto nunca
reescrito; E4.9 não iniciada.

## 11. Gate

```text
E4_8_IMPLEMENTATION = COMPLETE
E4_8_FINAL_STATUS = AWAITING_INDEPENDENT_AUDIT
PATCH_CHAIN = 61
READY_FOR_E4_9 = FALSE
```

O implementador não declara `PASS FINAL`. **E4.9 não foi iniciada.**
