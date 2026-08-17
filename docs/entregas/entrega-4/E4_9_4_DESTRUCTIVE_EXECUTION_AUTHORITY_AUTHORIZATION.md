# E4.9.4 — Present-User Destructive Execution Authority Authorization

**Natureza:** entrega **exclusivamente documental**.
**Fecha:** a última Stop Condition **normal** do preflight da E4.9.
**Baseline:** `PATCH_CHAIN = 73` · HEAD `9b2e07385d9d…` ✓ ·
PARENT `6c759f05133d…` ✓ · TREE `9e7d2febac9b…` ✓ ·
PATCH_ID `dec9719bb41a…` ✓ · bundle SHA-256 `d7bedfac…eae4f1` ✓ ·
migration head `7b2e4c9a15df` ✓ · clone direto no HEAD ✓ · árvore limpa ✓

Baseline reproduzida com PostgreSQL 16 real, banco recriado:
**2446 passed / 1 skipped / 0 failed**, RAW **2073 / 374**.

Decisão arquitetural integral em
`EDR_E4_9_4_DESTRUCTIVE_EXECUTION_AUTHORITY.md`.

```text
DESTRUCTIVE_AUTHORITY_CONTRACT      = AUTHORIZED_NOT_IMPLEMENTED
DESTRUCTIVE_EXECUTION_AUTHORITY_GAP = CLOSED_CANDIDATE_BY_AUTHORIZATION
POSTHUMOUS_SUCCESSION_AUTHORITY     = SEPARATE_FUTURE_MODULE
E4_9_IMPLEMENTATION                 = NOT_STARTED
```

---

## 1. Verificação da baseline (§2.3 e §2.4 do prompt)

Medido no código e no banco, não presumido.

**`actor_ref` continua descritivo.** `app/memory/schemas/memory_context.py`
declara: *"Quem opera — **entrada descritiva**, não ator autorizado"*,
com `ACTOR PRESENCE != AUTHORIZATION`.

**Existe estrutura de autenticação; não existe autenticador.** Este
achado precisa ficar registrado com precisão, porque é fácil lê-lo ao
contrário:

| Presente na baseline | O que de fato é |
|---|---|
| `PIA-7001 AUTHENTICATION_ERROR` | código declarado em `error_codes.py` |
| `AuthenticationException` | classe em `exceptions/api.py`, **nunca levantada** em `backend/app` |
| `TAG_AUTHENTICATION` | tag OpenAPI com `placeholder=True` |
| `app/security/` (11 arquivos) | cabeçalhos, CORS, hosts confiáveis, validação, sanitização, rate limiting, segredos — o docstring diz: *"Sem login, usuários, OAuth, JWT ou permissões"* |
| `jwt` | só num validador de configuração |
| `password` | só na montagem da URL do banco e na lista de campos redigidos em log |
| `identity` (20 ocorrências) | **identidade cognitiva** (COID/CLID, integridade, contexto) — `memory_context.py` congela `CONTEXT != IDENTITY` |

```text
ERROR CODE EXISTS   != AUTHENTICATOR EXISTS
SECURITY MIDDLEWARE != IDENTITY PROVIDER
```

Zero ocorrências de `authn`, `authz`, `passkey`, `biometric`, `mfa`,
`step_up`, `nonce`, `approval`, `approve`, `idp`.

**Tabelas.** `to_regclass` devolve `NULL` para `approval_records`,
`destructive_approvals`, `identities`, `principals`,
`retention_policies` e `erasure_records`.

**`LEGAL_ERASURE` é representável e não é poder.** `CognitiveOperation`
tem 11 membros, incluindo `retention_assessment`,
`retention_disposition` e `legal_erasure`. Nomear a operação permitiu à
governança resolvê-la (E4.3.5); não executa nada.

```text
OPERATION IS REPRESENTABLE != OPERATION IS PERMITTED
POLICY RESOLVES            != HUMAN APPROVES
```

---

## 2. As seis equivalências proibidas

```text
actor_ref PRESENT == authenticated principal   → FALSO
session PRESENT   == destructive authority     → FALSO
policy ALLOWS     == human consent             → FALSO
voice command     == identity proof            → FALSO
saved preference  == current approval          → FALSO
expiry            == permission to erase       → FALSO
```

A E4.9.4 **não promove** `actor_ref`. A autoridade vem de fronteira
externa, e este contrato descreve o que ela deve entregar — não a
constrói.

---

## 3. Contratos congelados

```text
DELETE_DECISION_OWNER     = USER
DESTRUCTIVE_APPROVER      = AUTHENTICATED_PRESENT_USER
AI_MODEL_DELETE_AUTHORITY = NONE

ASSESS != PROPOSE != AUTHORIZE != EXECUTE != RECEIPT

IDENTITY_PROVIDER       != AI_MODEL
AUTHENTICATION_EVIDENCE != CREDENTIAL
SESSION_PRESENCE        != STEP_UP
VOICE                   != IDENTITY_PROOF
ROLE_LABEL              != VERIFIED_POWER
NAME/EMAIL/GROUP/KINSHIP != POWER

CHANGED_SCOPE     = NEW_APPROVAL_REQUIRED
STALE_APPROVAL    = INVALID
REPLAYED_APPROVAL = INVALID
REVOKED_APPROVAL  = INVALID
CONSUMED_APPROVAL = INVALID_FOR_REUSE

APPROVAL_SCOPE_HASH != CONTENT_HASH
APPROVAL_SCOPE_HASH != LOCATOR

APPROVAL_RECORD   != ERASURE_RECORD
APPROVAL          != EXECUTION
POLICY_RESOLUTION != HUMAN_APPROVAL

IDP UNAVAILABLE = BLOCK, NEVER DEGRADE
AMBIGUITY = BLOCK, NEVER BEST EFFORT

POSTHUMOUS_SUCCESSION_AUTHORITY = SEPARATE_FUTURE_MODULE
NOT_INHERITED_FROM_E4_9_4
```

**"Presente"** = participação operacional na confirmação atual, não
sessão aberta. **"Apto a confirmar"** = capaz de revisar e responder ao
impacto apresentado; o PIA **não diagnostica capacidade civil**.

**Dual control não é universal.** Policy ou risco podem exigir aprovação
adicional, sempre de humanos identificados com poderes separados.

---

## 4. Envelope conceitual de aprovação

Requisitos para um futuro `DestructiveApprovalEnvelope` **ou
equivalente**. Nenhuma classe, schema, serialização, assinatura,
algoritmo ou banco escolhido.

Identificador opaco · principal autenticado com nível de assurance ·
tenant/domínio e finalidade · operação (`TRASH` reversível **ou** erasure
definitiva) · lote materializado com versão/estado de cada alvo · policy
e `GovernanceResolution` exatas · resolução **fresca** de custódia e
capacidade · impacto apresentado com quantidade e volume
conhecido/desconhecido · dependências, holds, conflitos e provedores
externos · canal apenas como proveniência · emissão, expiração e janela
de frescor · nonce, uso único e estado de consumo/revogação · prova de
confirmação **sem conteúdo, localizador ou segredo**.

**Volume desconhecido é registrado como desconhecido** — inventá-lo
apresentaria impacto falso ao humano que está autorizando, e o impacto
apresentado é justamente o que ele confirma.

---

## 5. Binding: o que exige nova aprovação

Item, lista ou filtro; ordenação que determine o lote; quantidade ou
volume; versão, estado **ou proteção de legado**; policy ou resolution;
custódia, conector ou provedor; lixeira versus erasure; dependência,
legal hold ou conflito; impacto apresentado; identidade, tenant, domínio
ou finalidade; janela de frescor.

A **proteção de legado** entrou na lista por decisão desta entrega: um
item que perca a proteção da E4.9.3.1 entre aprovação e execução mudou
de natureza, e a aprovação anterior descrevia outro mundo.

---

## 6. Texto e voz

Convergem ao mesmo envelope. Voz é intenção e proveniência, **não**
prova de identidade; biometria de voz **não é autorizada**.

Fluxo futuro para erasure definitiva por voz: fala → transcrição
revisável → intenção normalizada → seleção exata materializada →
apresentação de impacto → **step-up seguro independente** → confirmação
explícita vinculada ao escopo → execução futura → recibo separado.

Bloqueiam: baixa confiança, ruído, homófono, alvo pronominal,
transcrição alterada, falha de step-up. **O mesmo comando digitado
recebe as mesmas exigências** — governança assimétrica criaria um
caminho preferencial, e o preferencial vira o único.

Exemplos paralelos, incluindo *"excluir permanentemente as dez maiores
imagens da lixeira"*, no EDR §8.1.

---

## 7. Os vinte casos e as dezenove ameaças

Os **20 casos obrigatórios** do §16 e as **19 ameaças** do §17 estão
tratados individualmente em tabela no EDR, §14 e §15, com decisão,
autoridade, binding, recusa e limite atual.

**Todos os vinte terminam hoje em recusa por ausência de capacidade:**
não existe identidade, step-up, envelope, orquestrador, executor nem
recibo. As dezenove ameaças são **modeladas, não mitigadas**.

As dez recusas conceituais do §15 estão no EDR §12, **sem criar código
de erro** — `PIA-8041` segue livre.

---

## 8. Riscos declarados por conta própria

Quatro, detalhados no EDR §16:

1. **O contrato fecha o gap sem construir nada** — há distância enorme
   entre "definimos que step-up é obrigatório" e "há um step-up". O
   placar não deve ser lido como progresso de segurança.
2. **A estrutura de autenticação já presente convida ao erro** — quem
   olhar para `PIA-7001` e `app/security/` pode concluir que basta
   ligar. Não basta: a exceção nunca é levantada e o pacote declara por
   escrito que não faz login nem permissões.
3. **O step-up será o primeiro item cortado por atrito de produto** —
   "lembrar do step-up por 30 minutos" transforma aprovação específica
   em autorização ambiente; se for concedido, é mudança de contrato com
   EDR próprio, não ajuste de usabilidade.
4. **A re-resolução fresca pode ser sacrificada por custo** — é a única
   defesa contra TOCTOU, e é exatamente o que se proporá pular "quando
   nada mudou".

---

## 9. Compatibilidade com o Master v1.6

O adendo **Autoridade destrutiva do usuário presente v1.6** é
materialmente aplicável e foi aplicado integralmente: princípio,
principal humano, aprovação vinculada ao efeito, texto e voz, separação
de funções e limites.

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

---

## 10. Arquivos e escopo

Exatamente **quatro**, como manda o §19:

```text
docs/entregas/entrega-4/E4_9_4_DESTRUCTIVE_EXECUTION_AUTHORITY_AUTHORIZATION.md  (novo)
docs/entregas/entrega-4/EDR_E4_9_4_DESTRUCTIVE_EXECUTION_AUTHORITY.md            (novo)
docs/entregas/entrega-4/E4_GOVERNANCE_BOUNDARIES.md                              (§6.6 aditiva)
docs/entregas/entrega-4/E4_DEFERRED_INVENTORY.md                                 (linhas aditivas)
```

As duas atualizações são **estritamente aditivas**: §6.2, §6.3, §6.4 e
§6.5 permanecem íntegras, e nenhuma linha histórica do inventário foi
apagada ou reformulada.

```text
CODE_DELTA = 0        TEST_DELTA = 0
MIGRATION_DELTA = 0   SCHEMA_DELTA = 0
NEW_ENUM = NONE       NEW_ERROR_CODE = NONE
```

---

## 11. Gates medidos

Coletados em clone limpo com banco recriado, nunca derivados por
subtração:

```text
FULL_SUITE       2446 passed / 1 skipped / 0 failed
RAW_SUITE        2073 passed / 374 skipped / 0 failed
GLOBAL_COVERAGE  99,14%      APP_MEMORY 100%   APP_COGNITIVE 100%
RUFF PASS        BLACK PASS
MYPY 7 erros históricos em 3 arquivos, NEW = 0
DRIFT 5 passed   ALEMBIC single head 7b2e4c9a15df
git diff --check CLEAN
```

**Regressões, delta 0:**

```text
E3 = 732   E4.1 = 40   E4.2 = 42   E4.3 = 255   E4.4 = 74
E4.5 = 187   E4.6 = 275   E4.7 = 240   E4.8 = 146
```

**Árvores executáveis idênticas ao pai:**

```text
backend/app      b8e1eaa729134a1b151fe6045f4bd41cd090a95d
backend/tests    3a7bc98f6b0644c8287888738981128074113677
backend/alembic  65a066dea0925edc55ad88e0c774f56b1944254f
```

---

## 12. Placar das Stop Conditions

```text
RETENTION_OPERATION_AUTHORITY_GAP   = CLOSED_FINAL
RETENTION_RETRIEVAL_COMPOSITION_GAP = CLOSED_FINAL
ON_EXPIRY_ACTION_UNRESOLVED         = CLOSED_FINAL
ERASURE_AUDIT_PRIMITIVE_GAP         = CLOSED_CANDIDATE_BY_AUTHORIZATION
ERASURE_TARGET_OWNERSHIP_GAP        = CLOSED_CANDIDATE_BY_AUTHORIZATION
LEGAL_ERASURE_CAUSAL_HISTORY_GAP    = CLOSED_CANDIDATE_CONDITIONAL
DESTRUCTIVE_EXECUTION_AUTHORITY_GAP = CLOSED_CANDIDATE_BY_AUTHORIZATION  ← esta

EXCEPTIONAL_CAUSAL_RECORD_ERASURE   = DEFERRED_STOP_CONDITION
POSTHUMOUS_SUCCESSION_AUTHORITY     = SEPARATE_FUTURE_MODULE
```

**As sete Stop Conditions normais do preflight estão encaminhadas.**
Permanecem, por desenho, a exceção causal deferida e a autoridade de
sucessão como módulo futuro.

**Fechar contratos não constrói o módulo.** Para a E4.9 existir faltam,
em runtime: fronteira de identidade e autenticação; step-up; envelope de
aprovação com consumo atômico; orquestrador dos cinco estados;
`ErasureRecord`; resolvedor de alvo; `ArtifactStorage` e conectores; e
`RetentionPolicy`.

```text
CONTRACTS CLOSED != MODULE READY
```

---

## 13. Gate

```text
PATCH_CHAIN = 74
E4_9_4_IMPLEMENTATION = COMPLETE_CANDIDATE_DOCUMENTAL
E4_9_4_STATUS = AWAITING_INDEPENDENT_AUDIT
DESTRUCTIVE_AUTHORITY_CONTRACT = AUTHORIZED_NOT_IMPLEMENTED
DESTRUCTIVE_EXECUTION_AUTHORITY_GAP = CLOSED_CANDIDATE_BY_AUTHORIZATION
POSTHUMOUS_SUCCESSION_AUTHORITY = SEPARATE_FUTURE_MODULE
E4_9_IMPLEMENTATION = NOT_STARTED
E4_10_IMPLEMENTATION = NOT_STARTED
```

Não se declara `PASS_FINAL`, `CLOSED_FINAL`, autenticação implementada
ou executor.
