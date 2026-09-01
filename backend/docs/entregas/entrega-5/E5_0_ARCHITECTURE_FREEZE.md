# E5.0 — Architectural Documentary Freeze

**Entrega 5 — Predictive Accessibility Layer (PIAP + COUT-P v1.3)**
**Estado:** `FREEZE_CANDIDATE_PENDING_INDEPENDENT_AUDIT`

Este documento é o índice do freeze arquitetural da E5.0 e o ponto de entrada
para os sete documentos complementares.

```text
E5_0_PLAN = PASS_FINAL
E5_0_FREEZE_DOCUMENTS = FREEZE_CANDIDATE_PENDING_INDEPENDENT_AUDIT
E5_RUNTIME_IMPLEMENTED = NO
E5_IMPLEMENTATION = NOT_STARTED
```

---

## 1. Autoridade

| Artefato | Identidade |
|---|---|
| Plano aprovado | `PRE_IMPLEMENTATION_PLAN_E5_0_CORRECTIVE_v2.8.2.md` |
| SHA256 do plano | `8c52f1209cc221a24ce964b6bd0f009ded2872e33dee0e0cc4f6aabcc08669f4` |
| Linhas / bytes | 2938 / 141524 · UTF-8 estrito |
| Auditoria | `PASS_FINAL_AUDITORIA_INDEPENDENTE_E5_0_PLAN_v2.8.2.md` |
| SHA256 da auditoria | `73f81bb395d3255542d8a37f73b25f2343ce903f12e7b78ed0083ee18bdb94a2` |
| Veredito | `PASS_FINAL` — 30/30 saídas, 0 blocker, 0 major |
| Kit normativo | `PIA_OS_KIT_E5_CONTROLADO_CHAIN97_MASTER_v2.8` — 48/48 checksums |
| Master | `PIA_OS_SOPHIA_MASTER_INTEGRADO_v2.8.md` — `389f4481…` |
| Baseline pai | `HEAD 340443aa…` · `TREE f45013d9…` · migration head `e7c25a91f4b3` |

```text
APPROVED_PLAN = SINGLE_NORMATIVE_SOURCE_FOR_THIS_FREEZE
SCIENTIFIC_CONTRACT_REOPENED = NO
NEW_THRESHOLD_AUTHORITY_PROVIDER_OR_ROUTE = FORBIDDEN
IMPLEMENTER_REPORT != INDEPENDENT_AUDIT
```

Os oito documentos deste diretório são uma decomposição documental do plano
aprovado. Não o reinterpretam, não reabrem contrato científico e não criam
capacidade.

---

## 2. Índice

| Documento | Conteúdo |
|---|---|
| [Nomenclatura e colisões](E5_0_NAMING_AND_COLLISIONS.md) | C1–C4, D2 e C4 congeladas, namespace e prefixos, guardas com mutantes |
| [Contrato científico](E5_0_SCIENTIFIC_CONTRACT.md) | símbolos, Power Gate, três estados, plano estatístico, regime, horizonte, reconfiguração, `L_total` |
| [Conflito e assertividade](E5_0_CONFLICT_AND_ASSERTIVENESS.md) | contrato v2.6, conflito como relação entre alegações, assertividade operacional, kill tests 14–23 |
| [Completude e proteção](E5_0_COMPLETENESS_AND_PROTECTION.md) | contrato v2.7, `MATERIALITY_STATUS`, proveniência emergencial, kill tests 24–33 |
| [Custo total e contrafactual](E5_0_TOTAL_BURDEN_AND_COUNTERFACTUAL.md) | contrato v2.8, A0/A1/A2, vetor plural, fronteira com `L_total`, kill tests 34–45 |
| [Decomposição e grafo de dependências](E5_0_DECOMPOSITION_AND_DEPENDENCY_GRAPH.md) | E5.a–E5.t, grafo causal, matriz G0–G18, distribuição dos 45 casos, mutantes |
| [EDR E5.0](EDR_E5_0.md) | decisões, colisões, lacunas, histórico de achados, riscos |

---

## 3. Mapa PIAP × COUT-P, sem fonte duplicada

```text
PIAP   = camada PROTOCOLAR. transporta, versiona, atribui. não conhece ciência.
COUT-P = família CIENTÍFICA. mede acessibilidade preditiva. não conhece transporte.
```

```text
PIAP = VERSIONED_PROVENANCE_PRESERVING_PROTOCOL_ENVELOPE
PIAP_TRANSPORTS_CONTEXT_CLAIMS_EVIDENCE_AND_CONTRACT_METADATA = TRUE
PIAP_INTERPRETS_PREDICTIVE_SCIENCE = FALSE
PIAP_DECIDES_EPISTEMIC_STATE_OR_ROUTE = FALSE
PIAP_WRITES_E4_STATE = FALSE
PIAP_EXECUTES_OR_SELECTS_PROVIDER = FALSE
PIAP_ENVELOPE != AI_HANDOFF_ENVELOPE
```

O envelope preserva, conceitualmente e sem materializar tipo de runtime:
identidade e referência da fonte, versão, hash quando aplicável, proveniência,
alvo, sinal, horizonte, instante de referência, disponibilidade temporal,
jurisdição e política quando aplicáveis, e estado de autoridade e permissão.

Os metadados de autoridade, explicitados por D1 e D4:

```text
approval_reference
approval_status
approval_version
approval_scope
approval_expiry
jurisdiction
reference_or_binding_to_the_proposed_bound_or_promotion
```

```text
PIAP_TRANSPORTS_APPROVAL_REFERENCE_AND_BINDING = TRUE
PIAP_DUPLICATES_THE_APPROVED_OBJECT = FALSE
E5_VALIDATES_BUT_DOES_NOT_GRANT_APPROVAL = TRUE
MISSING_EXPIRED_MISMATCHED_OR_OUT_OF_SCOPE_APPROVAL = TYPED_VALIDATION_OUTCOME
```

### 3.1 Fonte única de verdade, por objeto

```text
identidade e proveniência do dado           -> E4, via PIAP, somente leitura
versão de contrato e compatibilidade        -> PIAP
autoridade e permissão carimbadas           -> PIAP (transporta; não concede)
validade histórica e regime                 -> COUT-P (V_t, K_history, D_regime)
acessibilidade preditiva                    -> COUT-P (A-, A*, K_pred, H_pred)
estado epistêmico por alegação              -> COUT-P
relação de conflito entre alegações         -> E5.m
completude, materialidade e ramos protetivos-> E5.o
validade da orientação emergencial          -> E5.p
contrafactual e vetor de ônus               -> E5.q e E5.r
rota de resposta                            -> E5.s
execução                                    -> FORA DA E5 (E6, E7, E8)
prova experimental independente             -> E9

PIAP_DOES_NOT_STORE_SCIENTIFIC_STATE = TRUE
COUT_P_DOES_NOT_STORE_TRANSPORT_STATE = TRUE
NO_OBJECT_IS_WRITTEN_BY_BOTH_LAYERS = TRUE
```

---

## 4. Cadeia completa de avaliação e recomendação

```text
E4 (read-only, governado)
   |  PIAP envelope in (proveniência, versão, autoridade, jurisdição, tempo)
   v
[1]  CLAIM DECOMPOSITION      alvo, sinal, horizonte, instante, regime,
                              proveniência, pressupostos, restrições
   v
[2]  AVAILABILITY GATE        avail(Z_j,t,Delta) em {0,1}, antes de tudo
   v
[3]  HISTORICAL VALIDITY      R(k->t) -> V_t , K_history
   v
[4]  REGIME ASSESSMENT        D_regime vs theta -> REGIME_SHIFT_CANDIDATE?
   v
[5]  PREDICTIVE ACCESSIBILITY A-, null/placebo, multiplicidade
   v
[6]  POWER GATE               A*_worst vs A_rel
   v
[7]  HORIZON SPECTRUM         H_pred(R_t), Delta_cont, R_pred
   v
[8]  EPISTEMIC STATE AND      classifica o estado por alegação e MONTA
     CLAIM EVALUATION         o objeto imutável de sete componentes
     ASSEMBLY                 -> CLAIM_EVALUATION_RESULT
   v
[9]  CLAIM CONFLICT           comensurabilidade; conflito real x falso;
                              restrição decisiva. sem média, voto ou escolha
   v
[10] PRIMARY CONCLUSION       conclusão principal candidata e assertividade
     CANDIDATE                por alegação
   v
[11] PROTECTIVE CANDIDATES    frentes materiais de redução de danos;
     AND MATERIALITY          MATERIALITY_STATUS por ramo; aceitos, rejeitados
                              e não resolvidos, com razão e proveniência
   v
[12] GUIDANCE PROVENANCE      valid | missing | stale | invalid |
     VALIDATION               jurisdiction/version mismatch
   |
   |  PORTÃO CAUSAL: nenhum ramo com orientação material passa daqui sem
   |  resultado explícito de [12].
   v
[13] COUNTERFACTUAL AND       A0 inação, A1 escalonada reversível, A2 plena,
     COMPLETE ASSEMBLY        montadas sobre [10], [11] e [12]
   v
[14] TOTAL BURDEN VECTOR      seis dimensões, incidência, dominância, trade-offs
   v
[15] FINAL RECOMMENDATION     rota por alegação e rota composta, recomendadas;
     AND ROUTING              assertividade REVALIDADA sobre [10] a [14];
                              ROBUST somente com limites autorizados ou
                              validados contra os metadados de aprovação
   |  PIAP envelope out (conclusão, restrição decisiva, autoridade, gatilho)
   v
consumidor humano ou E6/E7/E8 — a E5 PARA AQUI
```

Detalhamento das arestas e dos dois portões causais em
[Decomposição e grafo de dependências](E5_0_DECOMPOSITION_AND_DEPENDENCY_GRAPH.md).

---

## 5. Estado, rota e execução

```text
EPISTEMIC_STATE   descreve o que a evidência permite afirmar sobre UMA alegação
RESPONSE_ROUTE    descreve o tratamento governado apropriado
EXECUTION         descreve o que acontece no mundo — FORA DA E5

EPISTEMIC_STATE != RESPONSE_ROUTE != EXECUTION

PREDICTION_CONFLICT = RELATION_BETWEEN_CLAIMS
PREDICTION_CONFLICT != EPISTEMIC_STATE
PREDICTION_CONFLICT != RESPONSE_ROUTE
PREDICTION_CONFLICT != MODEL_VOTE
PREDICTION_CONFLICT != PROVIDER_ARBITRATION
```

Conflito é uma quarta coisa e não entra em nenhuma das três dimensões. Daí
existir um componente próprio em vez de um campo `conflict` no objeto de estado.

A separação é estrutural, não documental:

```text
o objeto de estado epistêmico NÃO tem campo de rota;
o objeto de rota NÃO tem campo de execução;
o objeto de conflito NÃO tem campo de estado nem de rota — referencia alegações;
a função que mapeia estado para rota é PURA e SEPARADA dos value objects;
não existe construtor público que produza combinação incoerente.
```

### 5.1 As quatro rotas — e a abstenção, que não é uma delas

```text
RESPONSE_ROUTE = PREDICT | RECONFIGURE | INVESTIGATE | ROBUST
```

```text
PREDICT       alegação PREDICTABLE e modelo vigente admissível
RECONFIGURE   CANDIDATA. exige degradação medida
                        + D_regime > theta testado contra flutuação
                        + alternativa com A- > 0 em validação prospectiva/cega
INVESTIGATE   alegação UNRESOLVED, ou regime novo ainda não identificado
              propõe Z* = argmax Delta_A_pred(Z)/cost(Z) — PROPOSTA, não acesso
ROBUST        alegação PREDICTIVELY_INACCESSIBLE, ou questão composta com
              limites LEGÍTIMOS, REVERSÍVEIS e AUDITÁVEIS
```

A abstenção é o comportamento governado da ausência de rota segura. A função de
roteamento é **parcial**: devolve uma rota do conjunto de quatro, ou devolve a
ausência de rota, e a ausência obriga a explicação de limites.

```text
route(claim_state, evidence, bounds) -> RESPONSE_ROUTE  ou  NO_SAFE_ROUTE
NO_SAFE_ROUTE não é membro de RESPONSE_ROUTE
NO_SAFE_ROUTE obriga EXPLAIN_LIMITS
ABSTENTION_IS_A_BEHAVIOUR_NOT_A_ROUTE = TRUE
ABSTAIN_AS_FIFTH_ROUTE = FORBIDDEN
```

Se `ABSTAIN` fosse membro do conjunto, um roteador poderia escolher abster-se
como quem escolhe entre alternativas, e a abstenção competiria com `ROBUST` na
mesma prateleira. Ela não compete: é o que sobra quando nenhuma das quatro tem
base.

```text
RECONFIGURE != QUARTO_ESTADO_EPISTEMICO
RECONFIGURE != MUDANCA_DE_MODELO
ROUTE_RECOMMENDATION != EXECUTION
PREDICT != AUTORIDADE_DECISORIA_DO_USUARIO
ROBUST_ROUTE_WITHOUT_AUTHORIZED_OR_VALIDATED_BOUNDS = FORBIDDEN
```

O mapeamento default (`PREDICTABLE -> PREDICT`, `UNRESOLVED -> INVESTIGATE`,
`PREDICTIVELY_INACCESSIBLE -> ROBUST` quando legítimo) é default, não bijeção.

---

## 6. Fronteiras

### 6.1 E4 read-only

```text
E5_CONSUMES_E4_ACCESSIBLE_CONTEXT_READ_ONLY = TRUE
E5_AUTONOMOUS_MEMORY_ACCESS = FORBIDDEN
E5_MEMORY_WRITER = FORBIDDEN
E5_RETENTION_OR_ERASURE_AUTHORITY = NONE
PREDICTIVE_FILTERING_DOES_NOT_WRITE_E4_STATE = TRUE
PREDICTIVE_EXCLUSION != RETENTION_FORGETTING
K_HISTORY_MEMBERSHIP != DELETION
NOT_PREDICTIVELY_ADMISSIBLE != INACCESSIBLE_MEMORY
E5_PREDICTIVELY_INACCESSIBLE != E4_ACCESSIBILITY_STATE
```

`K_history` é conjunto calculado e transiente sobre o contexto lido. Não é
estado persistido no patrimônio, não é marcação em objeto da E3 e não é entrada
para retenção. Um objeto pode estar em `K_history` e continuar `ACTIVE` na E4
indefinidamente. Se `K_history` virar coluna, a E5 virou escritor de memória, e
isso é Stop Condition.

A leitura da E5 ocorre sob `CognitiveOperation.READ` (D6). Nenhum décimo segundo
membro do enum é criado.

### 6.2 Owners E6 a E9

```text
E6_OWNS_PROGRAMMATIC_ACCESS_AND_SDK = TRUE
E7_OWNS_PROVIDER_AGENT_SELECTION_AND_MULTI_AI_ARBITRATION = TRUE
E8_OWNS_INTERACTION_UX_AND_SECURITY = TRUE
E9_OWNS_INDEPENDENT_BENCHMARKS_AND_EXPERIMENTAL_PROOF = TRUE
```

O fixture `El Niño e SIN em 2027` é caso de teste de arquitetura, não evidência
sobre o setor elétrico brasileiro. Usá-lo para afirmar qualquer coisa sobre o
mundo, e não sobre o comportamento da E5, seria benchmark usado para construir a
hipótese declarado prova independente.

---

## 7. Escopo negativo global

```text
E5_CONSUMES_E4_ACCESSIBLE_CONTEXT_READ_ONLY = TRUE
E5_AUTONOMOUS_MEMORY_ACCESS = FORBIDDEN
E5_MEMORY_WRITER = FORBIDDEN
E5_RETENTION_OR_ERASURE_AUTHORITY = NONE

E5_RESPONSE_ROUTER_SELECTS_PROVIDER_OR_AGENT = FALSE
E5_RESPONSE_ROUTER_EXECUTES_WORLD_ACTION = FALSE
E5_EXTERNAL_EFFECT_AUTHORITY = NONE
E5_ALERTS_EVACUATES_SHELTERS_OR_DEPLOYS_RESPONDERS = FALSE
RECOMMENDATION_COMPARISON != EXECUTION

E5_CREATES_SDK_OR_PUBLIC_API = FALSE               (E6)
E5_ARBITRATES_MULTI_AI = FALSE                     (E7)
E5_DEFINES_APPROVAL_UX_OR_SECURITY = FALSE         (E8)
E5_DECLARES_INDEPENDENT_EXPERIMENTAL_PROOF = FALSE (E9)
E5_ACQUIRES_DATA = FALSE                           (só PROPÕE Z*)
```

---

## 8. Matriz de rastreabilidade das 30 saídas do plano

| # | Saída obrigatória | Congelada em |
|---:|---|---|
| 1 | identidade medida da baseline e método | [EDR](EDR_E5_0.md) §1 |
| 2 | checksums, segurança dos ZIPs, worktree e `git fsck` | [EDR](EDR_E5_0.md) §1 |
| 3 | inventário de módulos, contratos e dependências | [EDR](EDR_E5_0.md) §2 |
| 4 | inventário real de PIAP | [EDR](EDR_E5_0.md) §2 |
| 5 | símbolos preditivos e colisões nominais | [Nomenclatura](E5_0_NAMING_AND_COLLISIONS.md) §1–§2 |
| 6 | mapa PIAP × COUT-P sem duplicação | este documento §3 |
| 7 | estado, rota e execução separados | este documento §5 |
| 8 | conflitos por alegação, comensurabilidade, sem média/voto | [Conflito](E5_0_CONFLICT_AND_ASSERTIVENESS.md) §1–§3 |
| 9 | assertividade, restrição decisiva, autoridade, gatilho | [Conflito](E5_0_CONFLICT_AND_ASSERTIVENESS.md) §5–§6 |
| 10 | completude e ramos materiais de proteção | [Completude](E5_0_COMPLETENESS_AND_PROTECTION.md) §1–§3 |
| 11 | proveniência emergencial: fonte, versão, jurisdição, tempo | [Completude](E5_0_COMPLETENESS_AND_PROTECTION.md) §4 |
| 12 | recomendação multidimensional sem ação externa | [Completude](E5_0_COMPLETENESS_AND_PROTECTION.md) §5–§6 |
| 13 | contrafactual ação, ação escalonada, inação | [Custo total](E5_0_TOTAL_BURDEN_AND_COUNTERFACTUAL.md) §1–§2 |
| 14 | vetor plural de ônus, incidência, agregação proibida | [Custo total](E5_0_TOTAL_BURDEN_AND_COUNTERFACTUAL.md) §3–§4 |
| 15 | Power Gate, abstenção e resposta útil | [Científico](E5_0_SCIENTIFIC_CONTRACT.md) §3; este documento §5.1 |
| 16 | regime, transportabilidade, temporalidade, leakage | [Científico](E5_0_SCIENTIFIC_CONTRACT.md) §5 |
| 17 | plano estatístico | [Científico](E5_0_SCIENTIFIC_CONTRACT.md) §4 |
| 18 | reconfiguração controlada | [Científico](E5_0_SCIENTIFIC_CONTRACT.md) §6 |
| 19 | espectro de horizontes | [Científico](E5_0_SCIENTIFIC_CONTRACT.md) §7 |
| 20 | aquisição como proposta sem execução | [Científico](E5_0_SCIENTIFIC_CONTRACT.md) §8 |
| 21 | E4 read-only e owners E6 a E9 | este documento §6 |
| 22 | proveniência, auditabilidade, custo e `L_total` distinto do vetor | [Custo total](E5_0_TOTAL_BURDEN_AND_COUNTERFACTUAL.md) §5 |
| 23 | decomposição E5.a–E5.t | [Decomposição](E5_0_DECOMPOSITION_AND_DEPENDENCY_GRAPH.md) §1–§3 |
| 24 | caracterização bilateral anterior ao código | [Decomposição](E5_0_DECOMPOSITION_AND_DEPENDENCY_GRAPH.md) §5 |
| 25 | matriz de testes e kill tests por etapa | [Decomposição](E5_0_DECOMPOSITION_AND_DEPENDENCY_GRAPH.md) §6–§7 |
| 26 | três checklists cumulativos | [EDR](EDR_E5_0.md) §7 |
| 27 | Stop Conditions cumulativas | [Decomposição](E5_0_DECOMPOSITION_AND_DEPENDENCY_GRAPH.md) §8 |
| 28 | delta documental do freeze | este documento §9 |
| 29 | riscos, lacunas, decisões e viabilidade | [EDR](EDR_E5_0.md) §3–§6 |
| 30 | nenhuma alteração no repositório pelo preflight | [EDR](EDR_E5_0.md) §8 |

```text
NORMATIVE_CONTENT_LOST = NONE
```

---

## 9. O que este freeze é e o que não é

```text
E5_0_FREEZE_DOCUMENTS = FREEZE_CANDIDATE_PENDING_INDEPENDENT_AUDIT
FILES_CREATED = 8
FILES_MODIFIED = 0
PRODUCTION_CODE_WRITTEN = NO
TEST_CODE_WRITTEN = NO
MIGRATION_CREATED = NO
SCHEMA_ENUM_OR_API_CREATED = NO
E5_RUNTIME_IMPLEMENTED = NO
E5_IMPLEMENTATION = NOT_STARTED
NEXT_STAGE = BLOCKED_PENDING_AUDIT
```

Nenhuma capacidade de runtime da E5 existe. Nenhum módulo, schema, enum,
migration, porta ou serviço foi criado. Este diretório contém decisões
arquiteturais congeladas, e decisão congelada não é capacidade construída.

```text
DECLARED != PROVED
FREEZE_DOCUMENT != IMPLEMENTATION
PLAN_PASS != IMPLEMENTATION_PASS
NEXT_STAGE != AUTOMATIC
```
