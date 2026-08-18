# E4_DEFERRED_INVENTORY — o que a E4.0 não entrega

**Módulo:** E4.0 — Architecture & Contract Freeze

> Compõe com `E3_FINAL_MANIFEST.md` §12 — **não duplica**. Itens já
> inventariados na E3 aparecem aqui apenas quando a E4 muda seu
> destino.

---

## 1. Proibido na própria E4.0 (§26)

```
PRODUCTION CODE   = NO
MIGRATION         = NO
NEW TABLE         = NO
NEW ENUM          = NO
NEW API           = NO
```

Verificado: a E4.0 entrega **somente documentos**. Nenhum arquivo em
`backend/app/`, `backend/alembic/` ou `backend/tests/` foi criado ou
modificado.

---

## 2. Deferido dentro da E4 — com destino

| Item | Destino | Por que não na E4.0 |
|---|---|---|
| política completa de transição de `AccessibilityState` | **E4.7** (sob autoridade de E4.3) | §6 do prompt canônico proíbe inventar transições aqui |
| ~~identidade de `DomainMembership`~~ | **RESOLVIDO em E4.1** | identidade própria adotada (convenção `BaseModel`); `UNIQUE(domain_id, coid)` é a identidade estrutural |
| lifecycle de `DomainMembership` (`left_at`) | E4.3+ | entra junto com a remoção, que exige autoridade — coluna sem escritor não preserva história |
| remoção de membership | E4.3+ | remover é operação sob autoridade |
| `DOMAIN_DELETION` / `DOMAIN_RENAME` / `DOMAIN_MERGE` | não atribuído | não se cria operação destrutiva para completar CRUD |
| hierarquia de domínio (`parent_domain_id`, `path`) | não atribuído | `MEMORY_DOMAIN != FILESYSTEM_FOLDER` |
| `owner` / `policy_ref` de domínio | E4.3 | autoridade é Governance |
| ~~`MemoryContext` persistente ou transiente~~ | **RESOLVIDO em E4.2** | TRANSIENT confirmado; value object imutável, sem tabela |
| `ContextDefinition` | **não atribuído** | E4.0 registrou "provável", não congelou; sem consumidor até Governance/Retrieval existirem |
| campos `task` e `scope` de contexto | não atribuído | sem necessidade demonstrada; §13 proíbe inventar modelo de escopo |
| ~~campos de `MemoryContext`~~ | **RESOLVIDO em E4.2** | `domain_ids` + `session_id?` + `actor_ref?` + `purpose?`; nada mais |
| forma de expressão de `rules` de policy | E4.3 (Governance) | Stop Condition 12 — não escolher motor por conveniência |
| motor de policy (OPA / Cedar / DSL) | E4.3+ (Governance) | a semântica precede a ferramenta |
| `on_expiry_action` de retenção | E4.9 | decidido pela E4.9.3 e **MATERIALIZADO pela E4.9.6** (cadeia 76, migration `c8a3f5017e94`) como `RetentionExpiryAction.ASSESS_AND_INFORM` — enum de **um único membro**, para que ampliar exija contrato novo. `RETENTION_EVALUATOR = NOT_COMPOSED`: a policy diz quando avaliar, e nada avalia |
| lixeira reversível, segmentação da Biblioteca Cognitiva e pastas editáveis | **E4.9** | **AUTORIZADAS pela E4.9.3** (`EDR_E4_9_3_DELETE_TIMING_TRASH_DISPOSITIONS.md`). `AUTHORIZED_NOT_IMPLEMENTED`; nenhuma lixeira, pasta, busca ou interface existe |
| nota qualitativa de revisão por transição de versão | **E4.9** | **AUTORIZADA pela E4.9.3**. Nasce durante a revisão, sobrevive ao apagamento e não pode reconstruir conteúdo. `AUTHORIZED_NOT_IMPLEMENTED` |
| estado `VALIDATED_CURRENT` (artefato canônico) | **EDR próprio, não atribuído** | conceito autorizado pela E4.9.3, **sem lastro no schema**: `RevisionStatus` tem só `current` e `superseded`. Materializá-lo toca a E3 congelada |
| envelope único de comando texto/voz | **E4.9.4** | autorizado conceitualmente pela E4.9.3; parser, ASR e interface **não** existem |
| história causal de vida e Biblioteca do Legado | **não atribuído** | **AUTORIZADAS pela E4.9.3.1** (`EDR_E4_9_3_1_LIFE_CAUSAL_LEGACY_INHERITANCE.md`). Vista da Biblioteca Cognitiva, sem storage novo. `AUTHORIZED_NOT_IMPLEMENTED`; nenhuma trajetória, categoria, importador ou narrativa existe |
| grau de confirmação de afirmação biográfica (`DOCUMENT_VERIFIED`…`UNKNOWN`) | **não atribuído** | vocabulário **conceitual** da E4.9.3.1, sem enum e sem coluna. `PIA_INFERRED_UNCONFIRMED != FACT` |
| plano de legado e diretiva de herança dirigida | **não atribuído** | **AUTORIZADOS pela E4.9.3.1**. Modalidades conceituais e revogáveis; poderes separados (ler, custodiar, publicar, licenciar, transferir, excluir). Nenhum beneficiário, administrador, escopo ou versão existe |
| gatilho verificado de morte ou incapacidade | **módulo futuro próprio, não atribuído** | `POSTHUMOUS_SUCCESSION_AUTHORITY = SEPARATE_FUTURE_MODULE`. Exige evidência externa verificável, revisão humana e compatibilidade jurídica. `INACTIVITY != DEATH`; **não** é herdado da E4.9.4 |
| integração com instrumento jurídico sucessório | **fora da E4** | `LEGAL_INSTRUMENT_INTEGRATION = DEFERRED`. `PIA_LEGACY_PLAN != LEGAL_WILL`; jurisdição, documento e autoridade não são escolhidos por arquitetura |
| recuperação ou delegação de conta e segredos | **arquitetura de segurança própria, não atribuída** | `CREDENTIALS != INHERITABLE_CONTENT`. Segredo nunca entra em legado, nota causal, recibo ou exportação |
| exportação/portabilidade do legado | **não atribuído** | direção autorizada pela E4.9.3.1; formato não escolhido e nenhum exportador existe. `EXPORT != RIGHT_TRANSFER`; `EXPORT != SOURCE_ERASURE` |
| fronteira de identidade e autenticação de principal | **subsistema próprio, não atribuído** | **EXIGIDA pela E4.9.4** (`EDR_E4_9_4_DESTRUCTIVE_EXECUTION_AUTHORITY.md`). `PIA-7001` e `app/security/` existem como ESTRUTURA: a exceção nunca é levantada e o pacote declara não fazer login nem permissões. `ERROR CODE EXISTS != AUTHENTICATOR EXISTS` |
| autenticação reforçada (step-up) para erasure definitiva | **subsistema próprio, não atribuído** | exigida pela E4.9.4 sem escolher tecnologia ou fornecedor. Falha do IdP **bloqueia**: `IDP UNAVAILABLE = BLOCK, NEVER DEGRADE` |
| envelope de aprovação destrutiva (`DestructiveApprovalEnvelope` ou equivalente) | **E4.9** | **AUTORIZADO pela E4.9.4**. `AUTHORIZED_NOT_IMPLEMENTED`; nenhuma classe, schema, serialização, assinatura, nonce ou store existe. `APPROVAL_RECORD != ERASURE_RECORD` |
| registro de aprovação (quem autorizou qual escopo e quando) | **E4.9** | autorizado pela E4.9.4, separado do `ErasureRecord`; não pode conter conteúdo, localizador vivo, segredo ou credencial |
| orquestrador dos cinco estados `ASSESS→PROPOSE→AUTHORIZE→EXECUTE→RECEIPT` | **E4.9** | autorizado conceitualmente pela E4.9.4; consumo atômico, re-resolução fresca e version check são **requisitos futuros**, sem queue/saga/outbox/worker |
| hash de escopo da aprovação | **E4.9** | conceitualmente autorizado pela E4.9.4 com limite duro: `APPROVAL_SCOPE_HASH != CONTENT_HASH` e `!= LOCATOR`. Canonicalização e algoritmo ficam para a implementação |
| **conciliação legal erasure × `CausalHistory`** | **E4.9** | `LEGAL_ERASURE_VS_CAUSAL_HISTORY = DEFERRED_TO_E4_9` — ver §6. Direção congelada em A + B pela E4.9.0; **caminho normal DECIDIDO pela E4.9.2** (`CLOSED_CANDIDATE_CONDITIONAL`). A **exceção** que alcança o registro causal permanece aberta por desenho |
| exceção: obrigação que alcança o próprio registro causal | **EDR próprio, não atribuído** | `EXCEPTIONAL_CAUSAL_RECORD_ERASURE = DEFERRED_STOP_CONDITION` (E4.9.2). Exige EDR jurídico-arquitetural com escopo concreto e autoridade explícita; o sistema **para** com exceção tipada |
| primitiva de auditoria de apagamento (`ErasureRecord`) | **E4.9** | Autorizada pela E4.9.0 e **IMPLEMENTADA pela E4.9.5** (cadeia 75, migration `9d4f1a7c2be8`): modelo, tabela, repository append-only em três camadas e testes. `IMPLEMENTATION_STATUS = COMPLETE_CANDIDATE`. **Nenhum escritor runtime foi composto** — `ERASURE_RECORD_RUNTIME_WRITER = NOT_COMPOSED`, `ERASURE_EFFECT = NONE` |
| contrato de alvo e custódia para erasure (`ErasureTargetDescriptor`, portas de resolução e efeito) | **E4.9** | **AUTORIZADO prospectivamente pela E4.9.1** (`EDR_E4_9_1_ERASURE_TARGET_CUSTODY_CONTRACT.md`). `AUTHORIZED_NOT_IMPLEMENTED`; nenhum resolvedor, storage, conector, credencial ou executor existe |
| Artifact Storage e conectores externos | **não atribuído** | `ARTIFACT_STORAGE = DEFERRED`; a E4.9.1 autorizou o CONTRATO de alvo, não o mecanismo. Sem eles, nenhuma classe de alvo é executável |
| portabilidade de `MemoryDomain` | **E4.3+** | E4.1 manteve `MEMORY_DOMAIN_SYNC = DEFERRED`: o critério decisivo (*se carregar semântica de acesso, é LOCAL*) só é avaliável depois de Governance existir |
| portabilidade de `ValidatedExperience` | E4.11 | análise registrada, decisão do módulo |
| escopo exato do registro da E4.11 | E4.11 | limite proposto, a confirmar |
| mecanismo de promoção transcript → patrimônio | não atribuído | exige mecanismo explícito ainda não desenhado |
| envelope de sync para estado E4 | módulo próprio | §22 — E3 Sync não é alterado |

---

## 3. Deferido para além da E4

| Item | Status | Nota |
|---|---|---|
| `CognitiveDistinction` | DEFERRED | herdado da E3 |
| `CausalClassRef` | DEFERRED | herdado da E3 |
| `CausalComparison` | DEFERRED | herdado da E3 |
| `CognitiveExecution` | **E7** | `COGNITIVE_EXECUTION = DEFERRED` |
| Multi-AI Orchestration | **E7** | `MULTI_AI_ORCHESTRATION = DEFERRED` |
| Artifact Storage | DEFERRED | `MemoryDomain` não é diretório; `CognitiveObject` não é arquivo; `payload_ref` continua referência |
| busca full-text / vetorial / embeddings | DEFERRED | apenas descoberta; nunca fonte da verdade |
| integridade referencial de `input_refs` / `output_refs` | DEFERRED | herdado da E3 |
| política externa / tombstone | DEFERRED | ligado a E4.9 |
| RLS no PostgreSQL | **investigação apenas** | defesa em profundidade; owner/`BYPASSRLS`, backup e FK a analisar antes |
| authentication / authorization | fora do escopo E4 | matriz de fronteiras em `E4_GOVERNANCE_BOUNDARIES` §8 |
| encryption / secrets management | fora do escopo E4 | idem |

---

## 4. Permanentemente proibido

Não é "deferido" — é decisão de arquitetura, sem data futura:

```
AUTONOMOUS_KERNEL_MUTATION          = FORBIDDEN
ERROR_BASED_LEARNING                = FORBIDDEN
AUTO_DESTRUCTIVE_REPAIR             = FORBIDDEN
COUT_GLOBAL_SCORE                   = NONE
COUT_DECISION_ENGINE                = NONE
VECTOR_DATABASE_AS_SOURCE_OF_TRUTH  = FALSE
TRANSCRIPT_AS_MEMORY                = FALSE
persistence_score / survival score  = NONE
importance / promotion score        = NONE
```

E o que decorre deles: nenhuma policy pode alterar existência; nenhuma
consolidação pode apagar fontes; nenhuma similaridade pode fundir
identidades; nenhum resultado de busca é prova.

---

## 5. Item conhecido na E3 — registrado, não tocado

`app/cognitive/services/accessibility_manager.py` documenta um proxy
interino: a transição para `CAUSALLY_EXTINCT` exige `reason` não-vazio
**porque `E3.9` ainda não existia** quando `E3.6` foi escrito. A
exigência formal do Domain Model Draft é um **evento causal
associado**.

`E3.9` foi implementado. O proxy pode ser substituído pela exigência
formal.

**A E4.0 não faz isso e a E4 provavelmente não deveria.** Alterar
`app/cognitive/` durante a E4 aciona a Stop Condition 1 (*"modificar
E3 para fazer E4.0 fechar"*). A E4.0 fecha sem essa mudança — ela não
é necessária para nada aqui.

**Recomendação:** tratar como corretivo próprio da E3
(p.ex. `e3-6-2b-causally-extinct-requires-causal-event.patch`), com
seu próprio gate e sua própria auditoria, fora da E4 e por decisão sua.
Registrado aqui para não se perder.

---

## 6. Tensão preservada — legal erasure × `CausalHistory`

```
LEGAL_ERASURE_VS_CAUSAL_HISTORY = DEFERRED_TO_E4_9
```

**Esta tensão não foi resolvida e não deve ser apagada.** Ela
permanece visível aqui de propósito: um inventário de deferidos que
esconde a questão mais difícil da entrega não é inventário, é
maquiagem.

O conflito, em uma frase: `CausalHistoryEvent` é imutável por contrato
(`PIA-8020`) e sustenta `COUT-P4`; uma obrigação legítima de exclusão
que atinja conteúdo referenciado por eventos causais coloca dois
compromissos legítimos em rota de colisão.

O que **está** congelado, e vale desde já:

```
PRESERVATION = RETENTION FOREVER   ← FALSE
```

COUT não autoriza retenção ilimitada contra política legítima ou
obrigação de exclusão. O que COUT exige é que a exclusão seja
**explícita, registrada e distinguível** de inacessibilidade, extinção
causal e não-recuperação.

O que **não** está congelado: o mecanismo. As direções candidatas
estão em `E4_GOVERNANCE_BOUNDARIES.md` §6.2 — apagar o referente
preservando a referência; tombstone explícito; ou reconhecer um limite
nomeado e auditável.

**Atualização da E4.9.0 (cadeia 65).** A escolha entre as direções
deixou de estar aberta; o mecanismo continua não existindo. O que foi
congelado:

```text
AUTHORIZED_DIRECTION = A + B
OPTION_C = REJECTED_FOR_NORMAL_FLOW
ERASURE_RECORD = AUTHORIZED_NOT_IMPLEMENTED
```

A e B são complementares — A é o efeito no referente externo, B é o
recibo local do efeito observado. `B WITHOUT A = NO GROUND TO DECLARE
SUCCEEDED`; `A WITHOUT B = UNAUDITABLE ERASURE`.

**A tensão permanece aberta**, e continua visível aqui pela mesma razão
de antes. O que a E4.9.0 fez foi autorizar a primitiva de registro; ela
não criou Artifact Storage, porta, credencial, executor nem aprovação
verificável, e portanto nenhum apagamento é executável hoje:

```text
ERASURE_TARGET_OWNERSHIP_GAP        = OPEN
DESTRUCTIVE_EXECUTION_AUTHORITY_GAP = OPEN
LEGAL_ERASURE_CAUSAL_HISTORY_GAP    = OPEN_CONDITIONAL
```

Uma obrigação externa que atinja o próprio registro causal continua
sendo Stop Condition e exige EDR excepcional próprio.

**Atualização da E4.9.1 (cadeia 70).** A pergunta "o que o PIA-OS pode
afirmar que apaga?" deixou de estar em aberto **como contrato**; o
mecanismo continua não existindo. O que foi autorizado:

```text
ERASURE_TARGET_CUSTODY_CONTRACT = AUTHORIZED_NOT_IMPLEMENTED
ERASURE_TARGET_OWNERSHIP_GAP    = CLOSED_CANDIDATE_BY_AUTHORIZATION
```

Classificação fechada de alvos — `PIA_MANAGED_ARTIFACT`,
`AUTHORIZED_CONNECTOR_REFERENT`, `COGNITIVE_METADATA_RECORD`,
`UNRESOLVED_OPAQUE_REFERENCE` —, descritor transitório que nunca
persiste o localizador, e duas portas distintas em que **resolver é
observacional**.

```text
TECHNICAL_CUSTODY  != LEGAL_OWNERSHIP
REFERENCE          != RESOLVED TARGET
TARGET RESOLUTION  != DELETION AUTHORITY
DELETION AUTHORITY != EFFECT
```

**A tensão do §6 permanece aberta.** A E4.9.1 estabelece a entrada
necessária para decidi-la — sem saber o que é um alvo, não há como
decidir o que acontece quando uma obrigação alcança o registro causal —
mas não a decide:

```text
LEGAL_ERASURE_CAUSAL_HISTORY_GAP    = OPEN_CONDITIONAL
ON_EXPIRY_ACTION_UNRESOLVED         = OPEN
DESTRUCTIVE_EXECUTION_AUTHORITY_GAP = OPEN
```

**Atualização da E4.9.2 (cadeia 71).** O caminho **normal** da tensão foi
decidido: apagar o referente verificável, **preservar** história causal,
identidade e estrutura, e registrar o efeito observado num
`ErasureRecord` append-only sem FK para o sujeito.

```text
NORMAL_REFERENT_ERASURE_PRESERVES_CAUSAL_HISTORY = AUTHORIZED_NOT_IMPLEMENTED
LEGAL_ERASURE_CAUSAL_HISTORY_GAP  = CLOSED_CANDIDATE_CONDITIONAL
EXCEPTIONAL_CAUSAL_RECORD_ERASURE = DEFERRED_STOP_CONDITION
```

A história preserva **o rastro da passagem do conteúdo**, não a
informação para reconstituí-lo — e derivado reconstruível sob controle
(cópia, cache, réplica, embedding reversível, hash de relocalização)
é **alvo do efeito**, não rastro.

**A tensão do §6 não está encerrada.** A exceção que alcança o próprio
registro causal continua aberta por desenho, e nada foi implementado:

```text
ON_EXPIRY_ACTION_UNRESOLVED         = OPEN
DESTRUCTIVE_EXECUTION_AUTHORITY_GAP = OPEN
ERASURE_EXECUTOR = NONE   ARTIFACT_STORAGE = DEFERRED
```

**Atualização da E4.9.3 (cadeia 72).** `on_expiry` deixou de estar em
aberto: expiração **inicia avaliação**, e a decisão pertence ao usuário
ou principal humano autorizado.

```text
ON_EXPIRY_ACTION_UNRESOLVED = CLOSED_CANDIDATE_BY_AUTHORIZATION
AI_MODEL_DELETE_AUTHORITY   = NONE
AUTOMATIC_PERMANENT_ERASURE = FORBIDDEN
TRASH != LEGAL_ERASURE      TRASHED != SPACE RECLAIMED
```

Continua sem implementação — não há lixeira, executor, storage, conector,
`ErasureRecord`, parser ou voz — e **uma** Stop Condition segue aberta,
mais a exceção deferida:

```text
DESTRUCTIVE_EXECUTION_AUTHORITY_GAP = OPEN
EXCEPTIONAL_CAUSAL_RECORD_ERASURE   = DEFERRED_STOP_CONDITION
```

**Atualização da E4.9.3.1 (cadeia 73).** Acrescenta uma disposição de
**proteção histórica e legado**, sem reabrir `on_expiry` e sem alterar o
placar acima.

```text
LEGACY_ITEM != AUTOMATIC_CLEANUP_CANDIDATE
OLD != DISPOSABLE     INACTIVE != VALUELESS
BENEFICIARY != AUTHOR    STEWARDSHIP != OWNERSHIP
INACTIVITY != DEATH      AI_INFERENCE != SUCCESSION_PROOF
PIA_LEGACY_PLAN != LEGAL_WILL
```

Item marcado como legado fica fora de sugestão automática de limpeza por
idade, tamanho ou ausência de uso; retirar a proteção e excluir seguem
sendo decisões distintas, e nenhuma é do PIA. Registrar intenção de
transmissão é possível; **agir** sobre ela não, porque a autoridade
executiva continua aberta e a autoridade de sucessão é módulo futuro
próprio.

```text
LIFE_CAUSAL_LEGACY_CONTRACT         = AUTHORIZED_NOT_IMPLEMENTED
USER_DIRECTED_INHERITANCE_PLAN      = AUTHORIZED_NOT_IMPLEMENTED
POSTHUMOUS_EXECUTION_AUTHORITY      = NOT_AUTHORIZED
POSTHUMOUS_SUCCESSION_AUTHORITY     = SEPARATE_FUTURE_MODULE
DESTRUCTIVE_EXECUTION_AUTHORITY_GAP = OPEN
EXCEPTIONAL_CAUSAL_RECORD_ERASURE   = DEFERRED_STOP_CONDITION
```

**Atualização da E4.9.4 (cadeia 74).** A última Stop Condition **normal**
do preflight foi encaminhada: a autoridade destrutiva do usuário
presente tem contrato.

```text
DESTRUCTIVE_EXECUTION_AUTHORITY_GAP = CLOSED_CANDIDATE_BY_AUTHORIZATION
DESTRUCTIVE_AUTHORITY_CONTRACT      = AUTHORIZED_NOT_IMPLEMENTED
ACTOR PRESENCE != AUTHORIZATION     SESSION_PRESENCE != STEP_UP
POLICY_RESOLUTION != HUMAN_APPROVAL APPROVAL != EXECUTION
```

O contrato exige identidade de fronteira externa, step-up fresco para
exclusão permanente, aprovação específica/fresca/vinculada/de uso único,
e cinco estados separados em que nenhum implica o seguinte. **Nada
disso está implementado.**

Para a E4.9 sair do papel faltam, em runtime: fronteira de identidade e
autenticação; step-up; envelope de aprovação com consumo atômico;
orquestrador dos cinco estados; `ErasureRecord`; resolvedor de alvo;
`ArtifactStorage` e conectores; e `RetentionPolicy`.

```text
CONTRACTS CLOSED != MODULE READY
E4_9_IMPLEMENTATION = NOT_STARTED
EXCEPTIONAL_CAUSAL_RECORD_ERASURE = DEFERRED_STOP_CONDITION
POSTHUMOUS_SUCCESSION_AUTHORITY   = SEPARATE_FUTURE_MODULE
```

**Atualização da E4.9.5 (cadeia 75).** Primeira fatia de **runtime** da
E4.9. `erasure_records` existe, é append-only em ORM, repositório e
PostgreSQL, e **ninguém escreve nela**.

```text
ERASURE_RECORD_FOUNDATION     = COMPLETE_CANDIDATE
ERASURE_RECORD_RUNTIME_WRITER = NOT_COMPOSED
ERASURE_EFFECT                = NONE
E4_9_IMPLEMENTATION           = IN_PROGRESS_NOT_OPERATIONAL
```

Continuam ausentes em runtime: identidade e autenticação, step-up,
envelope e registro de aprovação, orquestrador dos cinco estados,
resolvedor de alvo e portas de efeito, `ArtifactStorage` e conectores,
`RetentionPolicy` e lixeira.

```text
ERASURE_RECORD_PERSISTENCE != ERASURE_EXECUTION
ERASURE_RECORD_PERSISTENCE != DELETION_AUTHORITY
ERASURE_RECORD_PERSISTENCE != RETENTION_POLICY
```

**Atualização da E4.9.6 (cadeia 76).** Segunda fatia de **runtime**.
`retention_policies` existe, é versionada e append-only em ORM,
repositório e PostgreSQL — e **ninguém a lê para agir**.

```text
RETENTION_POLICY_RUNTIME      = PERSISTED_LOCAL_VERSIONED
EXPIRY_BEHAVIOR               = ASSESS_AND_INFORM_ONLY
RETENTION_EVALUATOR           = NOT_COMPOSED
TRASH_RUNTIME                 = NONE
DESTRUCTIVE_EFFECT            = NONE
ERASURE_RECORD_RUNTIME_WRITER = NOT_COMPOSED
```

A âncora é `created_at`, única desta versão: o preflight mediu que
`updated_at` se move por transição de acessibilidade, e ancorar
retenção nele faria um objeto reclassificado rejuvenescer.

```text
RETENTION_POLICY_PERSISTENCE != RETENTION_EVALUATION
RETENTION_EVALUATION         != USER_DECISION
USER_DECISION                != DESTRUCTIVE_EXECUTION
```

Continuam deferidos: avaliação, lixeira, seleção por tamanho/data,
identidade e step-up, envelope e registro de aprovação, orquestrador
dos cinco estados, resolvedor de alvo, `ArtifactStorage`, conectores,
parser de texto e voz.

---

## Atualização aditiva — E4.9.8.3 (cadeia 88)

Lacuna **antecedente** fechada: a proteção de legado integrava o binding nos
documentos da E4.9.4 e não existia no runtime.

```text
LEGACY_PROTECTION_STATE_IN_DESCRIPTOR = IMPLEMENTED_CANDIDATE
LEGACY_PROTECTION_STATE_IN_SNAPSHOT   = IMPLEMENTED_CANDIDATE
LEGACY_PROTECTION_STATE_SOURCE        = ONE
LEGACY_PROTECTION_DEFAULT             = NONE
UNKNOWN_AS_NOT_PROTECTED              = FORBIDDEN
SAFE_TARGET_SNAPSHOT_MATERIALIZER     = IMPLEMENTED_CANDIDATE
```

Continuam deferidos, e esta fatia **não** os toca:

```text
LEGACY_PROTECTION_PERSISTENCE   = NONE
LEGACY_PROTECTION_UI            = NONE
LEGACY_PROTECTION_AS_BLOCKER    = NOT_MODELED
EFFECTIVE_APPROVAL_INVALIDATION = DEFERRED_TO_E4_9_9_D
APPROVAL_PERSISTENCE            = NONE
ERASURE_EFFECT_PORT             = NONE
RETENTION_EVALUATOR             = NOT_COMPOSED
ERASURE_RECORD_RUNTIME_WRITER   = NOT_COMPOSED
```

```text
STRUCTURAL_DISTINGUISHABILITY = IMPLEMENTED_HERE
EFFECTIVE_INVALIDATION        = DEFERRED_TO_E4_9_9_D
PROTECTED_IS_AUTOMATIC_DENIAL     = FALSE
PROTECTED_IS_AUTOMATIC_PERMISSION = FALSE
```

A proteção pertence ao usuário: retirar proteção e excluir são decisões
distintas, e o PIA não retira proteção como efeito colateral de uma proposta
destrutiva.

---

## Atualização aditiva — E4.9.9.a (cadeia 90)

```text
APPROVAL_RECORD_PERSISTENCE   = IMPLEMENTED_CANDIDATE
ATOMIC_SINGLE_USE_CONSUMPTION = IMPLEMENTED_CANDIDATE
ATOMIC_REVOCATION             = IMPLEMENTED_CANDIDATE
REPLAY_AFTER_RESTART          = BLOCKED_CANDIDATE
APPROVAL_PERSISTENCE_TABLES   = 3
```

Continuam deferidos, e esta fatia **não** os toca:

```text
ERASURE_EFFECT_PORT           = NONE            (E4.9.9.b)
OBSERVED_ATTEMPT_RESULT       = NONE            (E4.9.9.b)
RETENTION_EVALUATOR           = NOT_COMPOSED    (E4.9.9.c)
DESTRUCTIVE_ORCHESTRATOR      = NONE            (E4.9.9.d)
FRESH_TARGET_RE_RESOLUTION    = NONE            (E4.9.9.d)
ERASURE_RECORD_RUNTIME_WRITER = NOT_COMPOSED    (E4.9.9.d)
AUTHENTICATOR / IdP / STEP_UP = NONE
TRASH_RUNTIME / API / UI      = NONE
```

```text
PERSISTED_APPROVAL != EXECUTION
CONSUMED_APPROVAL  != OBSERVED_ERASURE_ATTEMPT
EXPIRY_IS_DERIVED_NOT_STORED
REVOCATION = DURABLE_STATE_TRANSITION, NEVER_ROW_REMOVAL
```

Limites declarados: o binding compara o que foi **persistido**, não o
mundo — TOCTOU segue aberto até a E4.9.9.d; `IdentityEvidence` continua
**representando** evidência externa, sem verificá-la.
