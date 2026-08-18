# EDR E4.9.6.3 — Assignment and Result Boundaries

**Natureza:** corretivo dos três achados da auditoria independente da
E4.9.6.2. Não é fatia funcional nova.
**Baseline:** cadeia 78 (`b199e26c`), `E4_9_6_2_AUDIT = FAIL_CORRECTIVE_REQUIRED`.

```text
VALID VALUE           != AUTHORITY TO REASSIGN
JSON ITERABLE         != CANONICAL JSON ARRAY
NOT NULL CONSTRAINT   != DOMAIN BOUNDARY VALIDATION
```

```text
A4A_RULES_REASSIGNMENT = FIXED   (bloqueante)
A4B_RESULT_JSON_SHAPE  = FIXED   (bloqueante)
A4C_NONE_BIND_BYPASS   = FIXED   (contrato)
TEST_TYPE_SUPPRESSIONS = REMOVED (as seis da cadeia 78)
MIGRATION_DELTA = 0   DATABASE_SCHEMA_DELTA = 0   E3_DELTA = 0
EVALUATOR_DELTA = 0   EFFECT_DELTA = 0   API_DELTA = 0
```

Os três achados são defeitos meus e os três são reais.

---

## 1. Bloco de compatibilidade — Master v1.8 §0.4

Conferi o v1.8 contra o v1.7 antes de reaproveitar o bloco: a lista de 20
linhas é **idêntica**; o que a v1.8 acrescenta é um adendo de estado técnico
(seções 1–6, 164 linhas) e três linhas no cabeçalho normativo.

```text
PIA_OS_SOPHIA_MASTER_COMPATIBILITY
├── USER_AUTHORITY_PRESERVED ................ SIM. `AI_MODEL_DELETE_AUTHORITY
│     = NONE` e `EXPIRY_TRIGGERS_ASSESSMENT_NOT_DELETION` intactos; nada
│     nesta fatia decide apagar.
├── SOPHIA_BRAND_PIA_OS_CODEBASE_PRESERVED .. SIM. Nenhum identificador de
│     marca no código.
├── MODULE_SCOPE_AND_DEFERRED_CAPABILITIES ... Escopo: fronteiras de
│     atribuição e de reconstrução de `rules`. Diferidas: avaliador, lixeira,
│     aprovação, efeito, resolução de alvo.
├── SCHEDULE_MODE_DECLARED ................... N/A — corrective only.
├── AI_ROLE_AND_STEP_INSTRUCTION_DISTINGUISHED N/A — corrective only.
├── PROVIDER_CONNECTION_METHOD_DECLARED ...... N/A — corrective only.
├── AUTOMATION_SCOPE_DECLARED ................ NENHUMA. Guardas `s10` e `s25`
│     provam ausência de relógio, scheduler e consumidor.
├── APPROVAL_GATES_DECLARED .................. N/A — nada nesta fatia executa.
├── PERSISTENCE_BEHAVIOR_DECLARED ............ Append-only inalterado. A
│     recusa de reatribuição ACRESCENTA uma camada em memória; mapper,
│     repository e trigger seguem idênticos.
├── MULTI_AI_RESULT_ATTRIBUTION_DECLARED ..... N/A — corrective only.
├── DIVERGENCE_PRESERVATION_DECLARED ......... Sequências Unicode distintas
│     continuam não fundidas; nenhuma normalização introduzida.
├── CONCURRENT_WORK_ISOLATION_DECLARED ....... `UNIQUE(policy_key, version)` e
│     o teste de concorrência da E4.9.6 preservados (`i48`).
├── BACKGROUND_EXECUTION_AUTHORIZATION ....... NENHUMA.
├── RESOURCE_LIMITS_QUEUE_AND_COST_DECLARED .. N/A — corrective only.
├── REMOTE_RESOURCE_SCOPE_DECLARED ........... NENHUM. `RETENTION_POLICY_SYNC
│     = NONE` e `PORTABLE = FALSE` (`s05`).
├── OBSERVATION_PREPARATION_EXECUTION ........ Distinguidos: persistir policy
│     é preparação; não há observação de patrimônio nem execução.
├── CREDENTIAL_AND_SECRET_BOUNDARY_DECLARED .. N/A. O identificador é opaco
│     por contrato e não é interpretado como segredo ou localizador.
├── FAILURE_ROLLBACK_AND_CONCURRENCY ......... Recusa não corrompe: referência
│     e conteúdo anteriores preservados (`u75`, `i41`, `i47`).
├── CURRENT_CAPABILITY_NOT_OVERSTATED ........ Este EDR corrige uma segunda
│     afirmação minha excessiva. Ver §5.
└── FROZEN_MODULES_UNCHANGED ................. `app/cognitive` e
      `backend/alembic` byte a byte idênticos.
```

**Ordem cumprida desta vez.** Na E4.9.6.2 eu implementei antes de redigir o
bloco e registrei a inversão. Aqui o bloco foi lido e preenchido antes do
código.

### 1.1 Divergência documental registrada

O adendo do Master v1.8 declara `NEXT_AUTHORIZED_CORRECTIVE = E4.9.6.2` e
`DOCUMENT_BASELINE_PATCH_CHAIN = 77`. Ele foi escrito do ponto de vista da
cadeia 77 e está uma etapa atrás do estado real. Não é conflito material: o
próprio §1 do adendo diz que registra estado técnico, e a hierarquia de
autoridade do projeto põe o bundle e a auditoria da cadeia 78 acima dos
documentos mestres. Registro em vez de corrigir em silêncio.

---

## 2. Baseline verificada

```text
HEAD b199e26cb1d25f36701c9e2c44f48ef57d369a4c
PARENT 3407c774…  TREE 2913f2f1…  PATCH_ID 62e9d9f4…  PATCH_CHAIN 78
MIGRATION_HEAD c8a3f5017e94   árvore limpa
app/cognitive  be407b46f679a009e0f7f7e9f01fb784f08dea54
backend/alembic cc68c3e274f388bda2a8674d6432d515bb8cbc4a
```

Caracterização antes de tocar em código:

```text
A4A_VALID_RULES_REASSIGNMENT=REPRODUCED
A4B_OBJECT_DOMAIN_IDS_ACCEPTED=REPRODUCED
A4C_NONE_BIND_BYPASS=REPRODUCED
DEFECTS_REPRODUCED=3   EXIT=0
```

Nenhum consumidor runtime de `RetentionPolicy` fora dos próprios módulos
(`s01`, `s16`, `s20`, `s25`).

---

## 3. A4a — inicialização versus reatribuição

### 3.1 Reprodução na cadeia 78

```text
policy = RetentionPolicy(..., rules=(regra_a,))
policy.rules = (regra_b,)          → ACEITO
policy.rules[0].rule_id            = regra_b
policy.typed_rules[0].rule_id      = regra_b
```

O `@validates` verificava a **forma** e devolvia qualquer tupla válida. Não
distinguia construção de substituição.

O erro tem duas partes, e a segunda é pior: `test_u57` da cadeia 78 se chamava
`atribuicao_valida_substitui` e **congelava o comportamento errado como
contrato**. Escrevi um teste que declarava correto exatamente aquilo que a
E4.9.6.1 tinha declarado impossível — que duas leituras na mesma sessão não
podem divergir. Um teste que sanciona o defeito é pior que a ausência do
teste, porque a próxima auditoria encontra a justificação escrita.

### 3.2 O mecanismo, e por que não o óbvio

```python
estado = inspect(self)
if estado.has_identity or key in estado.dict:
    raise ValueError("rules não pode ser reatribuída — ...")
return validar_regras_retencao(key, value)
```

`"rules" in self.__dict__` sozinho **não serve**, e o §11.5 do prompt nomeia a
razão: numa instância expirada o atributo some do `__dict__`, e a próxima
atribuição passaria por primeira inicialização. Medido: depois de
`session.expire()`, `"rules" in lida.__dict__` é `False` — e a recusa
continua, porque `has_identity` é verdadeiro.

A tabela de estados, toda medida:

| estado | `has_identity` | `key in estado.dict` | resultado |
|---|---|---|---|
| transiente, 1ª atribuição | False | False | **aceita** |
| transiente, 2ª atribuição | False | True | recusa |
| pendente (na sessão, antes do flush) | False | True | recusa |
| persistente carregada | True | — | recusa |
| persistente expirada | True | False | recusa |

Carregamento e `refresh` continuam funcionais porque o `loading` do SQLAlchemy
popula o `__dict__` sem evento de atributo — a mesma propriedade que a
E4.9.6.2 já usava para não duplicar validação com o `process_result_value`.

`s22` e `u76` provam na AST que a checagem usa `has_identity` e **não**
`self.__dict__`.

---

## 4. A4b — forma do JSON persistido

### 4.1 Reprodução na cadeia 78

```json
"domain_ids": {"00000000-0000-0000-0000-000000000001": "ignored"}
```

```text
RESULT_ACCEPTED = TRUE
domain_ids = frozenset({UUID("0000...0001")})
JSON_OBJECT_VALUES = SILENTLY_IGNORED
```

Python itera um `dict` pelas **chaves**. Cada chave virava UUID e os valores
sumiam. JSON estruturalmente inválido virava regra válida com significado
diferente do gravado. E `rule_id=[]` chegava ao `set` de duplicidade e
produzia `unhashable type: 'list'` — incidental da estrutura de dados, não do
contrato.

### 4.2 A correção

`regra_de_json(indice, item)` em `schemas/retention.py`. Valida a forma dos
seis campos e **só então** converte e constrói:

```text
rule_id, scope_kind, anchor, on_expiry_action  → str exata
minimum_age_days                                → int verdadeiro, bool proibido
domain_ids                                      → list exata
domain_ids[i]                                   → str, e UUID parseável
```

`list` **exata** para `domain_ids`: `dict` foi o caso reproduzido, mas `str`,
`tuple` e `set` também são iteráveis e produziriam conversão plausível a
partir de algo que o formato canônico nunca gravou.

Duas camadas, nesta ordem: **forma** aqui, **domínio** no construtor de
`RetentionRule`, que segue sendo a autoridade sobre vocabulário fechado,
`minimum_age_days >= 1` e a matriz de escopo. `u87` prova a segunda camada
viva com forma válida e domínio inválido.

A duplicidade passou para depois da validação de forma, então `rule_id` já é
`str` quando entra no `set`.

### 4.3 Efeito colateral que vale registrar

Validar a forma antes de converter estreita o tipo para o verificador. Isso
eliminou a necessidade de `cast` que uma primeira versão desta correção tinha
— e `cast` é proibido pelo §7. A restrição de typing e a correção apontavam
para o mesmo desenho.

---

## 5. A4c — semântica de `None`

```text
cadeia 78:  process_bind_param(None, dialect) → None
cadeia 79:  process_bind_param(None, dialect) → TypeError
            process_result_value(None, dialect) → ValueError
```

A coluna é `nullable=False`. `NULL` nunca é valor legítimo, e devolver `None`
daqui delegava a recusa ao banco:

```text
NOT NULL CONSTRAINT != DOMAIN BOUNDARY VALIDATION
```

**A afirmação que corrijo:** o §3.3 do EDR da E4.9.6.2 diz que atribuição,
bind e leitura defensiva usam o mesmo contrato. Com o atalho de `None` isso
não era literalmente verdade. É a segunda vez seguida que uma frase minha
descreve uma garantia mais completa do que o código entregava — na E4.9.6.1
foi "não existe `list[dict]` pública em momento algum", aqui foi "as três
fronteiras usam o mesmo contrato". O padrão não é de código: é de redação,
e a correção de método é escrever a garantia depois de enumerar as saídas,
não antes.

`test_u49`, que congelava a passagem de `None`, foi atualizado com nota.
`u78` prova na AST que o bind não tem mais nenhum `return` precoce.

---

## 6. Supressões de typing removidas

As seis acrescentadas pelo patch 78 saíram: cinco no unitário e uma na
integração. Substituídas por três helpers que **não silenciam** o verificador:

| helper | por que passa sem supressão |
|---|---|
| `_chamar(alvo, metodo, **kwargs)` | função obtida por `getattr` não tem assinatura conhecida |
| `_atribuir_campo(alvo, campo, valor)` | `setattr` aceita `(object, str, Any)`; o nome em variável também evita a reescrita B010 do ruff |
| `_atribuir_item(alvo, chave, valor)` | `__setitem__` obtido por nome; levanta `TypeError` próprio quando o método não existe |

O terceiro não é vacuidade: se `rules` voltar a ser lista de dicionários, o
`__setitem__` existe, a mutação passa e o teste falha — que é exatamente o que
se quer dele.

Verificação por categoria de erro do mypy nos três arquivos de teste, contra a
cadeia 77:

```text
arg-type    4 → 4     (remover as supressões NÃO reintroduziu erro de argumento)
misc        0 → 0
assignment  0 → 0
```

`no-untyped-def` e `no-untyped-call` crescem com o número de funções de teste,
como em todo o repositório — os testes deste projeto não são anotados e
`mypy tests` não é gate. Declaro os números para não repetir a omissão que a
auditoria apontou no §6 dela.

Produção: `schemas/retention.py` 0 supressões, `retention_policy.py` 1 (a
histórica do `JSONB()`), repository 0. Nenhum `cast`. `s24` fixa isso.

---

## 7. Testes atualizados e acrescentados

Três testes meus mudaram, todos com nota no corpo:

- **`test_u57`** — invertido. Chamava-se `atribuicao_valida_substitui` e
  congelava o A4a; agora exige a recusa;
- **`test_u49`** — congelava `None` atravessando bind e result; agora exige
  erro controlado nos dois;
- **`test_i33`** — numa instância carregada a recusa passou de `TypeError` de
  forma para `ValueError` de autoridade.

Contagens **coletadas**:

| arquivo | cadeia 78 | cadeia 79 |
|---|---:|---:|
| `tests/unit/memory/test_retention_policy.py` | 155 | 226 |
| `tests/integration/.../test_retention_policy_integration.py` | 47 | 58 |
| `tests/static/test_retention_policy_isolation.py` | 21 | 25 |
| **E4.9.6 total** | **223** | **309** |

Rodados três vezes com resultado idêntico.

### 7.1 Uma guarda minha nasceu frágil pela quarta vez

`u76` buscava `self.__dict__` no texto bruto do validador e acusou a docstring
que **explica** por que não se usa `self.__dict__`. É o mesmo falso positivo
de `gv16` (E4.3.1), `s02`/`s11` (E4.9.6) e `s15` (E4.9.6.1). Corrigido por AST
antes de rodar o gate, e `s22` já nasceu por AST.

A lição já não é sobre o caso: guarda que compara texto de arquivo tem de
nascer comparando código executável neste projeto, porque as docstrings daqui
descrevem nominalmente o que o módulo **não** faz.

---

## 8. Gates medidos

Clone limpo, PostgreSQL recriado e **pré-migrado** antes do FULL:

```text
FULL_SUITE       2868 passed / 1 skipped / 0 failed   (cadeia 78: 2782/1/0)
RAW_SUITE        2401 passed / 468 skipped / 0 failed (cadeia 78: 2326/457/0)
GLOBAL_COVERAGE  99,24%   (era 99,23% — subiu)
  retention_enums.py               100%
  retention_policy.py              100%
  schemas/retention.py             100%
  retention_policy_repository.py   100%
RUFF PASS   BLACK PASS
MYPY app    7 históricos — registry.py 4, base_repository.py 2, handlers.py 1
            NEW = 0
ALEMBIC single head c8a3f5017e94 — INALTERADO
git diff --check CLEAN
```

**Regressões, delta 0:**

```text
E3 = 732 · E4.1 = 40 · E4.2 = 42 · E4.3 = 255 · E4.4 = 74 · E4.5 = 187
E4.6 = 275 · E4.7 = 240 · E4.8 = 146 · E4.9.5 = 113
```

A condição de pré-migração declarada no §10.1 do EDR anterior continua valendo
e continua sendo propriedade do harness, não do patch.

Caracterização bilateral, sem traceback:

```text
cadeia 78:  A4A/A4B/A4C = REPRODUCED       total 3   exit 0
cadeia 79:  A4A/A4B/A4C = NOT_REPRODUCED   total 0   exit 0
cadeia 79:  A3A/A3B     = NOT_REPRODUCED   total 0   exit 0   (não reabri nada)
```

---

## 9. Arquivos alterados

```text
app/memory/schemas/retention.py         CAMPOS_JSON_OBRIGATORIOS + regra_de_json
app/memory/models/retention_policy.py   @validates com estado do mapeamento,
                                        bind/result sem atalho de None,
                                        deserialize_rules delegando a forma
tests/unit/memory/test_retention_policy.py            +20 funções, 2 atualizadas
tests/integration/.../test_retention_policy_integration.py +8, 1 atualizada
tests/static/test_retention_policy_isolation.py       +4
docs/.../EDR_E4_9_6_3_...md                           novo
```

`retention_policy_repository.py` não precisou mudar. Nada em migration,
schema, `BaseRepository`, `GovernancePolicy`, `AccessibilityPolicy`, Sync,
Retrieval, E3, enums ou `errors/codes.py`. Nenhum código de erro novo;
`PIA-8042` e `PIA-8043` inalterados.

---

## 10. Riscos que declaro

**(a) A recusa de reatribuição é uma decisão de contrato, não uma lei da
natureza.** Se uma fatia futura precisar de um caminho legítimo para corrigir
`rules` antes do flush — não vejo qual seria, já que correção semântica cria
versão nova — ela vai encontrar esta recusa e terá de justificar a exceção em
EDR próprio. É o efeito pretendido.

**(b) `__dict__` direto continua contornando.** `policy.__dict__["rules"] = x`
não passa pelo evento de atributo, e `u59` faz isso de propósito para provar a
defesa de `typed_rules`. Frozen e eventos protegem contra mutação idiomática,
não contra circunvenção deliberada — mesma posição da E4.9.1, E4.6.3.1,
E4.9.6.1 e E4.9.6.2.

**(c) A validação de forma não é um validador de JSON Schema.** Cobre os seis
campos que o formato canônico grava. Um campo **extra** no objeto é ignorado,
não recusado — deliberado, porque recusar extras quebraria a leitura de
qualquer linha gravada por uma versão futura que acrescente campo, e essa
rigidez custaria mais do que protege hoje.

**(d) Homóglifos continuam fora.** `а` cirílico e `a` latino seguem sendo duas
chaves que se parecem, como declarado na E4.9.6.2.

**(e) A policy continua sem leitor.** Inalterado desde a E4.9.6.

---

## 11. Estado

```text
PATCH_CHAIN = 79
MIGRATION_HEAD = c8a3f5017e94 (INALTERADO)
E4_9_6_3_IMPLEMENTATION = COMPLETE_CANDIDATE
E4_9_6_3_STATUS         = AWAITING_INDEPENDENT_AUDIT
A4A = FIXED   A4B = FIXED   A4C = FIXED   SUPPRESSIONS = REMOVED
RETENTION_EVALUATOR = NOT_COMPOSED   TRASH_RUNTIME = NONE
DESTRUCTIVE_EFFECT = NONE
E4_9_7 = NOT_STARTED
```

`git am` do patch isolado sobre a cadeia 78 reproduz a TREE exata. O bundle
carrega `HEAD` e `refs/heads/audit/e3-final-validation`, sem refs residuais.

Não se declara `PASS_FINAL`, E4.9.6 não é promovida a `CLOSED_FINAL`, e não há
autorização para a E4.9.7.
