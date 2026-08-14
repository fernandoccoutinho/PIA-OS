# E3_4_2_LIB04_MULTI_INPUT_TRANSFORMATION

**Módulo:** E3.4.2 — Multi-Input Cognitive Transformation Corrective
**Baseline:** `PATCH_CHAIN = 45` · HEAD `3f500701a0cd…` ✓ ·
TREE `8ac019a79388…` ✓ · PARENT `02e582b019ad…` ✓ ·
bundle SHA-256 `d77b3328…0c9a` ✓ · `git bundle verify` OK ·
migration head `4ca61776b982` ✓ · `git status` limpo ✓
**Patch:** `e3-4-2-multi-input-transformation-corrective.patch` (46º)

Trees de controle conferidos na baseline:

```text
backend/app/cognitive     = f32780bc37c45bc495aed000898354a7d71c8b1b
backend/app/memory        = c5cec4aeab8d494c24ccd71bb766265bc2250619
backend/alembic           = f01a1f812eb11695b9daeb6b1707e6477e9330fa
docs/entregas/entrega-4   = 27fd09fa53487b96835015090dfecbfb9387f9f7
```

---

## 1. Missão

```text
PERSISTIR UMA TRANSFORMAÇÃO COGNITIVA COM N ENTRADAS
PRESERVANDO INTEGRALMENTE TODAS AS FONTES
```

Mecanismo público, tipado, coberto e transacional, dentro de
`app/cognitive` — o único dono do patrimônio cognitivo.

---

## 2. Pre-implementation findings

### 2.1 A lacuna é real e foi confirmada por varredura

`grep` de `input_refs` em todo `app/`: as únicas escritas eram
`version_manager.py:186` e `:332`, ambas `input_refs=[str(source.id)]`.
Nenhum writer multi-input público existia.

### 2.2 A construção da E3.12 não é contrato — e é incoerente consigo

O cenário `G1` produz **dois** `TransformationRecord` para o mesmo
`{o2,o3} → o4`:

| Origem | kind | input_refs |
|---|---|---|
| `derive(o2, relation_type=MERGE)` | `DERIVATION` | `[o2]` |
| `uow.session.add(...)` manual | `REVISION` | `[o2, o3]` |

O primeiro não menciona `o3`; o segundo declara `REVISION` sem que
ninguém seja superseded. Copiar essa combinação teria violado
"exatamente um registro" e afirmado supersessão que não ocorre. Este
módulo produz **um** registro `DERIVATION` coerente com o que de fato
acontece.

### 2.3 `ClidManager.inherit()` é inutilizável aqui

Código lido antes de decidir:

```python
resolved_clid = parent.clid if parent.clid is not None else self.generate()
if parent.clid is None:
    parent.clid = resolved_clid
    self._objects.update(parent)     # ← escreve na FONTE
```

Com fonte sem CLID, `inherit()` gera um e o grava na fonte — mutação de
fonte e fabricação de continuidade. Além disso aceita um único parent.
Só `assign()` é usado, e apenas sobre o alvo.

---

## 3. Contrato público

```python
MultiInputTransformationManager.derive_many(
    *,
    source_coids: Iterable[uuid.UUID],
    operation_type: str,
    declared_losses: Iterable[str],
    declared_preservations: Iterable[str] = (),
    actor_ref: uuid.UUID | None = None,
    policy_ref: str | None = None,
    predecessor_event_ids: Iterable[uuid.UUID] = (),
    occurred_at: datetime | None = None,
) -> MultiInputTransformationReceipt
```

Superfície pública do manager: **exatamente `{"derive_many"}`**,
verificado por teste.

Produz, por construção: 1 `CognitiveObject` alvo · N `LineageEdge(MERGE)`
· 1 `TransformationRecord` multi-input · 1 evento-raiz **ou** N eventos
causais.

### 3.1 Ordem de preflight (§6.1)

Cardinalidade e duplicidade → tipos dos COIDs → `operation_type`
(incluindo a capacidade real da coluna, `String(64)`) →
`declared_losses` → `declared_preservations` → existência de todas as
fontes → existência dos predecessores → pertencimento causal →
tipos de `actor_ref`/`policy_ref`/`occurred_at`.

Cada iterable é materializado **uma única vez**. Erro de preflight
produz `DATABASE_WRITES = 0`, provado por listener de cursor.

---

## 4. Implementação

```text
app/cognitive/schemas/multi_input_transformation.py       recibo imutável
app/cognitive/services/multi_input_transformation_manager.py
app/cognitive/errors/codes.py       + PIA-8029/8030/8031
app/cognitive/errors/exceptions.py  + 3 exceções
app/cognitive/errors/__init__.py    + reexports
```

Compõe `ObjectRepository`, `ClidManager` (só para o alvo),
`LineageRepository`, `TransformationRepository`, `CausalHistoryManager`
e `CausalHistoryRepository`. **Nenhum `session.add()` fora de
repositório, nenhum SQL cru, nenhum registry lookup, nenhum import
dinâmico, nenhum `commit()` interno.**

Nenhum arquivo de `app/memory`, `alembic/` ou `docs/entregas/entrega-4`
foi tocado. Nenhuma migração, tabela, coluna ou enum novo.

---

## 5. Testes

| Grupo | Onde | Qtd |
|---|---|---|
| Recibo (§12.1) | `tests/unit/cognitive/schemas/test_multi_input_transformation.py` | 32 |
| Manager (§12.2) | `tests/unit/cognitive/services/test_multi_input_transformation_manager.py` | **70** |
| PostgreSQL real (§13) | `tests/integration/cognitive/test_multi_input_transformation_integration.py` | 20 |
| **Total novo** | | **122** |

> **Correção E3.4.2.1.** A primeira versão desta tabela declarava 69
> testes de manager e total 121. A coleta real do pytest é **70** e
> **122** — o número anterior foi contado à mão, não coletado. Corrigido
> aqui pela coleta real, e a disciplina fica registrada: contagem se
> obtém do `pytest --collect-only`, nunca por estimativa. As contagens
> após o corretivo E3.4.2.1 estão em
> `E3_4_2_1_LIB04_MULTI_INPUT_CONTRACT_HARDENING.md`.

### 5.1 Rollback provado por injeção de falha

Três etapas materiais recebem falha injetada — primeira/intermediária
edge, `TransformationRecord` e história causal — e após o rollback o
censo confirma:

```text
orphan target = 0        partial lineage = 0
partial transformation = 0    partial causal history = 0
source mutation = 0      (censo linha a linha das fontes)
```

Mais `pg15`: rollback **por omissão** da `UnitOfWork` — sem `commit()`,
nada da operação sobrevive.

### 5.2 Concorrência

`pg20`: duas consolidações simultâneas das mesmas fontes, sincronizadas
por barreira, produzem **dois alvos distintos**, sem deadlock e sem
mutar fontes.

```text
REPEATED CONSOLIDATION != SAME EVENT
MULTIPLE HISTORY PRESERVATION
```

Nenhuma constraint foi criada que destruísse essa possibilidade.

### 5.3 Fronteiras verificadas por ausência estrutural

O fonte é comparado como **código executável** (AST com docstrings
removidas, técnica de E4.3.1 — as docstrings citam nominalmente o que o
módulo não faz) contra `_score`, `rank`, `winner`, `best_source`,
`resolve_divergence`, `learn`, `embedding`, `provider`, `transcript`,
`commit(` e `REVISION`. Testar ausência é o único modo honesto de
provar uma fronteira.

Também: nenhum import de `app.memory` nos dois módulos novos, e as
quatro ordens de import públicas rodam em **interpretadores limpos**
(dentro do mesmo processo `sys.modules` esconderia um ciclo — foi assim
que o sétimo defeito da E4.3.1 passou despercebido).

---

## 6. Defeitos meus, encontrados e corrigidos

Registrados porque um módulo que silencia os próprios erros é menos
confiável, não mais.

**(a) Helper de teste que engolia o caso `None`.** `_recibo()` usava
`None` como marcador de "não informado", então o teste que exigia
recusa de `source_coids=None` nunca chegava ao value object e passava
por engano. Corrigido com sentinela.

**(b) Asserção de fronteira que acusava a própria docstring.** O teste
buscava a string `"app.memory"` no fonte e encontrava a frase que
explica que o módulo *não* importa `app.memory`. Passou a casar
declarações de import por regex — mesmo tipo de falso positivo que a
E4.3.1 corrigiu em `gv16`.

**(c) Teste de drift contaminado pelo harness.** Passava isolado e
falhava na suíte completa, acusando três tabelas
(`test_base_model_concrete_entity`, `test_base_model_soft_delete_entity`,
`test_mixin_fixture_entity`) que **fixtures de teste** registram no
`Base` real durante a coleta. Não era drift. Adotei o recorte que `IX5`
(E3.7) já usava e `CHI8` (E3.9) repetiu, em vez de inventar solução
própria.

**(d) Três ramos de validação de tipo sem cobertura**, revelados pela
exigência de 100% — mesmo mecanismo que já revelara código morto em
E3.11.1, E4.1, E4.2.1 e E4.3. Fechados com casos, e a regra ficou mais
estrita, não mais frouxa.

**(e) Um erro novo de mypy** — `tuple[object, ...]` como retorno de
`_registrar_causalidade`. Tipado corretamente como
`tuple[CausalHistoryEvent, ...]`.

E um achado de ambiente, não de código: **SQLite descarta `tzinfo`**
mesmo em `DateTime(timezone=True)`. A asserção com fuso preservado
migrou para a integração PostgreSQL, onde a coluna é `timestamptz` de
verdade — afirmar no unitário o que ele não prova seria overclaim.

---

## 7. Limitação declarada

`actor_ref`, quando informado, precisa referenciar um `ProvenanceRecord`
existente, porque `causal_history_events.actor_ref` é FK real para
`provenance_records.id` — enquanto o campo homônimo de
`TransformationRecord` não tem FK. A autoridade final é a FK do banco,
não uma pré-checagem inventada. Registrado no EDR §10.

---

## 8. Resultados

```text
FULL_SUITE = 1439 passed / 1 skipped / 0 failed
RAW_SUITE  = 1245 passed / 184 skipped / 0 failed

E3_REGRESSION_DELTA   = 0   (598/598)
E4_1_REGRESSION_DELTA = 0   (40/40)
E4_2_REGRESSION_DELTA = 0   (42/42)
E4_3_REGRESSION_DELTA = 0   (108/108)
E4_4_REGRESSION_DELTA = 0   (74/74)

E3_4_2 NOVOS = 122 passed   (corrigido em E3.4.2.1; antes declarado 121)

GLOBAL_COVERAGE = 98,85%   (baseline 98,79%)
APP_COGNITIVE_COVERAGE = 100%
APP_MEMORY_COVERAGE    = 100%

RUFF = PASS   BLACK = PASS
MYPY_TOTAL_ERRORS = 7 (idênticos à baseline)   MYPY_NEW_ERRORS = 0
git diff --check = limpo

SCHEMA_ORM_DRIFT = 0
MIGRATION_HEAD = 4ca61776b982 (inalterada, single-head)
NEW_MIGRATION = NO   NEW TABLE = NO   NEW COLUMN = NO
NEW PERSISTENT ENTITY = NO   ENUM AMPLIADO = NO

POSTGRESQL = 16.14 real
```

Próximo error code global livre: **`PIA-8032`**.

---

## 9. Stop Conditions

```text
STOP_CONDITIONS = NONE
```

Nenhuma das 19 do §15 ocorreu. Em particular: nenhuma tabela/coluna/
migração foi necessária, nenhum enum foi ampliado, `app/memory` não foi
tocado, G17 e MD6 não foram afrouxados, nenhum `importlib`/registry/
`sys.modules`/SQL cru foi usado, nenhum `session.add()` fora de
repositório, nenhum `commit()` no manager, nenhuma fonte foi mutada,
nenhum CLID foi gerado para fonte, nenhuma causalidade foi inferida, e
nenhum defeito arquitetural congelado foi corrigido em silêncio.

---

## 10. Gate

```text
E3_4_2_IMPLEMENTATION = COMPLETE
E3_4_2_FINAL_STATUS   = AWAITING_INDEPENDENT_AUDIT

E4_5_IMPLEMENTATION = NOT_STARTED
E4_5_STATUS         = BLOCKED_PENDING_E3_4_2_AUDIT
READY_FOR_E4_5      = FALSE
READY_FOR_E4_6      = FALSE
```

E4.5 **não** é iniciada automaticamente.
