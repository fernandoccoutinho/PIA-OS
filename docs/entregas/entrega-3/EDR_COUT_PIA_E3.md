# EDR — COUT-PIA (Entrega 3)

**Tipo:** Engineering Decision Record
**Módulo:** E3.0 — Baseline Intake & Interface Freeze
**Status:** Aceito

## Contexto

A Entrega 3 introduz as primeiras estruturas computacionais
relacionadas ao COUT-PIA dentro do PIA-OS. Antes de qualquer
implementação (LIB-01–LIB-11), é necessário formalizar por escrito o
que COUT-PIA **é** e, com igual peso, o que COUT-PIA **não é** — para
que nenhum módulo futuro (desta entrega ou de entregas seguintes)
implemente, por atalho de conveniência, um mecanismo de decisão
automática disfarçado de representação.

## Decisão

**COUT-PIA é o framework operacional de governança da continuidade
causal do PIA-OS.**

Sua função é representar, preservar, comparar e rastrear distinções
cognitivas causalmente recuperáveis ao longo de: objetos, versões,
sessões, representações, transformações, agentes, modelos, providers,
ferramentas e fontes.

## O que COUT-PIA não é

COUT-PIA não é:

- motor universal de decisão;
- mecanismo universal de seleção;
- ranking obrigatório;
- função universal de otimização;
- seletor automático de IA;
- substituto do Kernel;
- substituto do Runtime;
- substituto do Scheduler;
- substituto de policies;
- substituto de arbiters.

## Separação de responsabilidades

```text
AGENT / LLM
    ↓
produz inferência

POLICY / ARBITER
    ↓
seleciona ação quando necessário

COUT-PIA
    ↓
representa e avalia continuidade causal

PIA-OS
    ↓
preserva patrimônio cognitivo, estado, provenance e histórico.
```

Esta cadeia nunca colapsa para `COUT → decisão automática`. Nenhum
módulo de E3 (LIB-01–LIB-11) implementa Policy, Arbiter, Kernel,
Runtime ou Scheduler — esses componentes, quando existirem, consomem
o que COUT-PIA representa; COUT-PIA não os substitui nem antecipa.

## Proibições formais desta decisão

1. **Nenhuma scalarização é canônica nesta fase.** Em particular,
   `A_COUT = R * P * T` não é implementado como score universal.
   `A`, `P`, `T` (ou descritores equivalentes) podem existir
   futuramente como componentes multidimensionais ou métricas
   setoriais — nunca como um único número que substitui comparação
   estruturada.
2. **Nenhum destes nomes (ou equivalente funcional) é criado
   automaticamente** por E3: `cout_score`, `global_admissibility_score`,
   `universal_rank`, `best_cognitive_path`.
3. **`INCOMPARABLE` é um resultado arquiteturalmente válido** de
   `CausalComparison` — não um caso de erro, não um estado transitório
   a ser eliminado por heurística. Um sistema que nunca produz
   `INCOMPARABLE` está, por construção, forçando comparabilidade onde
   ela não existe.

## Identidade: COID e CLID

- **COID** — identidade permanente do `CognitiveObject`.
- **CLID** — identidade conceitual / continuidade de linhagem.

COID e CLID nunca são o mesmo campo, nem um é derivado implicitamente
do outro por similaridade de conteúdo. Duas histórias podem convergir
para o mesmo conteúdo final e permanecerem causalmente distintas — a
deduplicação automática por igualdade de conteúdo é, por definição,
uma violação desta decisão.

## Multi-IA e memória

- A arquitetura é provider-agnostic. Claude é a ferramenta usada para
  **desenvolver** o código nesta fase — não é parte obrigatória da
  arquitetura de runtime do PIA-OS.
- A memória pertence ao PIA-OS, não a Claude nem a qualquer outro LLM.
  Nenhum agente escreve diretamente na memória consolidada sem passar
  pelos serviços e políticas do PIA-OS (políticas completas de acesso
  são escopo de E4, não desta entrega).
- Multi-AI Orchestrator é responsabilidade de E7/Hypervisor — não
  implementado aqui, nem antecipado estruturalmente além dos campos
  já existentes em `RequestContext` (`provider`, `tenant`) herdados de
  E2.

## Multi-IA Triple-Mode (decisão arquitetural congelada — correção E3.0.1)

A arquitetura futura do PIA-OS trabalha oficialmente com três modos de
orquestração multi-IA:

```text
OrchestrationMode:
  1. COMPETITIVE
  2. COMPLEMENTARY
  3. SEQUENTIAL
```

**`COMPETITIVE`** — duas ou mais IAs recebem o mesmo problema. As
respostas permanecem separadas e rastreáveis antes da arbitragem. O
PIA poderá, posteriormente (via Policy/Arbiter, não via COUT):
comparar, selecionar, combinar, manter divergência ou declarar
incomparabilidade. COUT não escolhe sozinho o vencedor.

**`COMPLEMENTARY`** — diferentes IAs recebem papéis diferentes (ex.:
`generator`, `critic`, `verifier`, `synthesizer`). Este é o modo
**default** inicial da futura orquestração, salvo policy em contrário.

**`SEQUENTIAL`** — uma IA produz um resultado usado/revisado por
outra (ex.: `draft` → `review` → `correction` → `validation`). Toda a
cadeia permanece rastreável.

**E3 não implementa nenhum destes modos.** A execução pertence
futuramente a **E7 — PIA Hypervisor / Multi-AI Orchestrator**. A
obrigação de E3 é apenas ser **TRIPLE-MODE-READY**: os contratos de
provenance, lineage, transformations, metadata, cognitive objects e
causal history (`E3_DOMAIN_MODEL_DRAFT.md`) não podem impedir,
estruturalmente, nenhum dos três modos — sem que isso signifique
implementar orquestração, Hypervisor, ou `OrchestrationMode` como
serviço nesta fase.

### Invariante multi-IA

Duas ou mais respostas produzidas por agentes diferentes **não podem
ser sobrescritas silenciosamente** apenas porque: pertencem à mesma
tarefa; possuem conteúdo semelhante; chegam à mesma conclusão; uma
delas foi selecionada pelo Arbiter. As saídas originais devem
permanecer recuperáveis conforme policy futura. Esta invariante é
necessária para os três modos (`COMPETITIVE`, `COMPLEMENTARY`,
`SEQUENTIAL`) igualmente — é consequência direta da proibição de
deduplicação automática já registrada em "Identidade: COID e CLID".

### COUT e Multi-IA

COUT-PIA pode fornecer informação estrutural sobre: provenance,
lineage, distinções, equivalência, divergência, transformação,
acessibilidade. Mas **COUT-PIA não seleciona automaticamente a melhor
IA nem a melhor resposta** — essa decisão pertence a Policy/Arbiter,
consistente com "COUT não é Arbiter" já estabelecido na Separação de
Responsabilidades acima.

```text
Task
  │
  ▼
Orchestration Policy
  │
  ▼
OrchestrationMode
  │
  ├──▶ Agent A
  ├──▶ Agent B
  └──▶ Agent N
  │
  ▼
COUT Comparison
  │
  ▼
Policy / Arbiter
  │
  ▼
Governed Persistence
  │
  ▼
Cognitive Library
```

Nenhum componente deste diagrama além de "COUT Comparison" e
"Cognitive Library" é implementado por E3 — o diagrama existe para
que os contratos de E3 (em particular `ProvenanceRecord`) não sejam
projetados de um jeito que precise ser refeito quando E7 existir.

## Consequências

- Todo módulo LIB-01–LIB-11 desta entrega é auditado, entre outros
  critérios, contra esta decisão: qualquer PR que introduza scoring
  universal, deduplicação automática por conteúdo, ou colapso da
  cadeia de responsabilidades acima é uma Stop Condition (§20 do
  módulo E3.0), não um ajuste a ser resolvido silenciosamente.
- `CausalComparison` deve ser projetado desde o schema inicial
  (`E3_DOMAIN_MODEL_DRAFT.md`) para suportar `UNRESOLVED` e
  `INCOMPARABLE` como primeira classe, não como exceção.

## Revisão futura

Esta decisão só é revista por um novo EDR/ADR explícito que a
referencie e declare a revisão — nunca por acúmulo silencioso de
exceções pontuais em código.

## Documentos relacionados

- `EDR_E3_COGNITIVE_PACKAGING.md` — decisão arquitetural separada
  sobre a organização de pacotes do código de E3 (`app.cognitive` como
  bounded context vs. layout horizontal). Não é uma decisão sobre o
  que COUT-PIA é — é sobre onde o código mora — por isso foi mantida
  em documento próprio em vez de expandir este EDR.

## COUT Data Preservation Rule (adicionada em E3.5.2)

**Princípio arquitetural geral** — não é uma regra específica de
`Relationship`; orienta qualquer módulo futuro de E3 que produza
schema/migrações sobre patrimônio cognitivo já persistido.

> Uma transformação de representação — inclusive downgrade de schema —
> não pode recuperar compatibilidade apagando, fundindo ou
> sobrescrevendo distinções históricas legitimamente preservadas.
>
> Se a representação anterior não puder expressar o estado atual sem
> perda de distinções, a transformação deve ser explicitamente
> recusada.

Formalizações operacionais:

```text
HISTORICAL PRESERVATION > DOWNGRADE CONVENIENCE

SCHEMA REVERSIBILITY != HISTORICAL ERASURE
```

### Origem

Identificada na auditoria da migração `63d205dec996` (correção
E3.5.1): o lifecycle de `Relationship` permite legitimamente múltiplas
gerações históricas da mesma tripla `(source_coid, target_coid,
relationship_type)` — uma `retired`, uma `active` (o ciclo "retirar a
antiga, criar uma nova"). O schema anterior a essa migração exigia
unicidade incondicional sobre todas as linhas; um downgrade
convencional, executado depois desse estado ter sido legitimamente
produzido, não conseguiria recriar a constraint anterior sem apagar,
fundir ou escolher arbitrariamente qual geração preservar.

### Aplicação (E3.5.2)

`63d205dec996` foi classificada como `CONDITIONALLY_REVERSIBLE`:
downgrade permitido quando o estado atual é representável pelo schema
anterior sem perda; `DOWNGRADE_SEMANTICALLY_BLOCKED` (recusa
explícita, antes de qualquer alteração estrutural) quando não é. Ver
`E3_5_2_LIB05_COUT_DATA_PRESERVATION.md` para a implementação
completa.

### Orientação para módulos futuros

Qualquer migração que reintroduza uma constraint mais restritiva do
que o schema atual (unicidade incondicional substituindo unicidade
condicional, `NOT NULL` substituindo nullable com dados já gravados,
etc.) deve, no `downgrade()`, verificar explicitamente se o estado
atual é representável pela constraint mais restritiva **antes** de
tentar recriá-la — nunca depender do erro genérico que o próprio banco
produziria ao tentar aplicá-la sobre dados incompatíveis, porque nesse
ponto a transação já pode ter executado outras alterações destrutivas
anteriores no mesmo `downgrade()`.

## Princípios de história causal (decisão arquitetural — E3.9)

Três princípios congelados por `E3.9`/`LIB-09`. Implementação e provas
em `E3_9_LIB09_CAUSAL_HISTORY.md`.

### ARCHAEOLOGICAL CAUSAL TRACE PRINCIPLE

Um estado presente pode preservar informação causalmente transmitida
sobre uma distinção que existiu em um estado passado, mesmo quando a
fonte ou a organização original já se transformou. Observar agora não
obriga a estar observando o estado atual da fonte.

```text
PRESENT OBSERVATION MAY BE PRESENT ACCESS TO A PAST CAUSAL TRACE
CURRENT != ONLY CAUSALLY ACCESSIBLE HISTORY
```

Cenário motivador (**metáfora arquitetural, não modelo físico**):
`GALAXY TRACE` — uma fonte distante já evoluiu de `S0` para `S1`,
mas informação emitida em `S0` continua chegando ao observador. Nada
de relatividade geral, lente gravitacional, geodésicas, cosmologia,
CLEO ou LOP é implementado; a lente serve apenas para lembrar que uma
fonte pode ter **múltiplos caminhos causais**
(`GRAVITATIONAL_LENSING = ANALOGY_ONLY`).

### DISTINCTION EXTINCTION PRINCIPLE

A extinção presente de uma distinção não nega sua existência
histórica, e não exige que o substrato material tenha desaparecido.

```text
MATERIAL PERSISTENCE      != DISTINCTION PERSISTENCE
SUBSTRATE CONTINUITY      != ORGANIZATIONAL IDENTITY
DISTINCTION EXTINCTION    != RETROACTIVE HISTORICAL ERASURE
CAUSALLY_EXTINCT          != NEVER EXISTED
SUPERSEDED                != FICTION
TRANSFORMED               != NEVER EXISTED
```

Cenário motivador: `BROKEN GLASS` — um objeto organizado se
fragmenta e se dispersa. O material pode continuar existindo; o que
deixa de existir é a organização que permitia identificá-lo *como
aquilo*. Registrar que um estado originou outros **não** afirma que
esses outros ainda sejam o original.

### EPISTEMIC NON-FABRICATION PRINCIPLE

Ausência de evidência preservada não autoriza nenhuma das duas
conclusões opostas.

```text
NO PRESENT EVIDENCE != NEVER EXISTED
NO PRESENT EVIDENCE != ASSERT THAT IT EXISTED
ONTOLOGICAL POSSIBILITY != RECORDED HISTORICAL FACT
NO SURVIVING TRACE MAY IMPLY HISTORY NOT RECONSTRUCTIBLE
RECORDED HISTORY != COMPLETE HISTORY OF REALITY
```

O PIA nunca preenche lacuna causal por imaginação ou inferência
silenciosa. Em particular, precedência temporal não é causalidade
(`TEMPORAL PRECEDENCE != CAUSALITY`): ordenar eventos por tempo de
registro é apresentação, nunca afirmação de parentesco causal.

E o corolário operacional que muda a implementação: **o registro
histórico é ele próprio um rastro preservado**. Simular a extinção de
um rastro apagando o registro destruiria a evidência que o sistema
existe para guardar — por isso história causal é append-only, e
corrigir é anexar um evento que referencia o anterior.

### Topologia da história causal (E3.9.1)

```text
ONE_HISTORY_PER_SUBJECT   = TRUE
CROSS_HISTORY_PREDECESSOR = ALLOWED
```

`CausalHistory` é o agregado histórico **por sujeito**;
`CausalHistoryEvent.predecessor_event_id` é relação causal **entre
eventos**, não restrita ao mesmo sujeito. Daí:

```text
history boundary != causal boundary
cross-history predecessor != shared identity
```

Transmissão causal atravessa sujeitos sem fundir suas identidades nem
suas histórias. Um evento pode referenciar como predecessor um evento
da história de outro sujeito, e `COID_A != COID_B` e
`HISTORY_A != HISTORY_B` continuam valendo.

### Garantia de aciclicidade causal (E3.9.1a)

```text
CAUSAL_DAG_GUARANTEE          = APPLICATION_STRUCTURAL
DB_LEVEL_GLOBAL_DAG_GUARANTEE = FALSE
```

A topologia de eventos causais é um DAG **sob o contrato append-only
autorizado de Repository/Manager**. O PostgreSQL impõe
independentemente a validade das FKs e a rejeição de auto-predecessor,
mas não impõe independentemente aciclicidade global — não há
constraint recursiva, trigger de DAG, detector de ciclos nem
imutabilidade append-only no nível do banco.

```text
SELF_LINK_PROTECTION             != GLOBAL_DAG_PROOF
APPLICATION_APPEND_ONLY_CONTRACT != DB_LEVEL_IMMUTABILITY
CROSS_HISTORY                    != CYCLE_PERMISSION
```

`GLOBAL_DB_CYCLE_PROTECTION = NOT_REQUIRED_IN_E3_9` — a API autorizada
preserva a propriedade necessária; a garantia será reavaliada se
houver requisito de writers externos ou acesso direto ao banco.

### Integridade, conformidade e aprendizado (E3.10)

```text
INTEGRITY_DETECTS_DOES_NOT_DECIDE
ERROR_IS_EVIDENCE_NOT_LEARNING
PIA_LEARNING_SOURCE = VALIDATED_EXPERIENCE
COMPLIANCE != LEARNING
IMPROVEMENT != REPAIR
KERNEL_CHANGE != INCIDENT_RESPONSE
AUTO_DESTRUCTIVE_REPAIR = FORBIDDEN_E3_10
```

**Integridade detecta, não decide.** O Integrity Manager observa,
verifica e diagnostica; decidir o que fazer com uma condição detectada
é governança, que pertence a `E4`. Detectar inconsistência não
autoriza apagá-la: um estado inconsistente pode ser parte da história
observada do sistema (`DETECTED INCONSISTENCY != AUTHORIZATION TO
ERASE HISTORY`), e `INTERNALLY_CONSISTENT != TRUE_ABOUT_REALITY` —
auditoria testa invariantes internos, não verdade ontológica.

**Erro é evidência possível, não aprendizado.** O PIA não aprende com
erro como regra. Um finding é observação, não conhecimento. Sucesso
repetido, resultado superior, estabilidade, comparação entre
estratégias, feedback humano, evidência externa, descoberta causal,
resultado experimental e divergência Multi-IA também produzem
evidência — `LEARNING != FAILURE_RESPONSE`.

A fonte do aprendizado futuro é **experiência validada**:

```text
EXPERIENCE → EVIDENCE → EVALUATION → VALIDATION → LEARNING →
IMPROVEMENT PROPOSAL → GOVERNANCE → CONTROLLED EVOLUTION
```

Conformidade poderá participar como **uma** fonte de evidência nesse
fluxo, nunca como motor de aprendizado. Um caso fechado não altera
automaticamente regra, política, contrato ou Kernel.

**Kernel.** `KERNEL_SELF_MODIFICATION = NOT_AUTHORIZED`;
`KERNEL_IMPROVEMENT = FUTURE_CONTROLLED_PROCESS`. Candidato a melhoria
exige experiência validada mais reprodutibilidade, evidência
suficiente, generalizabilidade e aprovação de governança. Nunca
`INCIDENT → KERNEL CHANGE`.
