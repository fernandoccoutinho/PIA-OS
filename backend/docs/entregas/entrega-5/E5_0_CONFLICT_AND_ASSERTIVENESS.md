# E5.0 — Conflito entre Alegações e Assertividade Operacional

Retorno ao índice: [E5.0 — Architectural Documentary Freeze](E5_0_ARCHITECTURE_FREEZE.md)

Congela o contrato v2.6 (Master v2.8, secao 16.14) integralmente.

---

## 1. A unidade correta de avaliação

Conflito é relação entre alegações. Não é quarto estado epistêmico, não é quinta
rota, não é votação de modelos e não é arbitragem de provedores.

```text
PREDICTION_CONFLICT = RELATION_BETWEEN_CLAIMS
PREDICTION_CONFLICT != EPISTEMIC_STATE
PREDICTION_CONFLICT != RESPONSE_ROUTE
PREDICTION_CONFLICT != MODEL_VOTE
PREDICTION_CONFLICT != PROVIDER_ARBITRATION
```

Cada alegação é identificada, no mínimo, por:

```text
alvo e sinal
horizonte e instante de referência
regime aplicável
proveniência e versão
pressupostos e restrições
evidência disponível no instante da previsão
```

```text
CONFLICTING_CLAIMS_REQUIRE_DECOMPOSITION = TRUE
EACH_CLAIM_REQUIRES_INDEPENDENT_COUT_P_GATES = TRUE
```

A decomposição por alegação precede os gates. Se viesse depois, os gates teriam
rodado sobre uma pergunta composta e o resultado por alegação seria
irrecuperável.

```text
CLAIM_LEVEL_STATE_AND_ROUTE = REQUIRED
```

---

## 2. Resolução governada, em ordem

```text
1. normalizar alvo, horizonte, regime e tempo de disponibilidade
2. determinar se as alegações são realmente COMENSURÁVEIS
3. aplicar PIAP e gates COUT-P SEPARADAMENTE a cada alegação
4. preservar resultado, evidência e incerteza de CADA alegação
5. proibir média ou voto sem desenho científico válido
6. identificar a RESTRIÇÃO DECISIVA para a questão composta
7. recomendar a rota governada, sem executar ação
8. declarar autoridade pendente e gatilho de revisão quando aplicável
```

```text
NO_AVERAGING_WITHOUT_COMMENSURABILITY_AND_VALID_DESIGN = TRUE
NO_MAJORITY_VOTE_AS_PREDICTIVE_VALIDATION = TRUE
MODEL_DISAGREEMENT_ALONE != REGIME_SHIFT
MODEL_DISAGREEMENT_ALONE != RECONFIGURE_CANDIDATE
COMPOSITE_RESPONSE_PRESERVES_CLAIM_LEVEL_RESULTS = TRUE
```

O passo 2 separa conflito real de falso conflito. Duas previsões com alvos,
horizontes ou regimes diferentes não são votos sobre a mesma pergunta; são
respostas a perguntas diferentes que parecem discordar. Detectar isso resolve o
conflito por decomposição, não por escolha.

---

## 3. Coexistência e resposta composta

Uma alegação `PREDICTABLE -> PREDICT` pode coexistir com uma restrição
`UNRESOLVED -> INVESTIGATE`. A resposta composta pode recomendar `ROBUST`
somente quando houver limites legítimos, reversíveis e auditáveis. Sem esses
limites, propõe a aprovação deles ou explica limites e se abstém.

```text
PREDICTABLE_CLAIM_MAY_COEXIST_WITH_UNRESOLVED_CONSTRAINT = TRUE
COMPOSITE_ROBUST_ROUTE_REQUIRES_LEGITIMATE_BOUNDS = TRUE
COMPOSITE_RESPONSE_DOES_NOT_OVERWRITE_CLAIM_LEVEL_RESULTS = TRUE
CONFLICT_RESOLUTION_DOES_NOT_EXECUTE_ACTION = TRUE
```

A rota composta não substitui as rotas por alegação: as duas coexistem no
envelope de saída. Apagar as rotas por alegação ao produzir a composta é Stop
Condition, e é o modo de falha mais provável deste componente.

---

## 4. Fronteiras

```text
E5_STRUCTURED_RECOMMENDATION != E8_USER_EXPERIENCE
E5_RECOMMENDATION != USER_DECISION
PREDICTION_CONFLICT != PROVIDER_ARBITRATION
```

A E7 continua proprietária da seleção e arbitragem entre provedores, agentes e
modelos. A E8 continua proprietária da experiência de interação e aprovação. O
usuário mantém a decisão final dentro das fronteiras válidas de segurança e
execução.

As alegações comparadas podem vir de um único modelo, de fontes documentais, de
política, de contrato ou de medição. A E5 compara alegações, não autores. Um
componente desenhado como comparador de saídas de IAs teria virado E7 por
construção.

---

## 5. Assertividade operacional

```text
EPISTEMIC_UNCERTAINTY != OPERATIONAL_VAGUENESS
ASSERTIVE_RESPONSE != OVERCLAIM
ASSERTIVE_RESPONSE != FORCED_ACTION
```

Assertividade é não esconder, em linguagem vaga, a conclusão que os gates
permitem. Não é fabricar certeza nem forçar ação. As duas falhas são simétricas
e igualmente graves: dizer mais do que a evidência permite, e dizer menos do que
ela permite por medo de errar.

A assertividade é avaliada **duas vezes**: por alegação em `E5.n`, sobre o que os
gates científicos e o conflito permitem afirmar; e revalidada no conjunto em
`E5.s`, já conhecendo proteção, proveniência, contrafactual e ônus. As duas
respostas podem legitimamente diferir — uma conclusão candidata assertiva pode
ficar menos assertiva ao descobrir um ramo protetivo `UNRESOLVED`.

### 5.1 Conteúdo mínimo obrigatório da recomendação estruturada

```text
1. conclusão aplicável
2. alvo e horizonte
3. estado e rota POR ALEGAÇÃO
4. restrição decisiva
5. incerteza relevante
6. próximo tratamento governado
7. estado da autoridade
8. gatilho de interrupção ou reavaliação, quando aplicável
```

```text
ASSERTIVE_RESPONSE_REQUIRES_EXPLICIT_CONCLUSION = TRUE
ASSERTIVE_RESPONSE_REQUIRES_DECISIVE_CONSTRAINT = TRUE
ASSERTIVE_RESPONSE_REQUIRES_NEXT_GOVERNED_ROUTE = TRUE
ASSERTIVE_RESPONSE_REQUIRES_AUTHORITY_STATUS = TRUE
ASSERTIVE_RESPONSE_REQUIRES_STOP_OR_REVIEW_TRIGGER_WHEN_APPLICABLE = TRUE
```

Uma recomendação que nomeia uma ação mas omite o item 4 ou o item 7 é
incompleta, e o teste correspondente reprova.

---

## 6. Limites materiais exigem proveniência e autoridade

Limite quantitativo, tolerância de risco, duração de piloto, orçamento e gatilho
de parada não podem ser inventados pela E5. Vêm do usuário, de política válida,
de contrato aprovado ou de evidência explicitamente validada, sempre com
proveniência no PIAP.

```text
SIMULATED_THRESHOLD != AUTHORIZED_THRESHOLD
PROPOSED_BOUND != APPROVED_BOUND
MATERIAL_LIMIT_REQUIRES_PROVENANCE_AND_AUTHORITY = TRUE
ROBUST_ROUTE_WITHOUT_AUTHORIZED_OR_VALIDATED_BOUNDS = FORBIDDEN
E5_VALIDATES_BUT_DOES_NOT_GRANT_APPROVAL = TRUE
```

Faltando o limite, a E5 pode propô-lo para aprovação, mas não tratá-lo como
autorizado. A rota mais tentadora sob incerteza é justamente a que exige mais
proveniência.

Os metadados que tornam essa validação executável chegam pelo PIAP e alcançam
`E5.s` por aresta explícita — ver
[Decomposição](E5_0_DECOMPOSITION_AND_DEPENDENCY_GRAPH.md) secao 3.2.

---

## 7. Kill tests 14 a 23

| # | Caso | Etapa | Resultado exigido |
|---:|---|---|---|
| 14 | mesmo alvo e horizonte, previsões incompatíveis | E5.m | preservar e avaliar cada alegação; sem média nem voto |
| 15 | alvos, horizontes ou regimes diferentes | E5.m | detectar FALSO conflito por decomposição |
| 16 | `PREDICTABLE` coexistindo com restrição `UNRESOLVED` | E5.m, E5.s | preservar AMBAS as rotas por alegação |
| 17 | resposta composta `ROBUST` com limites legítimos e reversíveis | E5.s | PASSA, com limites auditáveis e autorização validada contra os metadados de aprovação |
| 18 | ausência de limites autorizados | E5.n, E5.s | proposta ou abstenção; NUNCA execução. Cobre os quatro desfechos negativos: ausente, expirado, versão divergente e escopo insuficiente |
| 19 | desacordo entre modelos | E5.g, E5.m | não inferir regime shift nem `RECONFIGURE` sozinho |
| 20 | saída assertiva completa | E5.n | conclusão, restrição decisiva, incerteza, autoridade e gatilho |
| 21 | conflito sem rota segura | E5.s | explicação explícita e abstenção |
| 22 | tentativa de média ou voto como validação | E5.m | rejeição |
| 23 | escolha silenciosa de modelo ou provedor | E5.m, E5.b | rejeição e preservação da fronteira E7 |

O caso 23 aparece também em `E5.b` porque a fronteira com a E7 é mensurável por
guarda estática: nenhum módulo de `predictive_accessibility` importa ou chama SDK
de provedor.

Distribuição completa dos 45 casos em
[Decomposição](E5_0_DECOMPOSITION_AND_DEPENDENCY_GRAPH.md) secao 6.

---

## 8. Stop Conditions desta área

```text
SC-E5.0-K  resposta composta que sobrescreve ou apaga estado, rota, evidência
           ou incerteza por alegação ao produzir a rota composta.
SC-T3-B    retornar ROBUST em E5.s sem consumir e validar os metadados de
           aprovação e autoridade transportados pelo PIAP.
```

Lista cumulativa completa em
[Decomposição](E5_0_DECOMPOSITION_AND_DEPENDENCY_GRAPH.md) secao 8.
