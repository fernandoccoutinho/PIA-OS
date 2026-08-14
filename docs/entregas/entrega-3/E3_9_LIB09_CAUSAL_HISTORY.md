# E3.9 / LIB-09 — CausalHistory

## Objetivo

Representar **história causal preservada** — não um log de aplicação.
A diferença é operacional, não retórica: um log registra o que o
sistema fez; esta camada registra o que o PIA *preservou* sobre a
trajetória de uma distinção, com causalidade declarada explicitamente
e com a incompletude assumida honestamente.

```text
distinção → transformação/transmissão → preservação ou perda de
acessibilidade → rastro histórico
```

## Contrato

Autoridade estrutural: `E3_DOMAIN_MODEL_DRAFT.md`, seção "3.
CausalHistory / CausalHistoryEvent". O Draft define
`history_id`, `subject_ref`, `events` para a história e
`event_id`, `history_ref`, `event_type`, `actor_ref`, `payload_ref`,
`created_at` para o evento, mais a regra de append-only.

### Concretizações que o Draft delega a E3.9

| Draft | Implementado | Justificativa |
|---|---|---|
| `subject_ref: COID \| distinction_id` | `subject_coid` FK → `cognitive_objects.id` | `CognitiveDistinction` está `DEFERRED` desde `E3.5`; mesma decisão já tomada em `E3.6` para `ProvenanceRecord.coid` |
| `event_type: str  # vocabulário fechado em E3.9` | `CausalEventType` = `CREATED`, `TRANSFORMED`, `COMPARED`, `ACCESSED` | exatamente os quatro exemplos do Draft; ampliar exige EDR |
| `actor_ref: ProvenanceRecord ref?` | FK nullable → `provenance_records.id` | referência, nunca cópia |
| `payload_ref: object?` | `String(512)` nullable | referência opaca; `CAUSAL_TRACE != TRANSCRIPT` |

### Duas adições além da lista literal de campos

Ambas documentadas em vez de silenciosas, mesmo padrão de
`ProvenanceRecord.coid` em `E3.6` ("novo, não está no Draft").

**`predecessor_event_id`** — o próprio Draft exige que "correção de um
evento histórico é um novo evento **que referencia o anterior**". Sem
uma referência evento→evento, essa referência não teria onde existir,
e a única forma de ligar dois eventos seria inferir causalidade da
ordem de `created_at` — proibido. `None` significa "nenhum predecessor
registrado", nunca "não houve predecessor".

**`occurred_at`** — tempo do evento, distinto do tempo de registro.
`NULL` significa exatamente "o PIA não sabe quando ocorreu", e **não é
preenchido com `created_at` por conveniência**. Sem este campo, um
evento sobre um fato passado seria indistinguível de um fato ocorrido
no instante do registro, e o sistema estaria afirmando implicitamente
algo que não sabe.

## Semântica temporal

```text
EVENT TIME (occurred_at, nullable)  !=  REGISTRATION TIME (created_at)
OBSERVATION_TIME_FIELD      = DEFERRED
PHYSICAL_TRANSMISSION_TIME  = DEFERRED
```

`created_at` já é tempo de registro (`server_default=now()`), então
nenhum `observed_at` foi criado — o Draft não o prevê e a metáfora
sozinha não justificaria um campo. `occurred_at <= created_at` é o
caso normal de um rastro arqueológico, mas **não é imposto**: exigir a
desigualdade seria o sistema afirmar conhecimento que não tem sobre
relógios externos.

## Causalidade é declarada, nunca inferida

```text
TEMPORAL_PRECEDENCE != CAUSAL_PREDECESSOR
```

`t(A) < t(B)` não implica `A → B`. Nenhuma consulta deste módulo
deriva parentesco de `created_at`; `predecessors()`/`successors()`
seguem exclusivamente `predecessor_event_id`. Ordenar eventos por
tempo de registro é **apresentação**, e o Draft pede isso
explicitamente ("ordenados por created_at, nunca reordenados
retroativamente") — apresentação não é afirmação causal. Teste `CH8`.

### Política de ciclos

```text
CYCLE_PROTECTION = STRUCTURAL
```

Não foi copiada de `LineageEdge` (`SELF_ONLY`) por hábito. Aqui a
proteção é estrutural: a tabela é append-only e a FK exige que o
predecessor **já exista** no momento do INSERT, então toda aresta
aponta para um evento anterior — o grafo é um DAG por construção, e
não há operação de update capaz de fechar um ciclo depois. O único
caso que a construção não cobre é auto-referência dentro do próprio
INSERT, barrada por `CheckConstraint`
(`ck_causal_history_events_no_self_predecessor`) e por guarda de
domínio no repositório.

### Múltiplos caminhos

```text
MULTIPLE_CAUSAL_PATHS = SUPPORTED
```

Vários eventos podem declarar o mesmo predecessor — ramificação
legítima, não conflito a resolver. O módulo **não** elege um caminho
como "o verdadeiro". Testes `CH19`/`CH15b`.

## Fronteiras

| | Responde | E3.9 faz |
|---|---|---|
| `ProvenanceRecord` | de onde veio, quem produziu, sob qual contexto | **referencia** por `actor_ref`; não copia provider/model/session/agent |
| `TransformationRecord` | transformação declarada entre referências | separado; a queda e a fragmentação podem ser transformações, mas a história que as conecta não redefine `TransformationRecord` |
| `LineageEdge` | continuidade/derivação entre objetos | separado; história causal não é linhagem |
| `Relationship` | relação semântica | separado; `SUPPORTS` não vira `CAUSES`, `RELATED_TO` não vira `CAUSAL_PARENT`, `REFERENCES` não vira transmissão |
| `RevisionStatus` | estado na continuidade | intocado |
| `AccessibilityState` | condição de acessibilidade | **intocado** — nenhuma transição automática |

```text
SUPERSEDED != INACCESSIBLE
CURRENT != ONLY HISTORICALLY REAL STATE
CAUSALLY_EXTINCT != SUPERSEDED
```

### Accessibility

```text
NO AUTOMATIC ACCESSIBILITY TRANSITION
FULL_ACCESSIBILITY_MATRIX = E4
```

`E3.9` não altera `AccessibilityState` de ninguém. A ligação futura
— disponibilidade de rastro causal como *evidência* para decisões de
acessibilidade — fica registrada como direção, não implementada. Isso
importa porque `E3.6` documentou que a exigência de `reason` para
`CAUSALLY_EXTINCT` era um proxy interino à espera de
`CausalHistoryEvent`: o mecanismo agora existe, mas ligá-lo à
transição é decisão de `E4`, não efeito colateral desta entrega.

## Source of truth

```text
CAUSAL_HISTORY_SOURCE_OF_TRUTH = TRUE   (para os fatos registrados)
RECORDED_CAUSAL_HISTORY != COMPLETE_HISTORY_OF_REALITY
```

Diferente de Index (`E3.7`) e Search (`E3.8`), que são derivados e
reconstruíveis, a história causal **é** dado de origem: nada mais no
sistema preserva esses fatos. Isso não significa verdade ontológica
absoluta — significa fonte persistida do que o PIA registrou. Podem
existir eventos reais sem rastro preservado, e o sistema representa
essa incompletude em vez de escondê-la.

## Os três regimes COUT

### Regime A — rastro preservado (Galaxy Trace)

Metáfora arquitetural, **sem física**. Uma fonte em `S0` evolui para
`S1`; `S1` passa a ser o estado corrente, e ainda assim o rastro
causal preservado sobre `S0` continua acessível no presente — a
observação de agora carrega informação legítima sobre um estado
passado.

```text
COUT-CH-1  PRESENT OBSERVATION MAY ACCESS PAST STATE
COUT-CH-2  CURRENT != ONLY HISTORICALLY ACCESSIBLE STATE
```

Nada de relatividade geral, geodésicas, cosmologia, CLEO, LOP, óptica
ou tempo de viagem. A lente gravitacional entra apenas para mostrar
que **uma fonte pode ter múltiplos caminhos causais** —
`GRAVITATIONAL_LENSING = ANALOGY_ONLY`. Teste `CH15`.

### Regime B — extinção da distinção (Broken Glass)

Cenário abstrato; a palavra "copo" não vira dado de domínio. `G0` é um
objeto organizado; transformações sucessivas levam a `G3`, um estado
que já não preserva a distinção que definia `G0`. O ponto não é o
desaparecimento da matéria — o substrato pode continuar existindo. O
que se perde é a **organização** que permitia identificar aquilo como
aquilo.

```text
COUT-CH-3   MATERIAL PERSISTENCE != DISTINCTION PERSISTENCE
COUT-CH-4   DISTINCTION EXTINCTION != HISTORICAL ERASURE
COUT-CH-10  TRANSFORMATION MAY PRESERVE SUBSTRATE WHILE DESTROYING A DISTINCTION
```

E o módulo não inventa identidade através da transformação: registrar
que `G0` originou estados posteriores **não** afirma que esses estados
"ainda são" `G0`. Cada estado é objeto próprio; a continuidade
ontológica, se houver, é decidida por `LineageEdge`/
`TransformationRecord`, não por `E3.9`. Testes `CH16`/`CH17`.

### Regime C — desconhecido irrecuperável

Sem rastro registrado, o sistema devolve ausência — não reconstrução.

```text
COUT-CH-5  NO PRESENT TRACE != NEVER EXISTED
COUT-CH-6  NO PRESENT TRACE != AUTHORIZATION TO ASSERT PAST EXISTENCE
COUT-CH-8  RECORDED HISTORY != COMPLETE HISTORY OF REALITY
```

`history_for()` devolve `None` e `events_for()` devolve `[]`, e
**nenhuma das duas cria história implicitamente** — ler nunca
materializa. Criar história é operação explícita (`ensure_history()`).
Lacuna causal não é preenchida por imaginação nem por inferência
silenciosa. Teste `CH18`.

## Append-only e o registro como rastro

```text
APPEND_ONLY = TRUE
COUT-CH-9   HISTORICAL RECORD IS ITSELF A PRESERVED TRACE
```

`update()`/`delete()` sempre rejeitam, para história e para evento
(`PIA-8020`). Corrigir um fato histórico é `correct()`: anexar um
evento novo que referencia o anterior, exatamente como o Draft
determina. O evento corrigido permanece intacto e recuperável.

Isso tem uma consequência que o módulo trata explicitamente: **não se
simula a extinção de um rastro apagando o registro**. Se o PIA já
registrou um evento, esse registro passou a ser ele próprio um rastro
histórico; apagá-lo destruiria justamente a evidência que o sistema
deveria preservar. Testes `CH4`/`CH5`/`CH20`/`CHI5`.

## Migração e reversibilidade

`c9a3f61b74d2`, aditiva, linear sobre `b7c41d0e92a5`. Nenhuma migração
publicada foi editada.

```text
MIGRATION_REVERSIBILITY = CONDITIONALLY_REVERSIBLE
DOWNGRADE_GUARD = SIM, embutida no próprio downgrade()
```

Tabelas vazias → downgrade permitido. Com qualquer história registrada
→ recusado **antes de qualquer alteração estrutural**, com
`CAUSAL_HISTORY_DOWNGRADE_SEMANTICALLY_BLOCKED`. Diferente de `E3.7`,
onde dropar índice não é dropar história, aqui o downgrade apagaria
fatos que nenhum outro lugar preserva.

A guarda vive **dentro** deste `downgrade()`, e não numa migração
posterior separada como em `E3.5.2`/`E3.6.1`. A diferença é
deliberada: naqueles casos a migração original já estava publicada e a
disciplina do projeto proíbe editá-la, o que obrigava a uma
migração-guarda nova. Aqui a migração nasce com a guarda — uma segunda
migração no-op só para replicar o formato seria ruído. Testes `CHI6`
(vazio permite) e `CHI7` (com dado bloqueia, censo idêntico depois).

## Concorrência

```text
CONCURRENCY_INVARIANT = NO_LOST_APPEND
```

O invariante real aqui não é exclusividade — append-only não tem
last-write-wins a proteger. É **nenhuma perda**: dois appends
simultâneos devem ambos sobreviver. Testado com duas threads, duas
sessões/conexões independentes e barreira, contra PostgreSQL real
(`CHI3`). Nenhum lock foi adicionado, porque nenhum invariante o
exige.

## Navegação

`events_for`, `predecessors`, `successors`, `roots` — um salto,
explícito. Não há query language de grafo, caminho mais curto,
centralidade, ranking causal, score de influência ou caminho inferido.

```text
GRAPH_ENGINE = DEFERRED      CAUSAL_INFERENCE = DEFERRED
CAUSAL_SCORING = DEFERRED
```

## Storage, metadata, provider

```text
TRANSCRIPT_AUTO_STORAGE = NONE
COGNITIVE_DOMAIN_METADATA_PRIMITIVE = NONE   (E3.6.2, preservado)
PROVIDER_NEUTRALITY = PASS
```

`payload_ref` é referência opaca de 512 caracteres, nunca conteúdo.
Nenhum `metadata: dict` foi introduzido. Nenhum SDK de provider é
importado, e nenhum campo específico de provider existe nas tabelas de
história — o vínculo com agentes se dá por referência a
`ProvenanceRecord`. `MULTI_AI_ORCHESTRATION` continua em `E7`;
nenhuma `CognitiveExecution` foi criada. Verificado por inspeção do
schema real (`CHI9`) e do código (`CH23`/`CH24`).

## Índices

Três, criados junto com as tabelas: `subject_coid` (único, um sujeito
tem no máximo uma história), `history_id` e `predecessor_event_id` —
todos servindo FK e navegação declarada. Nenhum índice especulativo.
Index e Search continuam derivados, read-only e **não** fonte da
verdade; `E3.8` não foi alterado para acomodar `E3.9`.

## Deferred

```text
PHYSICAL_PROPAGATION = DEFERRED     PHYSICAL_TRACE_MODEL = DEFERRED
GRAVITATIONAL_LENSING = ANALOGY_ONLY
GR / CLEO / LOP = NOT IMPLEMENTED
CAUSAL_INFERENCE / CAUSAL_SCORING / GRAPH_ENGINE = DEFERRED
OBSERVATION_TIME_FIELD = DEFERRED
COGNITIVE_EXECUTION / MULTI_AI_ORCHESTRATION = E7
FULL_ACCESSIBILITY_MATRIX = E4
```

## Testes

- **Unitários**
  (`tests/unit/cognitive/services/test_causal_history_manager.py`, 22):
  `CH1`-`CH24`, incluindo Galaxy Trace (`CH15`), múltiplos caminhos
  (`CH19`), Broken Glass (`CH16`/`CH17`), não-fabricação (`CH18`),
  timestamp não gera causalidade (`CH8`), tempo de evento anterior ao
  registro (`CH9`), correção por anexo, e append que não muta
  anteriores (`CH20`).
- **Integração PostgreSQL**
  (`tests/integration/cognitive/test_causal_history_integration.py`, 9):
  round-trip; constraints do banco como autoridade final; concorrência
  real de append; leitura com zero escritas; imutabilidade de eventos
  anteriores; downgrade permitido com tabela vazia; **downgrade
  bloqueado com história registrada, sem perda**; metadata sincronizado;
  ausência de colunas de transcript.

Estado: 423 unitários cognitivos, 58 de integração cognitiva, suíte
completa sem regressão E1/E2, `app.cognitive` em 100% de cobertura.
