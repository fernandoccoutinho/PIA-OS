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
| `on_expiry_action` de retenção | E4.9 | tensão com `CausalHistory` não resolvida — o preflight da E4.9 devolveu `ON_EXPIRY_ACTION_UNRESOLVED`, que **permanece aberta** |
| **conciliação legal erasure × `CausalHistory`** | **E4.9** | `LEGAL_ERASURE_VS_CAUSAL_HISTORY = DEFERRED_TO_E4_9` — ver §6. **Direção congelada em A + B pela E4.9.0**; C rejeitada para o fluxo normal. A tensão **não** está fechada |
| primitiva de auditoria de apagamento (`ErasureRecord`) | **E4.9** | **AUTORIZADA prospectivamente pela E4.9.0** (`EDR_E4_9_0_ERASURE_AUDIT_PRIMITIVE.md`). `IMPLEMENTATION_STATUS = AUTHORIZED_NOT_IMPLEMENTED`; nenhuma tabela, migração ou código existe |
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
