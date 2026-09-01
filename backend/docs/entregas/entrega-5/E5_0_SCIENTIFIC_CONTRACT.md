# E5.0 — Contrato Científico (COUT-P v1.3)

Retorno ao índice: [E5.0 — Architectural Documentary Freeze](E5_0_ARCHITECTURE_FREEZE.md)

```text
COUT_P_v1_3 = FROZEN_CANDIDATE
COUT_P_v1_2 = SUPERSEDED_AS_CANDIDATE_BY_v1_3
SCIENTIFIC_CONTRACT_REOPENED = NO
```

Reconcilia os invariantes das duas fontes v1.2 — a original, que fixa Power
Gate, multiplicidade, auditabilidade e `L_total`; e a revisada, que acrescenta
validade de regime, `R(k->t)`, `V_t`, `K_history` e reconfiguração.

---

## 1. Símbolos e semântica

```text
A-               cota inferior de ganho preditivo acessível, corrigida
A*_worst         pior caso de potência sobre classe PRÉ-REGISTRADA (C,S)
A_rel            efeito mínimo relevante, DECLARADO ANTES do teste
K_pred           canais sem acessibilidade preditiva demonstrada
R(k->t)          pertinência da observação histórica k ao instante t
V_t              histórico admissível { k : R(k->t) > rho_min }, pode ser descontínuo
K_history        passado sem validade demonstrada para o presente
                 K_history != K_pred ; K_history != apagamento
D_regime         d[ P_ref(Y|X) , P_recent(Y|X) ], limiar theta
H_pred(R_t)      conjunto de horizontes admissíveis — ESPECTRO, não supremo
Delta_cont       sup{ d : [0,d] contido em H_pred }
R_pred           H_pred menos [0, Delta_cont]  (recorrência)
Delta_A_incremental   A-(T+Z) menos max(A-(T), A-(Z))
                 NUNCA rotulado "sinergia n*=2"
avail(Z,t,Delta) em {0,1}, obrigatório inclusive para variáveis de regime
L_total          L_pred + L_false_action + L_unnec_acquisition
                 + L_abstention + L_compute
```

### 1.1 A classe pré-registrada `(C,S)`

`A*_worst` é supremo sobre **biblioteca finita declarada**, não sobre todas as
formas possíveis. A notação honesta é `PREDICTIVELY_INACCESSIBLE^(C,S)` com `S`
declarada.

```text
A_STAR_WORST_IS_SUPREMUM_OVER_PREREGISTERED_LIBRARY = TRUE
UNIVERSAL_BOUND_CLAIM_WITHOUT_C_S = OVERCLAIM
```

Esta ressalva é obrigatória em toda saída. O núcleo v1.1 já reportou uma cota
como universal quando não era.

---

## 2. Objeto composto por alegação

```text
CLAIM_EVALUATION_RESULT
  = claim + provenance + regime + evidence + uncertainty + horizon + state
```

Os sete componentes viajam juntos porque separá-los perderia o que os contratos
v2.6 a v2.8 exigem preservar: sem `provenance` não há atribuição por alegação;
sem `uncertainty` a assertividade vira overclaim; sem `regime` e `horizon` não
há como detectar falso conflito; sem `state` não há rota.

O produtor é `E5.j` — ver
[Decomposição](E5_0_DECOMPOSITION_AND_DEPENDENCY_GRAPH.md) §3.

```text
NAMED_COMPOSITE_INPUT_WITHOUT_PRODUCER != IMPLEMENTABLE_DEPENDENCY_GRAPH
ASSEMBLY_DOES_NOT_RECOMPUTE_COMPONENTS = TRUE
```

A montagem é composição imutável dos sete componentes já produzidos a montante.
Não recalcula regime, não reestima evidência, não reduz incerteza e não trunca
horizonte. Componente ausente é defeito, não valor vazio.

---

## 3. Power Gate e os três estados epistêmicos

```text
PREDICTABLE
    A- > 0 E todos os gates confirmatórios aplicáveis = PASS

UNRESOLVED
    A- <= 0 E potência insuficiente para excluir efeito >= A_rel
    isto é: A*_worst >= A_rel

PREDICTIVELY_INACCESSIBLE
    A- <= 0 E A*_worst < A_rel
    relativo a alvo, sinal, informação, horizonte, resolução, A_rel e potência
    NUNCA impossibilidade metafísica
```

```text
POWER_GATE = REQUIRED
THREE_EPISTEMIC_STATES = REQUIRED
EVIDENCE_AND_AUDIT_TRAIL = REQUIRED
UNRESOLVED_IS_VALID_OUTPUT = TRUE
PREDICTIVELY_INACCESSIBLE_IS_VALID_OUTPUT = TRUE
USEFUL_RESPONSE_ROUTING = REQUIRED

"nao encontrei" != "posso excluir"
potência insuficiente           -> UNRESOLVED           (NUNCA inacessível)
potência suficiente e A- <= 0   -> PREDICTIVELY_INACCESSIBLE^(C,S)
gate confirmatório FAIL         -> previsão NÃO liberada, em nenhum estado
nenhuma rota segura             -> EXPLAIN_LIMITS_AND_ABSTAIN
```

Transições admissíveis:

```text
qualquer estado --[nova evidência ou novo Z admitido]--> reavaliação completa
qualquer estado --[reconfiguração aprovada]-----------> reavaliação completa
UNRESOLVED --[mais potência, mesmo desenho]-----------> PREDICTABLE ou PRED.INACCESSIBLE
PREDICTIVELY_INACCESSIBLE --[A_rel menor OU novo canal]--> reavaliação completa

PROIBIDO: UNRESOLVED -> PREDICTIVELY_INACCESSIBLE por baixa potência
PROIBIDO: qualquer transição sem reexecutar o Power Gate
```

Resposta útil quando legítima não elimina a abstenção. Fabricar rota para evitar
saída inconclusiva é Stop Condition. As quatro rotas e o comportamento
`NO_SAFE_ROUTE` estão em
[Architecture Freeze](E5_0_ARCHITECTURE_FREEZE.md) §5.1.

---

## 4. Plano estatístico

```text
NULL            null apropriado ao canal, pré-registrado
PLACEBO         p_placebo < alpha_corrigido
SHUFFLE         havendo temporalidade: G_real > G_shuffled
BASELINE        ganho medido SOBRE baseline relevante declarado
MULTIPLICIDADE  incorporada AO QUANTIL, não subtraída depois como penalidade
                arbitrária
CEGO            G_blind > 0; seleção NUNCA olha o bloco cego
HETEROGENEIDADE e INCERTEZA reportadas, não colapsadas em ponto

MULTIPLE_COMPARISON_CORRECTION = REQUIRED
```

Duas armadilhas já pagas pelo núcleo v1.1 e aqui fixadas:

1. A calibração do gerador tem de ser exata contra marginais empíricas. Gerador
   mal calibrado produz `A- > 0` a partir de ruído.
2. `A*_worst` é supremo sobre biblioteca finita — ver secao 1.1.

---

## 5. Validade histórica, regime, transportabilidade e temporalidade

```text
PAST_VALIDITY != CURRENT_PREDICTIVE_VALIDITY
HISTORICAL_CORRELATION != CURRENT_CAUSAL_TRANSPORTABILITY
RECENCY != RELEVANCE
HISTORICAL_TRUTH != CURRENT_PREDICTIVE_ADMISSIBILITY
K_HISTORY_PRESERVES_PROVENANCE = TRUE

PREDICTION_ERROR != REGIME_SHIFT
REGIME_SHIFT_CANDIDATE != CONFIRMED_SHIFT
CONFIRMED_SHIFT != CAUSAL_EXPLANATION
MODEL_DISAGREEMENT_ALONE != REGIME_SHIFT

ALL_PREDICTORS_REQUIRE_AVAILABILITY_AT_PREDICTION_TIME = TRUE
REGIME_VARIABLES_REQUIRE_AVAILABILITY_AT_PREDICTION_TIME = TRUE
FUTURE_LEAKAGE = FORBIDDEN
SELECTION_AND_VALIDATION_DATA_REUSE = FORBIDDEN_WITHOUT_VALID_DESIGN
```

Regra operacional: `avail = 0` implica **rejeição da variável antes do
estimador**, não penalização depois. Rejeição antes é verificável por teste — o
estimador não foi chamado —, o mesmo padrão de prova usado na E4.5.2 ao provar
que o `PersistenceManager` não é chamado após falha de fidelidade. Penalização
posterior não é verificável do mesmo modo.

O gate de disponibilidade precede o detector de regime porque `avail` vale também
para as variáveis usadas na identificação de regime; se o detector rodasse antes,
ele próprio poderia vazar futuro.

`K_history` é conjunto transiente e não escreve estado na E4 — ver
[Architecture Freeze](E5_0_ARCHITECTURE_FREEZE.md) secao 6.1.

---

## 6. Reconfiguração controlada

```text
erro isolado                   não implica RECONFIGURE
D_regime > theta sozinho       não implica RECONFIGURE
melhor ajuste retrospectivo    não implica PROMOÇÃO
desacordo entre modelos        não implica RECONFIGURE

RECONFIGURE_CANDIDATE exige:  degradação medida
                            + D_regime > theta testado CONTRA FLUTUAÇÃO
                            + candidato com A- > 0 em validação PROSPECTIVA
                              ou adequadamente ANINHADA e CEGA

PROMOÇÃO exige: versão, proveniência, hipótese, dados de validação, custo,
                responsável, aprovação aplicável e caminho de ROLLBACK
APOS A PROMOÇÃO: o modelo novo VOLTA a passar por TODOS os gates COUT-P e o
                estado epistêmico é REAVALIADO

NO_SILENT_RETRAINING = TRUE
NO_SILENT_PROVIDER_OR_MODEL_SWITCH = TRUE
MODEL_OR_REGIME_CHANGE_REQUIRES_VERSIONING = TRUE
ROLLBACK_PATH_REQUIRED = TRUE
BLIND_VALIDATION_PRECEDES_PROMOTION = TRUE
```

A mesma janela não pode selecionar e confirmar. É reutilização de evidência, não
validação independente.

A aprovação da promoção chega a `E5.l` pelos metadados de autoridade do PIAP.
Ausência, expiração, versão divergente ou escopo insuficiente impedem a promoção
— ver [Decomposição](E5_0_DECOMPOSITION_AND_DEPENDENCY_GRAPH.md) secao 3.2.

```text
NO_PROMOTION_IN_E5_l_WITHOUT_VALIDATED_PIAP_APPROVAL_METADATA = TRUE
APPROVAL_VALIDATION_FAILURE != AUTHORIZATION_TO_INVENT_APPROVAL
```

Persistência da reconfiguração usa ownership e repository/port próprios da E5
(D3). Reuso ou escrita de `ApprovalRecord` da E4 é proibido.

---

## 7. Horizonte como espectro

```text
PROIBIDO: Delta_C = sup{ Delta : A-(Delta) > 0 } como representação única
EXIGIDO:  H_pred(R_t) = { Delta : A-(Delta) > 0 e Gates(Delta) = PASS }
          mais Delta_cont (persistência) e R_pred (recorrência)

persistência != recorrência != sazonalidade
PREDICTIVE_HORIZON = SET_OR_SPECTRUM
HORIZON_MAY_BE_REGIME_DEPENDENT = TRUE
```

---

## 8. Aquisição de informação

```text
Z* = argmax_Z  Delta_A_pred(Z) / cost(Z)

PROPOSED_Z_STAR != AUTHORIZED_DATA_ACCESS
INFORMATION_ACQUISITION_PROPOSAL != CONNECTOR_EXECUTION
ACQUISITION_REQUIRES_SCOPE_PERMISSION_PRIVACY_AND_COST_CHECKS = TRUE
E5_ACQUIRES_DATA = FALSE
```

A E5 emite proposta nomeada e custeada. Quem pode acessar, com que escopo, sob
qual privacidade e com qual aprovação é decisão fora da E5. A consulta à E4
permanece somente leitura.

---

## 9. `L_total` como critério científico

```text
L_total = L_prediction + L_false_action + L_unnecessary_acquisition
        + L_abstention + L_compute
```

`L_total` é o critério pelo qual se julga se COUT-P merece permanecer no PIA-OS:
ele só merece se reduzir `L_total` em benchmark cego. É medida sobre o
**comportamento do sistema**.

```text
L_TOTAL_FORMULA != AUTHORIZED_NUMERIC_IMPLEMENTATION
L_TOTAL_COMPONENT_UNITS_NORMALIZATION_AND_WEIGHTS_REQUIRE_BENCHMARK_FREEZE
TOTAL_BURDEN_VECTOR != L_TOTAL_BY_DEFAULT
```

A fórmula é o critério; a métrica só existe depois que o desenho do benchmark
congelar unidades, normalização e pesos, com proveniência e autoridade. As cinco
parcelas têm unidades diferentes e não se somam por estarem escritas na mesma
linha.

Fronteira completa com o `TOTAL_BURDEN_VECTOR` em
[Custo total e contrafactual](E5_0_TOTAL_BURDEN_AND_COUNTERFACTUAL.md) secao 5.

O benchmark independente pertence à E9. Benchmark que constrói a hipótese não é
prova independente.

---

## 10. Stop Conditions desta área

```text
SC-E5.0-F  K_history materializado como coluna, flag ou estado em qualquer
           tabela de E3 ou E4.
SC-E5.0-G  A*_worst reportado como cota universal, sem a ressalva (C,S).
SC-E5.0-S  fórmula de L_total tratada como implementação numérica autorizada.
SC-T3-A    consumir CLAIM_EVALUATION_RESULT sem produtor e sem arestas para os
           sete componentes obrigatórios.
SC-T3-B    promover em E5.l, ou retornar ROBUST em E5.s, sem consumir e validar
           os metadados de aprovação do PIAP.
```

Lista cumulativa completa em
[Decomposição](E5_0_DECOMPOSITION_AND_DEPENDENCY_GRAPH.md) secao 8.
