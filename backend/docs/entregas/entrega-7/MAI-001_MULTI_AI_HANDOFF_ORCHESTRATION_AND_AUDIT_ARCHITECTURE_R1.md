# MAI-001 R1 — Arquitetura de Handoff, Orquestração e Auditoria Multi-IA

```text
STAGE = E7.0 CORRECTIVE R1
BASE_HEAD = 91fdfe4d36a01f317fd35282f4ea8d4b84f948e9
BASE_TREE = cc1ff0773bac241f36ae9b320891d949727d6dc1
BASE_COUNT = 108
MIGRATION_HEAD = b4d71c58ae02
STATUS = CORRECTED_PENDING_INDEPENDENT_REAUDIT
PASS_FINAL = NOT_DECLARED_BY_IMPLEMENTER
```

Selos: `MEASURED`, `DERIVED`, `PROPOSED`, `BLOCKED_BY_EVIDENCE`. As
medições aceitas pela auditoria são preservadas sem repetição; duas foram
acrescentadas por serem a base factual de B1 e B2.

## 0. Medições preservadas e as duas novas

```text
PRESERVADAS (aceitas pela auditoria)
MEASURED  Schedule/CognitiveExecution/Agent/Provider/Connector/Handoff/
          arbitragem/audit runtime: ausentes em app/**
MEASURED  22 tabelas; nenhuma modela trabalho, etapa, tentativa ou repasse
MEASURED  ProvenanceRecord: 5 campos multiagente nullable sem escritor;
          separa provider_id, model_id, session_id, actor_type
MEASURED  Envelopes: PiapEnvelope (E5), DestructiveApprovalEnvelope (E4.9);
          AIHandoffEnvelope não existe
MEASURED  append-only com trigger de rejeição em 4 tabelas
MEASURED  httpx só em dev.txt; sem celery/rq/arq/kafka/redis/apscheduler
MEASURED  zero idempotency, zero cancel, zero advisory lock
MEASURED  6 rotas HTTP, 1 autenticada; 68 schemas
MEASURED  tetos: 8 claims, 512 refs, pool_timeout 30; sem teto de bytes,
          timeout externo ou concorrência
MEASURED  credencial E6.2 = digest HMAC, rótulo próprio, escopo fechado

NOVAS — base factual dos bloqueadores
MEASURED  approval_record.py:129  operation: Mapped[DestructiveOperation]
          -> não existe aprovação genérica na E4.9 (base de B1)
MEASURED  provenance_manager.py:40  def record(*, coid: uuid.UUID, ...)
          -> proveniência E3 exige CognitiveObject materializado (base de B2)
```

## 1. Fronteira e ownership

```text
PROPOSED
E7_OWNS  trabalho, etapa, tentativa, repasse, resultado, modo de execução,
         delegação técnica, atribuição de handoff, divergência
E7_USES  erros PIA (E1), principal técnico (E6.2)
E7_NEVER ciência (E5), DTO público (E6.1), identidade e aprovação humanas
         (E8), efeito externo (E9), aprovação destrutiva (E4.9)
```

A E7 orquestra e registra: não avalia, não aprova, não age no mundo.

## 2. Vocabulário — oito coisas distintas

```text
PROPOSED
função   papel no trabalho; não é quem executa
agente   instância que ocupa a função numa execução; identidade por tentativa
provedor organização | produto superfície | modelo artefato versionado
conta    relação comercial/credencial | sessão continuidade de contexto
ferramenta capacidade invocável
autoridade permissão de progressão — NÃO é atributo de nenhum dos sete
```

```text
DERIVED  ProvenanceRecord já separa provider_id, model_id, session_id e
         agent_role. A E7 herda a distinção como vocabulário, sem
         escrever naquela tabela (ver §9).
```

Colapsar qualquer par é Stop Condition (Master §19.11). O par perigoso é
`agente`+`autoridade`: um agente que "concorda" não autoriza nada.

## 3. `AIHandoffEnvelope` — conteúdo e recibo separados (C3)

A versão anterior punha `sealed_at` dentro do hash e prometia
determinismo por conteúdo. Contraditório: dois selamentos do mesmo
conteúdo em instantes distintos nunca dariam o mesmo hash.

```text
PROPOSED
ENVELOPE_CONTENT = {envelope_version, schedule_id, step_id, role,
  instruction_ref, context_refs[{uri, sha256, bytes}],
  expected_output_contract, constraints}
ENVELOPE_CONTENT_SHA256 = sha256(json canônico de ENVELOPE_CONTENT)
SEAL_RECEIPT = {content_sha256, sealed_at, attempt_id, sealer_ref}

SEALED_AT_IN_CONTENT_HASH = FALSE   CONTENT_DETERMINISM = TRUE
SAME_CONTENT + MULTIPLE_ATTEMPTS -> mesmo hash, recibos distintos
CONTENT_CHANGED -> hash distinto
```

Não reutilizo `PiapEnvelope`: ele transporta autoridade de aprovação
científica; este transporta instrução de trabalho. Fundi-los faria um
repasse aceito valer como aprovação PIAP.

```text
CONTENT_HASH_CHANGED -> PREVIOUS_DELEGATION_INVALID
```

## 4. Composição × modo de execução

```text
PROPOSED
COMPOSITION = o que fazer, em que ordem, com quais papéis
EXECUTION_MODE = como o repasse atravessa a fronteira
COMPOSITION_CHANGE != EXECUTION_MODE_CHANGE
```

Eixos independentes: o mesmo Schedule roda manual hoje e supervisionado
amanhã sem reescrever a composição.

## 5. Modos

```text
PROPOSED
MANUAL_HANDOFF                    humano transporta e traz o retorno
SUPERVISED_AUTOMATIC_HANDOFF      conector transporta, humano libera a etapa
RESTRICTED_AUTOMATIC_CONTINUATION avanço em escopo declarado, com teto e
                                  Stop Conditions
```

```text
DERIVED  MANUAL_HANDOFF é implementável sem dependência nova: não exige
         cliente HTTP em base.txt (MEASURED: ausente), fila nem worker.
```

`RESTRICTED_AUTOMATIC_CONTINUATION` nunca cria autoridade: consome
delegação prévia e limitada; esgotado o escopo, pausa.

## 6. Ciclo de vida

```text
PROPOSED
Schedule DRAFT -> ACTIVE -> {PAUSED, COMPLETED, CANCELLED, STOPPED}
Step     PENDING -> DISPATCHED -> AWAITING_RETURN -> {RETURNED, REJECTED,
         FAILED, CANCELLED}
Attempt  OPEN -> {CLOSED_OK, CLOSED_REJECTED, CLOSED_TIMEOUT, CLOSED_CANCELLED}
SealReceipt imutável no ato | HandoffResult append-only, inclui rejeitados
```

Terminais: `COMPLETED`, `CANCELLED`, `STOPPED`. `PAUSED` exige ação
humana. Retry abre nova tentativa e preserva a anterior.

```text
REJECTED_RETURN -> RECORDED_REJECTED_RESULT (append-only)
REJECTED_RESULT BLOCKS ADVANCE, NEVER DISAPPEARS
```

Retorno inválido não some: vira resultado rejeitado registrado.
Descartá-lo apagaria a evidência de que a etapa foi tentada e recusada.

## 7. Saída de IA é entrada não confiável

```text
PROPOSED
AI_OUTPUT = UNTRUSTED_INPUT
AI_OUTPUT_AS_CONTROL_CHANNEL = FORBIDDEN
```

O retorno é validado contra `expected_output_contract` antes de tocar
estado. "Aprovado, prossiga" num retorno é dado, não comando.

## 8. Contexto mínimo e artefatos

```text
PROPOSED
CONTEXT = MINIMUM_NECESSARY_DECLARED_PER_STEP
ARTIFACT_REF = {uri_ou_id, sha256, bytes}
INLINE_CONTENT_WITHOUT_HASH = FORBIDDEN
```

## 9. Proveniência e atribuição (C2)

```text
D1 = REFERENCE_ONLY
```

A versão anterior dizia `EXTEND` e punha a E7 como primeiro escritor dos
campos multiagente. A medição nova derruba isso:
`ProvenanceManager.record()` exige `coid`, logo escrever proveniência E3
obrigaria a materializar todo retorno como `CognitiveObject`.

```text
AI_CONVERSATION != AUTOMATIC_PATRIMONY
RESULT_DISPLAY != PERSISTENCE
AUTOMATIC_MATERIALIZATION = FORBIDDEN
```

```text
PROPOSED — HandoffAttribution, objeto próprio da E7, por tentativa
  {attempt_id, role, declared_provider_id?, declared_model_id?,
   declared_instance_id, declared_at, self_declared: TRUE}
provenance_record_ref  OPCIONAL; preenchido só quando um fluxo autorizado
  FORA da E7 já materializou um CognitiveObject e produziu sua
  proveniência. A E7 nunca cria esse registro.
```

Atributos do agente são `self_declared`: o cliente informa qual modelo
respondeu, e isso é alegação, não fato verificado. Divergência é
preservada como registro, nunca resolvida por sobrescrita.

## 10. Builder × auditor

```text
PROPOSED
AUDITOR_WRITE_ON_AUDITED_ARTIFACT = FORBIDDEN
AUDITOR_OUTPUT = parecer separado, append-only
SELF_CRITIQUE != INDEPENDENT_AUDIT
```

## 11. Autoridade e delegação técnica (C1)

A versão anterior propunha reusar `ApprovalRecord` da E4.9. Sua coluna
`operation` é tipada como `DestructiveOperation`: consumi-la num gate E7
exigiria declarar que progressão multi-IA é apagamento destrutivo.

```text
PROPOSED
GateAuthorizationPort — porta; a E7 não implementa autoridade humana
ServiceDelegation (objeto próprio da E7):
  {delegation_id, schedule_id, step_id, content_sha256, scope,
   valid_until, state: ACTIVE|CONSUMED|REVOKED|EXPIRED,
   granted_by_principal_ref}

SERVICE_DELEGATION != HUMAN_APPROVAL
TECHNICAL_PRINCIPAL != HUMAN_IDENTITY
SUGGESTION_NEVER_AUTHORIZES_PROGRESSION | AI_SELF_PASS_FINAL = FORBIDDEN
```

Limitada por schedule, step, `content_sha256`, escopo, validade e consumo
único. Ligada ao content hash, morre quando o conteúdo muda.

```text
CONTENT_HASH_CHANGED -> DELEGATION_INVALID
```

Nenhum teste pode chamar isso de aprovação do usuário quando a fonte é
principal técnico. A implementação humana com MFA e step-up é E8, plugável
na mesma porta.

## 12. Conectores

```text
D4 = PORT_ONLY -> DETERMINISTIC_TEST
PROVIDER_NEUTRAL = TRUE
MANUAL_IS_A_LEGITIMATE_TRANSPORT = TRUE
```

```text
MEASURED  não há cliente HTTP em base.txt; adicioná-lo é decisão de
          dependência de runtime.
DERIVED   provider real no patch 1 exigiria dependência + credencial +
          rede: três riscos antes do primeiro teste de valor.
```

## 13. Credenciais

```text
PROPOSED
PROVIDER_CREDENTIAL NOT IN {envelope, prompt, log, persistência comum}
CREDENTIAL_SHARING_BETWEEN_PROVIDERS = FORBIDDEN
E6_2_SERVICE_CREDENTIAL != PROVIDER_CREDENTIAL
DERIVED   a credencial E6.2 não serve a provedores: o rótulo a liga a um
          propósito e o escopo não inclui repasse.
BLOCKED_BY_EVIDENCE  sem cofre nem decisão para credencial de provedor.
          Impacto: bloqueia REAL_PROVIDER. Menor decisão do arquiteto:
          onde vive o segredo e quem o injeta.
```

## 14. Custo, cota, timeout, concorrência

```text
D10 = OBSERVED_ONLY
MEASURED  sem teto de bytes, timeout externo ou limite de concorrência; a
          cota existente é por principal E6.2.
DERIVED   ENFORCED exigiria contadores e autoridade de orçamento;
          observar primeiro produz o dado que define o teto.
PROPOSED  NO_SILENT_PROVIDER_SWITCH — troca sempre registrada.
```

## 15. Persistência e idempotência de comando (C4)

```text
D3 = REQUIRED_NOW
```

A versão anterior usava `(schedule_id, step_id, content_sha256)` como
chave de idempotência e exigia que retry criasse tentativa nova. A mesma
tripla não distingue reenvio acidental de retry legítimo.

```text
PROPOSED
COMMAND_IDEMPOTENCY_KEY = do chamador, única no escopo da operação
SAME_COMMAND_KEY -> SAME_RECEIPT, NO_DUPLICATE_EFFECT
RETRY -> NEW_COMMAND_KEY -> NEW_ATTEMPT
SAME_CONTENT_SHA256 MAY_HAVE MULTIPLE_ATTEMPTS
```

Separar identidade de comando de identidade de conteúdo dá as duas
garantias juntas: reenvio não duplica, e repetir a mesma instrução é
tentativa nova e legítima.

## 16. Cancelamento

```text
D9 = COOPERATIVE
```

```text
MEASURED  não há worker nem fila; não existe execução a interromper fora
          do request.
PROPOSED  CANCELLED_STATE -> NO_SUBSEQUENT_DISPATCH.
```

## 17. Observabilidade e isolamento

```text
PROPOSED
LOG_CONTAINS = ids, estados, hashes, durações, contadores
LOG_NEVER_CONTAINS = prompt, resposta, segredo, contexto
TRANSCRIPT_PERSISTENCE = OPT_IN_EXPLICIT
Schedule 1..N Step 1..N Attempt 1..N SealReceipt 1..1 Result
CROSS_SCHEDULE_STATE_SHARING = FORBIDDEN
```


Toda consulta é escopada por `schedule_id`.
## 18. Fronteira com E6, E8, E9 (C5)

```text
D5 = YES (no patch E7.2)
D6 = NOT_REQUIRED_FOR_SERVICE_FLOW
```

A versão anterior deixava o MVP alcançável só por chamada Python interna.
Depois de a E6 criar superfície programática, isso voltaria a acumular
núcleo sem produto acessível — o padrão que a E4 já produziu.

```text
PROPOSED — API mínima, escopo técnico NOVO (não predictive:evaluate)
POST /api/v1/schedules                          criar
GET  /api/v1/schedules/{id}                     estado
POST /api/v1/schedules/{id}/steps/{sid}/handoff-export   selar e exportar
POST /api/v1/schedules/{id}/steps/{sid}/handoff-import   importar retorno
GET  /api/v1/schedules/{id}/attempts            tentativas e resultados

TECHNICAL_PRINCIPAL_AUTHORIZES_HTTP_CALL = TRUE
TECHNICAL_PRINCIPAL_SATISFIES_HUMAN_GATE = FALSE
TECHNICAL_PRINCIPAL_EXCEEDS_EFFECTIVE_DELEGATION = FALSE
```

Padrão E6.2: escopo próprio, cota própria, `security` no OpenAPI,
credencial nunca em rota pública.

## 19. Stop Conditions

As dezesseis do Master §19.11, mais quatro derivadas da medição:

```text
PROPOSED
S17  dependência nova em backend/requirements/base.txt sem decisão
S18  escrever em provenance_records a partir da E7
S19  segundo vocabulário de agente divergente do E3
S20  materializar retorno como CognitiveObject automaticamente
```

## 20. Provas e mutantes obrigatórios

```text
PROPOSED — provas
P1 envelope chega sem ampliação | P2 conteúdo alterado invalida delegação
P3 output adversarial não altera Schedule/ferramenta/autoridade
P4 Stop Condition impede chamada seguinte | P5 auditoria não modifica artefato
P6 retry cria tentativa nova e preserva a anterior
P7 cancelamento impede despacho | P8 credencial fora de envelope/log/persistência
P9 mesmo content hash, duas tentativas -> dois recibos
P10 mesma command key -> mesmo recibo, sem duplicar
P11 retorno rejeitado registrado e bloqueando avanço
P12 principal técnico não satisfaz gate

PROPOSED — mutantes (todos devem morrer)
M1 ampliar contexto | M2 aceitar retorno sem validar contrato
M3 reusar delegação após mudança de content hash
M4 escrita da auditora no artefato | M5 sobrescrever tentativa no retry
M6 despachar após cancelamento | M7 incluir sealed_at no content hash
M8 descartar retorno rejeitado | M9 principal técnico como gate humano
M10 escrever em provenance_records a partir da E7
```

Regra herdada da E6.2/E6.3: mutante executado em cópia isolada,
`baseline exit 0 -> mutante exit != 0`. Guarda de ausência de símbolo é
`CHARACTERIZATION`, fora da contagem.

## 21. Grafo produtor→consumidor

Todo objeto tem produtor único; nenhuma referência sem produtor.

```text
PROPOSED — produtor único por objeto
ScheduleService     -> Schedule, Step
HandoffService      -> ENVELOPE_CONTENT, SealReceipt, Attempt
ReturnValidationSvc -> HandoffResult (ok OU rejeitado), HandoffAttribution
DelegationService   -> ServiceDelegation
AuditService        -> AuditOpinion
CommandReceiptSvc   -> CommandReceipt
Transport(port)     -> RawReturn (transitório, não persistido)

Consumo
Step -> HandoffService | SealReceipt -> DelegationService
RawReturn -> ReturnValidationSvc
HandoffResult -> ScheduleService.advance(), AuditService
ServiceDelegation -> ScheduleService.advance()
CommandReceipt -> API (resposta idempotente)

Referência sem produção pela E7
ProvenanceRecord --REFERENCED_ONLY_IF_EXISTS--> HandoffAttribution
  produtor: fluxo cognitivo E3, externo à E7. A E7 nunca o produz.
```

Arestas de impedimento, ligando X ao decisor de Y:

```text
StopCondition        --lida por--> ScheduleService.advance() --impede--> dispatch
CancelledState       --lida por--> HandoffService.dispatch() --impede--> envio
ContentHashMismatch  --lido por--> DelegationService --invalida--> ServiceDelegation
ContractViolation    --lida por--> ReturnValidationSvc --produz--> resultado
                                   rejeitado --impede--> advance
MissingDelegation    --lida por--> ScheduleService.advance() --impede--> avanço
```

**Regra temporal (equivalente a R10-9):**

```text
NO_COMPOSITE_DEPENDS_ON_DOWNSTREAM_COMPONENT
```

`ENVELOPE_CONTENT` não pode conter campo produzido no ato do selamento —
por isso `sealed_at` e `attempt_id` vivem no `SealReceipt`, a jusante.
`HandoffResult` não pode conter campo de `AuditService`. Verificável pela
ordem topológica acima.

## 22. Checklist `MULTI_AI_HANDOFF_COMPATIBILITY` (Master §19.10)

Nada aqui existe em código. `PLANNED` = desenhado e alocado a um patch;
`PARTIAL` = desenho cobre parte do item. Nenhuma linha é `PASS`: isso
pertence à auditoria de código.

| # | linha | estado | materializado por |
|---|---|---|---|
| 1 | HANDOFF_MODE_DECLARED | PLANNED | §5; enum `HandoffMode`, E7.1 |
| 2 | SCHEDULE_COMPOSITION_AND_EXECUTION_MODE_DISTINGUISHED | PLANNED | §4; eixos separados, E7.1 |
| 3 | ROLE_PROVIDER_MODEL_ACCOUNT_DISTINGUISHED | PLANNED | §2/§9; `HandoffAttribution`, E7.2 |
| 4 | HANDOFF_ENVELOPE_AND_VERSION_DECLARED | PLANNED | §3; content hash + SealReceipt, E7.1, provas P1/P9/M7 |
| 5 | MINIMUM_NECESSARY_CONTEXT_DECLARED | PLANNED | §8; `context_refs`, E7.1, mutante M1 |
| 6 | ARTIFACT_IDENTITY_HASH_AND_PROVENANCE_DECLARED | PLANNED | §8/§9; `{uri, sha256, bytes}`, E7.1 |
| 7 | AI_OUTPUT_TREATED_AS_UNTRUSTED | PLANNED | §7; ReturnValidationSvc, E7.2, prova P3 |
| 8 | VALIDATION_AND_INDEPENDENT_AUDIT_DISTINGUISHED | PLANNED | §10; serviços distintos, E7.3 |
| 9 | BUILDER_AUDITOR_WRITE_BOUNDARY_DECLARED | PLANNED | §10; AuditOpinion separado, E7.3, P5/M4 |
| 10 | AUTOMATIC_ADVANCE_SCOPE_DECLARED | PLANNED | §5/§11; escopo da delegação, E7.3 |
| 11 | USER_GATES_AND_OVERRIDE_DECLARED | **PARTIAL** | §11; `GateAuthorizationPort` + delegação técnica em E7.3. O gate HUMANO depende de E8 e não existe no MVP — declarar PLANNED aqui afirmaria capacidade que a E7 não entrega |
| 12 | STOP_AND_PAUSE_CONDITIONS_DECLARED | PLANNED | §19; aresta StopCondition→advance(), E7.3, prova P4 |
| 13 | PROVIDER_SWITCH_COST_AND_QUOTA_DECLARED | **PARTIAL** | §14; registro e observação em E7.3. Enforcement não: `D10 = OBSERVED_ONLY`, sem teto medido a impor |
| 14 | SECRET_CREDENTIAL_AND_PRIVACY_BOUNDARY_DECLARED | PLANNED | §13; prova P8, E7.1-E7.3 |
| 15 | PERSISTENCE_AND_RETENTION_BEHAVIOR_DECLARED | PLANNED | §15; migration da E7.1 |
| 16 | DIVERGENCE_AND_ATTRIBUTION_PRESERVED | PLANNED | §9; append-only, E7.2, P6/M5 |
| 17 | CURRENT_CAPABILITY_NOT_OVERSTATED | PLANNED | §0/§12; `D4 = PORT_ONLY` e `D1 = REFERENCE_ONLY` declaram o que não existe |

Transversais: entrada (§0.4) por D5/D6; operação remota aplicável com
`D5 = YES`, seguindo E6.2; distribuição e Mobile não aplicáveis.

## 23. Decisões literais

```text
D1  ProvenanceRecord           REFERENCE_ONLY      (corrigido: era EXTEND)
D2  primeiro modo executável   MANUAL
D3  persistência inicial       REQUIRED_NOW
D4  primeiro conector          PORT_ONLY -> DETERMINISTIC_TEST
D5  API E7 no MVP              YES (E7.2)          (corrigido: era NO)
D6  identidade humana E8       NOT_REQUIRED_FOR_SERVICE_FLOW
D7  auditoria independente     CONTRACT_AND_READ_ONLY_BOUNDARY
D8  arbitragem                 PRESERVE_ONLY
D9  cancelamento               COOPERATIVE
D10 orçamento                  OBSERVED_ONLY
```

D7 e D8 seguem conservadoras: `RUNTIME_NOW` depende de conector real,
bloqueado por credencial; `GOVERNED_SYNTHESIS` exigiria uma autoridade que
decide qual divergência vence — por código, viraria arbitragem silenciosa.

```text
E7_CODE = NOT_STARTED
NEXT_STAGE = BLOCKED_PENDING_REAUDIT
```
