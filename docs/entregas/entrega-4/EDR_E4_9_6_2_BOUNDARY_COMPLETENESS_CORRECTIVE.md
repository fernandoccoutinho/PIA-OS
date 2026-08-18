# EDR E4.9.6.2 — Boundary Completeness

**Natureza:** corretivo dos achados da auditoria independente da E4.9.6.1.
Não é fatia funcional nova.
**Baseline:** cadeia 77 (`3407c774`), `E4_9_6_1_AUDIT = FAIL_CORRECTIVE_REQUIRED`.

```text
TYPE DECORATOR BOUNDARY != ORM ASSIGNMENT BOUNDARY
ANNOTATED TYPE          != RUNTIME TYPE PROOF
VALIDATED OPAQUE KEY    != NORMALIZED KEY
```

```text
A3B_DIRECT_ORM_BOUNDARY = FIXED   (defeito bloqueante)
A3A_UNICODE_BOUNDARY    = HARDENED (endurecimento autorizado)
A3C_CHARACTERIZATION    = FIXED   (bilateral, sem traceback)
MIGRATION_DELTA = 0   DATABASE_SCHEMA_DELTA = 0   E3_DELTA = 0
EVALUATOR_DELTA = 0   EFFECT_DELTA = 0   API_DELTA = 0
```

O A3b é defeito meu e é real. O A3a **não** é descumprimento retroativo: a
E4.9.6.1 fechou exatamente C0+DEL, que era o contrato que ela tinha. A
auditoria autorizou ampliar, e este documento mantém as duas coisas
separadas porque confundi-las falsearia o histórico.

---

## 1. Bloco de compatibilidade exigido pelo Master v1.7 §0.4

```text
PIA_OS_SOPHIA_MASTER_COMPATIBILITY
├── USER_AUTHORITY_PRESERVED ................ SIM. Nada nesta fatia decide
│     apagar. `on_expiry_action` continua unitário em ASSESS_AND_INFORM.
├── SOPHIA_BRAND_PIA_OS_CODEBASE_PRESERVED .. SIM. Nenhum identificador de
│     marca entrou no código; SOPHIA é produto, PIA-OS é a base.
├── MODULE_SCOPE_AND_DEFERRED_CAPABILITIES ... Escopo: fronteiras de
│     validação de `rules` e de identificador opaco. Diferidas: avaliador,
│     lixeira, aprovação, efeito, resolução de alvo.
├── SCHEDULE_MODE_DECLARED ................... N/A — corrective only.
├── AI_ROLE_AND_STEP_INSTRUCTION_DISTINGUISHED N/A — corrective only.
├── PROVIDER_CONNECTION_METHOD_DECLARED ...... N/A — corrective only.
├── AUTOMATION_SCOPE_DECLARED ................ NENHUMA. Sem relógio, sem
│     scheduler, sem consumidor. Guarda `s10` e `s20` provam.
├── APPROVAL_GATES_DECLARED .................. N/A — nada nesta fatia executa.
├── PERSISTENCE_BEHAVIOR_DECLARED ............ Append-only inalterado: mapper
│     event, override de repositório e trigger PostgreSQL seguem idênticos.
├── MULTI_AI_RESULT_ATTRIBUTION_DECLARED ..... N/A — corrective only.
├── DIVERGENCE_PRESERVATION_DECLARED ......... Duas sequências Unicode
│     distintas nunca são fundidas (`test_u69`). Sem normalização.
├── CONCURRENT_WORK_ISOLATION_DECLARED ....... `UNIQUE(policy_key, version)`
│     inalterada; teste de concorrência da E4.9.6 preservado.
├── BACKGROUND_EXECUTION_AUTHORIZATION ....... NENHUMA execução em segundo
│     plano foi introduzida.
├── RESOURCE_LIMITS_QUEUE_AND_COST_DECLARED .. N/A — corrective only.
├── REMOTE_RESOURCE_SCOPE_DECLARED ........... NENHUM. `RETENTION_POLICY_SYNC
│     = NONE` e `PORTABLE = FALSE` seguem valendo (`s05`).
├── OBSERVATION_PREPARATION_EXECUTION ........ Distinguidos: persistir policy
│     é preparação; não há observação de patrimônio nem execução.
├── CREDENTIAL_AND_SECRET_BOUNDARY_DECLARED .. N/A. O validador é opaco de
│     propósito e não interpreta a chave como segredo ou localizador.
├── FAILURE_ROLLBACK_AND_CONCURRENCY ......... Recusa de atribuição não
│     corrompe: valor anterior preservado (`test_u56`, `test_i33`).
├── CURRENT_CAPABILITY_NOT_OVERSTATED ........ Este EDR corrige uma frase
│     minha da E4.9.6.1 que afirmava garantia inexistente. Ver §3.
└── FROZEN_MODULES_UNCHANGED ................. `app/cognitive` e
      `backend/alembic` byte a byte idênticos.
```

Registro de processo: o §2 do prompt pede este bloco **antes** de escrever.
Eu implementei antes de redigi-lo e o apresento aqui. Nenhuma linha acima
mudou uma decisão de código — se tivesse mudado, o correto seria refazer, não
documentar depois.

---

## 2. Baseline verificada

```text
HEAD 3407c774aa3b791d6fbbc4d380f2fec4259780ac
PARENT 83f31ba0…  TREE f0da6a4f…  PATCH_ID eb59a213…  PATCH_CHAIN 77
MIGRATION_HEAD c8a3f5017e94   árvore limpa
app/cognitive  be407b46f679a009e0f7f7e9f01fb784f08dea54
backend/alembic cc68c3e274f388bda2a8674d6432d515bb8cbc4a
```

Caracterização antes de tocar em código:

```text
A3A_UNICODE_INVISIBLES_ACCEPTED=REPRODUCED
A3B_DIRECT_ORM_MUTABLE=REPRODUCED
DEFECTS_REPRODUCED=2   EXIT=0
```

Confirmado que **nenhum consumidor runtime** avalia `RetentionPolicy`: os
únicos importadores dos quatro módulos são eles mesmos (`s01`, `s16`, `s20`).

---

## 3. A3b — o defeito, e por que ele passou

### 3.1 Reprodução na cadeia 77

```text
RetentionPolicy(rules=[{...}])
type(policy.rules)          = list
type(policy.rules[0])       = dict
type(policy.typed_rules[0]) = dict      # anotado tuple[RetentionRule, ...]
policy.rules[0]["minimum_age_days"] = 0 → ACEITO
```

### 3.2 A causa

`RetentionRulesType` é um `TypeDecorator`, e um `TypeDecorator` corre em
`process_bind_param` e `process_result_value` — **disco**. Um objeto
construído em Python e nunca gravado nem carregado não atravessa nenhuma das
duas. A E4.9.6.1 pôs o congelamento no tipo da coluna e escreveu na docstring
que "não há `list[dict]` pública em momento algum, nem na escrita". Era falso,
e a frase foi corrigida no código.

Não é coincidência de forma: é a terceira vez que declaro uma garantia e cubro
só a fronteira que estava em foco. Na E4.6.3.1 protegi o retorno e deixei o
argumento; na E4.9.6.1 protegi a persistência e deixei a leitura; aqui protegi
disco e deixei memória. A lição de método que registrei na E4.9.6.1 —
enumerar **todas** as fronteiras — eu registrei e não apliquei ao próprio
corretivo que a registrou.

### 3.3 A correção

Um contrato único, `validar_regras_retencao(nome, valor)`, em
`schemas/retention.py`, chamado por **três** fronteiras:

| fronteira | mecanismo |
|---|---|
| atribuição (construtor e `setattr`) | `@validates("rules")` |
| ida ao disco | `process_bind_param` |
| leitura defensiva | `typed_rules` |

Contrato: `tuple` exata, não vazia, todo item `RetentionRule`, sem `rule_id`
duplicado. Devolve a **mesma** tupla, sem reordenar — a ordem canônica é
imposta na serialização, e reordenar aqui faria o valor observado divergir do
declarado pelo chamador.

`list` é recusada de propósito. Aceitá-la reintroduziria coleção mutável como
representação pública legítima, e converter em silêncio faria a violação
parecer válida — a mesma razão pela qual a E4.6.2 recusou converter
`Iterable` em `Sequence`.

`@validates` **não** corre no carregamento: o `loading` do SQLAlchemy popula o
`__dict__` sem evento de atributo. É correto que seja assim — quem valida o
que vem do banco é `process_result_value`, que reconstrói pelo construtor
tipado. As duas fronteiras não se sobrepõem e nenhuma fica descoberta.

### 3.4 Alternativas rejeitadas

- **Só o `TypeDecorator`, como estava.** É o defeito.
- **`RetentionPolicyView` com confinamento total.** Já rejeitada na E4.9.6.1 e
  continua rejeitada: exigiria sobrescrever os sete métodos herdados com
  retorno incompatível com `BaseRepository[ModelType]`, fechando no mypy só com
  `type: ignore` novo (Stop Condition 8) ou alterando `BaseRepository`
  (Stop Condition 4).
- **Congelar todos os escalares do ORM.** O prompt dispensa explicitamente, e
  seria escopo novo: `version` e `policy_key` já são protegidos pelo
  append-only na escrita.
- **Cópia rasa na leitura.** `tuple` externo com `dict` interno continua
  mutável — mascarar, não corrigir.

### 3.5 Erros deixaram de ser incidentais

```text
cadeia 77:  bind(list[dict]) → AttributeError: 'dict' object has no attribute 'rule_id'
cadeia 78:  bind(list[dict]) → TypeError do contrato

cadeia 77:  result([{"lixo": True}]) → KeyError
cadeia 78:  result([{"lixo": True}]) → ValueError nomeando as chaves faltantes
```

`deserialize_rules` passou a recusar item que não seja objeto JSON e item sem
as seis chaves obrigatórias, com índice e nomes na mensagem.

---

## 4. A3a — endurecimento Unicode

A E4.9.6.1 recusava `ord(c) < 32 or ord(c) == 127`, que é exatamente C0+DEL —
cumpriu o contrato que tinha. O que a auditoria mostrou é que o **argumento**
daquele contrato ("uma chave assim se apresenta de uma forma em log, de outra
em exportação e de uma terceira numa interface") vale igual para tokens que
passavam:

```text
cadeia 77:  U+0085 NEL · U+2028 LS · U+200B ZWSP · U+202E RLO  → ACEITOS
cadeia 78:  categorias Cc, Cf, Zl, Zp                          → RECUSADAS
```

A inspeção é por `unicodedata.category`, que **classifica**. Nunca
`unicodedata.normalize`, que **transformaria** — e a guarda `s15` proíbe
`normalize`, `casefold`, `lower()`, `upper()`, `NFC/NFD/NFKC/NFKD`,
`translate` e `encode` no corpo do validador, exigindo `category` presente.

Preservado e provado: tipo exatamente `str`, não vazio, teto 256, valor
devolvido byte a byte (`is` com o original), `Zs` permitido, português
acentuado permitido, e duas sequências Unicode distintas nunca fundidas —
`ação` pré-composta e decomposta continuam sendo duas chaves.

`Zs` ficou fora da lista de propósito: o espaço comum é visível e a auditoria
mandou preservá-lo. `s21` fixa o conjunto em exatamente quatro categorias, nos
dois sentidos: menos deixaria passar invisível, mais recusaria letra ou
pontuação.

---

## 5. A3c — caracterização bilateral

`reproduce_e4962_boundaries.py` classifica a representação antes de acessar
atributo, e por isso encerra normalmente dos dois lados:

```text
cadeia 77:  A3A=REPRODUCED      A3B=REPRODUCED      total 2   exit 0
cadeia 78:  A3A=NOT_REPRODUCED  A3B=NOT_REPRODUCED  total 0   exit 0
```

Os mesmos casos viraram testes permanentes: `u52` (a lista de dicionários
exata do auditor), `u58` (a mutação aninhada exata) e `u66`/`u67` (a matriz
Unicode nos três campos).

---

## 6. As cinco fronteiras, provadas separadamente

| fronteira | entrada válida | entrada inválida |
|---|---|---|
| **1. construtor ORM** | tupla tipada entra e permanece tupla (`u51`) | `list`, `dict`, `str`, `int`, `None`, `()`, item errado, duplicata (`u52`–`u55`) |
| **2. atribuição** | substitui (`u57`) | recusa **e preserva o valor anterior** (`u56`) |
| **3. bind** | serializa canônico, ordem estável (`u63`) | erro de contrato, nunca `AttributeError` (`u61`, `u62`) |
| **4. result** | volta `tuple[RetentionRule, ...]`, round trip determinístico (`u65`) | payload malformado recusado de forma controlada (`u64`, `i20`) |
| **5. repository** | publicar → commitar → reler devolve tipado; **os sete métodos herdados** (`i31`, `i32`) | recusa antes do `INSERT`, zero linhas gravadas (`i35`, `i36`) |

Nenhum teste passa apenas porque o banco recusa `NULL` ou porque
`serialize_rules` falha depois que o objeto mutável já existiu: `i35` e `i36`
verificam `count(*) = 0` **e** a recusa é de contrato, anterior à sessão.

`typed_rules` é provado defensivo forçando o `__dict__` para contornar o
`@validates` (`u59`) — e continua devolvendo a mesma tupla, sem fabricar
cópia (`u60`).

---

## 7. Alcance real — e o que continua possível

```text
policy.rules = [{...}]               → TypeError, valor anterior intacto
policy.rules[0]["x"] = 0             → TypeError
policy.rules[0].minimum_age_days = 0 → FrozenInstanceError
policy.rules[0] = outra              → TypeError
domain_ids.add(...)                  → AttributeError (frozenset)
```

Continua possível, declarado: `object.__setattr__` contorna `frozen=True`, e
`policy.__dict__["rules"] = ...` contorna o `@validates` — é justamente o que
`u59` faz de propósito. Frozen e eventos de atributo protegem contra mutação
**acidental e idiomática**, não contra circunvenção deliberada; mesma posição
da E4.9.1, E4.6.3.1 e E4.9.6.1. A diferença que importa é que o banco não
muda, e nova sessão lê os bytes originais (`i33`).

---

## 8. Duas mudanças em testes existentes, deliberadas

**`test_s15` — guarda minha, afrouxada de propósito.** A versão da E4.9.6.1
proibia o módulo `unicodedata` inteiro. Era grosso demais: o endurecimento
autorizado exige `category`. Passou a proibir o que transforma e a exigir o
que classifica. É a única guarda relaxada nesta entrega, e o motivo está
escrito dentro do teste.

**`test_i20` — passou a exigir erro controlado.** Esperava `KeyError`; agora
exige `ValueError` nomeando as chaves faltantes. Mais estrito, não menos.

Nenhum outro teste da cadeia 77 precisou mudar. `u25`, que fixa
`typed_rules is rules`, continua valendo sem alteração — a leitura defensiva
devolve a mesma tupla.

---

## 9. Testes acrescentados

Contagens **coletadas**, não somadas à mão — lição da E4.9.5, onde reportei um
número colhido antes de terminar de escrever os testes. Funções de teste e
casos coletados são coisas diferentes, porque a matriz Unicode e as tabelas de
entrada inválida são parametrizadas:

| arquivo | cadeia 77 | cadeia 78 | funções novas |
|---|---:|---:|---|
| `tests/unit/memory/test_retention_policy.py` | 82 | 155 | 23 (`u51`–`u73`) |
| `tests/integration/.../test_retention_policy_integration.py` | 33 | 47 | 10 (`i31`–`i40`) |
| `tests/static/test_retention_policy_isolation.py` | 16 | 21 | 5 (`s17`–`s21`) |
| **E4.9.6 total** | **131** | **223** | **38** |

O crescimento de 92 casos coletados a partir de 38 funções é a
parametrização: `u66` sozinho é 10 invisíveis × 2 campos.

Rodados três vezes com resultado idêntico.

Guardas novas relevantes: `s17` prova na AST que o `@validates("rules")`
existe — se alguém o remover confiando no decorador, o A3b volta e o teste
cai; `s18` exige as três chamadas do contrato compartilhado e prova que não
sobrou cópia local do invariante; `s19` prova que `typed_rules` não voltou a
ser retorno cru.

---

## 10. Gates medidos

Em clone limpo, com PostgreSQL recriado:

```text
FULL_SUITE       2782 passed / 1 skipped / 0 failed   (cadeia 77: 2690/1/0)
RAW_SUITE        2326 passed / 457 skipped / 0 failed (cadeia 77: 2248/443/0)
GLOBAL_COVERAGE  99,23% — não reduziu
  retention_enums.py               100%
  retention_policy.py              100%
  schemas/retention.py             100%
  retention_policy_repository.py   100%
RUFF PASS   BLACK PASS (382 arquivos)
MYPY app    7 históricos — registry.py 4, base_repository.py 2, handlers.py 1
            NEW = 0.  Linha `note:` não contada.
type: ignore no arquivo tocado: 1 (a mesma da cadeia 76, movida na 77)
ALEMBIC single head c8a3f5017e94 — INALTERADO
git diff --check CLEAN
```

Schema conferido no banco real: `rules` segue `jsonb`, 4 `CHECK`, trigger
`trg_retention_policies_append_only` presente, `erasure_records` intacta.

**Regressões medidas por seletor, todas delta 0:**

```text
E3 = 732 · E4.1 = 40 · E4.2 = 42 · E4.3 = 255 · E4.4 = 74 · E4.5 = 187
E4.6 = 275 · E4.7 = 240 · E4.8 = 146 · E4.9.5 = 113
E4.9.6 = 131 → 223  (única contagem que sobe, pelos testes deliberados)
```

### 10.1 Condição de medição que precisa constar

O número FULL depende de o banco estar **migrado antes** da execução. Com o
banco recém-criado, a primeira execução dá `2597 passed / 186 skipped`; com
`migrations.upgrade("head")` aplicado antes, dá `2782 passed / 1 skipped`.

Isto **não** foi introduzido por este corretivo. Medi o mesmo clone da cadeia
77 nas duas condições: `2505/186` sem pré-migração e `2690/1` com — e `2690/1`
é exatamente o número publicado na cadeia 77. O delta de 186 é idêntico nas
duas cadeias, logo é propriedade do harness, não do patch.

Declaro porque o §9 do prompt manda separar RAW de FULL e medir em clone
limpo: quem repetir a medição sem pré-migrar vai ver 186 skips e precisa saber
que isso não é regressão.

---

## 11. Arquivos alterados

```text
app/memory/schemas/retention.py            categorias Unicode + validar_regras_retencao
app/memory/models/retention_policy.py      @validates, typed_rules defensivo,
                                           bind/serialize/deserialize controlados
tests/unit/memory/test_retention_policy.py            +23
tests/integration/.../test_retention_policy_integration.py +10, 1 atualizado
tests/static/test_retention_policy_isolation.py       +5, 1 atualizado
docs/.../EDR_E4_9_6_2_...md                           novo
```

`retention_policy_repository.py` **não** precisou mudar: já chamava
`validar_identificador_opaco` para as duas chaves e `serialize_rules` como
preflight, e ambos passaram a carregar o contrato novo por dentro.

Nada em migration, schema, `BaseRepository`, `GovernancePolicy`,
`AccessibilityPolicy`, Sync, Retrieval, E3 ou `errors/codes.py`. Nenhum código
de erro novo; `PIA-8042` e `PIA-8043` inalterados e testados (`u73`).

---

## 12. Riscos que declaro

**(a) A quarta fronteira.** Fechei atribuição, bind, result e leitura. A que
ainda não é fronteira é `__dict__` direto, e ela é intencionalmente aberta
porque é o que permite provar a defesa. Se um dia isso incomodar, a resposta
não é mais uma camada — é confinar o ORM, que exige alterar `BaseRepository`.

**(b) O custo da verificação defensiva.** `typed_rules` agora valida em toda
leitura, e `process_result_value` reconstrói em toda carga. Irrelevante para
configuração local; vale registrar caso alguém liste milhares de versões.

**(c) A lista de categorias é uma escolha, não uma verdade.** `Cc/Cf/Zl/Zp`
cobre o que a auditoria nomeou. Não cobre homóglifos — `а` cirílico e `a`
latino continuam sendo duas chaves distintas que se parecem. Recusá-los
exigiria heurística de confusão visual, e heurística que falha em silêncio é
pior que ausência de checagem — mesma posição declarada para `scope_token` na
E4.9.5.

**(d) A policy continua sem leitor.** Inalterado desde a E4.9.6: existe uma
tabela cujo conteúdo parece acionável e nada a avalia. Fechar fronteiras não
aproxima o avaliador, e não deve.

---

## 13. Estado

```text
PATCH_CHAIN = 78
MIGRATION_HEAD = c8a3f5017e94 (INALTERADO)
E4_9_6_2_IMPLEMENTATION = COMPLETE_CANDIDATE
E4_9_6_2_STATUS         = AWAITING_INDEPENDENT_AUDIT
A3B = FIXED   A3A = HARDENED   A3C = FIXED
RETENTION_EVALUATOR = NOT_COMPOSED   TRASH_RUNTIME = NONE
DESTRUCTIVE_EFFECT = NONE
E4_9_7 = NOT_STARTED
```

`git am` do patch isolado sobre a cadeia 77 reproduz a TREE exata, verificado
em clone independente. O bundle carrega `HEAD` e
`refs/heads/audit/e3-final-validation`, sem refs residuais.

Não se declara `PASS_FINAL`, E4.9.6 não é promovida a `CLOSED_FINAL`, e não há
autorização para a E4.9.7.
