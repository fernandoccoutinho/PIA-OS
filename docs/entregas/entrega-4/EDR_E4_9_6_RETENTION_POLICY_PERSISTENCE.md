# EDR E4.9.6 — `RetentionPolicy` Contract and Persistence

**Natureza:** segunda fatia de **runtime** da E4.9. Persiste a regra e
nada mais.
**Baseline:** cadeia 75 (`74fe1ae8`), auditada como
`E4_9_5_AUDIT = PASS_FINAL`.

```text
RETENTION_POLICY_PERSISTENCE != RETENTION_EVALUATION
RETENTION_EVALUATION         != USER_DECISION
USER_DECISION                != DESTRUCTIVE_EXECUTION
```

```text
RETENTION_POLICY_RUNTIME      = PERSISTED_LOCAL_VERSIONED
EXPIRY_BEHAVIOR               = ASSESS_AND_INFORM_ONLY
RETENTION_EVALUATOR           = NOT_COMPOSED
TRASH_RUNTIME                 = NONE
DESTRUCTIVE_EFFECT            = NONE
ERASURE_RECORD_RUNTIME_WRITER = NOT_COMPOSED
```

---

## 1. Fatos medidos da baseline

```text
HEAD ecb… → 74fe1ae88a7ea5c3473a7fa9db0f49519daeec77
PARENT ecb630b0…   TREE 34196039…   PATCH_ID 087316e6…
ALEMBIC_HEAD 9d4f1a7c2be8   árvore limpa
FULL 2559 passed / 1 skipped / 0 failed
RAW  2150 passed / 410 skipped / 0 failed
PIA-8042 e PIA-8043: zero ocorrências em app/ e tests/
to_regclass('retention_policies') = NULL
to_regclass('erasure_records')    = erasure_records
```

`RetentionPolicy` aparecia apenas em **docstrings** de
`accessibility_policy.py` e `erasure_record.py`, declarando sua
ausência. Nenhum escritor composto em `ErasureRecordRepository`.

**Correção de uma imprecisão minha, apontada pela auditoria da cadeia
75:** o EDR anterior registrou `RAW 2149/409` quando o medido é
`2150/410`. A causa foi colher o número **antes** de acrescentar os
dois últimos testes de cobertura. Os números deste EDR foram colhidos
depois de todo o código estar escrito, e conferidos contra a soma dos
itens coletados.

---

## 2. Decisões de schema

### 2.1 Enums de um único membro são deliberados

`RetentionAnchor` e `RetentionExpiryAction` têm **um** membro. Não é
provisório: um enum unitário transforma qualquer ampliação futura em
mudança explícita de contrato.

Onde isso mais importa é em `RetentionExpiryAction`. Se ele nascesse
com dois ou três membros "por simetria", acrescentar `DELETE` depois
pareceria natural. Nascendo com um, acrescentar exige justificar por
que a decisão da E4.9.3 — auditada como `CLOSED_FINAL` — deixou de
valer.

```text
EXPIRY_TRIGGERS_ASSESSMENT_NOT_DELETION
```

Não existem, nem devem existir sem novo contrato: `DELETE`, `ERASE`,
`TRASH`, `MARK_INACCESSIBLE`, `ARCHIVE`, `NOTIFY_AND_DELETE`,
`AUTO_CLEANUP`.

### 2.2 `CREATED_AT` é a única âncora — e a razão foi medida

```text
UPDATED_AT != RETENTION_ANCHOR
```

O preflight da E4.9 mediu, em PostgreSQL real: `created_at` é estável
entre transações, através de mutação de `accessibility` e de soft
delete. `updated_at` **se move** — muda por transição de
acessibilidade, que não tem relação nenhuma com a idade do patrimônio.
Ancorar retenção nele faria um objeto reclassificado rejuvenescer.

A armadilha que produziu essa lição também merece registro: a primeira
medição foi feita dentro de **uma** transação, e `updated_at` "não se
moveu" — porque `now()` do PostgreSQL é o timestamp de início da
transação.

### 2.3 Escopo explícito, nunca vazio-como-curinga

```text
ALL_LOCAL_PATRIMONY -> domain_ids VAZIO
MEMORY_DOMAIN_SET   -> domain_ids NÃO VAZIO
EMPTY SET != WILDCARD
```

A E4.3 usa vazio-como-curinga em `GovernanceRule`, e ali é adequado: o
efeito de uma regra ampla demais é uma permissão ou recusa, que o
usuário observa. Aqui o efeito é elegibilidade à avaliação de **todo**
o patrimônio local, e um campo esquecido não deveria produzir isso em
silêncio.

A matriz é validada nos **dois** sentidos. Só proibir o vazio em
`MEMORY_DOMAIN_SET` deixaria passar um `ALL_LOCAL_PATRIMONY` com
domínios listados — que pareceria restrito e não seria.

`ALL_LOCAL_PATRIMONY` inclui conceitualmente patrimônio sem domínio
algum: `ZERO DOMAIN MEMBERSHIP != NONEXISTENCE`, congelado na E4.1.

### 2.4 Regras não vazias, sem `default`

`rules` não tem `default=list`. Uma policy publicada sem regra não
expressa retenção alguma, e ausência de policy já representa ausência
de regra aplicável. Um default de lista vazia tornaria trivial
publicar uma policy que **parece** regular algo e não regula nada.

### 2.5 A regra é deliberadamente pobre

Não filtra por tamanho, extensão, pasta, uso recente, conversa,
projeto, legado ou estado de validação. Não por irrelevância, mas
porque os schemas que as sustentariam **não existem** — uma regra que
citasse `VALIDATED_CURRENT` hoje citaria algo que `RevisionStatus` não
tem (medido: `['current', 'superseded']`).

Seleção e ordenação por tamanho ou data pertencem à avaliação e à
lixeira futuras, não à policy persistente.

### 2.6 Nenhuma FK

Zero FKs, provado em integração. `governance_policy_key` é texto pelo
mesmo raciocínio de `AccessibilityPolicy`: uma FK apontaria para a
linha de uma versão específica e congelaria a autoridade numa versão
que pode ter sido sucedida — o oposto do versionamento que a E4.3
estabeleceu. `domain_ids` é escopo declarativo: persistir a policy não
é avaliar patrimônio, e verificar existência de domínio aqui faria a
publicação depender de um estado que a avaliação futura reconsultará
de qualquer forma.

---

## 3. Alternativas rejeitadas

| # | Alternativa | Por que foi rejeitada |
|---|---|---|
| 1 | JSON livre como contrato de regra | é a Stop Condition 12 da E4.3: deixa a ferramenta definir a semântica |
| 2 | `on_expiry_action` com `DELETE` disponível "para o futuro" | prescreveria ação inexistente e contradiria decisão auditada |
| 3 | `updated_at` como âncora | medido: se move por transição de acessibilidade |
| 4 | `domain_ids` vazio como curinga | escopo total por omissão é o oposto de explícito |
| 5 | FK para `GovernancePolicy` | congelaria a autoridade numa versão sucedida |
| 6 | FK para `MemoryDomain` | faria publicar policy depender de estado que a avaliação reconsulta |
| 7 | `rules` com `default=list` | permitiria policy que parece reter e não retém |
| 8 | repositório lendo o relógio | consultar qual regra valia não é decidir que está na hora de agir |
| **9** | **tipos fechados, escopo explícito, sem FK, sem relógio** | **adotada** |

---

## 4. Prova de que `on_expiry` só avalia e informa

Quatro camadas independentes:

1. **vocabulário** — `RetentionExpiryAction` tem um membro, e ele é
   `ASSESS_AND_INFORM`;
2. **guarda estática** — `test_s03` verifica ausência de dez nomes
   destrutivos no enum;
3. **superfície do repositório** — `test_u35` verifica que
   `evaluate`, `assess`, `expire`, `notify`, `trash`, `erase`,
   `delete_target`, `cleanup`, `purge`, `apply` e `run` **não existem**
   em `dir(RetentionPolicyRepository)`;
4. **ausência de relógio** — `test_s10` percorre a AST e verifica que
   o repositório nunca chama `now`, `utcnow` ou `today`.

`effective_version_at` recebe o instante por argumento justamente por
isso: um repositório que lesse o relógio sozinho estaria a um passo de
agir sozinho.

```text
POLICY_MATCH != DELETION_CANDIDATE_CONFIRMED
```

---

## 5. Matriz de campos e constraints

| Campo | Contrato | Constraint no banco |
|---|---|---|
| `policy_key` | identidade lógica, ≤256, não vazia | `ck_..._policy_key_not_blank`, índice |
| `version` | `int` real (não `bool`), ≥1 | `ck_..._version_positive`, `UNIQUE(key, version)` |
| `governance_policy_key` | referência lógica, sem FK | `ck_..._governance_key_not_blank` |
| `rules` | JSON canônico de regras tipadas, não vazio | `NOT NULL` |
| `effective_from` | tz-aware, opcional | — |
| `effective_until` | tz-aware, opcional, **exclusivo** | `ck_..._effective_window` |

**Limite declarado honestamente.** O banco garante que `rules` é JSON
válido e não nulo. A **forma** das regras é garantia do tipo, na
serialização — um `INSERT` bruto com JSON estruturalmente válido e
semanticamente inválido entra, e a desserialização tipada é quem o
recusa depois. `test_i20` documenta exatamente isso, em vez de afirmar
uma constraint que o banco não tem.

Isto é diferente da E4.9.5, onde acrescentei `CHECK` explícito de
vocabulário porque os valores eram escalares verificáveis. Aqui a
estrutura é aninhada, e um `CHECK` sobre JSON aninhado seria ou
incompleto ou um validador reimplementado em SQL.

---

## 6. Imutabilidade: três camadas

| Camada | Mecanismo | O que pega |
|---|---|---|
| 1 | eventos `before_update` / `before_delete` | mutação por fora do repositório — defeito real da E4.3.1 |
| 2 | repositório | `update`, `delete`, `delete_by_id`, `soft_delete`, `bulk_update`, `bulk_delete` |
| 3 | trigger PostgreSQL | `UPDATE`/`DELETE` em SQL bruto |

Função e trigger têm **nomes próprios** de retenção
(`reject_retention_policy_mutation`,
`trg_retention_policies_append_only`), não compartilhados com
`erasure_records`. Compartilhar faria o downgrade de uma tabela
derrubar a proteção da outra, e a mensagem de erro citaria a tabela
errada.

As policies antigas (`governance_policies`, `accessibility_policies`)
**não** ganharam trigger nesta fatia — retroagir nelas é escopo de
outra entrega, e o prompt proíbe.

```text
NEW POLICY VERSION = INSERT
POLICY CORRECTION  = NEW VERSION
UPDATE/DELETE      = FORBIDDEN
```

---

## 7. Guardas que envelheceram

Treze testes falharam, **nenhum** por regressão de comportamento:

| Guarda | O que afirmava | O que fiz |
|---|---|---|
| 5 pins de migration head | head é `9d4f1a7c2be8` | atualizado para `c8a3f5017e94` com nota |
| `ci28`, `ri25`, `pi13` | conjunto exato de tabelas | acrescentado `retention_policies`; continuam exigindo conjunto EXATO |
| `ci27`, `ri24` | head único e inalterado | atualizado; protegem ausência de branching |
| `ii16` | drift + single head | atualizado |
| `gi435` | `retention_policies` **não existe** | invertido para "existe, criada por `c8a3f5017e94`"; o que passa a ser protegido é a **autoria**, e o guarda irmão `test_e435_production_diff_is_confined_to_the_enum_module` segue provando que a E4.3.5 não tocou produção |
| `test_e435` (unit) | nada em `app/memory` menciona `RetentionPolicy` | isentei **apenas** os arquivos autorizados; `RetentionAssessment`, `RetentionDecision`, `assess_retention`, `dispose`, `erase` e `forget` seguem proibidos **em todos** os arquivos, inclusive nos novos |
| **`test_s08`** (minha, da E4.9.5) | `class RetentionPolicy` não existe | removido `RetentionPolicy` da lista — **a guarda fez exatamente o que devia**, acusou a chegada da fatia seguinte |
| **`i21`/`i22`** (minhas, da E4.9.5) | head `9d4f1a7c2be8`; `downgrade -1` remove `erasure_records` | `downgrade -2`, porque `erasure_records` deixou de ser a última migração |

Nenhuma asserção foi afrouxada. As duas guardas minhas que falharam
são o caso mais interessante: escrevi-as na fatia anterior justamente
para que a chegada de `RetentionPolicy` fosse **notada**, e foram.

`app/cognitive` permanece byte a byte idêntico (`git diff` vazio).

---

## 8. Correção minha durante a fatia

Minhas próprias guardas estáticas falharam por **falso positivo**:
`test_s02` e `test_s11` procuravam `ErasureRecordRepository` e
`CognitiveObject` por busca textual, e acusaram as docstrings dos
novos módulos — que citam nominalmente o que eles **não** fazem.

É o mesmo falso positivo que a E4.3.1 corrigiu em `gv16` e que a
guarda da E4.3.5 já resolve. Adotei a mesma solução do projeto:
comparar o **código executável**, com as docstrings removidas via AST.

---

## 9. Gates medidos

Em clone limpo com PostgreSQL recriado, contagens medidas e não
derivadas:

```text
FULL_SUITE       2653 passed / 1 skipped / 0 failed
RAW_SUITE        2219 passed / 435 skipped / 0 failed
GLOBAL_COVERAGE  99,20%   (era 99,17% — subiu)
  retention_enums.py               100%
  retention_policy.py              100%
  retention.py (schemas)           100%
  retention_policy_repository.py   100%
RUFF PASS   BLACK PASS   MYPY 7 históricos em 3 arquivos, NEW = 0
ALEMBIC single head c8a3f5017e94
migration upgrade → downgrade → upgrade limpo, sem função órfã,
  e `erasure_records` intacta durante todo o round trip
git diff --check CLEAN
```

**Regressões, delta 0:** E3 = 732 · E4.1 = 40 · E4.2 = 42 · E4.3 = 255 ·
E4.4 = 74 · E4.5 = 187 · E4.6 = 275 · E4.7 = 240 · E4.8 = 146 ·
**E4.9.5 = 113**.

Fatia nova: **94** (58 unitários + 25 integração + 11 estáticos),
rodados três vezes com resultado idêntico.

---

## 10. Arquivos e LOC

**Novos (produção):** `retention_enums.py` 107 ·
`retention_policy.py` 258 · `schemas/retention.py` 148 ·
`retention_policy_repository.py` 222 · migration 125 = **860 linhas**.

**Novos (testes):** unit 433 · integração 414 · estáticos 213 =
**1060 linhas**.

**Modificados:** `errors/codes.py`, `errors/exceptions.py`,
`models/__init__.py` (exports), mais 10 arquivos de teste com guardas
atualizadas — 162 inserções, 18 remoções.

---

## 11. Riscos que declaro por conta própria

**(a) A policy existe e nada a lê.** Mesmo estado da E4.9.5, e a
mesma fragilidade social: duas primitivas prontas e inertes convidam a
"só ligar o avaliador". A diferença é que agora existe uma tabela cujo
conteúdo *parece* acionável — alguém pode publicar uma policy de 30
dias e supor que algo acontecerá. Nada acontecerá, e isso precisa
estar visível para quem publicar.

**(b) `effective_version_at` desempata janelas sobrepostas.** Publicar
janelas sobrepostas continua **possível**: nada no banco impede. O
desempate pela maior versão torna a resposta determinística, mas não
corrige a sobreposição — e uma interface futura que apresente "a
policy vigente" sem avisar que há duas declaradas mentiria por
omissão.

**(c) `domain_ids` referencia domínios que podem não existir.** Escopo
declarativo sem FK é escolha (§2.6), e o preço é que uma policy pode
citar um `MemoryDomain` inexistente ou removido. A avaliação futura
precisará tratar isso como **observação**, não como erro nem como
escopo vazio silencioso.

**(d) A forma das regras não é garantida pelo banco.** `test_i20`
prova que um `INSERT` bruto com JSON inválido entra e só falha na
leitura tipada. Isso é aceitável para configuração local escrita pela
aplicação — mas não seria se um dia alguém alimentasse esta tabela por
script de migração de dados.

---

## 12. Capacidades ainda ausentes

```text
RETENTION_EVALUATOR           = NOT_COMPOSED
TRASH_RUNTIME                 = NONE
DESTRUCTIVE_EFFECT            = NONE
ERASURE_RECORD_RUNTIME_WRITER = NOT_COMPOSED
```

Continuam ausentes em runtime: avaliação de retenção; lixeira;
fronteira de identidade e autenticação; step-up; envelope e registro
de aprovação; orquestrador dos cinco estados; resolvedor de alvo e
portas de efeito; `ArtifactStorage` e conectores.

Nenhuma rota, nenhum endpoint, nenhum parser de texto ou voz. Sync não
contém `retention_policies` nem `erasure_records` —
`RETENTION_POLICY_SYNC = NONE`, porque autoridade não é transferível.

`RevisionStatus`, `CausalEventType` e `CognitiveOperation`
inalterados. `VALIDATED_CURRENT` continua sem existir, e nada nesta
fatia o pressupõe.

---

## 13. Estado

```text
PATCH_CHAIN = 76
MIGRATION_HEAD = c8a3f5017e94
E4_9_6_IMPLEMENTATION = COMPLETE_CANDIDATE
E4_9_6_STATUS         = AWAITING_INDEPENDENT_AUDIT
RETENTION_POLICY_RUNTIME = PERSISTED_LOCAL_VERSIONED
E4_9_IMPLEMENTATION = IN_PROGRESS_NOT_OPERATIONAL
E4_10_IMPLEMENTATION = NOT_STARTED
```

```text
RETENTION_POLICY_PERSISTENCE != RETENTION_EVALUATION
RETENTION_EVALUATION         != USER_DECISION
USER_DECISION                != DESTRUCTIVE_EXECUTION
```

Não se declara `PASS_FINAL`, E4.9 pronta, avaliação executável, lixeira
ou qualquer efeito destrutivo.
