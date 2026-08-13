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
