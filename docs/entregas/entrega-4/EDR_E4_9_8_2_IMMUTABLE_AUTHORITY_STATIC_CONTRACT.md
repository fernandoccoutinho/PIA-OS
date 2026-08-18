# EDR E4.9.8.2 — Imutabilidade da matriz de autoridade e restauração do contrato estático

**Natureza:** corretivo dos achados A18, A19 e A20 da auditoria independente da
E4.9.8.1.
**Baseline:** cadeia 86 (`8a728493`), `E4_9_8_1_AUDIT = FAIL_CORRECTIVE_REQUIRED`.

```text
MUTABLE_AUTHORITY_MATRIX = NONE
STATIC_TYPE_CONTRACT != RUNTIME_TYPE_ENFORCEMENT
BOTH_REQUIRED = TRUE
FROZEN_VALUE_OBJECT != FROZEN_GLOBAL_DEPENDENCY
```

```text
A18 = FIXED   A19 = FIXED   A20 = FIXED
PUBLIC_SIGNATURE_DELTA_CHAIN85_TO_CHAIN87 = 0
RUNTIME_TYPE_ENFORCEMENT = PRESERVED
MIGRATION_DELTA = 0  E3_DELTA = 0  E4_3_DELTA = 0  E4_9_7_DELTA = 0
E4_9_9 = NOT_STARTED
```

---

## 1. Causa raiz

### 1.1 A18 — `frozen=True` não protege dependência global mutável

A E4.9.8.1 fechou o binding de operação com uma tabela correta e uma guarda
que não podia falhar:

```python
OPERACAO_DE_GOVERNANCA: dict[DestructiveOperation, CognitiveOperation] = {...}
```

Os value objects são `frozen`, e eu tratei isso como se a fatia inteira fosse
imutável. Não era: a decisão sobre **qual governança autoriza qual ação** vivia
num `dict` público. Uma atribuição depois da importação trocava
`PERMANENT_ERASURE → READ`, e uma resolução de leitura passava a formar
proposta de apagamento permanente.

```text
FROZEN_VALUE_OBJECT != FROZEN_GLOBAL_DEPENDENCY
```

`s19` contava um único `AnnAssign` e as ocorrências no texto executável.
Provava unicidade **textual** — nunca tentou mutar a tabela. É a mesma família
de "guarda que só pode passar" que venho fechando desde a E4.9.7, desta vez
sobre a própria fronteira de autoridade.

### 1.2 A19/A20 — eu apresentei regressão de contrato como detalhe benigno

No relatório da cadeia 86 escrevi que a mudança para `object`

> amplia o tipo aceito estaticamente e o restringe em runtime, sem quebrar
> chamador algum.

A frase descreve o mecanismo corretamente e **omite o que importa**: era
regressão de contrato público, feita dentro de um corretivo cujo plano
declarava não prever assinatura nova. Não era detalhe; era exatamente o tipo de
mudança que o A6 da E4.9.7.4 estabeleceu como Stop Condition.

E há o agravante: `s99_7`, a demonstração que escrevi para provar que a guarda
consegue falhar, apresentava `operacao: object` como a versão **correta** desde
que houvesse `isinstance`. A suíte não apenas deixou de detectar a ampliação —
ela a sancionou.

```text
STATIC_TYPE_CONTRACT != RUNTIME_TYPE_ENFORCEMENT
BOTH_REQUIRED = TRUE
```

A anotação diz ao type checker o que é aceitável escrever; o `isinstance`
recusa o que chega apesar dela. Nenhum substitui o outro.

---

## 2. Baseline e caracterizações

```text
HEAD 8a72849355d396548f374dd8b26ff1695b0154aa
PARENT 74a388eb…  TREE c680741d…  PATCH_ID 7fbbddc8…  PATCH_CHAIN 86
MIGRATION_HEAD c8a3f5017e94   árvore limpa   87 commits
app/cognitive be407b46…   backend/alembic cc68c3e2…
```

Seis scripts, byte a byte, `stderr = 0`:

```text
                                              cadeia 86   cadeia 87
reproduce_e4971_defects.py                    0/8  EXIT=1  0/8  EXIT=1
reproduce_e4972_defects.py                    0/5  EXIT=1  0/5  EXIT=1
reproduce_e4973_textual_confidentiality.py    0/9  EXIT=1  0/9  EXIT=1
reproduce_e4974_verified_authority_default.py 0/3  EXIT=1  0/3  EXIT=1
reproduce_e4981_binding_defects_v2.py        0/11  EXIT=1 0/11  EXIT=1
reproduce_e4982_contract_defects.py           3/3  EXIT=0  0/3  EXIT=1
```

---

## 3. Inventário de usos públicos da matriz

Medido antes de decidir o mecanismo:

| Local | Uso | Impacto |
|---|---|---|
| `schemas/destructive_approval.py` (definição) | fonte | **muda** para `Mapping` |
| `schemas/destructive_approval.py` `__post_init__` | `[self.operation]` | leitura por chave — inalterado |
| `tests/unit/…` fábrica | `[operacao]` | inalterado |
| `tests/unit/…` totalidade | `set(...)`, comparação | inalterado |
| `tests/static/…` | `AnnAssign`, contagem | **muda** — `s19` reescrita |

Nenhum consumidor de produção fora do módulo. **Nenhuma mutação existente** — o
que confirma que a mutabilidade nunca foi requisito, apenas descuido.

---

## 4. Mecanismo escolhido e prova

`MappingProxyType` sobre **literal sem nome**:

```python
OPERACAO_DE_GOVERNANCA: Mapping[DestructiveOperation, CognitiveOperation] = (
    MappingProxyType({...})
)
```

Medido antes de adotar:

```text
tipo                  mappingproxy
__setitem__           TypeError
update/pop/clear/setdefault/popitem/__delitem__   AUSENTES
dict(proxy)           cópia independente; a fonte não muda
```

### 4.1 Ausência de backing mutável alcançável

Este é o ponto que o proxy sozinho **não** garante. Se eu escrevesse
`_OPERACAO = {...}` e depois `MappingProxyType(_OPERACAO)`, o dicionário
privado continuaria alcançável como atributo de módulo, e
`MUTABLE_AUTHORITY_MATRIX = NONE` seria falso.

O argumento é um literal sem nome: nenhum símbolo de módulo o referencia.
`u98` varre `dir(modulo)` procurando qualquer `dict` com chaves
`DestructiveOperation` e falha se encontrar um; `s19` exige na AST que o
argumento de `MappingProxyType` seja `ast.Dict` — um `ast.Name` ali significaria
backing nomeado.

### 4.2 Limite declarado

`MappingProxyType` não protege contra introspecção deliberada de runtime, por
exemplo `gc.get_referents`. Isso está fora do modelo de ameaça: a proteção é
contra mutação **acidental e idiomática**, não contra decisão deliberada com
ferramentas de baixo nível. Mesma posição das redações de representação das
fatias anteriores, e declarada aqui em vez de alegada como imutabilidade
absoluta.

### 4.3 Alternativas rejeitadas

| Alternativa | Por que |
|---|---|
| função `match` total | perde a legibilidade da matriz e a checagem de totalidade por `set()` |
| `frozenset` de pares | obriga varredura linear na leitura, sem ganho |
| cópia defensiva na leitura | o §5.1 do prompt proíbe nominalmente |
| propriedade devolvendo o dict interno | idem — expõe o backing |
| `dict` com guarda de teste que tenta mutar | deixa a mutação possível em produção; guarda não é imutabilidade |

---

## 5. Restauração do contrato estático

```text
                       cadeia 85              cadeia 86       cadeia 87
satisfies(operacao)    DestructiveOperation   object          DestructiveOperation
permite_proposta(canal) InputChannel          object          InputChannel
```

```text
PUBLIC_SIGNATURE_DELTA_CHAIN85_TO_CHAIN87 = 0
```

Preservados dentro dos métodos: `isinstance` explícito, `TypeError` controlado
para string equivalente, `None`, `bool` e objeto arbitrário. Sem coerção, sem
alias, sem `False` para tipo inválido.

Os testes de entrada inválida usam **invocação por referência** — o método é
obtido como valor e chamado — para medir o runtime sem enfraquecer a assinatura
e sem `type: ignore`, `Any` ou `cast`.

---

## 6. Matriz A18–A20

| # | Reprodução na cadeia 86 | Correção | Regressão | Guarda |
|---|---|---|---|---|
| A18 | trocar item da matriz faz `READ` autorizar apagamento | `Mapping` sobre literal sem nome | `u92`–`u99` | `s19` reescrita |
| A19 | `get_type_hints(satisfies)["operacao"] is object` | anotação `DestructiveOperation` | `u100`, `u102`, `u103` | `s23`, `s99_7` |
| A20 | idem para `canal` | anotação `InputChannel` | `u101`, `u102`, `u104` | `s23`, `s99_7` |

### 6.1 Um detalhe que faria o teste passar pelo motivo errado

`type(proxy).__setitem__` levanta **`AttributeError`**, não `TypeError` — o
proxy simplesmente não tem o método. A sonda tem de exercitar a **operação**
(`operator.setitem`), não procurar o atributo. Um teste que capturasse
`AttributeError` passaria sem provar que a escrita é recusada.

---

## 7. As três guardas reescritas

**`s19`** passou a provar três coisas distintas: fonte única (um `AnnAssign`,
uma ocorrência de cada `CognitiveOperation`), forma imutável na AST
(`MappingProxyType` sobre `ast.Dict`) e recusa dinâmica de escrita
(`operator.setitem` → `TypeError`).

**`s23`** verificava só `isinstance` e `TypeError`. Passou a exigir também a
**anotação exata**, na AST e por `get_type_hints`.

**`s99_7`** apresentava `object` como correto. Reescrita com três mutantes —
anotação sem runtime, runtime com anotação ampliada, nenhum dos dois — todos
rejeitados; só a combinação completa passa.

As oito demonstrações `s99` anteriores foram preservadas.

---

## 8. Garantia por camada

| Garantia | Camada |
|---|---|
| matriz não aceita escrita | `TYPE_LEVEL` (mappingproxy) |
| matriz sem backing alcançável | `APPLICATION_LEVEL` (literal sem nome) |
| matriz total sobre `DestructiveOperation` | `APPLICATION_LEVEL` (`u99`) |
| contrato estático dos dois helpers | `TYPE_LEVEL` (anotação) |
| recusa de não-membro em runtime | `APPLICATION_LEVEL` (`isinstance`) |
| os onze bindings da E4.9.8.1 | `APPLICATION_LEVEL` — preservados |
| proteção contra introspecção deliberada | `NOT_MODELED` — §4.2 |
| autenticação, persistência, consumo, TOCTOU, delegação | `DEFERRED` |

---

## 9. Conformidade documental — quatro camadas (Master v2.3)

### 9.1 `PIA_OS_SOPHIA_MASTER_COMPATIBILITY` — 20 linhas

```text
 1 USER_AUTHORITY_PRESERVED ............... REFORÇADO. A matriz que decide
     qual governança autoriza cada ação deixa de ser alterável após import.
 2 SOPHIA_BRAND_PIA_OS_CODEBASE_PRESERVED . SIM.
 3 MODULE_SCOPE_AND_DEFERRED_CAPABILITIES . Implementado: A18, A19, A20 e
     nada além. Diferidos: os mesmos da cadeia 86, inalterados.
 4 SCHEDULE_MODE_DECLARED ................. NOT_APPLICABLE.
 5 AI_ROLE_AND_STEP_INSTRUCTION_DISTINGUISHED NOT_APPLICABLE.
 6 PROVIDER_CONNECTION_METHOD_DECLARED .... NOT_APPLICABLE.
 7 AUTOMATION_SCOPE_DECLARED .............. NENHUMA.
 8 APPROVAL_GATES_DECLARED ................ REFORÇADO: o portão de operação
     deixa de ser contornável por mutação global.
 9 PERSISTENCE_BEHAVIOR_DECLARED .......... NENHUMA.
10 MULTI_AI_RESULT_ATTRIBUTION_DECLARED ... NOT_APPLICABLE.
11 DIVERGENCE_PRESERVATION_DECLARED ....... SIM. Nenhuma normalização; a
     matriz não ganhou `get(..., default)` nem fallback.
12 CONCURRENT_WORK_ISOLATION_DECLARED ..... Inalterado desde a cadeia 86.
13 BACKGROUND_EXECUTION_AUTHORIZATION ..... NOT_APPLICABLE.
14 RESOURCE_LIMITS_QUEUE_AND_COST_DECLARED  NOT_APPLICABLE.
15 REMOTE_RESOURCE_SCOPE_DECLARED ......... NENHUM acesso remoto.
16 OBSERVATION_PREPARATION_EXECUTION ...... Inalterado; ainda PREPARAÇÃO.
17 CREDENTIAL_AND_SECRET_BOUNDARY_DECLARED  SIM. Nenhum campo novo.
18 FAILURE_ROLLBACK_AND_CONCURRENCY ....... Sem escrita; a tentativa de
     mutação falha com TypeError, sem estado parcial.
19 CURRENT_CAPABILITY_NOT_OVERSTATED ...... §4.2 declara o limite de
     introspecção em vez de alegar imutabilidade absoluta.
20 FROZEN_MODULES_UNCHANGED ............... cognitive, alembic, E4.3 e
     E4.9.7 intocados.
```

### 9.2 `SOPHIA_UX_COMPATIBILITY` — 17 linhas

```text
 1 USER_AUTHORITY_PRESERVED ............... REFORÇADO.
 2 SCHEDULE_MODE_DECLARED ................. NOT_APPLICABLE.
 3 AUTOMATION_SCOPE_DECLARED .............. NENHUMA.
 4 PERSISTENCE_BEHAVIOR_DECLARED .......... NENHUMA.
 5 PROVIDER_NEUTRALITY_PRESERVED .......... SIM — nada tocado.
 6 PERSONALIZATION_REVERSIBLE ............. NOT_APPLICABLE.
 7 CONCURRENT_WORK_ISOLATION_DECLARED ..... Inalterado.
 8 BACKGROUND_EXECUTION_AUTHORIZATION ..... NOT_APPLICABLE.
 9 RESOURCE_LIMITS_AND_QUEUE_DECLARED ..... NOT_APPLICABLE.
10 AI_ROLE_CONTROL_DECLARED ............... NOT_APPLICABLE.
11 ROLE_AND_STEP_INSTRUCTION_DISTINGUISHED  NOT_APPLICABLE.
12 PIA_SEQUENCE_SUGGESTION_BEHAVIOR ....... NOT_APPLICABLE.
13 MULTI_AI_RESULT_ATTRIBUTION_DECLARED ... NOT_APPLICABLE.
14 PIA_INTEGRATION_DIVERGENCE_PRESERVATION  NOT_APPLICABLE.
15 POST_RESULT_USER_COMMAND_DECLARED ...... Inalterado.
16 RESULT_APPROVAL_AND_PERSISTENCE ........ Inalterado.
17 FROZEN_MODULES_UNCHANGED ............... SIM.
```

### 9.3 `MULTICHANNEL_COMMAND_COMPATIBILITY_v1_3` — 10 marcadores

```text
 1 INPUT_CHANNELS_DECLARED ................ TEXT | VOICE, inalterado.
 2 COMMAND_ENVELOPE_DECLARED .............. Inalterado.
 3 CHANNEL_NORMALIZATION_DECLARED ......... NOT_APPLICABLE.
 4 IDENTITY_CONTEXT_AND_SCOPE_DECLARED .... Inalterado.
 5 VOICE_CONFIDENCE_AND_CORRECTION ........ REFORÇADO no contrato ESTÁTICO:
     `permite_proposta` volta a exigir `InputChannel` também para o checker.
 6 CONFIRMATION_POLICY_DECLARED ........... Inalterado.
 7 DESTRUCTIVE_INTENT_BINDING_DECLARED .... REFORÇADO: a matriz que liga
     intenção destrutiva a pergunta de governança deixa de ser alterável.
 8 GOVERNANCE_PARITY_ACROSS_CHANNELS ...... Preservada; ambos os helpers
     voltam ao tipo fechado simetricamente.
 9 AUDIT_AND_RECEIPT_DECLARED ............. NOT_APPLICABLE.
10 CURRENT_CAPABILITY_NOT_OVERSTATED ...... SIM — §8.
```

### 9.4 Parte II §12 — 8 obrigações

```text
1 citar esta diretriz .................... citada aqui e no plano.
2 declarar o que será implementado ....... A18, A19, A20.
3 declarar o que continua diferido ....... §8, linhas DEFERRED e NOT_MODELED.
4 separar observação/preparação/aprovação/execução — inalterado.
5 identificar o usuário ou autoridade competente — usuário presente e
    autenticado; esta fatia não cria a infraestrutura que prova a presença.
6 definir falhas, rollback e concorrência . TypeError na tentativa de
    mutação, sem estado parcial; `Mapping` imutável é seguro entre threads.
7 verificar compatibilidade com E3/E4 congeladas — delta zero.
8 interromper em Stop Condition .......... nenhuma disparou; a assinatura
    pública foi RESTAURADA, não alterada.
```

### 9.5 Parte II §12.1 — 11 Stop Conditions mínimas

```text
 1 nova entidade persistente ou migração ... não exigida.
 2 ownership de Workspace/Schedule/domínio/conector — não exigido.
 3 armazenamento de credenciais ........... não exigido.
 4 execução externa irreversível .......... não exigida.
 5 ampliação silenciosa de autoridade ..... É O DEFEITO QUE FECHO. O
     corretivo só restringe: matriz somente leitura e anotações fechadas.
 6 assinatura de provedor não suportada ... não exigida.
 7 sincronização destrutiva de arquivos ... não exigida.
 8 perda de proveniência ou origem ........ não ocorre.
 9 colapso entre múltiplos Schedules ...... NOT_APPLICABLE.
10 execução sem rollback declarado ........ NOT_APPLICABLE.
11 alteração de congelados por conveniência não ocorre.
```

### 9.6 Parte II §12.2 — 11 provas mínimas

```text
 1 nenhuma chamada externa quando recusado . PROVADA.
 2 nenhum acesso fora do escopo autorizado . PROVADA, inalterada.
 3 nenhuma escrita durante observação/preparação — PROVADA.
 4 aprovação obrigatória antes de ação crítica — REPRESENTADA.
 5 rollback sob falha injetada ............ NOT_APPLICABLE.
 6 proteção contra estado obsoleto ........ DEFERRED.
 7 comportamento concorrente determinístico  REFORÇADA: a única estrutura
     global mutável da fatia deixou de existir.
 8 preservação de origem, versão e histórico PROVADA.
 9 recibo fiel ao pedido e à execução ..... NOT_APPLICABLE.
10 cancelamento sem estado parcial oculto . NOT_APPLICABLE.
11 isolamento entre Schedules e Workspaces  PROVADA.
```

### 9.7 Parte III §13 — impacto sobre distinções

```text
1 cria distinção?          NÃO — restringe o que já existia
2 transforma distinção?    NÃO
3 compara distinções?      NÃO
4 muda acessibilidade?     NÃO
5 afeta persistência?      NÃO
6 altera proveniência?     NÃO
7 altera história causal?  NÃO
```

### 9.8 E5 / COUT-P

`E4_INTEGRATION_OF_COUT_P = FORBIDDEN` respeitado. Nenhum score, nenhuma
dependência.

---

## 10. Gates medidos

Clone limpo, PostgreSQL recriado e pré-migrado:

```text
COLLECTED        3420                                  (cadeia 86: 3393)
FULL_SUITE       3419 passed / 1 skipped / 0 failed    (cadeia 86: 3392/1/0)
RAW_SUITE        2952 passed / 468 skipped / 0 failed  (cadeia 86: 2925/468/0)
GLOBAL_COVERAGE  99,29%   — não caiu
  approval_enums.py            52/52    100%
  destructive_approval.py    239/239    100%
RUFF PASS   BLACK PASS (391)
MYPY app    7 históricos, NEW = 0
supressões / cast / Any novos: 0
ALEMBIC heads = current = c8a3f5017e94
git diff --check CLEAN
```

**Regressões, delta 0:**

```text
E3 = 732 · E4.1 = 40 · E4.2 = 42 · E4.3 = 255 · E4.4 = 74 · E4.5 = 187
E4.6 = 275 · E4.7 = 240 · E4.8 = 146 · E4.9.5 = 113 · E4.9.6 = 309
E4.9.7 = 285
```

**Fatia: E4.9.8 = 239 → 266** (234 unitários + 32 estáticos), três execuções
idênticas. Os 239 anteriores continuam passando.

---

## 11. Arquivos

```text
ALTERADOS
  app/memory/schemas/destructive_approval.py     matriz → Mapping imutável
  app/memory/models/approval_enums.py            anotações restauradas
  tests/unit/memory/test_destructive_approval.py u92–u104
  tests/static/test_destructive_approval_isolation.py  s19, s23, s99_7
NOVO
  docs/entregas/entrega-4/EDR_E4_9_8_2_...md
```

Nada em E3, E4.3, contratos da E4.9.7, Alembic, migration, ORM, adapter, efeito
ou recibo.

---

## 12. Riscos restantes

**(a) A imutabilidade é de runtime idiomático, não absoluta.** `gc.get_referents`
alcança o dicionário subjacente. Declarado, fora do modelo de ameaça — e é o
tipo de limite que prefiro escrito a descoberto por auditoria.

**(b) Décima vez que uma guarda minha não podia falhar.** `s19` provava texto,
não estrutura. O padrão persiste apesar da lição registrada, e a única
contramedida que funcionou até agora é exigir demonstração de falha para cada
guarda nova — que é o que as onze `s99` fazem.

**(c) Apresentei uma regressão pública como detalhe benigno.** Não foi engano de
medição: eu descrevi o mecanismo com precisão e omiti a classificação. É o modo
de falha mais difícil de guardar contra, porque o texto está correto e a
conclusão não.

**(d) Os limites da cadeia 86 seguem abertos.** `GovernanceResolution` vazando
na fonte, delegação não modelada, TOCTOU, replay, nonce sem consumo. Nenhum
tocado por este corretivo.

---

## 13. Estado

```text
PATCH_CHAIN = 87
MIGRATION_HEAD = c8a3f5017e94 (INALTERADO)
E4_9_8_2_IMPLEMENTATION = COMPLETE_CANDIDATE
E4_9_8 = AWAITING_INDEPENDENT_REAUDIT
A18 = FIXED   A19 = FIXED   A20 = FIXED
PUBLIC_SIGNATURE_DELTA_CHAIN85_TO_CHAIN87 = 0
MUTABLE_AUTHORITY_MATRIX = NONE
AUTHENTICATOR = NONE          ERASURE_EFFECT = NONE
DELEGATION = NOT_MODELED
E4_9_READY = FALSE
E4_9_9 = NOT_STARTED
```

`PASS_FINAL` pertence à auditoria independente.
