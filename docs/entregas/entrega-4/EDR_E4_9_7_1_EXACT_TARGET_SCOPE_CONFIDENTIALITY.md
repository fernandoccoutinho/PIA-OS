# EDR E4.9.7.1 — Exact Target, Context Isolation and Confidentiality

**Natureza:** corretivo confinado dos três achados da auditoria independente da
E4.9.7. Não é fatia funcional nova.
**Baseline:** cadeia 80 (`075f2651`), `E4_9_7_AUDIT = FAIL_CORRECTIVE_REQUIRED`.

```text
ONE_DESCRIPTOR = ONE_EXACT_TARGET
FIELD_COUNT = 1 DOES_NOT_PROVE TARGET_CARDINALITY = 1
REDACTED_REPR != SECRET_FREE_OBJECT
SAFE_DIAGNOSTIC != FREE_TEXT
```

```text
A1_EXACT_TARGET = FIXED
A2_CONTEXT_ISOLATION_PROOF = FIXED
A3_CONFIDENTIALITY = FIXED
MIGRATION_DELTA = 0   DATABASE_SCHEMA_DELTA = 0   E3_DELTA = 0
EFFECT_DELTA = 0      ERASURE_RECORD_WRITER_DELTA = 0   API_DELTA = 0
```

Os três achados são defeitos meus e os três são reais.

---

## 1. Causa raiz — as três são a mesma forma de erro

Vale dizer isto antes das causas individuais, porque a repetição é o dado mais
importante deste corretivo.

Nos três casos **eu escrevi no EDR uma garantia mais forte do que o runtime
sustentava**, e em nenhum deles a diferença era visível no teste que eu mesmo
escrevi:

| Achado | O que o EDR da cadeia 80 afirmou | O que o runtime fazia |
|---|---|---|
| A1 | "um descritor representa exatamente um alvo" | validava só texto opaco; `s3://bucket/*` entrava |
| A2 | "cross-tenant fechado por `CONTROL_SCOPE_MISMATCH`" | o dublê comparava **só** `workspace_id` |
| A3 | "`MUST_NOT_CONTAIN_SECRET_OR_CREDENTIAL`" | validava **nome de campo**, não conteúdo |

É a quarta vez seguida — E4.9.6.1, E4.9.6.2, E4.9.6.3 e agora. A §15.2 do Master
v2.1 exige classificar toda garantia pela camada que a sustenta, e é exatamente
a disciplina que teria pegado os três. Aplico-a no §7 deste documento.

---

## 2. Baseline verificada e caracterização

```text
HEAD 075f265163795e0c3999ba60ad88c5821cc54b90
PARENT 4ec4aa49…  TREE 5f39bad9…  PATCH_ID 380ae79f…  PATCH_CHAIN 80
MIGRATION_HEAD c8a3f5017e94   árvore limpa   81 commits
app/cognitive  be407b46f679a009e0f7f7e9f01fb784f08dea54
backend/alembic cc68c3e274f388bda2a8674d6432d515bb8cbc4a
```

`reproduce_e4971_defects.py` executado **sem edição** dos dois lados:

```text
cadeia 80:  8 REPRODUCED   DEFECTS_REPRODUCED=8   EXPECTED=8   EXIT=0
cadeia 81:  8 NOT_REPRODUCED DEFECTS_REPRODUCED=0 EXPECTED=8   EXIT=1
```

O `EXIT=1` na cadeia corrigida é o comportamento declarado no cabeçalho do
próprio script: é reprodutor de defeito, não teste de regressão.

---

## 3. A1 — alvo exato como invariante executável

### 3.1 O erro

`u38` da cadeia 80 inspecionava **nomes de campo plurais** (`targets`,
`locators`, `subject_coids`) e concluía cardinalidade um. Ausência de `list`
não prova nada: uma única string cabe um padrão.

```text
cadeia 80:  ErasureTargetDescriptor(transient_locator="s3://bucket/*") → ACEITO
```

### 3.2 A correção

`validar_localizador_exato`, **estrutural** e neutra de provedor. Decompõe com
`urlsplit` e recusa:

1. `userinfo` (`//usuário:senha@`) — credencial embutida;
2. query ou fragmento — parâmetro de capacidade não pertence ao localizador;
3. `*`, `[`, `]`, `{`, `}` e `?` — designam mais de um objeto;
4. barra final — prefixo é coleção, não objeto.

O valor aceito é devolvido byte a byte. Recusar não é corrigir: nada é
normalizado, reescrito ou canonicalizado.

### 3.3 A distinção que o corretivo NÃO podia apagar

`capability.scope` continua aceitando `workspace/w1/*`, e **tem** de aceitar.

```text
capability.scope   = o que a conta PODE      → legitimamente um conjunto
transient_locator  = qual objeto é o alvo    → exatamente um
```

Aplicar a mesma regra aos dois confundiria autoridade com alvo, que é o oposto
do contrato da E4.9.1. Travado em `u52`, e é a razão de o validador exato ser
uma função separada em vez de um endurecimento de `validar_texto_opaco`.

### 3.4 Alternativas rejeitadas

| # | Alternativa | Por que |
|---|---|---|
| 1 | `bool exact=True` no descritor | o §2.1 proíbe, e com razão: qualquer chamador declararia sem prova. `s20` fixa a ausência |
| 2 | lista de substrings de padrões conhecidos | frágil por desenho, e o §5.2 adverte contra apresentá-la como segurança total |
| 3 | regex de "chave válida" por provedor | quebra a neutralidade de provedor exigida pelo §2.1.5 |
| 4 | endurecer `validar_texto_opaco` | apagaria a distinção do §3.3 — `capability.scope` usa a mesma função |
| **5** | **decomposição estrutural em função própria** | **adotada** |

### 3.5 Limites declarados

- Um objeto cujo **nome legítimo** contenha `[`, `{` ou `?` é recusado. Recusa
  conservadora deliberada: aceitar por engano designa alvo errado; recusar por
  engano só exige que o adaptador enderece o objeto de outra forma.
- Vírgula **não** é recusada: é comum em nome legítimo, e recusá-la trocaria
  proteção real por ruído.
- Segredo escondido **no caminho** — uma chave pré-assinada como segmento — não
  é detectável por estrutura, e nenhuma lista de palavras o detectaria de forma
  confiável. Fica declarado, não coberto por checagem que falharia em silêncio.

---

## 4. A2 — a prova de isolamento cobria uma dimensão de cinco

### 4.1 O erro

`_ResolvedorObservacional.resolve_target()` comparava só
`control_scope.workspace_id`. Medido na cadeia 80:

```text
TENANT_MISMATCH    → ErasureTargetDescriptor
PRINCIPAL_MISMATCH → ErasureTargetDescriptor
PROVIDER_MISMATCH  → ErasureTargetDescriptor
NAMESPACE_MISMATCH → ErasureTargetDescriptor
```

E a docstring de `u35` dizia "fecha o cross-tenant no comportamento, não só no
contrato". Dizia o que o teste não media.

### 4.2 A correção

Cada dimensão tem recusa própria e teste comportamental independente:

```text
WORKSPACE_MISMATCH         → CONTROL_SCOPE_MISMATCH          (u62)
TENANT_MISMATCH            → CONTROL_SCOPE_MISMATCH          (u63)
CONTROL_PRINCIPAL_MISMATCH → CONTROL_SCOPE_MISMATCH          (u64)
PROVIDER_MISMATCH          → PROVIDER_NAMESPACE_OUT_OF_SCOPE (u65)
NAMESPACE_MISMATCH         → PROVIDER_NAMESPACE_OUT_OF_SCOPE (u66)
```

`expected_namespace=None` continua legítimo e **não fabrica correspondência**
(`u67`): a maior parte das referências da E3 não diz onde o conteúdo vive, e
ausência de expectativa significa que não há o que comparar — não que houve
match.

### 4.3 O que isto é, e o que não é

```text
CONTRACT_AND_FAKE_PROOF = STRENGTHENED
EXTERNAL_RUNTIME_CROSS_TENANT_CLOSURE = NOT_CLAIMED
```

Não existe adaptador nesta fatia. O dublê é o contrato da porta exercitado, não
um resolvedor real. **Não afirmo cross-tenant fechado em runtime externo** — a
afirmação correta é que a porta obriga a recusa e que nenhuma dimensão
divergente pode devolver descritor de sucesso.

Nenhum adaptador foi criado para satisfazer estes testes, e as recusas novas não
introduziram efeito: `u69` mede escritas e chamadas externas em zero.

---

## 5. A3 — confidencialidade imposta, não declarada

### 5.1 A3a — credencial embutida no localizador

O contrato dizia `MUST_NOT_CONTAIN_SECRET_OR_CREDENTIAL` e validava apenas
**nomes de campo** (`u25`). Medido:

```text
cadeia 80: transient_locator =
  "https://user:password@storage.example/object?token=secret&signature=abc"
  → ACEITO
```

Agora a URL do reprodutor é recusada por **duas razões independentes**:
`userinfo` e presença de query. `u53` e `u54` testam cada uma separadamente,
para que a remoção de uma não deixe a outra sem prova.

A recusa de query é **estrutural, não vocabulário**: cai toda query, não apenas
as que contêm `token`, `signature` ou `api_key`. É estritamente mais forte e
não depende de adivinhar o nome do parâmetro de cada provedor. E há onde pôr
versão sem query — `version_etag` já existia como campo (`u56`).

### 5.2 A3b — diagnóstico de texto livre

```text
cadeia 80: TargetResolutionRefusal(diagnostic=LOCATOR) → ACEITO
           repr(refusal) e str(refusal) → REVELAM o localizador
```

`u24` usava só diagnóstico benigno. A auditoria passou a entrada proibida.

**A correção não podia ser redigir o `repr`**, e este é o ponto central: o valor
proibido já estaria dentro do objeto, disponível a qualquer consumidor. O §2.3.6
do prompt diz exatamente isso.

`diagnostic: str | None` foi **removido**. Entrou
`observed_dimension: RefusalDimension | None`, vocabulário fechado de oito
membros sem genérico, que nomeia a dimensão divergente e não tem onde
transportar localizador, segredo ou conteúdo.

### 5.3 Compatibilidade pública

```text
BREAKING_CHANGE = TargetResolutionRefusal.diagnostic REMOVED
CONSUMERS_IMPACTED = 0
```

Verificado: nenhum consumidor runtime da porta existe (`s10`), e o campo era
usado apenas em `u24`. O §4 do prompt autoriza expressamente — "não mantenha uma
API insegura apenas para preservar uma assinatura que a auditoria demonstrou
falsa".

`s19` fixa a ausência **e** prova que `origin` é o único campo `str` da recusa:
ele é a referência que motivou a tentativa, dado do pedido, não contexto que o
resolvedor compõe.

---

## 6. Tabela evidência → antes → depois

| Evidência | Cadeia 80 | Cadeia 81 | Regressão |
|---|---|---|---|
| `A1_WILDCARD_ACCEPTED` | aceito | `ValueError` "exatamente um alvo" | `u46` |
| `A3_SECRET_LOCATOR_ACCEPTED` | aceito | `ValueError` "credencial" | `u53`, `u55` |
| `A3_DIAGNOSTIC_ACCEPTED` | aceito | `TypeError` — campo inexistente | `u57` |
| `A3_DIAGNOSTIC_REPR_LEAK` | vazava | inconstruível | `u60`, `u61` |
| `A2_TENANT_MISMATCH_SUCCEEDS` | sucesso | `CONTROL_SCOPE_MISMATCH` | `u63` |
| `A2_PRINCIPAL_MISMATCH_SUCCEEDS` | sucesso | `CONTROL_SCOPE_MISMATCH` | `u64` |
| `A2_PROVIDER_MISMATCH_SUCCEEDS` | sucesso | `PROVIDER_NAMESPACE_OUT_OF_SCOPE` | `u65` |
| `A2_NAMESPACE_MISMATCH_SUCCEEDS` | sucesso | `PROVIDER_NAMESPACE_OUT_OF_SCOPE` | `u66` |

---

## 7. Classificação das garantias (Master v2.1 §15.2)

A disciplina que teria evitado os três achados. Cada garantia com a camada que
a sustenta — e nada além.

| Garantia | Camada | Alcance real |
|---|---|---|
| localizador de sucesso não expressa wildcard/coleção | `APPLICATION_LEVEL` | construtor direto; qualquer caminho que construa o VO |
| localizador não embute userinfo/query/fragmento | `APPLICATION_LEVEL` | idem |
| localizador não esconde segredo **no caminho** | `DEFERRED` | não detectável por estrutura; declarado no §3.5 |
| recusa não carrega texto livre | `APPLICATION_LEVEL` | por ausência de campo, não por validação |
| `repr`/`str` não revelam localizador | `APPLICATION_LEVEL` | sucesso e todas as formas de recusa |
| dimensões divergentes não viram sucesso | `POLICY_LEVEL` (contrato + dublê) | **não** é runtime externo — §4.3 |
| cross-tenant fechado em provedor real | `DEFERRED` | não há adaptador |
| ausência de efeito e de escrita | `AUDIT_LEVEL` (guarda estática + dublê) | `s02`–`s04`, `s22`, `u69` |
| ausência de persistência | `APPLICATION_LEVEL` + `AUDIT_LEVEL` | zero ORM, zero migração |

---

## 8. Conformidade documental — quatro camadas

### 8.1 `PIA_OS_SOPHIA_MASTER_COMPATIBILITY` — 20 linhas

```text
├── USER_AUTHORITY_PRESERVED ................ SIM. Corretivo só restringe;
│     nada aqui decide, aprova ou executa.
├── SOPHIA_BRAND_PIA_OS_CODEBASE_PRESERVED .. SIM.
├── MODULE_SCOPE_AND_DEFERRED_CAPABILITIES ... Escopo: três fronteiras
│     auditadas. Diferidos: adaptador, efeito, E4.9.8.
├── SCHEDULE_MODE_DECLARED ................... NOT_APPLICABLE — corrective only.
├── AI_ROLE_AND_STEP_INSTRUCTION_DISTINGUISHED NOT_APPLICABLE.
├── PROVIDER_CONNECTION_METHOD_DECLARED ...... NOT_APPLICABLE — nenhum
│     conector; o mecanismo de alvo exato é neutro de provedor por desenho.
├── AUTOMATION_SCOPE_DECLARED ................ NENHUMA (`s15`, `s22`).
├── APPROVAL_GATES_DECLARED .................. NOT_APPLICABLE.
├── PERSISTENCE_BEHAVIOR_DECLARED ............ NENHUMA.
├── MULTI_AI_RESULT_ATTRIBUTION_DECLARED ..... NOT_APPLICABLE.
├── DIVERGENCE_PRESERVATION_DECLARED ......... SIM — localizador devolvido
│     byte a byte, sem normalização (`u50`, `u51`).
├── CONCURRENT_WORK_ISOLATION_DECLARED ....... REFORÇADO — é o achado A2.
├── BACKGROUND_EXECUTION_AUTHORIZATION ....... NOT_APPLICABLE.
├── RESOURCE_LIMITS_QUEUE_AND_COST_DECLARED .. NOT_APPLICABLE.
├── REMOTE_RESOURCE_SCOPE_DECLARED ........... NENHUM acesso remoto.
├── OBSERVATION_PREPARATION_EXECUTION ........ Continua só OBSERVAÇÃO.
├── CREDENTIAL_AND_SECRET_BOUNDARY_DECLARED .. REFORÇADO — é o achado A3.
├── FAILURE_ROLLBACK_AND_CONCURRENCY ......... Sem escrita, nada a reverter.
├── CURRENT_CAPABILITY_NOT_OVERSTATED ........ §7 classifica cada garantia
│     por camada; §4.3 recusa explicitamente a alegação de runtime.
└── FROZEN_MODULES_UNCHANGED ................. cognitive e alembic idênticos.
```

### 8.2 `SOPHIA_UX_COMPATIBILITY` — 17 linhas

```text
├── USER_AUTHORITY_PRESERVED ................. SIM.
├── SCHEDULE_MODE_DECLARED ................... NOT_APPLICABLE.
├── AUTOMATION_SCOPE_DECLARED ................ NENHUMA.
├── PERSISTENCE_BEHAVIOR_DECLARED ............ NENHUMA.
├── PROVIDER_NEUTRALITY_PRESERVED ............ REFORÇADO — os metacaracteres
│     recusados não são sintaxe de storage algum (`u49`).
├── PERSONALIZATION_REVERSIBLE ............... NOT_APPLICABLE.
├── CONCURRENT_WORK_ISOLATION_DECLARED ....... REFORÇADO — cinco dimensões.
├── BACKGROUND_EXECUTION_AUTHORIZATION ....... NOT_APPLICABLE.
├── RESOURCE_LIMITS_AND_QUEUE_DECLARED ....... NOT_APPLICABLE.
├── AI_ROLE_CONTROL_DECLARED ................. NOT_APPLICABLE.
├── ROLE_AND_STEP_INSTRUCTION_DISTINGUISHED .. NOT_APPLICABLE.
├── PIA_SEQUENCE_SUGGESTION_BEHAVIOR ......... NOT_APPLICABLE.
├── MULTI_AI_RESULT_ATTRIBUTION_DECLARED ..... NOT_APPLICABLE.
├── PIA_INTEGRATION_DIVERGENCE_PRESERVATION .. NOT_APPLICABLE.
├── POST_RESULT_USER_COMMAND_DECLARED ........ NOT_APPLICABLE.
├── RESULT_APPROVAL_AND_PERSISTENCE ......... Distinguidos por ausência.
└── FROZEN_MODULES_UNCHANGED ................. SIM.
```

### 8.3 `MULTICHANNEL_COMMAND_COMPATIBILITY_v1_3` — 10 marcadores

```text
├── INPUT_CHANNELS_DECLARED ................. TEXT | VOICE, ambos futuros.
├── COMMAND_ENVELOPE_DECLARED ............... Contratos utilizáveis pelo
│     envelope futuro; o envelope é da E4.9.8 e NÃO foi criado.
├── CHANNEL_NORMALIZATION_DECLARED .......... NOT_APPLICABLE — sem canal.
├── IDENTITY_CONTEXT_AND_SCOPE_DECLARED ..... PARCIAL, declarado: os campos
│     de `ControlScope` são declarados pela fronteira, não autenticados —
│     e agora TODOS são verificados na recusa, não só workspace.
├── VOICE_CONFIDENCE_AND_CORRECTION ......... NOT_APPLICABLE.
├── CONFIRMATION_POLICY_DECLARED ............ NOT_APPLICABLE.
├── DESTRUCTIVE_INTENT_BINDING_DECLARED ..... REFORÇADO: o corretivo fecha
│     `target expansion` no VALOR, não só na forma do campo — era a única
│     das seis ameaças que o §6 do EDR anterior afirmava sem sustentar.
├── GOVERNANCE_PARITY_ACROSS_CHANNELS ....... SIM — `origin` continua sem
│     virar autoridade (`u39`), qualquer que seja o canal.
├── AUDIT_AND_RECEIPT_DECLARED .............. NOT_APPLICABLE — sem recibo.
└── CURRENT_CAPABILITY_NOT_OVERSTATED ....... SIM — §7.
```

### 8.4 Parte II §12 — 8 obrigações, 11 Stop Conditions, 11 provas

**Oito obrigações:** cumpridas — diretriz citada; implementado no §3–§5;
diferido no §10; observação/preparação/aprovação/execução separadas (só a
primeira existe); autoridade é o usuário e nenhum contrato a substitui; sem
escrita não há rollback e VOs imutáveis não têm concorrência; compatibilidade
com E3/E4 por regressão delta zero; nenhuma Stop Condition disparou.

**Onze Stop Conditions mínimas:** nenhuma disparou — sem entidade persistente
ou migração, sem ownership de Workspace/conector, sem credenciais (é o achado
que fechamos), sem execução externa, sem ampliação de autoridade, sem
assinatura de provedor, sem sincronização, sem perda de proveniência, sem
colapso de Schedules, sem rollback declarado, sem alteração de congelados.

**Onze provas mínimas:** PROVADAS — nenhuma chamada externa (`s04`, `u69`),
nenhum acesso fora do escopo (`u62`–`u66`), nenhuma escrita durante observação
(`u69`), preservação de origem/versão (`u39`, `u56`), isolamento entre
Workspaces (`u62`). `NOT_APPLICABLE` — aprovação prévia, rollback, concorrência
determinística, recibo fiel, cancelamento. `DEFERRED` — estado obsoleto,
modelado em `resolved_at`/`version_etag`/`STALE_RESOLUTION` e não executável sem
executor.

### 8.5 Checklist de impacto sobre distinções (Master v2.1, Parte III §13)

Ausente nos EDRs anteriores. Registro agora, como o documento exige:

```text
1. cria distinção?          NÃO — restringe VOs existentes
2. transforma distinção?    NÃO
3. compara distinções?      NÃO — compara contexto declarado, não patrimônio
4. muda acessibilidade?     NÃO
5. afeta persistência?      NÃO — zero ORM, zero migração
6. altera proveniência?     NÃO — `origin` inalterado
7. altera história causal?  NÃO
```

---

## 9. Gates medidos

Clone limpo, PostgreSQL recriado e **pré-migrado**:

```text
COLLECTED        3048                                (cadeia 80: 2985)
FULL_SUITE       3047 passed / 1 skipped / 0 failed  (cadeia 80: 2984/1/0)
RAW_SUITE        2580 passed / 468 skipped / 0 failed (cadeia 80: 2517/468/0)
GLOBAL_COVERAGE  99,26%   (era 99,25% — subiu)
  target_resolution_enums.py   100%
  schemas/erasure_target.py    100%
  ports/erasure_target.py      100%
RUFF PASS   BLACK PASS (387)
MYPY app    7 históricos — registry 4, base_repository 2, handlers 1; NEW = 0
supressões / cast / Any novos: 0
ALEMBIC heads = current = c8a3f5017e94, single head
git diff --check CLEAN
```

**Regressões, delta 0:**

```text
E3 = 732 · E4.1 = 40 · E4.2 = 42 · E4.3 = 255 · E4.4 = 74 · E4.5 = 187
E4.6 = 275 · E4.7 = 240 · E4.8 = 146 · E4.9.5 = 113 · E4.9.6 = 309
```

E4.9.7: **116 → 179** (157 unitários + 22 estáticos). Executada três vezes com
resultado idêntico.

---

## 10. Arquivos alterados

```text
app/memory/models/target_resolution_enums.py   + RefusalDimension (8 membros)
app/memory/schemas/erasure_target.py           + validar_localizador_exato,
                                               + METACARACTERES_DE_EXPANSAO,
                                               diagnostic → observed_dimension
tests/unit/memory/test_erasure_target.py       +57, 1 atualizado (u24)
tests/static/test_erasure_target_isolation.py  +6, 1 atualizado (s04)
docs/.../EDR_E4_9_7_1_...md                    novo
```

`ports/erasure_target.py` não precisou mudar: a assinatura da porta já era
`referência → sucesso | recusa`, e o corretivo endureceu os value objects que
ela transporta.

### 10.1 Uma guarda minha envelheceu, e a correção não foi a reflexa

`s04` proibia o módulo `urllib` inteiro. Grosso demais — `urllib.parse.urlsplit`
é decomposição de string, sem rede. Passou a proibir o que **abre conexão**:
`urllib.request`, `urlopen`, `urlretrieve`.

É a mesma forma da correção de `s15` na E4.9.6.2, que proibia `unicodedata`
inteiro quando o necessário era proibir `normalize`. A lição que registro:
**guarda de import deve nomear a capacidade proibida, não o pacote que a
contém**.

---

## 11. Modelo de ameaças — o que mudou

| Ameaça | Cadeia 80 | Cadeia 81 |
|---|---|---|
| **Target expansion** | afirmada fechada "por forma"; wildcard entrava | fechada no VALOR do localizador, `APPLICATION_LEVEL` |
| **Cross-tenant** | afirmada fechada; só workspace verificado | cinco dimensões, `POLICY_LEVEL`; runtime externo segue `DEFERRED` |
| **Locator leakage** | `repr` redigido; diagnóstico livre vazava | sem campo de texto livre; nenhuma forma de recusa revela |
| **Credential confusion** | provedor/namespace declarados, não verificados | verificados no contrato e no dublê |
| **Confused deputy** | `capability.verified` obrigatório | inalterado — segue `DEFERRED` sem conector |
| **Stale resolution** | `resolved_at` + `version_etag` | inalterado — segue `DEFERRED` sem executor |

---

## 12. Riscos que declaro

**(a) A recusa conservadora do §3.5 pode incomodar.** Um objeto legítimo com
`[` ou `{` no nome é recusado. Se um provedor real exigir isso, a resposta
correta é EDR e refinamento por estrutura — nunca relaxar para "aceitar se
parecer nome de arquivo", que é heurística que falha em silêncio.

**(b) Segredo no caminho continua indetectável.** Declarado, não mitigado.

**(c) A prova de A2 é contratual.** O dublê é o contrato exercitado. Um
adaptador real que ignore `ControlScope` satisfaz o `Protocol` e produz
descritores errados. É a razão de a E4.9.1 exigir adaptador **autorizado**, e a
autorização não é implementável nesta fatia.

**(d) `observed_dimension` é opcional.** Uma recusa sem dimensão continua
válida — nem toda recusa observa uma. O campo informa quando houve observação e
não deve virar obrigatório sem que exista quem o preencha sempre.

**(e) Quatro corretivos seguidos com a mesma forma de erro.** O padrão é de
redação, não de código. A §15.2 do Master v2.1 é a contramedida, e este é o
primeiro EDR a aplicá-la; se voltar a acontecer com a tabela do §7 no lugar, o
problema é mais fundo que disciplina de escrita.

---

## 13. Estado

```text
PATCH_CHAIN = 81
MIGRATION_HEAD = c8a3f5017e94 (INALTERADO)
E4_9_7_1_IMPLEMENTATION = COMPLETE_CANDIDATE
E4_9_7 = AWAITING_INDEPENDENT_REAUDIT
A1 = FIXED   A2 = FIXED   A3 = FIXED
TARGET_RESOLVER_ADAPTER = NONE
ERASURE_EFFECT = NONE
ERASURE_RECORD_WRITER = NOT_COMPOSED
E4_9_READY = FALSE
E4_9_8 = NOT_STARTED
```

Não há adaptador, não há efeito e a E4.9.8 não foi iniciada. `PASS_FINAL`
pertence à auditoria independente.
