# E4_MEMORY_SEMANTICS — o que é memória no PIA-OS

**Módulo:** E4.0 — Architecture & Contract Freeze
**Natureza:** documento normativo. Nenhuma implementação.
**Baseline:** E3 FROZEN em `014455f9` / tree `83217c40`.

---

## 1. A definição

```
Memory(Context) = Admissible_Context( Persistent( CognitivePatrimony ) )
```

Leitura em português: **memória é a parte do patrimônio cognitivo
persistente que é admissível em um dado contexto.**

Três coisas que essa expressão diz e que precisam ficar explícitas:

1. **Memória é uma função, não uma tabela.** Não existe "a memória" em
   algum lugar do banco. Existe patrimônio (E3) e existe uma relação de
   admissibilidade (E4). Memória é o que resulta da aplicação de uma
   à outra.
2. **Memória é indexada por contexto.** Não há memória sem contexto —
   perguntar "o que o sistema lembra?" sem dizer *para quem, para quê,
   em que escopo* é uma pergunta malformada.
3. **A expressão é conceitual.** Não é fórmula, não é score, não é
   ranking, não é função numérica. Quem a implementar como
   `memory_score(obj, ctx) -> float` terá violado o contrato.

### 1.1 O que essa definição proíbe

`Admissible_Context` **filtra**. Não cria, não altera, não apaga, não
reordena por importância inventada. Um objeto fora da vista de um
contexto continua idêntico no patrimônio — mesmo COID, mesma história,
mesma proveniência.

---

## 2. Memória não é

Congelado:

```
MEMORY != STORAGE
MEMORY != TRANSCRIPT
MEMORY != SEARCH
MEMORY != INDEX
MEMORY != CACHE
MEMORY != VECTOR DATABASE
MEMORY != CURRENT STATE ONLY
```

Por que cada um importa:

| Confusão | Por que é errada | Consequência de aceitá-la |
|---|---|---|
| Memory = Storage | Storage guarda bytes; memória é relação contextual sobre distinções | O sistema "lembraria" tudo igualmente, sempre |
| Memory = Transcript | Transcript é registro de troca, não distinção validada | Toda conversa viraria patrimônio automaticamente |
| Memory = Search | Search é mecanismo de descoberta sobre o que já existe | *Search miss* viraria esquecimento |
| Memory = Index | Índice é derivado e reconstruível | O derivado viraria fonte da verdade |
| Memory = Cache | Cache é otimização descartável | Expiração de cache viraria perda de memória |
| Memory = Vector DB | Similaridade não é identidade nem causalidade | Proximidade semântica viraria prova |
| Memory = estado atual | O passado é parte da memória | História seria descartável |

O último é o mais perigoso e o mais sutil: um sistema que trata memória
como "o estado atual das coisas" não perde dados — perde a **capacidade
de distinguir trajetórias**, que é precisamente o que a E3 inteira foi
construída para preservar.

---

## 3. As quatro distinções fundamentais

Congeladas:

```
EXISTENCE    != PERSISTENCE
PERSISTENCE  != ACCESSIBILITY
ACCESSIBILITY != RELEVANCE
RELEVANCE    != EXISTENCE
```

### 3.1 Definições precisas

**EXISTENCE** — pertencimento ao patrimônio cognitivo preservado.
Um `CognitiveObject` existe se está no patrimônio. Ponto. Existência
não admite grau, contexto ou opinião. É propriedade do patrimônio, e o
patrimônio é da E3.

**PERSISTENCE** — continuidade de uma distinção relevante através de
estados, transformações ou tempo. Persistência é *sobre a distinção*,
não sobre o registro: quando `O1` se transforma em `O2`, o registro
`O1` continua existindo, e o que persiste é a **continuidade** entre
eles — materializada em CLID, linhagem, transformação e história
causal.

**ACCESSIBILITY** — admissibilidade de acesso em determinado contexto.
É relacional: não existe "objeto acessível", existe "objeto acessível
*em C*". A E3 já persiste um eixo disso no `AccessibilityState` do
objeto; a E4 acrescenta o eixo contextual. Os dois compõem — nenhum
substitui o outro.

**RELEVANCE** — pertinência para uma finalidade/contexto específico.
Relevância é a mais fraca das quatro e a mais perigosa de reificar:
é julgamento, não fato do patrimônio. Nada no PIA-OS pode converter
"irrelevante aqui" em qualquer alteração de existência.

### 3.2 As consequências obrigatórias

```
NOT_RETRIEVED  != FORGOTTEN
INACCESSIBLE   != NONEXISTENT
IRRELEVANT     != DELETED
```

Cada uma corresponde a um modo de falha real de sistemas de memória:

- **`NOT_RETRIEVED != FORGOTTEN`** — a busca não encontrou. Isso é um
  fato sobre a busca, não sobre o patrimônio. Já congelado em E3.8
  (`SEARCH MISS != NON-EXISTENCE`); a E4 herda sem reinterpretar.
- **`INACCESSIBLE != NONEXISTENT`** — política restringiu acesso. O
  objeto está lá. Um sistema que responde "não existe" quando quer
  dizer "você não pode ver" está mentindo, e a mentira contamina toda
  inferência a jusante.
- **`IRRELEVANT != DELETED`** — irrelevância é sempre *em um contexto*.
  Um objeto irrelevante para C1 pode ser o objeto central de C2.

### 3.3 Matriz A — EXISTENCE / PERSISTENCE / ACCESSIBILITY / RELEVANCE

| | Existence | Persistence | Accessibility | Relevance |
|---|---|---|---|---|
| **Pergunta que responde** | está no patrimônio? | a distinção sobreviveu? | pode ser acessado aqui? | interessa aqui? |
| **Natureza** | fato binário | fato histórico | relação (objeto × contexto) | julgamento (objeto × propósito) |
| **Depende de contexto?** | **não** | não | **sim** | **sim** |
| **Proprietário** | E3 | E3 (mecanismo) / E4 (política) | E3 (estado) + E4 (contexto) | E4 |
| **Persistido?** | sim (`cognitive_objects`) | sim (CLID/lineage/causal) | parcial: estado sim, contexto a definir | **não** — nunca materializada |
| **Pode ser revogado?** | não | não | sim | sim |
| **Governança pode alterar?** | **NUNCA** | não | sim | sim |
| **Perda implica perda de existência?** | — | não | não | não |

A linha decisiva é a penúltima. Governança opera nas duas colunas da
direita e **nunca** nas duas da esquerda.

---

## 4. Papel do LOP na E4

LOP entra como **princípio de persistência** — e apenas isso.

**Proibido implementar:**

```
persistence_score        = NONE
universal survival score = NONE
global importance score  = NONE
automatic promotion score= NONE
```

**Congelado:**

```
PERSISTENCE != POPULARITY
PERSISTENCE != RECENCY
PERSISTENCE != FREQUENCY
```

Persistência será tratada por **estados, relações, evidências,
continuidade e contexto** — estruturas que já existem e já são
auditáveis — e não por uma métrica universal inventada para a ocasião.

A razão não é estética. Um score universal de persistência tem três
defeitos fatais para este sistema: ele (a) colapsa dimensões
incomparáveis em um número, violando `COUT-P8`; (b) torna-se
decisório na prática, violando `COUT-P9`; e (c) é irrefutável — não
há como um score de 0,73 estar *errado*, e o que não pode errar não
pode ser auditado.

---

## 5. Papel do CLEO na E4

CLEO entra **exclusivamente** como princípio de admissibilidade
contextual:

```
EXISTING_PATRIMONY != ADMISSIBLE_PATRIMONY_IN_CONTEXT
```

**Proibido importar:** cosmologia, horizonte físico, equações de
Friedmann, equações de Einstein, de Sitter, termodinâmica de
horizontes, kernels cosmológicos.

A E4 não é implementação cosmológica. A analogia útil é uma só, e é
estrutural, não física: **o que é observável depende de onde se
observa, e isso não altera o que existe.** Nada além disso atravessa
para o software. Nenhuma equação física entra em `app/`.

O mesmo cuidado já foi exercido na E3 com o cenário "Galaxy Trace" —
analogia nominal para separar evento/história de fonte atual, com
`NO GR / NO COSMOLOGY` explicitamente congelado. A E4 mantém a mesma
disciplina.

---

## 6. Matriz C — MEMORY vs STORAGE vs SEARCH vs TRANSCRIPT

| | Memory | Storage | Search | Transcript |
|---|---|---|---|---|
| **O que é** | patrimônio admissível em contexto | bytes persistidos | mecanismo de descoberta | registro bruto de troca |
| **Fonte da verdade?** | não (é vista) | não | **não** | **não** |
| **Depende de contexto** | sim | não | parcial (critérios) | não |
| **Miss significa** | não admissível aqui | — | não encontrado ≠ inexistente | — |
| **Vira patrimônio automaticamente?** | — | não | não | **NUNCA** |
| **Proprietário** | E4 (relação) sobre E3 (conteúdo) | infra | E3.8 | fora do domínio cognitivo |
| **Auditável** | sim | sim | sim | não persistido |

---

## 7. Transcript e busca vetorial

```
TRANSCRIPT_AUTO_STORAGE = NONE
TRANSCRIPT_AS_MEMORY    = FALSE
```

Uma conversa **pode produzir** `CognitiveObject`s. O transcript bruto
**não vira** memória cognitiva automaticamente. A promoção de conteúdo
exige mecanismo explícito, que a E4.0 não define e que nenhum módulo
da E4 pode introduzir implicitamente.

```
SEARCH RESULT          != MEMORY
TOP_K                  != TRUTH
EMBEDDING_SIMILARITY   != COGNITIVE_EQUIVALENCE
VECTOR_DATABASE_AS_SOURCE_OF_TRUTH = FALSE
```

Embeddings e busca vetorial podem, no futuro, servir como **mecanismo
de descoberta**. Nunca como fonte da verdade, mecanismo de identidade,
prova causal ou prova de persistência.

`EMBEDDING_SIMILARITY != COGNITIVE_EQUIVALENCE` é a proteção direta de
`COUT-P7` (`EQUIVALENCE != DESTRUCTIVE COLLAPSE`): dois objetos com
vetores quase idênticos e histórias diferentes continuam sendo dois
objetos. Qualquer dedupe por similaridade seria o colapso destrutivo
que a E3 provou não cometer.

---

## 8. Neutralidade de provider

```
PROVIDER_NEUTRALITY = TRUE
```

Memória não pode depender semanticamente de OpenAI, Anthropic, Google,
Meta ou de qualquer modelo local específico.

Provider e model **participam da proveniência** — `provider_id` e
`model_id` já existem em `provenance_records`, ambos nullable, e a E3
provou em teste que `NULL` permanece válido em todo o pipeline.
Participar da proveniência é registrar *quem contribuiu*; não é possuir
a identidade cognitiva do patrimônio.

`COUT-P10` — a memória cognitiva persistente pertence ao PIA-OS, não a
um modelo ou fornecedor — permanece intocado pela E4.
