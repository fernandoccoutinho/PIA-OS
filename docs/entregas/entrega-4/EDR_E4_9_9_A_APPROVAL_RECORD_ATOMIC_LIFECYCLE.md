# EDR E4.9.9.a — ApprovalRecord persistente e ciclo atômico de uso único

**Baseline:** cadeia 89 (`9739f025`). **Saída:** cadeia 90.

```text
PERSISTED_APPROVAL != AUTHENTICATED_USER
PERSISTED_APPROVAL != EXECUTION
APPROVAL_RECORD    != ERASURE_RECORD
CONSUMED_APPROVAL  != OBSERVED_ERASURE_ATTEMPT
NONCE_PRESENT      != CONSUMED
```

```text
E4_9_9_A = COMPLETE_CANDIDATE
APPROVAL_RECORD_RUNTIME = IMPLEMENTED
ATOMIC_CONSUMPTION = IMPLEMENTED
ATOMIC_REVOCATION = IMPLEMENTED
ERASURE_EFFECT = NONE
ERASURE_RECORD_WRITER = NOT_COMPOSED
E4_9_9_B = NOT_STARTED
E4_9_READY = FALSE
PASS_FINAL = NOT_DECLARED
```

---

## 1. Modelo persistente — três tabelas

A terceira é decisão autorizada, e o motivo é material. Reconstruir
`DestructiveApprovalProposal` exige a `GovernanceResolution` **exata**: o
construtor não aceita menos, e montá-la a partir de referências
significaria inventar treze campos, que o §3.3 proíbe. Ela tem **seis**
campos de tupla ordenada.

| Alternativa | Por que foi rejeitada |
|---|---|
| JSON / JSONB | reabriria a fronteira que a E4.9.6 fechou em **três** corretivos |
| colunas `ARRAY` | exigem variante para SQLite nos testes RAW, e a variante é JSON |
| seis tabelas-filhas | oito tabelas ao todo |
| persistir só referências de governança | impossibilita reconstruir sem inventar defaults |
| **uma filha genérica ordenada** | **adotada** |

```text
approval_records                   binding escalar + ciclo de vida
approval_record_targets            lote ordenado, sem localizador
approval_record_governance_items   as seis tuplas, por kind e position
```

```text
APPROVAL_PERSISTENCE_TABLES = 3
JSON_STORAGE = FORBIDDEN
GOVERNANCE_ORDER = PRESERVED
APPROVAL_SCOPE_DIGEST = NOT_USED
```

Três colunas de valor **mutuamente exclusivas** — `value_uuid`,
`value_enum`, `value_text` — com `CHECK` condicionado ao `kind`, em vez de
uma coluna textual polimórfica que aceitaria um UUID malformado como
texto e só falharia na reconstrução.

### 1.1 O que nunca entra em coluna

Conteúdo, `transient_locator`, capacidade, credencial, token, segredo,
biometria, material de step-up, comando em linguagem natural, `pickle`,
`asdict`, `__dict__`. Medido sobre o **schema real** em `u07`.

`subject_coid` **não tem FK**: uma FK faria o apagamento futuro do alvo
destruir a prova de que ele foi aprovado.

---

## 2. Ciclo de vida

```text
ACTIVE | CONSUMED | REVOKED
EXPIRY_IS_DERIVED_NOT_STORED
```

**Não existe `EXPIRED`.** Um estado exigiria scheduler para existir, e
entre o vencimento real e a passagem dele a linha diria `ACTIVE` sobre
aprovação já vencida. Nenhum estado de execução, tentativa ou recibo —
isso é `ErasureRecord`.

**Revogação é transição durável:**

```text
REVOCATION = DURABLE_STATE_TRANSITION, NEVER_ROW_REMOVAL
ROW_DELETION = FORBIDDEN
REVOKED_BEFORE_CONSUMPTION -> NO_CONSUMPTION
CONSUMED_BEFORE_REVOCATION -> REVOCATION_CANNOT_UNDO_CONSUMPTION
```

A expiração **não** entra na condição de revogação: retirar aprovação
vencida é inócuo, e recusar obrigaria o usuário a conviver com uma linha
que ele pediu para remover (`i12`).

---

## 3. Autoridade temporal e comando único

```text
clock_timestamp()
UPDATE ... WHERE ... RETURNING
```

`now()` é o instante de **início da transação**: duas sessões abertas
antes do vencimento poderiam consumir depois dele. O chamador **nunca**
fornece o instante — aceitá-lo deixaria quem pede o consumo decidir se a
aprovação ainda vale.

`SELECT`-depois-`UPDATE` faria as duas sessões lerem `ACTIVE` e ambas
escreverem. Um único `UPDATE` condicional deixa o banco arbitrar.

```text
ZERO_ROWS_RETURNED = LOST_OR_INELIGIBLE
DIAGNOSTIC_READ_NEVER_CONVERTS_DEFEAT_INTO_SUCCESS
```

---

## 4. Binding completo na decisão atômica

```text
PARTIAL_BINDING_MATCH = FORBIDDEN
FULL_STRUCTURAL_BINDING_IN_ATOMIC_DECISION = REQUIRED
```

**Correção material durante a implementação.** A primeira versão levava
cinco campos ao `WHERE` — principal, tenant, workspace, domínio e nonce —
e eu a apresentei como binding. Não era. A autoridade apontou, e o método
passou a receber o **envelope exato**: o binding completo não se expressa
em argumentos soltos.

| Camada | O que entra na condição |
|---|---|
| escalares (32) | operação, finalidade, principal, assurance, `authenticated_at`, tenant/workspace/domínio, canal, revisão de voz, impacto (3), governança escalar (12), os quatro instantes, nonce |
| lote | `EXISTS` correlacionado por posição, com os 12 campos — inclusive `legacy_protection_state` e `version_etag` |
| governança | `EXISTS` correlacionado por `kind` e `position`, nas seis tuplas |
| cardinalidade | `COUNT` correlacionado do lote e de cada `kind` |

**As duas metades são necessárias.** O `EXISTS` prova que cada elemento
esperado está lá; o `COUNT` prova que **não há um a mais**. Só o primeiro
deixaria passar uma linha extra, porque eu verificaria apenas o que
esperava encontrar.

Sem JSON e sem digest — comparação relacional.

### 4.1 Envelopes alternativos, nunca estados fabricados

```text
ALTERNATIVE_ENVELOPE != PATCHED_INVALID_STATE
```

Cada teste de divergência usa um envelope **integralmente válido** pelos
construtores públicos. Nenhum `object.__setattr__`, monkeypatch ou bypass.

Exemplo do desenho: para isolar **assurance**, o par é lixeira com
`STEP_UP_VERIFIED` versus lixeira com `AUTHENTICATED` — as duas
combinações são legítimas, e só o campo em teste difere (`i14`).

Provado: operação (`i13`), assurance (`i14`), canal (`i15`),
cardinalidade de governança (`i16`), proteção de legado (`i17`), ordem do
lote (`i18`).

---

## 5. Proteções de banco

`approval_records` **não** é append-only — tem uma transição legítima.

```text
APPEND_ONLY != SINGLE_USE_LIFECYCLE
```

A trigger enumera as 31 colunas de binding e recusa alteração em qualquer
uma; permite só `ACTIVE → CONSUMED | REVOKED`, com o instante
correspondente preenchido e o outro nulo; recusa transição a partir de
estado terminal; proíbe `DELETE`. As duas filhas são integralmente
imutáveis.

Funções e triggers de **nomes próprios**, como a E4.9.5 estabeleceu: uma
função compartilhada faria o downgrade de uma tabela derrubar a proteção
da outra.

Provado contra SQL bruto em `i23`–`i28`. Round trip sem trigger, função
ou tabela órfã em `i30`.

---

## 6. Reconstituição validada

```text
INVALID_ROW != USABLE_APPROVAL
```

Toda leitura reconstrói pelos **construtores públicos**, reexecutando as
invariantes da E4.9.8 e E4.9.8.1. Sem `pickle`, `object.__new__`, escrita
em `__dict__` ou `cast`. O ORM devolve `list`; a conversão para `tuple` é
explícita, senão uma coleção que a E4.3 declara imutável escaparia
mutável (`i03`).

Linha inválida falha de modo tipado (`i05`), nunca vira aprovação
utilizável.

---

## 7. Erros tipados

```text
BOOLEAN_OUTCOME = FORBIDDEN
```

`PIA-8044` com `ApprovalUsageRefusalReason` fechado — sete motivos:
não encontrada, já consumida, revogada, expirada, binding divergente,
linha inválida, corrida perdida. `PIA-8045` para imutabilidade,
`PIA-8046` para linha inválida.

`False` não distinguiria "expirada" de "binding divergente", e a segunda
é sinal de que alguém pediu consumo com contexto que não corresponde ao
aprovado.

---

## 8. Achado durante a cobertura

`GovernanceResolution` **recusa** `ADMISSIBLE` que carregue capacidade
bloqueada — "capacidade bloqueada é a marca da fronteira" —, e a proposta
exige `ADMISSIBLE`.

```text
ADMISSIBLE + BLOCKED_CAPABILITIES = UNCONSTRUCTIBLE
```

Portanto o ramo de `BLOCKED_CAPABILITY` é **inalcançável por envelope
válido**. Ficou declarado como tal, com a razão medida no código, em vez
de coberto por um teste que fabricasse um estado que os construtores
recusam. O laço permanece por fidelidade: `GovernanceItemKind` cobre as
seis tuplas, e omitir uma faria a persistência divergir se a E4.3 mudar.

`_listar_ativas` foi **removido**: método sem consumidor e sem teste é
escopo além do necessário, e o prompt exige só as operações da fatia.

---

## 9. Revisão das 23 guardas — dentro da cadeia 90

```text
NEW_PATCH_FOR_GUARD_MAINTENANCE = FORBIDDEN
GUARD_REVIEW_STAYS_INSIDE_CHAIN_90 = TRUE
```

Eu havia atualizado quinze por substituição mecânica e pedi pausa por
isso — foi assim que nasceram `s34`, `s37` e `s38` da cadeia 89, guardas
cuja **medição** não correspondia ao **nome**. Todas foram relidas.

| Guarda | O que mudou | O que continua provando |
|---|---|---|
| `s08` (recibo) | `ApprovalRecord` saiu | **ganhou** `DestructiveExecutionService` e `ObservedAttemptResult`: efeito, executor e writer seguem ausentes |
| `s01` (recibo) | três módulos da fatia permitidos | nada ali importa `ErasureRecord`, repositório ou `append_observed` |
| `s10` (alvo) | dois consumidores de **value object** autorizados | `ErasureTargetResolverPort` segue com **zero** consumidores |
| `s12` (aprovação) | persistência é o primeiro consumidor autorizado | nenhum consumidor **destrutivo** apareceu |
| `s37` (alvo) | head autorizado | nenhuma **outra** migration nasceu; o head é folha |
| `s38` (alvo) | **renomeada** para `e4_9_9_b_c_d_nao_foram_iniciadas` | b, c e d seguem sem símbolo, stub ou contrato |
| `i21` ×2 | `-1`/`-2` → alvo **explícito** | o que cada teste sempre quis dizer, sem quebrar a cada migration |
| head fixo (12) | `c8a3f5017e94` → `a1f7c2d40e93` | single head |
| conjunto de tabelas (3) | três tabelas acrescentadas | nenhuma outra nasceu |

`s38` é o caso a registrar: enquanto a fatia `a` estava bloqueada, o nome
dizia o que a guarda media. Autorizada e implementada, manter o nome faria
a guarda prometer uma ausência que deixou de existir.

```text
GUARD_NAME != GUARD_MEASUREMENT  ->  renomear, não afrouxar
```

Nenhuma demonstração por mutante nova, salvo duas onde a guarda é a
**única** prova estática de propriedade material: `s99_1` (o instante é do
banco) e `s99_2` (o comando é único).

---

## 10. Master Integrado v2.4

### 10.1 `PIA_OS_SOPHIA_MASTER_COMPATIBILITY` — 20 linhas

```text
 1 USER_AUTHORITY_PRESERVED ....... REFORÇADO: a confirmação humana ganha
     existência durável e USO ÚNICO.
 2 SOPHIA_BRAND_PIA_OS_CODEBASE ... SIM.
 3 MODULE_SCOPE_AND_DEFERRED ...... Implementado: ApprovalRecord, lote,
     governança, repositório, migration. Diferidos: efeito, avaliador,
     orquestrador, autenticador, adapters.
 4 SCHEDULE_MODE_DECLARED ......... NOT_APPLICABLE — expiração é derivada.
 5 AI_ROLE_AND_STEP_INSTRUCTION ... NOT_APPLICABLE.
 6 PROVIDER_CONNECTION_METHOD ..... NOT_APPLICABLE.
 7 AUTOMATION_SCOPE_DECLARED ...... NENHUMA — sem worker, fila ou background.
 8 APPROVAL_GATES_DECLARED ........ É o objeto da fatia: ACTIVE + não
     vencida + binding completo -> CONSUMED, uma vez só.
 9 PERSISTENCE_BEHAVIOR_DECLARED .. PRIMEIRA persistência de aprovação;
     três tabelas; migration sucessora de `c8a3f5017e94`.
10 MULTI_AI_RESULT_ATTRIBUTION .... NOT_APPLICABLE.
11 DIVERGENCE_PRESERVATION ........ SIM — ordem por coluna, sem normalização.
12 CONCURRENT_WORK_ISOLATION ...... REFORÇADO — tenant, workspace, domínio e
     principal entram na condição de consumo.
13 BACKGROUND_EXECUTION ........... NOT_APPLICABLE.
14 RESOURCE_LIMITS_QUEUE_AND_COST . NOT_APPLICABLE.
15 REMOTE_RESOURCE_SCOPE .......... NENHUM acesso remoto.
16 OBSERVATION_PREPARATION_EXEC ... Preparação DURÁVEL; execução não existe.
17 CREDENTIAL_AND_SECRET_BOUNDARY . Nenhuma coluna de segredo (u07).
18 FAILURE_ROLLBACK_AND_CONCURRENCY Rollback não queima (i22); commit falho
     não publica estado; corrida com vencedor único (i19–i21).
19 CURRENT_CAPABILITY_NOT_OVERSTATED PERSISTED_APPROVAL != EXECUTION; zero
     consumidor destrutivo.
20 FROZEN_MODULES_UNCHANGED ....... cognitive be407b46 byte a byte.
```

### 10.2 `SOPHIA_UX_COMPATIBILITY` — 17 linhas

```text
 1 USER_AUTHORITY_PRESERVED ......... REFORÇADO.
 2 SCHEDULE_MODE_DECLARED ........... NOT_APPLICABLE.
 3 AUTOMATION_SCOPE_DECLARED ........ NENHUMA.
 4 PERSISTENCE_BEHAVIOR_DECLARED .... Declarada em detalhe no §1.
 5 PROVIDER_NEUTRALITY_PRESERVED .... SIM — `custody_provider` é dado, não
     escolha de vendor.
 6 PERSONALIZATION_REVERSIBLE ....... NOT_APPLICABLE.
 7 CONCURRENT_WORK_ISOLATION ........ REFORÇADO.
 8 BACKGROUND_EXECUTION ............. NOT_APPLICABLE.
 9 RESOURCE_LIMITS_AND_QUEUE ........ NOT_APPLICABLE.
10 AI_ROLE_CONTROL_DECLARED ......... NOT_APPLICABLE.
11 ROLE_AND_STEP_INSTRUCTION ........ NOT_APPLICABLE.
12 PIA_SEQUENCE_SUGGESTION .......... NOT_APPLICABLE — nada sugere.
13 MULTI_AI_RESULT_ATTRIBUTION ...... NOT_APPLICABLE.
14 PIA_INTEGRATION_DIVERGENCE ....... NOT_APPLICABLE.
15 POST_RESULT_USER_COMMAND ......... A confirmação do usuário é o que se
     persiste, com uso único e revogação.
16 RESULT_APPROVAL_AND_PERSISTENCE .. Aprovação persiste; efeito e recibo
     NÃO — `ErasureRecord` segue sem writer.
17 FROZEN_MODULES_UNCHANGED ......... SIM.
```

### 10.3 Multicanal v1.3 — 10 marcadores

```text
 1 INPUT_CHANNELS_DECLARED ........ TEXT | VOICE persistidos como
     PROVENIÊNCIA, nunca autoridade.
 2 COMMAND_ENVELOPE_DECLARED ...... O envelope da E4.9.8 torna-se durável.
 3 CHANNEL_NORMALIZATION .......... NOT_APPLICABLE — sem parser.
 4 IDENTITY_CONTEXT_AND_SCOPE ..... PARCIAL, declarado: principal e assurance
     são DECLARADOS pela fronteira externa e persistidos como tal.
 5 VOICE_CONFIDENCE_AND_CORRECTION  Estado de revisão persistido; voz não
     reduz assurance nem cria atalho.
 6 CONFIRMATION_POLICY_DECLARED ... REFORÇADO — janela, uso único, revogação.
 7 DESTRUCTIVE_INTENT_BINDING ..... REFORÇADO — o binding completo entra no
     `WHERE` da decisão atômica.
 8 GOVERNANCE_PARITY_ACROSS_CHANNELS SIM — `i31` parametriza o ciclo de vida
     inteiro nos dois canais.
 9 AUDIT_AND_RECEIPT_DECLARED ..... NOT_APPLICABLE — APPROVAL_RECORD !=
     ERASURE_RECORD.
10 CURRENT_CAPABILITY_NOT_OVERSTATED SIM.
```

### 10.4 Parte II §12

**Oito obrigações:** diretriz citada; implementado nos §1–§7; diferidos no
§12; estágios separados — só preparação durável existe; autoridade
competente é o usuário, e esta fatia **não** cria a infraestrutura que
prova a presença dele; falhas por recusa tipada, rollback devolve o
consumo, concorrência resolvida no banco; compatibilidade E3/E4 por
regressão delta zero; Stop Condition assumida — e **exercida** na pausa
para revisão das guardas.

**Onze Stop Conditions:** nenhuma disparou. A entidade persistente e a
migration são **autorizadas** pelo §1 do prompt; sem ownership novo, sem
credenciais, sem execução externa, sem ampliação de autoridade — o
binding só restringe —, sem provedor, sem sincronização, proveniência
preservada, sem Schedule, sem rollback de efeito porque não há efeito,
congelados intocados.

**Onze provas:** `PROVADAS` — nenhuma chamada externa, nenhum acesso fora
do escopo (`i13`–`i18`), aprovação antes de ação crítica (a ação não
existe), **comportamento concorrente determinístico** (`i19`–`i21`, núcleo
da fatia), preservação de origem e ordem (`i02`), isolamento entre
workspaces, rollback sob falha (`i22`). `NOT_APPLICABLE` — recibo fiel,
cancelamento. `DEFERRED` — estado obsoleto do alvo, que a E4.9.9.d
fechará.

### 10.5 Parte III §13

```text
1 cria distinção?         SIM — "utilizável" vs. "consumida" vs. "revogada",
                          durável. É o objetivo.
2 transforma distinção?   NÃO
3 compara distinções?     NÃO — compara contexto declarado
4 muda acessibilidade?    NÃO
5 afeta persistência?     SIM — três tabelas novas, declarado
6 altera proveniência?    NÃO — canal, origem e ordem preservados
7 altera história causal? NÃO — CausalHistory intocada
```

### 10.6 Parte III §19 e E5/COUT-P

```text
MULTI_AI_HANDOFF_COMPATIBILITY = NOT_APPLICABLE
REASON = internal persistence slice; no AI-to-AI runtime handoff introduced
E4_INTEGRATION_OF_COUT_P = FORBIDDEN
```

---

## 11. Gates medidos

```text
COLLECTED        3579                                  (cadeia 89: 3494)
FULL_SUITE       3578 passed / 1 skipped / 0 failed    (cadeia 89: 3493/1/0)
RAW_SUITE        3076 passed / 503 skipped / 0 failed  (cadeia 89: 3026/468/0)
GLOBAL_COVERAGE  99,28%
  approval_lifecycle_enums.py      42/42    100%
  approval_record.py               75/75    100%
  approval_record_repository.py  126/126    100%
RUFF PASS   BLACK PASS
MYPY app    7 históricos, NEW = 0
supressões / cast / Any novos: 0
ALEMBIC heads = current = a1f7c2d40e93, single head, round trip limpo
git diff --check CLEAN
cognitive be407b46… byte a byte
```

**Treze seletores em delta zero.** E4.9.7 = 326 e E4.9.8 = 299 permanecem
nos valores da cadeia 89. Fatia nova: **E4.9.9.a = 85**, três execuções
idênticas.

**Oito caracterizações**, `stderr = 0`, `EXIT=1`:

```text
0/8 · 0/5 · 0/9 · 0/3 · 0/11 · 0/3 · 0/8 · 0/8
```

A nova (`499a`) reproduz **8/8 na cadeia 89** e **0/8 na 90**, com gate de
validade próprio distinguindo `DEFECT_REPRODUCED`,
`DEFECT_NOT_REPRODUCED` e `INSTRUMENT_INVALID`.

---

## 12. Riscos e limites

**(a) Nenhum consumidor de produção existe.** É o quinto contrato sem
consumidor destrutivo, e é o estado correto: a E4.9.9.d o consumirá.

**(b) O binding compara o que foi persistido, não o mundo.** Se o alvo
mudou desde a aprovação, esta fatia não sabe — re-resolução fresca é
E4.9.9.d. `TOCTOU` segue aberto e declarado.

**(c) `IdentityEvidence` continua representando, não verificando.** Uma
fronteira externa que sempre declare `STEP_UP_VERIFIED` produz aprovações
válidas e falsas. `AUTHENTICATOR = NONE`.

**(d) O ramo de capacidade bloqueada é inalcançável hoje.** Se a E4.3
passar a admitir a combinação, ele entra em uso sem teste. Declarado no
código e aqui.

**(e) A trigger enumera 31 colunas.** Uma coluna nova sem entrada na
função passaria a ser mutável. É o preço de proteger campo a campo em vez
de comparar a linha inteira, e fica registrado como ponto de atenção para
qualquer alteração futura do schema.

---

## 13. Estado

```text
PATCH_CHAIN = 90
MIGRATION_HEAD = a1f7c2d40e93
E4_9_9_A = COMPLETE_CANDIDATE
APPROVAL_RECORD_RUNTIME = IMPLEMENTED
ATOMIC_CONSUMPTION = IMPLEMENTED
ATOMIC_REVOCATION = IMPLEMENTED
ERASURE_EFFECT = NONE
ERASURE_RECORD_WRITER = NOT_COMPOSED
AUTHENTICATOR = NONE
PRODUCT_DESTRUCTIVE_EXECUTION = NOT_AVAILABLE
E4_9_9_B = NOT_STARTED  E4_9_9_C = NOT_STARTED  E4_9_9_D = NOT_STARTED
E4_10 = NOT_STARTED
E4_9_READY = FALSE
PASS_FINAL = NOT_DECLARED
```
