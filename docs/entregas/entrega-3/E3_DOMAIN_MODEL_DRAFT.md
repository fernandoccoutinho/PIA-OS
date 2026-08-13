# E3 — Domain Model Draft

Módulo E3.0. **Contratos/schemas propostos apenas** — nenhuma destas
classes é implementada como código nesta etapa (nenhuma tabela,
nenhuma migração, nenhum ORM real). A notação abaixo é
Pydantic/dataclass-like, para ficar diretamente traduzível para
`app.cognitive.schemas`/`app.cognitive.models` quando E3.1 começar,
mas é documentação, não implementação.

Convenções usadas: `?` = opcional; tipos entre colchetes = enum de
valores permitidos; `ref` = referência por identidade (COID/CLID/UUID),
nunca por objeto embutido.

## 0. CognitiveObject (referenciado por todas as primitivas)

A Biblioteca Cognitiva continua baseada em `CognitiveObject`. **Correção
E3.0.1**: este contrato mínimo de identidade não pertence a um módulo
de "fundamentos" separado — é implementado dentro do próprio `E3.1 =
LIB-01` (Cognitive Object + Object Repository), junto com o CRUD
completo via `BaseRepository`/`UnitOfWork` (ver
`E3_IMPLEMENTATION_SEQUENCE.md`). Nenhum outro campo de
conteúdo/domínio além do listado abaixo é definido aqui.

```text
CognitiveObject
  coid: COID                 # identidade permanente — nunca muda
  clid: CLID?                # continuidade conceitual/linhagem — pode ser None
                              # para objetos sem linhagem conhecida ainda
  accessibility: AccessibilityState
  created_at, updated_at     # herdado de BaseModel (E2)
```

Restrição de identidade: `coid` é atribuído uma única vez, na criação,
e nunca é reatribuído. `clid` pode ser `None` na criação e populado
depois (por `LIB-03 CLID Manager`) — uma única vez. **Correção
E3.1.1**: uma vez que `clid` deixa de ser `None`, ele é imutável para
aquele `CognitiveObject` — nem um valor diferente nem `None` são
aceitos depois disso, sem exceção. Uma mudança de identidade causal
suficiente para justificar outro CLID não muta este objeto: cria um
novo objeto/estado e relaciona os dois via `TransformationRecord`/
`LineageEdge` (E3.3/E3.4) — a formulação anterior deste parágrafo
("nunca substituído... sem passar por TransformationRecord/LineageEdge
explícito") sugeria ambiguamente que esses mecanismos poderiam mutar o
CLID do mesmo objeto; não podem. CLID não é campo de conveniência
editável livremente.

## 1. CognitiveDistinction

Distinção cognitiva recuperável associada a um ou mais `CognitiveObject`.

```text
CognitiveDistinction
  distinction_id: UUID
  subject_refs: list[COID]        # 1..N CognitiveObjects associados
  origin: ProvenanceRecord ref?
  representation: str?            # forma/formato da distinção — livre nesta fase
  provenance: ProvenanceRecord ref?
  lineage: list[LineageEdge] ref?
  accessibility: AccessibilityState
  causal_history: CausalHistory ref?
  transformation: TransformationRecord ref?
  equivalence_class: CausalClassRef?
  divergence_of: CognitiveDistinction ref?   # quando aplicável — não obrigatório
  created_at: datetime
```

Nota: `subject_refs` é uma lista porque uma distinção pode ser
"sobre" mais de um objeto simultaneamente (ex.: uma comparação
registrada como distinção em si). Nenhum campo aqui implica ordenação
ou score — apenas associação.

## 2. ProvenanceRecord

Propriedade: `E3.6` (`LIB-06` Metadata Manager + Provenance +
Accessibility) — não `E3.9` como o rascunho original de E3.0 sugeria
implicitamente ao agrupá-lo perto de Knowledge Provenance Engine (ver
correção em `E3_IMPLEMENTATION_SEQUENCE.md`, §"Racional da
ordenação").

```text
ProvenanceRecord
  provenance_id: UUID
  source_type: str                # ex.: "human", "agent", "import", "system" — enum fechado em E3.6, aberto aqui
  source_ref: str?
  actor_type: str                 # "human" | "agent" | "system" — nunca assume IA por padrão
  actor_id: str?
  provider_id: str?                # OPCIONAL — só populado se actor_type == "agent" e aplicável
  model_id: str?                   # OPCIONAL — idem
  session_id: str?                 # populável a partir de app.logging.context.LoggingContext
  correlation_id: str?             # idem
  evidence_refs: list[str]         # default vazio
  created_at: datetime

  # --- Campos preparatórios Multi-IA Triple-Mode (correção E3.0.1 §9) ---
  # Todos OPCIONAIS — nenhum torna um provider ou modo de orquestração
  # obrigatório. Existem para que E7 (Hypervisor) não exija migração
  # de ProvenanceRecord quando for implementado; E3 não os popula com
  # lógica própria, apenas reserva o campo.
  orchestration_run_id: str?       # identifica uma execução de orquestração (COMPETITIVE/COMPLEMENTARY/SEQUENTIAL)
  agent_role: str?                 # ex.: "generator" | "critic" | "verifier" | "synthesizer" — vocabulário de E7, não fechado aqui
  agent_instance_id: str?          # distingue instâncias do mesmo agente/role numa mesma orquestração
  agent_sequence: int?             # posição do agente numa cadeia SEQUENTIAL — irrelevante em COMPETITIVE/COMPLEMENTARY
  parent_agent_output_ref: str?    # referência ao output anterior numa cadeia SEQUENTIAL
```

Restrição explícita do prompt (§10 do módulo E3.0): `provider_id`/
`model_id` são opcionais e **nunca obrigatórios** — um
`ProvenanceRecord` de origem humana ou interna do sistema não pode
depender desses campos para ser válido. A mesma regra se estende aos
cinco campos Multi-IA acima (correção E3.0.1 §9): nenhum é obrigatório,
e nenhum torna uma IA/provider/modo de orquestração parte obrigatória
da arquitetura. Validação de "obrigatoriedade condicional" (ex.: exigir
`provider_id` quando `actor_type == "agent"`, ou `agent_sequence`
quando `orchestration_run_id` está presente e o modo é `SEQUENTIAL`) é
decisão de `E3.6`, não travada aqui.

## 3. CausalHistory / CausalHistoryEvent

Propriedade: `E3.9` (`LIB-09` Knowledge Provenance Engine +
CausalHistory).

```text
CausalHistory
  history_id: UUID
  subject_ref: COID | distinction_id
  events: list[CausalHistoryEvent]   # ordenados por created_at, nunca reordenados retroativamente

CausalHistoryEvent
  event_id: UUID
  history_ref: CausalHistory ref
  event_type: str                     # vocabulário fechado em E3.9 (ex.: "created", "transformed", "compared", "accessed")
  actor_ref: ProvenanceRecord ref?
  payload_ref: object?                # referência opaca — nunca conteúdo bruto embutido
  created_at: datetime
```

`CausalHistoryEvent` é apend-only por construção — não há campo de
edição. Correção de um evento histórico é um novo evento que referencia
o anterior, nunca uma mutação in-place (mesmo princípio de
`TimestampMixin`/`AuditMixin` de E2: nada aqui reescreve o passado).

## 4. AccessibilityState

```text
AccessibilityState = ACTIVE | LATENT | INACCESSIBLE | CAUSALLY_EXTINCT
```

Regra explícita do prompt (§9), repetida aqui por ser crítica:
**`CAUSALLY_EXTINCT` nunca é inferido apenas porque uma informação não
aparece no contexto atual.** Um objeto ausente do contexto de uma
sessão é, no máximo, `LATENT` ou `INACCESSIBLE` — `CAUSALLY_EXTINCT`
exige uma transição explícita e registrada (via `CausalHistoryEvent`),
não uma ausência observada. A máquina de transição de estados
completa (quem pode mover o quê, sob qual autoridade) é escopo de E4
(políticas de memória) — E3 apenas define e persiste o enum e valida
que a transição para `CAUSALLY_EXTINCT` sempre tem um evento causal
associado, nunca é o valor default nem um efeito colateral de query.

## 5. CausalClassRef

Propriedade: `E3.5` (`LIB-05` Relationship Engine), se necessário como
referência relacional — não é obrigatório que `E3.5` já implemente sua
persistência completa, apenas que reserve o campo se o Relationship
Engine precisar dele.

```text
CausalClassRef
  class_id: UUID
  label: str?                # rótulo legível, não é a identidade
  members: list[COID | distinction_id]
```

Representa uma classe de equivalência causal entre objetos/distinções
já avaliados como `EQUIVALENT` (ver `CausalComparison`, §7). Não é
gerado automaticamente por similaridade — só existe uma
`CausalClassRef` para um conjunto de membros depois de comparações
explícitas resultarem em `EQUIVALENT` entre eles.

## 6. TransformationRecord

Propriedade: `E3.4` (`LIB-04` Version Manager + TransformationRecord).

```text
TransformationRecord
  transformation_id: UUID
  operation_type: str          # ex.: summarize | translate | merge | compress |
                                #      abstract | generalize | redact | restore |
                                #      import | export | transfer | derive
  input_refs: list[COID | distinction_id]
  output_refs: list[COID | distinction_id]
  actor_ref: ProvenanceRecord ref
  policy_ref: str?              # referência a uma política — nenhuma política implementada em E3
  declared_preservations: list[str]   # o que a transformação afirma preservar
  declared_losses: list[str]          # o que a transformação afirma perder/descartar
  timestamp: datetime
```

`declared_preservations`/`declared_losses` são **declarações do
executor da transformação**, não verificações automáticas — E3 não
implementa nenhuma lógica que audite se a declaração é verdadeira
(isso seria, na prática, um mecanismo de avaliação/score fora do
escopo desta fase — ver EDR).

## 7. CausalComparison

Propriedade: **não atribuída** — o contrato abaixo pode ser refinado
antes da implementação, mas nenhum módulo específico o possui ainda
(ver `E3_IMPLEMENTATION_SEQUENCE.md`, §"Ownership das primitivas por
módulo"). Correção E3.0.1: sua implementação, onde quer que caia, deve
permanecer desacoplada de qualquer ranking ou seleção automática —
isso vale independentemente de qual módulo eventualmente a possuir.

```text
CausalComparison
  comparison_id: UUID
  left_ref: COID | distinction_id
  right_ref: COID | distinction_id
  result: CausalComparisonResult
  evidence_refs: list[str]      # default vazio
  performed_by: ProvenanceRecord ref?
  created_at: datetime

CausalComparisonResult = EQUIVALENT | DISTINGUISHABLE | INCOMPARABLE | UNRESOLVED
```

Os quatro resultados têm peso igual no schema — nenhum é "resultado
padrão" nem "caminho feliz". Em particular (repetindo o EDR):
`INCOMPARABLE` é resultado válido, não erro; `UNRESOLVED` representa
uma comparação que não pôde ser concluída com a evidência disponível
e é igualmente um resultado terminal válido (não obriga nova tentativa
automática).

## 8. LineageEdge

Propriedade: `E3.3` (`LIB-03` CLID Manager + Lineage).

```text
LineageEdge
  edge_id: UUID
  relation: LineageRelation
  from_ref: COID | distinction_id
  to_ref: COID | distinction_id
  transformation_ref: TransformationRecord ref?
  created_at: datetime

LineageRelation = PARENT | CHILD | BRANCH | MERGE | DERIVED_FROM | TRANSFORMED_FROM
```

Lineage é reconstruída percorrendo `LineageEdge` — nunca inferida do
conteúdo textual atual de um objeto (§12 do prompt). `PARENT`/`CHILD`
são inversos um do outro por construção (um `LineageEdge` com
`relation=PARENT` de A para B implica a existência lógica do inverso
`CHILD` de B para A — decisão de E3.3 sobre se ambos são persistidos
ou um é derivado em leitura).

## Índice de dependências entre primitivas

```text
CognitiveObject  (base de identidade — COID/CLID)
   ├── CognitiveDistinction  (referencia N CognitiveObject)
   │      ├── ProvenanceRecord      (origem)
   │      ├── CausalHistory ──── CausalHistoryEvent (append-only)
   │      ├── TransformationRecord  (referencia ProvenanceRecord)
   │      ├── CausalComparison      (referencia ProvenanceRecord?)
   │      ├── CausalClassRef        (agrupa por resultado EQUIVALENT)
   │      └── LineageEdge           (referencia TransformationRecord?)
   └── AccessibilityState  (estado, não entidade referenciável)
```

Nenhuma primitiva embute outra por valor — toda relação é por
referência de identidade (COID/CLID/UUID), consistente com
`app.repositories.repository_protocol` (E2) já operar por identidade,
nunca por objeto aninhado.
