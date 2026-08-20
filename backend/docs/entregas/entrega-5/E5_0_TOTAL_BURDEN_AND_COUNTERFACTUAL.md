# E5.0 — Custo Total e Contrafactual Ação, Ação Escalonada, Inação

Retorno ao índice: [E5.0 — Architectural Documentary Freeze](E5_0_ARCHITECTURE_FREEZE.md)

Congela o contrato v2.8 (Master v2.8, secao 16.16) integralmente.

---

## 1. Contrafactual obrigatório

```text
A0 = INACTION_OR_MAINTAIN_CURRENT_COURSE
A1 = STAGED_REVERSIBLE_ACTION
A2 = FULL_OR_INTENSIVE_ACTION
```

Outras alternativas podem existir, mas não substituem silenciosamente `A0`.

```text
MATERIAL_RECOMMENDATION_REQUIRES_COUNTERFACTUAL = TRUE
ALTERNATIVES_INCLUDE_ACTION_STAGED_ACTION_AND_INACTION_WHEN_APPLICABLE = TRUE
INACTION_IS_AN_ALTERNATIVE_WITH_CONSEQUENCES = TRUE
MISSING_INACTION_COST != ZERO_INACTION_COST
ACTION_EFFECTIVENESS_ALONE != TOTAL_BURDEN_JUSTIFICATION
```

A inação não é baseline neutra. Custo ausente ou não medido não equivale a custo
zero — e essa é a assimetria que o contrato existe para impedir, porque os custos
de agir costumam ser explícitos e orçamentários enquanto os custos de não agir
costumam ser difusos e não registrados.

---

## 2. Base comparável

```text
COUNTERFACTUAL_COMPARABILITY = REQUIRED
SAME_TARGET_POPULATION_HORIZON_AND_REGIME = DEFAULT
ASYMMETRIC_COMPARISON_REQUIRES_EXPLICIT_JUSTIFICATION = TRUE
HIDDEN_BURDEN_TRANSFER = FORBIDDEN
```

As alternativas usam o mesmo alvo, população, jurisdição, horizonte, regime,
informação disponível e convenção temporal. Não é permitido fazer a ação parecer
cara no curto prazo e comparar sua inação apenas num horizonte em que os danos
ainda não surgiram, nem usar populações diferentes para ocultar transferência de
ônus.

O contrafactual é montado sobre candidatos completos e com proveniência validada
— ver
[Decomposição](E5_0_DECOMPOSITION_AND_DEPENDENCY_GRAPH.md) secao 3.1.

---

## 3. Vetor plural de ônus

```text
TOTAL_BURDEN_VECTOR
|-- FINANCIAL_AND_RESOURCE_BURDEN
|-- SOCIAL_AND_HUMAN_BURDEN
|-- CRITICAL_SERVICE_CONTINUITY_BURDEN
|-- DISTRIBUTIONAL_AND_EQUITY_BURDEN
|-- OPPORTUNITY_AND_DELAY_BURDEN
+-- IRREVERSIBILITY_AND_RECOVERY_BURDEN
```

Somente dimensões materiais e sustentadas são registradas; criar categoria
artificial é tão errado quanto omitir categoria material. Cada dimensão registra
quem paga, quem se beneficia, quem permanece exposto, quando o ônus ocorre, se é
reversível e qual evidência o sustenta.

---

## 4. Proibição de agregação inventada

```text
PLURAL_BURDEN_VECTOR != AUTOMATIC_SCALAR_SCORE
SOCIAL_HARM != INVENTED_MONETARY_VALUE
UNAUTHORIZED_WEIGHTING = FORBIDDEN
NONCOMMENSURABLE_DIMENSIONS_REMAIN_SEPARATE = TRUE
QUANTIFICATION_REQUIRES_UNIT_SOURCE_TIME_AND_UNCERTAINTY = TRUE
DISCOUNT_RATE_RISK_TOLERANCE_AND_VALUE_WEIGHTS_REQUIRE_AUTHORITY = TRUE
```

Na ausência de comensurabilidade, a E5 preserva o vetor, as relações de
dominância, os limites e os trade-offs. Não fabrica uma soma.

Decisão sob incerteza:

```text
EXPECTED_LOSS_REQUIRES_VALIDATED_PROBABILITIES_AND_MAGNITUDES = TRUE
UNRESOLVED_UNCERTAINTY_REQUIRES_SCENARIOS_OR_BOUNDS = TRUE
ROBUST_OR_LOW_REGRET_RECOMMENDATION_REQUIRES_VALID_BOUNDS = TRUE
UNCERTAINTY != ZERO_COST_INACTION
UNCERTAINTY != LICENSE_FOR_EXTREME_ACTION
```

A E5 declara dominância e trade-offs. A inação pode ser legitimamente
recomendada quando agir produz maior ônus total ou quando não há rota segura.
Não pode vencer porque seus custos foram omitidos.

---

## 5. Fronteira entre `TOTAL_BURDEN_VECTOR` e `L_total`

Os dois objetos parecem a mesma coisa e não são.

```text
L_total = L_prediction + L_false_action + L_unnecessary_acquisition
        + L_abstention + L_compute
```

`L_total` é requisito científico herdado e mede o **comportamento do sistema** —
erra menos, age falsamente menos, adquire desnecessariamente menos, abstém-se na
hora certa, gasta menos computação.

`TOTAL_BURDEN_VECTOR` mede as **consequências no mundo** das alternativas
comparadas numa recomendação material — quem paga, quanto, quando, com que
reversibilidade.

```text
TOTAL_BURDEN_VECTOR != L_TOTAL_BY_DEFAULT
L_TOTAL_SEMANTICS_REQUIRE_E5_0_FREEZE = TRUE
```

Freeze semântico, em seis pontos:

```text
1. `L_total` mede desempenho do SISTEMA no benchmark; é escalar por construção,
   com as cinco parcelas da fonte original, e pertence ao critério de fechamento
   da E5.
2. `TOTAL_BURDEN_VECTOR` mede ônus das ALTERNATIVAS no mundo; é plural por
   construção e pertence à recomendação material entregue ao usuário.
3. Os dois NÃO se somam, NÃO se convertem um no outro e NÃO compartilham unidade.
4. `L_false_action` e `L_abstention` são as parcelas de `L_total` mais próximas
   do vetor, porque ambas dependem de consequência. Ainda assim são parcelas de
   uma métrica de desempenho de sistema, medidas no desenho do benchmark, e não
   o vetor de ônus de uma recomendação concreta.
5. Qualquer composição escalar do vetor, função de utilidade, taxa de desconto,
   valor estatístico de vida ou tolerância de risco exige proveniência,
   validação e autoridade explícitas. A E5 não cria esses parâmetros.
6. A FÓRMULA de `L_total` não é uma implementação numérica autorizada. As cinco
   parcelas têm unidades diferentes; somá-las exige normalização e pesos, e
   nenhum dos dois nasce aqui.
```

```text
L_TOTAL_FORMULA != AUTHORIZED_NUMERIC_IMPLEMENTATION
L_TOTAL_COMPONENT_UNITS_NORMALIZATION_AND_WEIGHTS_REQUIRE_BENCHMARK_FREEZE
```

O ponto 4 é onde a confusão nasceria na prática: um implementador apressado veria
`L_false_action` e o ramo social do vetor e concluiria que são a mesma medida com
nomes diferentes. Não são — a primeira é parcela de perda do sistema agregada
sobre o benchmark; a segunda é o dano a pessoas concretas de uma alternativa
concreta. O ponto 6 é o mesmo erro um nível acima.

---

## 6. Envelope mínimo do contrafactual

```text
ALTERNATIVES_CONSIDERED
INACTION_BASELINE_AND_CONSEQUENCES
BURDEN_VECTOR_BY_ALTERNATIVE
AFFECTED_GROUPS_AND_BURDEN_DISTRIBUTION
EVIDENCE_PROVENANCE_AND_UNCERTAINTY
TIME_HORIZON_AND_REVERSIBILITY
DOMINANCE_AND_TRADEOFF_RESULT
RECOMMENDED_ALTERNATIVE_AND_RATIONALE
OWNER_AND_AUTHORITY_STATUS
EXECUTION_STATUS = NOT_EXECUTED_BY_E5
STOP_TRANSITION_OR_REVIEW_TRIGGER
```

---

## 7. Kill tests 34 a 45

| # | Caso | Etapa | Resultado exigido |
|---:|---|---|---|
| 34 | ação com custo explícito e inação tratada como custo zero | E5.q | FALHA |
| 35 | comparação financeira que omite dano social material | E5.r | FALHA |
| 36 | monetização ou ponderação social sem método e autoridade | E5.r | FALHA |
| 37 | incidência do ônus sobre grupo vulnerável omitida | E5.r | FALHA |
| 38 | horizontes, populações ou regimes assimétricos sem justificativa | E5.q | FALHA |
| 39 | ação escalonada reversível dominante omitida | E5.q | FALHA |
| 40 | alternativa dominada recomendada sem restrição decisiva | E5.r, E5.s | FALHA |
| 41 | inação legitimamente preferível por menor ônus total | E5.r, E5.s | PASSA |
| 42 | probabilidade não validada usada em perda esperada numérica | E5.r | FALHA |
| 43 | cenários e limites válidos com rota robusta e gatilho de revisão | E5.r, E5.s | PASSA |
| 44 | vetor plural preservado sem soma arbitrária, com trade-offs | E5.r | PASSA |
| 45 | recomendação comparativa convertida em efeito externo pela E5 | E5.b, E5.s | FALHA |

---

## 8. Fixture composto — El Niño e SIN em 2027

```text
NATUREZA = FIXTURE_COMPOSTO
NÃO ACRESCENTA UM 46o CASO
APLICA CUMULATIVAMENTE OS CASOS ACIMA
ETAPA = E5.t, com ensaio parcial em E5.q e E5.r
```

Dada evidência climática prospectiva de risco, sem prova suficiente de apagão, a
E5 compara:

```text
A0 = NO_ADDITIONAL_PREPARATION
A1 = STAGED_REVERSIBLE_READINESS_WITH_REVIEW_TRIGGERS
A2 = IMMEDIATE_EXTRAORDINARY_OPERATIONAL_MEASURES
```

A comparação inclui custos de preparação, reserva e oportunidade; efeitos sociais
de eventual interrupção sobre saúde, água, telecomunicações, trabalho e
segurança; distribuição regional dos ônus; continuidade de serviços críticos;
reversibilidade; e custo de recuperação.

```text
A0 NÃO recebe custo zero
A2 NÃO é acionada apenas pela existência do El Niño
```

Se limites válidos demonstrarem que `A1` reduz o arrependimento e preserva opções
com ônus controlável, a recomendação esperada é preparação escalonada, com
medidas extraordinárias condicionadas a critérios vigentes e gatilhos
documentados. Se essa dominância não estiver sustentada, o resultado permanece
`UNRESOLVED -> INVESTIGATE` ou abstém-se da escolha. Em todos os casos,
`E5_EXECUTION = NONE`.

### 8.1 Restrição obrigatória sobre o fixture

Os dados de cenário são SINTÉTICOS e assim rotulados no próprio artefato de
teste. Não podem ser lidos como previsão sobre o setor elétrico, não geram limite
autorizado e não constituem evidência setorial.

```text
SYNTHETIC_FIXTURE != SECTOR_EVIDENCE
SYNTHETIC_FIXTURE != AUTHORIZED_BOUND
BENCHMARK_THAT_BUILDS_THE_HYPOTHESIS != INDEPENDENT_PROOF
E9_OWNS_INDEPENDENT_BENCHMARKS_AND_EXPERIMENTAL_PROOF = TRUE
```

---

## 9. Stop Conditions desta área

```text
SC-E5.0-L  fixture El Niño e SIN em 2027 cujos dados sintéticos sejam
           apresentados como previsão real, evidência setorial ou limite
           autorizado.
SC-E5.0-S  fórmula de L_total tratada como implementação numérica autorizada,
           somando parcelas de unidades diferentes sem normalização e pesos
           congelados no desenho do benchmark.
SC-T3-D    declarar E5.o como único componente sujeito a falha por omissão;
           E5.q e E5.r também têm obrigações de não omissão.
```

Lista cumulativa completa em
[Decomposição](E5_0_DECOMPOSITION_AND_DEPENDENCY_GRAPH.md) secao 8.
