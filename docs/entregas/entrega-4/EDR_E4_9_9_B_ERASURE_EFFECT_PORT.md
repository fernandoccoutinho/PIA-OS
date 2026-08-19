# EDR E4.9.9.b — Fronteira de efeito destrutivo e resultado tipado

**Baseline:** cadeia 90 (`22b1ba56`). **Saída:** cadeia 91.

```text
REFERENCE           != RESOLVED_TARGET
RESOLUTION          != DELETION_AUTHORITY
APPROVAL            != CONSUMPTION
CONSUMPTION         != EFFECT
EFFECT              != ERASURE_RECORD
NO_MATERIAL_ATTEMPT -> NO_ERASURE_RECORD
```

```text
E4_9_9_B = COMPLETE_CANDIDATE
ERASURE_EFFECT_PORT = IMPLEMENTED
ERASURE_EFFECT_ADAPTER = NONE
OBSERVED_ATTEMPT_RESULT = IMPLEMENTED
ERASURE_RECORD_WRITER = NOT_COMPOSED
E4_9_9_C = NOT_STARTED
E4_9_READY = FALSE
PASS_FINAL = NOT_DECLARED
```

---

## 1. Correção material antes do código

O desenho inicial desta fatia previa uma matriz local traduzindo
`DestructiveOperation` para `capability.operation`, e estava **errado**.

Medido no repositório: `capability.operation` é **texto opaco do
provedor** — o valor real em uso é `"delete_object"` —, e não existe
contrato canônico que diga a que operação aprovada cada texto
corresponde.

```text
APPLICATION_LEVEL_CAPABILITY_OPERATION_MAPPING = FORBIDDEN
CAPABILITY_OPERATION_SEMANTICS = ADAPTER_BOUNDARY
```

O custo do erro é **assimétrico**: uma correspondência inventada poderia
deixar passar apagamento **definitivo** com capacidade que só autorizava
lixeira. Uma matriz que errasse para o outro lado apenas bloquearia
demais; esta erraria para o lado que destrói.

Quem conhece o provedor é o adaptador. É ele que confirma compatibilidade
e, **antes de qualquer efeito**, devolve `OPERATION_NOT_SUPPORTED` ou
`CAPABILITY_REFUSED_BEFORE_ATTEMPT`.

Provado em duas camadas: `u19` aceita **seis textos distintos** de
capacidade para as **duas** operações aprovadas — a fronteira não opina;
`u20` e `s11` provam por AST que `capability.operation` sequer é lido no
código executável, e `s99_1` demonstra que a guarda detecta a introdução
de uma tradução.

---

## 2. O que o request valida — e o que não valida

| Valida | Não valida |
|---|---|
| operação aprovada tipada | correspondência com `capability.operation` |
| `capability.verified is True` | — |
| tenant, workspace, principal contra o `ControlScope` | — |
| classe de conteúdo apagável | — |
| tipos e instantes timezone-aware | re-resolução do alvo |
| — | comparação com o snapshot aprovado |

As duas últimas são E4.9.9.d. Alegá-las aqui seria capacidade acima da
camada.

### 2.1 Achado sobre a camada que recusa

Medido durante os testes: `ErasureTargetDescriptor` **já** exige
`verified is True` desde a E4.9.7.4 — *"capacidade presumida é a forma
silenciosa do confused deputy"*. Logo, um descritor válido nunca chega à
fronteira com capacidade não verificada.

```text
UNVERIFIED_CAPABILITY = REJECTED_AT_DESCRIPTOR
```

A verificação permanece no request como **segunda camada**: se a E4.9.7
relaxar a exigência, a fronteira de efeito não herda o relaxamento em
silêncio. `u15` documenta qual camada recusa hoje, em vez de alegar uma
prova que a outra dá; `u48` alcança a segunda camada por subclasse
controlada — construção legítima, não bypass.

---

## 3. Quatro desfechos, três no enum

```text
NOT_STARTED | SUCCEEDED | FAILED | PARTIAL
```

`SUCCEEDED`, `FAILED` e `PARTIAL` vêm de `ErasureOutcome`, **fonte única**
desde a E4.9.5. Duplicá-los criaria duas verdades sobre o que foi
observado.

`NOT_STARTED` fica **fora** do enum de propósito: entrar ali o tornaria
elegível a recibo, e recibo descreve tentativa material.

```text
NOT_STARTED not in ErasureOutcome
NOT_STARTED -> NO_ERASURE_RECORD
```

### 3.1 `stage` é etiqueta derivada, nunca argumento

```text
DISJOINT_RESULT_TYPE = SOURCE_OF_TRUTH
STAGE = DERIVED_TAG_ONLY
```

`EffectAttemptStage` é `@property` constante em cada classe — fora de
`dataclasses.fields`, fora de `__init__`. Se fosse campo, seria possível
construir uma não-tentativa marcada como observada, e a etiqueta
competiria com o tipo pela verdade. `u06`–`u08` medem; `s10` fixa na AST;
`s99_2` demonstra que a guarda detecta a introdução do campo.

### 3.2 Vocabulário de não-tentativa

Quatro membros, e nenhum duplica etapa anterior:

```text
ADAPTER_UNAVAILABLE · OPERATION_NOT_SUPPORTED
CAPABILITY_REFUSED_BEFORE_ATTEMPT · PROVIDER_PRECONDITION_REFUSED
```

`TargetResolutionRefusalReason` e `ApprovalUsageRefusalReason` descrevem
etapas que já terminaram quando esta fronteira é alcançada — a requisição
só existe com descritor resolvido e evidência de consumo. Copiá-las
inflaria o enum e faria a fronteira parecer capaz de observar o que não
observa. `u02` prova a disjunção.

Sem `UNKNOWN`, `OTHER` ou `ERROR`: uma exceção inesperada **não** é
nenhum destes motivos.

```text
EXCEPTION != OBSERVED_OUTCOME
TIMEOUT   != PROOF_OF_NO_EFFECT
NO_FABRICATED_ERASURE_RECORD_FROM_EXCEPTION
```

### 3.3 Matriz outcome/failure

```text
completed_at >= attempted_at
SUCCEEDED         -> failure_code IS NONE
FAILED | PARTIAL  -> failure_code obrigatório e não vazio
```

Seis combinações medidas em `u25`, três impossíveis recusadas.

---

## 4. Evidência de consumo

```text
TYPED_CONSUMPTION_EVIDENCE != DATABASE_PROOF
```

Construir a instância **não** prova que o banco confirmou consumo. Mesma
disciplina de `VerifiedDeletionCapability.verified` e `IdentityEvidence`.

Nesta fatia **ninguém a produz**: `ApprovalRecordRepository` não é
importado, e `u12` mede isso no **código executável**, não na docstring.

Seis campos, e nada além — sem nonce, credencial, fator de autenticação,
token ou envelope completo. O adaptador precisa saber *que* houve consumo
e *sob qual escopo*, não reconstruir a aprovação.

---

## 5. Confidencialidade composta

O request contém o descritor, e o descritor contém `transient_locator`.

`ErasureEffectRequest.__repr__` **não delega** ao descritor, embora ele
redija o próprio localizador. Um campo novo lá dentro mudaria o que esta
classe expõe sem decisão local — é o defeito A5 da cadeia 82 visto do
outro lado.

`u36` injeta marcador **real** em cinco canais compostos simultâneos:
principal de controle, provedor, namespace, capacidade e localizador.
Zero vazamento em `repr`, `str` e f-string. `u39` prova que a mensagem de
exceção também não transporta.

O **resultado** nunca carrega localizador nem capacidade (`u24`, `u29`).

---

## 6. O port

Uma requisição tipada, um resultado disjunto, nenhum `Session`, UoW,
repositório, callback ou logger na assinatura.

```text
RUNTIME_CHECKABLE != SIGNATURE_PROOF
```

`isinstance` contra um `Protocol` verifica apenas **presença de membro**.
`u43` mede isso explicitamente: uma classe com assinatura errada passa no
`isinstance`. Quem prova a assinatura é o mypy, sobre a atribuição
estática de `u41`. O limite está escrito na docstring do port.

`u51` prova por **execução** que o corpo não faz nada — chamar o método
não vinculado devolve `None`.

```text
RESOLUTION != DELETION_AUTHORITY
```

`s08` prova que a porta de resolução não ganhou `attempt_effect` e a de
efeito não ganhou `resolve`. Uma porta única deixaria quem sabe **onde** o
objeto está com o poder de destruí-lo.

---

## 7. Guardas envelhecidas — oito, revisadas uma a uma

A presença **autorizada** de `ErasureEffectPort` invalidou guardas cuja
prova era a ausência do nome.

| Guarda | Antes | Depois |
|---|---|---|
| `s09` (alvo), `s13` (aprovação) | ausência do **nome** `ErasureEffectPort` | ausência de **classe concreta** com `attempt_effect` |
| `s13` (aprovação `a`), `s38` (alvo) | port e resultado na lista de ausentes | só `c` e `d` permanecem |
| `s08` (recibo) | port, executor e resultado | só o **executor** — port e resultado são inertes |
| `s01` (recibo), `s10` (alvo), `s12` (aprovação) | — | consumidor autorizado, com nota do porquê |

O caso a registrar é `s09`/`s13`: a propriedade material nunca foi "o
nome não existe", e sim "não há efeito". Trocar o alvo do *nenhum* torna
a guarda mais forte, não mais frouxa.

```text
EFFECT_PORT    = DECLARED_BOUNDARY
EFFECT_ADAPTER = NONE
```

Dois mutantes novos, ambos onde a guarda é a **única** prova estática de
propriedade material: `s99_1` (tradução de capacidade) e `s99_2`
(`stage` como campo).

---

## 8. Master Integrado v2.4

### 8.1 `PIA_OS_SOPHIA_MASTER_COMPATIBILITY` — 20 linhas

```text
 1 USER_AUTHORITY_PRESERVED ....... A evidência de consumo vincula a chamada
     à decisão humana já tomada; nada aqui a substitui.
 2 SOPHIA_BRAND_PIA_OS_CODEBASE ... SIM.
 3 MODULE_SCOPE_AND_DEFERRED ...... Implementado: enums, contratos, port.
     Diferidos: adaptador, avaliador, orquestrador, re-resolução, writer.
 4 SCHEDULE_MODE_DECLARED ......... NOT_APPLICABLE.
 5 AI_ROLE_AND_STEP_INSTRUCTION ... NOT_APPLICABLE.
 6 PROVIDER_CONNECTION_METHOD ..... NOT_APPLICABLE — nenhum provedor nomeado;
     é por isso que a semântica de capacidade fica no adaptador.
 7 AUTOMATION_SCOPE_DECLARED ...... NENHUMA.
 8 APPROVAL_GATES_DECLARED ........ O request EXIGE evidência de consumo, e
     esta fatia não a produz.
 9 PERSISTENCE_BEHAVIOR_DECLARED .. NENHUMA. MIGRATION_DELTA = 0.
10 MULTI_AI_RESULT_ATTRIBUTION .... NOT_APPLICABLE.
11 DIVERGENCE_PRESERVATION ........ SIM — sem normalização de executor_ref,
     failure_code ou capability.operation.
12 CONCURRENT_WORK_ISOLATION ...... Tenant, workspace e principal no binding
     do request.
13 BACKGROUND_EXECUTION ........... NOT_APPLICABLE.
14 RESOURCE_LIMITS_QUEUE_AND_COST . NOT_APPLICABLE.
15 REMOTE_RESOURCE_SCOPE .......... NENHUM acesso remoto (s01).
16 OBSERVATION_PREPARATION_EXEC ... Declara a fronteira de execução SEM
     executar.
17 CREDENTIAL_AND_SECRET_BOUNDARY . Sem nonce, credencial, token ou envelope
     completo no request (u09).
18 FAILURE_ROLLBACK_AND_CONCURRENCY Sem escrita. Exceção é estado AMBÍGUO,
     documentado e não convertido em desfecho.
19 CURRENT_CAPABILITY_NOT_OVERSTATED SUCCEEDED é o que a E4.9.2 congelou —
     escopo controlado confirmado, não prova metafísica.
20 FROZEN_MODULES_UNCHANGED ....... cognitive e alembic byte a byte.
```

### 8.2 `SOPHIA_UX_COMPATIBILITY` — 17 linhas

```text
 1 USER_AUTHORITY_PRESERVED ......... SIM.
 2 SCHEDULE_MODE_DECLARED ........... NOT_APPLICABLE.
 3 AUTOMATION_SCOPE_DECLARED ........ NENHUMA.
 4 PERSISTENCE_BEHAVIOR_DECLARED .... NENHUMA.
 5 PROVIDER_NEUTRALITY_PRESERVED .... REFORÇADO — nenhum provedor é nomeado,
     e a semântica de capacidade fica no adaptador exatamente por isso.
 6 PERSONALIZATION_REVERSIBLE ....... NOT_APPLICABLE.
 7 CONCURRENT_WORK_ISOLATION ........ Binding de tenant/workspace/principal.
 8 BACKGROUND_EXECUTION ............. NOT_APPLICABLE.
 9 RESOURCE_LIMITS_AND_QUEUE ........ NOT_APPLICABLE.
10 AI_ROLE_CONTROL_DECLARED ......... NOT_APPLICABLE.
11 ROLE_AND_STEP_INSTRUCTION ........ NOT_APPLICABLE.
12 PIA_SEQUENCE_SUGGESTION .......... NOT_APPLICABLE.
13 MULTI_AI_RESULT_ATTRIBUTION ...... NOT_APPLICABLE.
14 PIA_INTEGRATION_DIVERGENCE ....... NOT_APPLICABLE.
15 POST_RESULT_USER_COMMAND ......... Inalterado.
16 RESULT_APPROVAL_AND_PERSISTENCE .. Resultado observado != recibo; writer
     segue não composto.
17 FROZEN_MODULES_UNCHANGED ......... SIM.
```

### 8.3 Multicanal v1.3 — 10 marcadores

```text
 1 INPUT_CHANNELS_DECLARED ........ Inalterado — o canal pertence à
     proveniência da aprovação, não à fronteira de efeito.
 2 COMMAND_ENVELOPE_DECLARED ...... Inalterado.
 3 CHANNEL_NORMALIZATION .......... NOT_APPLICABLE.
 4 IDENTITY_CONTEXT_AND_SCOPE ..... Parcial: o request carrega principal e
     escopo; não autentica.
 5 VOICE_CONFIDENCE_AND_CORRECTION  NOT_APPLICABLE.
 6 CONFIRMATION_POLICY_DECLARED ... Inalterado.
 7 DESTRUCTIVE_INTENT_BINDING ..... REFORÇADO — operação, escopo e principal
     vinculados ao descritor.
 8 GOVERNANCE_PARITY_ACROSS_CHANNELS SIM, e por construção: NÃO existe campo
     de canal nesta fronteira (u47), logo não há como tratar voz diferente.
 9 AUDIT_AND_RECEIPT_DECLARED ..... NOT_APPLICABLE — EFFECT != ERASURE_RECORD.
10 CURRENT_CAPABILITY_NOT_OVERSTATED SIM.
```

### 8.4 Parte II §12

**Oito obrigações** cumpridas: diretriz citada; implementado nos §2–§6;
diferidos no §10; estágios separados — declara a fronteira sem executar;
autoridade competente é o usuário, cuja decisão chega como evidência de
consumo; sem escrita não há rollback, e exceção fica documentada como
ambígua; compatibilidade E3/E4 por regressão delta zero; Stop Condition
assumida — e **exercida** na correção da matriz de capacidade.

**Onze Stop Conditions:** nenhuma disparou — sem migration, tabela ou
persistência; sem alterar E3, `ApprovalRecord` ou `ErasureRecord`; sem
adaptador ou acesso externo; o request evita nonce, credencial e envelope
completo; a saída não carrega localizador nem capacidade; observado e
não-tentativa são tipos distintos; `ErasureOutcome` não foi duplicado;
nenhum consumidor runtime novo.

**Onze provas:** `PROVADAS` — nenhuma chamada externa, nenhuma escrita,
nenhum acesso fora do escopo, preservação de proveniência.
`NOT_APPLICABLE` — rollback, concorrência, recibo, cancelamento.
`DEFERRED` — estado obsoleto do alvo, que é E4.9.9.d.

### 8.5 Parte III §13

```text
1 cria distinção?         SIM — "nenhuma tentativa" e "tentativa observada"
                          passam a ser distinguíveis por TIPO
2 transforma distinção?   NÃO
3 compara distinções?     NÃO
4 muda acessibilidade?    NÃO
5 afeta persistência?     NÃO — MIGRATION_DELTA = 0
6 altera proveniência?    NÃO
7 altera história causal? NÃO
```

### 8.6 Parte III §19 e E5/COUT-P

```text
MULTI_AI_HANDOFF_COMPATIBILITY = NOT_APPLICABLE
REASON = internal typed effect boundary; no AI-to-AI runtime handoff introduced
E4_INTEGRATION_OF_COUT_P = FORBIDDEN
```

---

## 9. Gates medidos

```text
COLLECTED        3669                                  (cadeia 90: 3579)
FULL_SUITE       3668 passed / 1 skipped / 0 failed    (cadeia 90: 3578/1/0)
RAW_SUITE        3166 passed / 503 skipped / 0 failed  (cadeia 90: 3076/503/0)
GLOBAL_COVERAGE  99,29%
  erasure_effect_enums.py    13/13    100%
  erasure_effect.py        111/111    100%
  ports/erasure_effect.py      6/6    100%
RUFF PASS   BLACK PASS (403)
MYPY app    7 históricos, NEW = 0
supressões / cast / Any novos: 0
ALEMBIC heads = a1f7c2d40e93 — INALTERADO
git diff --check CLEAN
cognitive be407b46… · alembic 3b1cd66e… byte a byte
```

**Catorze seletores em delta zero:**

```text
E3 = 732 · E4.1 = 40 · E4.2 = 42 · E4.3 = 255 · E4.4 = 74 · E4.5 = 187
E4.6 = 275 · E4.7 = 240 · E4.8 = 146 · E4.9.5 = 113 · E4.9.6 = 309
E4.9.7 = 326 · E4.9.8 = 299 · E4.9.9.a = 85
```

**Fatia nova: E4.9.9.b = 90**, três execuções idênticas.

**Nove caracterizações**, `EXIT=1`, `stderr=0`:

```text
0/8 · 0/5 · 0/9 · 0/3 · 0/11 · 0/3 · 0/8 · 0/8 · 0/8
```

A nova é bilateral: **8/8 na cadeia 90**, **0/8 na 91**, com gate de
validade próprio.

---

## 10. Riscos e limites

**(a) Sexto contrato sem consumidor.** É o estado correto: a E4.9.9.d
consumirá port, request e resultados.

**(b) `SUCCEEDED` é o que o adaptador confirmou.** Escopo controlado, não
prova de que todos os bytes desapareceram de toda réplica, backup ou
cache. Está escrito no contrato e aqui.

**(c) A evidência de consumo é representada, não verificada.** Quem a
construir sem consumo confirmado produzirá uma requisição válida e falsa.
Mesma estrutura de `verified` e de `IdentityEvidence`.

**(d) Exceção do adaptador futuro deixa estado ambíguo.** Esta fatia só
documenta a fronteira; o tratamento operacional é da E4.9.9.d, e **não**
se pode inferir `FAILED`, `PARTIAL` ou `NOT_STARTED` sem observação.

**(e) A verificação de capacidade no request é hoje inalcançável por
descritor válido.** Permanece como segunda camada; se a E4.9.7 relaxar, o
teste `u48` continua exercendo-a por subclasse controlada.

---

## 11. Estado

```text
PATCH_CHAIN = 91
MIGRATION_HEAD = a1f7c2d40e93 (INALTERADO)
E4_9_9_B = COMPLETE_CANDIDATE
ERASURE_EFFECT_PORT = IMPLEMENTED
ERASURE_EFFECT_ADAPTER = NONE
OBSERVED_ATTEMPT_RESULT = IMPLEMENTED
ERASURE_RECORD_WRITER = NOT_COMPOSED
DESTRUCTIVE_EXECUTION_SERVICE = NONE
RETENTION_EVALUATOR = NONE
FRESH_TARGET_RE_RESOLUTION = NONE
E4_9_9_C = NOT_STARTED   E4_9_9_D = NOT_STARTED   E4_10 = NOT_STARTED
E4_9_READY = FALSE
PASS_FINAL = NOT_DECLARED
```
