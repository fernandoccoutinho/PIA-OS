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

---

## 12. Corretivo E4.8.1 — Isolation Authority & Result Fidelity

**Patch 62.** A auditoria confirmou que a arquitetura fecha o vazamento
`intersection authorization + union retrieval`, mas encontrou quatro
incoerências de **autoridade** ainda aceitas.

### 12.1 Reprodução A–D contra a cadeia 61

| # | Fato registrado |
|---|---|
| **A** | resultado com contexto `alice/research` e decisão emitida para `mallory/other` — **aceito** |
| **B** | Retrieval autorizada por `policy-nao-solicitada` — aceita; e mesma `policy_key` com `version`/`id` diferentes — aceita |
| **C** | Retrieval negada após todas as decisões admitirem → `ValueError`, `IS_PIA_8040 = FALSE` |
| **D** | dois singletons com `policy_id` divergente — `ONE_POLICY_ID = FALSE` |

### 12.2 Causa-raiz

A E4.8 implementou duas relações e faltaram duas:

```text
verificadas:  REQUEST ↔ SINGLETON RESOLUTION
              RETURNED COIDS ⊆ MEMBERSHIP SNAPSHOT
ausentes:     ORIGINAL CONTEXT ↔ EVERY DOMAIN DECISION
              DOMAIN DECISIONS ↔ RETRIEVAL GOVERNANCE RESOLUTION
```

O manager verificava cada singleton **no instante em que o resolvia**,
mas nada reamarrava as decisões ao ator e ao propósito do contexto
original, nem à autoridade que a Retrieval declarava.

```text
SCOPE NON-EXPANSION WITHOUT AUTHORITY FIDELITY = INCOMPLETE ISOLATION
SAME DOMAIN != SAME CONTEXT
DOMAIN BINDING ALONE != CONTEXT BINDING
```

### 12.3 Isolamento de escopo != fidelidade da autoridade

São garantias diferentes, e a E4.8 só tinha a primeira:

- **isolamento de escopo** — nenhum COID devolvido está fora da união
  de memberships dos domínios autorizados;
- **fidelidade da autoridade** — a cadeia inteira (contexto → decisões
  → vista) foi fundamentada na **mesma** pergunta e na **mesma**
  autoridade local.

Sem a segunda, um resultado podia provar domínios e COIDs corretos
enquanto compunha autoridade de ator, propósito ou versão de policy
diferentes.

### 12.4 Identidade local `(policy_key, policy_version, policy_id)`

Definida como identidade **exata**. Os três campos são tudo-ou-nada
pelos invariantes congelados da E4.3.2, então basta um para saber se há
proveniência.

`matched_rule_id` **não** entra: regras diferentes podem casar em
domínios diferentes da **mesma** versão de policy, e usá-lo como
identidade recusaria composição legítima. Há teste provando que
`regra-a` em `D1` e `regra-b` em `D2` continuam válidas.

```text
SAME POLICY KEY != SAME POLICY VERSION
MATCHED RULE != POLICY IDENTITY
ONE REQUEST != MULTIPLE AUTHORITY PROVENANCES
```

### 12.5 Outcomes sem policy local não recebem proveniência fabricada

`PROHIBITED` e `NOT_APPLICABLE` por ausência de versão vigente não
carregam proveniência local, e o isolamento **não** a inventa: a E4.3
deliberadamente não consultou policy nesses casos. Eles recusam
atomicamente, sem Retrieval. `INADMISSIBLE` de origem local preserva a
sua identidade.

Um `PROHIBITED` sem proveniência ao lado de um `ADMISSIBLE` com ela
**não** é incoerência — há teste cobrindo esse caso misto.

### 12.6 Uma implementação, dois pontos de aplicação

`verificar_coerencia_resultado_isolado()` é função pura no schema,
usada por:

1. `MemoryIsolationResult.__post_init__` → `ValueError` (construtor
   direto não contorna a garantia);
2. `MemoryIsolationManager` → `PIA-8040` **antes** de construir o value
   object.

```text
COLLABORATOR DISAGREEMENT != INVALID REQUEST
```

O manager converte divergência de colaborador em `PIA-8040` porque o
pedido já foi validado — o que resta é desacordo interno. O value object
levanta `ValueError` porque ali o erro é de construção. Duas cópias da
mesma regra divergiriam: E4.5.1, E4.6.1 e E4.7.2 já pagaram por isso.

O modo `apenas_decisoes=True` permite recusar identidades divergentes
**antes** de ler memberships — patrimônio não se toca sob autoridade
incoerente.

### 12.7 Correção do harness

O helper unitário gerava `uuid.uuid4()` por chamada como `policy_id`,
normalizando como aceitável uma combinação que o repositório real não
produz. Passou a usar identidade estável por versão publicada, com nota.
O dublê de Retrieval passou a **ecoar a `policy_key` recebida**, como a
E4.6 real faz — antes ele devolvia sempre `gov-iso` e era ele próprio
incoerente. Nenhum teste foi removido ou enfraquecido.

### 12.8 Classificação contra a cadeia 61

```text
FAILS_ON_CHAIN_61_BY_BEHAVIOR ......... 18
PASSES_ON_BOTH_SIDES_AS_GUARD ......... 10
FAILS_ONLY_BY_NEW_SYMBOL_OR_IMPORT .... 0
```

Os testes dos defeitos A–D **coletam e falham por comportamento** na
cadeia 61 — nenhum `ModuleNotFoundError` foi contado como prova.

### 12.9 Resultados

```text
FULL_SUITE = 2279 passed / 1 skipped / 0 failed   (candidata: 2251)
RAW_SUITE  = 1947 passed / 333 skipped / 0 failed
E4.8 = 134 (era 107)   demais módulos delta 0

GLOBAL_COVERAGE = 99,13%   (inalterado)
APP_MEMORY = 100%   APP_COGNITIVE = 100%
RUFF = PASS   BLACK = PASS (`black --check .`, black 24.10.0)
MYPY_NEW_ERRORS = 0   ALEMBIC_SINGLE_HEAD = 7b2e4c9a15df
NEW_ERROR_CODE = NO   NEW_MIGRATION = NO   NEW_TABLE = NO   NEW_COLUMN = NO
E3_MODIFIED = NO   DATABASE_WRITES_DURING_ISOLATION = 0
```

Escopo: 4 arquivos (2 produção, 2 testes) e este documento.

### 12.10 Limite honesto sobre o instante

`GovernanceResolution` **não** carrega o instante em que foi avaliada.
A prova de "uma autoridade por pedido" usa portanto a **identidade da
versão de policy**, não um relógio inforjável: duas resoluções da mesma
versão são indistinguíveis quanto ao momento.

Repassar o mesmo `moment` continua necessário — e é o que impede a
composição por versões diferentes na prática —, mas a garantia
verificável é de identidade, não temporal. A garantia geral do módulo
permanece **application-level, explicit-scope, read-path**.

---

## 13. Corretivo E4.8.2 — Denied-Path Authority Coherence

**Patch 63.** A auditoria encontrou que a verificação de coerência
introduzida pela E4.8.1 só era exercida quando **todas** as decisões
autorizavam.

### 13.1 Reprodução contra a cadeia 62

Pedido com dois domínios sob a mesma `policy_key` e o mesmo `moment`:

```text
D1 → ADMISSIBLE,   policy_key=K, version=1, policy_id=A
D2 → INADMISSIBLE, policy_key=K, version=1, policy_id=B   (A != B)
```

Executado pelo caminho público `retrieve_isolated(...)`:

```text
EXCEPTION_TYPE = ValueError
code           = None
IS_PIA_8040    = FALSE
memberships    = 0
retrieval      = 0
```

O mesmo com `INADMISSIBLE(A) + INADMISSIBLE(B)`.

### 13.2 Causa-raiz

No corpo de `retrieve_isolated()` da cadeia 62:

1. as decisões eram produzidas;
2. o ramo `if not all(d.authorized ...)` **retornava**;
3. `_verificar_coerencia(..., apenas_decisoes=True)` aparecia só
   **depois** desse retorno.

A incoerência era então detectada pelo `__post_init__` do value object —
corretamente, mas como `ValueError` cru, sem o diagnóstico do caminho
canônico.

**A função pura não estava errada. A posição da chamada estava.**

Registro isso como erro meu de sequenciamento: ao mover a verificação
para "antes do snapshot" na E4.8.1, coloquei-a depois de um `return` que
já existia, e nenhum teste da E4.8.1 cobria o caminho recusado com
identidades divergentes.

### 13.3 Correção

Ordem agora exigida e implementada:

```text
1. produzir todas as decisões
2. verificar coerência contextual e identidade comum das decisões
3. se incoerentes → PIA-8040
4. se coerentes e alguma não autoriza → recusa atômica normal
5. se todas autorizam → snapshot, Retrieval e verificação final
```

A chamada anterior, que ficava antes do snapshot, tornou-se redundante e
foi **removida**. Restam exatamente duas no fluxo: a das decisões e a
final, sobre o resultado da Retrieval.

Nenhuma segunda função foi criada, e o manager continua sem comparar
`policy_key`, `policy_version` ou `policy_id` por conta própria — há
teste estrutural provando ambas as coisas, e outro provando a **ordem**
das chamadas dentro do método.

### 13.4 Semântica congelada

`PIA-8040` para identidades locais divergentes **independentemente dos
outcomes** — `ADMISSIBLE+INADMISSIBLE`, `INADMISSIBLE+INADMISSIBLE`, e
qualquer combinação que transporte duas identidades locais.

Continuam legítimos, com teste cada um:

- `ADMISSIBLE + INADMISSIBLE` com a **mesma** identidade → recusa
  atômica normal;
- `ADMISSIBLE + PROHIBITED` → `PROHIBITED` não carrega proveniência
  local, então não há duas identidades;
- `matched_rule_id` diferentes da mesma versão → válido;
- construtor direto de `MemoryIsolationResult` → continua `ValueError`.

Nenhuma membership ou Retrieval é consultada antes de confirmar a
coerência — provado com contadores nos dublês e com listener SQL contra
o banco real.

### 13.5 Classificação contra a cadeia 62

```text
FAILS_ON_CHAIN_62_BY_BEHAVIOR ......... 5
PASSES_ON_BOTH_SIDES_AS_GUARD ......... 7
FAILS_ONLY_BY_NEW_SYMBOL_OR_IMPORT .... 0
```

Os testes do defeito coletam e falham por comportamento na cadeia 62.

### 13.6 Resultados

```text
FULL_SUITE = 2291 passed / 1 skipped / 0 failed   (candidata: 2279)
RAW_SUITE  = 1957 passed / 335 skipped / 0 failed
E4.8 = 146 (era 134)   demais módulos delta 0

GLOBAL_COVERAGE = 99,13%   (inalterado)
APP_MEMORY = 100%   APP_COGNITIVE = 100%
RUFF = PASS   BLACK = PASS (`black --check .`, black 24.10.0)
MYPY_NEW_ERRORS = 0   ALEMBIC_SINGLE_HEAD = 7b2e4c9a15df
NEW_ERROR_CODE = NO   NEW_MIGRATION = NO   E3_MODIFIED = NO
```

Produção: **um único arquivo**,
`backend/app/memory/services/memory_isolation_manager.py`. A função pura
não precisou mudar.
