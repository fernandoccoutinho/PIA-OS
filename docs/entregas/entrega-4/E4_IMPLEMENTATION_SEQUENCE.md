# E4_IMPLEMENTATION_SEQUENCE — sequência canônica e grafo de dependências

**Módulo:** E4.0 / E4.0.1 — Sequence & Ownership Consistency Freeze
**Natureza:** sequência **congelada**. Nenhuma implementação.

> **Estado: CONGELADO.** A auditoria da E4.0 encontrou duas inversões
> de dependência na sequência originalmente proposta. O titular do
> Plano Mestre aprovou a **OPTION A** (troca de E4.3 e E4.7). Este
> documento passa a registrar a sequência canônica única — não mais
> uma proposta.
>
> ```
> SEQUENCE_DECISION = OPTION_A
> E4_SEQUENCE       = FROZEN
> ```

---

## 1. Sequência canônica

```
E4.0   Architecture & Contract Freeze
E4.1   Memory Domain Foundation
E4.2   Context Manager
E4.3   Governance Policy
E4.4   Persistence Manager
E4.5   Consolidation Manager
E4.6   Memory Retrieval
E4.7   Accessibility Policy
E4.8   Memory Isolation
E4.9   Retention / Forgetting
E4.10  Compliance Boundary
E4.11  Validated Experience Registry
E4.12  Final Integration Gate
```

Esta é a **única** interpretação válida. Qualquer documento que
divirja dela está desatualizado e foi corrigido na E4.0.1.

**Ownership canônico:**

```
E4.3 owns:  GovernancePolicy
            governance authority semantics

E4.7 owns:  AccessibilityPolicy
            admissibility / transition policy
```

---

## 2. Razão do congelamento

```
GOVERNANCE BEFORE ACCESSIBILITY POLICY
GOVERNANCE BEFORE MEMORY RETRIEVAL
```

### 2.1 Por que Governance precede Accessibility Policy

A Accessibility Policy precisa responder **quem pode mover/acessar o
quê, sob qual autoridade**. O código congelado da E3, em
`app/cognitive/services/accessibility_manager.py`, define o escopo
nestas palavras:

> "a máquina de transição de estados completa (**quem pode mover o
> quê, sob qual autoridade**) é escopo de `E4`"

Autoridade **é** o conceito de governança. Ela não pode ser definida
só depois de ser usada.

Mantida a ordem original, uma de duas coisas aconteceria, e ambas são
ruins: ou o módulo de acessibilidade inventaria um modelo de
autoridade *ad hoc* — e o módulo de governança chegaria depois para
encontrar um segundo modelo já em produção, exatamente o cenário de
duas fontes da verdade que a §21 da E4.0 proíbe; ou entregaria
transições sem autoridade nenhuma, a serem retrofitadas — e
retrofitting de controle de acesso é o padrão que mais confiavelmente
produz vazamento.

### 2.2 Por que Governance precede Memory Retrieval

Memory Retrieval compõe `Context + Governance + Accessibility +
Search(E3)` para produzir a vista admissível. Construído antes de
Governance existir, nasceria **sem o ponto de composição** para a
decisão de governança — o mesmo defeito de §2.1, uma camada acima.

Com a OPTION A, Governance passa a ser E4.3 e antecede E4.6
naturalmente.

---

## 3. Registro histórico do achado

Preservado deliberadamente, conforme a disciplina do projeto de nunca
apagar a história de uma correção.

A sequência originalmente proposta na E4.0 tinha
`E4.3 = Accessibility Policy` e `E4.7 = Governance Policy`. A
auditoria da E4.0 identificou as duas inversões descritas na §2 e
apresentou duas emendas: **(A)** trocar as posições, e **(B)** manter
a numeração dividindo o escopo entre matriz estrutural de transição e
autoridade.

**OPTION A foi aprovada.** A opção B foi descartada — a divisão era
mais frágil do que aparentava, porque várias perguntas de transição
(`INACCESSIBLE → ACTIVE` é válida?) só têm boa resposta quando se sabe
*quem* pergunta.

---

## 4. Fronteira de Memory Retrieval (E4.6)

```
RETRIEVAL != GOVERNANCE
```

Memory Retrieval **não define autoridade**. Ele consome:

```
MemoryDomain (E4.1)
Context      (E4.2)
Governance   (E4.3)
Accessibility
Search       (E3.8)
```

e produz:

```
admissible memory view
```

### 4.1 Precisão obrigatória sobre "Accessibility" nesta lista

O termo cobre **duas coisas distintas**, e confundi-las reintroduziria
a inversão que este corretivo elimina:

| O que é | Onde vive | Natureza | Relação com E4.6 |
|---|---|---|---|
| `AccessibilityState` (ACTIVE / LATENT / INACCESSIBLE / CAUSALLY_EXTINCT) | **E3.6 — já existe e está congelado** | estado persistido do objeto | **dependência dura** — já satisfeita |
| `AccessibilityPolicy` | **E4.7** | política de **transição**: quem pode mover entre estados | **dependência de composição** |

Retrieval **lê**. Filtrar por `AccessibilityState` não exige política
de transição alguma — transição é mutação, e recuperação não muta
nada. O teste arquitetural forte executado na E4.0 confirmou isso na
prática: a vista admissível foi construída usando apenas
`AccessibilityState` da E3 mais o recorte de contexto, sem nenhuma
política de transição existir.

Portanto **E4.6 não bloqueia em E4.7**. Quando E4.7 existir, a vista
admissível passa a compor também a política de transição; até lá,
E4.6 é construível e testável por completo.

Isso é consistente com o gate desta entrega, que exige "Retrieval
consumir **Governance**" — e não "consumir Accessibility Policy".

> **Ponto que merece sua confirmação.** Se a intenção for que E4.6
> dependa **duramente** de `AccessibilityPolicy` (E4.7), então E4.6 e
> E4.7 também precisariam trocar de posição, pelo mesmo argumento da
> §2. A leitura adotada aqui — dependência de composição, não dura —
> é a que mantém a sequência aprovada internamente coerente, e é
> substantivamente correta porque ler um estado não é o mesmo que
> autorizar a mudança dele. Registrado explicitamente para não ser
> uma escolha silenciosa.

---

## 5. Fronteira de Accessibility Policy (E4.7)

E4.7 **não define**:

```
identidade        → E3.1 / E3.2 / E3.3
existência        → E3 (patrimônio)
verdade           → nada define; GOVERNANCE != TRUTH ENGINE
autoridade geral  → E4.3 (Governance)
```

E4.7 **aplica** admissibilidade e transição **sob a autoridade já
definida por Governance (E4.3)**.

Congelado, e reafirmado:

```
CAUSALLY_EXTINCT != HISTORICAL_ERASURE
ACCESSIBILITY    != EXISTENCE
```

---

## 6. Fronteira de Governance Policy (E4.3)

E4.3 define:

```
authority
permission semantics
policy applicability
allowed operations
```

E preserva, sem exceção:

```
GOVERNANCE != TRUTH ENGINE
GOVERNANCE != LEARNING ENGINE
GOVERNANCE != REPAIR ENGINE
GOVERNANCE != COUT DECISION ENGINE

GOVERNANCE MAY RESTRICT ACCESS.
GOVERNANCE MUST NOT REWRITE EXISTENCE.
```

---

## 7. Grafo de dependências canônico

```
                         E3 (FROZEN)
                              |
                            E4.0
                              |
                            E4.1  Memory Domain
                              |
                            E4.2  Context
                              |
                            E4.3  Governance   <- autoridade
                       +------+------+
                  E4.4 Persistence   E4.7 Accessibility
                       |                  |
                  E4.5 Consolidation      |
                       |                  |
                       +------+-----------+
                            E4.6  Memory Retrieval
                              |
                            E4.8  Isolation
                              |
                            E4.9  Retention / Forgetting
                              |
                            E4.10 Compliance

        E4.11 Validated Experience -- ramo independente
                              |
                            E4.12 Final Integration Gate  <- consome todos
```

O ramo `E4.7 -> E4.6` é a **dependência de composição** precisada na
§4.1: a vista admissível compõe a política de transição quando ela
existir, sem que E4.6 bloqueie em E4.7.

`E4.11` permanece **independente**, conforme o contrato congelado na
E4.0 — nenhuma dependência foi inventada para ele.

---

## 8. Matriz G — dependências entre módulos da E4

Dependências **duras** (`X`) bloqueiam; **de composição** (`o`) não.

| ↓ depende de → | E3 | 4.0 | 4.1 | 4.2 | 4.3 | 4.4 | 4.5 | 4.6 | 4.7 | 4.8 | 4.9 | 4.10 | 4.11 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **E4.1** Memory Domain | X | X | — | | | | | | | | | | |
| **E4.2** Context | X | X | o | — | | | | | | | | | |
| **E4.3** Governance | X | X | X | X | — | | | | | | | | |
| **E4.4** Persistence | X | X | o | o | o | — | | | | | | | |
| **E4.5** Consolidation | X | X | | | | X | — | | | | | | |
| **E4.6** Retrieval | X | X | X | X | **X** | | X | — | **o** | | | | |
| **E4.7** Accessibility | X | X | | X | **X** | | | | — | | | | |
| **E4.8** Isolation | X | X | X | X | X | | | X | X | — | | | |
| **E4.9** Retention | X | X | o | | X | X | o | | X | X | — | | |
| **E4.10** Compliance | X | X | o | o | X | | | | X | o | X | — | |
| **E4.11** Validated Exp. | X | X | | o | | | | | | | | | — |
| **E4.12** Gate | X | X | X | X | X | X | X | X | X | X | X | X | X |

**Leitura:**

- **E4.3 (Governance) é o gargalo real** da entrega — sete módulos
  dependem dela de forma dura. É exatamente por isso que posicioná-la
  cedo importa: um gargalo tarde na sequência bloqueia trabalho já
  feito.
- **E4.6 → E4.7** é a única célula `o` de peso, e a §4.1 explica por
  quê.
- **E4.11** é o único ramo desacoplado; pode ser executado a qualquer
  momento após E4.0.
- **E4.4 → E4.5** permanece a única dependência dura fora do tronco:
  consolidação é operação de persistência, não o contrário.

---

## 9. Gate E4 → E5

Proposto por simetria com o gate E3 → E4, que funcionou:

```
E4.12_IMPLEMENTATION_GATE = PASS   <- o executor pode declarar
E4_FINAL_FREEZE           = PENDING_INDEPENDENT_AUDIT
GATE_E4_TO_E5             = PENDING
READY_FOR_E5              = FALSE  <- até auditoria independente
```

Condições substantivas propostas:

1. `Accessible(P, C1) != Accessible(P, C2)` demonstrado **em código
   executável**, não apenas em documento;
2. `Patrimony(P)` invariante sob mudança de contexto — censo canônico
   idêntico, como no teste G1 da E3.12;
3. as quatro distinções fundamentais verificáveis em teste;
4. nenhuma policy capaz de alterar existência — provado por teste
   negativo;
5. `E3_MODIFIED = NO` — a E3 permanece intacta byte a byte;
6. consolidação rastreável até as fontes (`S1 ← {M1, M2, M3}`);
7. Galaxy Trace e Broken Glass **não regridem**;
8. `LEARNING_ENGINE_IMPLEMENTED = NO` mantido;
9. neutralidade de provider preservada;
10. inventário de deferidos completo e honesto;
11. nenhuma Stop Condition;
12. auditoria independente reproduz a evidência.

A condição 5 é a mais importante e a mais fácil de verificar: os tree
hashes de `backend/app/cognitive` e `backend/alembic` devem permanecer
idênticos aos da E3 congelada ao fim da E4.
