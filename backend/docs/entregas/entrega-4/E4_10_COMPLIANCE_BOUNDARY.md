# E4.10 — Compliance Boundary

Avaliação de estado ou ação contra política explícita e versionada,
produzindo diagnóstico e evidência.

```text
E4_10 = COMPLETE_CANDIDATE
COMPLIANCE_FINDING_PERSISTED = NO
MIGRATION = NONE
REPAIR_IMPLEMENTED = NO
PUBLIC_API = NONE
E4_11 = NOT_STARTED
PASS_FINAL = NOT_DECLARED
```

---

## 1. A distinção que esta fatia existe para preservar

```text
INTEGRITY   = estado × invariantes estruturais
GOVERNANCE  = ação × permissão
COMPLIANCE  = estado/ação × policy
```

O `E4_GOVERNANCE_BOUNDARIES` §3 fixa o exemplo que decide tudo: um ciclo
causal é falha de **integridade** — seria falha em qualquer instalação
do PIA-OS. Um estado avaliado contra uma política específica é
**conformidade** — outra instalação, com outra política, não teria falha
alguma.

```text
COMPLIANCE != INTEGRITY
COMPLIANCE != GOVERNANCE_DECISION
COMPLIANCE != REPAIR
COMPLIANCE != LEARNING
COMPLIANCE != ACCESSIBILITY_MUTATION
COMPLIANCE != RETENTION_EXECUTION
COMPLIANCE != ERASURE_EXECUTION
```

Governança decide **antes**; conformidade constata **depois**.

## 2. Escopo entregue

```text
NOVO   app/memory/models/compliance_enums.py        vocabulários fechados
NOVO   app/memory/schemas/compliance.py             contratos transitórios
NOVO   app/memory/services/compliance_evaluator.py  função pura
MIGRATION  NONE
```

Nenhum arquivo de E4.1–E4.9 alterado. Nenhum `app/cognitive/` tocado.
Nenhuma tabela, nenhum endpoint, nenhum worker, nenhum scheduler.

## 3. Os quatro desfechos

```text
COMPLIANT                 policy aplicável, avaliada, sem violação
POLICY_NOT_APPLICABLE     não alcança o sujeito, ou não vigorava
INSUFFICIENT_INFORMATION  faltou observação para decidir
VIOLATION_CONFIRMED       ao menos uma violação localizada
```

```text
NO_POLICY                != COMPLIANT
INSUFFICIENT_INFORMATION != COMPLIANT
```

Três não bastariam: sem o terceiro estado, a falta de observação cairia
em conformidade ou em violação, e as duas seriam afirmações que ninguém
observou.

### `INSUFFICIENT_INFORMATION` é evidência, não finding

Representação **única**, e a escolha é material: um finding afirma uma
condição encontrada **no sujeito**, e insuficiência é condição da
**observação**. Emitir um warning finding diria que há algo errado com o
objeto quando o que falta é dado sobre ele — e colidiria com o
invariante, tornando `len(findings) >= 1` ambíguo entre violação e
insuficiência.

## 4. Invariantes fechados no construtor

```text
COMPLIANT                -> zero findings, ao menos uma regra avaliada
POLICY_NOT_APPLICABLE    -> zero findings, zero regras aplicáveis
INSUFFICIENT_INFORMATION -> zero findings, ao menos uma observação faltante
VIOLATION_CONFIRMED      -> ao menos um finding
```

Cada finding cita **exatamente** o sujeito, a política, a versão e o
instante do relatório. Um finding de outra versão é inconstrutível
dentro de um relatório.

`INSUFFICIENT_INFORMATION` nunca vira `COMPLIANT` por três camadas: o
tipo é congelado; o mesmo par de valores não satisfaz os dois desfechos,
porque um exige `missing_observations` não vazio e o outro exige vazio;
e nenhuma função do módulo produz desfecho a partir de outro relatório —
não existe caminho de reclassificação.

## 5. As três matrizes concretas

### GOVERNANCE

```text
DENY  + EXECUTED                 -> COMPLIANCE-GOV-001
vigente sem regra + EXECUTED     -> COMPLIANCE-GOV-002
DENY  + NOT_EXECUTED             -> COMPLIANT
ADMIT + EXECUTED | NOT_EXECUTED  -> COMPLIANT
só ADMIT   + NOT_OBSERVED        -> COMPLIANT
algum DENY + NOT_OBSERVED        -> INSUFFICIENT_INFORMATION
sem regra  + NOT_OBSERVED        -> INSUFFICIENT_INFORMATION
```

As regras aplicáveis são resolvidas **antes** de tratar a não
observação:

```text
MISSING_OBSERVATION_MATTERS_ONLY_WHERE_IT_CHANGES_THE_RESULT
```

Quando todas as regras aplicáveis admitem, os dois estados possíveis são
conformes, e o dado que falta não decide nada — pedi-lo seria exigir uma
observação sem consequência. Onde alguma regra nega, ou onde não há
regra aplicável, a observação decide entre desfechos distintos, e a
insuficiência é real.

`ObservedOperationState` é enum próprio, e não `GovernanceEffect`:

```text
PRESCRIPTION != FACT
ADMISSION    != OBLIGATION_TO_EXECUTE
```

`ADMIT + NOT_EXECUTED` é conforme. Tratar o não uso de uma permissão
como desvio transformaria a política num agendador.

### ACCESSIBILITY

Aresta **exata**, `declared_source → current_state`, com
`DENY_OVERRIDES`.

```text
COMPLIANCE-ACC-001  transição observada contra regra DENY
COMPLIANCE-ACC-002  extinção causal observada sem evidência
COMPLIANCE-ACC-003  transição observada sem regra aplicável vigente
```

`declared_source=None` ou evidência `NOT_OBSERVED` produz insuficiência,
nunca conformidade.

### RETENTION

```text
MINIMUM_AGE       = PRESERVATION_FLOOR
MINIMUM_AGE      != DELETION_DEADLINE
ASSESS_AND_INFORM != DELETE
AGE >= MINIMUM_AGE != VIOLATION_BY_PERMANENCE
```

```text
POLICY_NOT_EFFECTIVE | OUT_OF_SCOPE      -> POLICY_NOT_APPLICABLE
PRESERVE_LEGACY_PROTECTED | NOT_YET_DUE  -> COMPLIANT
ASSESS_AND_INFORM + PRESENT              -> COMPLIANT
ASSESS_AND_INFORM + ABSENT               -> COMPLIANCE-RET-001
ASSESS_AND_INFORM + NOT_OBSERVED         -> INSUFFICIENT_INFORMATION
anchor_at ausente                        -> INSUFFICIENT_INFORMATION
```

`COMPLIANCE-RET-001` significa: avaliação e informação exigidas após a
elegibilidade, e confirmadamente ausentes. O cálculo de elegibilidade
**não é reimplementado** — `avaliar_retencao` é a fonte única desde a
E4.9.9.c, e reproduzir a regra do máximo dos vencimentos criaria duas
respostas para a mesma pergunta.

## 6. Achados desta fatia

**A1 — dois erros novos de mypy, fechados por estreitamento.**
`declared_source: str | None` e `subject.domain_id: UUID | None` não
narrowavam através das listas de acumulação. A saída não foi `cast` nem
`type: ignore`: os ramos de insuficiência passaram a retornar
diretamente, e o estreitamento virou **estrutural**.

**A2 — a checagem redundante de versão escondia a dimensão que importa.**
`PolicyReference` já carrega a versão, então uma divergência de versão
fazia falhar primeiro a comparação da referência inteira, com mensagem
genérica. A ordem foi invertida: a versão é verificada antes, e o erro
nomeia a dimensão que dá sentido ao diagnóstico.

**A3 — guarda cega ao receptor.** `SET_ADD != SESSION_ADD`. A primeira
versão da guarda de mutação reprovou `identificadores.add(rule_id)` — um
`set` local detectando duplicata. Proibir o nome sem olhar o receptor
proibiria estrutura de dados, não escrita. É a mesma lição que a guarda
`g13` da cadeia 94 pagou ao contar um `SELECT` como DDL.

**A4 — duas sondas do plano estavam erradas, e a auditoria pegou uma.**
A sonda de consumidor media **chamadas** a `avaliar_conformidade`, e
produção define a fronteira sem consumi-la —
`DEFINITION_IS_ALSO_A_REFERENCE`, terceira ocorrência da mesma família.
A sonda de vínculo família-regra exigia as três famílias dentro de uma
única função e teria reprovado a forma canônica do projeto: mapa
constante no topo, consumido por um validador. Ambas corrigidas e a
cadeia 94 **re-medida** com o instrumento já corrigido.

**A5 — manutenção de instrumento na cadeia 94, autorizada.**

```text
E4_9_PRODUCTION_CHANGED          = NO
E4_9_CONTRACT_CHANGED            = NO
E4_9_RUNTIME_FINDING             = NONE
E4_9_TEST_INSTRUMENT_MAINTENANCE = AUTHORIZED
```

`test_i24` da E4.9.9.d media `id(resultado.session)` e comparava o
tamanho do conjunto.

```text
OBJECT_IDENTITY_OVER_TIME != MEMORY_ADDRESS
```

`id()` é endereço, e endereço é reciclável: quando a primeira `Session`
era coletada antes de a segunda existir, o alocador devolvia o mesmo
endereço e duas sessões genuinamente distintas produziam `id` idêntico.
MEDIDO: 1 falha em 10 execuções isoladas. O comportamento sob teste
nunca esteve em questão — a E4.9.9.d prova a mesma separação por outras
duas vias (`i20` conta duas UoW; `i03` prova commit independente por
recibo). O defeito era do instrumento.

A correção guarda **referência forte** às duas sessões, o que impede a
coleta durante a medição, e compara identidade real com `is not`.
Nenhum `id()`, `hash`, endereço ou coleta manual. MEDIDO após a
correção: 100 execuções, 0 falhas.

Classificação: manutenção objetiva de instrumento, autorizada dentro
deste commit. Nenhum arquivo de produção, contrato ou migration da E4.9
foi tocado.

**A6 — as três famílias divergem no contrato de leitura.** MEDIDO:
governança e acessibilidade guardam JSON e expõem `deserialize_rules`;
retenção devolve regra tipada pelo `RetentionRulesType`. A conversão
pertence a quem lê, e a E4.10 não é dona desse contrato.

## 7. Compatibilidade — Master v2.4

### `PIA_OS_SOPHIA_MASTER_COMPATIBILITY` (20)

```text
USER_AUTHORITY_PRESERVED                        OK  diagnóstico não decide nada
SOPHIA_BRAND_PIA_OS_CODEBASE_PRESERVED          OK
MODULE_SCOPE_AND_DEFERRED_CAPABILITIES_DECLARED OK  §2 e §9
SCHEDULE_MODE_DECLARED                          OK  SCHEDULER = NONE
AI_ROLE_AND_STEP_INSTRUCTION_DISTINGUISHED      OK  o modelo não avalia nem decide
PROVIDER_CONNECTION_METHOD_DECLARED             OK  nenhuma
AUTOMATION_SCOPE_DECLARED                       OK  nenhuma execução automática
APPROVAL_GATES_DECLARED                         OK  não consome aprovação
PERSISTENCE_BEHAVIOR_DECLARED                   OK  nada é persistido
MULTI_AI_RESULT_ATTRIBUTION_DECLARED            NOT_APPLICABLE_TO_RUNTIME
DIVERGENCE_PRESERVATION_DECLARED                OK  quatro desfechos disjuntos
CONCURRENT_WORK_ISOLATION_DECLARED              OK  função pura, sem estado
BACKGROUND_EXECUTION_AUTHORIZATION_DECLARED     OK  nenhuma
RESOURCE_LIMITS_QUEUE_AND_COST_DECLARED         OK  QUEUE = NONE
REMOTE_RESOURCE_SCOPE_DECLARED                  OK  nenhum recurso remoto
OBSERVATION_PREPARATION_EXECUTION_DISTINGUISHED OK  observação tipada, sem execução
CREDENTIAL_AND_SECRET_BOUNDARY_DECLARED         OK  sem campo de conteúdo
FAILURE_ROLLBACK_AND_CONCURRENCY_DECLARED       OK  sem transação
CURRENT_CAPABILITY_NOT_OVERSTATED               OK  §9
FROZEN_MODULES_UNCHANGED                        OK  E3 e E4.1-E4.9 intactas
```

### `SOPHIA_UX_COMPATIBILITY` (17)

```text
USER_AUTHORITY_PRESERVED                          OK
SCHEDULE_MODE_DECLARED                            OK  nenhum
AUTOMATION_SCOPE_DECLARED                         OK  nenhuma
PERSISTENCE_BEHAVIOR_DECLARED                     OK  transitório
PROVIDER_NEUTRALITY_PRESERVED                     OK  nenhum provedor citado
PERSONALIZATION_REVERSIBLE                        NOT_APPLICABLE  sem UX
CONCURRENT_WORK_ISOLATION_DECLARED                OK
BACKGROUND_EXECUTION_AUTHORIZATION_DECLARED       OK  nenhuma
RESOURCE_LIMITS_AND_QUEUE_DECLARED                OK  nenhuma fila
AI_ROLE_CONTROL_DECLARED                          OK
ROLE_AND_STEP_INSTRUCTION_DISTINGUISHED           OK
PIA_SEQUENCE_SUGGESTION_BEHAVIOR_DECLARED         NOT_APPLICABLE
MULTI_AI_RESULT_ATTRIBUTION_DECLARED              NOT_APPLICABLE_TO_RUNTIME
PIA_INTEGRATION_DIVERGENCE_PRESERVATION_DECLARED  OK
POST_RESULT_USER_COMMAND_DECLARED                 NOT_APPLICABLE  sem superfície
RESULT_APPROVAL_AND_PERSISTENCE_DISTINGUISHED     OK  diagnóstico != decisão
FROZEN_MODULES_UNCHANGED                          OK
```

### Multicanal v1.3 (10)

Nenhum canal entra nesta fronteira: a avaliação recebe observação
tipada, nunca comando. Os dez marcadores são preservados por ausência de
superfície de entrada — `NATURAL_LANGUAGE_NEVER_REACHES_THE_EVALUATOR`.

```text
MULTI_AI_HANDOFF_COMPATIBILITY = NOT_APPLICABLE_TO_RUNTIME
E4_INTEGRATION_OF_COUT_P = FORBIDDEN
COMPLIANCE_FINDING_PORTABLE = FALSE
```

### Parte III §13 — impacto sobre distinções

Nenhuma distinção é extinta. Os quatro desfechos não colapsam; a
severidade preserva três graus; política não aplicável, insuficiência e
violação permanecem irredutíveis entre si.

```text
DISTINCTION EXTINCTION != HISTORICAL ERASURE
FORGETTING      != INACCESSIBILITY
INACCESSIBILITY != LEGAL_ERASURE
RETENTION       != DELETION_AUTHORITY
```

## 8. Riscos declarados

- **(a)** `COMPLIANT` vale para **uma** versão de **uma** política, no
  instante avaliado — nunca "o patrimônio está em ordem".
- **(b)** A observação é **fornecida**, não verificada: quem afirma que
  a operação foi executada é o chamador, e a fronteira confia nessa
  afirmação como confia num argumento tipado.
- **(c)** `COMPLIANCE-GOV-002` depende de as regras da versão avaliada
  serem completas; uma política deliberadamente parcial produzirá
  findings que refletem a política, não o patrimônio.
- **(d)** A conversão de regras persistidas em regras tipadas pertence a
  quem lê. Um chamador que a faça errado avaliará contra regras que a
  política não tem.
- **(e)** Não há enumeração de patrimônio: a fronteira responde sobre
  **um** sujeito quando alguém pergunta.
- **(f)** Ausência de achado adicional não é prova de ausência de
  defeito.

## 9. O que continua não existindo

```text
COMPLIANCE_CONSUMER = NONE
POLICY_ENUMERATOR = NONE
PATRIMONY_SCANNER = NONE
PUBLIC_API = NONE
SCHEDULER = NONE
QUEUE = NONE
REPAIR_ENGINE = NONE
LEARNING_ENGINE = NONE
```

A E4.10 entrega a fronteira. Quem a consome, com que periodicidade e
sobre qual recorte de patrimônio é decisão posterior e não foi tomada
aqui.

`PASS_FINAL` pertence à auditoria independente e não é declarado neste
documento.
