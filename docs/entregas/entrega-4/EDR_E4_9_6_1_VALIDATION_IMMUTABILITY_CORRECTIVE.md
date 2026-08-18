# EDR E4.9.6.1 — Opaque-Key Validation and Deep Read Immutability

**Natureza:** corretivo dos dois defeitos reproduzidos pela auditoria
independente da E4.9.6. Não é fatia funcional nova.
**Baseline:** cadeia 76 (`83f31ba0`), `E4_9_6_AUDIT = FAIL_CORRECTIVE_REQUIRED`.

```text
VALIDATED OPAQUE KEY != NORMALIZED KEY
PERSISTENT IMMUTABILITY != DEEP READ IMMUTABILITY
BOTH ARE REQUIRED
```

```text
A1_OPAQUE_KEY_VALIDATION  = FIXED
A2_DEEP_READ_IMMUTABILITY = FIXED
MIGRATION_DELTA = 0   DATABASE_SCHEMA_DELTA = 0   E3_DELTA = 0
EVALUATOR_DELTA = 0   EFFECT_DELTA = 0
```

Os dois achados são defeitos meus, e ambos são reais. Este documento
registra a reprodução antes e depois, a estratégia escolhida e o que
ela não resolve.

---

## 1. Baseline verificada

```text
HEAD 83f31ba0…  PARENT 74fe1ae8…  TREE 14a8e06c…  PATCH_ID 04e1e8b0…
MIGRATION_HEAD c8a3f5017e94   árvore limpa
app/cognitive be407b46f679a009e0f7f7e9f01fb784f08dea54
FULL 2653 passed / 1 skipped / 0 failed
RAW  2219 passed / 435 skipped / 0 failed
```

**Nenhum consumidor runtime** de `RetentionPolicyRepository` fora do
próprio arquivo — condição necessária para poder mudar a superfície de
leitura sem quebrar ninguém.

**Inventário dos métodos herdados de `BaseRepository` que devolvem a
entidade ORM**, exigido pelo §2: `add`, `create`, `get_by_id`,
`get_by_id_or_raise`, `list`, `refresh`, `paginate`. Os demais
(`exists`, `exists_by`, `count`, `total_pages`, `has_next`) devolvem
escalares; `update` e `delete` já eram recusados desde a E4.9.6.

---

## 2. Achado A1 — reprodução antes e depois

O §10 do prompt da E4.9.6 tornou obrigatória a rejeição de caracteres
de controle. Implementei isso **apenas** em `RetentionRule.rule_id`. Em
`policy_key` e `governance_policy_key` verifiquei somente `strip()`, e
`strip()` não vê um `\n` cercado de texto.

**Antes (cadeia 76), pelo caminho público `add_policy`:**

```text
policy_key='ret\nembedded'   gov='gov.ok'      → ACEITO
policy_key='ret.ok'          gov='gov\tkey'    → ACEITO
policy_key='ret\x00x'                          → ACEITO
policy_key='ret\x7fx'                          → ACEITO
policy_key= 257 caracteres                     → ACEITO
```

**Depois (cadeia 77):**

```text
todos os cinco                                 → recusados
256 caracteres                                 → aceito
chave válida com espaços e acentos             → devolvida byte a byte
```

### 2.1 A correção

`validar_identificador_opaco(nome, valor, tamanho)` em
`schemas/retention.py`, aplicado a `rule_id`, `policy_key` e
`governance_policy_key`. Contrato: tipo exatamente `str`; não vazio nem
branco; todo C0 (`U+0000..U+001F`) e DEL (`U+007F`) recusados; teto em
caracteres; **valor original devolvido**.

Não normalizar é parte do contrato, não descuido:

```text
VALIDATED OPAQUE KEY != NORMALIZED KEY
```

Uma chave que o sistema altera em silêncio deixa de ser a identidade
que o chamador declarou, e a policy publicada passaria a responder por
uma chave que ninguém escreveu. `TypeError` e `ValueError` permanecem
diagnósticos distintos, como em todo o projeto.

Nenhuma migration foi criada para A1. Os `CHECK`s de banco existentes
permanecem como defesa; a correção exigida era a fronteira tipada.

---

## 3. Achado A2 — reprodução antes e depois

**Antes (cadeia 76):**

```python
policy.rules[0]["minimum_age_days"] = 0   # aceito em memória
policy.typed_rules                        # ValueError: deve ser >= 1
```

Nenhuma das três camadas de imutabilidade dispara, e a razão é
instrutiva: **nada foi persistido**. Mapper event, override de
repositório e trigger protegem a escrita. O objeto na identity map
passou a mostrar algo que o banco não tem.

Hoje isso é inócuo porque não há avaliador. Amanhã, um avaliador na
mesma sessão poderia ler uma policy diferente da persistida — e essa é
exatamente a classe de defeito que a E4.6.3.1 já me custou uma vez:

```text
CONTRACT SHAPE GOVERNS THE RETURN; VALUE ISOLATION GOVERNS THE ARGUMENT
```

Ali eu havia protegido o retorno e deixado o argumento exposto. Aqui
protegi a persistência e deixei a leitura exposta. É a mesma forma de
erro em outra fronteira.

**Depois (cadeia 77):**

```text
type(policy.rules)                    → tuple
policy.rules[0]["minimum_age_days"]=0 → TypeError
policy.rules[0].minimum_age_days = 0  → FrozenInstanceError
policy.rules[0] = outra_regra         → TypeError
valor observado                       → preservado
```

---

## 4. Estratégia escolhida — e por que não a outra

### 4.1 Adotada: Estratégia A, congelamento na fronteira ORM

`RetentionRulesType(TypeDecorator)`. O atributo `rules` **é**
`tuple[RetentionRule, ...]` em memória e vira JSON apenas ao ir para o
disco: `process_bind_param` serializa canonicamente,
`process_result_value` reconstrói pelo construtor tipado.

Não existe `list[dict]` pública em momento algum — nem na escrita. E,
como o congelamento vive no **tipo da coluna**, todo método herdado de
`BaseRepository` passa a devolver a estrutura já imutável sem que
nenhuma assinatura mude.

`load_dialect_impl` devolve `JSONB` no PostgreSQL e `JSON` nos demais,
idêntico ao que a migration `c8a3f5017e94` criou:

```text
MIGRATION_DELTA = 0   DATABASE_SCHEMA_DELTA = 0
```

Verificado no banco real: `data_type = jsonb`, 4 `CHECK`, trigger
`trg_retention_policies_append_only`, head `c8a3f5017e94`.

### 4.2 Rejeitada: Estratégia B, `RetentionPolicyView` com confinamento

O prompt é explícito: não basta um `get_view()` opcional enquanto
`get_by_id()` e `list()` continuam devolvendo ORM cru. Confinar de
verdade exigiria sobrescrever os **sete** métodos herdados com tipo de
retorno incompatível com `BaseRepository[ModelType]` — o que só
fecharia no mypy com `type: ignore` novo (vedado pela Stop Condition 8)
ou alterando `BaseRepository` (vedado pela Stop Condition 3).

A Estratégia A resolve o mesmo problema sem tocar em nenhum dos dois.

### 4.3 Rejeitada: cópia rasa na leitura

`tuple` externo contendo `dict` interno continua mutável. O prompt já
proíbe, e a proibição está certa: seria mascarar o defeito.

---

## 5. Alcance real — e o que continua possível

```text
policy.rules[0]["x"] = 0             → TypeError
policy.rules[0].minimum_age_days = 0 → FrozenInstanceError
policy.rules[0] = outra              → TypeError
domain_ids.add(...)                  → AttributeError (frozenset)
```

**O que continua possível, declarado honestamente:**
`object.__setattr__(policy.rules[0], "minimum_age_days", 0)` contorna
`frozen=True`, como contorna em qualquer dataclass congelada do
projeto. É o mesmo limite que a E4.9.1 e a E4.6.3.1 já declararam:
frozen protege contra mutação **acidental e idiomática**, não contra
circunvenção deliberada.

A diferença relevante é que, mesmo assim, o banco não muda: a mutação
não persiste, e uma nova sessão lê os bytes originais — provado em
`test_i26`.

Um `UPDATE`/`DELETE` por SQL bruto continua recusado pela trigger. Uma
linha gravada por SQL bruto com JSON semanticamente inválido continua
falhando na leitura — só que agora **na própria carga**, dentro de
`process_result_value`, e não mais quando alguém pedisse `typed_rules`.
A linha inválida deixou de ser observável como objeto, o que é mais
estrito, não menos.

---

## 6. Supressão de tipo — contagem inalterada

A cadeia 76 já carregava `# type: ignore[no-untyped-call]` na
construção de `JSONB()`, na constante `_RULES_JSON` que este decorador
substituiu. A supressão foi **movida**, não criada: o arquivo continua
com exatamente uma, no mesmo motivo e no mesmo tipo.

```text
MYPY 7 erros históricos em 3 arquivos, NEW = 0
```

---

## 7. Testes ajustados e acrescentados

**Dois testes meus da E4.9.6 assumiam a representação antiga** e foram
atualizados com nota — não afrouxados:

- `test_u25` construía a policy com `serialize_rules(...)`, isto é,
  `list[dict]`. Agora passa a tupla tipada e ainda verifica
  `typed_rules is rules`;
- `test_i20` esperava `KeyError` ao pedir `typed_rules`; agora a recusa
  ocorre na carga, e o teste assevera isso.

**Acrescentados:** 11 unitários de A1 (matriz de controle nos dois
campos, limites 256/257, tipo errado, ausência de normalização,
contrato do validador compartilhado), 6 unitários de A2 (tupla tipada,
mutação aninhada, `domain_ids`, round trip do decorador, nulos e forma
inválida, dialetos), 8 de integração (recusa antes do banco, leitura
imutável, duas leituras na mesma sessão, bytes originais em nova
sessão, **os sete métodos herdados**, publicação, schema idêntico,
trigger e colisão preservadas) e 5 guardas estáticas.

Uma guarda minha nasceu frágil e eu a corrigi: `test_s15` fatiava o
texto bruto e acusava a docstring que **explica** por que o validador
não normaliza — o mesmo falso positivo que já me pegou na E4.9.6. Passou
a usar a AST, e a contagem de chamadas passou a ser feita por nós de
`ast.Call` em vez de substring, porque o import multilinha não repete o
parêntese.

---

## 8. Gates medidos

Em clone limpo com PostgreSQL recriado:

```text
FULL_SUITE       2690 passed / 1 skipped / 0 failed
RAW_SUITE        2248 passed / 443 skipped / 0 failed
GLOBAL_COVERAGE  99,23%   (era 99,20% — subiu)
  retention_enums.py               100%
  retention_policy.py              100%
  schemas/retention.py             100%
  retention_policy_repository.py   100%
RUFF PASS   BLACK PASS   MYPY 7 históricos, NEW = 0
ALEMBIC single head c8a3f5017e94 — INALTERADO
git diff --check CLEAN
```

**Regressões, delta 0:** E3 = 732 · E4.1 = 40 · E4.2 = 42 · E4.3 = 255 ·
E4.4 = 74 · E4.5 = 187 · E4.6 = 275 · E4.7 = 240 · E4.8 = 146 ·
E4.9.5 = 113.

**E4.9.6 = 131** (era 94): os 37 acrescidos são deliberados, conforme o
§8 do prompt. Rodados três vezes com resultado idêntico.

---

## 9. Arquivos alterados

```text
app/memory/schemas/retention.py                       validador + MAX_KEY_LENGTH
app/memory/models/retention_policy.py                 RetentionRulesType, coluna tipada
app/memory/repositories/retention_policy_repository.py validação das duas chaves
tests/unit/memory/test_retention_policy.py            +17 testes, 1 atualizado
tests/integration/.../test_retention_policy_integration.py +8 testes, 1 atualizado
tests/static/test_retention_policy_isolation.py       +5 guardas
docs/.../EDR_E4_9_6_1_...md                           novo
```

Nada em `errors/codes.py`, enums, migration, `BaseRepository`,
`GovernancePolicy`, `AccessibilityPolicy`, Sync, Retrieval ou E3.
Nenhum código de erro novo.

---

## 10. Riscos que declaro

**(a) O mesmo erro em outra fronteira.** Protegi o retorno e esqueci o
argumento na E4.6.3.1; protegi a persistência e esqueci a leitura aqui.
A lição que registro é de método, não de caso: quando uma garantia é
declarada, vale enumerar **todas** as fronteiras por onde o valor
entra e sai, em vez de a que estava em foco.

**(b) `object.__setattr__` continua contornando.** Declarado no §5. A
proteção é contra mutação idiomática, e a persistência permanece
intacta de qualquer forma.

**(c) A reconstrução tipada agora ocorre em toda carga.** Antes só ao
pedir `typed_rules`. É mais estrito e um pouco mais caro; irrelevante
para configuração local, e vale registrar caso alguém um dia liste
milhares de versões.

**(d) A validação não inspeciona semântica.** Recusa controle, vazio e
excesso; não adivinha se a chave é um caminho, um segredo ou um
localizador — mesma posição declarada na E4.9.5 para `scope_token`,
porque heurística que falha em silêncio é pior que ausência de
checagem.

---

## 11. Estado

```text
PATCH_CHAIN = 77
MIGRATION_HEAD = c8a3f5017e94 (INALTERADO)
E4_9_6_1_IMPLEMENTATION = COMPLETE_CANDIDATE
E4_9_6_1_STATUS         = AWAITING_INDEPENDENT_AUDIT
A1_OPAQUE_KEY_VALIDATION  = FIXED
A2_DEEP_READ_IMMUTABILITY = FIXED
RETENTION_EVALUATOR = NOT_COMPOSED
E4_9_7 = NOT_AUTHORIZED
```

Não se declara `PASS_FINAL`, E4.9.6 promovida a `CLOSED_FINAL`, nem
autorização para a E4.9.7.
