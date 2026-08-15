# E4_6_MEMORY_RETRIEVAL

**Módulo:** E4.6 — Memory Retrieval
**Baseline:** `PATCH_CHAIN = 50` · HEAD `8cc795312662…` ✓ ·
PARENT `007ee5bec502…` ✓ · TREE `00aa609e412e…` ✓ ·
PATCH_ID `7075ebeb523e…` ✓ · bundle SHA-256 `ae4027bd…761f` ✓ ·
migration head `4ca61776b982` ✓ · `git status` limpo ✓ ·
trees protegidos `cognitive be407b46` e `alembic f01a1f81` ✓
**Patch:** `e4-6-memory-retrieval.patch` (51º)

Suíte da baseline reexecutada antes de qualquer alteração:
**1638 passed / 1 skipped / 0 failed**.

---

## 1. O que o módulo é

Compositor **transitório** de uma vista admissível do patrimônio
cognitivo persistido:

```text
Memory(Context) = Admissible_Context(Persistent(CognitivePatrimony))
```

Compõe `MemoryDomain` (E4.1), `MemoryContext` (E4.2), Governance (E4.3),
`AccessibilityState` (E3.6) e Search (E3.8), e produz uma
`ADMISSIBLE MEMORY VIEW`.

```text
RETRIEVAL CHANGES VIEW
RETRIEVAL DOES NOT REWRITE PATRIMONY

RETRIEVAL != GOVERNANCE   RETRIEVAL != SEARCH    RETRIEVAL != MEMORY
RETRIEVAL != STORAGE      RETRIEVAL != RANKING   RETRIEVAL != EXISTENCE
NOT RETRIEVED != FORGOTTEN
NO RESULT     != NEVER EXISTED
DENIED        != EMPTY RESULT
```

A E3 permanece a única fonte da verdade do patrimônio.

---

## 2. A porta estrutural — e por que ela é tipada

`app/memory` não importa `app.cognitive`. O §10 exigia composição
**tipada**, sem reflexão e sem `Any`. A inspeção do código real mostrou
que isso é alcançável, e o achado que destrava tudo é este:

> `AccessibilityState` e `RevisionStatus` são `StrEnum` na E3.

Portanto uma property de protocolo tipada como `str` é satisfeita
**covariantemente** por um atributo `Mapped[AccessibilityState]`. A E4.6
lê o token sem importar o enum.

```python
CriteriaT_contra = TypeVar("CriteriaT_contra", contravariant=True)

class CognitiveObjectView(Protocol):        # id, clid, accessibility,
    ...                                      # revision_status, created_at,
                                             # deleted_at — só properties

class CognitiveSearchPort(Protocol[CriteriaT_contra]):
    def search(self, criteria, *, limit=None, offset=None) -> Sequence[CognitiveObjectView]: ...
```

- **critérios opacos**: `CriteriaT_contra` é contravariante e a E4.6
  nunca inspeciona os critérios. O vocabulário continua sendo o da E3.8
  (`coid`, `clid`, `accessibility`, `revision_status`, `trace_id`,
  `created_from`, `created_until`, `include_deleted`), e recriá-lo aqui
  produziria um segundo `SearchCriteria` que divergiria do primeiro;
- **resultado estrutural**: satisfeito pelo `CognitiveObject` real sem
  que ele saiba da porta;
- **retorno covariante**: `Sequence[...]` aceita `list[CognitiveObject]`.

Verificado, não presumido: `isinstance(SearchEngine(...), CognitiveSearchPort)`
e `isinstance(CognitiveObject(), CognitiveObjectView)` são asserções de
teste, unitário e de integração.

Precedente: as portas da E4.5. A diferença é que lá a forma do recibo
era conhecida; aqui os critérios precisam permanecer desconhecidos.

**Nenhuma Stop Condition do §20.6 foi acionada.**

Custo declarado — o mesmo que a E4.4 assumiu ao ler a E3 por descritores
de tabela: acoplamento por **forma**, não por tipo nominal. Se a E3
renomear um campo ou trocar o tipo base de um enum, isto quebra aqui, e
é o mypy que deve apontar.

---

## 3. Ordem canônica da operação

```text
1. validar limit/offset e o descritor
2. exigir CognitiveOperation.READ
3. validar o MemoryContext (contrato da E4.2)
4. GovernanceManager.resolve() — caminho canônico
5. se não autorizado: resultado explícito, SEM Search e SEM memberships
6. escopo contextual de domínios (união)
7. Search da E3 em lotes determinísticos
8. filtros de admissibilidade
9. paginação DEPOIS dos filtros
10. projeção em value objects imutáveis
```

**Governança precede qualquer toque no patrimônio** — inclusive a
leitura de memberships destinada a compor a vista. Sob recusa, a
quantidade de objetos, ou o fato de existirem, já seria informação
vazada. Provado com contador de chamadas em `SearchEngine.search` e em
`list_memberships_of_domain`, nos três desfechos de recusa.

Só `resolution.execution_authorized is True` autoriza a Search. A
assinatura pública não oferece por onde injetar autoridade externa: só
`policy_key` — não há `policy`, `resolution`, `authorized` nem `rules`,
verificado por inspeção da assinatura.

```text
ACTOR PRESENCE != AUTHORIZATION       POLICY ABSENCE != ADMISSION
NOT_APPLICABLE != ADMISSIBLE          INADMISSIBLE   != EMPTY SEARCH
PROHIBITED     != LOCAL DENIAL
```

Um descritor de outra operação é recusado **antes** da resolução: não é
pedido de leitura que a governança deva julgar, é pedido endereçado ao
módulo errado.

---

## 4. Recusa não é vista vazia

```text
NEGADO      → search_executed=False, items=(), has_more=None
AUTORIZADO  → search_executed=True,  items=tupla,  has_more=bool
```

Deliberadamente **não existe campo de contagem**. Registrar
`matched_count = 0` numa recusa afirmaria que uma busca ocorreu e nada
encontrou — vazando que o patrimônio está vazio sob aqueles critérios.
Silêncio sobre existência é parte da recusa, e há teste verificando que o
atributo não existe.

Busca autorizada com `items = ()` é resultado **legítimo** e continua
distinguível pela combinação `search_executed=True` / `has_more=False`.

A `GovernanceResolution` é preservada íntegra, inclusive as alternativas
admissíveis da fronteira de segurança: a E4.6 não inventa, não remove e
não reclassifica nenhuma.

Todos os invariantes vivem em `__post_init__`, valem no construtor direto
e em `dataclasses.replace()` — sexta vez que o projeto aplica a lição
(E4.2.1, E4.3.2, E4.4.1, E3.4.2.1, E4.5.1):

```text
frozen=True ALONE != DEEP IMMUTABILITY
```

---

## 5. Domínios — união

```text
MULTI_DOMAIN_CONTEXT = UNION OF DECLARED DOMAIN MEMBERSHIPS
scope(D1, D2) = members(D1) ∪ members(D2)
```

O contexto declara um conjunto de **perspectivas**, não uma conjunção de
requisitos. Exigir pertencimento simultâneo introduziria interseção
restritiva que o contrato não indica — e a interseção que a governança já
faz é outra decisão, sobre outra coisa.

| Situação | Comportamento |
|---|---|
| contexto com domínios | só COIDs em ao menos um domínio declarado |
| contexto sem domínios | nenhum filtro de domínio |
| COID em dois domínios | aparece **uma** vez |
| objeto zero-domain | aparece sem recorte; não aparece com recorte |
| domínio desconhecido | diagnóstico da E4.2, **não** vista vazia |

`session_id`, `actor_ref` e `purpose` não filtram objeto: influenciam
governança, não a identidade do patrimônio.

**Limitação declarada:** o escopo é materializado uma vez, com uma
consulta por domínio declarado, e cresce com o total de membros desses
domínios. Uma versão incremental exigiria consulta por candidato — troca
de custo, não de semântica.

---

## 6. Accessibility na vista

```text
ACTIVE, LATENT           → retrievable
INACCESSIBLE             → not exposed
CAUSALLY_EXTINCT         → not exposed
soft-deleted             → not exposed
```

Comparação por **igualdade exata** dos tokens persistidos
(`"active"`, `"latent"`), sem normalização — mesma disciplina congelada
na E4.5.1 para `qualifier`.

O filtro de soft-deleted é **defensivo**: vale mesmo que um critério
traga `include_deleted=True`, porque auditoria histórica pertence aos
caminhos próprios da E3/E4.4. Provado em integração.

```text
INACCESSIBLE     != NONEXISTENT
CAUSALLY_EXTINCT != HISTORICALLY ERASED
FILTERED OUT     != DELETED
```

Os objetos excluídos permanecem **íntegros no banco** — verificado por
contagem direta após o retrieval.

A E4.6 lê estados e não executa transições. Não altera estado, não
reativa objeto, não infere extinção, não cria `AccessibilityPolicy` e não
antecipa a matriz de transições da E4.7 — da qual **não depende**.

---

## 7. Paginação depois dos filtros

O erro que este desenho evita: aplicar `limit`/`offset` ao conjunto bruto
da Search e filtrar depois produz páginas incompletas, buracos entre
páginas e `has_more` errado, porque há candidatos que os filtros
contextuais descartam.

Implementação: Search em lotes determinísticos (`SEARCH_BATCH_SIZE = 100`,
independente do `limit` público) → filtros → descarta `offset` sobre
itens **já admissíveis** → coleta `limit + 1` → deriva `has_more`.

```text
DEFAULT_LIMIT = 50    MAX_LIMIT = 100    limit >= 1    offset >= 0
```

O total contextual **não** é exposto: apurá-lo exigiria varrer
integralmente todos os candidatos, e `has_more` basta nesta etapa.

Nada reordena. A ordenação é a canônica da E3 (`created_at ASC, id ASC`)
e **ordem não é ranking**.

Há testes construídos para que uma paginação "filtrar depois do limit"
falhe de forma determinística: admissíveis e inadmissíveis intercalados,
com asserção de que cada página tem exatamente 2 itens — no unitário e
contra PostgreSQL.

---

## 8. Distinções preservadas

Nada é privilegiado em silêncio: nem `CURRENT` sobre `SUPERSEDED`, nem
consolidação sobre suas fontes, nem objeto com CLID sobre objeto sem
CLID, nem objeto com evidência de continuidade sobre objeto sem ela.

```text
MISSING CONTINUITY EVIDENCE != RETRIEVAL INADMISSIBILITY
CONSOLIDATION != SOURCE REPLACEMENT
DIVERGENCE != INVALIDITY
```

A E4.6 nem sequer recebe o `PersistenceManager` — verificado por
inspeção da assinatura do construtor.

**Nenhuma desduplicação** por CLID, equivalência, conteúdo presumido,
cadeia de revisão, consolidação ou similaridade. Só o mesmo **COID**
repetido é tratado como defeito, e produz diagnóstico explícito
(`PIA-8033`) em vez de escolha silenciosa de qual ocorrência apresentar.

Ausentes por construção, verificado sobre o **código executável** (AST
sem literais de string): score, rank, relevance, top-k, embedding,
vector, similarity, popularity, recency, trust, weight.

---

## 9. Somente leitura

```text
MEMORY_RETRIEVAL_PERSISTENCE = TRANSIENT
NEW_PERSISTENT_ENTITY = NO   MIGRATION_REQUIRED = NO
DATABASE_WRITES_DURING_RETRIEVAL = 0
```

Sem `commit()`, `flush()` ou `session.add()`. Sem tabela de retrieval,
saved search, cache persistente, query history, view materializada,
índice vetorial, transcript, log cognitivo, evento causal, experiência
validada, policy, domínio ou membership.

Provado por listener de cursor contra PostgreSQL, nos dois caminhos
(autorizado e negado), com verificação adicional de que a sessão fica sem
`new`, `dirty` ou `deleted`.

Erro de busca **não** vira lista vazia: a exceção sobe. Erro de busca não
é aprendizado; resultado vazio não é experiência validada.

---

## 10. Erro novo

`PIA-8033 RETRIEVAL_DUPLICATE_COID`, categoria `SYSTEM`. Confirmado como
próximo código **global** livre por varredura dos dois catálogos (E4.5
ocupou `PIA-8032`). É realmente levantado e tem testes — não é reserva
preventiva. Próximo livre: `PIA-8034`.

---

## 11. Testes — contagens coletadas

| Arquivo | Testes |
|---|---|
| `tests/unit/memory/test_retrieval.py` | **84** |
| `tests/integration/memory/test_retrieval_integration.py` | **16** |
| **Total E4.6** | **100** |

### Classificação honesta

A E4.6 não existia na cadeia 50. Executei os dois arquivos contra ela:
**a coleta falha inteira**, com
`ModuleNotFoundError: No module named 'app.memory.ports.retrieval'`.

```text
FALHAM POR DEFEITO CORRIGIDO ........................ 0
FALHAM APENAS PORQUE O MÓDULO NÃO EXISTIA ........... 100
```

Nenhum teste é apresentado como provador de defeito, porque nenhum o é.

Por **inspeção** — não por execução, já que a coleta não chega a rodar —
cinco são guardas de regressão cujas asserções não tocam código da E4.6 e
passariam nos dois lados se o módulo existisse: G17 (`r37`), drift de
schema (`ri23`), migration head (`ri24`), ausência de tabela nova
(`ri25`) e vocabulário de governança intocado (`r38d`). Registro a
diferença entre inspeção e execução em vez de apresentar as duas como
equivalentes.

### Três defeitos meus, corrigidos

**(a)** O helper de resolução montava proveniência de policy parcial;
o invariante tudo-ou-nada da E4.3.2 corretamente recusa — `policy_id`
faz parte da identidade.

**(b)** Assumi `trace_id` como campo de `CognitiveObject` e `publish()`
como método do repositório de policy. Nenhum dos dois existe:
`trace_id` vive em `ProvenanceRecord` (a Search casa por junção) e o
método é `add_policy()`. Corrigi inspecionando, não adivinhando.

**(c)** O extrator de código executável removia apenas a **primeira**
string de cada bloco, deixando passar as "docstrings de atributo" —
string solta após uma constante de módulo. Uma delas contém
`FILTERED OUT != DELETED`, e o teste de ausência de escrita acusou
`DELETE`. Passou a remover toda expressão que seja só literal de string:
elas documentam sem executar nada.

E uma remoção: `admissible_accessibility_tokens()` ficou sem chamador —
código morto por antecipação, revelado pela exigência de 100% e
**removido**, não testado para existir. Mesmo padrão da E4.3.

---

## 12. Limitações declaradas

- O escopo de domínios é materializado por consulta por domínio (§5).
- Não há total contextual, apenas `has_more` (§7).
- A conformidade estrutural é verificada por `isinstance`, que para
  protocolos de dados checa presença de membros, não tipos; a checagem
  de tipos é do mypy.
- A E4.6 depende da forma dos campos da E3, não de seus tipos nominais —
  renomear um campo quebra aqui.

---

## 13. Resultados

```text
FULL_SUITE = 1738 passed / 1 skipped / 0 failed   (baseline: 1638)
RAW_SUITE  = 1499 passed / 240 skipped / 0 failed

E3 = 598/598   E3.4.2/.1 = 134/134   E4.1 = 40/40   E4.2 = 42/42
E4.3 = 108/108 E4.4 = 74/74          E4.5 = 187/187    (todos delta 0)
E4.6 = 100 passed

GLOBAL_COVERAGE = 98,96%   (baseline 98,91% — não decresceu)
APP_COGNITIVE_COVERAGE = 100%    APP_MEMORY_COVERAGE = 100%
RUFF = PASS   BLACK = PASS
MYPY_TOTAL_ERRORS = 7 (idênticos à baseline)   MYPY_NEW_ERRORS = 0
git diff --check = limpo   SCHEMA_ORM_DRIFT = 0
MIGRATION_HEAD = 4ca61776b982 (inalterada, single-head)
DATABASE_WRITES_DURING_RETRIEVAL = 0
PostgreSQL 16.14 real
```

Trees protegidos byte a byte:
`backend/app/cognitive = be407b46f679a009e0f7f7e9f01fb784f08dea54`,
`backend/alembic = f01a1f812eb11695b9daeb6b1707e6477e9330fa`.

### Escopo

Produção (5): `ports/retrieval.py`, `ports/__init__.py`,
`schemas/retrieval.py`, `services/retrieval_manager.py`, mais
`errors/codes.py` e `errors/exceptions.py` (só o `PIA-8033`).
Testes (2). Doc (1). Nenhum repository, model ORM, tabela, coluna, enum
ou migração.

---

## 14. Stop Conditions

```text
STOP_CONDITIONS = NONE
```

Nenhuma das 16 do §20 ocorreu. Em particular: baseline conferiu
integralmente; E3 e Alembic intactos; nenhuma semântica congelada de
E4.1–E4.5 alterada; nenhum import de `app.cognitive` em produção da E4;
G17 preservado; a composição tipada com a Search E3.8 foi possível **sem**
reflexão e **sem** `Any`; nenhum SQL paralelo substituindo a Search;
paginação correta após os filtros contextuais; nenhuma tabela, coluna,
migração ou entidade persistente; nenhuma dependência de E4.7 ou E4.8;
nenhum score, vector DB ou ranking; nenhum documento congelado corrigido
em silêncio; nenhum enum da E3 ampliado; nenhuma regressão; PostgreSQL
real disponível e todos os gates executados.

---

## 15. Gate

```text
E4_6_IMPLEMENTATION = COMPLETE
E4_6_FINAL_STATUS   = AWAITING_INDEPENDENT_AUDIT
PATCH_CHAIN = 51

E4_7_IMPLEMENTATION = NOT_STARTED
READY_FOR_E4_7      = FALSE
```

O implementador não declara `PASS FINAL`. E4.7 não é iniciada.

---

## 16. Corretivo E4.6.1 — Retrieval Authority & Contract Fidelity

**Patch 52.** A auditoria devolveu cinco defeitos, todos reproduzidos
contra a cadeia 51 antes de qualquer correção.

| Defeito | Reprodução contra a cadeia 51 |
|---|---|
| **A** — autorização de outra operação | pedido `READ`, resolução `operation=TRANSFORM` → `SEARCH_CALLS=1`, `EXECUTION_AUTHORIZED=True` |
| **B** — resolução de outra policy | pedido `"requested-policy"`, resolução `"other-policy"` → Search executada |
| **C** — substituição de contexto | `validate()` devolveu outro ator/propósito → vista construída sobre a perspectiva substituída |
| **D** — violação da porta vira vista vazia | `accessibility=123`, `deleted_at="yesterday"`, token desconhecido → `search_executed=True, items=()` |
| **E** — value object incoerente | construtor aceitou `operation=TRANSFORM` com `len(items)=2 > limit=1`, e `revision_status="garbage"` |

### Causa raiz

Quatro fronteiras sem pós-condição:

```text
REQUEST ↔ VALIDATED CONTEXT
REQUEST ↔ GOVERNANCE RESOLUTION
SEARCH PORT ↔ COGNITIVE OBJECT VIEW
RESULT PAGE ↔ PAGINATION CONTRACT
```

O erro comum é meu e é um só: **`execution_authorized` não diz qual
operação nem qual policy produziram a autorização.** Eu tratei o
booleano como se fosse a decisão inteira. E, no lado da porta, filtrei o
hit antes de validar sua forma — o que transforma dado malformado em
ausência legítima.

```text
AUTHORIZATION TO TRANSFORM != AUTHORIZATION TO READ
REQUESTED POLICY           != RESOLVED POLICY
CONTEXT VALIDATION         != CONTEXT SUBSTITUTION
PORT CONTRACT VIOLATION    != EMPTY VIEW
MALFORMED EVIDENCE         != NO MATCH
```

### Correções

**Fidelidade pedido↔resolução.** Antes de memberships e Search: a
resolução tem de ser `GovernanceResolution`, sobre `READ`, sobre a mesma
operação do descritor e — quando carregar identidade de policy — sobre a
policy solicitada. Comparação exata, sem normalizar nomes. Todos os
motivos acumulados.

A identidade de policy só é exigida quando a resolução a carrega:
`PROHIBITED` nunca tem proveniência local (a fronteira decide antes de a
policy ser consultada) e `NOT_APPLICABLE` pode não tê-la quando nenhuma
versão vigente existe. Exigi-la nesses casos recusaria recusas legítimas
— há teste para os dois.

**Fidelidade do contexto.** Tipo inválido agora produz `TypeError`, não
`AttributeError` lá adiante. `validate()` devolvendo contexto diferente é
`PIA-8034` **antes** da governança. E, mesmo quando devolve objeto
estruturalmente igual, quem segue é o **objeto original do pedido**:

```text
VALIDATOR CONFIRMS
VALIDATOR DOES NOT REWRITE
```

**Validação dos hits.** Cada candidato é validado **antes** de qualquer
filtro, contra o contrato completo e contra os vocabulários fechados da
E3 (`active/latent/inaccessible/causally_extinct` e
`None/current/superseded`). Token desconhecido é violação, não objeto a
excluir: excluí-lo em silêncio esconderia que a E3 mudou o vocabulário
sob os pés da E4.6. Retorno não iterável também é violação. Nada é
normalizado.

**Invariantes do value object.** `RetrievedMemoryItem` restringe
`revision_status` ao vocabulário. `MemoryRetrievalResult` passa a exigir
`operation is READ`, `limit <= MAX_LIMIT`, `len(items) <= limit` e —
para página parcial — `has_more is False`, já que o coletor canônico
preencheria a página antes de declarar que há mais.

**Centralização.** `DEFAULT_LIMIT` e `MAX_LIMIT` migraram para
`schemas/retrieval.py` e o manager importa de lá. Duas cópias da mesma
constante divergiriam — a lição da E4.5.1 sobre duas implementações da
mesma regra. Sem ciclo: a dependência já apontava nessa direção.

`PIA-8034 RetrievalContractViolationError`, categoria `SYSTEM`, próximo
código global livre. `PIA-8033` continua significando **exclusivamente**
COID duplicado, com teste que o confirma. Próximo livre: `PIA-8035`.

### Ordem corrigida

```text
1. validar context, descriptor e paginação
2. ContextManager.validate()
3. confirmar que o contexto não foi substituído
4. GovernanceManager.resolve()
5. fidelidade pedido ↔ resolução
6. se não autorizado: recusa
7. escopo de domínio
8. Search
9. validar cada hit
10. filtrar e paginar
11. construir resultado
```

Nenhum `ValueError` cru do value object escapa pelo caminho canônico: o
manager detecta a divergência antes e a converte em `PIA-8034`.

### Testes

| Arquivo | Cadeia 51 | Cadeia 52 | Δ |
|---|---|---|---|
| `tests/unit/memory/test_retrieval.py` | 84 | **128** | +44 |
| `tests/integration/memory/test_retrieval_integration.py` | 16 | **25** | +9 |
| **Total** | **100** | **153** | **+53** |

Classificação **obtida por execução** contra a cadeia 51 (com os
símbolos novos substituídos por stubs, senão o módulo nem coleta):

```text
FALHAM NA 51, PASSAM NA 52 ......... 34 unitários + 8 integração = 42
PASSAM NOS DOIS LADOS (guardas) .... 10 unitários + 1 integração = 11
```

Os 11 guardas verificam comportamento que já existia — recusas sem
Search, vocabulário aceito, composição real intacta — e agora ficam
travados contra regressão.

### Efeito colateral legítimo

O corretivo quebrou testes da E4.6 que **já eram incoerentes**: os dublês
fixavam `policy_key="pk"` enquanto o pedido ia sem policy — exatamente o
defeito B, escrito no harness. O dublê de governança passou a **ecoar** a
policy solicitada, como o `GovernanceManager` real faz, e um wrapper
`_executar()` concentra a policy padrão. Nenhum teste foi removido ou
enfraquecido; o que mudou foi o harness parar de simular a violação.

### Três defeitos meus, no processo

**(a)** Um passe de substituição em massa apagou a linha
`policy_key=_POLICY_KEY,` de dentro do próprio helper — o texto era
idêntico ao das injeções que eu removia — deixando proveniência parcial.

**(b)** Um regex trocou `manager.retrieve(` por `_executar(manager, `
inclusive **dentro** do próprio `_executar`, produzindo recursão
infinita.

**(c)** Dois testes novos desempacotavam 4 valores de `_manager()`, que
devolve 5, e um passava `context=None` — que o wrapper substitui pelo
default, impedindo o caso de chegar ao manager.

Todos apareceram na execução, não na revisão. Registro porque um relatório
que só mostra o resultado final esconde onde o processo é frágil.

### Divergência registrada

O `PATCH_SHA256` declarado no §1 deste prompt tem **63** dígitos
hexadecimais (`3105a81f…216da5`) — está truncado em um caractere. O valor
real do patch 51 é `3105a81f…216da5e2`. O prefixo confere integralmente e
o `BUNDLE_SHA256` está correto, então a baseline foi validada; registro
em vez de corrigir em silêncio.

### Resultados

```text
FULL_SUITE = 1791 passed / 1 skipped / 0 failed   (candidata: 1738)
RAW_SUITE  = 1543 passed / 249 skipped / 0 failed

E3 = 598/598   E3.4.2/.1 = 134/134   E4.1 = 40/40   E4.2 = 42/42
E4.3 = 108/108 E4.4 = 74/74          E4.5 = 187/187    (todos delta 0)
E4.6 + E4.6.1 = 153 passed

GLOBAL_COVERAGE = 98,98%   (candidata 98,96% — não reduziu)
APP_COGNITIVE_COVERAGE = 100%    APP_MEMORY_COVERAGE = 100%
RUFF = PASS   BLACK = PASS   MYPY_NEW_ERRORS = 0
SCHEMA_ORM_DRIFT = 0   MIGRATION_HEAD = 4ca61776b982
DATABASE_WRITES_DURING_RETRIEVAL = 0
```

```text
E4_6_1_IMPLEMENTATION = COMPLETE
E4_6_FINAL_STATUS     = AWAITING_INDEPENDENT_AUDIT
PATCH_CHAIN = 52
E4_7_IMPLEMENTATION = NOT_STARTED
READY_FOR_E4_7 = FALSE
```

---

## 17. Corretivo E4.6.2 — Search Sequence & No-Reflection Contract

**Patch 53.** Duas lacunas remanescentes da E4.6.1, ambas reproduzidas
contra a cadeia 52 antes de qualquer correção.

### Defeito F — contrato de retorno subvalidado

`CognitiveSearchPort` declara `Sequence`, mas o coletor aceitava
qualquer iterável:

```text
GENERATOR_ACCEPTED = TRUE
SET_ACCEPTED = TRUE
DICT_ACCEPTED = TRUE
CANONICAL_ORDER_PRESERVED = FALSE   (com 30 objetos)
```

Com 4 objetos a ordem coincidiu por acaso; com 30 a divergência
apareceu. Registro os dois resultados porque a reprodução com poucos
elementos **não** demonstra o defeito — é o tipo de verificação que
passa por sorte.

`Sequence` não é detalhe formal:

```text
SEQUENCE             != ARBITRARY ITERABLE
UNORDERED COLLECTION != DETERMINISTIC SEARCH RESULT
```

Uma `Sequence` tem **ordem**, e a ordem da Search da E3 é o contrato
determinístico do qual a paginação da E4.6 depende. Um `set` entrega os
mesmos objetos numa ordem que ninguém definiu; um generator não é
reposicionável.

**Por que não converter nem ordenar.** `list(bruto)` faria um generator
parecer válido, e `sorted(...)` de um `set` fabricaria uma ordem que a
Search não produziu — a E4.6 estaria escondendo o defeito da porta em
vez de reportá-lo, e apresentaria como "ordem oficial" algo que inventou.
A E4.6 **preserva** a ordem oficial; não fabrica outra. Há teste de
ausência estrutural verificando que o coletor não constrói `list(bruto)`
nem ordena.

`str` e `bytes` continuam inválidos, embora implementem `Sequence`: são
sequências de caracteres, não de objetos cognitivos.

### Defeito G — reflexão contrária ao contrato

`_coletar` usava `hasattr`; `_validar_hit` usava `hasattr` **e**
`getattr`. E `app/memory/ports/retrieval.py` declara, na própria
docstring, "nenhum `getattr`, nenhuma reflexão".

**A documentação e o código executável se contradiziam — e a
contradição era minha, com uma docstring escrita para justificá-la.** A
E4.6.1 acrescentou um parágrafo explicando por que o `getattr` seria
aceitável ali. Não era: o contrato já dizia o contrário, e um comentário
não revoga um contrato.

A validação passou a ler os seis campos por **acesso tipado direto**,
dentro de um `try/except AttributeError` convertido em `PIA-8034`. Sem
`Any`, `cast`, `type: ignore`, `vars`, `__dict__`, `inspect`, `getattr`
ou `hasattr` — verificado por inspeção AST do código executável dos dois
métodos, com as docstrings removidas (elas citam nominalmente o que o
módulo não faz).

**Custo declarado.** `AttributeError` interrompe na **primeira**
ausência, então um hit sem vários campos passa a reportar um motivo em
vez de todos. Campos **presentes** e malformados continuam acumulando
motivos. Entre reportar menos e violar o contrato que a própria porta
declara, reporta-se menos — e o teste da E4.6.1 que asserava três
motivos foi ajustado para refletir isso, não removido.

### Diagnóstico

Apenas `PIA-8034`. Nenhum código novo. `PIA-8033` continua exclusivo de
COID duplicado, com teste que o confirma.

### Testes

| Arquivo | Cadeia 52 | Cadeia 53 | Δ |
|---|---|---|---|
| `tests/unit/memory/test_retrieval.py` | 128 | **152** | +24 |
| `tests/integration/memory/test_retrieval_integration.py` | 25 | **31** | +6 |
| **Total** | **153** | **183** | **+30** |

Classificação **obtida por execução** contra a cadeia 52:

```text
FALHAM NA 52, PASSAM NA 53 ......... 8 unitários + 4 integração = 12
PASSAM NOS DOIS LADOS (guardas) .... 16 unitários + 2 integração = 18
```

Nenhuma falha por símbolo novo ou erro de coleta: os arquivos coletam
integralmente na cadeia 52, porque o corretivo não introduziu nome
público novo — só endureceu comportamento. Os 18 guardas verificam o que
já funcionava (list/tuple aceitos, tipos e tokens diagnosticados, ordem
oficial preservada, composição real intacta) e agora ficam travados
contra regressão.

Dois testes da E4.6.1 foram **ajustados**, não removidos: um asserava
três motivos para atributos ausentes (agora um, pelo custo declarado
acima) e outro asserava a mensagem "não é uma coleção", que passou a
dizer "não é uma `Sequence`" — o contrato é mais estrito que "iterável".

### Contradição documental corrigida

A seção 2 deste documento continha o parágrafo da E4.6.1 que justificava
o `getattr`. Foi removido no mesmo patch: documentação que descreve
comportamento inexistente é pior que documentação ausente.

### Resultados

```text
FULL_SUITE = 1821 passed / 1 skipped / 0 failed   (candidata: 1791)
RAW_SUITE  = 1567 passed / 255 skipped / 0 failed

E3 = 598/598   E3.4.2/.1 = 134/134   E4.1 = 40/40   E4.2 = 42/42
E4.3 = 108/108 E4.4 = 74/74          E4.5 = 187/187    (todos delta 0)
E4.6 + .1 + .2 = 183 passed

GLOBAL_COVERAGE = 98,98%   (não reduziu)
APP_COGNITIVE_COVERAGE = 100%    APP_MEMORY_COVERAGE = 100%
RUFF = PASS   BLACK = PASS   MYPY_NEW_ERRORS = 0
SCHEMA_ORM_DRIFT = 0   MIGRATION_HEAD = 4ca61776b982
DATABASE_WRITES_DURING_RETRIEVAL = 0
```

Stop Condition 1 verificada explicitamente: o `SearchEngine` real
devolve `list`, que **é** `Sequence` — a correção não o exclui, e há
teste de integração que confere isso contra o banco.

```text
E4_6_2_IMPLEMENTATION = COMPLETE
E4_6_FINAL_STATUS     = AWAITING_INDEPENDENT_AUDIT
PATCH_CHAIN = 53
E4_7_IMPLEMENTATION = NOT_STARTED
READY_FOR_E4_7 = FALSE
```
