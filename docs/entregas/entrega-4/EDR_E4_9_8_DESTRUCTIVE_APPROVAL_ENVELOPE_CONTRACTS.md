# EDR E4.9.8 — Destructive Approval Envelope Contracts

**Natureza:** primeira fronteira tipada da aprovação destrutiva. Contratual e
**inerte**.
**Baseline:** cadeia 84 (`187f40d9`), `E4_9_7_AUDIT = PASS_FINAL`.

```text
ASSESS != PROPOSE != AUTHORIZE != EXECUTE != RECEIPT
CONSTRUCTIBLE_VALUE_OBJECT != VERIFIED_EXTERNAL_APPROVAL
APPROVAL_RECORD != ERASURE_RECORD
```

```text
E4_9_8 = COMPLETE_CANDIDATE
DESTRUCTIVE_APPROVAL_CONTRACTS = IMPLEMENTED_CANDIDATE
AUTHENTICATOR = NONE          STEP_UP_RUNTIME = NONE
APPROVAL_PERSISTENCE = NONE   ATOMIC_CONSUMPTION = NONE
ERASURE_EFFECT = NONE         ERASURE_RECORD_WRITER = NOT_COMPOSED
MIGRATION_DELTA = 0  E3_DELTA = 0  API_DELTA = 0
E4_9_READY = FALSE            E4_9_9 = NOT_STARTED
```

Esta fatia materializa `PROPOSE` e o artefato contratual de `AUTHORIZE`. Nada
aqui autentica, executa, move para a lixeira, apaga, persiste aprovação,
consome nonce ou escreve recibo.

---

## 1. Inventário real da baseline

Medido por reflexão e AST **antes** de projetar tipos, como o §4.1 exige — e
não pelo nome dos campos, que é o erro que custou quatro corretivos à E4.9.7.

### 1.1 Símbolos de aprovação já existentes

```text
approval | confirmation | assurance | nonce | voice | trash  em backend/app
  → ZERO ocorrências fora de erasure/retention já conhecidos
```

Nenhum vocabulário a reutilizar. Todos os seis enums desta fatia são novos e
nenhum duplica fonte da verdade — `s18` prova.

### 1.2 Os sete contratos da E4.9.7

Capturei assinatura, ordem, defaults, factories e flags de `repr` dos sete.
`s15` congela o retrato: qualquer alteração deles nesta fatia derruba a guarda.
É a contramedida direta ao A6, onde um `= True` acidental alterou um contrato
público sem que nenhum teste medisse.

Estado confirmado e preservado:

```text
VerifiedDeletionCapability(operation: str, scope: str, verified: bool)
  sem default em nenhum dos três
redigidos: control_principal_ref · provider · namespace · operation · scope
           opaque_reference · transient_locator · version_etag
```

### 1.3 `GovernanceResolution` — o achado que mudou o desenho

```text
frozen = True                deep-immutable = True (post_init da E4.3.2 coage)
campos `str` livres VISÍVEIS no repr = 11
  context_actor_ref, context_purpose, safety_rationale, preserved_intent,
  admissible_alternatives, constraints, declared_preservations,
  declared_losses, policy_key, matched_rule_id, policy_rationale
```

O §5.1 exige incorporar a resolução **exata**. Se a proposta delegasse
`resolution!r`, os onze vazariam pela composição — exatamente o defeito A5
medido na cadeia 82.

Redigi-los na origem seria alterar contrato público da E4.3: **Stop Condition
10**. A saída é redigir na composição, e é o que a proposta faz.

Registro a assimetria com honestidade: a fonte continua vazando quando alguém
imprime uma `GovernanceResolution` diretamente. Esta fatia não pode consertar
isso, e não finge ter consertado.

---

## 2. Opções consideradas e decisão

| # | Opção | Decisão |
|---|---|---|
| 1 | reutilizar `ErasureTargetDescriptor` no lote | **rejeitada** — carrega `transient_locator`; o §5.1 proíbe e a E4.9.7 gastou dois corretivos estabelecendo que localizador não sobrevive ao efeito |
| 2 | digest/hash da proposta como binding | **rejeitada** — seria calculado sobre dados de custódia e poderia virar chave de relocalização sem canonicalização provada. `PROPOSAL_DIGEST = NOT_USED`, `s07` prova |
| 3 | reutilizar `RetentionExpiryAction` para a operação | **rejeitada** — o enum descreve o que a expiração dispara, e expiração **inicia avaliação, nunca exclusão** |
| 4 | pôr `APPROVED`/`PENDING` em `ErasureOutcome` | **rejeitada** — o recibo descreve o que uma tentativa **material** observou; estados de aprovação ali reabririam o que a E4.9.0 fechou |
| 5 | assurance uniforme para lixeira e apagamento | **rejeitada** — exigir step-up para a lixeira treinaria o reflexo de reautenticar, e reflexo é o que não se quer no dia do apagamento definitivo |
| 6 | delegar `repr` da `GovernanceResolution` | **rejeitada** — §1.3 |
| **7** | **snapshot seguro + binding estrutural + assurance proporcional** | **adotada** |

---

## 3. Separação de estágios

```text
ASSESS      não existe nesta fatia
PROPOSE     DestructiveApprovalProposal
AUTHORIZE   DestructiveApprovalEnvelope  (contrato; a verificação é externa)
EXECUTE     não existe — s02, s13
RECEIPT     não existe — s02
```

`u26` e `u43` provam por reflexão que nenhum dos dois objetos tem método de
execução, persistência, consumo, revogação ou recibo.

`is_approvable` diz o que diz e nada além:

```text
APPROVABLE != APPROVED
```

Ausência de bloqueio não é aprovação — é a ausência do que a impediria.

---

## 4. Mapa de tipos e campos

```text
approval_enums.py
  DestructiveOperation   MOVE_TO_TRASH | PERMANENT_ERASURE
  AssuranceLevel         UNAUTHENTICATED | AUTHENTICATED | STEP_UP_VERIFIED
                         + satisfies(operacao) -> bool
  InputChannel           TEXT | VOICE
  VoiceReviewState       NOT_APPLICABLE | NOT_REVIEWED | LOW_CONFIDENCE
                         | AMBIGUOUS | REVIEWED_AND_CONFIRMED
                         + permite_proposta(canal) -> bool
  ApprovalBlockerKind    6 membros, sem genérico
  ImpactVolumeKind       KNOWN | UNKNOWN

destructive_approval.py
  SafeTargetSnapshot     classe, sujeito, ControlScope, CustodyNamespace,
                         ReferenceProvenance, version_etag (redigido)
  PresentedImpact        item_count, volume_kind, bytes_total
  IdentityEvidence       principal_ref (redigido), assurance_level,
                         authenticated_at
  ApprovalContext        tenant, workspace, domain, purpose_ref (redigido)
  SafeVoiceProvenance    channel, voice_review
  DestructiveApprovalProposal
  DestructiveApprovalEnvelope
```

---

## 5. Matriz de binding e invalidação

Qualquer divergência **impede a formação do envelope**. Não há mutação: mudar
exige nova instância (`u49`).

| Dimensão | Onde é vinculada | Divergência |
|---|---|---|
| ação | `proposal.operation` | assurance é reavaliada contra a operação (`u34`) |
| lote e **ordem** | `proposal.targets`, tupla | ordem preservada, não reordenada (`u19`) |
| quantidade | `impact.item_count == len(targets)` | `ValueError` (`u20`) |
| volume | `volume_kind` + `bytes_total` | fabricação recusada (`u11`) |
| versão observada | `snapshot.version_etag` | parte do snapshot imutável |
| policy | `governance_resolution` | objeto exato, sem reavaliação (`u21`) |
| custódia | `snapshot.custody_namespace` | parte do snapshot |
| identidade | `identity.assurance_level` | `satisfies` (`u03`, `u34`) |
| tenant/workspace/domínio | `context == proposal.context` | `ValueError` (`u37`) |
| finalidade | `context.purpose_ref` | `ValueError` (`u38`) |
| canal | `provenance == proposal.provenance` | `ValueError` (`u39`) |
| bloqueios | `proposal.blockers` | qualquer um impede (`u36`) |
| tempo | `materialized ≤ issued ≤ confirmed < expires` | `ValueError` (`u40`) |

Isolamento contextual também é imposto **dentro** do lote: alvo cujo
`ControlScope` divirja do tenant/workspace da proposta é recusado (`u25`).

---

## 6. Matriz texto/voz

```text
TEXT_GOVERNANCE = VOICE_GOVERNANCE
VOICE != IDENTITY   VOICE != AUTHORITY   VOICE_TRANSCRIPT != CONFIRMATION
```

| Canal | Revisão | Forma proposta | Prova |
|---|---|---|---|
| `TEXT` | `NOT_APPLICABLE` | sim | `u27` |
| `TEXT` | qualquer outra | **não** | `u30` |
| `VOICE` | `REVIEWED_AND_CONFIRMED` | sim | `u27` |
| `VOICE` | `NOT_REVIEWED` / `LOW_CONFIDENCE` / `AMBIGUOUS` | **não** | `u29` |
| `VOICE` | `NOT_APPLICABLE` | **não** | `u30` |

A coerência é exigida **nos dois sentidos**. `TEXT` obrigado a declarar
`NOT_APPLICABLE` e `VOICE` proibido de declará-lo — sem a segunda metade, a
revisão de uma entrada de voz sumiria sem que ninguém a negasse.

`u28` prova que as **recusas** também têm paridade: assurance insuficiente
falha igual nos dois canais. Paridade é simetria, não indulgência.

```text
ASR_ERROR_MUST_NOT_BECOME_CONSENT
```

Baixa confiança e ambiguidade pertencem à fronteira anterior e **não são
corrigidas aqui** — corrigir seria este módulo decidindo o que o usuário quis
dizer. Nenhum áudio, transcrição ou texto original existe como campo (`u31`).

---

## 7. Garantia por camada

| Garantia | Camada |
|---|---|
| lote imutável, ordenado, sem duplicata | `TYPE_LEVEL` + `APPLICATION_LEVEL` |
| snapshot sem localizador | `TYPE_LEVEL` |
| step-up exigido para apagamento definitivo | `APPLICATION_LEVEL` |
| bloqueio/legal hold impede envelope | `APPLICATION_LEVEL` |
| binding proposta↔envelope | `APPLICATION_LEVEL` |
| coerência temporal | `APPLICATION_LEVEL` — instante **recebido** |
| redação textual direta e composta | `APPLICATION_LEVEL` |
| **evidência de identidade** | `EXTERNAL_BOUNDARY_LEVEL` — representada, não verificada |
| autenticação, step-up, IdP | `DEFERRED` |
| nonce de uso único | `DEFERRED` |
| revogação, replay, TOCTOU, re-resolução | `DEFERRED` |
| persistência e consumo atômico | `DEFERRED` |
| `GovernanceResolution` livre de segredo na fonte | `DEFERRED` — §1.3 |

```text
TYPED_ASSURANCE_CLAIM != AUTHENTICATION_PERFORMED
NONCE_PRESENT         != SINGLE_USE_ENFORCED
EXPIRES_AT_PRESENT    != EXPIRY_ENFORCED
IMMUTABLE_BATCH       != FRESH_TARGET_RE_RESOLUTION
```

O envelope **não prova autenticação**. Ele representa evidência tipada que uma
fronteira externa futura deverá verificar.

---

## 8. Inventário de assinaturas e defaults

Campos com default nos sete contratos novos — congelado em `u44`:

```text
SafeTargetSnapshot            version_etag
PresentedImpact               bytes_total
IdentityEvidence              —
ApprovalContext               —
SafeVoiceProvenance           —
DestructiveApprovalProposal   —
DestructiveApprovalEnvelope   —
```

**Nenhum campo de autoridade, confirmação, assurance, canal, revisão ou
instante tem default, sentinel ou factory.** `u45` prova por `inspect.signature`
que omitir qualquer um é `TypeError`, nunca valor implícito.

Os dois defaults existentes são opcionalidade genuína: nem todo provedor
oferece versão, e volume desconhecido **não pode** carregar bytes.

---

## 9. Inventário de confidencialidade

```text
UNRESTRICTED_PUBLIC_STR = MAY_CONTAIN_SENSITIVE_VALUE
DIRECT_REDACTION != COMPOSITE_REDACTION
REDACTED_REPR != SECRET_FREE_OBJECT
```

Campos `str` livres nesta fatia — derivados por **reflexão** em `u54`, não
escritos à mão:

| Campo | Redigido | Composições provadas |
|---|---|---|
| `SafeTargetSnapshot.version_etag` | sim | proposta, envelope |
| `IdentityEvidence.principal_ref` | sim | envelope |
| `ApprovalContext.purpose_ref` | sim | proposta, envelope |

Herdados e já redigidos pela E4.9.7: `control_principal_ref`, `provider`,
`namespace`. Provados de novo **através** das composições novas (`u50`).

`u53` prova por reflexão que **nenhum** contrato tem campo para conteúdo,
prompt, resposta, nota, áudio, transcrição, token, segredo, senha, credencial,
cookie, assinatura, biometria, localizador ou diagnóstico livre.

`u56` prova que as **exceções controladas** não transportam o marcador — o
canal que ninguém costuma testar.

---

## 10. Limites — o que NÃO existe

```text
AUTHENTICATION        nenhuma. IdentityEvidence representa, não verifica
STEP_UP               nenhum runtime; só o nível declarado
APPROVAL_PERSISTENCE  nenhuma tabela, repositório, writer
ATOMIC_CONSUMPTION    nenhum consumo de nonce; SINGLE_USE_RUNTIME = DEFERRED
REVOCATION            nenhuma; REVOCATION_RUNTIME = DEFERRED
REPLAY_PROTECTION     nenhuma
TOCTOU_CLOSURE        nenhuma — o lote é imutável, o mundo não
FRESH_RE_RESOLUTION   nenhuma; IMMUTABLE_BATCH != FRESH_TARGET_RE_RESOLUTION
CLOCK                 nenhum; datetime.now() escondido é proibido (s06)
DURAÇÃO CANÔNICA      nenhuma inventada — a janela vem do chamador
```

`is_temporally_coherent_at` recebe o instante explicitamente e o nome diz
exatamente o que ela observa: coerência temporal declarada, **não** revogação,
consumo, replay ou autoridade externa.

---

## 11. Conformidade documental — quatro camadas (Master v2.3)

### 11.1 `PIA_OS_SOPHIA_MASTER_COMPATIBILITY` — 20 linhas

```text
├── USER_AUTHORITY_PRESERVED ................ SIM. O envelope REGISTRA a
│     decisão do usuário; não a substitui, não a presume, não a infere.
├── SOPHIA_BRAND_PIA_OS_CODEBASE_PRESERVED .. SIM.
├── MODULE_SCOPE_AND_DEFERRED_CAPABILITIES ... Escopo: PROPOSE + contrato de
│     AUTHORIZE. Diferidos: autenticação, persistência, consumo, efeito, recibo.
├── SCHEDULE_MODE_DECLARED ................... NOT_APPLICABLE — sem Schedule.
├── AI_ROLE_AND_STEP_INSTRUCTION_DISTINGUISHED NOT_APPLICABLE — sem multi-IA.
├── PROVIDER_CONNECTION_METHOD_DECLARED ...... NOT_APPLICABLE — nenhum conector;
│     `AssuranceLevel` é neutro de provedor por desenho.
├── AUTOMATION_SCOPE_DECLARED ................ NENHUMA (s06, s12).
├── APPROVAL_GATES_DECLARED .................. É o objeto desta fatia, e está
│     declarado como CONTRATO: step-up para erasure, autenticado para lixeira,
│     nenhuma operação sem evidência. Runtime = DEFERRED.
├── PERSISTENCE_BEHAVIOR_DECLARED ............ NENHUMA (s01).
├── MULTI_AI_RESULT_ATTRIBUTION_DECLARED ..... NOT_APPLICABLE.
├── DIVERGENCE_PRESERVATION_DECLARED ......... SIM — nenhuma normalização;
│     ordem do lote preservada; valores devolvidos byte a byte.
├── CONCURRENT_WORK_ISOLATION_DECLARED ....... SIM — tenant/workspace/domínio
│     no binding, e alvo fora do contexto é recusado (u25, u37).
├── BACKGROUND_EXECUTION_AUTHORIZATION ....... NOT_APPLICABLE — nada executa.
├── RESOURCE_LIMITS_QUEUE_AND_COST_DECLARED .. NOT_APPLICABLE — sem chamada
│     externa; o volume apresentado é informação ao usuário, não cota.
├── REMOTE_RESOURCE_SCOPE_DECLARED ........... NENHUM acesso remoto.
├── OBSERVATION_PREPARATION_EXECUTION ........ Distinguidos: esta fatia é
│     PREPARAÇÃO. Observação é da E4.9.7; execução não existe.
├── CREDENTIAL_AND_SECRET_BOUNDARY_DECLARED .. SIM — u53 e s04.
├── FAILURE_ROLLBACK_AND_CONCURRENCY ......... Sem escrita, nada a reverter.
│     Value objects congelados não têm concorrência.
├── CURRENT_CAPABILITY_NOT_OVERSTATED ........ §7 classifica cada garantia;
│     §10 enumera o que não existe; §12 declara TOCTOU e replay abertos.
└── FROZEN_MODULES_UNCHANGED ................. cognitive e alembic idênticos.
```

### 11.2 `SOPHIA_UX_COMPATIBILITY` — 17 linhas

```text
├── USER_AUTHORITY_PRESERVED ................. SIM — ver §11.1.
├── SCHEDULE_MODE_DECLARED ................... NOT_APPLICABLE.
├── AUTOMATION_SCOPE_DECLARED ................ NENHUMA.
├── PERSISTENCE_BEHAVIOR_DECLARED ............ NENHUMA.
├── PROVIDER_NEUTRALITY_PRESERVED ............ SIM — nenhum IdP, método ou
│     fator aparece em `AssuranceLevel`; `CustodyNamespace` inalterado.
├── PERSONALIZATION_REVERSIBLE ............... NOT_APPLICABLE.
├── CONCURRENT_WORK_ISOLATION_DECLARED ....... SIM.
├── BACKGROUND_EXECUTION_AUTHORIZATION ....... NOT_APPLICABLE.
├── RESOURCE_LIMITS_AND_QUEUE_DECLARED ....... NOT_APPLICABLE.
├── AI_ROLE_CONTROL_DECLARED ................. NOT_APPLICABLE.
├── ROLE_AND_STEP_INSTRUCTION_DISTINGUISHED .. NOT_APPLICABLE.
├── PIA_SEQUENCE_SUGGESTION_BEHAVIOR ......... NOT_APPLICABLE — nada sugere.
├── MULTI_AI_RESULT_ATTRIBUTION_DECLARED ..... NOT_APPLICABLE.
├── PIA_INTEGRATION_DIVERGENCE_PRESERVATION .. NOT_APPLICABLE — sem síntese.
├── POST_RESULT_USER_COMMAND_DECLARED ........ SIM, na parte que cabe: a
│     confirmação É comando do usuário, e o envelope a registra vinculada.
├── RESULT_APPROVAL_AND_PERSISTENCE ......... Distinguidos por construção:
│     aprovação existe como contrato; persistência não existe.
└── FROZEN_MODULES_UNCHANGED ................. SIM.
```

### 11.3 `MULTICHANNEL_COMMAND_COMPATIBILITY_v1_3` — 10 marcadores

```text
├── INPUT_CHANNELS_DECLARED ................. TEXT | VOICE, proveniência.
├── COMMAND_ENVELOPE_DECLARED ............... É esta fatia, na parte
│     contratual. Parser, ASR e normalizador NÃO existem (s05).
├── CHANNEL_NORMALIZATION_DECLARED .......... NOT_APPLICABLE — não recebemos
│     linguagem natural; nada a normalizar.
├── IDENTITY_CONTEXT_AND_SCOPE_DECLARED ..... PARCIAL e declarado: contexto e
│     principal vêm da fronteira externa e NÃO são autenticados aqui.
├── VOICE_CONFIDENCE_AND_CORRECTION ......... SIM — `VoiceReviewState`; baixa
│     confiança e ambiguidade impedem a proposta e não são corrigidas aqui.
├── CONFIRMATION_POLICY_DECLARED ............ SIM — a confirmação vincula ação,
│     lote, ordem, versões, policy, custódia, impacto, identidade, tenant,
│     domínio e finalidade; mudança exige nova instância (§5, u49).
├── DESTRUCTIVE_INTENT_BINDING_DECLARED ..... SIM — §5.
├── GOVERNANCE_PARITY_ACROSS_CHANNELS ....... SIM — §6, provado por
│     parametrização nos invariantes E nas recusas.
├── AUDIT_AND_RECEIPT_DECLARED .............. NOT_APPLICABLE — sem recibo. E o
│     §9 amplia a lista do que não pode entrar num recibo futuro.
└── CURRENT_CAPABILITY_NOT_OVERSTATED ....... SIM — §7 e §10.
```

### 11.4 Parte II §12

**Oito obrigações:** cumpridas — diretriz citada; implementado nos §3–§6;
diferido no §10; observação/preparação/aprovação/execução separadas por tipos
distintos; a autoridade competente é o usuário presente e autenticado, e esta
fatia **não** cria a infraestrutura que prova essa presença; sem escrita não há
rollback e VOs congelados não têm concorrência; compatibilidade com E3/E4 por
regressão delta zero; nenhuma Stop Condition disparou.

**Onze Stop Conditions mínimas:** nenhuma disparou — sem entidade persistente
ou migração, sem ownership de Workspace/conector, sem credenciais, sem execução
externa, sem ampliação de autoridade (o contrato só **restringe**), sem
assinatura de provedor, sem sincronização, sem perda de proveniência, sem
colapso de Schedules, sem rollback declarado, sem alteração de congelados.

**Onze provas mínimas:** PROVADAS — nenhuma chamada externa (`s03`), nenhum
acesso fora do escopo (`u25`, `u37`), nenhuma escrita (`s01`), **aprovação
anterior à ação crítica** (representada; a ação não existe), preservação de
proveniência (`u19`, `u31`), isolamento entre Workspaces (`u25`, `u37`).
`DEFERRED` — rollback, estado obsoleto, concorrência determinística, recibo
fiel, cancelamento.

### 11.5 Checklist de impacto sobre distinções (Parte III §13)

```text
1. cria distinção?          SIM — proposta e aprovação passam a ser
                            distinguíveis por TIPO, e é o objetivo da fatia
2. transforma distinção?    NÃO — nenhum valor é reescrito
3. compara distinções?      NÃO — compara contexto declarado, não patrimônio
4. muda acessibilidade?     NÃO
5. afeta persistência?      NÃO — zero ORM, zero migração
6. altera proveniência?     NÃO — preserva canal e origem
7. altera história causal?  NÃO — CAUSAL_HISTORY_DEPENDENCY é apenas um
                            motivo de BLOQUEIO, nunca uma alteração
```

### 11.6 Compatibilidade E5 / COUT-P

```text
E4_INTEGRATION_OF_COUT_P = FORBIDDEN — respeitado
```

Nenhum score, escalarização, `A = R*P*T`, `COUT_SCORE` ou dependência de
COUT-P. `AssuranceLevel` é vocabulário ordenado, não métrica: `satisfies`
devolve `bool` a partir de comparação de membros, não de número.

---

## 12. Riscos que declaro

**(a) `GovernanceResolution` continua vazando na fonte.** A composição está
redigida, e a fonte não. Se alguém imprimir a resolução diretamente, os onze
campos aparecem. Não posso corrigir sem alterar contrato público da E4.3, e o
prompt proíbe. Fica como `DEFERRED` — e como o candidato mais provável a virar
achado de auditoria numa fatia futura que a manipule.

**(b) O contrato representa evidência; não a verifica.** Uma fronteira externa
que sempre declare `STEP_UP_VERIFIED` produz envelopes válidos e falsos. É a
mesma estrutura de `VerifiedDeletionCapability.verified` na E4.9.7, e a mesma
razão de a E4.9.4 exigir autoridade **autorizada**. Nenhum teste pode fechar
isso sem o autenticador.

**(c) TOCTOU está aberto por desenho.** O lote é imutável; o mundo não. Entre a
materialização da proposta e um efeito futuro, o alvo pode mudar de versão,
custódia ou existência. `version_etag` **modela** a detecção; nada a impõe.
Re-resolução fresca é `DEFERRED`, e um executor que confie no snapshot sem
reresolver agirá sobre estado velho.

**(d) Nonce sem consumo é decoração até a E4.9.9.** Ele é obrigatório, opaco e
distinto do `approval_id`, mas nada impede reutilizar o mesmo envelope duas
vezes — não há repositório, lock nem consumo atômico. `NONCE_PRESENT !=
SINGLE_USE_ENFORCED` está no código para que ninguém leia a presença do campo
como proteção contra replay.

**(e) Contratos sem consumidor acumulam.** São agora quatro: recibo que ninguém
escreve, policy que ninguém avalia, porta que ninguém implementa e envelope que
ninguém consome. Cada um convida a "só ligar o adaptador", e as guardas por AST
protegem apenas enquanto ninguém as alterar.

**(f) A janela temporal não tem duração canônica.** Deliberado — não inventei
"5 minutos". O custo é que dois chamadores podem escolher janelas
incomparáveis, e não há nada que os alinhe até existir política.

---

## 13. Gates medidos

Clone limpo, PostgreSQL recriado e **pré-migrado**:

```text
COLLECTED        3311                                  (cadeia 84: 3154)
FULL_SUITE       3310 passed / 1 skipped / 0 failed    (cadeia 84: 3153/1/0)
RAW_SUITE        2843 passed / 468 skipped / 0 failed  (cadeia 84: 2686/468/0)
GLOBAL_COVERAGE  99,29%   (era 99,26% — subiu)
  approval_enums.py          48/48    100%
  destructive_approval.py  209/209    100%
RUFF PASS   BLACK PASS (391)
MYPY app    7 históricos — registry.py 4, base_repository.py 2, handlers.py 1
            NEW = 0
supressões / cast / Any novos: 0
ALEMBIC heads = current = c8a3f5017e94, single head
git diff --check CLEAN
```

**Regressões, delta 0:**

```text
E3 = 732 · E4.1 = 40 · E4.2 = 42 · E4.3 = 255 · E4.4 = 74 · E4.5 = 187
E4.6 = 275 · E4.7 = 240 · E4.8 = 146 · E4.9.5 = 113 · E4.9.6 = 309
E4.9.7 = 285
```

**Fatia nova: E4.9.8 = 157** (134 unitários + 23 estáticos), três execuções
idênticas.

Quatro caracterizações, byte a byte, `stderr = 0`: `0/8 · 0/5 · 0/9 · 0/3`,
todas `EXIT=1`.

### 13.1 Três guardas anteriores envelheceram

Nenhuma por regressão.

- **`s01`** do `erasure_record`: o schema novo reutiliza `ErasureTargetClass`.
  Acrescentado aos permitidos, com a mesma nota da E4.9.7.
- **`s08`** do `erasure_record`: `DestructiveApprovalEnvelope` saiu da lista de
  ausentes porque foi autorizado. **`ErasureEffectPort` e `ApprovalRecord`
  permaneceram.**
- **`s10`** do `erasure_target`: esta eu **separei em duas**, e a separação é a
  correção. Ela dizia "nenhum consumidor da porta" e media também consumo dos
  *value objects*. Colapsados, a guarda cairia a cada fatia que reutilizasse um
  `ControlScope`, e a ausência de adaptador — o que ela existe para provar —
  deixaria de ser o que ela mede. Agora a **porta** tem zero consumidores e os
  **value objects** têm um consumidor autorizado e nomeado.

### 13.2 Robustez da própria suíte (§11.5)

Cinco demonstrações de que cada mecanismo **consegue falhar** (`s99_1` a
`s99_5`): mutante com o termo proibido no código versus só na docstring;
supressão real em comentário versus mencionada em docstring; retrato de
assinatura detectando default acrescentado; objeto que delega `!r` vazando
versus redigido; ausência de script de caracterização dentro do repositório.

Depois de sete achados na E4.9.7, publicar guarda que só pode passar seria pior
que não publicar nenhuma.

### 13.3 Fronteiras descobertas pela exigência de 100%

Dezesseis recusas de tipo em `volume_kind`, `assurance_level`, `channel`,
`voice_review`, quatro campos da proposta, item do lote e quatro do envelope.
Nenhuma era linha morta: passavam porque as fábricas sempre entregam o tipo
certo. `u63` exigiu o **construtor direto** — a fábrica monta o contexto *a
partir da* proposta, então uma proposta falsa nem chegaria ao construtor.

---

## 14. Arquivos

```text
NOVOS
  app/memory/models/approval_enums.py                    6 vocabulários
  app/memory/schemas/destructive_approval.py             7 value objects
  tests/unit/memory/test_destructive_approval.py         134 casos
  tests/static/test_destructive_approval_isolation.py    23 guardas
  docs/entregas/entrega-4/EDR_E4_9_8_...md
ALTERADOS
  app/memory/models/__init__.py                          reexport
  app/memory/schemas/__init__.py                         reexport
  tests/static/test_erasure_record_isolation.py          2 guardas envelhecidas
  tests/static/test_erasure_target_isolation.py          1 guarda separada em duas
```

Nada em migration, schema, ORM, repository, port, writer, E3, Alembic ou
`errors/codes.py`. Nenhum código de erro novo. Nenhuma assinatura pública
existente alterada — `s15` prova.

---

## 15. Estado

```text
PATCH_CHAIN = 85
MIGRATION_HEAD = c8a3f5017e94 (INALTERADO)
E4_9_8_IMPLEMENTATION = COMPLETE_CANDIDATE
E4_9_8_STATUS = AWAITING_INDEPENDENT_AUDIT
DESTRUCTIVE_APPROVAL_CONTRACTS = IMPLEMENTED_CANDIDATE
AUTHENTICATOR = NONE          STEP_UP_RUNTIME = NONE
APPROVAL_PERSISTENCE = NONE   ATOMIC_CONSUMPTION = NONE
TARGET_RESOLVER_ADAPTER = NONE
ERASURE_EFFECT = NONE         ERASURE_RECORD_WRITER = NOT_COMPOSED
E4_9_READY = FALSE
E4_9_9 = NOT_STARTED
```

Não existe autenticador, não existe efeito, e a E4.9.9 não foi iniciada.
`PASS_FINAL` pertence à auditoria independente.
