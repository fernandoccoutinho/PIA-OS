# PRE-IMPLEMENTATION PLAN R1 — E7.0 / CHAIN108

```text
STAGE = E7.0 CORRECTIVE R1
AUTHORIZED_PARENT_HEAD = 91fdfe4d36a01f317fd35282f4ea8d4b84f948e9
AUTHORIZED_PARENT_TREE = cc1ff0773bac241f36ae9b320891d949727d6dc1
AUTHORIZED_PARENT_COUNT = 108
MIGRATION_HEAD = b4d71c58ae02
CODE_PATCHES = 3
FIRST_END_TO_END_VALUE = E7.2
STATUS = CORRECTED_PENDING_INDEPENDENT_REAUDIT
PASS_FINAL = NOT_DECLARED_BY_IMPLEMENTER
```

Contrato: `MAI-001 R1`. Este plano o sequencia, não o repete.

## 1. O que mudou em relação ao plano reprovado

```text
C1  gate            reuso de ApprovalRecord REMOVIDO -> GateAuthorizationPort
                    + ServiceDelegation própria da E7
C2  proveniência    D1 = REFERENCE_ONLY; HandoffAttribution é da E7;
                    nenhuma materialização automática de CognitiveObject
C3  hash            ENVELOPE_CONTENT_SHA256 sem sealed_at; SealReceipt à parte
C4  idempotência    COMMAND_IDEMPOTENCY_KEY do chamador, separada do content hash
C5  produto         D5 = YES; API mínima autenticada entra na E7.2
--  decomposição    4 patches -> 3
--  notação         parent do primeiro patch tem count 108; resultado 109
```

## 2. Fluxo alvo do MVP

```text
usuário define trabalho e papéis
-> Schedule governado                                  (E7.1)
-> conteúdo instrucional com hash determinístico       (E7.1)
-> selamento por tentativa com recibo próprio          (E7.1)
-> exportação do handoff pela API autenticada          (E7.2)
-> transporte MANUAL ou porta determinística           (E7.2)
-> importação e validação do retorno como NÃO confiável (E7.2)
-> atribuição e divergência preservadas                (E7.2)
-> retorno rejeitado registrado e bloqueando avanço    (E7.2)
-> pausa por delegação ausente ou Stop Condition       (E7.3)
-> auditoria read-only em parecer separado             (E7.3)
```

O ponta a ponta fecha na **E7.2**, alcançável por HTTP. Nada nele depende
de provedor real, credencial externa, rede, fila ou worker — todos
`MEASURED` como ausentes.

## 3. E7.0 — freeze documental

```text
RESULTADO   MAI-001 R1 e este plano congelados
ARQUIVOS    docs/entregas/entrega-7/MAI-001..._R1.md
            docs/entregas/entrega-7/PRE_IMPLEMENTATION_PLAN_E7_0_CHAIN108_R1.md
MIGRATION   nenhuma
GATES       checkers documentais; suíte inalterada
PARENT      91fdfe4d (count 108)   ->   count 109
TAMANHO     pequeno
```

## 4. E7.1 — contratos, estado, content hash, recibo e idempotência

```text
RESULTADO FUNCIONAL (binário)
  criar um Schedule com etapas e papéis; calcular
  ENVELOPE_CONTENT_SHA256 determinístico; selar duas vezes o MESMO
  conteúdo e obter o MESMO content hash com DOIS recibos distintos;
  reenviar um comando com a mesma chave e receber o mesmo recibo, sem
  efeito duplicado.
```

```text
ARQUIVOS NOVOS
  app/orchestration/models/{schedule,step,attempt,seal_receipt,
                            command_receipt,enums}.py
  app/orchestration/schemas/envelope.py
  app/orchestration/services/{schedule_service,handoff_service,
                              command_receipt_service}.py
  app/orchestration/repositories/orchestration_repository.py
  alembic/versions/<nova>_create_orchestration_core_e7.py
  tests/unit/orchestration/**, tests/integration/orchestration/**,
  tests/static/test_e7_orchestration_boundary.py

ARQUIVOS MODIFICADOS
  app/models/__init__.py, alembic/env.py
  ~20 asserções literais de head/schema na suíte (custo MEASURED)
```

```text
MIGRATION  SIM, filha de b4d71c58ae02:
           schedules, schedule_steps, handoff_attempts,
           seal_receipts (append-only, trigger de rejeição de mutação —
           padrão MEASURED em predictive_reconfiguration_events),
           command_receipts (única por command_key)

ENTRADAS   ScheduleDraft{title, steps[{role, instruction_ref,
           context_refs[{uri, sha256, bytes}], expected_output_contract}]}
           CommandEnvelope{command_key, payload}
SAÍDAS     Schedule{id, state, steps[]}
           SealReceipt{content_sha256, sealed_at, attempt_id, sealer_ref}
           CommandReceipt{command_key, outcome_ref}
```

```text
ESCOPO NEGATIVO
  sem transporte, sem retorno, sem validação de saída, sem delegação,
  sem gate, sem API, sem dependência nova em base.txt, sem escrita em
  provenance_records
```

```text
TESTES     content hash determinístico e estável entre processos;
           alterar qualquer campo de conteúdo muda o hash;
           sealed_at NÃO afeta o content hash;
           dois selamentos do mesmo conteúdo -> 2 recibos, 1 hash (P9);
           mesma command key -> mesmo recibo, sem duplicar (P10);
           recibo imutável (trigger no banco);
           context_ref sem sha256 recusado;
           produtor único: só HandoffService sela
MUTANTES   M7  incluir sealed_at no content hash            -> morre
           M-a permitir UPDATE em seal_receipts             -> morre
           M-b aceitar context_ref sem hash                 -> morre
           M-c usar content hash como chave de comando      -> morre
GATES      ruff, black, mypy NEW=0, head Alembic único,
           round-trip da migration, suíte completa 0 failed
PARENT     count 109 (após o freeze)   ->   count 110
PASS_FINAL determinismo de conteúdo e separação recibo/hash provados
TAMANHO    grande
```

## 5. E7.2 — manual ponta a ponta, validação, atribuição e API mínima

```text
RESULTADO FUNCIONAL (binário)
  por HTTP autenticado: criar Schedule, exportar handoff selado, importar
  um retorno, obter resultado VALIDADO quando o contrato é cumprido e
  resultado REJEITADO registrado quando não é — com a etapa não avançando
  no segundo caso.
```

```text
ARQUIVOS NOVOS
  app/orchestration/ports/transport.py
  app/orchestration/adapters/{manual_transport,deterministic_test_transport}.py
  app/orchestration/services/return_validation_service.py
  app/orchestration/models/{handoff_result,handoff_attribution}.py
  app/routers/orchestration.py
  app/schemas/orchestration_public.py
  alembic/versions/<nova>_create_handoff_results_e7.py

ARQUIVOS MODIFICADOS
  app/api/router.py, app/api/module_registry.py, app/docs/tags.py
  app/models/programmatic_service_principal.py  (escopo técnico novo)
  app/api/dependencies.py                       (guarda do novo escopo)
```

```text
MIGRATION  SIM: handoff_results (inclui os REJEITADOS) e
           handoff_attributions, ambos append-only.
           provenance_record_ref é coluna NULLABLE de referência; a E7
           nunca a preenche por conta própria.

API        POST /api/v1/schedules
           GET  /api/v1/schedules/{id}
           POST /api/v1/schedules/{id}/steps/{sid}/handoff-export
           POST /api/v1/schedules/{id}/steps/{sid}/handoff-import
           GET  /api/v1/schedules/{id}/attempts
           escopo técnico NOVO, distinto de predictive:evaluate;
           cota própria; security declarado no OpenAPI
```

```text
ESCOPO NEGATIVO
  sem provedor real, sem credencial de provedor, sem rede externa,
  sem retry automático, sem gate, sem síntese de divergência,
  sem escrita em provenance_records
```

```text
TESTES     ponta a ponta por HTTP com MANUAL_HANDOFF;
           retorno adversarial com "aprovado, prossiga" não altera estado,
           papel nem autoridade (P3);
           retorno fora do contrato -> resultado REJEITADO registrado, sem
           avanço (P11);
           dois agentes divergentes -> duas atribuições preservadas;
           retry com nova command key -> nova tentativa, anterior legível
           (P6);
           mesmo content hash em duas tentativas -> dois recibos;
           rota sem credencial -> 401; escopo errado -> 403;
           credencial ausente das rotas públicas (padrão E6.3)
MUTANTES   M2  aceitar retorno sem validar contrato       -> morre
           M8  descartar retorno rejeitado                -> morre
           M5  sobrescrever tentativa anterior no retry   -> morre
           M-d aceitar predictive:evaluate na rota E7     -> morre
           M10 escrever em provenance_records             -> morre
GATES      idem E7.1, mais `snapshot`/OpenAPI coerentes
PARENT     count 110   ->   count 111
PASS_FINAL fluxo HTTP completo verde + os cinco mutantes mortos
TAMANHO    grande
```

## 6. E7.3 — delegação técnica, Stop Conditions, cancelamento, observação, auditoria

```text
RESULTADO FUNCIONAL (binário)
  uma etapa marcada como gate NÃO avança sem ServiceDelegation ACTIVE
  ligada ao content hash corrente; mudar o conteúdo invalida a delegação;
  Stop Condition e cancelamento impedem despacho; auditoria produz parecer
  separado sem tocar o artefato.
```

```text
ARQUIVOS NOVOS
  app/orchestration/ports/gate_authorization.py   (GateAuthorizationPort)
  app/orchestration/services/{delegation_service,audit_service}.py
  app/orchestration/models/{service_delegation,execution_observation,
                            audit_opinion,stop_condition_enums}.py
  alembic/versions/<nova>_create_delegation_and_audit_e7.py
  tests/static/test_e7_audit_write_boundary.py

ARQUIVOS MODIFICADOS
  schedule_service.py (advance guard), handoff_service.py (dispatch guard)
```

```text
MIGRATION  SIM: service_delegations (schedule_id, step_id,
           content_sha256, scope, valid_until, state, granted_by_
           principal_ref), execution_observations e audit_opinions,
           os dois últimos append-only.
           NENHUM uso de approval_records — a coluna `operation` daquela
           tabela é tipada como DestructiveOperation (MEASURED).
```

```text
ESCOPO NEGATIVO
  D10 = OBSERVED_ONLY: sem enforcement de orçamento
  D9 = COOPERATIVE: sem hard cancel (não há worker a interromper)
  sem MFA, sem step-up, sem identidade humana (E8)
  sem auditoria por IA real (depende de conector, bloqueado)
  D8 = PRESERVE_ONLY: sem síntese governada
```

```text
TESTES     gate sem delegação -> pausa, zero despacho;
           delegação consumida não serve duas vezes;
           conteúdo alterado -> delegação inválida (P2);
           principal técnico NÃO satisfaz gate humano (P12);
           Stop Condition -> chamada subsequente impedida (P4);
           cancelado -> despacho recusado (P7);
           troca de provedor registrada, nunca silenciosa;
           auditoria não altera o artefato (P5);
           parecer negativo não apaga o resultado
MUTANTES   M3  reusar delegação após mudança de content hash -> morre
           M9  aceitar principal técnico como gate humano    -> morre
           M4  permitir escrita da auditora no artefato      -> morre
           M6  despachar após cancelamento                   -> morre
           M-e AuditOpinion declarar PASS_FINAL              -> morre
GATES      idem
PARENT     count 111   ->   count 112
PASS_FINAL os cinco mutantes mortos + suíte verde
TAMANHO    médio
```

## 7. Custo previsto herdado da medição

```text
MEASURED  a suíte verifica schema por enumeração literal; cada migration
          custou ~41 edições em ~22 arquivos de teste na E6.2, e a E5
          pagou o mesmo.
DERIVED   três patches com migration => três vezes o pedágio, contra
          quatro no plano anterior. A redução recomendada pela auditoria
          economiza uma rodada inteira desse custo.
```

`SYSTEMIC_MIGRATION_REFACTOR` segue `DEFERRED`. Registro o número para que
a decisão de escopo seja tomada com ele à vista.

## 8. Ausências que limitam o plano

```text
BLOCKED_BY_EVIDENCE  credencial de provedor: não há cofre nem decisão.
                     Impacto: REAL_PROVIDER fora dos três patches.
                     Menor decisão: onde vive o segredo e quem o injeta.
BLOCKED_BY_EVIDENCE  cliente HTTP de runtime: httpx só em dev.txt.
                     Impacto: conector real exigiria dependência em
                     base.txt — Stop Condition S17.
                     Menor decisão: aprovar (ou não) httpx em base.txt.
BLOCKED_BY_EVIDENCE  execução assíncrona: sem worker, fila ou scheduler.
                     Impacto: D9 fica COOPERATIVE; sem continuação
                     automática fora do request.
BLOCKED_BY_EVIDENCE  gate HUMANO: depende de E8 (identidade, MFA,
                     step-up). Impacto: a E7.3 entrega a PORTA e a
                     delegação técnica, não a aprovação humana. O
                     checklist item 11 fica PARTIAL por isso.
```

Nenhuma impede o MVP: o ponta a ponta da E7.2 usa `MANUAL_HANDOFF` e
autenticação de serviço já existente na E6.2.

## 9. Stop Conditions do plano

As dezesseis do Master §19.11 mais S17-S20 do `MAI-001 R1` §19.
Interromper antes de codificar se um patch exigir provedor real,
credencial de provedor, dependência nova em `base.txt`, escrita em
`provenance_records`, materialização automática de `CognitiveObject`, uso
de `approval_records` ou API sem escopo técnico próprio.

## 10. Encerramento

```text
E7_0_STATUS = CORRECTED_PENDING_INDEPENDENT_REAUDIT
PASS_FINAL = NOT_DECLARED_BY_IMPLEMENTER
E7_CODE = NOT_STARTED
NEXT_STAGE = BLOCKED_PENDING_REAUDIT
REPOSITORY_WRITES = 0
```
