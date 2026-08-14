# E3.10 / LIB-10 — Integrity Manager

## Escopo

Camada **read-only** de auditoria global da Biblioteca Cognitiva.
Responde a uma pergunta e só a ela:

> O patrimônio cognitivo persistido continua satisfazendo os
> invariantes estruturais e históricos **atualmente declarados** pelo
> PIA-OS?

```text
INTEGRITY  = OBSERVATION + VERIFICATION + DIAGNOSIS
INTEGRITY != DECISION + REPAIR
```

O módulo **detecta, localiza, classifica e reporta**. Não repara, não
governa, não arbitra, não sincroniza, não resolve conflito, não muda
política, não toca no Kernel e não inventa história.

```text
INTEGRITY_MANAGER          = E3.10
AUTOMATIC_REPAIR           = NOT_IMPLEMENTED
AUTO_DESTRUCTIVE_REPAIR    = FORBIDDEN
REPAIR_POLICY              = OUT_OF_SCOPE_E3_10
GOVERNANCE_ENGINE          = OUT_OF_SCOPE_E3   (E4)
COMPLIANCE_CASE_MANAGEMENT = FUTURE
SYNCHRONIZATION            = E3.11
MULTI_AI_ORCHESTRATION     = E7
```

## Arquitetura

```text
IntegrityRepository (leitura pura)
        ↓
IntegrityManager (classificação)
        ↓
IntegrityReport { findings, audited_at, scope }  — transitório
```

`MIGRATION_REQUIRED = NO`. Nenhuma tabela, nenhum estado persistido,
nenhum cache, nenhum daemon, nenhum scheduler, nenhum graph DB.
Findings e reports vivem apenas na chamada que os produziu.

`ERROR_CODES = NONE`. Um ciclo encontrado é **resultado válido** da
auditoria, não exceção — `IntegrityCode` é um vocabulário de
diagnóstico (`INTEGRITY-LIN-001`, ...), deliberadamente fora do
catálogo `PIA-8xxx`, que continua reservado a falhas de execução.

### Complexidade

Detecção de ciclo: DFS **iterativo** com coloração
branco/cinza/preto, `O(V + E)` em tempo e `O(V)` em memória.
Iterativo de propósito: a versão recursiva estouraria o limite de
recursão do Python em cadeias longas, e um `RecursionError` durante
uma auditoria seria a pior forma possível de "resultado". A ordem de
iteração segue a leitura determinística do banco (`created_at ASC,
id ASC`), então o mesmo patrimônio devolve sempre o mesmo ciclo.

`find_cycle()` é **função pura** — recebe adjacência, devolve caminho.
É o que permite testá-la exaustivamente, inclusive com grafos que
nenhuma API do PIA conseguiria criar, sem corromper banco.

## Invariantes auditados

| Código | Invariante | Origem |
|---|---|---|
| `INTEGRITY-LIN-001` | ciclo no grafo de linhagem (`FULL_DAG`) | débito que `E3.3` deixou para `E3.10` |
| `INTEGRITY-LIN-002` | self-link de linhagem | `E3.3` |
| `INTEGRITY-LIN-003` | endpoint de linhagem pendente | `E3.3` |
| `INTEGRITY-REL-001` | self-link de relação | `E3.5` |
| `INTEGRITY-REL-002` | `RELATED_TO` fora da ordem canônica | `E3.5.1` |
| `INTEGRITY-REL-003` | duplicidade de relação **ativa** | `E3.5.1` |
| `INTEGRITY-REL-004` | endpoint de relação pendente | `E3.5` |
| `INTEGRITY-VER-001` | `COUNT(CURRENT) <= 1` por CLID | `E3.4.1` |
| `INTEGRITY-PRV-001` | `ProvenanceRecord` com `coid` pendente | `E3.6` |
| `INTEGRITY-CAU-001` | ciclo no grafo causal global | `E3.9`/`E3.9.1a` |
| `INTEGRITY-CAU-002` | evento predecessor de si mesmo | `E3.9` |
| `INTEGRITY-CAU-003` | mais de uma história por sujeito | `E3.9.1` |
| `INTEGRITY-CAU-004` | referência causal pendente | `E3.9` |

### Deliberadamente não auditados

- **`RELATIONSHIP_DAG = NOT_APPLICABLE`.** Relações podem formar
  ciclos legitimamente (`A RELATED_TO B`, `B RELATED_TO A` é o caso
  trivial), e relações contraditórias entre os mesmos objetos são
  permitidas — `RelationshipEngine` nunca arbitrou conflito.
- **Ordem temporal.** `TEMPORAL_PRECEDENCE != CAUSALITY`: nenhum
  finding nasce de `created_at`/`occurred_at` parecerem "fora de
  ordem". Não existe invariante temporal congelado a auditar.
- **`provider_id`/`model_id` ausentes.** Opcionais por contrato desde
  `E3.6`, inclusive para `actor_type = AGENT`.
- **Limitações deferidas conhecidas.** `input_refs`/`output_refs` de
  `TransformationRecord` e o bypass de `add()`/`create()` herdados em
  `LineageRepository` são limitações **explicitamente aceitas**;
  transformá-las em corrupção porque `E3.10` as desejaria mais fortes
  seria reclassificar decisão como defeito.
  `KNOWN_DEFERRED_LIMITATION != INTEGRITY_VIOLATION`.

## Matriz DB / Application / Audit

Existe para impedir overclaim futuro — cada garantia tem um dono.

| Invariante | DB | Aplicação | Auditoria |
|---|---|---|---|
| Lineage self-link | sim (`CHECK`) | sim (`add_edge`) | sim |
| Lineage ciclo indireto | **não** | não previne globalmente | **sim** |
| Lineage endpoint existe | sim (FK) | sim | sim (legado/import) |
| Relationship self-link | sim (`CHECK`) | sim | sim |
| Relationship ordem canônica simétrica | sim (`CHECK`) | sim | sim |
| Relationship unicidade ativa | sim (índice parcial) | sim | sim |
| `CURRENT` único por CLID | sim (índice parcial) | sim (pré-checagem) | sim |
| Uma história por sujeito | sim (índice único) | sim | sim |
| Auto-predecessor causal | sim (`CHECK`) | sim | sim |
| **DAG causal global** | **não** | `APPLICATION_STRUCTURAL_DAG` | **sim** |
| Append-only de história | **não** | sim (repositório) | indireto (via ciclo) |

As duas linhas em negrito são a razão de o módulo existir: são os
únicos invariantes que **nenhuma** outra camada garante.

`INTEGRITY_AUDIT != DB_CONSTRAINT` — auditar o DAG causal **não**
altera a classificação de `E3.9.1a`
(`DB_LEVEL_GLOBAL_DAG_GUARANTEE = FALSE`). Detectar depois não é o
mesmo que impedir antes, e o documento não promete o contrário.

## Read-only

```text
AUDIT_READ_ONLY = TRUE
DOMAIN_WRITE_COUNT_DURING_AUDIT = 0
PATRIMONY_AFTER == PATRIMONY_BEFORE
```

Provado com censo completo e ordenado de todas as sete tabelas
cognitivas, listener em `before_cursor_execute` contando qualquer
`INSERT`/`UPDATE`/`DELETE`/`TRUNCATE`, duas auditorias executadas, e
comparação do censo depois (`IA2`).

## Consistência e concorrência

```text
CONCURRENCY_RESULT = READ_COMMITTED_PER_QUERY (sem lock adicionado)
```

As consultas rodam na transação do chamador, no nível de isolamento
padrão do projeto — `READ COMMITTED`, não alterado por `E3.10`. Uma
auditoria concorrente com escritas enxerga um recorte consistente
**por consulta**, não um snapshot global do patrimônio. Prometer
`SERIALIZABLE` seria falso; quem precisar dessa garantia abre a
transação nesse nível explicitamente. Nenhum lock global foi
adicionado, porque nenhum invariante o exige.

## False-positive gate

Nada disto é corrupção por si só, e cada item tem teste:

- **Galaxy Trace** — estado `SUPERSEDED` causalmente referenciável
  enquanto outro é `CURRENT`. `PRESERVED_TRACE != CORRUPTION`.
- **Broken Glass** — distinção extinta, sujeito `CAUSALLY_EXTINCT`,
  história preservada. `DISTINCTION_EXTINCTION != CORRUPTION`,
  `HISTORICAL_EXISTENCE != CURRENT_EXISTENCE`.
- `SUPERSEDED`, `INACCESSIBLE`, `CAUSALLY_EXTINCT` — nenhum é
  corrupção.
- predecessor causal entre histórias (`E3.9.1`);
- múltiplos caminhos causais a partir da mesma origem;
- ciclo de `Relationship` permitido e relações contraditórias;
- tripla de relação recriada após `retire()`;
- `occurred_at = None`, `provider_id = None`, `model_id = None`;
- limitações deferidas conhecidas;
- patrimônio vazio.

## Epistemologia

```text
NOT_FOUND          != NEVER_EXISTED
NO_CURRENT_TRACE   != NEVER_EXISTED
MISSING_REFERENCE  != AUTHORIZATION_TO_FABRICATE
SEARCH_MISS        != NON_EXISTENCE
```

Referência pendente vira **finding**, nunca objeto fabricado. A
auditoria opera sobre o patrimônio persistido, não sobre resultados de
Search — `Index`/`Search` continuam derivados e não são fonte da
verdade.

E o limite mais importante:

```text
INTERNALLY_CONSISTENT != TRUE_ABOUT_REALITY
```

O Integrity Manager testa invariantes internos. Ele não declara
verdade ontológica. `PASS` significa "os invariantes declarados e
auditáveis estão satisfeitos" — nada além disso.

Também: `DETECTED INCONSISTENCY != AUTHORIZATION TO ERASE HISTORY`.
Um estado inconsistente pode ser parte da história observada do
sistema; detectá-lo não autoriza apagá-lo, e é por isso que
`AUTO_DESTRUCTIVE_REPAIR = FORBIDDEN` não é uma limitação a corrigir
depois, mas uma decisão.

## Integridade não é governança

O módulo detecta uma condição; **não decide o que fazer com ela**.
Decidir é governança, e governança é `E4`. Nenhum documento antigo que
mencione "repair automático" foi implementado: repair implicaria
decisão e mutação, ambas fora da fronteira atual.

Fluxo futuro reservado, **nenhuma parte executável em `E3.10`**:

```text
IntegrityFinding → ConformanceCase → Analysis → Classification →
Proposed Action / Accepted Risk / Exception → Governance Decision →
Controlled Action → Verification
```

`E3.10` implementa apenas o primeiro artefato: `IntegrityFinding`.

## Integridade não é aprendizado

```text
FINDING = OBSERVATION        FINDING != KNOWLEDGE
ERROR   = POSSIBLE_EVIDENCE  ERROR   != LEARNING
COMPLIANCE = POSSIBLE_FUTURE_EVIDENCE_SOURCE
COMPLIANCE != LEARNING_ENGINE
PIA_LEARNING_SOURCE = VALIDATED_EXPERIENCE
```

O PIA não aprende com erro como regra de aprendizado. Erro é **uma**
fonte possível de evidência — e não a principal. Sucesso repetido,
resultado superior, estabilidade, comparação entre estratégias,
feedback humano, evidência externa, descoberta causal, resultado
experimental e divergência Multi-IA também produzem evidência.

```text
LEARNING != FAILURE_RESPONSE
```

Arquitetura futura reservada, `CONTINUOUS_COGNITIVE_IMPROVEMENT =
FUTURE`:

```text
EXPERIENCE → EVIDENCE → EVALUATION → VALIDATION → LEARNING →
IMPROVEMENT PROPOSAL → GOVERNANCE → CONTROLLED EVOLUTION
```

Um caso de conformidade fechado **não** altera automaticamente regra,
política, contrato ou Kernel.

### Kernel

```text
KERNEL_SELF_MODIFICATION = NOT_AUTHORIZED
KERNEL_IMPROVEMENT       = FUTURE_CONTROLLED_PROCESS
```

Nunca `INCIDENT → KERNEL CHANGE`, nunca `FINDING → KERNEL CHANGE`,
nunca `ERROR → SELF-MODIFICATION`. Candidato a melhoria de Kernel
exige experiência validada **mais** reprodutibilidade, evidência
suficiente, generalizabilidade e aprovação de governança — nenhum
desses mecanismos existe em `E3`.

## Grafos separados

```text
LINEAGE_GRAPH   ≠   CAUSAL_GRAPH   ≠   RELATIONSHIP_GRAPH
```

Nenhum grafo universal artificial é construído. `Relationship` não
vira causalidade, `Lineage` não vira causalidade, e cada auditoria lê
seu próprio namespace.

## Corrupção legada / importada

O módulo detecta estado inconsistente ainda que tenha surgido por SQL
direto, import futuro, restore legado, versão antiga ou bug anterior.
Isso é **capacidade diagnóstica**, não autorização de bypass — e é a
razão de auditar até invariantes já impostos pelo banco: um patrimônio
restaurado pode ter chegado com índice ausente ou constraint
desabilitada.

Nos testes, corrupção é injetada por SQL direto em banco descartável
(`IA4`, `IA5`), exclusivamente em fixture. Não altera schema de
produção e não constitui precedente arquitetural.

## Storage, metadata, provider

```text
TRANSCRIPT_AUTO_STORAGE = NONE
COGNITIVE_DOMAIN_METADATA_PRIMITIVE = NONE  (E3.6.2, preservado)
PROVIDER_NEUTRALITY = PASS
```

Invariantes estruturais não precisam de conteúdo para serem
verificados. Nenhum payload, nenhum transcript, nenhum metadata bag —
`evidence` carrega identificadores e contagens, não conteúdo. Nenhum
SDK de provider é importado, e nenhuma semântica específica de
fornecedor existe.

## Fronteiras

| | |
|---|---|
| `E3.11` | Synchronization — import, export, merge, remap, sync, resolução de conflito. `E3.10` pode produzir findings que `E3.11` consuma; não antecipa nada |
| `E4` | Governança, conformidade, decisões de política, autorização de remediação, arquitetura de melhoria contínua |
| `E7` | `CognitiveExecution`, orquestração Multi-IA |
| Futuro | melhoria controlada de Kernel |
| Ainda deferidos | `CognitiveDistinction`, `CausalComparison`, `CausalClassRef` |

## Testes

- **Unitários**
  (`tests/unit/cognitive/services/test_integrity_manager.py`, 21):
  `IG1`-`IG7` sobre `find_cycle()` puro (incluindo ciclo de 1000 nós,
  para provar a ausência de `RecursionError`, e componentes múltiplos);
  caminho de reporte de **todos** os invariantes via repositório
  controlado; evidência diagnóstica estruturada; ausência de
  identidade cognitiva no finding; `status` derivado; e o
  false-positive gate sobre patrimônio real em SQLite (Galaxy Trace,
  Broken Glass, patrimônio legítimo amplo), mais detecção de ciclo
  indireto real de linhagem.
- **Integração PostgreSQL**
  (`tests/integration/cognitive/test_integrity_integration.py`, 7):
  `IA1` patrimônio amplo legítimo audita `PASS`; `IA2` read-only
  strong gate; `IA3` `FULL_DAG` sobre arestas reais; `IA4` ciclo
  causal injetado por SQL direto; `IA5` `CURRENT` duplicado injetado
  com índice temporariamente removido; `IA6` patrimônio vazio; `IA7`
  nenhuma tabela de auditoria criada.

Estado: 450 unitários cognitivos, 66 de integração cognitiva, suíte
completa sem regressão E1/E2, `app.cognitive` em 100% de cobertura.
