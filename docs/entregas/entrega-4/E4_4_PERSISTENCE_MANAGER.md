# E4_4_PERSISTENCE_MANAGER

**Módulo:** E4.4 — Persistence Manager
**Baseline:** bundle `pia-os-e4-3-2-resolution-invariants.bundle`
SHA-256 `84441933…` ✓ · `git bundle verify` OK · HEAD `afb5c38c…` ✓ ·
TREE `7635198a…` ✓ · `PATCH_CHAIN = 43` ✓ · migration head
`4ca61776b982` ✓
**Patch:** `e4-4-persistence-manager.patch` (44º)

---

## 1. Missão

```
PERSISTENCE = CONTINUITY OF A DISTINCTION
              ACROSS STATES, TRANSFORMATIONS OR TIME

PERSISTENCE != STORAGE
PERSISTENCE != EXISTENCE
PERSISTENCE != ACCESSIBILITY
PERSISTENCE != RELEVANCE
```

O módulo **reúne e apresenta evidências já registradas**. Não decide
que algo merece sobreviver, não pontua, não ranqueia, não promove.

```
LOP = PERSISTENCE PRINCIPLE, NOT A METRIC
PERSISTENCE_SCORE = NONE   SURVIVAL_SCORE = NONE
GLOBAL_IMPORTANCE_SCORE = NONE   AUTOMATIC_PROMOTION = NONE
```

---

## 2. PRE-IMPLEMENTATION PLAN

### 2.1 Hipótese arquitetural confirmada

```
PersistenceManager = read-only composition over E3 primitives
NEW_PERSISTENT_ENTITY = NO   MIGRATION_REQUIRED = NO   E3_MODIFIED = NO
```

A hipótese se sustenta: as quatro fontes canônicas de continuidade
(`CLID`, `LINEAGE`, `TRANSFORMATION`, `CAUSAL HISTORY`) já existem e
já são consultáveis. Nada precisa ser criado — apenas lido e
apresentado de forma tipada.

**Nenhuma Stop Condition foi encontrada.**

### 2.2 O problema central: ler a E3 sem importá-la

O gate `G17` da E3.12 varre `backend/app/**` e proíbe qualquer import
de `app.cognitive` fora do próprio pacote. A E4.1 já enfrentou isso do
lado da **escrita** e resolveu declarando a FK por **nome de tabela**
(`ForeignKey("cognitive_objects.id")`), resolvida no `MetaData`
compartilhado.

E4.4 precisa do análogo do lado da **leitura**. A solução adotada é a
mesma técnica: descritores leves de tabela
(`sqlalchemy.table()`/`column()`) que referenciam as tabelas da E3
**por nome**, sem importar um único símbolo de `app.cognitive`.

Custo assumido e declarado: o módulo passa a conhecer nomes de tabela
e de coluna da E3. É acoplamento por **nome**, não por tipo — o mesmo
que a E4.1 já aceitou, e o mesmo que mantém a fronteira estrutural em
vez de documental. A alternativa seria importar os modelos, o que
quebraria `G17` e produziria `E3_REGRESSION_DELTA != 0`.

### 2.3 A varredura de `input_refs`/`output_refs`, e por que ela fica

`TransformationRecord.input_refs`/`output_refs` são colunas `JSON`
contendo listas de COIDs em texto. Não há FK e não há índice — a
integridade referencial desses campos está declarada
**`DEFERRED`** desde a E3 e reafirmada em
`E4_DEFERRED_INVENTORY.md`.

Consequência: descobrir "quais transformações citam este COID" exige
projetar as três colunas e filtrar em Python. É `O(n)` sobre
`transformation_records`.

**Isso não é corrigido aqui, e a decisão é deliberada.** Criar índice,
tabela auxiliar ou coluna derivada para acelerar seria exatamente as
Stop Conditions 3 e 4 — nova entidade persistente e segunda fonte da
verdade. O custo é consequência de uma decisão congelada da E3, e o
lugar de revisá-la é um corretivo da E3, não este módulo. Registrado
como limitação conhecida, não como defeito silencioso.

### 2.4 Três resultados, não dois

```
SUBJECT_NOT_FOUND
NO_RECORDED_CONTINUITY_EVIDENCE
RECORDED_CONTINUITY_EVIDENCE
```

Não podem colapsar, e cada colapso apagaria uma distinção diferente:

```
MISSING EVIDENCE != EVIDENCE OF NON-PERSISTENCE
MISSING EVIDENCE != AUTHORIZATION TO FABRICATE HISTORY
OBJECT EXISTS    != CONTINUITY IS RECORDED
```

"Não existe objeto" e "existe objeto sem continuidade registrada" são
situações que pedem providências opostas — a primeira sugere erro de
referência; a segunda é um fato legítimo sobre um objeto novo. Fundi-las
num `False` seria a mesma perda diagnóstica que a E3.12 provou não
cometer no *negative strong gate*.

### 2.5 Evidência é referência, nunca objeto

```
PersistenceEvidence
    kind          vocabulário fechado
    reference     identificador estável do fato (str de UUID)
    related_coid  o outro extremo, quando há
    qualifier     valor estável do fato (relation_type, event_type)
```

Nenhuma instância ORM atravessa o contrato público. `qualifier` guarda
o **valor** persistido (`"branch"`, `"created"`), não o membro do enum
da E3 — importá-lo quebraria `G17`, e o valor é o que é estável no
banco de qualquer modo.

**Direções preservadas:** `LINEAGE_PARENT` ≠ `LINEAGE_CHILD`,
`TRANSFORMATION_INPUT` ≠ `TRANSFORMATION_OUTPUT`. Colapsar direção
seria perder a informação que torna a linhagem uma linhagem.

**Múltiplos ramos permanecem múltiplos.** Nada escolhe "o verdadeiro":
`EQUIVALENCE != DESTRUCTIVE COLLAPSE`, `DIVERGENCE != INVALIDITY`.

### 2.6 O que **não** entra como evidência

```
DOMAIN MEMBERSHIP   CONTEXT   GOVERNANCE OUTCOME   ACCESSIBILITY STATE
POPULARITY   RECENCY   FREQUENCY   SEARCH RANK   REUSE COUNT
SUCCESS   ERROR   REPETITION   PROVIDER   MODEL   SESSION
```

**Proveniência continua sendo proveniência.** Ela responde "de onde
veio", não "atravessou o quê" — reclassificá-la como continuidade
seria o tipo de deslize silencioso que muda o significado de um
registro sem que ninguém decida isso.

`revision_status` é lido e reportado como **descrição da trajetória**,
não como evidência: ele descreve o estado presente do objeto, e a
distinção entre descrever e evidenciar é justamente o que este módulo
protege.

### 2.7 Invariantes desde o primeiro commit

Registrado na memória do projeto como padrão a não repetir — três
ocorrências (E4.2.1, E4.3.1, E4.3.2) de invariante declarado em
docstring e não imposto em código. Aqui os dois value objects nascem
com `__post_init__` canonicalizando coleções, validando tipos e
recusando estados incoerentes.

### 2.8 Independência de contexto

```
CONTEXT CHANGES VIEW
CONTEXT DOES NOT CHANGE PERSISTENCE

GOVERNANCE MAY RESTRICT ACCESS
GOVERNANCE MUST NOT REWRITE EXISTENCE
GOVERNANCE MUST NOT REWRITE PERSISTENCE
```

`assess()` recebe **apenas um COID**. Não recebe `MemoryContext`, nem
policy, nem domínio — e essa é a garantia mais forte possível de
independência: não é que o resultado ignore o contexto, é que o
contexto **não tem por onde entrar**.

### 2.9 Fronteira com E4.5

```
E4_4 != CONSOLIDATION
DO_NOT_IMPLEMENT_E4_5
```

E4.5 consumirá `PersistenceAssessment` para reconhecer evidências de
continuidade. Nada de síntese, merge, criação de objeto consolidado,
obrigatoriedade de `declared_losses` ou seleção de fontes entra aqui.
Nenhuma abstração de escrita foi criada "para preparar" E4.5 — uma
abstração sem consumidor real é especulação, e a E4.1 já registrou
essa lição com o `left_at` que não foi criado.

### 2.10 Discrepância documental reportada

O prompt lista `E4_3_2_GOVERNANCE_RESOLUTION_INVARIANTS.md` entre as
autoridades documentais. **Esse arquivo não existe**: a documentação
da E4.3.2 foi anexada como seções 8–11 de
`E4_3_1_GOVERNANCE_SAFETY_RESOLUTION.md`.

O conteúdo está presente e foi lido; apenas o caminho difere do
citado. Não é Stop Condition — nenhuma autoridade documental está
ausente — mas fica registrado para que a auditoria não procure um
arquivo inexistente.

---

## 3. Implementação

```
app/memory/schemas/persistence.py                          value objects
app/memory/repositories/continuity_evidence_repository.py  leitura por nome de tabela
app/memory/services/persistence_manager.py                 assess(coid)
```

Três arquivos de produção. **Nenhuma migração, nenhuma tabela, nenhum
arquivo de E3/E4.1/E4.2/E4.3 tocado.**

### 3.1 Superfície pública

```
PersistenceManager.assess(coid: uuid.UUID) -> PersistenceAssessment
```

E nada mais — verificado por teste (`pv12`): a superfície pública do
manager é exatamente `{"assess"}`.

### 3.2 `revision_status` é descrição, não evidência

Ele descreve o **estado presente** do objeto; evidência é o que atesta
**travessia**. Por isso aparece no resultado e **não** entra em
`evidence`: nenhuma contagem o inclui, e nenhum caminho o converte em
prova de continuidade.

## 4. Achado sobre a E3 — reproduzido, não corrigido

Um teste revelou que a E3 persiste enums com **duas convenções
diferentes**:

```
lineage_edges.relation_type        (E3.3)  values_callable → grava o .value  "branch"
causal_history_events.event_type   (E3.9)  sem values_callable → grava o NOME "CREATED"
```

Não bloqueia a E4.4: o valor é estável dos dois lados, e este módulo
reporta **o que está gravado**, sem normalizar — normalizar inventaria
uma convenção que o banco não tem e esconderia um fato da E3.

Mas é armadilha para qualquer consumidor futuro que assuma uma
convenção só, e por isso está registrada em teste (`pi17`) em vez de
virar conhecimento tácito.

**Não corrigida aqui.** Alterar `app/cognitive/` acionaria as Stop
Conditions 2 e 13 deste módulo. O lugar de revisá-la é um corretivo da
E3, por decisão sua.

## 5. Limitação conhecida, herdada e declarada

`transformations_citing()` é `O(n)` sobre `transformation_records`,
porque `input_refs`/`output_refs` são colunas `JSON` sem FK e sem
índice — integridade referencial desses campos está `DEFERRED` desde a
E3.

Acelerar exigiria índice, tabela auxiliar ou coluna derivada: as Stop
Conditions 3 e 4. Registrado como custo herdado, não como defeito
silencioso.

## 6. Testes

| Grupo | Onde | Quantidade |
|---|---|---|
| value objects e fronteiras estruturais | `tests/unit/memory/test_persistence.py` | 30 |
| evidências reais, read-only, independência | `tests/integration/memory/test_persistence_integration.py` | 17 |

Correspondência com os 25 requisitos:

| # | Requisito | Teste |
|---|---|---|
| 1 | inexistente ≠ sem evidência | `pi1`, `pv1` |
| 2 | ausência reportada honestamente | `pi2` |
| 3 | CLID é evidência, não score | `pi3` |
| 4 | direção de linhagem preservada | `pi4`, `pv2` |
| 5 | ramos múltiplos permanecem múltiplos | `pi5` |
| 6 | input ≠ output | `pi6`, `pv2` |
| 7 | eventos por referência | `pi7` |
| 8 | ausência de história não cria história | `pi8` |
| 9 | ordem determinística | `pv3`, `pi12` |
| 10 | duplicatas estáveis | `pv4` |
| 11 | coleções externas não alteram o resultado | `pv5` |
| 12 | construtor direto rejeita inválido | `pv6`, `pv7`, `pv8` |
| 13 | zero `INSERT`/`UPDATE`/`DELETE` | `pi9` |
| 14 | censo canônico inalterado | `pi9` |
| 15–17 | contexto/membership/policy não alteram | `pi10`, `pv16` |
| 18 | acessibilidade não cria nem destrói continuidade | `pi11` |
| 19 | nenhum score/rank/importance | `pv11` |
| 20 | nenhuma tabela ou migração nova | `pi13` |
| 21 | E3 intacta | `pv13` |
| 22 | Sync com sete seções | `pi14` |
| 23–24 | sem transcript/provider/embedding/vector | `pv14` |
| 25 | regressões zero | suíte completa |

`pv16` merece nota: ele verifica a **assinatura** de `assess()`.
Independência de contexto garantida pelo tipo, não por disciplina de
chamador — o contexto não tem por onde entrar.

`pv12`, `pv13`, `pv14` e `pv15` testam **ausência estrutural** (AST com
docstrings removidas, como em E4.3.1): é o único modo honesto de provar
fronteira, porque um teste de comportamento passaria igual se a
capacidade proibida existisse mas não fosse chamada.

## 7. Resultados

```
FULL_SUITE = 1290 passed / 1 skipped / 0 failed
E3_REGRESSION_DELTA   = 0   (598/598)
E4_1_REGRESSION_DELTA = 0   (40/40)
E4_2_REGRESSION_DELTA = 0   (42/42)
E4_3_REGRESSION_DELTA = 0   (108/108)

GLOBAL_COVERAGE = 98,78%   APP_MEMORY = 100%   APP_COGNITIVE = 100%
RUFF = PASS   BLACK = PASS   MYPY_NEW_ERRORS = 0   git diff --check = limpo
SCHEMA_ORM_DRIFT = 0   MIGRATION_HEAD = 4ca61776b982 (inalterada)
DATABASE_WRITES_DURING_ASSESSMENT = 0

NEW_PERSISTENT_ENTITY = NO   MIGRATION_REQUIRED = NO   E3_MODIFIED = NO
STOP_CONDITIONS = NONE

E4_4_IMPLEMENTATION = COMPLETE
E4_4_FINAL_STATUS   = AWAITING_INDEPENDENT_AUDIT
READY_FOR_E4_5      = FALSE
```
