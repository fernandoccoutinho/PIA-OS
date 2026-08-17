# E4_9_3_DELETE_TIMING_TRASH_DISPOSITIONS_AUTHORIZATION

**Módulo:** E4.9.3 — Delete Timing, Trash and User Disposition Authorization
**Natureza:** **exclusivamente documental**
**Origem:** `ON_EXPIRY_ACTION_UNRESOLVED`, deferida desde a E4.0

```text
ON_EXPIRY_ACTION_UNRESOLVED        = CLOSED_CANDIDATE_BY_AUTHORIZATION
DELETE_DISPOSITION_CONTRACT        = AUTHORIZED_NOT_IMPLEMENTED
USER_COGNITIVE_PATRIMONY_AUTHORITY = AUTHORIZED_NOT_IMPLEMENTED
QUALITY_REVIEW_CAUSAL_NOTE         = AUTHORIZED_NOT_IMPLEMENTED
DESTRUCTIVE_EXECUTION_AUTHORITY_GAP = OPEN
E4_9_IMPLEMENTATION                = NOT_STARTED
```

**Baseline:** `PATCH_CHAIN = 71` · HEAD `041b152fbef2…` ✓ ·
PARENT `c4050501c6fe…` ✓ · TREE `2fe4016c5c7f…` ✓ ·
PATCH_ID `b3b2eeea3f6c…` ✓ · bundle SHA-256 `03165702…dceec` ✓ ·
migration head `7b2e4c9a15df` ✓ · clone direto no HEAD ✓ · árvore limpa ✓

Baseline reproduzida com PostgreSQL 16 real, banco recriado:
**2446 passed / 1 skipped / 0 failed**, RAW **2073 / 374**.

```text
backend/app              b8e1eaa729134a1b151fe6045f4bd41cd090a95d
backend/tests            3a7bc98f6b0644c8287888738981128074113677
backend/alembic          65a066dea0925edc55ad88e0c774f56b1944254f
docs/entregas/entrega-4  22d76c229b35211e5d27d73405a88bb48b798f27
```

---

## 1. Duas divergências registradas antes de tudo

**Caminhos dos entregáveis.** O §16 do prompt indica
`docs/entrega-4/...` e `E4_DEFERRED_CAPABILITIES_INVENTORY.md`. O
repositório real tem `docs/entregas/entrega-4/` e
`E4_DEFERRED_INVENTORY.md`. Pelo §3 do próprio prompt — *"código e
schema realmente presentes na cadeia 71"* precede o prompt — usei os
caminhos reais. Nenhum arquivo foi criado fora deles.

**Vocabulário de estados.** O §10 usa seis estados conceituais; o enum
persistido `RevisionStatus` tem **dois** (`current`, `superseded`).
`VALIDATED_CURRENT` **não existe** na E3, e `RevisionStatus.CURRENT`
significa "revisão corrente da cadeia", não "validado pelo usuário".

```text
CONCEPTUAL VOCABULARY  != PERSISTED VOCABULARY
RevisionStatus.CURRENT != VALIDATED_CURRENT
```

Nenhum enum foi criado. Materializar `VALIDATED_CURRENT` exigirá EDR
próprio, porque ampliar `RevisionStatus` toca a E3 congelada.

---

## 2. Evidência da baseline

```text
trash / lixeira / TrashItem / voice / voz / transcription   0 ocorrências
ArtifactStorage / connector / ErasureRecord / ErasureEffect 0
ErasureTargetResolver / scheduler / worker / outbox         0
on_expiry                                                   0
parser                                1 — docstring da E3.8 dizendo que
                                          a Search NÃO tem parser

RevisionStatus     = ['current', 'superseded']
CausalEventType    = ['created', 'transformed', 'compared', 'accessed']
AccessibilityState = ['active', 'latent', 'inaccessible', 'causally_extinct']
to_regclass('public.retention_policies') = NULL
to_regclass('public.erasure_records')    = NULL
```

---

## 3. Contratos e invariantes autorizados

```text
COGNITIVE_PATRIMONY_OWNER  = USER
DELETE_DECISION_OWNER      = USER_OR_AUTHORIZED_HUMAN_PRINCIPAL
PIA_ROLE                   = ORGANIZE_INFORM_RECOMMEND
AI_MODEL_DELETE_AUTHORITY  = NONE
AUTOMATIC_PERMANENT_ERASURE = FORBIDDEN

EXPIRY_TRIGGERS_ASSESSMENT_NOT_DELETION
RETENTION_POLICY != USER_DECISION
NO_AUTOMATIC_ACTION = PRESERVE_AND_REPORT
MARK_INACCESSIBLE   = REVERSIBLE_ACCESS_STATE_ONLY

TRASH   != LEGAL_ERASURE
TRASHED  = REVERSIBLE          TRASHED != SPACE RECLAIMED
ERASED   = IRREVERSIBLE_WITHIN_VERIFIED_SCOPE

COGNITIVE_LIBRARY_SEGMENTATION = EXTENSIBLE_USER_ORGANIZED_VIEWS
USER_EDITABLE_FOLDERS = REQUIRED
FOLDER_DELETION       != CONTENT_DELETION
CONVERSATION_DELETION != ARTIFACT_DELETION
USER_SELECTED_HISTORY_PRESERVATION = REQUIRED
UNSELECTED TRANSIENT INTERACTION  != AUTOMATIC MEMORY

LATEST_TIMESTAMP   != VALIDATED_VERSION
VALIDATED_CURRENT   = CANONICAL_ARTIFACT
CANONICAL_ARTIFACT != CLEANUP_CANDIDATE

QUALITY_REVIEW_NOTE = REQUIRED_PER_VERSION_TRANSITION
QUALITY_REVIEW_NOTE_SURVIVES = TRUE
DELETED_CONTENT_SURVIVES     = FALSE
QUALITY_REVIEW_NOTE != CONTENT_BACKUP != POST_ERASURE_SUMMARY

VOICE_IS_AUTHORITY = FALSE
TRANSCRIPTION_IS_COMMAND_CANDIDATE
ASR_ERROR_MUST_NOT_BECOME_CONSENT
AMBIGUOUS_ERASURE_SCOPE = NO_EXECUTION
```

---

## 4. Matriz de disposição

| Situação | Disposição autorizável | Requisito |
|---|---|---|
| item comum dispensável | lixeira primeiro | decisão informada |
| item ambíguo ou com dependência | bloquear | resolver impacto |
| versão canônica validada | preservar por padrão | confirmação reforçada |
| versão superada | candidata, não descartável automática | provar que não é fonte única |
| segredo ou risco ativo | quarentena → investigação → rota direta futura | autoridade e impacto próprios |
| obrigação legal válida | rota definitiva futura, sem lixeira | alvo/custódia/autoridade verificados |
| conversa | lixeira ou rota definitiva futura | separar conversa de derivados |
| pasta | remover/mover visão | nunca apagar conteúdo silenciosamente |
| conflito, legal hold, autoridade insuficiente | não apagar | explicar o bloqueio |

Momentos: `IMEDIATO E REVERSÍVEL` (lixeira) · `APÓS PRAZO` (retenção na
lixeira até data autorizada) · `IMEDIATO E IRREVERSÍVEL` (legal erasure
confirmado) · `NÃO EXECUTAR`.

---

## 5. Os dez casos obrigatórios

### Caso 1 — livro com V1, V2 e V3 `VALIDATED_CURRENT`

**Decisão:** V3 é o artefato canônico; V1 e V2 tornam-se `SUPERSEDED` e
**não** são apagadas por serem anteriores. DOCX mestre, PDF e EPUB da
mesma edição podem ser canônicos simultaneamente — não são duplicatas.
**Explicação ao usuário:** qual é a canônica atual, quais foram
superadas e o que cada exportação representa.
**Confirmação:** nenhuma — validar não apaga.
**Limite atual:** `VALIDATED_CURRENT` não existe no enum persistido
(§1); a proteção é contrato, não mecanismo.

### Caso 2 — excluir V1/V2 preservando as notas de revisão

**Decisão:** exclusão permitida como decisão do usuário, após provar que
não são fonte única nem dependência. As notas `V1→V2` e `V2→V3`
**permanecem**; o conteúdo das versões, não.
**Explicação:** o que se perde é a possibilidade de restaurar aquelas
versões — o rastro causal **não é backup**.
**Confirmação:** vinculada à lista exata de versões.
**Resultado conceitual:** história e notas preservadas; conteúdo
irrecuperável dentro do escopo confirmado.

### Caso 3 — sugerir exclusão da versão canônica

**Decisão:** **bloqueado como sugestão.** O canônico não entra em
proposta por tamanho, idade ou duplicidade presumida.
**Explicação:** se o usuário pedir explicitamente, o PIA mostra perda de
produto, publicações, dependências e reprodutibilidade.
**Confirmação:** reforçada e específica àquele artefato — nunca dentro
de um lote de limpeza.
**Ameaça coberta:** IA decidindo dispensabilidade.

### Caso 4 — dez maiores imagens da lixeira

**Decisão:** materializar a lista exata dos dez itens, com volume
verificável, dependências, derivados conhecidos e alvos externos.
**Explicação:** aviso de irreversibilidade e o que permanece como rastro
não reconstruível.
**Confirmação:** vinculada àquela lista.
**Limite atual:** não há lixeira; para alvos externos o tamanho pode ser
**desconhecido**, e o PIA não inventa tamanho nem espaço recuperável.

### Caso 5 — seleção alterada depois da confirmação

**Decisão:** a confirmação anterior é **invalidada**.

```text
CHANGING ITEM, FILTER, COUNT, DETERMINING ORDER OR SCOPE
INVALIDATES THE PRIOR CONFIRMATION
```

**Explicação:** o usuário confirmou *aquela* lista, não a operação em
abstrato.
**Confirmação:** nova, sobre a nova seleção.
**Ameaça coberta:** confirmação genérica reutilizada.

### Caso 6 — comando de voz ambíguo

*"Apague este arquivo."*

**Decisão:** **não executar.** Ambíguo quanto à reversibilidade.
**Explicação:** *"Deseja movê-lo para a lixeira, com possibilidade de
restauração, ou apagá-lo definitivamente?"*
**Confirmação:** só depois de a transcrição ser revisada e a intenção
desambiguada. Baixa confiança de ASR, ruído ou ambiguidade **bloqueiam**.
**Limite atual:** não há ASR nem parser.

### Caso 7 — remover pasta sem remover objetos

**Decisão:** remover a pasta retira apenas a **visão organizacional**.

```text
FOLDER_DELETION != CONTENT_DELETION
```

**Explicação:** a interface pergunta o destino dos itens ou os mantém na
Biblioteca; itens exclusivos, compartilhados, canônicos, dependentes e
externos aparecem **separadamente**.
**Confirmação:** sobre a pasta, não sobre o conteúdo.

### Caso 8 — conversa que originou artefato validado

**Decisão:** excluir a conversa **não** apaga o livro validado.
**Explicação:** quais artefatos derivaram dela; se algum prompt, fonte
ou anexo é necessário à reprodutibilidade; quais cópias podem existir em
provedores externos.
**Confirmação:** separada para conversa e para artefatos.
**Resultado conceitual:** por local — `SUCCEEDED`, `PARTIAL` ou
`USER_ACTION_REQUIRED`; nunca alegação de desaparecimento universal.

### Caso 9 — obrigação legal sem passar pela lixeira

**Decisão:** rota definitiva, **sem** etapa reversível — a lixeira não é
imposta quando a obrigação exige efeito definitivo.
**Explicação:** alvo, custódia, autoridade e escopo verificados; o que
permanece como rastro não reconstruível.
**Confirmação:** vinculada ao escopo, por principal humano com
autoridade.
**Limite atual:** **o efeito não é autorizado** —
`DESTRUCTIVE_EXECUTION_AUTHORITY_GAP = OPEN`, e não há executor,
storage ou conector. Hoje isso termina em recusa explicada.

### Caso 10 — nota de revisão com informação reconstruível

**Decisão:** **bloquear a nota.** Se ela copia trecho substancial,
guarda prompt capaz de regenerar o original ou funciona como substituto
semântico, deixa de ser rastro e **passa a integrar o alvo**.

```text
IF THE NOTE CAN RECOMPOSE THE CONTENT, IT IS CONTENT
```

**Explicação:** o usuário reescreve a nota em forma qualitativa.
**Confirmação:** do usuário sobre a nota corrigida.
**Se a própria nota estiver juridicamente no escopo:** aplica-se a Stop
Condition excepcional da E4.9.2 — a história causal **não** é mutilada
em silêncio.

---

## 6. Matriz requisito → documento → verificação

| # | Requisito | Onde | Verificação |
|---|---|---|---|
| §4 | autoridade do usuário | EDR §2, doc §3 | cinco marcadores; listas do que o PIA pode e não pode |
| §5 | expiração é avaliação | EDR §3 | fluxo de seis passos; cinco desfechos conceituais sem enum |
| §6 | motivos de candidatura | EDR §4 | dez motivos com evidência e coluna "basta para excluir?" |
| §7 | matriz de disposição | EDR §5, doc §4 | nove linhas; quatro momentos |
| §8 | lixeira | EDR §6 | segmentos, ordenações, dados por item, confirmação vinculada, prazo sem autoridade |
| §9 | Biblioteca Cognitiva | EDR §7 | oito tipos extensíveis; cinco linhas `!=` de pasta |
| §10 | versionamento | EDR §8 | seis estados conceituais + caso do livro |
| §11 | nota qualitativa | EDR §10 | seis campos; seis proibições; limite de admissibilidade |
| §12 | história após exclusão | EDR §11 | cinco itens que permanecem, cinco que não |
| §13 | conversas | EDR §9 | duas linhas `!=`; quatro informações prévias |
| §14 | texto e voz | EDR §12 | nove campos do envelope; exemplos paralelos |
| §17 | dez casos | doc §5 | os dez, com decisão/explicação/confirmação/limite |
| §18 | treze ameaças | EDR §14 | tabela ameaça → exigência |
| §16 | EDR separa fatos/decisão/alternativas/ameaças/capacidade/stop/E4.9.4 | EDR §1,2,13,14,15,16,17 | seções dedicadas |

---

## 7. Arquivos alterados

```text
docs/entregas/entrega-4/EDR_E4_9_3_DELETE_TIMING_TRASH_DISPOSITIONS.md            (novo)
docs/entregas/entrega-4/E4_9_3_DELETE_TIMING_TRASH_DISPOSITIONS_AUTHORIZATION.md  (novo)
docs/entregas/entrega-4/E4_GOVERNANCE_BOUNDARIES.md                                (aditivo)
docs/entregas/entrega-4/E4_DEFERRED_INVENTORY.md                                   (aditivo)
```

```text
PRODUCTION_TREE = IDENTICAL   TEST_TREE = IDENTICAL   ALEMBIC_TREE = IDENTICAL
MIGRATION_DELTA = 0   SCHEMA_DELTA = 0   ENUM_DELTA = 0
NEW_ERROR_CODE  = NONE   (NEXT_FREE_ERROR_CODE = PIA-8041)
```

---

## 8. Gates medidos

```text
FULL_SUITE       2446 passed / 1 skipped / 0 failed
RAW_SUITE        2073 passed / 374 skipped / 0 failed
GLOBAL_COVERAGE  99,14%   APP_MEMORY 100%   APP_COGNITIVE 100%
RUFF PASS   BLACK PASS   MYPY 7 históricos, NEW = 0   DRIFT 5 passed
ALEMBIC single head 7b2e4c9a15df   git diff --check CLEAN
```

**Regressões, delta 0:** E3 = 732 · E4.1 = 40 · E4.2 = 42 · E4.3 = 255 ·
E4.4 = 74 · E4.5 = 187 · E4.6 = 275 · E4.7 = 240 · E4.8 = 146.

---

## 9. Compatibilidade SOPHIA / PIA-OS (Master v1.4)

```text
USER_AUTHORITY_PRESERVED = TRUE
SOPHIA_BRAND_PIA_OS_CODEBASE_PRESERVED = TRUE
AUTOMATION_SCOPE = NONE          PERSISTENCE_BEHAVIOR = NONE
APPROVAL_GATE_IMPLEMENTATION = NONE
OBSERVATION_PREPARATION_EXECUTION_DISTINGUISHED = TRUE
CURRENT_CAPABILITY_NOT_OVERSTATED = TRUE
FROZEN_MODULES_UNCHANGED = TRUE

PIA_OS_INPUT_CHANNELS = TEXT | VOICE
SAME_COMMAND_ENVELOPE_FOR_ALL_CHANNELS = TRUE
VOICE_IS_AUTHORITY = FALSE
```

O adendo v1.4 (patrimônio cognitivo, exclusão e memória de revisão) é
**materialmente aplicável** e foi incorporado. Nenhum código de voz,
parser, lixeira ou interface foi criado.

---

## 10. Placar das Stop Conditions

```text
RETENTION_OPERATION_AUTHORITY_GAP   = CLOSED_FINAL
RETENTION_RETRIEVAL_COMPOSITION_GAP = CLOSED_FINAL
ERASURE_AUDIT_PRIMITIVE_GAP         = CLOSED_CANDIDATE_BY_AUTHORIZATION
ERASURE_TARGET_OWNERSHIP_GAP        = CLOSED_CANDIDATE_BY_AUTHORIZATION
LEGAL_ERASURE_CAUSAL_HISTORY_GAP    = CLOSED_CANDIDATE_CONDITIONAL
ON_EXPIRY_ACTION_UNRESOLVED         = CLOSED_CANDIDATE_BY_AUTHORIZATION  ← esta

DESTRUCTIVE_EXECUTION_AUTHORITY_GAP = OPEN
EXCEPTIONAL_CAUSAL_RECORD_ERASURE   = DEFERRED_STOP_CONDITION
```

Seis de sete encaminhadas; **uma aberta**, mais a exceção deferida.

---

## 11. Gate

```text
E4_9_3_IMPLEMENTATION = COMPLETE_CANDIDATE_DOCUMENTAL
E4_9_3_STATUS         = AWAITING_INDEPENDENT_AUDIT
PATCH_CHAIN           = 72
E4_9_IMPLEMENTATION   = NOT_STARTED
E4_10_IMPLEMENTATION  = NOT_STARTED
```

`PASS_FINAL`, `CLOSED_FINAL`, implementação de lixeira, suporte de voz e
liberação da E4.9 **não** são declarados aqui.
