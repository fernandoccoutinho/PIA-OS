# E4.9.3.1 — Life Causal Legacy and User-Directed Inheritance Authorization

**Natureza:** entrega **exclusivamente documental**.
**Baseline:** `PATCH_CHAIN = 72` · HEAD `6c759f05133d…` ✓ ·
PARENT `041b152fbef2…` ✓ · TREE `b33603a07321…` ✓ ·
PATCH_ID `a63a64ce523d…` ✓ · bundle SHA-256 `4ccd2398…fcea7` ✓ ·
migration head `7b2e4c9a15df` ✓ · árvore limpa ✓

Baseline reproduzida com PostgreSQL 16 real, banco recriado:
**2446 passed / 1 skipped / 0 failed**, RAW **2073 / 374**.

Decisão arquitetural integral em
`EDR_E4_9_3_1_LIFE_CAUSAL_LEGACY_INHERITANCE.md`.

---

## 1. O que esta entrega autoriza

```text
LIFE_CAUSAL_LEGACY_CONTRACT    = AUTHORIZED_NOT_IMPLEMENTED
USER_DIRECTED_INHERITANCE_PLAN = AUTHORIZED_NOT_IMPLEMENTED
LEGACY_LIBRARY_VIEW            = AUTHORIZED_NOT_IMPLEMENTED
POSTHUMOUS_EXECUTION_AUTHORITY = NOT_AUTHORIZED
LEGAL_INSTRUMENT_INTEGRATION   = DEFERRED
CURRENT_IMPLEMENTATION_CLAIM   = NONE
```

O usuário poderá, quando implementado, reconstruir e organizar a
trajetória causal de sua vida produtiva; conectar experiências,
conhecimentos, decisões e obras; distinguir relato, documento,
confirmação e inferência; proteger itens de valor histórico contra
limpeza automática; criar uma Biblioteca do Legado; registrar instruções
revogáveis sobre privacidade, transmissão, administração, publicação e
exclusão futura; e definir beneficiários e administradores **sem** lhes
conceder automaticamente propriedade, autoria, credenciais ou execução.

---

## 2. Verificação da baseline (§2.3 e §2.4 do prompt)

Medido no código e no banco da cadeia 72, não presumido.

**Ausência confirmada.** Busca por palavra inteira em `backend/app`:

```text
legacy 0 · beneficiary 0 · beneficiario 0 · heir 0 · heranca 0
inheritance 0 · succession 0 · sucessao 0 · testament 0 · testamento 0
deceased 0 · death 0 · morte 0 · incapacity 0 · incapacidade 0
steward 0 · custodian 0 · publish 0 · publication 0
```

Três termos deram hits, e **nenhum** é o conceito em questão:
`legado` (2) aparece em `integrity_repository.py` no sentido de *dado
legado / restore legado*; `trigger` (1) é uma menção a trigger de banco
numa docstring de `causal_history.py`; `executor` (3) são o executor de
transformação da E3 e a frase da E4.3.5.1 dizendo que **nenhum executor
foi autorizado ou implementado**.

**Schema.** 11 tabelas declaradas: `accessibility_policies`,
`causal_histories`, `causal_history_events`, `cognitive_objects`,
`governance_policies`, `lineage_edges`, `memory_domain_memberships`,
`memory_domains`, `provenance_records`, `relationships`,
`transformation_records`. No banco real,
`to_regclass` devolve `NULL` para `retention_policies`,
`erasure_records`, `legacy_directives`, `beneficiaries` e
`legacy_items`.

**Enums.**

```text
RevisionStatus     = ['current', 'superseded']
CausalEventType    = ['created', 'transformed', 'compared', 'accessed']
AccessibilityState = ['active', 'latent', 'inaccessible', 'causally_extinct']
CognitiveOperation = 11 membros (inclui retention_assessment,
                     retention_disposition, legal_erasure)
VALIDATED_CURRENT em RevisionStatus = False
```

**`actor_ref`.** O próprio código o declara: *"Quem opera — **entrada
descritiva**, não ator autorizado"*, com `ACTOR PRESENCE !=
AUTHORIZATION`. Continua sem autenticação, identidade verificada ou
contrato de aprovação — e é por isso que nenhum beneficiário,
administrador ou gatilho pode ser reconhecido hoje.

---

## 3. Separações congeladas

```text
LEGACY_CAUSAL_HISTORY != CV
LEGACY_CAUSAL_HISTORY != FILE_BACKUP
LEGACY_CAUSAL_HISTORY != AI_GENERATED_BIOGRAPHY

LEGACY_LIBRARY          = COGNITIVE_LIBRARY_USER_VIEW
LEGACY_LIBRARY         != NEW_STORAGE
LEGACY_VIEW_MEMBERSHIP != CONTENT_DUPLICATION

OLD         != DISPOSABLE
INACTIVE    != VALUELESS
SUPERSEDED  != WITHOUT_HISTORICAL_VALUE
LEGACY_ITEM != AUTOMATIC_CLEANUP_CANDIDATE

USER_CONFIRMED_NARRATIVE != AI_DRAFT
CORRECTION               != HISTORICAL_ERASURE
QUALITY_REVIEW_NOTE      != CONTENT_BACKUP

READ_ACCESS           != STEWARDSHIP
STEWARDSHIP           != PUBLICATION_AUTHORITY
PUBLICATION_AUTHORITY != OWNERSHIP
BENEFICIARY           != AUTHOR

INACTIVITY          != DEATH
ABSENCE             != INCAPACITY
AI_INFERENCE        != SUCCESSION_PROOF
BENEFICIARY_MESSAGE != VERIFIED_TRIGGER
SCHEDULER_TIMEOUT   != POSTHUMOUS_AUTHORITY

PIA_LEGACY_PLAN    != LEGAL_WILL
OPERATIONAL_INTENT != AUTOMATIC_RIGHT_TRANSFER

CREDENTIALS     != INHERITABLE_CONTENT
SECRET_TRANSFER != LEGACY_TRANSFER
ACCOUNT_ACCESS  != CONTENT_INHERITANCE

LATEST_DIRECTIVE_TIMESTAMP        != VALID_DIRECTIVE
VALIDATED_CURRENT_LEGACY_DIRECTIVE = GOVERNING_INTENT
REVOCATION = NEW_CAUSAL_EVENT_NOT_HISTORICAL_ERASURE

EXPORT != RIGHT_TRANSFER
EXPORT != SOURCE_ERASURE
```

---

## 4. Vocabulário conceitual — não persistido

Nenhum enum foi criado. Nenhuma tabela, coluna ou modelo foi escolhido.

**Grau de confirmação:** `DOCUMENT_VERIFIED`, `USER_ATTESTED`,
`THIRD_PARTY_ATTESTED`, `PIA_INFERRED_UNCONFIRMED`, `DISPUTED`,
`UNKNOWN`.

**Modalidades de legado:** `PRESERVE_PRIVATE`, `SHARE_DURING_LIFETIME`,
`TRANSFER_READ_ONLY`, `TRANSFER_STEWARDSHIP`, `AUTHORIZE_PUBLICATION`,
`ERASE_ON_VERIFIED_TRIGGER`, `NO_POSTHUMOUS_TRANSFER`.

**Poderes separados:** visualizar; custodiar e organizar; publicar;
licenciar; transferir titularidade quando juridicamente possível;
excluir.

**Categorias iniciais da Biblioteca do Legado**, extensíveis pelo
usuário: trajetória profissional; formação acadêmica; empresas e
negócios; profissões e atividades; projetos e realizações; livros,
artigos e pesquisas; sites e produção digital; decisões, aprendizados e
contribuições; memórias e relatos pessoais; instruções autorais e de
legado.

**Elementos de uma diretiva futura:** identidade do beneficiário ou
administrador; vínculo e papel, sem inferir autoridade pelo vínculo
familiar; itens, coleções e versões exatas; modalidade e limites de
acesso; condições e gatilhos; duração, publicação, sublicença ou
proibições; itens explicitamente excluídos; instruções em caso de
conflito; versão vigente, substituições e revogações.

---

## 5. Casos e ameaças

Os **16 casos obrigatórios** do §17 e as **17 ameaças** do §18 estão
tratados em tabela no EDR, §5 e §6, com decisão, autoridade, bloqueio e
limite atual.

Sete casos terminam **hoje** em recusa explicada — beneficiário com
leitura, administrador sem titularidade, alegação de morte por terceiro,
conflito com legal hold, tentativa de transmitir segredo, publicação
autorizada e vinte e quatro meses sem login — porque
`DESTRUCTIVE_EXECUTION_AUTHORITY_GAP` e a autoridade de sucessão
continuam abertas.

As 17 ameaças são **modeladas, não mitigadas**: não existe beneficiário,
diretiva, gatilho, custódia, publicação ou executor em runtime.

---

## 6. Riscos declarados por conta própria

Quatro, detalhados no EDR §7 e resumidos aqui porque a próxima
implementação precisa herdá-los:

1. **A Biblioteca do Legado pode virar autobiografia assistida** — a
   confirmação precisa ser custosa o bastante para ser real, e o sistema
   deve mostrar quanto da narrativa nasceu de inferência.
2. **O plano será lido como testamento** por mais que se diga o
   contrário; a ressalva precisa chegar à interface em linguagem leiga,
   não ficar num EDR.
3. **`ERASE_ON_VERIFIED_TRIGGER` combina irreversibilidade com ausência
   do usuário** e merecerá autoridade *mais* estrita que a exclusão
   comum, não igual.
4. **Terceiros aparecem no legado sem terem escolhido aparecer** — um
   relato `USER_ATTESTED` sobre outra pessoa é dado pessoal que ela não
   forneceu; transmiti-lo a um beneficiário amplia o alcance. Não é caso
   de borda.

---

## 7. Compatibilidade com o Master v1.5

O adendo **Legado causal de vida e herança dirigida v1.5** é
materialmente aplicável a esta entrega, e foi aplicado integralmente:
finalidade, proveniência e grau de confirmação, preservação histórica,
Biblioteca do Legado, plano e transmissão, gatilhos e autoridade,
segredos e credenciais, alteração e revogação, e limite de capacidade.

O adendo de **entrada multicanal e envelope único de comando v1.3**
também se aplica, e da mesma forma que na E4.9.1:

```text
VOICE_IS_AUTHORITY = FALSE
NATURAL_LANGUAGE_REFERENCE != RESOLVED LEGACY DIRECTIVE
```

"Deixe tudo para minha filha" é **intenção expressa**, não diretiva
válida: não identifica beneficiário verificado, escopo, modalidade,
condição nem versão vigente. Nenhum código de voz, parser, envelope ou
interface foi criado.

```text
USER_AUTHORITY_PRESERVED = TRUE
SOPHIA_BRAND_PIA_OS_CODEBASE_PRESERVED = TRUE
AUTOMATION_SCOPE = NONE
PERSISTENCE_BEHAVIOR = NONE
APPROVAL_GATE_IMPLEMENTATION = NONE
OBSERVATION_PREPARATION_EXECUTION_DISTINGUISHED = TRUE
CURRENT_CAPABILITY_NOT_OVERSTATED = TRUE
FROZEN_MODULES_UNCHANGED = TRUE
```

---

## 8. Arquivos e escopo

Exatamente **quatro**, como manda o §20:

```text
docs/entregas/entrega-4/E4_9_3_1_LIFE_CAUSAL_LEGACY_INHERITANCE_AUTHORIZATION.md  (novo)
docs/entregas/entrega-4/EDR_E4_9_3_1_LIFE_CAUSAL_LEGACY_INHERITANCE.md            (novo)
docs/entregas/entrega-4/E4_GOVERNANCE_BOUNDARIES.md                               (§6.5 aditiva)
docs/entregas/entrega-4/E4_DEFERRED_INVENTORY.md                                  (linhas aditivas)
```

As duas atualizações são **estritamente aditivas**: o §6.2 de 2026, a
§6.3 da E4.9.2 e a §6.4 da E4.9.3 permanecem íntegros, e nenhuma linha
histórica do inventário foi apagada ou reformulada.

```text
CODE_DELTA = 0        TEST_DELTA = 0
MIGRATION_DELTA = 0   SCHEMA_DELTA = 0
NEW_ENUM = NONE       NEW_ERROR_CODE = NONE
```

---

## 9. Gates medidos

Coletados em clone limpo com banco recriado, nunca derivados:

```text
FULL_SUITE       2446 passed / 1 skipped / 0 failed
RAW_SUITE        2073 passed / 374 skipped / 0 failed
GLOBAL_COVERAGE  99,14%       APP_MEMORY 100%   APP_COGNITIVE 100%
RUFF PASS        BLACK PASS (`black --check .`)
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

## 10. Placar das Stop Conditions

```text
RETENTION_OPERATION_AUTHORITY_GAP   = CLOSED_FINAL
RETENTION_RETRIEVAL_COMPOSITION_GAP = CLOSED_FINAL
ON_EXPIRY_ACTION_UNRESOLVED         = CLOSED_FINAL
ERASURE_AUDIT_PRIMITIVE_GAP         = CLOSED_CANDIDATE_BY_AUTHORIZATION
ERASURE_TARGET_OWNERSHIP_GAP        = CLOSED_CANDIDATE_BY_AUTHORIZATION
LEGAL_ERASURE_CAUSAL_HISTORY_GAP    = CLOSED_CANDIDATE_CONDITIONAL

DESTRUCTIVE_EXECUTION_AUTHORITY_GAP = OPEN
EXCEPTIONAL_CAUSAL_RECORD_ERASURE   = DEFERRED_STOP_CONDITION
POSTHUMOUS_SUCCESSION_AUTHORITY     = SEPARATE_FUTURE_MODULE
```

Esta entrega **não altera** o placar: acrescenta uma disposição de
proteção histórica e uma pendência nova, declarada.

---

## 11. Gate

```text
PATCH_CHAIN = 73
E4_9_3_1_IMPLEMENTATION = COMPLETE_CANDIDATE_DOCUMENTAL
E4_9_3_1_STATUS = AWAITING_INDEPENDENT_AUDIT
LIFE_CAUSAL_LEGACY_CONTRACT = AUTHORIZED_NOT_IMPLEMENTED
USER_DIRECTED_INHERITANCE_PLAN = AUTHORIZED_NOT_IMPLEMENTED
POSTHUMOUS_EXECUTION_AUTHORITY = NOT_AUTHORIZED
E4_9_IMPLEMENTATION = NOT_STARTED
E4_10_IMPLEMENTATION = NOT_STARTED
```

Não se declara `PASS_FINAL`, validade testamentária, implementação ou
autoridade póstuma.
