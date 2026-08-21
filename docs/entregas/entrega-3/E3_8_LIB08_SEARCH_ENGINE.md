# E3.8 / LIB-08 — Search Engine

## Definição

Search é **composição de consulta** sobre o patrimônio cognitivo já
persistido. A cadeia é sempre:

```text
COGNITIVE PATRIMONY → INDEX → SEARCH → RESULT SET
```

e nunca o contrário. Os invariantes congelados por este módulo:

```text
SEARCH != SOURCE OF TRUTH
SEARCH_IS_READ_ONLY = TRUE
SEARCH MISS   != NON-EXISTENCE
SEARCH RANK   != TRUTH VALUE
SEARCH RESULT != NEW COGNITIVE FACT
```

Buscar é operação de acesso. Não cria, não modifica, não valida, não
invalida e não apaga distinção alguma.

## Search vs Index

```text
INDEX  = ACCESS PATH        (E3.7 — uma dimensão por vez)
SEARCH = QUERY COMPOSITION  (E3.8 — conjunção de dimensões)
```

`IndexManager` continua sendo o caminho para localizar por uma
dimensão isolada; `SearchEngine` compõe várias numa consulta só.
Nenhuma API de `E3.7` foi reimplementada, e `IndexRepository`
permanece intocado.

`SearchRepository` existe por uma razão específica: compor a conjunção
chamando vários métodos do `IndexRepository` e intersectando listas em
Python carregaria patrimônio inteiro para a memória — exatamente o que
o §21 do módulo proíbe. Aqui a conjunção vira **uma única consulta
SQL**, resolvida pelo PostgreSQL sobre os índices que `E3.7` já criou.

```text
MIGRATION_REQUIRED = NO      NEW_INDEXES = NONE
INDEX_REUSED = ix_cognitive_objects_clid,
               ix_cognitive_objects_accessibility_created_at_id,
               ix_cognitive_objects_revision_status_created_at_id,
               ix_provenance_records_trace_id,
               cognitive_objects_pkey
```

## Query model

`SearchCriteria` — dataclass congelada, tipada e fechada. Não é
`dict[str, Any]`, não é linguagem textual, não tem parser, não tem AST
booleana e **não admite metadata filters** (proibidos por `E3.6.2`:
`COGNITIVE_DOMAIN_METADATA_PRIMITIVE = NONE`).

| Dimensão | Origem |
|---|---|
| `coid` | identidade do objeto (`CognitiveObject.id`) |
| `clid` | continuidade |
| `accessibility` | `AccessibilityState` |
| `revision_status` | `RevisionStatus` |
| `trace_id` | via `ProvenanceRecord`, nunca campo do objeto |
| `created_from` / `created_until` | janela temporal fechada sobre `created_at` |
| `include_deleted` | modificador de escopo, **não** critério |

Ausência de um critério significa *"não filtre por esta dimensão"*,
nunca um default implícito.

Pelo menos um critério é obrigatório: uma consulta sem nenhum é
varredura completa disfarçada de busca, e o módulo se recusa a
executá-la. Quem quer listar tudo tem `ObjectRepository.list()`/
`paginate()`, explícitos desde `E3.1`. `include_deleted` sozinho não
conta como critério — precisamente para não abrir essa porta lateral.

### Composição

```text
SIMPLE_TYPED_CONJUNCTION = YES
ARBITRARY_BOOLEAN_AST    = NO
OR  = DEFERRED
NOT = DEFERRED
```

`OR` não tem caso de uso demonstrado nesta fase. `NOT` transformaria a
busca em varredura geral e ampliaria a semântica muito além do que o
contrato congelado sustenta.

### Dimensões deliberadamente ausentes

`relationship_type` e `lineage_relation` **não** são dimensões de
busca. `RelationshipRepository` (`outgoing`/`incoming`/`by_type`/
`neighbors`) e `LineageRepository` (`list_children`/`list_parents`) já
resolvem navegação de arestas; expô-las aqui duplicaria APIs
especializadas e empurraria o módulo para graph engine.

```text
MULTI_HOP_GRAPH_SEARCH = DEFERRED
GRAPH_SEARCH = DEFERRED
```

A separação `LINEAGE != RELATIONSHIP` fica preservada por construção:
não existe dimensão genérica de "edge" que colapse as duas
taxonomias.

## Accessibility

```text
ACCESSIBILITY_POLICY = CALLER_EXPLICIT
```

Das três opções do §5, a escolhida é **B — o chamador fornece o filtro
explícito**. Motivo: não existe política de exposição congelada em
`E3`, e o §5 proíbe inventar política de segurança. A matriz completa
de acessibilidade pertence a `E4`; `E3.6` deliberadamente restringiu
`AccessibilityManager` ao que o Draft autoriza, e `E3.7` estabeleceu
que o índice estrutural reflete o patrimônio persistido, deixando a
exposição para camadas superiores. `E3.8` mantém a mesma linha.

Consequências, todas testadas:

```text
EXISTENCE != ACCESSIBILITY != LOCALIZABILITY
filtered_out != erased
inaccessible != deleted
no_result    != never_existed
```

Sem filtro de acessibilidade, objetos de **todos** os quatro estados —
inclusive `CAUSALLY_EXTINCT` — entram no resultado. Filtrar esconde da
resposta daquela consulta; não apaga nada. Quando `E4` definir política
de exposição, ela se aplica **acima** desta camada, sem precisar mudar
o contrato de busca.

## Revision history

```text
REVISION_POLICY = BOTH_RETRIEVABLE, NO_IMPLICIT_PREFERENCE
```

`CURRENT` e `SUPERSEDED` são igualmente recuperáveis. Sem filtro de
revisão, os dois vêm juntos — o histórico **não** é silenciosamente
apagado da resposta. Não existe "prefer current" implícito; se algum
dia existir, será ordenação/exposição, nunca destruição de resultados
históricos. `RevisionStatus` não foi alterado.

## Result model

```text
RESULT_MODEL = list[CognitiveObject]
```

Nenhum DTO de resultado foi criado, e portanto não há resultado com
identidade cognitiva, lifecycle, lineage, provenance ou persistência.
O retorno são as **próprias entidades persistidas** — o teste `S19`
assevera identidade de objeto (`is`), não igualdade.

```text
SEARCH_PERSISTENCE = NONE
```

Nenhuma tabela de histórico de busca, log cognitivo de consulta, cache
persistente ou saved search. Confirmado por inspeção do schema real:
o conjunto de tabelas é idêntico ao de `E3.7`.

## Ordering, ranking e paginação

```text
RANKING    = DEFERRED
ORDERING   = created_at ASC, id ASC (canônico desde E3.1.2)
PAGINATION = OFFSET/LIMIT
```

Não existe informação semântica no domínio atual que justifique
ranking: `CognitiveObject` não tem conteúdo, não há sinal de
relevância, e inventar score seria fabricar semântica. Nada de
embeddings, LLM scoring, similaridade, heurística de provider,
popularidade ou pesos arbitrários. **Ordenação determinística não é
ranking semântico** — a distinção está no nome dos métodos e nos
testes.

Paginação por deslocamento é suficiente nesta fase e é estável porque
a ordenação é *total* (`created_at` com desempate por `id`): páginas
não se sobrepõem, não perdem objeto, e sua união é o resultado
completo. Keyset pagination fica `DEFERRED` — não há evidência de
paginação profunda que justifique a complexidade. `count()` existe
para o chamador saber se há mais páginas sem materializar tudo.

## Search miss

`result = []` significa exatamente *"nenhum objeto satisfaz os
critérios desta consulta sob o escopo aplicado"*. Não significa que o
objeto nunca existiu. Não gera tombstone, não altera
`AccessibilityState`, não registra extinção e não infere causalidade.
Zero resultados **não** é erro — não existe exceção para conjunto
vazio.

## Erros

Um único código novo: `PIA-8019` / `SearchCriteriaError`, para
critérios malformados — nenhuma dimensão informada, `trace_id` em
branco, janela temporal invertida, `limit`/`offset` negativos.
Levantado **antes** de qualquer acesso ao banco: consulta malformada
não deve nem chegar a ser executada. Faixa verificada por inspeção
real (`PIA-8001`..`PIA-8018` em uso; `8019` era o próximo livre).

## Preservação do patrimônio

```text
SEARCH(P, Q) -> R   com   P_after == P_before
DOMAIN_WRITE_COUNT_DURING_SEARCH = 0
```

O teste `SX3` monta patrimônio heterogêneo (500 objetos, dois estados
de acessibilidade, `CURRENT` e `SUPERSEDED`, proveniências com
`trace_id`), tira um censo **completo e ordenado de todas as linhas de
todas as tabelas cognitivas**, executa sete buscas diferentes com um
listener em `before_cursor_execute` contando qualquer
`INSERT`/`UPDATE`/`DELETE`/`TRUNCATE` emitido ao banco, e compara o
censo depois. Resultado: zero escritas, censo idêntico linha a linha.

Nos unitários, `S13`/`S14`/`S15` confirmam separadamente que consultar
não cria `ProvenanceRecord`, `TransformationRecord`, `Relationship`
nem `LineageEdge`.

## Performance

```text
PERFORMANCE_GATE = STRUCTURAL
```

`SX1` popula ~3000 objetos e ~3000 registros de proveniência, roda
`ANALYZE` e usa `EXPLAIN ANALYZE` sobre a consulta composta real
(compilada a partir do próprio `SearchRepository`, não de SQL escrito à
mão para o teste). O que se assevera é a **propriedade** — o plano usa
caminho indexado e não faz varredura sequencial das tabelas quando há
alternativa indexada —, não qual índice o planner deveria preferir.
Essa é a lição de `E3.7` aplicada:

```text
TEST THE PROPERTY, NOT THE IMPLEMENTER'S PREFERRED PLAN.
```

O filtro por `trace_id` usa `EXISTS` em vez de `JOIN`: evita
multiplicar linhas quando o mesmo objeto tem vários registros de
proveniência com o mesmo trace, sem precisar de `DISTINCT` — que
atrapalharia a ordenação e o planner.

## Concorrência

```text
CONCURRENCY_RESULT = NONE_NEW
```

Busca é read-only e não mantém estado próprio: não há invariante
concorrente novo a proteger. Nenhum teste de threads foi escrito para
este módulo — inventar um por tradição não provaria nada. Os testes de
concorrência de `E3.3.1`, `E3.4.1`, `E3.5.1` e `E3.6` continuam
passando.

## Dependência invertida — não

```text
SEARCH DEPENDS ON ACCESS PATHS
PATRIMONY DOES NOT DEPEND ON SEARCH
```

Nenhum cache, materialização ou estado de busca existe, portanto o
patrimônio não pode passar a depender de resultado de consulta. Isso é
consequência direta de `SEARCH_PERSISTENCE = NONE`, e `SX4` verifica a
ausência de qualquer tabela de busca/cache/consulta.

## Provider neutrality e transcript

```text
PROVIDER_NEUTRALITY = PASS
TRANSCRIPT_AUTO_STORAGE = NONE
ARBITRARY_METADATA = NONE
```

Varredura estrutural após a implementação: zero imports de SDK de
provider em `app/`, zero campos de transcript/prompt/response, zero
dicionário arbitrário como campo de domínio. `provider_id`/`model_id`
não são sequer dimensões de busca nesta fase.

## Deferred

```text
COGNITIVE_METADATA             = NOT_AUTHORIZED (E3.6.2)
FULL_TEXT_SEARCH               = DEFERRED
VECTOR_SEARCH                  = DEFERRED
EMBEDDINGS                     = DEFERRED
SEMANTIC_SIMILARITY / RANKING  = DEFERRED
GRAPH_SEARCH / MULTI_HOP       = DEFERRED
CAUSAL_SEARCH                  = DEFERRED
OR / NOT COMPOSITION           = DEFERRED
KEYSET_PAGINATION              = DEFERRED
CAUSAL_HISTORY                 = E3.9
ARCHAEOLOGICAL_TRACE_SEMANTICS = E3.9
PHYSICAL_TRACE_PROPAGATION     = DEFERRED
COGNITIVE_EXECUTION            = E7
MULTI_AI_ORCHESTRATION         = E7
```

Busca textual, vetorial e semântica ficam fora não por conveniência,
mas por ausência de objeto a indexar: `CognitiveObject` não tem
payload, e inventar um campo de conteúdo para tornar o Search Engine
mais "útil" seria mudar o domínio para servir a ferramenta. Nenhuma
tabela de embeddings, nenhum `pgvector`, nenhum provider externo.

Nada de `observed_at`, `propagation_delay`, distância causal,
reconstrução causal, rastro físico, analogia de lente ou ranking
temporal causal foi criado. `E3.8` localiza registros históricos que
já existem; **não interpreta fisicamente por que eles chegaram ao
observador** — isso é `E3.9`.

## Testes

- **Unitários** (`tests/unit/cognitive/services/test_search_engine.py`,
  19): `S1` critério isolado; `S2` conjunção; `S3` vazio é válido;
  `S4` miss não apaga fonte; `S5`/`S6`/`S7` sem mutação de objeto,
  COID e CLID; `S8`/`S9` `CURRENT` e `SUPERSEDED`; `S10`/`S10b`
  acessibilidade e soft delete; `S11`/`S11b` `trace_id` como dimensão,
  não identidade; `S12` lineage ≠ relationship; `S13`-`S15` nenhuma
  criação de registro de domínio; `S16` ordenação determinística;
  `S17` paginação; `S18`/`S18b` critérios inválidos tipados; `S19`/
  `S20` sem persistência de resultado ou consulta; janela temporal;
  `active_dimensions()`.
- **Integração PostgreSQL**
  (`tests/integration/cognitive/test_search_integration.py`, 5): `SX1`
  plano indexado; `SX2` round-trip; `SX3` gate COUT forte; `SX4`
  ausência de estado de busca; `SX5` paginação estável.

Estado: 401 unitários cognitivos, 49 de integração cognitiva, suíte
completa sem regressão E1/E2, `app.cognitive` em 100% de cobertura.
