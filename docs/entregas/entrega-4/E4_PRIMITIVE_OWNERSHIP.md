# E4_PRIMITIVE_OWNERSHIP — quem é dono do quê

**Módulo:** E4.0 — Architecture & Contract Freeze
**Natureza:** documento normativo. Nenhuma implementação.

---

## 1. A regra de admissão de primitivas

Toda entidade persistente candidata da E4 deve responder:

> **Por que a E3 não representa isto?**

Se a resposta for insuficiente, **a entidade não é criada**. Não se
inventa primitiva para preencher módulo.

Esta regra tem consequência imediata e desconfortável: vários módulos
da sequência da E4 podem terminar **sem nenhuma tabela nova**. Isso é
sucesso, não fracasso. A E3 entregou 7 entidades que cobrem
identidade, continuidade, linhagem, transformação, relação,
proveniência e história causal. A superfície legítima de novidade da
E4 é estreita por construção.

---

## 2. Congelamento de fonte da verdade (§21)

```
E3 Cognitive Library:
    source of truth for cognitive patrimony.

E4:
    source of truth only for genuinely new
    memory/governance state defined in E4.
```

**Proibido, sem exceção:**

```
duplicated CognitiveObject
duplicated Provenance
duplicated CausalHistory
duplicated Lineage
duplicated Relationship
duplicated Transformation
```

Duplicar qualquer uma dessas cria uma segunda fonte da verdade, e duas
fontes da verdade divergem — é questão de tempo, não de disciplina.
Quando divergirem, nenhuma regra do sistema saberá qual está certa,
porque ambas terão sido escritas por caminhos autorizados.

---

## 3. Matriz B — E3 vs E4 OWNERSHIP

| Conceito | Dono | Persistido | Tem identidade | Mutável | Fonte da verdade | Depende de |
|---|---|---|---|---|---|---|
| `CognitiveObject` | **E3.1** | sim | COID | não (identidade) | E3 | — |
| COID | **E3.2** | sim (PK) | é a identidade | **não** | E3 | — |
| CLID | **E3.3** | sim | continuidade | uma vez atribuído, não | E3 | COID |
| `LineageEdge` | **E3.3** | sim | id próprio | não (imutável) | E3 | COID |
| `TransformationRecord` | **E3.4** | sim | id próprio | não (imutável) | E3 | COID |
| `RevisionStatus` | **E3.4** | sim | — | sim (CURRENT/SUPERSEDED) | E3 | CLID |
| `Relationship` | **E3.5** | sim | id próprio | só `retired_at` | E3 | COID |
| `ProvenanceRecord` | **E3.6** | sim | id próprio | não (imutável) | E3 | COID |
| `AccessibilityState` | **E3.6** | sim (no objeto) | — | sim (transição) | E3 | COID |
| Index | **E3.7** | derivado | não | reconstruível | **não** | E3 |
| Search | **E3.8** | não | não | — | **não** | E3 |
| `CausalHistory` / `Event` | **E3.9** | sim | id próprio | **não** (imutável) | E3 | COID |
| Integrity findings | **E3.10** | não (transitório) | não | — | não | E3 |
| Sync package | **E3.11** | não (transitório) | não | — | não | E3 |
| — | | | | | | |
| **MemoryDomain** | E4.1 | **sim** | id próprio | sim (nome/descrição) | **E4** | — |
| **DomainMembership** | E4.1 | **sim** | ver §5 | sim (entra/sai) | **E4** | COID + MemoryDomain |
| **MemoryContext** | E4.2 | **ver §6** | ver §6 | — | E4 se persistido | — |
| **AccessibilityPolicy** | E4.3 | **sim** | id próprio | sim (versionada) | **E4** | — |
| **GovernancePolicy** | E4.7 | **sim** | id próprio | sim (versionada) | **E4** | — |
| **RetentionPolicy** | E4.9 | **sim** | id próprio | sim (versionada) | **E4** | — |
| **ComplianceFinding** | E4.10 | **não** | não | — | não | patrimônio + policy |
| **ValidatedExperience** | E4.11 | **sim** | id próprio | não (imutável) | **E4** | ver §7 |
| Consolidação | E4.5 | **nada novo** | — | — | **E3** | usa E3.4/E3.3 |
| Retrieval | E4.6 | **nada novo** | — | — | não | E3.8 + E4.2/E4.3 |
| Isolation | E4.8 | **nada novo** | — | — | não | E4.1 + E4.7 |

Três módulos — E4.5, E4.6, E4.8 — não introduzem nenhuma primitiva
persistente. São composição sobre o que já existe.

---

## 4. Justificativa de cada primitiva nova

Cada uma responde à pergunta obrigatória.

### 4.1 `MemoryDomain` (E4.1) — **admitida**

*Por que a E3 não representa isto?* A E3 não tem nenhum conceito de
segmentação lógica do patrimônio. `Relationship` liga objetos entre si,
mas um domínio não é um objeto e agrupar por relação criaria um
`CognitiveObject` que não é uma distinção cognitiva — seria abuso da
primitiva. Nenhuma tabela da E3 responde "a que recorte este objeto
pertence".

**Contrato:**

```
MEMORY_DOMAIN != FILESYSTEM_FOLDER
MEMORY_DOMAIN != DATABASE
MEMORY_DOMAIN != COGNITIVE_OBJECT
```

Um `CognitiveObject` pode pertencer a **zero, um ou vários**
`MemoryDomain`s. A associação **não pode duplicar COID** — o objeto
continua único e continua vivendo em `cognitive_objects`.

Cardinalidade zero é deliberada: um objeto sem domínio não é órfão nem
inválido. Ele existe. Domínio é recorte, não requisito de existência —
exigir domínio faria da segmentação uma condição de existir, violando
a Matriz A.

### 4.2 `DomainMembership` (E4.1) — **admitida, com pergunta aberta**

*Por que a E3 não representa isto?* É a relação N:N entre objeto e
domínio. Não existe na E3.

A pergunta aberta é se a associação precisa de **identidade própria**,
e ela não é decorativa — ver §5.

### 4.3 `MemoryContext` (E4.2) — **admissão condicional**

Ver §6. Pode não precisar ser persistido.

### 4.4 Policies — `AccessibilityPolicy`, `GovernancePolicy`, `RetentionPolicy` — **admitidas**

*Por que a E3 não representa isto?* A E3 não tem policy alguma, por
decisão explícita: `GOVERNANCE_IMPLEMENTED = NO`,
`full Accessibility policy = E4`. O próprio código da E3 defere: o
`AccessibilityManager` documenta que "a máquina de transição de estados
completa (quem pode mover o quê, sob qual autoridade) é escopo de E4".

**Contrato comum:** policy é **configuração**, não patrimônio
cognitivo — ver Q11 em `E4_ARCHITECTURE_FREEZE.md`. Consequências:
policies são versionadas, mutáveis, e **não viajam** no Sync da E3.

### 4.5 `ComplianceFinding` (E4.10) — **admitida como transitória**

*Por que a E3 não representa isto?* Não representa, mas a E3 já
estabeleceu o padrão correto: findings de Integrity **não são
persistidos** e não são exceções. Compliance segue o mesmo desenho —
diagnóstico é resultado de uma avaliação, não estado do mundo.

Persistir findings criaria a tentação de tratá-los como verdade
estabelecida em vez de resultado de uma avaliação datada contra uma
policy versionada.

### 4.6 `ValidatedExperience` (E4.11) — **admitida com a maior cautela**

*Por que a E3 não representa isto?* Um registro de que uma experiência
foi validada, por quem, contra qual critério, com qual evidência. A E3
tem `ProvenanceRecord` (de onde veio) e `CausalHistoryEvent` (o que
aconteceu), mas nenhum dos dois registra **validação** — que é um juízo
posterior sobre um evento, não o evento.

**A linha que não pode ser cruzada:** registrar experiência validada é
evidência. Usar esse registro para alterar comportamento
automaticamente é learning engine, e é proibido. A E4.11 entrega a
estrutura de registro e **nada** que a consuma.

Ver §7 para a questão em aberto sobre o que exatamente pode ser
registrado.

---

## 5. Questão aberta — `DomainMembership` precisa de identidade? (Q10)

Não é pergunta de estilo. A resposta determina se um objeto pode ter
**histórico de pertencimento**.

- **Sem identidade** (chave composta `coid + domain_id`): a associação
  é um fato binário do presente. Remover de um domínio e readicionar é
  indistinguível de nunca ter saído.
- **Com identidade** (`id` próprio + `joined_at` / `left_at`): o
  pertencimento tem história, e sair de um domínio não apaga ter
  estado nele.

**Recomendação da E4.0: com identidade.** A E3 já enfrentou exatamente
esta escolha em `Relationship` e decidiu por identidade própria com
`retired_at`, precisamente para que *retire* não fosse *delete
history* — e a E3.12 testou isso (`RETIRE != DELETE_HISTORY`, teste
G7). Repetir o mesmo desenho é consistência; escolher o contrário
seria criar uma primitiva onde a saída apaga o passado, dentro de um
sistema construído para não fazer isso.

**Não congelado na E4.0** — decidido em E4.1, com esta recomendação
registrada.

---

## 6. Questão aberta — `MemoryContext` é persistente ou transiente? (Q8)

A E4.0 **não congela**. Registra a análise.

**Argumento para transiente:** um contexto é a circunstância de uma
operação — quem, para quê, em que escopo. Circunstâncias são
efêmeras. A demonstração do teste arquitetural (§29) construiu
contexto como **objeto puramente em memória** e funcionou: nenhuma
tabela foi necessária para provar
`Accessible(P,C1) != Accessible(P,C2)`.

**Argumento para persistente:** contextos recorrentes e nomeados
("revisão do livro", "auditoria trimestral") são configuração
reutilizável, e reconstruí-los a cada operação convida à divergência.

**Posição da E4.0:** provavelmente **ambos**, e a distinção entre eles
é o ponto:

- **`ContextDefinition`** — configuração nomeada, persistida,
  versionada, reutilizável. Não é patrimônio cognitivo.
- **`MemoryContext`** — a instância efêmera de uma operação, montada a
  partir de uma definição mais os parâmetros do momento. **Não
  persistida.**

Congelado desde já, independentemente da decisão:

```
CONTEXT != IDENTITY
CONTEXT != MEMORY
CONTEXT != POLICY
CONTEXT != SESSION
```

Uma sessão pode **participar** de um contexto; não o define. A E3 já
guarda `session_id` em `provenance_records` — evidência de que sessão
é uma dimensão de proveniência, não a moldura inteira do contexto.

`CONTEXT != POLICY` é a mais fácil de perder na implementação:
contexto diz *onde se está olhando*; policy diz *o que é permitido
ver*. Fundi-los produziria um objeto que é simultaneamente pergunta e
resposta, e nenhuma auditoria conseguiria separar os dois depois.

---

## 7. Questão aberta — o que a E4.11 pode registrar? (Q19)

Limite proposto, a ser confirmado em E4.11:

**Pode registrar:** que uma experiência ocorreu; qual foi seu
resultado observado; quem a validou; contra qual critério explícito;
com qual evidência; quando. Tudo isso é **fato datado e atribuído**.

**Não pode registrar:** que a experiência "prova" algo; um score de
confiança; uma generalização derivada; uma recomendação de ação
futura. Todos são **inferência**, e inferência automática sobre
experiência é exatamente o learning engine proibido.

O teste prático: se remover o registro mudaria o **comportamento** do
sistema, virou learning engine. Se remover o registro apenas apaga
**evidência**, ainda é registro.

---

## 8. Primitivas explicitamente **não** criadas

| Não criado | Por quê |
|---|---|
| `Memory` (entidade) | memória é função de contexto sobre patrimônio, não tabela |
| `MemoryItem` | seria `CognitiveObject` duplicado |
| `Relevance` (persistida) | relevância é julgamento contextual, nunca materializado |
| `PersistenceScore` | proibido — `COUT-P8`/`COUT-P9` |
| `ConsolidatedObject` | é `CognitiveObject` com `TransformationRecord` de merge |
| `ConsolidationLineage` | é `LineageEdge` com `relation_type=MERGE` |
| `MemoryVector` / embedding store | descoberta, nunca fonte da verdade; deferido |
| `TranscriptRecord` | `TRANSCRIPT_AUTO_STORAGE = NONE` |
| `AccessLog` | não decidido; se existir, é observabilidade, não patrimônio |
| `Artifact` | `ARTIFACT_STORAGE = DEFERRED` |

A quarta e a quinta linhas merecem ênfase: a tentação de criar
primitivas de consolidação é forte porque consolidação *parece* nova.
Não é. É transformação com múltiplas entradas e perda declarada, e a
E3 já a demonstrou funcionando ponta a ponta.
