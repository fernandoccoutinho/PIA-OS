# E5.0 — Nomenclatura e Colisões

Retorno ao índice: [E5.0 — Architectural Documentary Freeze](E5_0_ARCHITECTURE_FREEZE.md)

```text
D2 = FROZEN
C4 = ACCEPTED_PREDICTIVE_CLAIM_SPECIFIC_NAME
E3_E4_RETROACTIVE_RENAME = FORBIDDEN
```

---

## 1. Estado medido da baseline

Medição executada sobre a cadeia 97, `HEAD 340443aa…`, nas 201 fontes de
produção, por três métodos: nome de módulo, nome de definição (`FunctionDef`,
`AsyncFunctionDef`, `ClassDef`) e ocorrência textual incluindo docstring e
comentário.

```text
PIAP_IMPLEMENTATION_IN_CHAIN97 = ABSENT
PIAP_CONTRACT_IN_CHAIN97       = ABSENT
PIAP_MENTION_IN_CHAIN97        = ONE_NARRATIVE_LINE_IN_README
PREDICTIVE_ACCESSIBILITY_IMPLEMENTATION = ABSENT
PREDICTIVE_SYMBOL_IN_PRODUCTION_CODE    = ZERO
DOCUMENT_MENTION != IMPLEMENTATION
```

Léxico dos contratos v2.6 a v2.8 na baseline, medido:

```text
Burden          0 ocorrências em produção
Protective      0
Inaction        0
Counterfactual  0
Assertive       0
Claim           0
Conflict        3 definições — ver C4
```

---

## 2. As quatro colisões

### C1 — `COUT-P<n>` histórico × família COUT-P Predictive Accessibility

A baseline usa `COUT-P1` a `COUT-P10` para os dez princípios de continuidade
COUT-PIA da E3 e da E4: 76 ocorrências em 17 arquivos, das quais 12 em produção,
todas em docstring. `COUT-P9` é o princípio "COUT informa; não decide", não um
score preditivo.

### C2 — `COUT-PIA` × `COUT-P`

Segundo token de prefixo idêntico, em 7 arquivos, incluindo `EDR_COUT_PIA_E3.md`
e `EDR_COUT_PIA_E4.md`. Busca ingênua por `COUT-P` casa com `COUT-PIA`.

### C3 — `AccessibilityState.INACCESSIBLE` × `INACCESSIBLE` epistêmico

O primeiro é estado persistido de acessibilidade de memória, com máquina de
transição própria (E4.7) e operação de governança própria
(`accessibility_transition`). O segundo, no handoff original, é estado
epistêmico preditivo. É a mais perigosa das quatro, porque as duas são
plausivelmente "acessibilidade".

```text
E5_PREDICTIVELY_INACCESSIBLE != E4_ACCESSIBILITY_STATE
NOT_PREDICTIVELY_ADMISSIBLE != INACCESSIBLE_MEMORY
```

### C4 — `Conflict` existente × `PREDICTION_CONFLICT`

A baseline já usa `Conflict` com três significados, e nenhum deles é conflito
entre alegações preditivas:

```text
SyncConflict (E3)                     colisão de IDENTIDADE: mesmo identificador
                                      persistente, estado estrutural diferente
ValidatedExperienceConflictError       mesmo experience_id, conteúdo canônico
(E4.11)                                divergente; protege ZERO_OVERWRITE
ConflictException (PIA-1004)           HTTP 409
```

Os três são conflitos de identidade sobre o mesmo objeto. `PREDICTION_CONFLICT`
é uma relação entre alegações sobre um alvo futuro. Se a E5 nomear seu tipo de
conflito simplesmente `Conflict`, a leitura do código passa a exigir contexto
para saber de qual conflito se fala, e a guarda de nomenclatura não consegue
distinguir os dois casos.

---

## 3. Registro de nomenclatura — D2 e C4 congeladas

```text
1. E3/E4 e COUT-P1..P10 NÃO serão renomeados.
   E3_E4_RETROACTIVE_RENAME = FORBIDDEN

2. COUT-P v1.3 permanece nome DOCUMENTAL da família científica.
   COUT_P_v1_3 = DOCUMENTARY_SCIENTIFIC_FAMILY_NAME

3. Símbolos novos de runtime usam namespace `predictive_accessibility` e nomes
   com prefixo `Predictive`.
   NEW_RUNTIME_PREFIX_COUT_P_OR_COUTP = FORBIDDEN

4. O estado é `PREDICTIVELY_INACCESSIBLE`. `INACCESSIBLE` isolado continua
   reservado à acessibilidade de memória da E3 e da E4.

5. Guardas estáticas de nomenclatura e de fronteira têm mutantes próprios.
   STATIC_NAMING_AND_BOUNDARY_GUARDS_REQUIRE_MUTANTS = TRUE

6. O tipo conceitual de conflito preditivo usa nome específico, como
   `PredictiveClaimConflict`, conservando obrigatoriamente `Predictive` e
   `Claim`. `Conflict` isolado fica PROIBIDO dentro do namespace
   `predictive_accessibility`.
   UNQUALIFIED_CONFLICT_IN_PREDICTIVE_NAMESPACE = FORBIDDEN
   RUNTIME_NAME_REQUIRES_PREDICTIVE_AND_CLAIM = TRUE
```

O nome exato de runtime só nasce no preflight da etapa correspondente. Este
documento congela a regra, não o identificador.

---

## 4. Lacuna de instrumento L1 — o alcance real da guarda M14 da E4.12

`test_m14_nenhum_cout_p_ou_predictive_accessibility_implementado`, em
`backend/tests/static/test_e4_12_final_gate_isolation.py`, varre as fontes de
produção e reprova se o nome de uma `FunctionDef`, `AsyncFunctionDef` ou
`ClassDef` contiver `COUTP`, `CoutP`, `PredictiveAccessibility` ou
`predictive_accessibility`.

O que ela não mede: nome de módulo; nome de variável, constante, atributo ou
parâmetro; string literal; chave de dicionário; nome de tabela ou coluna em
migration; e as grafias `COUT_P`, `COUT-P` e `cout_p`, ausentes da lista de
proibidos.

```text
M14_MEASURES = DEFINITION_NAMES_ONLY
DEFINITION_NAME_GUARD != ABSENCE_OF_CAPABILITY
```

A conclusão de ausência permanece correta — a medição independente descrita na
seção 1 é estritamente mais ampla e deu zero em produção. O que se registra aqui
é que a prova que a sustenta não é a M14.

A E4 está congelada e não será corrigida por isso. A guarda equivalente da E5
nasce correta, com o alcance ampliado e com mutante próprio.

---

## 5. Guardas de nomenclatura exigidas da E5

```text
GUARDA_SEM_MUTANTE = GUARDA_NAO_VERIFICADA

Escopo mínimo da guarda de nomenclatura da E5:
  nome de módulo
  nome de classe, função e método
  nome de variável, constante e atributo
  nome de tabela e coluna em migration
  grafias COUT_P, COUTP, CoutP, cout_p, COUT-P
  INACCESSIBLE sem qualificação dentro do namespace predictive_accessibility
  Conflict sem qualificação dentro do namespace predictive_accessibility
```

A guarda pertence à etapa `E5.b`, que precede qualquer módulo científico —
ver [Decomposição](E5_0_DECOMPOSITION_AND_DEPENDENCY_GRAPH.md) §4.

---

## 6. Stop Conditions desta área

```text
SC-E5.0-A  símbolo de runtime da E5 nomeado com prefixo COUT_P ou COUTP,
           reintroduzindo as colisões C1 e C2.
SC-E5.0-B  uso de INACCESSIBLE sem qualificação para o estado epistêmico,
           colidindo com AccessibilityState.INACCESSIBLE da E3 (colisão C3).
SC-E5.0-C  tipo de conflito preditivo da E5 nomeado apenas Conflict,
           colidindo com SyncConflict, ValidatedExperienceConflictError e
           ConflictException (colisão C4).
SC-E5.0-D  guarda de fronteira ou de nomenclatura entregue SEM mutante próprio.
SC-E5.0-E  guarda de ausência que meça apenas NOME DE DEFINIÇÃO e seja
           reportada como prova de ausência de capacidade (lacuna L1).
```

Lista cumulativa completa em
[Decomposição](E5_0_DECOMPOSITION_AND_DEPENDENCY_GRAPH.md) §8.
