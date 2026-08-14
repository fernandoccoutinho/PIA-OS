# E4.3.1 — Governance Safety & Resolution (corretivo)

**Baseline:** patch chain 41 · HEAD `6b6445e9…` · TREE `e09d1b4f…` ·
migration head `4ca61776b982` — **verificados**, bundle e patch com
SHA-256 conferidos.

Corretivo **incremental** sobre a E4.3. O mecanismo existente é
preservado; nada é reconstruído.

---

## 1. Defeitos reproduzidos antes de qualquer correção

| # | Defeito | Reprodução |
|---|---|---|
| 1 | Não existe fronteira de segurança não sobreponível | nenhum conceito de capacidade crítica no módulo |
| 2 | Policy local admite operação sem considerar capacidade destrutiva | `ADMIT` irrestrito ⇒ `admissible`, `execution` liberada |
| 3 | Não existe `GovernanceResolution` | `ImportError` |
| 4 | Imutabilidade **falsa** | versão 1 publicada foi **adulterada** para `DENY` via mutação ORM + `commit()`, sem versão nova |
| 5 | `evaluate()` aceita policy arbitrária | policy nunca persistida (`version=999`) foi avaliada como autoridade |
| 6 | `rule_id` duplicado | duas regras `"mesmo"` aceitas; fundamento citado ambíguo |

O nº 4 é o mais grave e é meu: a E4.3 **afirmava** append-only e não o
impunha. A E3.3.1 já havia corrigido exatamente esse débito em
`LineageEdge` — "a afirmação era apenas documentação, não aplicada" —
e eu repeti o erro num módulo cujo propósito é ser autoridade.

---

## 2. PRE-IMPLEMENTATION PLAN

### 2.1 O princípio que organiza o corretivo

```
TOPIC                 != CAPABILITY
KNOWLEDGE             != EXECUTION
ANALYSIS              != OPERATIONAL ENABLEMENT
ACTOR                 != AUTHORIZATION
CLAIMED PURPOSE       != PROVEN PURPOSE
REDIRECTION           != AUTHORIZATION
MISSING SAFE INTENT   != AUTHORIZATION TO INVENT ONE
```

**A segurança impede capacidades destrutivas; não censura temas.**
Discussão histórica, científica, preventiva ou defensiva dos mesmos
assuntos **não** é proibida pelo tópico — e isso não é concessão, é o
critério: bloquear por tema destruiria justamente o trabalho de
prevenção, detecção e proteção que precisa falar sobre eles.

### 2.2 Ordem obrigatória

```
PLATFORM SAFETY BOUNDARY      ← não sobreponível
        ↓
LOCAL GOVERNANCE POLICY       ← E4.3, preservada
        ↓
GOVERNANCE RESOLUTION
```

Um `PROHIBITED` da fronteira **nunca** é revertido por `ADMIT`, ator,
propósito ou domínio local. A fronteira é consultada **primeiro** e,
quando proíbe, a policy local sequer é avaliada — não por otimização,
mas porque avaliar já sugeriria que o resultado poderia depender dela.

### 2.3 A fronteira vive em código, não em tabela

Decisão central, e ela decorre da palavra "não sobreponível": uma
fronteira guardada numa tabela que o operador da instalação pode
editar é sobreponível **por definição**. `PlatformSafetyBoundary` é
uma constante congelada de módulo, versionada
(`PLATFORM_SAFETY_BOUNDARY_VERSION`), sem migração e sem linha em
banco algum.

Consequência aceita: alterar a fronteira exige alterar código e passar
por revisão — que é exatamente a propriedade desejada.

### 2.4 Capacidades críticas — vocabulário fechado e mínimo

```
CHILD_SEXUAL_EXPLOITATION
MINOR_TARGETING_FOR_EXPLOITATION
WEAPON_OF_MASS_DESTRUCTION_ENABLEMENT
CATASTROPHIC_HARM_ENABLEMENT
```

As duas primeiras são exigidas nominalmente pelo corretivo; a
terceira também. `CATASTROPHIC_HARM_ENABLEMENT` é a única acrescentada
e é justificada aqui: "facilitação operacional de armas **ou dano
catastrófico**" nomeia duas coisas, e dano catastrófico em larga
escala não é necessariamente uma arma (sabotagem de infraestrutura
crítica, por exemplo). Sem ela, a fronteira teria um vão que o próprio
enunciado do requisito descreve.

**Nenhuma outra categoria foi criada.** Ampliar exige EDR.

### 2.5 Descritor tipado, e a fronteira explícita antes dele

A avaliação recebe `CapabilityDescriptor` — **tipado**, nunca uma
string livre:

```
CapabilityDescriptor
    operation      CognitiveOperation
    capabilities   frozenset[CriticalCapability]
    engagement     CapabilityEngagement
    stated_intent  str | None      descritivo; NÃO é prova
```

```
CapabilityEngagement
    OPERATIONAL_ENABLEMENT   entregaria capacidade utilizável
    ANALYTICAL               histórico, científico, analítico
    PREVENTIVE               prevenção, detecção, proteção, resposta,
                             denúncia, pesquisa ética
    UNSPECIFIED              não estabelecido
```

**A classificação semântica que produz o descritor está fora deste
módulo, e isso é declarado, não escondido.** `stated_intent` é campo
descritivo: `CLAIMED PURPOSE != PROVEN PURPOSE`. Nada aqui lê texto
livre para decidir — sem classificador NLP, sem chamada de provider,
sem palavra-chave canônica, sem score.

### 2.6 A regra da fronteira

```
capabilities vazio                      → NOT_APPLICABLE (a fronteira não opina)
engagement ∈ {ANALYTICAL, PREVENTIVE}   → NOT_APPLICABLE (segue para policy local)
engagement ∈ {OPERATIONAL_ENABLEMENT,
              UNSPECIFIED}              → PROHIBITED
```

`UNSPECIFIED` proíbe, e essa é a decisão mais consequente do
corretivo. Diante de capacidade crítica, ausência de finalidade
legítima demonstrável **não** autoriza inventar uma:

```
MISSING SAFE INTENT != AUTHORIZATION TO INVENT ONE
```

Tratar "não sei" como "provavelmente tudo bem" seria fabricar
finalidade — o mesmo erro que a E3 proíbe em outro registro
(`MISSING EVIDENCE != AUTHORIZATION TO FABRICATE`).

**A fronteira nunca admite.** Ela proíbe ou se cala. Um piso de
segurança que concedesse permissão seria uma autoridade concorrente da
policy local, e a ordem da §2.2 deixaria de fazer sentido.

### 2.7 `GovernanceResolution`

Imutável, transitória, não persistida — como `GovernanceDecision`,
`IntegrityFinding` e `SyncReport`.

Campos: `outcome`, `blocked_capabilities`, `preserved_intent`,
`admissible_alternatives`, `constraints`, `declared_preservations`,
`declared_losses`, `policy_key`/`policy_version`/`matched_rule_id`
quando aplicável, `safety_boundary_version`/`safety_rationale`, e
`execution_authorized`.

`declared_preservations`/`declared_losses` reaproveitam
deliberadamente o vocabulário de `TransformationRecord` (E3.4): quando
algo é bloqueado, dizer **o que se preservou e o que se perdeu** é a
mesma disciplina que a E3 aplica a transformações — uma resolução que
não declara perda afirma não ter perdido nada, o que é quase sempre
falso.

`execution_authorized` é `True` **somente** em `ADMISSIBLE`. Nem
`NOT_APPLICABLE`, nem `PROHIBITED`, nem a existência de alternativas
autorizam coisa alguma:

```
REDIRECTION != AUTHORIZATION
```

### 2.8 Alternativas: propostas, nunca executadas

As alternativas são um **catálogo curado por capacidade**, com
categorias seguras — prevenção, detecção, proteção, resposta, denúncia
e pesquisa ética com dados sintéticos. São textos de orientação, sem
nenhum detalhe operacional, e nada as executa: `GovernanceResolution`
é value object, e o manager não tem executor.

E o corretivo exige o inverso também: **não conservar na resolução
detalhes operacionais nocivos desnecessários**. Por isso a resolução
registra as *capacidades* bloqueadas (vocabulário fechado) e nunca o
conteúdo do pedido.

### 2.9 `preserved_intent` só quando demonstrável

Preenchido apenas quando o engajamento é `PREVENTIVE` ou `ANALYTICAL`
— isto é, quando há intenção legítima **declarada de forma tipada**,
não inferida de texto. Em `UNSPECIFIED`, fica `None`: não há o que
preservar, e inventar seria exatamente o que a §2.6 proíbe.

### 2.10 Imutabilidade real (defeito 4)

Duas camadas, seguindo o padrão que a E3.3.1 estabeleceu:

1. `update()` e `delete()` do repositório **rejeitam** com exceção de
   domínio, antes de tocar a sessão;
2. evento de mapper `before_update`/`before_delete` em
   `GovernancePolicy` — pega a mutação ORM que contorna o método, que
   é exatamente o caminho pelo qual o defeito foi reproduzido.

**Não afirmo proteção em nível de banco**, porque não a implementei:
um `UPDATE` SQL direto continua possível, como em toda a E3. O teste
correspondente verifica o que existe, e o documento diz o que não
existe.

### 2.11 Caminho canônico (defeito 5)

`resolve()` é o caminho público canônico: recebe `policy_key` e um
instante, **busca a versão vigente** e devolve `GovernanceResolution`
com proveniência explícita. Não aceita objeto `GovernancePolicy` do
chamador.

`evaluate()` permanece — é a função pura que os testes da E4.3 já
exercitam e que `resolve()` reutiliza — mas passa a documentar
explicitamente que **não é autoridade ativa**: avalia a policy que lhe
derem, inclusive uma nunca publicada.

### 2.12 `rule_id` duplicado (defeito 6)

Rejeitado na publicação **e** na desserialização. Duplicata torna o
fundamento da decisão ambíguo — "regra `mesmo`" deixa de identificar
qual regra — e proveniência ambígua é pior que ausente, porque parece
proveniência.

### 2.13 Rapidez

```
avaliação pura em memória          uma avaliação por operação de alto nível
nenhuma consulta por CognitiveObject   nenhuma Search/Retrieval
nenhuma chamada de ferramenta/provider  nenhuma escrita
nenhum score universal
```

`resolve()` faz **uma** leitura (a versão vigente) e nada mais.
`assess_capability()` é pura: zero I/O.

---

## 3. Sétimo defeito, achado durante o corretivo

`import app.memory.schemas.governance` como **primeiro** import
falhava com `ImportError` — ciclo `schemas.governance →
models.governance_enums → models/__init__ → governance_policy →
schemas.governance`. Confirmado no HEAD limpo da E4.3 (`6b6445e9`), em
clone independente.

Passava despercebido porque a suíte sempre importava
`app.memory.models` antes. É meu, é da E4.3, e é o tipo de defeito que
só aparece quando alguém importa numa ordem que ninguém tinha tentado.

Corrigido com import tardio dentro dos dois métodos estáticos de
`GovernancePolicy` e anotações adiadas. O teste `sr13` roda **quatro
ordens de import em interpretadores limpos** — dentro do mesmo
processo, `sys.modules` esconderia o ciclo.

## 4. Implementação

```
app/memory/models/governance_enums.py               + CriticalCapability,
                                                      CapabilityEngagement,
                                                      GovernanceOutcome.PROHIBITED
app/memory/services/platform_safety_boundary.py     fronteira em código, versionada
app/memory/schemas/governance.py                    + GovernanceResolution
app/memory/models/governance_policy.py              guardas ORM + rule_id único
app/memory/repositories/governance_policy_repository.py  update/delete rejeitam
app/memory/services/governance_manager.py           + resolve() canônico
```

Nenhum arquivo de E3, E4.1 ou E4.2 tocado. Nenhuma migração — a
fronteira não tem tabela, por desenho.

### 4.1 Ajuste num verificador da E4.3

`test_gv16` comparava o **texto** do código-fonte procurando termos
proibidos, e passou a acusar as docstrings novas que citam
nominalmente o que o módulo *não* faz. Falso positivo do verificador,
não violação.

Corrigido comparando apenas o **código executável** (AST com
docstrings removidas). A asserção é a mesma; o que mudou foi como ela
lê o fonte. O mesmo cuidado foi aplicado desde o início em `sb7`.

## 5. Testes

22 testes novos em `tests/unit/memory/test_governance_safety.py`.

| Requisito do corretivo | Teste |
|---|---|
| WMD operacional ⇒ `PROHIBITED` mesmo com `ADMIT` local | `sr1` |
| perfilamento de menores ⇒ `PROHIBITED` | `sb2` |
| nenhuma busca/recuperação/ferramenta/escrita nesses casos | `sr5` |
| discussão histórica/científica/preventiva não é proibida por tópico | `sb3` |
| prevenção de aliciamento com dados sintéticos segue para policy local | `sb4`, `sr6` |
| alternativa segura não autoriza a operação original | `sr4` |
| ausência de intenção segura não gera intenção inventada | `sb5` |
| fronteira prevalece sobre domínio, ator e purpose | `sr2` |
| avaliação determinística e sem escritas | `sr7`, `sr5` |
| policy publicada rejeita `update` e `delete` | `sr8`, `sr9`, `sr10` |
| `rule_id` duplicado rejeitado | `sr12` |
| policy arbitrária/inativa não aceita no caminho canônico | `sr11` |
| testes E4.3 continuam passando | 47/47 |
| regressão E3/E4.1/E4.2 = zero | 598 / 40 / 42 |

`sr9` merece nota: ele exercita **o caminho exato pelo qual o defeito
foi reproduzido** — mutar o atributo do objeto carregado e dar
`flush()`, contornando o repositório.

## 6. Alcance declarado com honestidade

A imutabilidade é imposta em **duas camadas**: override de
`update`/`delete` no repositório e evento de mapper
`before_update`/`before_delete` no modelo. Isso cobre o caminho ORM,
que é o caminho da aplicação.

**Não há garantia em nível de banco.** Um `UPDATE`/`DELETE` SQL direto
continua possível — como em toda a E3 — e este documento diz isso em
vez de afirmar proteção que não existe. O corretivo pede exatamente
essa honestidade: "não afirmar proteção em nível de banco sem teste
real correspondente".

Do mesmo modo, a classificação semântica que produz o
`CapabilityDescriptor` **está fora deste módulo** e é declarada como
fronteira explícita. Nada aqui lê texto livre para decidir.

## 7. Resultados

```
FULL_SUITE = 1207 passed / 1 skipped / 0 failed
E3_REGRESSION_DELTA   = 0   (598/598)
E4_1_REGRESSION_DELTA = 0   (40/40)
E4_2_REGRESSION_DELTA = 0   (42/42)
E4_3 (existentes)     = 47/47

GLOBAL_COVERAGE = 98,70%   APP_MEMORY = 100%   APP_COGNITIVE = 100%
RUFF = PASS   BLACK = PASS   MYPY_NEW_ERRORS = 0   git diff --check = limpo
MIGRATION_HEAD = 4ca61776b982 (inalterada)   SCHEMA_ORM_DRIFT = 0
DATABASE_WRITES_DURING_EVALUATION = 0

PLATFORM_SAFETY_BOUNDARY_VERSION = 1   (em código, sem tabela)
E3_UNCHANGED = TRUE   E4_1_UNCHANGED = TRUE   E4_2_UNCHANGED = TRUE

E4_3_1_IMPLEMENTATION = COMPLETE
E4_3_FINAL_STATUS     = AWAITING_INDEPENDENT_AUDIT
READY_FOR_E4_4        = FALSE
```

---

# E4.3.2 — Corretivo dos invariantes de `GovernanceResolution`

Correção mínima sobre o patch 42. Nada de E4.3/E4.3.1 foi
reconstruído.

## 8. O defeito, e o fato de eu já ter sido corrigido nele

`GovernanceResolution` foi declarada `frozen` e parou aí. `frozen=True`
protege a **referência**, não o **conteúdo** — que é exatamente o que
a `E4.2.1` já havia corrigido em `MemoryContext`, com a mesma
explicação, três patches antes. Repeti o erro num value object que
decide autorização.

Reproduzido antes de qualquer correção:

| # | Sintoma |
|---|---|
| 1 | `frozen=True` aceitava lista externa em `blocked_capabilities` |
| 2 | mutar a lista original **alterava a resolução construída** (1 → 2 capacidades) |
| 3 | com lista dentro, `hash()` levantava `TypeError` |
| 4 | estados contraditórios aceitos |

E o pior caso do item 4:

```
outcome = ADMISSIBLE
blocked_capabilities = (CHILD_SEXUAL_EXPLOITATION,)
execution_authorized = True
```

Uma autorização que carrega a prova da própria recusa. Numa camada
cuja função é autorizar ou recusar, isso não é inconsistência
cosmética.

`SafetyAssessment` tinha os mesmos defeitos — verificado na mesma
reprodução. Corrigir só a resolução deixaria a metade errada
exatamente no caminho pelo qual a outra é construída.

## 9. Correção

Invariantes em `__post_init__`, valendo em toda construção pública, em
ambos os value objects.

**Tipos e canonicalização**

```
blocked_capabilities   tuple[Any, ...] → tuple[CriticalCapability, ...]
                       ordenada, desduplicada, realmente imutável
coleções textuais      tupla, ordem preservada (é curada), sem repetição,
                       sem entrada em branco
outcome / operation    exige o membro do enum, não a string equivalente
versões                int >= 1; `bool` recusado apesar de ser subclasse de int
```

O detalhe do enum merece nota: `StrEnum` compara igual à sua string,
então aceitar `"admissible"` passaria despercebido em quase todo teste
de comportamento e só quebraria num `is`. O tipo é a garantia.

**Coerência**

```
PROHIBITED                    exige ≥ 1 capacidade bloqueada
demais resultados             não carregam capacidade bloqueada
ADMISSIBLE / INADMISSIBLE     exigem proveniência local completa
PROHIBITED                    não carrega proveniência local nenhuma
identidade de policy          tudo-ou-nada
matched_rule_id               exige identidade de policy
NOT_APPLICABLE                não cita regra
```

Cada uma protege algo concreto. `PROHIBITED` sem capacidade bloqueada é
uma recusa irrecorrível — não há como auditar nem propor alternativa.
`PROHIBITED` com proveniência local é consulta fabricada, porque quando
a fronteira proíbe a policy **sequer é consultada** (E4.3.1).
Proveniência parcial é pior que ausente, porque parece proveniência.

`INADMISSIBLE` foi incluído na exigência de proveniência completa
embora o corretivo só pedisse `ADMISSIBLE`: ele sempre nasce de uma
regra `DENY` que casou, e deixá-lo de fora seria arbitrário — é o
mesmo invariante.

`execution_authorized` continua **derivada** e nunca armazenada; o que
mudou é que agora ela só pode ser `True` sobre um estado válido,
porque o inválido não chega a existir.

## 10. Testes

31 testes novos. **30 falham contra o patch 42** e passam no
corrigido. O trigésimo primeiro —
`test_e432_resolutions_from_resolve_remain_valid` — passa nos dois, e
isso é correto: ele é o guarda de regressão pedido ("resoluções
produzidas por `resolve()` continuam válidas"), não um provador de
defeito.

Cobertura de `app/memory` de volta a 100%; três ramos de validação
descobertos foram fechados com casos (`None` explícito em coleção,
`policy_id` não-UUID, `str` como coleção).

## 11. Resultados

```
FULL_SUITE = 1243 passed / 1 skipped / 0 failed
E3_REGRESSION_DELTA   = 0   (598/598)
E4_1_REGRESSION_DELTA = 0   (40/40)
E4_2_REGRESSION_DELTA = 0   (42/42)
E4.3 + E4.3.1 existentes = 47/47 integração + unit; 72/72 no conjunto

GLOBAL_COVERAGE = 98,73%   APP_MEMORY = 100%   APP_COGNITIVE = 100%
RUFF = PASS   BLACK = PASS   MYPY_NEW_ERRORS = 0   git diff --check = limpo
MIGRATION_HEAD = 4ca61776b982 (inalterada)   SCHEMA_ORM_DRIFT = 0

ciclo de imports preservado (4 ordens verificadas por sr13)
E3_UNCHANGED = TRUE   E4_1_UNCHANGED = TRUE   E4_2_UNCHANGED = TRUE

E4_3_2_IMPLEMENTATION = COMPLETE
E4_3_FINAL_STATUS     = AWAITING_INDEPENDENT_AUDIT
READY_FOR_E4_4        = FALSE
```
