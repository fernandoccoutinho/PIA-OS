# E3.5 / LIB-05 — Relationship Engine

## Objetivo

Implementar o Relationship Engine da Biblioteca Cognitiva: registro,
classificação, consulta/navegação e ciclo de vida de relações
semânticas explícitas entre `CognitiveObject`s — sem transformar
COUT em score, ranking ou mecanismo de decisão.

## Relationship vs Lineage

```text
Lineage: "de qual objeto este objeto veio?"     (histórico/derivação)
Relationship: "como estes objetos estão relacionados?"  (semântica)
```

Taxonomias disjuntas — verificado por teste (`TY4`):
`RelationshipType` (`related_to, references, supports, contradicts,
depends_on`) e `LineageRelation` (`parent, child, branch, merge,
derived_from, transformed_from`) não compartilham nenhum valor.
Nenhum tipo de `LineageRelation` é reutilizado para relação semântica;
nenhum `RelationshipType` duplica um fato já coberto por
`LineageEdge`.

`RelationshipEngine` nunca cria `LineageEdge` (`LS1`); `ClidManager`/
`VersionManager` nunca criam `Relationship` (`LS2`) — verificado por
teste, não apenas por convenção.

## Endpoint Identity

**Decisão: COID**, não CLID nem ambos.

Uma relação semântica declarada (`A SUPPORTS B`) é sobre objetos
específicos e suas afirmações concretas — não sobre a continuidade
inteira de um patrimônio (`CLID`). Mesmo padrão já estabelecido por
`LineageEdge.parent_coid`/`child_coid` (E3.3): FK real para
`cognitive_objects.id`, sem inventar uma entidade CLID artificial só
para obter integridade referencial (§18 do módulo, evitado
explicitamente).

Isso não é uma decisão arbitrária — é a mesma resolvida por E3.3 para
o mesmo dilema estrutural (relação entre objetos vs. relação entre
continuidades), reaplicada aqui sem necessidade de nova arquitetura.
Não foi Stop Condition.

## Relationship Type Taxonomy

```text
RELATED_TO    — SYMMETRIC
REFERENCES    — DIRECTED
SUPPORTS      — DIRECTED
CONTRADICTS   — DIRECTED
DEPENDS_ON    — DIRECTED
```

Taxonomia mínima — exatamente os exemplos conceituais que o próprio
módulo E3.5 julga semanticamente claros (não uma taxonomia congelada
em `E3_DOMAIN_MODEL_DRAFT.md`, que só menciona "tipos de
relacionamento" sem especificá-los). `CAUSES` deliberadamente **não**
incluído — §21 do módulo pede não introduzir sem requisito explícito
de causalidade declarada, e não há.

## Directionality

`RelationshipType.is_symmetric` — `True` apenas para `RELATED_TO`;
todos os demais são direcionados. Nenhuma edge inversa é criada
automaticamente para tipos direcionados (`TY2`, testado: `A
REFERENCES B` não implica `relationship_exists(B, A, REFERENCES)`).

## Duplicate Semantics

**Correção E3.5.1 (débito C1)**: unicidade vale apenas para relações
**vigentes** — índice único parcial
`uq_relationships_active_source_target_type`
(`UNIQUE(source_coid, target_coid, relationship_type) WHERE
retired_at IS NULL`), não uma `UniqueConstraint` incondicional (a
versão original de E3.5 também bloqueava relações já retiradas,
contrariando o próprio lifecycle aprovado — "retirar a antiga, criar
uma nova"). Suportado nativamente por PostgreSQL
(`postgresql_where`) e SQLite (`sqlite_where`).

Para tipos direcionados: tripla exata `(source_coid, target_coid,
relationship_type)`, restrita às linhas vigentes.

Para o tipo simétrico (`RELATED_TO`): os endpoints são normalizados
**na escrita** — o menor UUID (comparação lexicográfica de
`str(uuid)`) sempre vira `source_coid` — antes de tentar persistir.
Isso faz `(A,B)` e `(B,A)` colidirem no mesmo índice (`TY3`/`S1`,
testado nos dois sentidos).

**Correção E3.5.1 (débito C2) — `SYMMETRIC_UNIQUENESS = DB_LEVEL`**:
a versão original de E3.5 dependia exclusivamente da normalização do
repositório — um bypass direto (ORM/SQL cru) podia armazenar `(A,B,
RELATED_TO)` e `(B,A,RELATED_TO)` simultaneamente, e a documentação
não podia honestamente afirmar garantia de banco. Fechado com **Opção
A (estrutural)**: `CheckConstraint ck_relationships_symmetric_canonical_order`
(`relationship_type != 'related_to' OR source_coid < target_coid`)
rejeita qualquer linha `RELATED_TO` fora da forma canônica,
independentemente do caminho de escrita — testado (`S2`) via
construção direta do modelo, contornando `RelationshipRepository`
inteiramente.

A equivalência entre a ordenação `str(uuid) <` (usada pelo
repositório) e a ordenação nativa de UUID do banco (usada pelo
`CheckConstraint`) foi validada empiricamente antes da implementação
— 5000 amostras aleatórias contra SQLite, 3000 contra PostgreSQL real,
zero divergências (ambas comparam, na prática, a mesma sequência de
dígitos hexadecimais do UUID, hifens à parte).

## Self-Relation Policy

Proibida **globalmente**, para todos os 5 tipos — decisão própria,
não herdada automaticamente de `LineageEdge.CYCLE_PROTECTION =
SELF_ONLY` (mesma conclusão prática, mas por razão semântica
independente): nenhum caso de uso legítimo foi identificado para
`A -> A` em nenhum dos 5 tipos nesta fase. `CheckConstraint` no banco
(defesa em profundidade) + rejeição no domínio antes de qualquer
escrita (`CR6`, testado para os 5 tipos).

## Relationship Lifecycle

**Decisão: append-only + soft-retire** — não CRUD destrutivo, apesar
de o backlog (LIB-043/LIB-044) usar os verbos "update"/"remove".

Pergunta obrigatória do módulo: *alterar/remover uma relação deve
apagar um fato histórico?* — Não. Portanto:

- **"Remover"** = `RelationshipRepository.retire()` — marca
  `retired_at` (soft), nunca apaga a linha. Idempotente (retirar uma
  relação já retirada não é erro). A relação continua identificável,
  auditável, recuperável — mesma disciplina de `SUPERSEDED != DELETED`
  (E3.4).
- **"Atualizar"** = não existe mutação genérica de campos. Se uma
  relação declarada precisar mudar de natureza, a operação correta é
  retirar a antiga e criar uma nova (`create()` + `retire()`) — o
  histórico preserva ambos os fatos (a relação original foi declarada
  E depois deixou de ser vigente), em vez de sobrescrever
  silenciosamente.

`RelationshipRepository.update()`/`.delete()` (físico) sempre
rejeitam (`RelationshipImmutableError`, `PIA-8016`) — mesma disciplina
de `LineageEdge`/`TransformationRecord` (E3.3.1/E3.4). `retire()`
contorna deliberadamente esse bloqueio, chamando
`BaseRepository.update()` diretamente (não `self.update()`) — único
caminho de mutação pós-criação, controlado e de propósito único.

**Nenhum `RelationshipVersion` foi inventado** — soft-retire simples é
suficiente para preservar o histórico exigido; não há necessidade
demonstrada de uma arquitetura de versionamento relacional completa
(que seria Stop Condition-8 se fosse necessária).

**Correção E3.5.1**: o ciclo `create(A,B,SUPPORTS)` → `retire(old)` →
`create(A,B,SUPPORTS)` novamente — explicitamente esperado por este
lifecycle desde a versão original de E3.5 — só passou a funcionar de
fato nesta correção (débito C1); a `UniqueConstraint` incondicional
original bloqueava a segunda criação mesmo com a primeira já
retirada, contrariando a própria decisão de design documentada aqui.
Testado (`U2`/`U3`): recriação após retire funciona, histórico
retirado continua recuperável por COID/`include_retired=True`.

## Navigation

One-hop apenas — `outgoing(coid)`, `incoming(coid)`, `by_type(type)`,
`neighbors(coid)` (`outgoing` + `incoming` combinados). Todos
ordenados deterministicamente (`created_at ASC, id ASC`, mesma
convenção de E3.1.2/E3.3). Excluem relações retiradas por padrão
(`include_retired=True` como escape hatch) — mesmo padrão
soft-delete-aware de `ObjectRepository` (E3.1.1).

Nenhuma travessia multi-hop implementada — `neighbors()` não segue
arestas recursivamente; testado (`NV7`) que uma estrutura cíclica
(`A->B`, `B->A`, tipos diferentes) não trava nem loopa, porque a
consulta é sempre O(1) hop.

## CausalClassRef Status

`CAUSAL_CLASS_REF_STATUS = DEFERRED`.

`CausalClassRef` (Domain Model Draft, §5) representa uma classe de
equivalência formada por `CausalComparison` resultando em `EQUIVALENT`
— `CausalComparison` não existe e não é owned por E3.5. Nenhuma
funcionalidade concreta deste módulo exige `CausalClassRef` — nenhum
dos 5 `RelationshipType`s representa equivalência causal. Não
implementado, não reservado como campo morto sem uso.

## CognitiveDistinction Status

`COGNITIVE_DISTINCTION_STATUS = DEFERRED` (inalterado desde E3.1).
Nada em `Relationship` exige concretizá-la — os endpoints são COID
(`CognitiveObject`), não `distinction_id`.

## Files Created

```
app/cognitive/models/relationship.py
app/cognitive/repositories/relationship_repository.py
app/cognitive/services/relationship_engine.py
alembic/versions/2826ce7fa4dc_create_relationships_table_e3_5_lib_05.py
tests/unit/cognitive/models/test_relationship.py
tests/unit/cognitive/repositories/test_relationship_repository.py
tests/unit/cognitive/services/test_relationship_engine.py
tests/integration/cognitive/test_relationship_integration.py
```

## Files Modified

`app/cognitive/models/__init__.py`, `app/cognitive/models/enums.py`
(+`RelationshipType`), `app/cognitive/errors/{codes,exceptions,__init__}.py`
(+`PIA-8013`..`PIA-8016`), `tests/unit/cognitive/conftest.py`
(+tabela `Relationship`). **Nenhum arquivo de E3.1-E3.4 tocado** —
confirmado por `git diff --stat`.

## Migration

`2826ce7fa4dc_create_relationships_table_e3_5_lib_05.py` — tabela
nova, aditiva. `source_coid`/`target_coid` com FK real para
`cognitive_objects.id` (sem `ON DELETE CASCADE`, mesma política de
`LineageEdge`), `CheckConstraint` contra self-link,
`UniqueConstraint(source_coid, target_coid, relationship_type)`.

Bug pequeno corrigido antes de aplicar: a primeira geração automática
da migração produziu `retired_at` como `DateTime` sem timezone,
inconsistente com `created_at`/`updated_at`/`deleted_at` (todos
`DateTime(timezone=True)` na baseline) — corrigido no modelo
(`DateTime(timezone=True)` explícito) e a migração foi regenerada
antes de aplicar.

Testada `upgrade → downgrade → upgrade` contra PostgreSQL 16 real —
`cognitive_objects`, `lineage_edges`, `transformation_records`, e o
índice `uq_cognitive_objects_one_current_per_clid` (E3.4.1)
confirmados intactos em todo o ciclo. `alembic/env.py` não precisou
ser tocado.

**Correção E3.5.1**: nova migração aditiva,
`63d205dec996_active_uniqueness_and_symmetric_.py` —
`2826ce7fa4dc` **não foi editada** (já publicada em patch anterior).
Substitui a `UniqueConstraint` incondicional por
`uq_relationships_active_source_target_type` (índice único parcial,
`WHERE retired_at IS NULL`) e adiciona
`ck_relationships_symmetric_canonical_order`. Este último não foi
detectado pelo autogenerate do Alembic (limitação conhecida da
ferramenta para `CheckConstraint`) — adicionado manualmente ao
`upgrade()`/`downgrade()` gerados. Testada `upgrade → downgrade →
upgrade` contra PostgreSQL real — downgrade confirmado restaurando
exatamente o schema anterior (`UniqueConstraint` incondicional de
volta), `cognitive_objects`/`lineage_edges`/índice de `CURRENT`
(E3.4.1) confirmados intactos.

## Error Codes

| Código | Situação |
|---|---|
| `PIA-8013` (novo) | Self-relation (`source_coid == target_coid`) |
| `PIA-8014` (novo) | Relação duplicada (tripla direcionada ou par simétrico) |
| `PIA-8015` (novo) | Endpoint (`source_coid`/`target_coid`) inexistente |
| `PIA-8016` (novo) | `update`/`delete` físico rejeitado (append-only) |

`PIA-8001`-`PIA-8012` inspecionados; nenhum reaproveitável
semanticamente para os invariantes específicos de `Relationship`
(os equivalentes de `LineageEdge` — `PIA-8006`-`PIA-8009` — são
específicos daquele modelo, não genéricos).

## Tests

**Correção documental E3.5.2**: a contagem abaixo foi verificada por
inspeção real do repositório (`grep -c "^def test_"` + `pytest
--collect-only`), não por aritmética — os números originalmente
documentados aqui (75 para E3.5, 46 para o repository, 82 no total)
estavam incorretos. Ver `E3_5_2_LIB05_COUT_DATA_PRESERVATION.md` para
o detalhamento da correção.

**65 testes novos ao todo** (57 de E3.5 original + 8 da correção
E3.5.1 — 7 unitários e 1 de integração):

- **Model** (`test_relationship.py`, 7): criação, os 5 valores de
  `RelationshipType`, self-link/duplicata rejeitados por
  constraint, tipos diferentes entre o mesmo par permitidos, FK.
- **Repository** (`test_relationship_repository.py`, 36): `CR1`-`CR8`,
  `TY1`-`TY6`, `NV1`-`NV7`, `LS1`-`LS6`, append-only/lifecycle,
  classificação de violação isolada (sinal estruturado).
- **Engine** (`test_relationship_engine.py`, 10): delegação de
  create/retire/navigation, `MIA1`-`MIA5`.
- **Correção E3.5.1** (`test_relationship_active_uniqueness.py`, 7):
  `U1`-`U3` + variante extra ("apenas 1 ativa após retire+recreate"),
  `S1`-`S2` (+ variante confirmando que tipos direcionados não são
  afetados pelo `CheckConstraint` de simetria).
- **Integração contra PostgreSQL real**
  (`test_relationship_integration.py`, 5): `PG1`-`PG5` (E3.5 original,
  incluindo `PG5` — concorrência real de criação duplicada ativa,
  satisfaz `U4` da correção E3.5.1 sem duplicação de teste) + `U2`
  (novo, ciclo `create→retire→create` contra Postgres real).

**100% de cobertura de linha em todo `app/cognitive/`** (322 testes
unitários).

## PostgreSQL Result

5/5 testes de integração passando, incluindo `PG5`/`U4` (concorrência
real de duplicata ativa) e `U2` (ciclo retire+recreate) — nunca
simulados apenas em SQLite.

## Concurrency Result

`PG5`: duas threads/sessões/conexões distintas tentando criar
exatamente a mesma relação (`A, B, SUPPORTS`) simultaneamente — apenas
uma commita; a `UniqueConstraint` no banco rejeita a outra
(classificada como `RelationshipDuplicateError` via sinal
estruturado). Executado 4+ vezes, estável.

## Coverage

100% em `app/cognitive/` (322 testes unitários).

## Ruff/Black/Mypy

Todos limpos — mypy com os mesmos 7 erros pré-existentes de sempre,
zero novos.

## Non-Regression

777 passed, 19 skipped (sem `.env` local — mesmo padrão gracioso de
sempre), 97,54% (mantido em relação a antes da correção E3.5.1).
Revalidado explicitamente: COID imutável, CLID imutável após
atribuição, lineage append-only, `CURRENT` uniqueness por CLID (índice
de E3.4.1 intacto após as duas migrações de E3.5/E3.5.1),
`derive()`/`revise()`, `TransformationRecord` append-only, cadeia de
migrações completa (incluindo a nova `63d205dec996`), 7 erros mypy
pré-existentes (não aumentaram). Um teste pré-existente de E3.5
(`test_relationship_type_accepts_all_five_documented_values`) precisou
de ajuste — criava uma relação `RELATED_TO` em ordem arbitrária, o que
passou a violar o novo `CheckConstraint` de ordem canônica; não é
regressão de comportamento de produção, é o teste se adequando à nova
garantia estrutural. Nenhuma outra regressão.

## Multi-IA Readiness

```
COMPETITIVE_READY = TRUE
COMPLEMENTARY_READY = TRUE
SEQUENTIAL_READY = TRUE
```

Relações contraditórias coexistem sem erro (`TY6`/`MIA2`, testado:
`A SUPPORTS X` e `B CONTRADICTS X` persistem juntas). Nenhum método
público de `RelationshipEngine` aceita `provider`/`model`/`agent`
(`MIA3`). Nenhum SDK de IA é importado (`MIA4`). `RelationshipEngine`
não arbitra conflitos — API pública restrita a
`create/retire/outgoing/incoming/neighbors/by_type` (`MIA5`,
verificado por introspecção).

## Workspace / Controlled-Asset Status

Nenhuma promoção automática — `RelationshipEngine.create()` só é
chamado explicitamente; nenhum chat/output transitório vira
`Relationship` sozinho. `PROMOTION_POLICY_STATUS` continua `DEFERRED`
(inalterado desde E3.4.0).

## Deferred Items

- `CausalClassRef`: `DEFERRED`, ver seção dedicada acima.
- `CognitiveDistinction`: `DEFERRED`, inalterado.
- `ProvenanceRecord` completo: `E3.6`.
- Index/Search Manager (inclusive índices otimizados para navegação
  de grafo em escala): `E3.7`/`E3.8`.
- Integrity Manager (auditoria global do grafo, detecção completa de
  ciclos, repair automático): `E3.10`.
- Hypervisor/Arbiter (resolução automática de relações
  contraditórias): fase futura de governança, não numerada
  explicitamente na sequência atual.

## Risks

- Sem FK entre `Relationship` e `LineageEdge`/`TransformationRecord`
  — são entidades genuinamente independentes por design (§29 do
  módulo: evitar tripla representação do mesmo fato), então isso não
  é uma lacuna, é a separação pretendida.
- `outgoing`/`incoming`/`neighbors` sem paginação nesta fase — volume
  esperado desta fase não exige; candidato a revisão quando `E3.7`
  (Index Manager) existir.

## Stop Conditions

Nenhuma foi acionada. Análise explícita contra os 13 gatilhos do
módulo:

1-4 (COID/CLID/CURRENT uniqueness/Lineage incompatível): nenhum
tocado — `Relationship` é aditiva, não modifica semântica existente.
5 (migrations congeladas): nenhuma editada.
6-7 (`CognitiveDistinction`/`CausalClassRef` sem contrato): ambos
`DEFERRED`, não implementados.
8 (versionamento relacional não previsto): soft-retire simples
resolveu sem precisar de arquitetura nova.
9-12 (Metadata/Provenance/Integrity/Hypervisor antecipados): nenhum
implementado.
13 (contrato de E3.1-E3.4 quebrado): nenhum — confirmado por
non-regression completa.
