# EDR E4.9.3 — Delete Timing, Trash and User Dispositions

**Natureza:** decisão arquitetural sobre **disposição e autoridade do
usuário**. **Somente documental.**
**Exigido por:** `ON_EXPIRY_ACTION_UNRESOLVED`, deferida desde a E4.0 e
confirmada pelo preflight da E4.9.
**Complementa, sem reescrever:** `EDR_COUT_PIA_E4.md`,
`E4_GOVERNANCE_BOUNDARIES.md` §6, `EDR_E4_9_0_...`, `EDR_E4_9_1_...`,
`EDR_E4_9_2_...`, `PIA_OS_SOPHIA_CANONICAL_MASTER_v1.4.md`.

```text
DELETE_DISPOSITION_CONTRACT        = AUTHORIZED_NOT_IMPLEMENTED
USER_COGNITIVE_PATRIMONY_AUTHORITY = AUTHORIZED_NOT_IMPLEMENTED
QUALITY_REVIEW_CAUSAL_NOTE         = AUTHORIZED_NOT_IMPLEMENTED
DESTRUCTIVE_EXECUTION_AUTHORITY_GAP = OPEN
```

---

## 1. Fatos da baseline (cadeia 71)

Verificados no código e no schema reais, não presumidos.

### 1.1 Nada do escopo desta entrega existe

Busca por palavra inteira em `backend/app`, ignorando `__pycache__`:

```text
trash / lixeira / TrashItem          0 ocorrências
voice / voz / transcription          0
ArtifactStorage / connector          0
ErasureRecord / ErasureEffect        0
ErasureTargetResolver                0
scheduler / worker / outbox          0
on_expiry                            0
parser                               1 — numa docstring da E3.8 dizendo que
                                         a Search NÃO tem parser
```

`on_expiry_action` existe **apenas** como item deferido em
`E4_DOMAIN_MODEL_DRAFT.md` §9 e `E4_DEFERRED_INVENTORY.md`. Não há
implementação a interpretar.

### 1.2 Vocabulários realmente persistidos

```text
RevisionStatus     = ['current', 'superseded']
CausalEventType    = ['created', 'transformed', 'compared', 'accessed']
AccessibilityState = ['active', 'latent', 'inaccessible', 'causally_extinct']
```

**Divergência que precisa ficar registrada.** O §10 do prompt e o §13 do
handoff usam seis estados conceituais — `DRAFT`, `CANDIDATE`,
`VALIDATED_CURRENT`, `SUPERSEDED`, `TRASHED`, `ERASED`. O enum
persistido tem **dois** membros. `VALIDATED_CURRENT` **não existe** na
E3; o que existe é `RevisionStatus.CURRENT`, cujo significado é
"revisão corrente da cadeia", não "artefato validado pelo usuário".

```text
CONCEPTUAL VOCABULARY != PERSISTED VOCABULARY
RevisionStatus.CURRENT != VALIDATED_CURRENT
```

Este EDR usa os seis nomes **como vocabulário conceitual**, conforme o
prompt manda, e **não cria enum**. A etapa que os materializar terá de
decidir se `VALIDATED_CURRENT` é um estado novo, um atributo separado de
validação ou uma projeção — e essa decisão exige EDR próprio, porque
ampliar `RevisionStatus` toca a E3 congelada.

### 1.3 Herdado das autorizações anteriores

- `ErasureRecord` autorizado e **não implementado** (E4.9.0);
- contrato de alvo e custódia autorizado, sem resolvedor nem executor
  (E4.9.1, `PASS_FINAL`);
- caminho normal de erasure decidido: referente apagado, história
  preservada (E4.9.2, `PASS_FINAL`);
- `to_regclass('public.retention_policies')` e
  `to_regclass('public.erasure_records')` continuam `NULL`.

---

## 2. Decisão do usuário: soberania sobre o patrimônio

```text
COGNITIVE_PATRIMONY_OWNER  = USER
DELETE_DECISION_OWNER      = USER_OR_AUTHORIZED_HUMAN_PRINCIPAL
PIA_ROLE                   = ORGANIZE_INFORM_RECOMMEND
AI_MODEL_DELETE_AUTHORITY  = NONE
AUTOMATIC_PERMANENT_ERASURE = FORBIDDEN
```

O PIA **pode**: organizar e localizar; apontar duplicatas e versões
possivelmente superadas; informar tamanho, idade, dependências e
consequências; propor lixeira ou exclusão definitiva; pedir confirmação
vinculada ao escopo.

O PIA **não pode**: decidir que o patrimônio "não vale mais"; apagar por
economia de espaço, idade ou expiração sem decisão do usuário; presumir
consentimento por preferência genérica; converter silêncio, ambiguidade,
baixa confiança de voz ou ausência de uso em autorização; executar
fisicamente apagamento.

Em contexto organizacional, "usuário" é o **principal humano com
autoridade comprovada** sobre aquele patrimônio. Nem o modelo de IA, nem
o canal, nem o scheduler, nem o conector são principal.

---

## 3. Expiração é avaliação, não exclusão

```text
EXPIRY_TRIGGERS_ASSESSMENT_NOT_DELETION
RETENTION_POLICY != USER_DECISION
NO_AUTOMATIC_ACTION = PRESERVE_AND_REPORT
MARK_INACCESSIBLE = REVERSIBLE_ACCESS_STATE_ONLY
```

Fluxo conceitual autorizado:

```text
expiry or cleanup signal
→ assess candidate
→ explain why and impact
→ present disposition choices
→ obtain scope-bound human decision
→ reversible trash OR future separately-authorized permanent-erasure path
```

A avaliação pode concluir `PRESERVE`, `ASK_LATER`,
`MOVE_TO_TRASH_CANDIDATE`, `DIRECT_ERASURE_CANDIDATE` ou `BLOCKED` —
**nomes conceituais**, não enum nem schema.

**`on_expiry` fica resolvido pelo que a baseline permite dizer com
verdade:** nenhuma ação destrutiva está implementada, então nenhuma pode
ser prescrita como automática. A resposta é *avaliar, explicar e pedir
decisão*.

---

## 4. Motivos de candidatura

Taxonomia **aberta e explicável**. Cada candidato expõe motivo e
evidência.

| Motivo | Evidência exigida | Basta para excluir? |
|---|---|---|
| duplicata verificável | comparação real, não nome parecido | não — decisão do usuário |
| versão superada | validação posterior explícita, **nunca timestamp isolado** | não |
| temporário/intermediário | classificação explícita | não |
| exportação regenerável | fonte preservada **e verificada** | não |
| item grande ou antigo | tamanho/idade | **jamais** — sinal informativo |
| sem uso aparente | telemetria de acesso | **jamais** — ausência de uso não prova dispensabilidade |
| obrigação legal | obrigação identificada | não decide sozinha a disposição |
| solicitação do usuário | pedido explícito | é decisão, não candidatura |
| conversa/anexo indesejado | escolha do usuário | sim, com as ressalvas da §9 |
| falha, corrupção, risco | diagnóstico | tratamento próprio (quarentena) |

```text
SIZE != DISPENSABILITY
AGE  != DISPENSABILITY
NO RECENT USE != NO VALUE
```

Motivos diferentes **não** produzem automaticamente a mesma disposição.

---

## 5. Matriz de disposição

| Situação | Disposição autorizável | Requisito |
|---|---|---|
| item comum dispensável | lixeira primeiro | decisão informada |
| item ambíguo ou com dependência | **bloquear** | resolver impacto antes |
| versão canônica validada | **preservar por padrão** | confirmação reforçada para qualquer exclusão |
| versão superada | candidata, **não** descartável automática | provar que não é fonte única/necessária |
| segredo ou risco ativo | quarentena → investigação → rota direta futura | autoridade e impacto específicos |
| obrigação legal válida | rota definitiva futura, **sem** passar pela lixeira | alvo/custódia/autoridade verificados |
| conversa | lixeira ou rota definitiva futura | separar conversa de artefatos derivados |
| pasta | remover/mover **visão** | nunca apagar conteúdo silenciosamente |
| conflito, legal hold, autoridade insuficiente | **não apagar** | explicar o bloqueio |

Momentos:

```text
IMEDIATO E REVERSÍVEL   = lixeira
APÓS PRAZO              = retenção na lixeira até data autorizada
IMEDIATO E IRREVERSÍVEL = legal erasure/efeito crítico confirmado
NÃO EXECUTAR            = conflito, hold, alvo ou autoridade insuficiente
```

Lixeira **não** é imposta quando a obrigação jurídica exige efeito
definitivo — e o efeito **não** é autorizado sem a futura autoridade
executiva (E4.9.4).

### 5.1 Condições de bloqueio

Prazo legal de conservação; processo/auditoria/legal hold;
compartilhamento com terceiros; dependência de outro trabalho; única
cópia conhecida; derivados que dependem do item; autoria/custódia não
resolvidas; alvo externo fora de controle verificável; cópias, caches,
réplicas ou derivados reconstruíveis; conflito entre policies.

```text
AMBIGUITY = BLOCK, NEVER BEST EFFORT
```

---

## 6. Lixeira

```text
TRASH   != LEGAL_ERASURE
TRASHED  = REVERSIBLE
ERASED   = IRREVERSIBLE_WITHIN_VERIFIED_SCOPE
```

Coleção lógica única com **vistas segmentadas**, não storages separados:
Todos, Documentos, Imagens/mídia, Conversas, Outros, e "Aguardando
exclusão permanente" — que é **ação/estado**, não tipo de arquivo.

Ordenações mínimas: tamanho, data de envio, data original, nome, prazo.
Filtros combináveis e busca. Por item, quando disponível e autorizado:
nome, tipo, tamanho, data original, data de envio, ator, projeto/origem,
prazo restante, cópias/derivados conhecidos, condição de restauração,
impedimentos.

Mover para a lixeira retira das vistas normais, **preserva os bytes**,
permite restauração e registra quem/quando/origem — e **não** pode ser
apresentado como espaço já recuperado.

```text
TRASHED != SPACE RECLAIMED
```

Para alvos externos o tamanho pode ser **desconhecido**; o PIA-OS não
inventa tamanho nem espaço recuperável.

### 6.1 Confirmação vinculada à seleção

Pedido: *"Excluir permanentemente as dez maiores imagens da lixeira."*

O PIA materializa a lista exata, apresenta volume verificável,
dependências, derivados, alvos externos e o aviso de irreversibilidade,
e pede confirmação **vinculada àquela lista**.

```text
CHANGING ITEM, FILTER, COUNT, DETERMINING ORDER OR SCOPE
INVALIDATES THE PRIOR CONFIRMATION
```

### 6.2 Prazo de esvaziamento

**Não é autoridade.** Um prazo configurável futuro só pode existir como
escolha prévia, explícita, informada, revisável e revogável — e ainda
assim produz **aviso/avaliação**, exigindo autorização compatível com
este contrato. Até que exista, o comportamento seguro é notificar e
aguardar.

```text
SCHEDULED EMPTYING != CONSENT
TIME PASSING       != CONSENT
```

---

## 7. Biblioteca Cognitiva

```text
COGNITIVE_LIBRARY_SEGMENTATION = EXTENSIBLE_USER_ORGANIZED_VIEWS
USER_EDITABLE_FOLDERS          = REQUIRED
FOLDER_DELETION               != CONTENT_DELETION
USER_SELECTED_HISTORY_PRESERVATION = REQUIRED
```

Tipos iniciais, extensíveis: projetos, documentos, pesquisas, textos,
exercícios, imagens e mídias, conversas preservadas, e tipos/pastas
criados pelo usuário. **Não formam enum universal fechado.**

Pastas são **visões organizacionais editáveis**. Um objeto pode aparecer
em mais de uma visão sem duplicação física.

```text
FOLDER != STORAGE  != MEMORY DOMAIN  != OWNERSHIP
MOVE BETWEEN FOLDERS != CONTENT MOVE
REMOVE FROM FOLDER   != DELETE CONTENT
```

Interação transitória não vira memória por existir:

```text
UNSELECTED TRANSIENT INTERACTION != AUTOMATIC MEMORY
```

Isso reafirma `TRANSCRIPT_AS_MEMORY = FALSE`, congelado desde a E3.

---

## 8. Versionamento e proteção do artefato válido

```text
LATEST_TIMESTAMP  != VALIDATED_VERSION
VALIDATED_CURRENT  = CANONICAL_ARTIFACT
CANONICAL_ARTIFACT != CLEANUP_CANDIDATE
```

Estados conceituais: `DRAFT`, `CANDIDATE`, `VALIDATED_CURRENT`,
`SUPERSEDED`, `TRASHED`, `ERASED` — **sem criar enum**, e com a
divergência da §1.2 registrada.

Regras: a versão validada é a que vale, mesmo havendo arquivo mais novo;
nova validação torna a anterior `SUPERSEDED`, **não** a apaga; versões
anteriores permanecem enquanto o usuário quiser histórico; DOCX mestre,
PDF de impressão e EPUB podem ser **simultaneamente válidos** e não são
duplicatas por pertencerem à mesma edição; validar nova versão é
operação **distinta** de apagar a anterior; o canônico não entra em
sugestão por tamanho, idade ou duplicidade presumida; excluí-lo exige
intenção específica, impacto e confirmação reforçada.

```text
RESTORATION REQUIRES PRESERVED CONTENT
CAUSAL TRACE IS NOT A BACKUP
```

### 8.1 Caso normativo — projeto de livro

```text
PROJETO LIVRO
├── manuscrito_v21_G.docx   VALIDATED_CURRENT / fonte canônica
├── livro_impressao.pdf     VALIDATED_CURRENT / publicação impressa
├── livro.epub              VALIDATED_CURRENT / publicação digital
├── manuscrito_v20.docx     SUPERSEDED / preservação conforme policy
├── rascunho_teste.docx     DRAFT / elegível à lixeira
└── conversas de produção   suporte/proveniência; avaliadas à parte
```

Uma ação "limpar versões antigas" deve mostrar quais são canônicas,
quais superadas e **o que se perde em reprodutibilidade**. Nunca
selecionar o artefato válido por ser grande ou antigo.

---

## 9. Conversas com o PIA e outras IAs

```text
CONVERSATION_DELETION != ARTIFACT_DELETION
ARTIFACT_DELETION     != CONVERSATION_DELETION
```

Antes de excluir uma conversa, informar: quais artefatos derivaram dela;
se algum prompt, fonte ou anexo é necessário à **reprodutibilidade**;
quais cópias podem existir em provedores externos; o que o PIA controla
e o que exige ação do usuário ou conector futuro.

Excluir a conversa **não** apaga o livro validado. Excluir o livro
**não** apaga automaticamente a conversa. Provedor externo tem resultado
**por local** — `SUCCEEDED`, `PARTIAL`, `USER_ACTION_REQUIRED` — e
jamais recebe alegação de desaparecimento universal sem evidência.

---

## 10. Memória qualitativa da revisão

```text
QUALITY_REVIEW_NOTE = REQUIRED_PER_VERSION_TRANSITION
QUALITY_REVIEW_NOTE_SURVIVES = TRUE
DELETED_CONTENT_SURVIVES     = FALSE
QUALITY_REVIEW_NOTE != CONTENT_BACKUP
QUALITY_REVIEW_NOTE != POST_ERASURE_SUMMARY
```

Não basta registrar `V1 → V2`. Cada transição carrega nota curta sobre
**o que foi revisto**:

```text
V1 → V2
QUALITY_REVIEW_NOTE = "Revisados o argumento central, as referências do
capítulo 3 e a conclusão; corrigida a inconsistência entre as seções 4 e 7."
```

Campos conceituais: versão de origem e resultante; texto curto do que
foi revisto/corrigido/acrescentado/descartado; motivo; ator e data;
estado de validação antes e depois; vínculo com parent,
`TransformationRecord` ou equivalente **existente**.

A nota **nasce durante a revisão**. É proibido fabricá-la depois da
exclusão a partir de inferência, cache ou conteúdo residual. O PIA pode
propor; o usuário edita e confirma quando a revisão afetar patrimônio
validado.

### 10.1 O limite que torna a nota admissível

A nota **não pode** guardar: texto substancial da versão; imagem, áudio
ou anexo; resumo que substitua semanticamente o documento; prompt ou
instrução suficiente para regenerar o original; embedding reversível,
hash relocalizador ou localizador funcional; segredo ou dado protegido
alcançado pela obrigação.

```text
IF THE NOTE CAN RECOMPOSE THE CONTENT, IT IS CONTENT
```

Uma nota que ultrapasse esse limite **deixa de ser rastro admissível** e
passa a integrar o alvo do apagamento. Se a própria nota estiver
juridicamente no escopo, aplica-se a Stop Condition excepcional da
E4.9.2 — **não se mutila a história causal em silêncio**.

---

## 11. História causal depois da exclusão

Pode permanecer: identidade histórica mínima admissível; relações de
versão, transformação e proveniência; nota qualitativa não
reconstruível; ator, data, motivo e estados de validação;
`ErasureRecord` separado, após tentativa material observada.

Não pode permanecer: conteúdo integral ou parcial reconstruível; cache,
réplica, miniatura ou derivado reversível; prompt/response apagado capaz
de recompor resultado; referência executável ou localizador vivo;
qualquer substituto material do objeto apagado.

```text
CAUSAL TRACE SURVIVES
QUALITY REVIEW MEMORY SURVIVES
RECONSTRUCTIBLE CONTENT DOES NOT
```

E3, `CausalEventType`, FKs e schemas **não foram alterados**.

---

## 12. Texto e voz — envelope único

```text
channel · normalized_intent · actor_identity · authority_context
target_selection · scope · reversibility · impact · confirmation_binding
```

Regras vinculantes: o canal **não** concede autoridade; voz gera
transcrição revisável para ação material; baixa confiança, ruído ou
ambiguidade **bloqueiam**; *"apague os arquivos antigos"* **não** é
seleção suficiente; a confirmação repete ação, alvo, quantidade/volume,
reversibilidade e impacto principal; mudança de seleção invalida
confirmação anterior; áudio e transcrição **não** viram memória
automática.

```text
VOICE_IS_AUTHORITY = FALSE
TRANSCRIPTION_IS_COMMAND_CANDIDATE
ASR_ERROR_MUST_NOT_BECOME_CONSENT
AMBIGUOUS_ERASURE_SCOPE = NO_EXECUTION
```

### 12.1 Exemplos paralelos, resultado idêntico

**Digitado:** `excluir permanentemente as 10 maiores imagens da lixeira`
**Falado:** *"Exclua permanentemente as dez maiores imagens da lixeira."*

Ambos convergem ao mesmo envelope, produzem a **mesma lista
materializada**, o mesmo impacto apresentado e a **mesma confirmação
vinculada**. O canal aparece no envelope apenas como proveniência.

**Digitado:** `apague este arquivo` — **Falado:** *"Apague este arquivo."*
Ambos são ambíguos quanto à reversibilidade, e ambos produzem a mesma
pergunta: lixeira com restauração, ou definitivo?

Nenhum código de voz, parser ou interface foi criado. A materialização
permanece na **E4.9.4**.

---

## 13. Alternativas descartadas

| # | Alternativa | Por que foi rejeitada |
|---|---|---|
| 1 | `on_expiry` executa a ação da policy automaticamente | transformaria configuração em consentimento; nenhuma ação destrutiva existe para executar |
| 2 | lixeira com esvaziamento automático por prazo | tempo decorrido não é decisão humana |
| 3 | IA seleciona descartáveis por tamanho/idade/uso | é exatamente a ameaça nº 1 da §14 |
| 4 | timestamp mais recente define a versão válida | rascunho salvo por acidente destronaria o canônico |
| 5 | apagar pasta apaga conteúdo | confunde visão com propriedade |
| 6 | uma confirmação genérica reutilizável | permite troca silenciosa de escopo |
| 7 | nota de revisão gerada após a exclusão, a partir do que restou | seria backup semântico do conteúdo apagado |
| 8 | criar enum de estados agora | tocaria a E3 congelada; exige EDR próprio (§1.2) |
| **9** | **avaliar, explicar e exigir decisão humana vinculada ao escopo** | **adotada** |

---

## 14. Ameaças tratadas

| Ameaça | O que o contrato exige |
|---|---|
| IA decide dispensabilidade | `AI_MODEL_DELETE_AUTHORITY = NONE`; PIA informa, usuário decide |
| expiração vira apagamento | `EXPIRY_TRIGGERS_ASSESSMENT_NOT_DELETION` |
| timestamp substitui a validada | `LATEST_TIMESTAMP != VALIDATED_VERSION` |
| pasta apagada leva conteúdo | `FOLDER_DELETION != CONTENT_DELETION` |
| confirmação genérica reutilizada | vínculo à seleção exata; mudança invalida |
| voz ambígua vira consentimento | bloqueio por baixa confiança/ambiguidade |
| lixeira apresentada como erasure | `TRASH != LEGAL_ERASURE`; `TRASHED != SPACE RECLAIMED` |
| conversa apagada destrói derivado | `CONVERSATION_DELETION != ARTIFACT_DELETION` |
| resumo de revisão vira backup | limite da §10.1 |
| `ErasureRecord` recebe conteúdo/localizador | proibido desde a E4.9.0 |
| referência volta a funcionar por cache | proibido desde a E4.9.2 |
| provedor externo como apagamento universal | resultado por local; `PARTIAL` conservador |
| resolução misturada com execução | portas separadas desde a E4.9.1 |

Todas são **modeladas**, não mitigadas: não há lixeira, executor nem
interface para mitigá-las.

---

## 15. Capacidade autorizada × não implementada

| Item | Estado |
|---|---|
| taxonomia de motivos e matriz de disposição | **autorizada**, não implementada |
| lixeira reversível | **autorizada**, não implementada |
| segmentação da Biblioteca Cognitiva e pastas editáveis | **autorizadas**, não implementadas |
| proteção do artefato canônico | **autorizada**, não implementada |
| nota qualitativa de revisão | **autorizada**, não implementada |
| envelope único texto/voz | **autorizado**, não implementado |
| `ErasureRecord`, descritor de alvo, portas | autorizados antes, não implementados |
| executor, storage, conector, credencial | **não autorizados** |
| scheduler, worker, outbox, saga | **não autorizados** |
| UI, parser, ASR | **não autorizados** |

```text
NOTHING IN THIS DELIVERY DELETES, TRASHES OR EXECUTES ANYTHING
```

---

## 16. Riscos e decisões abertas

**Risco 1 — a lixeira parecer conclusão.** Um usuário que envia 40 GB à
lixeira pode acreditar que recuperou espaço. `TRASHED != SPACE
RECLAIMED` precisa aparecer na interface, não só aqui.

**Risco 2 — `VALIDATED_CURRENT` sem lastro no schema.** Enquanto o enum
persistido tiver dois membros, "artefato canônico" é promessa
documental. Uma implementação apressada que use `RevisionStatus.CURRENT`
como se fosse validação do usuário confundiria duas coisas distintas —
e o §8 inteiro dependeria de uma equivalência falsa.

**Risco 3 — a nota de revisão crescer até virar backup.** O limite da
§10.1 é qualitativo e será tensionado por quem quiser "não perder
contexto". Precisa de verificação real na etapa que a implementar.

**Continua aberto:**

```text
ON_EXPIRY_ACTION_UNRESOLVED         = CLOSED_CANDIDATE_BY_AUTHORIZATION
DESTRUCTIVE_EXECUTION_AUTHORITY_GAP = OPEN
EXCEPTIONAL_CAUSAL_RECORD_ERASURE   = DEFERRED_STOP_CONDITION
```

---

## 17. Implicações para a E4.9.4

A E4.9.4 herda deste EDR obrigações concretas: materializar o envelope
único; provar identidade e autoridade do principal humano; vincular a
confirmação a uma seleção exata e invalidá-la a qualquer mudança;
distinguir lixeira de erasure em toda superfície; manter resolução
observacional separada da execução; e produzir `ErasureRecord` apenas
após efeito observado, com `PARTIAL` conservador.

E herda uma decisão que **não** foi tomada aqui: **quem** pode autorizar
efeito destrutivo e **como** essa autoridade é verificada.
`MemoryContext.actor_ref` continua sendo, pelo texto do próprio código,
"entrada descritiva, não ator autorizado".

```text
DESTRUCTIVE_EXECUTION_AUTHORITY_GAP = OPEN
```
