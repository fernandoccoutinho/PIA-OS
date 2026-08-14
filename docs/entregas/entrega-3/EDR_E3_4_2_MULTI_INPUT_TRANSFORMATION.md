# EDR_E3_4_2 — decisões congeladas do corretivo Multi-Input

**Módulo:** E3.4.2 — Multi-Input Cognitive Transformation Corrective
**Natureza:** corretivo da E3, posterior ao congelamento.
**Baseline:** `PATCH_CHAIN = 45` · HEAD `3f500701` · TREE `8ac019a7` ·
migration head `4ca61776b982` — todos verificados em clone limpo.

> Este EDR **não reescreve** nenhuma decisão anterior. `EDR_COUT_PIA_E3.md`
> e `EDR_COUT_PIA_E4.md` permanecem válidos. Aqui ficam apenas as
> decisões que este corretivo acrescenta.

---

## 1. Por que a E3 foi reaberta

```text
VersionManager.derive()              = MONO-INPUT
MULTI-INPUT COGNITIVE TRANSFORMATION = ABSENT (até este patch)
```

`derive()` e `revise()` recebem um único `source` e gravam
`input_refs=[str(source.id)]`. Confirmado por varredura: as **únicas**
escritas de `input_refs` em todo `app/` eram essas duas.

A E3.12 demonstrou um cenário multi-input **apenas em teste**, com
`session.add()` direto e **dois** `TransformationRecord` mutuamente
incoerentes para a mesma operação `{o2,o3} → o4`: um `DERIVATION` com
`input_refs=[o2]` e um `REVISION` com `input_refs=[o2,o3]`. Construtor
de cenário não é contrato público, e a incoerência entre os dois é
precisamente o sintoma da lacuna.

A lacuna é **da E3**. Corrigi-la aqui, e não na camada que a consome, é
o que mantém intacta a regra que organiza toda a arquitetura:

```text
COGNITIVE PATRIMONY WRITER = app/cognitive
app/memory NEVER IMPORTS app.cognitive
G17 = PRESERVED      MD6 = PRESERVED
```

---

## 2. Semântica de CLID multi-origem

```text
IF all sources have the same single non-null CLID:
    target.clid = that CLID
ELSE:
    target.clid = None
```

| Fontes | CLID do alvo |
|---|---|
| Todas com o mesmo CLID não nulo | herda o CLID comum |
| CLIDs diferentes | `None` |
| Alguma fonte com `clid=None` | `None` |
| Todas com `clid=None` | `None` |

Congelado:

```text
SOURCE CLID MUTATION          = FORBIDDEN
SOURCE CLID GENERATION        = FORBIDDEN
SILENT CONTINUITY FABRICATION = FORBIDDEN
MIXED HISTORIES              != SINGLE CONTINUITY
MIXED CLID                   != AUTHORIZATION TO CREATE NEW SHARED CLID
COMMON CLID REQUIRES COMMON CONTINUITY
MERGE EDGE                   != CLID EQUALITY
```

**`ClidManager.inherit()` não é usado nesta operação**, e a razão é
substantiva, não estilística: quando o *parent* não tem CLID, `inherit()`
gera um e o **grava na fonte** (`parent.clid = resolved_clid;
update(parent)`). Isso mutaria uma fonte e fabricaria continuidade onde
não havia. Só `ClidManager.assign()` é usado, e apenas sobre o alvo —
que é linha nova da própria transação.

`target.clid = None` é resultado **legítimo**, não falha: o Domain Model
Draft já declara `clid` nullable para "objetos sem linhagem conhecida
ainda". A origem fica registrada na linhagem de qualquer modo.

---

## 3. Tipo da transformação

```text
TransformationKind = DERIVATION      (nunca REVISION)
```

`REVISION` significa que o alvo **sucede** a representação do mesmo
patrimônio lógico, e `VersionManager.revise()` move a fonte para
`SUPERSEDED`. Numa consolidação as fontes permanecem íntegras, então
`REVISION` afirmaria o oposto do que ocorre:

```text
MULTI-INPUT DERIVATION != SOURCE REPLACEMENT
SUMMARY                != SOURCE REPLACEMENT
```

O enum **não foi ampliado**. Nenhum `CONSOLIDATION` foi criado.

Nenhuma fonte vira `SUPERSEDED`, muda `revision_status`,
`accessibility`, `deleted_at` ou CLID. O alvo permanece com
`revision_status = None`.

---

## 4. Linhagem e registro

```text
N fontes → N LineageEdge(relation_type=MERGE), source_i → target
         → EXATAMENTE 1 TransformationRecord multi-input
```

```text
input_refs  = todos os source COIDs, ordem canônica, sem repetição
output_refs = [target_coid]
```

Ordem canônica **por valor de UUID**, aplicada num único ponto e válida
para `input_refs`, para as edges e para o recibo. Consequência
congelada:

```text
(M1, M2, M3) e (M3, M1, M2) produzem o mesmo registro
SOURCE ORDER != SOURCE RANKING
```

Duplicata é **erro**, nunca desduplicação silenciosa:

```text
DUPLICATE SOURCE = INVALID INPUT
```

Esconder a repetição entregaria N−1 edges para N fontes declaradas, e o
chamador nunca saberia que sua lista estava errada.

---

## 5. Perdas declaradas

```text
DECLARED_LOSS_ON_MULTI_INPUT_CONSOLIDATION = MANDATORY
```

Rejeitados: coleção vazia, string vazia, string só com espaços, tipo
inválido, e `str` usada como coleção (que viraria uma lista de
caracteres). **Nada é preenchido automaticamente** com `"none"`,
`"unknown"` ou equivalente — isso seria a mesma afirmação falsa, só que
escondida.

```text
DECLARED LOSS        != AUTOMATICALLY MEASURED LOSS
DECLARED PRESERVATION != PROVEN TRUTH
```

A E3 exige que a perda seja **declarada** e preserva a declaração. Não
verifica semanticamente se ela é verdadeira, e não tem como.

---

## 6. Causalidade multi-origem

```text
CausalEventType = TRANSFORMED     (enum não ampliado)
```

**Com N predecessores explícitos:** N eventos no alvo, um por
predecessor, `payload_ref = str(transformation_id)`. Cada predecessor
deve existir e pertencer à história causal de **uma das fontes
declaradas**. Predecessor *cross-history* continua legítimo — várias
fontes têm várias histórias; o que se exige é que o sujeito seja uma
fonte, não que todos venham de uma história só.

**Sem predecessor explícito:** exatamente **um** evento-raiz, com
`predecessor_event_id = None`.

```text
OPERATION OCCURRENCE  = KNOWN FACT
MISSING PREDECESSOR  != MISSING OPERATION
TEMPORAL PRECEDENCE  != CAUSALITY
MISSING HISTORY      != AUTHORIZATION TO INVENT PREDECESSOR
```

Nada é inferido: nenhum "último evento" é escolhido, `created_at` não
participa da decisão, e `occurred_at` omitido permanece `None` — nunca
recebe `created_at`.

N eventos para N predecessores não é escolha estética: `CausalHistoryEvent`
admite **no máximo um** `predecessor_event_id`, e representar múltiplas
origens de outra forma exigiria ampliar contrato da E3.

---

## 7. Soft delete

```text
SOFT_DELETED != NEVER EXISTED
SOFT_DELETED != SUBJECT_NOT_FOUND
SOFT_DELETED != HISTORICAL ERASURE
```

Fontes são localizadas com `include_deleted=True`. Uma fonte com
exclusão lógica é fonte legítima: aparece em `input_refs`, continua
endpoint de `LineageEdge`, **não** é recuperada e seu `deleted_at`
**não** é alterado.

E o limite, dito explicitamente: este corretivo é **mecanismo
cognitivo, não autorização de uso**. Incluir um objeto soft-deleted
numa transformação não decide nada sobre acesso a ele — isso é
governança (E4.3) e acessibilidade (E4.7).

---

## 8. Recibo e fronteira com a futura E4.5

`MultiInputTransformationReceipt` é `frozen`, hashable, com coleções
convertidas em tuplas defensivas e invariantes impostos em
`__post_init__`:

```text
frozen=True ALONE != DEEP IMMUTABILITY
```

Três correções anteriores (E4.2.1, E4.3.2, E4.4.1) pagaram por essa
lição pelo mesmo motivo: `frozen` protege a referência, não o conteúdo.
Aqui o construtor direto passa exatamente pelas mesmas regras que o
manager.

O recibo carrega **apenas UUIDs** — nenhuma instância ORM atravessa o
contrato público. Isso é deliberado e olha para frente: a E4.5
consumirá este mecanismo por inversão de dependência, definindo um
`Protocol` estrutural do lado dela. Um recibo feito de UUIDs e tuplas é
estruturalmente satisfazível por esse `Protocol` sem que `app/memory`
importe nada de `app.cognitive`.

**Este patch não cria** o port, o adapter, o `ConsolidationManager` nem
qualquer arquivo em `app/memory`.

```text
PERMISSION TO CONSOLIDATE != CONSOLIDATION IMPLEMENTATION
```

---

## 9. O que não foi implementado

```text
COUT score                     = NONE
best-source selection          = NONE
ranking / winner               = NONE
confiança global               = NONE
verdade majoritária            = NONE
resolução automática de divergência = NONE
equivalência sem perdas        = NONE
learning                       = NONE
promoção a Kernel              = NONE
```

```text
NEW PERSISTENT ENTITY = NO    NEW TABLE = NO
NEW COLUMN            = NO    MIGRATION_REQUIRED = NO
ENUM AMPLIADO         = NO
```

E, como em toda a E3: nenhuma equação física entrou em `app/`.
`PHYSICS_IN_APP = NONE`.

---

## 10. Achado registrado sobre o schema

`causal_history_events.actor_ref` é **FK real** para
`provenance_records.id` (E3.9), enquanto o campo homônimo de
`TransformationRecord` **não tem FK** ("nenhuma FK para tabela
inexistente", E3.4). Consequência: um `actor_ref` informado precisa ser
um `ProvenanceRecord` existente.

A autoridade final é a FK do banco, não uma pré-checagem inventada —
mesma disciplina de E3.3/E3.4. Nenhum código de erro novo foi criado
para isso: o §5 do prompt canônico proíbe reservar códigos para uso
futuro, e criar um sem chamador seria código morto do tipo que a
exigência de 100% já revelou quatro vezes neste projeto.

---

## 11. Diagnósticos

Faixa `PIA-8xxx` é **global ao projeto**. `PIA-8023`..`PIA-8028`
pertencem a `app/memory` (E4.1/E4.2/E4.3), então a numeração continua de
onde o catálogo **inteiro** parou:

```text
PIA-8029 = MULTI_INPUT_SOURCE_NOT_FOUND
PIA-8030 = CAUSAL_PREDECESSOR_NOT_FOUND
PIA-8031 = CAUSAL_PREDECESSOR_SUBJECT_MISMATCH
```

Próximo código global livre: **`PIA-8032`**.

Nenhum código foi reservado para uso futuro. Validações de tipo,
cardinalidade, duplicidade, string vazia e declaração de perdas usam
`TypeError`/`ValueError`, seguindo a convenção do projeto desde E3.2.

---

## 12. Estado

```text
E3_4_2_IMPLEMENTATION = COMPLETE
E3_4_2_FINAL_STATUS   = AWAITING_INDEPENDENT_AUDIT

E4_5_IMPLEMENTATION   = NOT_STARTED
E4_5_STATUS           = BLOCKED_PENDING_E3_4_2_AUDIT
READY_FOR_E4_5        = FALSE
READY_FOR_E4_6        = FALSE
```

O implementador não declara `PASS FINAL`. Isso pertence à auditoria
independente.
