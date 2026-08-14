# E4_ARCHITECTURE_FREEZE — congelamento arquitetural da Entrega 4

**Módulo:** E4.0 — Memory & Governance Architecture / Contract Freeze
**Natureza:** congelamento de arquitetura, semântica, fronteiras e
sequência. **Nenhuma implementação.**

```
BASELINE
    E3 = FROZEN FINAL
    E3.12.1 = PASS FINAL
    GATE_E3_TO_E4 = PASS

    HEAD = 014455f93bf7433232a945062e2024d536f7a004   ✓ verificado
    TREE = 83217c4026a6dc59ccfdec2286d70f77d566add9   ✓ verificado
    worktree limpa, 35 commits sobre a baseline E1/E2
```

---

## 1. A regra que organiza tudo

```
E3 OWNS COGNITIVE PATRIMONY.
E4 OPERATES OVER COGNITIVE PATRIMONY.

E4 consumes E3.
E4 does not replace E3.
E4 does not create a second Cognitive Library.
```

Toda decisão desta entrega decorre daí. Quando uma questão de desenho
tiver duas respostas plausíveis, a resposta correta é a que **não**
duplica, não estende e não reinterpreta a E3.

---

## 2. Documentos desta entrega

| Documento | Conteúdo |
|---|---|
| `E4_ARCHITECTURE_FREEZE.md` | este — freeze, matrizes E, perguntas pré-freeze, teste forte |
| `E4_MEMORY_SEMANTICS.md` | definição de memória, quatro distinções, LOP, CLEO, matrizes A e C |
| `E4_GOVERNANCE_BOUNDARIES.md` | governança, compliance, learning, retenção, defense in depth, matriz D |
| `E4_PRIMITIVE_OWNERSHIP.md` | admissão de primitivas, fonte da verdade, matriz B |
| `E4_DOMAIN_MODEL_DRAFT.md` | entidades candidatas — rascunho, nada congelado como esquema |
| `E4_IMPLEMENTATION_SEQUENCE.md` | auditoria da sequência, emendas propostas, matriz G |
| `E4_SYNC_BOUNDARY.md` | portable / local / transient, matriz F |
| `E4_DEFERRED_INVENTORY.md` | o que a E4.0 não entrega e para onde vai |
| `EDR_COUT_PIA_E4.md` | decisões congeladas, em forma normativa |

---

## 3. Matriz E — CONTEXT vs SESSION vs IDENTITY vs DOMAIN

| | Context | Session | Identity | Domain |
|---|---|---|---|---|
| **O que é** | circunstância de uma operação | período de interação | quem/o que algo é | recorte lógico do patrimônio |
| **Responde** | de onde se olha | quando/em qual troca | o que é isto | a que recorte pertence |
| **Persistido** | definição sim, instância não | fora do domínio cognitivo | **sim** (COID/CLID) | **sim** |
| **Imutável** | não | — | **sim** | não |
| **Proprietário** | E4.2 | infra / proveniência | **E3.1/E3.2/E3.3** | E4.1 |
| **Altera patrimônio** | **não** | não | é o patrimônio | **não** |
| **Cardinalidade com objeto** | N:N (vista) | — | 1:1 | 0..N |
| **Viaja no Sync** | não | como `session_id` em proveniência | sim (é o patrimônio) | em aberto |

Congelado:

```
CONTEXT != IDENTITY
CONTEXT != MEMORY
CONTEXT != POLICY
CONTEXT != SESSION
```

Uma sessão **participa** de um contexto; não o define. A E3 já registra
`session_id` em `provenance_records` — sessão é uma dimensão de
proveniência, não a moldura inteira.

`CONTEXT != POLICY` é a mais fácil de perder na implementação:
contexto diz *de onde se olha*; policy diz *o que é permitido ver*.
Fundi-los produz um objeto que é pergunta e resposta ao mesmo tempo, e
nenhuma auditoria consegue separá-los depois.

### 3.1 Onde estão as demais matrizes

| Matriz | Onde |
|---|---|
| **A** — existence / persistence / accessibility / relevance | `E4_MEMORY_SEMANTICS.md` §3.3 |
| **B** — E3 vs E4 ownership | `E4_PRIMITIVE_OWNERSHIP.md` §3 |
| **C** — memory / storage / search / transcript | `E4_MEMORY_SEMANTICS.md` §6 |
| **D** — integrity / governance / compliance / learning / repair | `E4_GOVERNANCE_BOUNDARIES.md` §3 |
| **E** — context / session / identity / domain | aqui, §3 |
| **F** — portable / local / transient | `E4_SYNC_BOUNDARY.md` §3 |
| **G** — dependências entre módulos E4 | `E4_IMPLEMENTATION_SEQUENCE.md` §5 |

---

## 4. Accessibility — o que a E4.0 faz e não faz (§6)

Os quatro estados da E3 são **preservados sem alteração**:

| Estado | Semântica atual (E3) | Existe? |
|---|---|---|
| `ACTIVE` | operacionalmente acessível; default de criação | sim |
| `LATENT` | existe, não em uso corrente; ainda "acessível" para `assert_accessible` | sim |
| `INACCESSIBLE` | acesso não admissível | **sim** |
| `CAUSALLY_EXTINCT` | a distinção deixou de existir no presente; a história permanece | **sim** |

**Transições congeladas hoje** (verificado no código da E3):

- `→ CAUSALLY_EXTINCT` exige `reason` não-vazio, senão `PIA-8018`;
- transição para o mesmo estado é no-op idempotente;
- `CAUSALLY_EXTINCT` **nunca** é default e **nunca** é inferido de
  ausência — invariante de todo o sistema, não só de E3.6;
- `assert_accessible` aceita apenas `ACTIVE` e `LATENT`.

**Transições que permanecem indefinidas:** todas as demais. O código
da E3 é explícito ao deferir: *"a máquina de transição de estados
completa (quem pode mover o quê, sob qual autoridade) é escopo de
E4"*. Em particular seguem indefinidos: se `CAUSALLY_EXTINCT` é
terminal; se `INACCESSIBLE → ACTIVE` é livre; e qual autoridade cada
transição exige.

**A E4.0 não inventa nenhuma transição.** Política completa deferida
para E4.3/E4.7 conforme a emenda de sequência.

Congelado, e reafirmado:

```
CAUSALLY_EXTINCT != HISTORICAL_ERASURE
```

---

## 5. Teste arquitetural forte (§29) — executado

O §29 pede demonstração **conceitual**. Foi feita demonstração
**executável**, contra a E3 congelada, porque um contrato que só
funciona no papel não é um contrato verificado.

O script é descartável e **não foi commitado** — não é código de
produção, não é teste da suíte, não altera nada. Resultado:

```
Accessible(P, C1) = 1 objeto      C1 = {ACTIVE}
Accessible(P, C2) = 2 objetos     C2 = {ACTIVE, LATENT}
Accessible(P, C3) = 0 objetos     C3 = {ACTIVE} ∩ escopo de domínio

1. CONTEXT CHANGES VIEW
   Accessible(P,C1) != Accessible(P,C2)   ✓
   Accessible(P,C1) != Accessible(P,C3)   ✓

2. CONTEXT DOES NOT REWRITE PATRIMONY
   censo canônico idêntico byte a byte    ✓

3. INACCESSIBLE REMAINS HISTORICALLY REPRESENTABLE
   objeto INACCESSIBLE ainda existe       ✓
   objeto CAUSALLY_EXTINCT ainda existe   ✓
   história causal preservada             ✓
   linhagem preservada                    ✓
   invisível em C1 e C2                   ✓

4. NOT_RETRIEVED != FORGOTTEN
   ausente de toda vista contextual       ✓
   recuperável por COID direto            ✓

COUT_STRONG_ARCHITECTURAL_TEST = PASS
E3_MODIFIED = NO
```

**Galaxy Trace e Broken Glass não regridem:** o objeto
`CAUSALLY_EXTINCT` do cenário mantém história causal e linhagem
íntegras enquanto está fora de toda vista — que é exatamente o que a
E3.12 provou nos testes G9 e G10, agora sob filtragem contextual.

**O achado mais relevante:** o contexto foi construído como objeto
**puramente em memória**, sem tabela, sem migração, sem estado
persistido. A separação entre vista e patrimônio não exigiu nenhuma
primitiva nova. Isso é evidência forte de que a E4 pode ser camada de
composição sobre a E3 — e não uma segunda biblioteca.

---

## 6. As vinte perguntas pré-freeze (§31)

**1. O que é memória no PIA?**
`Memory(Context) = Admissible_Context(Persistent(CognitivePatrimony))`.
Uma função de contexto sobre patrimônio — não uma tabela, não um
score, não um lugar.

**2. O que NÃO é memória?**
Storage, transcript, search, index, cache, banco vetorial, e "o estado
atual das coisas". O último é o erro mais sutil: descarta trajetória,
que é o que a E3 inteira existe para preservar.

**3. Quem possui o patrimônio?**
O usuário/organização, em sentido de **controle lógico**. O PIA-OS
gerencia persistência. Nenhum fornecedor de modelo adquire posse por
participar da proveniência (`COUT-P10`). Titularidade jurídica é
questão distinta e não é decidida por arquitetura.

**4. Quem possui a política?**
A instalação. Policy é configuração local, versionada, e **não viaja
no Sync**. Importar patrimônio nunca importa a governança da origem.

**5. O que é persistência?**
Continuidade de uma distinção relevante através de estados,
transformações ou tempo — materializada em CLID, linhagem,
transformação e história causal. **Não** é popularidade, recência,
frequência nem score.

**6. O que é acessibilidade?**
Admissibilidade de acesso em determinado contexto. Relacional por
natureza: não existe "objeto acessível", existe "acessível *em C*". A
E3 persiste um eixo (`AccessibilityState`); a E4 acrescenta o
contextual. Compõem, não se substituem.

**7. O que é relevância?**
Pertinência para uma finalidade/contexto. É julgamento, não fato do
patrimônio, e **nunca é materializada**. Irrelevância jamais autoriza
alteração de existência.

**8. Contexto é persistente ou transiente?**
Provavelmente ambos, e a distinção é o ponto: `ContextDefinition`
persistida e reutilizável; `MemoryContext` como instância efêmera de
operação, não persistida. **Não congelado** — decidido em E4.2. A
demonstração do §5 funcionou com contexto puramente em memória, o que
sugere que a instância não precisa persistir.

**9. `MemoryDomain` precisa de identidade?**
Sim. É entidade nomeável, referenciável e de vida longa, com atributos
próprios. Identidade própria, **nunca** COID — domínio não é objeto
cognitivo.

**10. `Membership` precisa de identidade?**
**Recomendado que sim.** Sem identidade, sair e voltar a um domínio é
indistinguível de nunca ter saído. Com identidade e `left_at`, o
pertencimento tem história. É a mesma escolha que a E3 fez em
`Relationship` com `retired_at`, pela mesma razão
(`RETIRE != DELETE_HISTORY`). Decisão formal em E4.1.

**11. Política é patrimônio cognitivo ou configuração?**
**Configuração.** Policy não tem COID, não tem linhagem, não tem
história causal, não participa de transformações. É versionada,
mutável e local. Tratá-la como patrimônio a tornaria imutável e
transportável — exatamente o oposto do que precisa ser.

**12. Política viaja no Sync?**
**Não.** `POLICY_PORTABLE = FALSE`. Autoridade não é transferível, o
contexto de execução difere entre instalações, e uma policy importada
produziria objetos invisíveis no destino sem que ninguém ali tenha
decidido isso.

**13. Retention policy é local ou portable?**
**Local**, com agravante: obrigações de retenção são jurisdicionais.
O destino de um import aplica **suas próprias** obrigações ao
patrimônio recebido.

**14. Como legal erasure convive com `CausalHistory`?**
Tensão real, **registrada e não resolvida** — decisão em E4.9. Direção
mais promissora: apagar o **referente** preservando a **referência**,
já que a E3 armazena referências e nunca conteúdo. Direções
alternativas e o reconhecimento do limite em
`E4_GOVERNANCE_BOUNDARIES.md` §6.2. O que está congelado é que
`PRESERVATION = RETENTION FOREVER` é **falso**.

**15. Consolidação cria novo `CognitiveObject`?**
Sim — `S1` é um `CognitiveObject` legítimo, ligado a `M1..M3` por
`LineageEdge` com `relation_type=MERGE` e por `TransformationRecord`
com perdas declaradas. **Nenhuma entidade nova é necessária.**

**16. O que ocorre com fontes consolidadas?**
**Nada.** Continuam existindo, com identidade, história e linhagem
intactas. `S1 ← {M1, M2, M3}` permanece rastreável.
`CONSOLIDATION != DELETION`. As fontes podem mudar de acessibilidade;
não de existência.

**17. Como impedir vazamento entre domínios?**
E4.8, sobre governança (E4.3) e domínio (E4.1), com a vista admissível
como único caminho de leitura. Defense in depth: política explícita na
aplicação; RLS, se adotado, como camada adicional — **nunca**
substituto. Advertência já registrada: um mecanismo que vaza
existência por erro de FK contradiz `INACCESSIBLE != NONEXISTENT` na
direção mais perigosa.

**18. Qual defesa pertence ao app e qual ao DB?**
App: **política cognitiva explícita** — é onde a decisão é tomada,
auditada e versionada. DB: defesa em profundidade. A política nunca
pode existir *apenas* como predicado de RLS, porque assim não pode ser
auditada, versionada nem explicada. Antes de qualquer adoção de RLS:
analisar owner/`BYPASSRLS`, backup/`pg_dump` parcial silencioso, e
integridade referencial.

**19. O que a E4.11 pode registrar sem virar learning engine?**
**Pode:** que uma experiência ocorreu, o resultado observado, quem
validou, contra qual critério, com qual evidência, quando — fatos
datados e atribuídos. **Não pode:** que a experiência "prova" algo,
score de confiança, generalização derivada, recomendação de ação.
Teste prático: **se remover o registro mudaria o comportamento do
sistema, virou learning engine.**

**20. Qual é exatamente o gate E4 → E5?**
Proposto em `E4_IMPLEMENTATION_SEQUENCE.md` §6, por simetria com o
gate E3 → E4 que funcionou: o executor pode declarar
`E4.12_IMPLEMENTATION_GATE = PASS`, mas `E4_FINAL_FREEZE` permanece
`PENDING_INDEPENDENT_AUDIT` e `READY_FOR_E5 = FALSE` até auditoria
independente. Doze condições substantivas listadas; a mais importante
é `E3_MODIFIED = NO`, verificável por tree hash.

---

## 7. Stop conditions (§30)

```
STOP_CONDITIONS = NONE
```

As quinze verificadas, uma a uma:

| # | Condição | Ocorreu |
|---|---|---|
| 1 | modificar E3 para fechar E4.0 | **não** — E3 intacta, tree verificado |
| 2 | reinterpretar COID/CLID | não |
| 3 | redefinir Provenance | não |
| 4 | redefinir CausalHistory | não |
| 5 | transformar Accessibility em existência | não — é o oposto do congelado |
| 6 | introduzir global score | não — proibido explicitamente |
| 7 | introduzir decision engine COUT | não |
| 8 | implementar learning | não |
| 9 | implementar repair | não |
| 10 | implementar orchestration | não |
| 11 | criar primitive sem contrato suficiente | não — regra de admissão aplicada, 6 candidatas |
| 12 | escolher policy engine por conveniência | **não** — deliberadamente adiado |
| 13 | tornar vector DB fonte da verdade | não |
| 14 | transcript como memória automática | não |
| 15 | importar estruturas cosmológicas | não — `PHYSICS_IN_APP = NONE` |

Duas merecem nota. A **12** foi ativamente evitada: a forma de
expressão das `rules` de policy ficou em aberto de propósito, porque a
semântica deve preceder a ferramenta. A **1** foi a que chegou mais
perto: existe um item real na E3 (o proxy interino de
`CAUSALLY_EXTINCT`, hoje fechável porque `E3.9` existe), e a decisão
foi **não tocá-lo** — está registrado em `E4_DEFERRED_INVENTORY.md`
§5 como corretivo próprio da E3, fora da E4.

---

## 8. Um ponto que exige sua decisão

A auditoria da sequência encontrou **duas inversões de dependência
reais** (`E4_IMPLEMENTATION_SEQUENCE.md` §2–§4):

- `E4.3 Accessibility Policy` precede `E4.7 Governance Policy`, mas
  precisa do conceito de autoridade que só chega em E4.7 — o próprio
  código da E3 define o escopo de E4.3 como *"quem pode mover o quê,
  **sob qual autoridade**"*;
- `E4.6 Memory Retrieval` precede `E4.7`, e nasceria sem ponto de
  composição para governança.

**Recomendação:** trocar E4.3 e E4.7 de posição. Alternativa viável:
manter a numeração e congelar **agora, por escrito**, a divisão de
escopo entre matriz estrutural de transição (E4.3) e autoridade
(E4.7).

Conforme §19 do prompt canônico, isso é **proposto, não congelado**.
Todo o restante desta entrega está congelado.

---

## 9. Gate

```
E4.0_ARCHITECTURE_GATE = PASS
E4_ARCHITECTURE        = FROZEN
READY_FOR_E4_1         = TRUE

E4_SEQUENCE = AUDITED — emenda proposta, pendente de decisão
```

E4.1 **não** é iniciada automaticamente.
