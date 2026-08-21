# E3.7 / LIB-07 — Index Manager

## Objetivo

Responder à pergunta central do módulo: **como localizar
eficientemente distinções cognitivas já persistidas sem transformar o
índice numa segunda fonte da verdade?**

```text
INDEX != SOURCE OF TRUTH
INDEX  = DERIVED + REBUILDABLE
```

O índice torna uma distinção **localizável**. Ele não fabrica, não
altera e não apaga a distinção indexada. A Biblioteca Cognitiva
persistente continua sendo a fonte da verdade, e a perda integral dos
índices é corrigível por recriação, sem perda de patrimônio.

## Arquitetura escolhida

Avaliadas as quatro opções do §13 do módulo, a resposta à pergunta
obrigatória — *"os índices nativos do PostgreSQL + uma camada de
serviço determinística já satisfazem LIB-07?"* — é **sim**. A
implementação é, portanto:

```text
A. índices nativos do PostgreSQL sobre as tabelas já existentes
   (migração b7c41d0e92a5)
+  camada de serviço determinística (IndexManager/IndexRepository)
```

**Nenhuma tabela de índice foi criada.** Não existe entidade de
índice, identidade de índice, lifecycle de índice, estado derivado
aplicativo, worker, fila, pipeline assíncrono ou cache. Criar uma
tabela materializada apenas porque o módulo se chama "Index Manager"
teria introduzido exatamente o que o §0 proíbe: uma segunda fonte da
verdade, com o problema de sincronização que vem junto.

`ARCHITECTURE = NATIVE_DB_INDEXES + DETERMINISTIC_SERVICE_LAYER`

### Componentes

| Arquivo | Papel |
|---|---|
| `alembic/versions/b7c41d0e92a5_*.py` | cria os 4 índices estruturais |
| `app/cognitive/repositories/index_repository.py` | consultas estruturais **somente de leitura** |
| `app/cognitive/services/index_manager.py` | primitivas determinísticas de localização |

`IndexRepository` é um repositório novo, não métodos novos nos
repositórios de `E3.1`–`E3.6`: acrescentar consultas àqueles arquivos
alteraria código congelado sem necessidade. As consultas aqui são de
outra natureza — localização estrutural, não regra de domínio.

`IndexManager` compõe `ObjectRepository` (identidade, reaproveitado —
`by_coid` é servido pela chave primária, nenhum índice novo) com
`IndexRepository` (demais dimensões).

## Fontes indexadas

`INDEXABLE_NOW` — quatro índices novos:

| Índice | Tabela | Forma | Por quê |
|---|---|---|---|
| `ix_cognitive_objects_clid` | `cognitive_objects` | parcial, `WHERE clid IS NOT NULL` | alta seletividade; único caminho para o **histórico completo** de um CLID |
| `ix_cognitive_objects_accessibility_created_at_id` | `cognitive_objects` | composto | baixa cardinalidade, mas atende `ORDER BY created_at, id LIMIT n` sem sort |
| `ix_cognitive_objects_revision_status_created_at_id` | `cognitive_objects` | composto, parcial `WHERE revision_status IS NOT NULL` | idem; único caminho para `SUPERSEDED` |
| `ix_provenance_records_trace_id` | `provenance_records` | parcial, `WHERE trace_id IS NOT NULL` | alta seletividade; `trace_id` é nullable e frequentemente ausente |

Os índices foram declarados **também** em `__table_args__` dos
modelos, e não apenas na migração. Sem isso, `Base.metadata` divergiria
do banco e um `alembic revision --autogenerate` futuro emitiria
`DROP INDEX` para todos eles. Um teste de integração (`IX5`) assevera
essa sincronia com `compare_metadata`.

### Fontes deliberadamente não indexadas

| Fonte | Classificação | Justificativa |
|---|---|---|
| `lineage_edges.relation_type` | `NOT_USEFUL_NOW` | 6 valores; navegação já é por `parent_coid`/`child_coid`, ambos já indexados desde E3.3 |
| `relationships.relationship_type` | `DEFERRED_TO_SEARCH` | 5 valores; `source_coid`/`target_coid` já indexados, e o índice parcial de unicidade ativa já cobre o padrão `(source, target, type) WHERE retired_at IS NULL` |
| `transformation_records.input_refs`/`output_refs` | `DEFERRED_TO_SEARCH` | são JSON; indexá-los exigiria GIN e um contrato de consulta que pertence a `E3.8` |
| `provider_id`, `model_id`, `session_id`, `correlation_id`, `actor_id` | `NOT_USEFUL_NOW` | nenhum caso de localização estrutural demonstrado; indexar por antecipação é a otimização prematura que o §21 proíbe |
| conteúdo textual | `OUT OF SCOPE` | `CognitiveObject` não tem payload — `FULL_TEXT_INDEX`, `EMBEDDING_INDEX` e `VECTOR_INDEX` ficam fora de escopo por ausência de objeto a indexar, não por decisão de conveniência |
| história causal | `DEFERRED_TO_CAUSAL_HISTORY` | `CausalHistory`/`CausalHistoryEvent` são de `E3.9` |

## Primitivas de navegação

Cinco, e só cinco:

```text
by_coid(coid)                      → CognitiveObject | None
by_clid(clid)                      → list[CognitiveObject]
by_accessibility(state, limit=)    → list[CognitiveObject]
by_revision_status(status, limit=) → list[CognitiveObject]
by_trace_id(trace_id)              → list[CognitiveObject]
```

Todas aceitam `include_deleted`, espelhando a semântica de soft delete
já estabelecida em `E3.1` — não redefinida aqui. Todas devolvem em
ordem determinística `created_at ASC, id ASC` (convenção canônica desde
`E3.1.2`), nunca ordem indefinida do banco.

`by_relationship_type` e `by_lineage_relation` **não** foram
implementadas: `RelationshipRepository.by_type`/`outgoing`/`incoming`
e `LineageRepository.list_children`/`list_parents` já existem e fazem
exatamente isso. Duplicá-las no Index Manager seria reimplementar
lógica existente.

## Index vs Search

`E3.7` fornece primitivas determinísticas; `E3.8` fará busca. Não há,
e não deve haver aqui: query language, busca textual, ranking, escore
de relevância, similaridade semântica, embeddings, base vetorial, RAG,
busca fuzzy, busca em linguagem natural, query planner próprio ou
recuperação via LLM. Consultas compostas e exploração pertencem a
`E3.8`.

## Index vs Metadata

`E3.6.2`/`E3.6.2a` congelaram `COGNITIVE_DOMAIN_METADATA_PRIMITIVE =
NONE`. O Index Manager consome **estruturas tipadas já existentes** —
`CognitiveObject` (COID/CLID), `AccessibilityState`, `RevisionStatus`,
`ProvenanceRecord` —, nunca um saco de metadata livre. Nenhum modelo,
tabela, repositório, manager, coluna, dicionário arbitrário ou blob
JSON de metadata foi criado.

## Existência, persistência, acessibilidade, localizabilidade

Quatro coisas distintas, e o módulo preserva a distinção:

```text
NOT RETURNED BY INDEX != DOES NOT EXIST
INDEX MISS            != COGNITIVE ERASURE
```

Um objeto `CAUSALLY_EXTINCT` continua localizável por
`by_accessibility(CAUSALLY_EXTINCT)` e por `by_coid`. Um objeto
soft-deleted some das consultas padrão e volta com
`include_deleted=True`. Mudar `AccessibilityState` move o objeto entre
consultas — nunca o destrói. Testes `I4`, `I4b`, `I10`, `I10b`.

### Accessibility

O índice **estrutural reflete o patrimônio persistido**: todos os
quatro estados são indexados e localizáveis. A decisão de exposição —
o que retornar a quem, sob qual política — não é do Index Manager;
filtrar é responsabilidade do chamador, e em `E3.8` em diante, de
política explícita. Isso mantém a garantia de que transição de
acessibilidade nunca é destruição de patrimônio.

### Revision status

`INDEX_CURRENT = TRUE`, `INDEX_SUPERSEDED = TRUE`. `SUPERSEDED`
continua patrimônio histórico e permanece estruturalmente localizável;
preferir `CURRENT` é decisão de camadas superiores.

**Achado de planner, registrado por honestidade**: para
`revision_status = 'current'`, o PostgreSQL prefere o índice único
parcial de `E3.4.1`
(`uq_cognitive_objects_one_current_per_clid`, restrito a
`revision_status = 'current'` e portanto muito menor) ao índice novo
deste módulo. Isso é comportamento correto — o índice de `E3.7`
acrescenta um caminho onde não havia nenhum (`SUPERSEDED`) sem
competir com o que já existia. O teste `IX1` assevera as duas coisas
explicitamente, em vez de afirmar que o índice novo é sempre o
escolhido.

## Lineage vs Relationship

A separação congelada é preservada: não há "edge index" genérico que
colapse os dois. `LineageEdge` e `Relationship` continuam em tabelas,
repositórios e taxonomias distintas — `LineageRelation` e
`RelationshipType` são conjuntos disjuntos, asseverado no teste `I5`.
`RELATED_TO` continua simétrico e canônico conforme `E3.5.1`; nenhuma
relação inversa é criada automaticamente. Retirar uma relação
(`retired_at`) não apaga histórico: a linha continua persistida e
recuperável com `include_retired=True` (teste `I6`).

## Trace semantics

```text
trace_id != COID
trace_id != CLID
trace_id != execution_id
```

`by_trace_id` localiza objetos **através de `ProvenanceRecord`**,
nunca por um campo próprio do objeto. `trace_id` não vira entidade,
não vira lineage, não vira identidade. Dois objetos distintos podem
compartilhar o mesmo `trace_id` (teste `I7`), e dois
`ProvenanceRecord`s do mesmo objeto com o mesmo `trace_id` devolvem o
objeto uma única vez (`I7b`). `CognitiveExecution` não foi criada —
continua deferida a `E7`.

## Storage principle

```text
LOGICAL IMMUTABILITY != PHYSICAL DUPLICATION
```

O índice não copia objetos. `IndexRepository` devolve as próprias
entidades persistidas — o teste `I13` assevera identidade de objeto
(`is`), não igualdade. Nada é materializado. Nenhum transcript,
prompt, resposta, payload de provider ou conteúdo arbitrário é
armazenado; `TRANSCRIPT_AUTO_STORAGE = NONE`, verificado no teste
`IX6` por inspeção do schema real (o conjunto de colunas de
`cognitive_objects` é exatamente o de `E3.6`, e nenhuma tabela nova
existe).

## Identidade e lifecycle

Nenhum `IndexID` foi inventado. COID continua identidade do objeto,
CLID continua identidade de continuidade; um índice é mecanismo de
acesso, não identidade cognitiva. O índice não tem `CURRENT`/
`SUPERSEDED`, não tem `AccessibilityState`, não tem lineage e não tem
provenance própria.

## Rebuild

Não existe estado derivado aplicativo, portanto **não existe API
`rebuild()`** — inventar um método só para ter um método chamado
`rebuild` seria API artificial. A semântica de reconstrução é
satisfeita pelo mecanismo nativo:

```text
downgrade(0460b6556563)  →  índices destruídos, patrimônio intacto
upgrade("head")          →  índices recriados, resultados equivalentes
```

Isso é determinístico, idempotente, não cria fato cognitivo algum e
não altera COID, CLID, lineage, relationship, provenance,
transformations, `AccessibilityState` ou `RevisionStatus`. O teste
`IX3` executa exatamente o roteiro do §29 (criar patrimônio → índices
presentes → destruir **somente** os índices → confirmar patrimônio
intacto e consultas ainda corretas → recriar → confirmar equivalência),
e o `IX4` confirma que dois ciclos completos devolvem o mesmo conjunto
de índices.

Durante a janela sem índices, as consultas continuam **corretas** —
apenas mais lentas. Essa é a prova operacional de que o índice é
otimização, não fonte da verdade.

## Consistency

```text
SOURCE TRANSACTION COMMIT  =>  STRUCTURAL INDEX CONSISTENT
```

Índices nativos são mantidos pelo próprio PostgreSQL dentro da
transação da fonte. Não há eventual consistency, background worker,
fila, event bus, polling ou cron — nada disso foi introduzido. Teste
`IX7`.

## Concorrência

`CONCURRENCY_INVARIANT = NONE_NEW`. Sem estado derivado aplicativo e
sem escrita, o Index Manager não introduz invariante concorrente novo:
a atomicidade dos índices é responsabilidade do banco, dentro da
mesma transação que escreve a fonte. Nenhum teste de threads foi
escrito para este módulo — inventar um apenas para cumprir tradição
não provaria nada. Os testes de concorrência de `E3.3.1`, `E3.4.1`,
`E3.5.1` e `E3.6` continuam valendo e passando.

## Migração e reversibilidade

`b7c41d0e92a5`, aditiva, linear sobre `0460b6556563`. Nenhuma migração
publicada foi editada.

```text
MIGRATION_REVERSIBILITY  = REVERSIBLE
DOWNGRADE_GUARD_REQUIRED = NO
```

Justificativa, não suposição: a migração cria **apenas índices**.
Nenhuma tabela, coluna, constraint, default ou dado. Portanto

```text
DROPPING AN INDEX != DROPPING COGNITIVE HISTORY
```

e o `downgrade()` remove otimização de acesso, jamais distinção
cognitiva. Guard só quando há perda semântica possível — foi o caso de
`f11551e97026` (Relationship, `E3.5.2`) e `0460b6556563` (Provenance,
`E3.6.1`), onde o downgrade destruiria fatos históricos
irrecuperáveis. Perda de performance não é perda cognitiva; criar
guard aqui por reflexo seria ruído. `IX3` prova a afirmação com dados
reais no banco durante o downgrade.

## Performance

```text
PERFORMANCE_GATE = STRUCTURAL
```

Não é gate de escala de produto. O teste `IX1` popula ~3000 objetos e
~3000 registros de proveniência, roda `ANALYZE` para que o planner
tenha estatísticas reais, e usa `EXPLAIN ANALYZE` para confirmar que
cada índice criado é de fato escolhido no padrão de consulta que
motivou sua criação. Onde o planner prefere um índice pré-existente, o
teste assevera essa preferência em vez de forçar a conclusão desejada.

## Provider neutrality

`PROVIDER_NEUTRAL = PASS`. Nenhum SDK de provider é importado; nenhum
embedding, índice vetorial ou lógica específica de modelo existe.
`provider_id`/`model_id` permanecem strings estruturais persistidas e
**não** foram indexados nesta entrega.

## Deferred

```text
COGNITIVE_METADATA             = NOT_AUTHORIZED (E3.6.2)
SEARCH_ENGINE                  = E3.8
CAUSAL_HISTORY                 = E3.9
ARCHAEOLOGICAL_TRACE_SEMANTICS = E3.9
PHYSICAL_TRACE_PROPAGATION     = DEFERRED
CAUSAL_HISTORY_INDEX           = DEFERRED_TO_E3_9_OR_LATER
COGNITIVE_EXECUTION            = E7
MULTI_AI_ORCHESTRATION         = E7
FULL_TEXT_SEARCH               = DEFERRED
VECTOR_SEARCH                  = DEFERRED
EMBEDDINGS                     = DEFERRED
```

Nenhum `observed_at`, `propagation_delay`, lente causal, modelo físico
de sinal ou semântica de histórico de eventos foi criado. `E3.7`
apenas evita decisões que impossibilitem `E3.9` depois: como o índice
é derivado e não carrega semântica temporal própria, a distinção
`event time` × `observation/access time` permanece inteiramente
disponível para quem for implementá-la.

## Interpretação COUT

O índice facilita acessibilidade; o índice não cria realidade
cognitiva. Tornar uma distinção localizável é operação sobre o
observador, não sobre a distinção — a mesma disciplina que separa
`AccessibilityState` de existência desde `E3.6`. Destruir o índice
empobrece o acesso e não toca no patrimônio; é a formulação
operacional, verificável por teste, de que o mapa não é o território.

## Testes

- **Unitários** (`tests/unit/cognitive/services/test_index_manager.py`,
  18): `I1` identidade estrutural; `I2` CLID com múltiplas revisões;
  `I3` `CURRENT` e `SUPERSEDED`; `I4`/`I4b` acessibilidade ≠
  existência; `I5` lineage ≠ relationship; `I6` retire não apaga
  histórico; `I7`/`I7b`/`I7c` semântica de `trace_id`; `I8` índice não
  cria objeto; `I9` índice não muta a fonte; `I10`/`I10b` ausência não
  apaga a fonte; `I13` sem duplicação; `limit`; ordenação
  determinística.
- **Integração PostgreSQL**
  (`tests/integration/cognitive/test_index_integration.py`, 7): `IX1`
  evidência de planner; `IX2` round-trip do serviço; `IX3` gate de
  destruição/recriação; `IX4` ciclo idempotente de migração; `IX5`
  metadata sincronizado; `IX6` sem tabela nova e sem transcript; `IX7`
  consistência transacional.

`I14` (provider neutrality) e `I15` (transcript storage) são
verificados estruturalmente — por ausência de import de SDK e por
inspeção do schema real em `IX6` — e não por teste unitário
tautológico.

Estado: 382 unitários cognitivos, 44 de integração cognitiva, suíte
completa sem regressão E1/E2, `app.cognitive` em 100% de cobertura.
