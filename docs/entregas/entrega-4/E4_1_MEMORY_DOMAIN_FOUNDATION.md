# E4_1_MEMORY_DOMAIN_FOUNDATION

**Módulo:** E4.1 — Memory Domain Foundation
**Baseline:** E3 FROZEN · E4.0 / E4.0.1 PASS FINAL · patch chain 37
**Patch:** `e4-1-memory-domain-foundation.patch` (38º)

---

## 1. Missão

Implementar a fundação persistente de `MemoryDomain` — segmentação
lógica do patrimônio cognitivo.

```
DOMAIN MEMBERSHIP != COGNITIVE EXISTENCE

COID → {D1, D2, ..., Dn}
one COID remains one CognitiveObject
```

`MemoryDomain` **não é**: pasta de filesystem, container de storage,
`CognitiveObject`, CLID, contexto, policy, ACL, sessão, índice de
busca.

---

## 2. Pre-implementation findings

Três achados da inspeção obrigatória (§3) que moldaram o desenho.

### 2.1 O teste G17 da E3.12 proíbe importar `app.cognitive` fora dele

`tests/integration/cognitive/test_e3_12_final_integration_gate.py`,
teste `test_g17_cout_is_not_a_decision_engine`, varre
`backend/app/**/*.py` ignorando caminhos que contêm `cognitive` e
exige:

```python
assert externos == [], "kernel/runtime passou a depender do domínio cognitivo"
```

Consequência direta: **`app/memory/` não pode importar `app.cognitive`
em nenhuma linha**, sob pena de quebrar um teste da E3 já congelado —
o que seria `E3_REGRESSION_DELTA != 0`.

Isso poderia parecer um obstáculo. Não é: é a restrição que torna a
fronteira E3/E4 **estrutural em vez de documental**, e ela é
satisfazível sem concessão alguma:

- a FK `memberships.coid → cognitive_objects.id` é declarada por
  **string** (`ForeignKey("cognitive_objects.id")`), resolvida pelo
  `MetaData` compartilhado — nenhum import Python é necessário;
- a API do módulo recebe `coid: uuid.UUID`, **nunca** um
  `CognitiveObject` — E4.1 referencia COID, não manipula patrimônio.

`app/memory/` foi escrito com **zero** imports de `app.cognitive`.
Isso é verificado por teste próprio (`MD6`), e não apenas afirmado.

### 2.2 `alembic/env.py` é o único ponto de registro de modelos

`alembic/env.py` já importa `app.cognitive.models` para participar do
`autogenerate`. É o **único** arquivo que o faz — e vive em
`alembic/`, fora de `app/`, portanto fora do alcance de G17.

E4.1 acrescenta uma linha análoga (`import app.memory.models`). Este é
o único arquivo pré-existente tocado por este módulo, e a §40 do
prompt canônico antecipa exatamente esse caso. Ele é **infraestrutura
E1/E2 (Módulo 2.1)**, não código de domínio da E3:

```
E3_COGNITIVE_FILES_MODIFIED = NONE
SHARED_INFRA_FILES_MODIFIED = alembic/env.py (1 linha de import)
```

### 2.3 O `BaseModel` do projeto já resolve a identidade de membership

`BaseModel = Base + UUIDMixin + TimestampMixin` fornece `id` (UUID),
`created_at` e `updated_at`. Seguir a convenção dá identidade própria
à associação **sem custo e sem decisão nova** — ver Q10/Q11.

---

## 3. As 23 perguntas obrigatórias (§4)

**1. `MemoryDomain` precisa ser persistente?**
Sim. É estado E4 genuinamente novo: nenhuma tabela da E3 responde "a
que recorte este objeto pertence". Admitido pela regra do
`E4_PRIMITIVE_OWNERSHIP.md` §1.

**2. Precisa de identidade própria?**
Sim. É entidade nomeável, referenciável e de vida longa.
`domain_id != COID` — ver Q3 e §6 do prompt.

**3. Qual tipo de identidade segue as convenções reais?**
`UUID` primário via `UUIDMixin`, como toda entidade do projeto. Herda
`BaseModel`, exatamente como `CognitiveObject` faz. Nenhuma hierarquia
declarativa paralela.

**4. O nome é identidade ou atributo?**
**Atributo.** `domain_id` é a identidade; `name` é legível por humano.
Logo `rename != new domain` — mas rename **não é implementado** aqui
(ver Q15).

**5. Nomes duplicados são permitidos?**
Sim, por ausência de contrato em contrário. Nada no freeze da E4
estabelece unicidade de nome, e `same name = same domain` é
explicitamente uma inferência proibida.

**6. Existe escopo congelado para unicidade de nome?**
**Não.** Portanto `UNIQUE(name)` **não** é criado (§7/§28). Inventar
unicidade de nome seria decidir por quem organiza o patrimônio.

**7. Hierarquia parent/child agora?**
**Não.** `DOMAIN_HIERARCHY = DEFERRED`. Nenhum `parent_domain_id`,
`path`, árvore ou membership recursiva. `MEMORY_DOMAIN != FILESYSTEM_FOLDER`.

**8. `owner` agora?**
**Não.** Owner é autoridade, e autoridade é E4.3 (Governance).
`DOMAIN_OWNER = DEFERRED`.

**9. `policy_ref` agora?**
**Não.** `DOMAIN_POLICY = DEFERRED` — E4.3.

**10. Membership precisa de identidade própria?**
Sim — e sai de graça pela convenção (`BaseModel.id`). Registrada com o
desvio explicado em §4.2.

**11. `(domain_id, coid)` é suficiente como identidade estrutural?**
Sim. É a **chave estrutural** e recebe `UNIQUE` no banco. O `id`
próprio é identidade de registro (convenção); a unicidade lógica é o
par.

**12. Membership precisa de lifecycle agora?**
**Não** — ver §4.2. Sem `left_at`, sem `retired_at`, sem soft delete.

**13. Remoção de membership pertence a E4.1?**
**Não.** Remover é operação sob autoridade, e autoridade é E4.3.
`MEMBERSHIP_REMOVAL = DEFERRED`.

**14. Domain deletion pertence a E4.1?**
**Não.** `DOMAIN_DELETION = DEFERRED`. Não se cria operação destrutiva
só para completar CRUD (§19).

**15. Domain rename pertence a E4.1?**
**Não.** `DOMAIN_RENAME = DEFERRED`. O princípio `rename != new domain`
fica congelado; o mecanismo espera contrato.

**16. Membership modifica `AccessibilityState`?**
**Não.** `DOMAIN MEMBERSHIP != ACCESSIBILITY`. Testado (MM10, COUT4).

**17. Membership modifica CLID?**
**Não.** Testado (MM9).

**18. Membership modifica Provenance?**
**Não** — e nenhum `ProvenanceRecord` é criado. Classificação
administrativa não é evento de origem cognitiva (§17). Testado (MM11).

**19. Membership gera `CausalHistoryEvent`?**
**Não.** Organização lógica não é causalidade cognitiva (§18). Testado
(MM12).

**20. `MemoryDomain` entra no E3 Synchronization agora?**
**Não.** `MEMORY_DOMAIN_SYNC = DEFERRED`. O `E4_SYNC_BOUNDARY.md`
deixou a portabilidade **em aberto**, e decidi-la aqui seria
antecipar política. `SECTION_BY_TABLE` da E3 permanece com sete
seções, intocado.

**21. A portabilidade de `MemoryDomain` já está congelada?**
**Não.** Continua `OPEN → E4.1` no freeze; esta entrega a mantém
aberta em vez de resolvê-la por conveniência, porque o critério
decisivo registrado no freeze — *se `MemoryDomain` carregar semântica
de acesso, é LOCAL* — só pode ser avaliado depois que E4.3 existir.

**22. Algum campo arbitrário de metadata é necessário?**
**Não.** `ARBITRARY_METADATA_DICT = NOT_AUTHORIZED` desde E3.6.2, e
seria a via lateral mais fácil de violar `TRANSCRIPT_AUTO_STORAGE =
NONE`.

**23. Alguma necessidade exige alterar E3?**
**Não.** Zero arquivos de `app/cognitive/` modificados; zero migrações
publicadas editadas. Único arquivo pré-existente tocado:
`alembic/env.py` (§2.2).

---

## 4. Contrato congelado

### 4.1 `MemoryDomain`

```
MemoryDomain(BaseModel)
    id          UUID   PK      ← domain_id, via UUIDMixin
    name        str(255)       ← atributo, NÃO identidade, NÃO único
    created_at  datetime       ← TimestampMixin
    updated_at  datetime       ← TimestampMixin
```

**MINIMAL DOMAIN CONTRACT.** Nada além disso. Em particular, campos
deliberadamente **ausentes**: `description`, `metadata`,
`arbitrary_json`, `embedding`, `owner`, `acl`, `provider`, `model`,
`policy_ref`, qualquer `*_score`, `path`, `filesystem_location`,
`parent_domain_id`.

`description` merece nota: o `E4_DOMAIN_MODEL_DRAFT.md` a listava como
opcional, mas aquele documento declara seus campos "ilustrativos", e o
§5 deste prompt exige necessidade **demonstrada**. Nenhuma operação de
E4.1 a consome. Fora.

### 4.2 `MemoryDomainMembership`

```
MemoryDomainMembership(BaseModel)
    id          UUID  PK       ← convenção do projeto
    domain_id   UUID  FK → memory_domains.id
    coid        UUID  FK → cognitive_objects.id
    created_at / updated_at

    UNIQUE(domain_id, coid)    ← identidade estrutural, DB-level
```

**Desvio consciente da recomendação da E4.0, registrado.** O
`E4_PRIMITIVE_OWNERSHIP.md` §5 recomendava identidade própria **com
`joined_at`/`left_at`**, por analogia a `Relationship.retired_at`
(`RETIRE != DELETE_HISTORY`).

A identidade própria foi adotada. O **lifecycle não**, e a razão é que
a analogia se rompe num ponto: `retired_at` existe na E3 porque existe
uma operação `retire()` que o escreve. Aqui, a remoção de membership
está deferida (Q13) — uma coluna `left_at` que nenhum código escreve
não preserva história nenhuma; ela apenas **promete** preservação que
o módulo não entrega, e engorda o contrato mínimo com especulação.

Quando E4.x implementar remoção sob autoridade, o lifecycle entra
junto, com o escritor que lhe dá sentido. Registrado em
`E4_DEFERRED_INVENTORY.md`.

### 4.3 Nenhuma cópia

A membership **não copia** nada do `CognitiveObject`: sem nome, sem
conteúdo, sem CLID, sem `accessibility`, sem `revision_status`, sem
proveniência, sem relações, sem história causal. Só o par de
referências.

```
E3  = source of truth for CognitiveObject and cognitive patrimony
E4.1 = source of truth only for MemoryDomain and Domain↔COID membership
```

---

## 5. Camadas

```
app/memory/
    models/      memory_domain.py, memory_domain_membership.py
    errors/      codes.py, exceptions.py
    repositories/ memory_domain_repository.py
                  memory_domain_membership_repository.py
    services/    memory_domain_manager.py
```

Pacote **novo e irmão** de `app/cognitive/` — não um subpacote dele. A
fronteira é estrutural: zero imports de `app.cognitive`.

### 5.1 Repositórios

`MemoryDomainRepository`: `add_domain`, `get_by_id`, `list` (herdados
e/ou finos sobre `BaseRepository`).

`MemoryDomainMembershipRepository`: `add_membership`, `contains`,
`list_objects_in_domain`, `list_domains_for_object` — todos com
ordenação determinística canônica (`created_at ASC, id ASC`).

### 5.2 Ordem de checagem em `add_membership`

Decisão de desenho que resolve uma ambiguidade real: `domain_id` e
`coid` são **duas** FKs, e uma violação `23503` sozinha não diz qual
delas falhou — a mesma limitação que E3.3 documentou e aceitou.

Aqui ela é **eliminável**, e sem importar `app.cognitive`:

1. pré-checagem de existência do domínio (tabela própria) →
   `MemoryDomainNotFoundError` (`PIA-8023`);
2. tentativa de escrita;
3. `23505` → `MemoryDomainMembershipDuplicateError` (`PIA-8024`);
4. `23503` restante → só pode ser o `coid` →
   `MemoryDomainMembershipObjectNotFoundError` (`PIA-8025`).

A pré-checagem é para **diagnóstico**, não para correção: a FK do
banco continua sendo a autoridade final, e a corrida entre passo 1 e
passo 2 termina em `23503` corretamente classificado — não em dado
inconsistente.

### 5.3 `MemoryDomainManager`

Existe porque acrescenta invariante além do repositório: a ordem de
checagem de §5.2 e a garantia de que nenhuma operação toca patrimônio.
Expõe `create_domain`, `add_object`, `list_members`,
`list_domains_for_object`.

Não contém Governance, não contém Context, não contém Retrieval.

---

## 6. Error codes

Catálogo próprio em `app/memory/errors/codes.py` — o catálogo da E3
está congelado e **não** foi tocado. A sequência `PIA-8xxx` continua
de onde parou, sem colisão:

| Código | Nome | Quando |
|---|---|---|
| `PIA-8023` | `MEMORY_DOMAIN_NOT_FOUND` | `domain_id` inexistente |
| `PIA-8024` | `MEMORY_DOMAIN_MEMBERSHIP_DUPLICATE` | par `(domain_id, coid)` repetido |
| `PIA-8025` | `MEMORY_DOMAIN_MEMBERSHIP_OBJECT_NOT_FOUND` | `coid` inexistente |

Próximo livre: **`PIA-8026`**.

"Objeto com zero domínios" **não** é exceção — é resultado válido, e
retorna lista vazia (§35).

---

## 7. Migração

`memory_domains` e `memory_domain_memberships`, revisão sucessora de
`c9a3f61b74d2`.

```
MIGRATION_REVERSIBILITY = CONDITIONALLY_REVERSIBLE
DOWNGRADE_GUARD         = EMBEDDED (desde a migração inicial)
```

A guarda nasce **dentro** da própria migração, como em E3.9 — e não
como migração-guarda separada, que na E3.5/E3.6 só foi necessária
porque a original já estava publicada. A dívida não se repete.

Com as tabelas vazias, o downgrade é permitido. Com qualquer domínio
ou membership registrado, é **bloqueado antes de qualquer alteração
estrutural**: a organização do patrimônio é trabalho humano que
nenhum outro lugar preserva.

```
HISTORICAL_PRESERVATION > DOWNGRADE_CONVENIENCE
```

### 7.1 FK sem CASCADE

Nenhuma FK usa `ON DELETE CASCADE`, seguindo a política da E3
(`LineageEdge`, `Relationship`): `CognitiveObject` usa soft delete e
nunca é fisicamente removido em fluxo normal.

```
DOMAIN DELETE MUST NOT CASCADE TO COGNITIVE PATRIMONY
```

Como `DOMAIN_DELETION` está deferida, não existe caminho para apagar
domínio; e mesmo que existisse, apagar organização jamais poderia
apagar patrimônio.

---

## 8. Princípios congelados por este módulo

```
DOMAIN MEMBERSHIP != COGNITIVE EXISTENCE
DOMAIN BOUNDARY   != COGNITIVE BOUNDARY
DOMAIN CLASSIFICATION MUST NOT COLLAPSE COGNITIVE IDENTITY

DOMAIN MEMBERSHIP != ACCESSIBILITY      (E4.7)
DOMAIN MEMBERSHIP != GOVERNANCE         (E4.3)
DOMAIN MEMBERSHIP != CONTEXT            (E4.2)
DOMAIN MEMBERSHIP != PERSISTENCE        (E4.4)
DOMAIN MEMBERSHIP != RELEVANCE
DOMAIN            != FILESYSTEM FOLDER

ZERO DOMAIN MEMBERSHIP != NONEXISTENCE
ONE COID CAN BELONG TO MULTIPLE DOMAINS WITHOUT DUPLICATION
CO-MEMBERSHIP CREATES NO COGNITIVE RELATION
DOMAIN CLASSIFICATION != CAUSAL RESURRECTION
```

O último merece ênfase: adicionar um objeto `CAUSALLY_EXTINCT` a um
domínio **não** o traz de volta a `ACTIVE`. Membership organiza; não
ressuscita distinção extinta (Broken Glass). Testado em `COUT4`.

---

## 9. Testes

| Grupo | Onde | Quantidade |
|---|---|---|
| MD1–MD10, MM1–MM16 | `tests/unit/memory/test_memory_domain_foundation.py` | 29 |
| DB1–DB5, CC1, COUT1–COUT5 | `tests/integration/memory/test_memory_domain_integration.py` | 11 |

### 9.1 O gate central — `COUT1`

Censo canônico das **sete** tabelas cognitivas, linha a linha e coluna
a coluna, antes e depois de criar dois domínios e registrar quatro
memberships:

```
censo_depois == censo_antes          ← patrimônio idêntico
(domínios, memberships) == (2, 4)    ← organização mudou de fato
IntegrityManager.audit() == PASS     ← organização nova não é corrupção
```

```
ORGANIZATION CHANGED
PATRIMONY DID NOT
```

Comparar por **conteúdo** e não por contagem é deliberado: contagem
provaria apenas que nada sumiu; o contrato de E4.1 é que nada **mude**.

### 9.2 Os demais gates fortes

- **`COUT2`** — mesmo COID em cinco domínios: um único
  `CognitiveObject`, mesmo CLID, linhagem e história causal intactas.
- **`COUT3`** — objeto sem domínio nenhum continua existindo e
  continua recuperável pelo Search da E3 pelas regras da E3 (domínio
  **não** é critério de busca cognitiva).
- **`COUT4`** — Broken Glass: classificar um objeto
  `CAUSALLY_EXTINCT` num domínio **não** o traz de volta a `ACTIVE`.
  `DOMAIN CLASSIFICATION != CAUSAL RESURRECTION`.
- **`COUT5`** — `SECTION_BY_TABLE` da E3 continua com as sete seções;
  nenhuma tabela de memória entrou no envelope de sincronização.
- **`CC1`** — duas sessões classificando o mesmo COID no mesmo domínio
  simultaneamente produzem **exatamente uma** membership. A unicidade
  estrutural do banco basta; nenhum lock global foi adicionado (mesma
  disciplina de E3.4.1 — inventar lock onde a constraint resolve seria
  custo sem invariante novo).
- **`DB3`** — lê o schema real, não o modelo: nenhuma FK declara
  `ON DELETE CASCADE`, e apagar um domínio com membership é recusado
  pelo banco em vez de arrastar a associação.
- **`DB4`** — ciclo `head → anterior → head` com tabelas vazias; com
  organização registrada, bloqueado e **nada alterado**.
- **`MD6`** — `app/memory/` não importa `app.cognitive` em nenhuma
  linha. O teste vive aqui, e não apenas no gate G17 da E3.12, porque
  a violação deve falhar no módulo que a introduziria.

---

## 10. Dois defeitos meus, encontrados e corrigidos

Registrados porque um módulo que silencia os próprios erros é menos
confiável, não mais.

**(a) Timestamps sem `server_default` na migração.** Escrevi
`sa.Column("created_at", sa.DateTime(timezone=True), nullable=False)`
sem `server_default=sa.func.now()`. O `TimestampMixin` do projeto
declara explicitamente que os timestamps são "mantidos pelo próprio
banco (não pela aplicação)" — e o ORM, portanto, não os envia no
`INSERT`. Nove testes de integração quebraram com
`NotNullViolation`. Corrigido nas quatro colunas.

**(b) O ramo PostgreSQL de violação de FK não estava coberto.** Os
unitários exercitavam a classificação pelo sinal do SQLite e o `DB2`
exercitava a FK por SQL direto — mas o caminho que de fato roda em
produção (violação de FK **através do repositório**, contra
PostgreSQL) nunca era executado. A exigência de 100% de cobertura
revelou a lacuna, como já havia acontecido em E3.11.1. Fechado com
`DB5`.

---

## 11. Resultados

```
TESTS
    unit memory            = 29
    integration memory     = 11
    unit cognitive         = 493   (inalterado)
    integration cognitive  = 105   (inalterado)
    TOTAL COLLECTED        = 1094

FULL_SUITE             = 1093 passed / 1 skipped / 0 failed
E3_REGRESSION_DELTA    = 0     (598/598 cognitivos verdes; gate E3.12 23/23)

GLOBAL_COVERAGE        = 98,52%
APP_MEMORY_COVERAGE    = 100%
APP_COGNITIVE_COVERAGE = 100%

RUFF = PASS   BLACK = PASS
MYPY_TOTAL_ERRORS = 7   MYPY_NEW_ERRORS = 0

ALEMBIC_SINGLE_HEAD = 3799d45ff96d
SCHEMA_ORM_DRIFT    = 0
POSTGRESQL          = 16.14

E3_COGNITIVE_FILES_MODIFIED = NONE
SHARED_INFRA_FILES_MODIFIED = alembic/env.py (1 import)
MIGRATIONS_MODIFIED         = NONE (a nova é adicionada, nenhuma publicada é editada)
```

---

## 12. Deferido por este módulo

```
DOMAIN_HIERARCHY            = DEFERRED
DOMAIN_OWNER                = DEFERRED   → E4.3
DOMAIN_POLICY               = DEFERRED   → E4.3
DOMAIN_DELETION             = DEFERRED
DOMAIN_RENAME               = DEFERRED
MEMBERSHIP_REMOVAL          = DEFERRED   → autoridade em E4.3
MEMBERSHIP_LIFECYCLE        = DEFERRED   → entra junto com a remoção
MEMORY_DOMAIN_SYNC          = DEFERRED   → portabilidade segue aberta
DOMAIN_MERGE                = DEFERRED
ARBITRARY_METADATA          = NOT_AUTHORIZED
```

Próximo error code livre: **`PIA-8026`**.
