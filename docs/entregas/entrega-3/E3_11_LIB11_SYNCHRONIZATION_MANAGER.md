# E3.11 / LIB-11 — Synchronization Manager

## Definição

```text
SYNCHRONIZATION = COGNITIVE_PATRIMONY_TRANSMISSION
```

E, explicitamente, **não**:

```text
SYNCHRONIZATION != COPY CURRENT ROWS
TRANSMISSION    != OVERWRITE
CONFLICT_DETECTION != CONFLICT_RESOLUTION
SAME_CURRENT_STATE != SAME_CAUSAL_HISTORY
```

O pacote transporta identidade e história, não um retrato do estado
atual. Depois de `EXPORT(A) → IMPORT(B)`, o patrimônio em `B` é *o
mesmo* patrimônio — não "objetos equivalentes novos".

## Arquitetura

```text
SyncRepository (leitura determinística + inserção com id explícito)
        ↓
SynchronizationManager (classificação: novo / idêntico / conflito)
        ↓
SyncReport (transitório)  |  pacote versionado (dict serializável)
```

```text
SYNC_ARCHITECTURE   = VERSIONED_ENVELOPE + TYPE_DRIVEN_CODEC + CONFLICT_DETECTOR
SYNC_FORMAT         = pia-os.cognitive-sync
SYNC_FORMAT_VERSION = 1.0
MIGRATION_REQUIRED  = NO
ERROR_CODES         = PIA-8022 (SYNC_PACKAGE_INVALID) — apenas este
```

Nada é persistido além do próprio patrimônio importado: sem tabela de
sync, de conflito, de histórico de merge ou de política de resolução.
Conflito é **resultado**, não entidade — e não vira exceção.

## Patrimônio transmitido

Sete seções, exatamente as primitivas implementadas em `E3`:

| Seção | Tabela |
|---|---|
| `objects` | `cognitive_objects` |
| `transformations` | `transformation_records` |
| `causal_histories` | `causal_histories` |
| `lineage` | `lineage_edges` |
| `provenance` | `provenance_records` |
| `relationships` | `relationships` |
| `causal_events` | `causal_history_events` |

`CognitiveDistinction`, `CausalComparison` e `CausalClassRef`
continuam `DEFERRED` e **não** ganham seção fantasma: inventar seções
vazias para elas seria simular contrato que não existe.

## Ordem de importação

```text
IMPORT_DEPENDENCY_ORDER = derivada de Base.metadata.sorted_tables
```

Não escolhida por intuição: a ordenação topológica vem das FKs
declaradas nos modelos. Dentro de `causal_history_events` há ainda a
auto-referência `predecessor_event_id`, e o PostgreSQL valida FK por
linha na inserção — por isso os eventos passam por uma ordenação
topológica própria, que garante predecessor antes de sucessor
inclusive quando o predecessor está na história de **outro** sujeito
(`E3.9.1`: `history boundary != causal boundary`).

Evento cujo predecessor **não está no pacote** não é adiado
indefinidamente: entra na ordem natural e o banco decide. Adiar seria
inventar política.

## Formato

```text
deterministic serialization   UUID round-trip lossless
explicit format version       datetime round-trip lossless
NULL preservation             enum round-trip lossless
```

A ordenação das linhas é `created_at ASC, id ASC` — a convenção
canônica desde `E3.1.2`. Sem ordem total, dois exports do mesmo
patrimônio poderiam diferir só na ordem e a comparação canônica
perderia sentido.

A **decodificação é dirigida pelo tipo real da coluna**, não por
heurística sobre o conteúdo: `Uuid` volta como `UUID`, `DateTime`
volta como `datetime` com fuso, `Enum` volta como o membro
correspondente ao valor persistido. É o que torna o round-trip
verificável em vez de plausível.

`canonical_payload()` exclui **um único** campo, `exported_at`, e por
um motivo verificável: é o instante em que o pacote foi gerado, não um
fato do patrimônio. Qualquer outra exclusão seria relaxar a comparação
por conveniência.

## Identidade

```text
IMPORT MUST NOT REGENERATE COGNITIVE IDENTITY
```

`id`, `created_at` e `updated_at` vêm do pacote e são inseridos
explicitamente. Preservados: COID, CLID, e os ids de
`ProvenanceRecord`, `LineageEdge`, `Relationship`,
`TransformationRecord`, `CausalHistory` e `CausalHistoryEvent`.

```text
COID_PRESERVATION           = PASS
CLID_PRESERVATION           = PASS
PROVENANCE_PRESERVATION     = PASS
LINEAGE_PRESERVATION        = PASS
RELATIONSHIP_PRESERVATION   = PASS
TRANSFORMATION_PRESERVATION = PASS
CAUSAL_HISTORY_PRESERVATION = PASS
ACCESSIBILITY_PRESERVATION  = PASS
```

## Import: três resultados, nenhum deles "vencedor"

| Situação | Resultado |
|---|---|
| id ausente no destino | **novo** — aplicado |
| id presente, representação idêntica | **idempotente** — ignorado |
| id presente, representação divergente | **conflito** |

```text
same ID + same representation → already present / idempotent
same ID + different representation → CONFLICT
```

Proibido, e nenhum implementado: destino vence, origem vence,
last-write-wins, timestamp mais novo vence, prioridade de provider,
prioridade de agente, score de confiança, score COUT.

```text
CONFLICT_RESOLUTION          = NOT_IMPLEMENTED
SILENT_LAST_WRITE_WINS       = FORBIDDEN
OVERWRITE_COUNT_ON_CONFLICT  = 0
```

O `SyncConflict` carrega **as duas representações** — a que veio e a
que estava — e localiza os campos divergentes. Nenhum dos lados
desaparece do diagnóstico (`COUT-P8`: unresolved is valid).

### Atomicidade

```text
ONE IMPORT = ONE DATABASE TRANSACTION
```

Havendo qualquer conflito, **nada** é aplicado — nem os registros
perfeitamente válidos do mesmo pacote. Import parcial deixaria
linhagem incompleta, provenance pela metade ou eventos causais órfãos,
e um patrimônio meio-transmitido é pior que um import recusado. O
manager não commita: a transação é do chamador, e é isso que torna o
rollback completo possível.

Pacote malformado (formato desconhecido, versão não suportada, seção
ausente ou não-lista, registro sem `id`, id inválido, campo
desconhecido, valor de enum inexistente) é recusado **antes de
qualquer escrita**, com `PIA-8022`.

## Princípios COUT

| | |
|---|---|
| `COUT-P1` | distinção existente não desaparece silenciosamente porque o destino tem estado diferente |
| `COUT-P2` | continuidade (CLID) sobrevive à transmissão |
| `COUT-P3` | provenance nunca é apagada nem substituída em silêncio |
| `COUT-P4` | histórias distintas não são colapsadas por chegarem a estado atual parecido |
| `COUT-P5` | `TransformationRecord` e suas `declared_preservations`/`declared_losses` sobrevivem |
| `COUT-P6` | os quatro estados de acessibilidade viajam como estados existentes |
| `COUT-P7` | equivalência não autoriza deduplicação destrutiva |
| `COUT-P8` | conflito pode permanecer sem resolução |
| `COUT-P9` | COUT informa; não decide |
| `COUT-P10` | identidade cognitiva pertence ao PIA, não ao provider |

### Accessibility

```text
ACTIVE → ACTIVE      LATENT → LATENT
INACCESSIBLE → INACCESSIBLE      CAUSALLY_EXTINCT → CAUSALLY_EXTINCT
ACCESSIBILITY_POLICY = E4
```

A sincronização transmite o valor persistido e não pergunta se o
estado "deveria" ser outro. E **ausência no pacote nunca vira
`CAUSALLY_EXTINCT`**: um objeto que existe no destino e não é
mencionado pelo pacote permanece exatamente como estava.

### Não-fabricação

```text
NO TRACE != AUTHORIZATION TO FABRICATE HISTORY
```

Se o pacote não traz evidência de determinada história, nada é
inventado: nem predecessor, nem provenance, nem transformação, nem
evento passado, nem extinção inferida.

### Galaxy Trace

Múltiplos caminhos causais a partir da mesma origem chegam ao destino
**distintos**, cada um na história do seu próprio sujeito. Nenhuma
trajetória é colapsada, e nenhuma aresta causal é inferida de
timestamp — o que viaja é o predecessor explícito
(`TEMPORAL_PRECEDENCE != CAUSALITY`).

`GRAVITATIONAL_LENSING = ANALOGY_ONLY` — nenhuma física implementada.

### Broken Glass

O sujeito chega em `CAUSALLY_EXTINCT` e a história dele chega junto.

```text
DISTINCTION_EXTINCTION != HISTORICAL_ERASURE
```

O "copo" é cenário de teste e documentação, não dado especial do
domínio.

## Depois do import

```text
INTEGRITY_AFTER_IMPORT = PASS   (E3.10 audita patrimônio importado)
SEARCH_AFTER_IMPORT    = PASS   (mesmos critérios de antes do export)
INDEX_SOURCE_OF_TRUTH  = FALSE
SEARCH_SOURCE_OF_TRUTH = FALSE
```

O `IntegrityManager` é usado como **verificação diagnóstica**, jamais
como reparo: `INTEGRITY_DETECTS_DOES_NOT_DECIDE`. Nenhum índice novo
foi criado e nenhum estado de busca foi materializado — os índices de
`E3.7` continuam derivados e reconstruíveis.

## Concorrência

```text
CONCURRENCY_RESULT = NO_DUPLICATION_GUARANTEED_BY_PRIMARY_KEY
```

O invariante real identificado foi um só: dois imports simultâneos do
mesmo pacote não podem duplicar patrimônio. Nenhum lock foi
adicionado, porque a chave primária já é a autoridade — o teste
verifica o **resultado observável**: uma transação aplica, a outra
falha limpa ou não aplica nada, e o censo final é exatamente o do
pacote.

## Limites

```text
ARTIFACT_STORAGE        = DEFERRED
TRANSCRIPT_AUTO_STORAGE = NONE
PROVIDER_NEUTRALITY     = PASS
GOVERNANCE  = NOT_IMPLEMENTED
LEARNING    = NOT_IMPLEMENTED
REPAIR      = NOT_IMPLEMENTED
```

Referências externas (`payload_ref`, `evidence_refs`, `source_ref`)
viajam **como referência**: o conteúdo apontado nunca é copiado. Não há
hierarquia de arquivos, pastas de usuário, S3, Drive, OneDrive, NAS ou
armazenamento binário.

Nenhum SDK de provider é importado, e o mesmo pacote transporta
patrimônio de `provider-a`, `provider-b`, humano e origem sem provider
sem alterar a semântica de identidade.

`E3.11` também não implementa ACL, autorização de usuário,
autenticação de nuvem, criptografia ou permissões de sistema de
arquivos — mas o formato não carrega segredo algum e não abre via
lateral para burlar ACLs futuras.

```text
SYNCHRONIZATION_IS_LEARNING   = FALSE
SYNCHRONIZATION_IS_GOVERNANCE = FALSE
SYNCHRONIZATION_IS_REPAIR     = FALSE
ERROR_IS_LEARNING             = FALSE
PIA_LEARNING_SOURCE = VALIDATED_EXPERIENCE
```

Conflito é evidência de divergência, não aprendizado automático, e não
é promovido ao Kernel.

## Preflight causal (E3.11.1)

```text
CAUSAL_IMPORT_DAG_PREFLIGHT        = IMPLEMENTED
APPLICATION_STRUCTURAL_DAG         = PRESERVED
DB_LEVEL_GLOBAL_DAG_GUARANTEE      = FALSE
SYNC_LEVEL_CAUSAL_CYCLE_PROTECTION = PREFLIGHT_BEFORE_WRITE
```

`E3.9.1a` congelou `APPLICATION_STRUCTURAL_DAG = TRUE` porque, pelo
caminho autorizado original, todo predecessor já estava persistido, o
evento novo era append e nenhuma operação legítima redirecionava
aresta antiga. **`E3.11` abriu um caminho autorizado novo** — import
direto em tabela — e um caminho novo não pode enfraquecer o invariante
anterior:

```text
SYNCHRONIZATION_IMPORT MUST PRESERVE APPLICATION_STRUCTURAL_DAG
SYNCHRONIZATION MUST NOT CREATE A CAUSAL HISTORY THAT THE AUTHORIZED
SOURCE CONTRACT COULD NOT HAVE PRODUCED
TRANSMISSION != STRUCTURAL MUTATION
```

### Precedência: conflito antes do preflight (E3.11.1a)

```text
IDENTITY_CONFLICT != CAUSAL_STRUCTURAL_INVALIDITY
DIVERGENCE        != INVALIDITY
```

Ordem do import:

```text
1. validar envelope
2. classificar ids existentes
3. havendo conflito → relatório de conflito, zero escritas
4. derivar SOMENTE os registros novos
5. preflight causal sobre destino + novos elegíveis
6. escrever atomicamente
```

A classificação precede o preflight, e isso não é detalhe de ordem: na
primeira versão, uma representação divergente de um id já existente
entrava no grafo hipotético e podia fechar um ciclo que **nunca seria
aplicado** — o import devolvia `SYNC_PACKAGE_INVALID` quando o fato
real era outro, duas histórias divergindo. Divergir não é estar
corrompido:

```text
TWO HISTORIES MAY CONFLICT WITHOUT EITHER BEING DECLARED CAUSALLY INVALID
detectar que duas representações divergem != declarar uma delas inválida
```

Formulação canônica do grafo:

```text
CANDIDATE_GRAPH = DESTINATION_ACCEPTED_STATE
                + PACKAGE_RECORDS_ELIGIBLE_FOR_INSERT
```

Nunca o estado aceito do destino sobrescrito em memória pela versão
conflitante do pacote. Registros idempotentes já são arestas do
destino; registros conflitantes nem chegam ao preflight.

Antes de qualquer escrita, o import monta o **grafo candidato** e
verifica aciclicidade. Global de propósito:
`CROSS_HISTORY_PREDECESSOR = ALLOWED` e
`HISTORY_BOUNDARY != CAUSAL_BOUNDARY`, então auditar por história
isolada perderia exatamente os elos que o contrato autoriza.

Reutiliza o detector **puro** de `E3.10` (`find_cycle`, DFS iterativo
colorido, `O(V + E)`). Reutilizar a função não acopla Sync ao
`IntegrityManager` como serviço de decisão — nenhum `IntegrityReport`
é produzido nem consultado.

Pacote cíclico → `SyncPackageInvalidError` (`PIA-8022`), nenhum código
novo criado:

```text
applied_count = 0   overwrite_count = 0   destination_unchanged = TRUE
PREFLIGHT_DOMAIN_WRITE_COUNT = 0
```

**E não se apoia no banco.** O PostgreSQL garante validade de FK e
rejeição de auto-predecessor, e nada além disso — `FK + NO_SELF !=
GLOBAL_CYCLE_PROTECTION`. Qualquer afirmação anterior de que "o banco
recusaria o ciclo de qualquer forma" foi corrigida:
`ORDERING != VALIDATION`, e `topologically_ordered_events()` terminar
diante de um ciclo é robustez daquela função, nunca garantia de
integridade causal.

**Escopo.** Trata somente `CausalHistory`, porque é `E3.9.1a` que
promete `APPLICATION_STRUCTURAL_DAG`. `Lineage` mantém o que foi
congelado: `CYCLE_PROTECTION = SELF_ONLY` em `E3.3` e `FULL_DAG` de
**auditoria** em `E3.10` — nenhuma regra nova foi estendida a ele.

**Nota honesta de alcançabilidade.** Por importação *insert-only*, com
conflito abortando tudo, uma aresta do destino apontando para um
evento ainda inexistente é impedida pela própria FK — não consegui
construir, pelo caminho autorizado atual, uma composição
destino+pacote que feche ciclo sem passar por conflito. O grafo
candidato é montado globalmente mesmo assim, e `CD4` prova que a
verificação é global forjando o lado do destino. A propriedade
protegida é a do contrato, não apenas a do caminho de hoje.

## Testes

- **Unitários**
  (`tests/unit/cognitive/services/test_synchronization_manager.py`,
  19): codec por tipo de coluna (UUID, datetime, enum, `None`,
  idempotência da decodificação); `canonical_payload` excluindo apenas
  o campo transportacional; ordem de importação derivada das FKs
  reais; ordenação topológica de eventos (predecessor primeiro,
  predecessor externo, término mesmo com pacote cíclico); recusa de
  cada forma de pacote inutilizável; pacote vazio como no-op;
  relatório e conflito derivando status, contagens e campos
  divergentes.
- **Integração PostgreSQL, duas instâncias reais**
  (`tests/integration/cognitive/test_synchronization_integration.py`,
  12): a instância `B` é um **banco descartável próprio**, criado pela
  fixture — a única forma honesta de provar transmissão *entre
  instâncias*. Cobre export determinístico e versionado; round-trip
  canônico completo (gate COUT central); idempotência; conflito
  explícito sem sobrescrita, com o destino intacto; conflito abortando
  o import inteiro; Galaxy Trace e predecessor entre histórias;
  Broken Glass; não-fabricação; Integrity + Search + Index depois do
  import; neutralidade de provider; imports concorrentes; recusa de
  pacotes malformados.

Estado: 479 unitários cognitivos, 80 de integração cognitiva, suíte
completa sem regressão E1/E2, `app.cognitive` em 100% de cobertura.
