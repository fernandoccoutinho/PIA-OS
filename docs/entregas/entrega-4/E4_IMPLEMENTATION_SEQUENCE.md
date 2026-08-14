# E4_IMPLEMENTATION_SEQUENCE — sequência auditada e grafo de dependências

**Módulo:** E4.0 — Architecture & Contract Freeze
**Natureza:** auditoria da sequência proposta. Nenhuma implementação.

> **Resultado da auditoria: a sequência proposta tem duas inversões de
> dependência reais.** Ambas estão descritas abaixo com emenda
> proposta. Conforme §19 do prompt canônico ("se houver necessidade de
> reordenar: propor antes de congelar"), a sequência é declarada
> **AUDITADA**, e o congelamento definitivo aguarda sua decisão entre
> as opções da §4.

---

## 1. Sequência proposta

```
E4.0   Architecture & Contract Freeze
E4.1   Memory Domain Foundation
E4.2   Context Manager
E4.3   Accessibility Policy
E4.4   Persistence Manager
E4.5   Consolidation Manager
E4.6   Memory Retrieval
E4.7   Governance Policy
E4.8   Memory Isolation
E4.9   Retention / Forgetting
E4.10  Compliance Boundary
E4.11  Validated Experience Registry
E4.12  Final Integration Gate
```

---

## 2. Achado 1 — `E4.3 Accessibility Policy` precede `E4.7 Governance Policy`

**Este é o achado mais sério da auditoria.**

O código congelado da E3 define o escopo de E4.3 nas seguintes
palavras, em `app/cognitive/services/accessibility_manager.py`:

> "a máquina de transição de estados completa (**quem pode mover o
> quê, sob qual autoridade**) é escopo de `E4`"

"Sob qual autoridade" **é** o conceito de governança. A E4.3, como
especificada, precisa de um conceito de autoridade que só chega em
E4.7 — quatro módulos depois.

As consequências de manter a ordem são concretas, não teóricas:

1. A E4.3 inventaria um modelo de autoridade *ad hoc* para conseguir
   fechar, e a E4.7 chegaria e encontraria um segundo modelo já em
   produção — precisamente o cenário de "duas fontes da verdade" que a
   §21 proíbe para patrimônio e que é igualmente tóxico para policy.
2. Ou a E4.3 entregaria uma política de transição sem autoridade —
   isto é, transições permitidas a qualquer um — que a E4.7 teria de
   retrofitar. Retrofitting de controle de acesso é o padrão que mais
   confiavelmente produz vazamento.

**Emenda proposta (A): trocar E4.3 e E4.7 de posição.**

```
E4.3   Governance Policy          (era E4.7)
E4.7   Accessibility Policy       (era E4.3)
```

Governança define autoridade; acessibilidade a consome. A ordem
natural é autoridade primeiro.

**Emenda alternativa (B): manter a numeração, dividir o escopo
explicitamente.**

- **E4.3** entrega apenas a **matriz estrutural de transição** — quais
  transições de `AccessibilityState` são semanticamente válidas,
  independentemente de quem as executa. Isso é decidível sem
  governança: por exemplo, se `CAUSALLY_EXTINCT` é terminal, se
  `LATENT → ACTIVE` é livre, e assim por diante.
- **E4.7** acrescenta a camada de **autoridade** — quem pode executar
  cada transição válida.

A opção B é viável e preserva o Plano Mestre, **desde que a divisão
seja congelada agora**, por escrito, e não deixada para a E4.3
descobrir sozinha. Sem isso, a E4.3 escorrega para dentro do escopo da
E4.7 por necessidade prática.

**Recomendação: opção A.** É mais simples, e a razão é que a divisão
da opção B é mais frágil do que parece — várias perguntas de transição
("`INACCESSIBLE → ACTIVE` é válida?") só têm resposta boa quando se
sabe *quem* pergunta.

---

## 3. Achado 2 — `E4.6 Memory Retrieval` precede `E4.7 Governance Policy`

Recuperação de memória é, pela definição congelada, a aplicação de
`Admissible_Context` ao patrimônio. Se governança restringe acesso e
governança ainda não existe quando o retrieval é construído, o
retrieval nasce **sem o ponto de composição** para a decisão de
governança e terá de ser modificado depois.

Este é o mesmo defeito do Achado 1, uma camada acima.

**Emenda proposta:** com a opção A do Achado 1, o problema se resolve
sozinho — Governance passa a ser E4.3 e antecede E4.6 naturalmente.
Com a opção B, a E4.6 deve ser explicitamente construída sobre uma
**interface de admissibilidade** cuja implementação de governança
chega em E4.7 — o que é possível, mas exige que a interface seja
congelada em E4.3.

---

## 4. Sequência recomendada

Aplicando a emenda A:

```
E4.0   Architecture & Contract Freeze          ← esta entrega
E4.1   Memory Domain Foundation
E4.2   Context Manager
E4.3   Governance Policy                        ← movido de E4.7
E4.4   Persistence Manager
E4.5   Consolidation Manager
E4.6   Memory Retrieval
E4.7   Accessibility Policy                     ← movido de E4.3
E4.8   Memory Isolation
E4.9   Retention / Forgetting
E4.10  Compliance Boundary
E4.11  Validated Experience Registry
E4.12  Final Integration Gate
```

Nenhum outro módulo muda de posição. A auditoria não encontrou
problema de ordenação em nenhum dos demais.

**Decisão pendente do titular do Plano Mestre:** opção A (troca),
opção B (divisão de escopo congelada), ou manutenção da ordem original
com justificativa que a auditoria não enxergou.

---

## 5. Matriz G — dependências entre módulos da E4

Dependências **duras** (o módulo não fecha sem elas) marcadas com `X`;
**de composição** (usa, mas não bloqueia) com `o`.

| ↓ depende de → | E3 | 4.0 | 4.1 | 4.2 | 4.3ᵍ | 4.4 | 4.5 | 4.6 | 4.7ᵃ | 4.8 | 4.9 | 4.10 | 4.11 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| **E4.1** Memory Domain | X | X | — | | | | | | | | | | |
| **E4.2** Context | X | X | o | — | | | | | | | | | |
| **E4.3** Governance ᵍ | X | X | X | X | — | | | | | | | | |
| **E4.4** Persistence | X | X | o | o | | — | | | | | | | |
| **E4.5** Consolidation | X | X | | | | X | — | | | | | | |
| **E4.6** Retrieval | X | X | X | X | X | | | — | | | | | |
| **E4.7** Accessibility ᵃ | X | X | | X | X | | | | — | | | | |
| **E4.8** Isolation | X | X | X | X | X | | | X | X | — | | | |
| **E4.9** Retention | X | X | o | | X | X | o | | X | | — | | |
| **E4.10** Compliance | X | X | o | o | X | | | | X | o | X | — | |
| **E4.11** Validated Exp. | X | X | | o | | | | | | | | | — |
| **E4.12** Gate | X | X | X | X | X | X | X | X | X | X | X | X | X |

ᵍ Governance na posição recomendada (emenda A).
ᵃ Accessibility Policy na posição recomendada (emenda A).

### 5.1 Leitura do grafo

```
                         E3 (FROZEN)
                              │
                            E4.0
                              │
                 ┌────────────┼────────────┐
               E4.1         E4.2         E4.4
                 │            │            │
                 └─────┬──────┘          E4.5
                       │
                     E4.3  (Governance — autoridade)
                       │
          ┌────────────┼────────────┬──────────┐
        E4.6         E4.7         E4.9       E4.10
          │            │
          └─────┬──────┘
              E4.8
                │
              E4.12  ← consome todos

        E4.11 ── ramo independente (só E3 + E4.0 + contexto)
```

**Observações da auditoria:**

- **E4.3 (Governance) é o gargalo real** da entrega. Cinco módulos
  dependem dela de forma dura. Isso reforça a emenda A: um gargalo
  posicionado tarde na sequência é um gargalo que bloqueia trabalho já
  feito.
- **E4.11 é independente** e pode ser executado em paralelo a qualquer
  momento após E4.0. É o único ramo desacoplado.
- **E4.4 → E4.5** é a única dependência dura fora do tronco principal:
  consolidação é uma operação de persistência, não o contrário.
- **E4.12** depende de todos, como o gate final da E3 dependia — e
  deve seguir o mesmo desenho: testes de integração e documentos, sem
  feature nova, com auditoria independente antes do freeze.

---

## 6. Gate E4 → E5 (Q20)

Proposto por simetria com o gate E3 → E4, que funcionou:

```
E4.12_IMPLEMENTATION_GATE = PASS   ← o executor pode declarar
E4_FINAL_FREEZE           = PENDING_INDEPENDENT_AUDIT
GATE_E4_TO_E5             = PENDING
READY_FOR_E5              = FALSE  ← até auditoria independente
```

Condições substantivas propostas para o gate E4 → E5:

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

A condição 5 é a mais importante e a mais fácil de verificar: o tree
hash da E3 (`83217c40…` para os caminhos de `app/cognitive/` e
`alembic/`) deve permanecer verificável ao fim da E4.
