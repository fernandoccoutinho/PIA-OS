# E4 → E5 — Handoff

Estado congelável da Entrega 4 e o que a Entrega 5 pode consumir sem
modificar.

```text
READY_FOR_E5 = FALSE
```

Este documento **não** libera a E5. Ele descreve o que existe, o que não
existe, e o que precisa acontecer antes.

---

## 1. Identidade do estado entregue

```text
CHAIN            97
PARENT           5eeab210627ae631bc2e58237fc5268dc663a93d
MIGRATION_HEAD   e7c25a91f4b3
PRODUCTION_DELTA NONE (na E4.12)
MIGRATION_DELTA  NONE (na E4.12)
```

Gates da cadeia 97 medidos em clone limpo do bundle, com PostgreSQL
comprovadamente pronto antes da coleta. Os números literais estão no
relatório de gates do pacote.

## 2. O que a E5 pode consumir sem modificar

Contratos estáveis, com fronteira declarada e teste próprio:

```text
MemoryContext                     E4.2
GovernanceResolution / resolve    E4.3
AccessibilityTransitionResult     E4.7
MemoryRetrievalResult             E4.6
RetentionAssessment               E4.9.9.c
DestructiveApprovalEnvelope       E4.9.8
ErasureEffectPort                 E4.9.9.b   CONTRACT_ONLY
ErasureTargetResolverPort         E4.9.7     CONTRACT_ONLY
ComplianceReport                  E4.10
ValidatedExperienceAppend         E4.11
```

Consumir significa **chamar e ler**. Alterar qualquer um deles exige
autorização própria e reabre a fatia de origem.

## 3. Candidato da E5

```text
COUT_P_V1_2           = PREDICTIVE_ACCESSIBILITY
STATUS                = DEFERRED
FUTURE_STOP_CONDITION = NO
```

```text
DEFERRED_CANDIDATE != FUTURE_STOP_CONDITION
```

`FUTURE_STOP_CONDITION` é reservado ao que **poderia bloquear** uma
entrega se fosse exigido. Nada na E4 depende de COUT-P, e nada na E5 o
exige antes de a própria E5 decidir o seu escopo — classificá-lo assim
inflaria a lista de bloqueios potenciais com um item que não é um.

`COUT-P v1.2 / Predictive Accessibility` é candidato **exclusivo** da
E5. Nada dele foi implementado na E4, e uma guarda estática
(`test_m14`) mede que nenhum símbolo com esse nome nasceu em produção.

A distinção que a E5 herda e não pode apagar:

```text
PREDICTED_ACCESSIBILITY != ACTUAL_ACCESSIBILITY
PREDICTION              != AUTHORITY
```

## 4. O que **não** foi implementado

```text
E5                              NOT_STARTED
LEARNING_ENGINE                 FORBIDDEN e ausente
TRANSPORTE DE VALIDATED_EXPERIENCE   DEFERRED
ADAPTADORES MATERIAIS           CONTRACT_ONLY
AUTENTICADOR                    NOT_APPLICABLE
API REMOTA / WORKER / SCHEDULER / FILA   ausentes
UNIFICAÇÃO DAS RAÍZES DOCUMENTAIS    não realizada
```

Nenhum destes é **pré-condição universal** para abrir a E5. O transporte
de `ValidatedExperience` e a unificação documental só exigem decisão se
o escopo da E5 vier a depender deles — e é a E5, no seu preflight, que
declara o escopo.

```text
DEFERRED_ITEM != UNIVERSAL_PRECONDITION
```

Nenhuma linha de E5 foi escrita. Nenhum item adiado foi promovido a
implementação por conveniência do gate.

## 5. O que a E5 precisa fazer antes de começar

1. novo preflight integral sobre o pacote da cadeia 97;
2. autorização expressa, com escopo e delta declarados;
3. caracterização bilateral própria, medida **antes** de qualquer
   produção;
4. decisão sobre o transporte de `ValidatedExperience` **se** o escopo
   declarado depender dele — hoje isso exigiria alterar
   `SECTION_BY_TABLE` na E3 congelada;
5. decisão sobre a unificação das duas raízes documentais **se** o
   escopo declarado depender dela.

## 6. Condição de liberação

```text
E4_FINAL_FREEZE = PENDING_INDEPENDENT_AUDIT
GATE_E4_TO_E5   = PENDING
READY_FOR_E5    = FALSE
PASS_FINAL      = NOT_DECLARED
```

`READY_FOR_E5` permanece `FALSE` até que a auditoria independente
declare `PASS_FINAL` da E4.12. Essa declaração não pertence a quem
implementa.
