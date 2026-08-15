# E4_5_CONSOLIDATION_MANAGER

**Módulo:** E4.5 — Consolidation Manager
**Baseline:** `PATCH_CHAIN = 47` · HEAD `b4e61a4702a4…` ✓ ·
TREE `1f24428c7754…` ✓ · PARENT `0e4d8c6e9f17…` ✓ ·
PATCH_ID `cab59cdc55e4…` ✓ · bundle SHA-256 `12a76ab4…cd8c` ✓ ·
patch SHA-256 `c7fc7bdb…b44f` ✓ · migration head `4ca61776b982` ✓ ·
`git status` limpo ✓ · patches 46 e 47 na cadeia ✓
**Patch:** `e4-5-consolidation-manager.patch` (48º)

Trees protegidos conferidos na baseline:

```text
backend/app/cognitive = be407b46f679a009e0f7f7e9f01fb784f08dea54
backend/app/memory    = c5cec4aeab8d494c24ccd71bb766265bc2250619
backend/alembic       = f01a1f812eb11695b9daeb6b1707e6477e9330fa
```

Suíte da baseline reexecutada antes de qualquer alteração:
**1451 passed / 1 skipped / 0 failed**.

---

## 1. Definição operacional de consolidação

Consolidar é **registrar estruturalmente** que N fontes deram origem a
um alvo, de modo que a origem permaneça permanentemente reconstruível:

```text
{M1, ..., Mn} → S1        e sempre        S1 ← {M1, ..., Mn}
```

Não é resumir, não é substituir, não é apagar:

```text
CONSOLIDATION != DELETION
SUMMARY       != SOURCE REPLACEMENT
MERGE         != IDENTITY COLLAPSE
NO SILENT SOURCE ERASURE
```

A E4.5 acrescenta **orquestração, disciplina e verificação** — não uma
nova fonte da verdade:

```text
NEW PERSISTENT ENTITY = NO    NEW TABLE = NO
NEW COLUMN            = NO    NEW MIGRATION = NO
NEW CONSOLIDATION ENUM = NO
```

O alvo é um `CognitiveObject` da E3; a origem é `LineageEdge(MERGE)`; a
operação é um `TransformationRecord(DERIVATION)`; a ocorrência é um
`CausalHistoryEvent(TRANSFORMED)`. Nenhuma entidade da lista proibida
(`ConsolidatedObject`, `ConsolidationRecord`, `ConsolidationLineage`,
`MemoryItem`, `PersistenceRecord`, `ConsolidationPolicy`,
`ConsolidationScore`) foi criada — provado por teste que inspeciona o
registry: as tabelas de `app/memory` continuam sendo exatamente
`memory_domains`, `memory_domain_memberships` e `governance_policies`.

---

## 2. A porta estrutural

`app/memory` não importa `app.cognitive`. O writer chega por
`MultiInputTransformationPort` / `MultiInputTransformationReceiptPort`
(`app/memory/ports/consolidation.py`), satisfeitos **estruturalmente**
pelo `MultiInputTransformationManager` e pelo
`MultiInputTransformationReceipt` da E3.4.2.

Os membros do recibo são declarados como `@property`, tornando o
protocolo somente-leitura: um `Protocol` com atributos mutáveis exigiria
que o implementador também os tivesse mutáveis, o que um dataclass
`frozen` não oferece — e a E4.5 não tem nada que escrever num recibo.

**Sem adapter.** A composição é direta:

```python
ConsolidationManager(
    transformation_port=MultiInputTransformationManager(...),
    persistence_manager=PersistenceManager(...),
)
```

Verificado em integração (`ci1`), com `isinstance` contra os dois
protocolos `runtime_checkable` — conformidade **verificada**, não
presumida. Nenhum `importlib`, `sys.modules`, registry, `TYPE_CHECKING`,
resolução por nome, `table()/column()` de escrita, SQL cru, callback
genérico ou duplicação de modelo/enum da E3.

Os testes importam os dois lados para montar a composição, o que o §5
permite explicitamente; o código de produção de `app/memory` não — e
isso é verificado por varredura em todo `app/`.

---

## 3. E3 permanece writer exclusivo

Toda escrita de patrimônio acontece dentro de `app/cognitive`, pela
E3.4.2. A E4.5 não escreve em tabela alguma:

```text
DATABASE_WRITES_BY_APP_MEMORY_DIRECTLY = 0
INTERNAL_COMMIT = 0
```

Provado por ausência estrutural: o **código executável** dos dois
módulos novos (AST com docstrings removidas, técnica de E4.3.1) não
contém `commit(`, `rollback(`, `Session`, `UnitOfWork`, `INSERT`,
`UPDATE`, `DELETE`, `text(`, `execute(`, `table(` nem `column(`. As
docstrings citam nominalmente o que o módulo não faz, então comparar o
texto bruto produziria falso positivo — o mesmo erro que a E4.3.1
corrigiu em `gv16`.

---

## 4. Consumo real da E4.4

A dependência é substantiva, não decorativa. Depois que a porta devolve
o recibo:

```python
assessment = persistence_manager.assess(receipt.target_coid)
```

A porta e o `PersistenceManager` são compostos sobre a **mesma
`Session`** — sem isso a avaliação não enxergaria as escritas ainda não
commitadas e a verificação seria uma consulta a um estado anterior à
própria consolidação, isto é, uma prova vazia.

Verificado, e qualquer divergência acumula motivo:

| # | Verificação |
|---|---|
| 1 | `assessment.coid == receipt.target_coid` |
| 2 | `outcome == RECORDED_CONTINUITY_EVIDENCE` |
| 3 | `subject_deleted == False` |
| 4 | exatamente uma `LINEAGE_PARENT` por fonte |
| 5 | conjunto de `related_coid` igual às fontes |
| 6 | referências das evidências iguais aos `lineage_edge_ids` |
| 7 | **correspondência posicional** fonte ↔ edge |
| 8 | **todas** as `LINEAGE_PARENT` com `qualifier == "merge"` |
| 9 | exatamente um `TRANSFORMATION_OUTPUT` |
| 10 | referência da transformação igual a `transformation_id` |
| 11 | ids dos `CAUSAL_EVENT` iguais aos `causal_event_ids` |
| 12 | **cardinalidade causal exata**, checada antes do conjunto |
| 13 | **todos** os eventos com `qualifier == "TRANSFORMED"` |
| 14 | `assessment.clid == target_clid` |

A verificação nº 7 não é redundante com a 5 e a 6: os dois conjuntos
podem bater com o **pareamento trocado**, e um teste dedicado monta
exatamente esse caso. A nº 12 pelo mesmo motivo: comparar só conjuntos
mascararia um evento sobrando.

### Contrato de qualifier (corretivo E4.5.1)

```text
LINEAGE QUALIFIER CONTRACT = EXACT PERSISTED TOKEN "merge"
CAUSAL QUALIFIER CONTRACT  = EXACT PERSISTED TOKEN "TRANSFORMED"

PERSISTED ENUM ASYMMETRY = KNOWN AND PRESERVED
ASYMMETRY != AUTHORIZATION TO IGNORE SEMANTICS
```

> **Correção.** A primeira versão deste documento afirmava que a
> linhagem seria casada "nunca por `qualifier`", alegando que verificar
> a string faria a E4.5 herdar a assimetria de serialização de enums da
> E3. **A afirmação estava errada e foi removida.** A E4.4.1 congelou
> que `qualifier` carrega o token exatamente como persistido, lido sem
> normalização — e é justamente isso que torna a igualdade exata
> verificável aqui, sem importar enum algum da E3 e sem normalizar
> nada. O que a omissão produziu foi uma verificação incompleta: uma
> `LineageEdge(BRANCH)` certificava uma consolidação, e um
> `CausalHistoryEvent(COMPARED)` passava por `TRANSFORMED`.

A capitalização diferente entre os dois tokens é contrato persistido,
não descuido: `lineage_edges.relation_type` usa `values_callable` e
grava o `.value` (`"merge"`); `causal_history_events.event_type` não usa
e grava o NOME do membro (`"TRANSFORMED"`). A comparação é de igualdade
exata — nenhum `lower()`, `upper()` ou `casefold()` existe no código de
produção, e há teste que verifica essa ausência.

Recusados explicitamente: `"MERGE"`, `"Merge"`, `"branch"`,
`"derived_from"`, `"transformed"`, `"Transformed"`, `"COMPARED"`,
`"CREATED"`.

```text
BRANCH != MERGE            DIVERGENCE  != CONSOLIDATION
EVENT IDENTITY != EVENT TYPE
```

### Centralização (corretivo E4.5.1)

A semântica de coerência vive numa **única** função pura,
`verificar_coerencia_consolidacao`, em
`app/memory/schemas/consolidation.py`. Ela devolve todos os motivos de
incoerência e é usada pelos dois caminhos:

- `ConsolidationResult.__post_init__` → `ValueError` (tipo inválido
  continua `TypeError`);
- `ConsolidationManager` → `ConsolidationVerificationError`
  (`PIA-8032`, categoria `SYSTEM`).

**O construtor direto impõe exatamente a mesma coerência material do
caminho canônico.** Antes deste corretivo o value object verificava
três regras e o manager sete — duas implementações da mesma semântica,
que divergiram como se espera que divirjam:

```text
INVARIANT IN MANAGER ONLY != VALUE OBJECT INVARIANT
PUBLIC CONSTRUCTOR        != BYPASS PATH
```

Como o manager verifica **antes** de construir o resultado, nenhum
`ValueError` cru escapa do caminho canônico — provado por teste
dedicado, inclusive contra o banco real.

`TransformationKind` continua fora do assessment da E4.4 (que não o
expõe) e segue verificado apenas na integração, contra o writer oficial.

O assessment avalia **o alvo**, nunca as fontes: nenhuma fonte é
consultada, pontuada, ranqueada ou admitida por evidência prévia.
`NO_RECORDED_CONTINUITY_EVIDENCE` numa fonte é fato legítimo sobre
objeto novo.

---

## 5. Regra de CLID

A E4.5 **não decide** CLID — delega integralmente à E3.4.2:

```text
todas as fontes com o mesmo CLID não nulo  → target herda esse CLID
CLIDs diferentes / alguma sem CLID / todas sem → target.clid = None
```

```text
MIXED HISTORIES != SINGLE CONTINUITY
MIXED CLID      != AUTHORIZATION TO CREATE NEW SHARED CLID
```

Nenhuma chamada a `ClidManager.inherit()`, nenhum CLID gerado, nenhum
CLID preenchido ou alterado em fonte, nenhum vencedor escolhido. A E4.5
apenas confere que recibo e assessment contam a mesma história —
`None` dos dois lados é coerência, não falha.

---

## 6. Declaração obrigatória de perdas

```text
DECLARED_LOSS_ON_CONSOLIDATION = MANDATORY
```

Rejeitados: ausente, vazio, item em branco, tipo inválido, e `str` usada
como coleção (que viraria uma lista de caracteres). Nada é preenchido
automaticamente com `"none"`, `"unknown"` ou `"sem perdas"` — seria a
mesma afirmação falsa, escondida:

```text
MISSING LOSS DECLARATION != LOSSLESS EQUIVALENCE
```

`strip()` é usado **apenas como predicado** de branco. O texto
encaminhado e persistido é byte a byte o que o chamador declarou,
espaços de borda inclusive — provado em integração contra o registro no
banco.

`declared_preservations` pode ser vazio, mas segue as mesmas regras de
tipo e branco.

---

## 7. Fontes não são alteradas

Nem COID, CLID, `RevisionStatus`, `AccessibilityState`, `deleted_at`,
proveniência, história causal ou membership de domínio. Provado por
censo linha a linha antes/depois, inclusive sob rollback.

Fontes soft-deleted participam estruturalmente sem serem recuperadas e
sem que `deleted_at` mude:

```text
SOFT_DELETED != NEVER EXISTED
SOFT_DELETED != HISTORICAL_ERASURE
```

Isso é mecanismo, não autorização de acesso.

`DOMAIN INHERITANCE ON CONSOLIDATION = NONE` — nenhuma membership é
copiada.

---

## 8. Ausência de governança e de retrieval

A matriz G congela `E4.5 hard deps = {E3, E4.0, E4.4}`. O construtor
recebe exatamente `transformation_port` e `persistence_manager`; a
assinatura pública de `consolidate` não tem `context`,
`memory_context`, `governance`, `policy`, `resolution` nem `domain` —
verificado por inspeção da assinatura.

```text
PERMISSION TO CONSOLIDATE != CONSOLIDATION IMPLEMENTATION
GOVERNANCE DECISION       != OPERATION EXECUTION
```

Receber uma `GovernanceResolution` só para parecer governada seria pior
que não recebê-la: sugeriria uma verificação que não acontece.
`PlatformSafetyBoundary` também não é chamada — a E4.5 recebe COIDs e
declarações estruturais, nunca conteúdo livre ou `CapabilityDescriptor`.

`policy_ref` é referência declarada pelo chamador; sua presença não
constitui autorização. `actor_ref` é descritor, não autenticação.

Nada de síntese textual, provider, embedding, vector DB, similaridade,
Search, Retrieval, alteração de acessibilidade, retenção, aprendizado,
transcript ou artifact — provado por ausência estrutural sobre o código
executável.

```text
SYNTHESIS CONTENT GENERATION = OUTSIDE E4_5
E4.6 = NOT STARTED
```

---

## 9. Repetição e concorrência

```text
REPEATED CONSOLIDATION != SAME EVENT
```

Nenhuma deduplicação por conjunto de fontes, nenhuma constraint que a
impedisse. Duas consolidações concorrentes das mesmas fontes,
sincronizadas por barreira, produzem **dois alvos distintos**, sem
deadlock, sem mutação das fontes e sem reaproveitamento silencioso de
target.

---

## 10. Atomicidade e rollback

O manager não cria `Session` nem `UnitOfWork`, não commita, não faz
rollback, não captura erro para continuar e não executa compensação.
Todas as escritas pertencem à porta E3, dentro da transação do chamador.

Se a verificação falhar, `ConsolidationVerificationError` (`PIA-8032`)
sobe e o rollback do chamador desfaz tudo:

```text
AUTO_DESTRUCTIVE_REPAIR = FORBIDDEN
MISMATCH != AUTHORIZATION TO FABRICATE OR REPAIR HISTORY
```

Três provas de rollback contra PostgreSQL real — omissão de `commit()`,
falha de verificação e exceção em `assess()` — todas confirmando:

```text
ORPHAN_TARGET = 0          PARTIAL_LINEAGE = 0
PARTIAL_TRANSFORMATION = 0 PARTIAL_CAUSAL_HISTORY = 0
SOURCE_MUTATION = 0        SOURCE_CLID_MUTATION = 0
```

O caso de exceção em `assess()` exige `chamadas["n"] > 0`, para que a
injeção não possa virar prova vazia — disciplina herdada da E3.4.2.1.

### `PIA-8032`

Confirmado como próximo código **global** livre por varredura dos dois
catálogos (E3 vai até `PIA-8031`). É realmente levantado e tem testes;
não é reserva preventiva. Carrega **todos** os motivos de uma vez —
uma divergência raramente vem sozinha, e reportar só a primeira
obrigaria a auditoria a descobrir as demais uma execução por vez.

Categoria `SYSTEM`, não `VALIDATION`: chegar aqui não significa pedido
inválido (isso já foi recusado no preflight), e sim que escrita e
leitura do patrimônio discordam.

---

## 11. Discrepância registrada

`ErrorCategory` (`app/core/error_codes.py`) é vocabulário **fechado** e
não possui `INTERNAL`, que seria a categoria natural para uma
inconsistência interna. Usei `SYSTEM`, a existente que melhor descreve
o caso. Ampliar um enum de E1/E2 por conveniência da E4.5 estaria fora
do escopo deste módulo e acionaria Stop Condition — registro em vez de
corrigir em silêncio.

---

## 12. Limitações declaradas

- A E4.5 registra a **estrutura** de uma consolidação. O conteúdo de
  `S1` não é gerado aqui: geração de síntese e artifact storage
  continuam deferidos.
- `actor_ref`, quando informado, precisa referenciar um
  `ProvenanceRecord` existente, porque `causal_history_events.actor_ref`
  é FK real (achado da E3.4.2). A FK do banco continua sendo a
  autoridade final; nenhum código de erro novo foi criado para isso.
- A verificação prova que o patrimônio **corresponde ao recibo**, não
  que a consolidação seja semanticamente boa. `COUT INFORMS; DOES NOT
  DECIDE`.
- `runtime_checkable` verifica presença de membros, não assinaturas; a
  conformidade de tipos é decidida pelo mypy.

---

## 13. Testes — contagens coletadas

Obtidas de `pytest --collect-only`, nunca estimadas.

| Arquivo | Testes |
|---|---|
| `tests/unit/memory/test_consolidation.py` | **87** |
| `tests/integration/memory/test_consolidation_integration.py` | **25** |
| **Total E4.5** | **112** |

### Classificação honesta (§19)

A E4.5 não existia no patch 47, então **nenhum** teste "falha antes"
por corrigir comportamento existente. A classificação é:

- **NEW CONTRACT TESTS (87 unitários)** — invariantes do value object e
  disciplina do manager. Não existiam e não podiam existir antes.
- **INTEGRATION PROOF TESTS (19 dos 25)** — composição real, CLID,
  cardinalidade do escrito, causalidade, `actor_ref`, verificação pela
  E4.4, censo das fontes, rollback (3 cenários), concorrência,
  rastreabilidade.
- **REGRESSION GUARDS (6 dos 25)** — drift de schema, migration head,
  ausência de model/tabela nova, fronteira G17/MD6 e as três ordens de
  import em interpretadores limpos. Passariam nos dois lados e é
  correto que passem.

### Dois defeitos meus, corrigidos

**(a)** Testes de integração liam atributos de instâncias ORM **depois**
do fechamento da `UnitOfWork`, disparando `DetachedInstanceError`. A
leitura passou para dentro da sessão.

**(b)** Um teste montava assessments divergentes com
`dataclasses.replace`, que os invariantes da E4.4.1 corretamente
recusam (`clid` declarado sem evidência CLID). Cada divergência passou a
ser montada como um assessment **internamente válido** — que é o caso
interessante, porque um assessment obviamente quebrado nem chegaria à
E4.5.

E um ajuste: sete linhas ficaram descobertas, reveladas pela exigência
de 100% — seis fechadas com testes, e o corpo `...` do stub de
`Protocol` marcado com `# pragma: no cover`, que já consta do
`exclude_lines` do `coverage.ini` (não alterado).

---

## 14. Resultados

```text
FULL_SUITE = 1563 passed / 1 skipped / 0 failed   (baseline: 1451)
RAW_SUITE  = 1352 passed / 212 skipped / 0 failed

E3_REGRESSION_DELTA     = 0   (598/598)
E3_4_2_REGRESSION_DELTA = 0   (134/134)
E4_1_REGRESSION_DELTA   = 0   (40/40)
E4_2_REGRESSION_DELTA   = 0   (42/42)
E4_3_REGRESSION_DELTA   = 0   (108/108)
E4_4_REGRESSION_DELTA   = 0   (74/74)
E4_5                    = 112 passed

GLOBAL_COVERAGE = 98,91%   (baseline 98,85%)
APP_COGNITIVE_COVERAGE = 100%    APP_MEMORY_COVERAGE = 100%
RUFF = PASS   BLACK = PASS
MYPY_TOTAL_ERRORS = 7 (idênticos à baseline)   MYPY_NEW_ERRORS = 0
git diff --check = limpo
SCHEMA_ORM_DRIFT = 0
MIGRATION_HEAD = 4ca61776b982 (inalterada, single-head)
PostgreSQL 16.14 real
```

Trees preservados byte a byte:
`backend/app/cognitive = be407b46f679a009e0f7f7e9f01fb784f08dea54`,
`backend/alembic = f01a1f812eb11695b9daeb6b1707e6477e9330fa`.
`backend/app/memory` mudou apenas pelo escopo declarado.

### Escopo

Produção (5): `ports/__init__.py`, `ports/consolidation.py`,
`schemas/consolidation.py`, `services/consolidation_manager.py`,
mais `errors/codes.py` e `errors/exceptions.py` (só o `PIA-8032` e sua
exceção). Testes (2). Doc (1). Nenhum repository, nenhum model ORM,
nenhuma migração.

---

## 15. Stop Conditions

```text
STOP_CONDITIONS = NONE
```

Nenhuma das 27 do §21 ocorreu. Em particular: `app/cognitive` e Alembic
intactos; nenhuma tabela, coluna, índice ou entidade persistente;
nenhum enum ampliado; nenhum import de `app.cognitive` em produção da
E4; nenhuma reflexão ou registry para encontrar classes da E3; nenhum
SQL cru de escrita; nenhum modelo ou enum duplicado; nenhuma fonte
alterada; nenhum CLID preenchido ou escolhido; `DERIVATION` sempre,
`REVISION` nunca; nenhuma fonte marcada `SUPERSEDED`, apagada ou tornada
inacessível; nenhuma membership copiada; assessment nunca usado como
score ou critério de admissão; nenhuma evidência prévia exigida de
fonte; Governance/Context não são dependência dura; nenhuma síntese ou
provider; nenhum Search/Retrieval; E4.6 não iniciada; `coverage.ini` e
`pytest.ini` intocados; `PIA-8032` tem consumidor real; nenhum reparo
destrutivo; a porta compôs diretamente com o manager E3 real; PostgreSQL
real validado.

---

## 16. Gate

```text
E4_5_IMPLEMENTATION = COMPLETE
E4_5_FINAL_STATUS   = AWAITING_INDEPENDENT_AUDIT
PATCH_CHAIN = 48

E4_6_IMPLEMENTATION = NOT_STARTED
READY_FOR_E4_6      = FALSE
```

O implementador não declara `PASS FINAL`. E4.6 não é iniciada.

---

## 17. Corretivo E4.5.1 — Consolidation Verification Invariants

**Patch 49.** A auditoria independente devolveu `E4_5_AUDIT = FAIL` com
três defeitos, todos reproduzidos contra o patch 48 antes de qualquer
correção.

| Defeito | Reprodução contra o patch 48 |
|---|---|
| **A** — `BRANCH` aceita como `MERGE` | assessment com `qualifier="branch"` certificou a consolidação |
| **B** — evento não-`TRANSFORMED` aceito | `qualifier="COMPARED"` passou por `TRANSFORMED` |
| **C** — construtor público contorna a verificação | as 4 variantes (branch, COMPARED, transformação errada, pareamento trocado) foram aceitas pelo construtor direto |

### Causa raiz

Uma só. Eu tratei a assimetria de serialização de enums da E3 como
razão para **não** verificar o `qualifier`. A conclusão correta era a
oposta: a E4.4.1 congelou `qualifier` como token persistido lido sem
normalização, e é exatamente isso que torna a igualdade exata
verificável sem importar enum e sem normalizar. Evitei uma dependência
que não existia e paguei com uma verificação incompleta.

O defeito C decorre da mesma decisão: como a verificação material vivia
só no manager, o value object nunca a teve — e o docstring dele afirmava
"já escrito **e já verificado**", uma afirmação que a API pública
contradizia. Quinta ocorrência da mesma classe (E4.2.1, E4.3.2, E4.4.1,
E3.4.2.1).

### Contagens coletadas

| Arquivo | Patch 48 | Patch 49 | Δ |
|---|---|---|---|
| `tests/unit/memory/test_consolidation.py` | 87 | **130** | +43 |
| `tests/integration/memory/test_consolidation_integration.py` | 25 | **31** | +6 |
| **Total** | **112** | **161** | **+49** |

### Classificação — obtida por execução contra o patch 48

Os 49 testes novos foram efetivamente executados contra o código
anterior. O arquivo unitário não coleta no patch 48 (as constantes de
qualifier não existem), então a classificação foi feita numa cópia com
as constantes substituídas por literais — caso contrário não haveria
classificação empírica alguma, apenas afirmação.

```text
FALHAM NO 48, PASSAM NO 49 ............................ 28 unitários + 3 integração
PASSAM NOS DOIS LADOS (guardas de regressão) .......... 15 unitários + 1 integração
FALHAM NO 48 APENAS POR ImportError ................... 2 integração
```

Os **2 por `ImportError`** são
`test_ci451_real_writer_persists_merge_qualifier_on_every_edge` e
`..._transformed_qualifier_on_every_event`. Eles importam as constantes
novas, que não existem no 48 — a falha **não é comportamental**: o
writer já gravava `"merge"` e `"TRANSFORMED"` corretamente antes do
corretivo. Registro isso explicitamente porque contá-los como
provadores de defeito seria falso.

Os 15 unitários que passam nos dois lados verificam comportamento que já
existia (aceitação de assessment correto, tuplas defensivas, hash,
pareamento correto, `PIA-8032` para divergências que o manager **já**
pegava) e agora ficam travados contra regressão.

### Efeito colateral registrado

Um teste da E4.5 (`test_cs52`) asserava a frase `"difere da do recibo"`.
Com a função compartilhada, a mensagem passou a dizer `"declarada"` —
do ponto de vista de uma função usada também pelo construtor direto, os
campos são declarados, não "do recibo". A asserção passou a casar
`"transformação registrada"`, que é o conteúdo estável. Nenhum teste foi
removido ou enfraquecido.

### Resultados do corretivo

```text
FULL_SUITE = 1612 passed / 1 skipped / 0 failed   (candidata: 1563)
RAW_SUITE  = 1395 passed / 218 skipped / 0 failed

E3 = 598/598   E3.4.2/.1 = 134/134   E4.1 = 40/40
E4.2 = 42/42   E4.3 = 108/108        E4.4 = 74/74      (todos delta 0)
E4.5 + E4.5.1 = 161 passed

GLOBAL_COVERAGE = 98,91%   (não reduziu)
APP_COGNITIVE_COVERAGE = 100%    APP_MEMORY_COVERAGE = 100%
RUFF = PASS   BLACK = PASS   MYPY_NEW_ERRORS = 0
SCHEMA_ORM_DRIFT = 0   MIGRATION_HEAD = 4ca61776b982
```

Escopo do patch 49: `schemas/consolidation.py`,
`services/consolidation_manager.py`, os 2 arquivos de teste e este
documento. Nenhuma mudança em E3, E4.4, `ErrorCategory`, migração,
tabela, enum, `coverage.ini` ou `pytest.ini`.

```text
E4_5_1_IMPLEMENTATION = COMPLETE
E4_5_FINAL_STATUS     = AWAITING_INDEPENDENT_AUDIT
PATCH_CHAIN = 49
READY_FOR_E4_6 = FALSE
```

---

## 18. Corretivo E4.5.2 — Request–Receipt Fidelity

**Patch 50.** A auditoria devolveu dois defeitos, ambos reproduzidos
contra a cadeia 49 antes de qualquer correção.

| Defeito | Reprodução contra a cadeia 49 |
|---|---|
| **D** — fontes substituídas | porta recebeu `(A,B)`, devolveu `(C,D)`, assessment coerente com `(C,D)` — resultado aceito sem exceção |
| **E** — predecessores substituídos | `P1` pedido, `P2` devolvido — aceito; e `(P1,P2)` pedido com `(P2,P1)` devolvido também |

### Causa raiz

A verificação que eu construí cobre **uma** relação: `receipt ↔
assessment`. Ela prova que o patrimônio observado corresponde ao que o
recibo afirma, e prova bem. Mas nunca compara o recibo com o **pedido
validado** — então recibo e banco podem concordar perfeitamente entre si
enquanto ambos descrevem uma operação diferente da solicitada.

```text
RECEIPT ↔ ASSESSMENT COHERENCE
DOES NOT IMPLY
REQUEST ↔ RECEIPT FIDELITY
```

Não é a mesma classe do corretivo E4.5.1: lá a verificação de uma
fronteira existente estava incompleta; aqui uma fronteira inteira não
estava modelada.

### As duas fronteiras

```text
REQUEST
   ↓ fidelity check           → verificar_fidelidade_pedido_recibo
RECEIPT
   ↓ material coherence check → verificar_coerencia_consolidacao
PERSISTENCE ASSESSMENT
   ↓
CONSOLIDATION RESULT
```

```text
REQUEST–RECEIPT FIDELITY     = REQUIRED
RECEIPT–ASSESSMENT COHERENCE = REQUIRED
ONE DOES NOT SUBSTITUTE THE OTHER

REQUEST FIDELITY != PERSISTENCE COHERENCE
BOTH ARE REQUIRED
```

Não é duplicação: fidelidade preserva a **intenção operacional
recebida**; coerência prova o **patrimônio efetivamente observado**.

A regra de fidelidade vive no manager, não no value object:
`ConsolidationResult` não recebe o pedido original e não deve
fabricá-lo — um value object que inventasse a intenção do chamador
afirmaria algo que ninguém lhe disse.

A verificação de fidelidade ocorre **antes** de `PersistenceManager.assess()`.
Uma divergência já demonstrada não precisa consultar o alvo para valer,
e há teste provando que `assess()` não é chamado nesses casos — tanto
com dublê quanto contra o banco real.

`PIA-8032` passa a cobrir falha de pós-condição em **qualquer** das duas
fronteiras (`request ↔ receipt` e `receipt ↔ persistence assessment`).
Código, categoria `SYSTEM`, HTTP status e severidade permanecem
inalterados; nenhum código novo foi criado.

### Divergência registrada — ordem dos predecessores

O §6 do prompt deste corretivo pede que a E4.5 **não ordene** os
predecessores e compare preservando a ordem do chamador. **Isso é
inalcançável ponta a ponta**, e a razão está no writer oficial:
`MultiInputTransformationManager._preflight_predecessores_tipos`
(E3.4.2) faz `tuple(sorted(...))`. O recibo devolve a tupla ordenada,
qualquer que seja a ordem pedida.

Comparar contra a ordem bruta faria **toda** consolidação com
predecessores fora de ordem falhar com `PIA-8032` — recusar operação
legítima. Confirmado empiricamente: foi o primeiro resultado da
integração antes do alinhamento.

Adotei a canonicalização por UUID nos dois lados, idêntica à da E3. A
verificação continua discriminando exatamente onde importa:

| Cenário | Detectado |
|---|---|
| predecessor substituído | sim |
| predecessor removido | sim |
| predecessor acrescentado | sim |
| recibo fora da ordem canônica | sim |
| ordem bruta do chamador não preservada pela E3 | **não** — a E3 não oferece essa garantia |

Corrigir isso na E3 seria Stop Condition (§13.1). Registro em vez de
resolver por conta própria: se a preservação literal da ordem for
requisito, ela pertence a um corretivo da E3, não à E4.5.

### Escopo

`schemas/consolidation.py` (função pura nova),
`services/consolidation_manager.py` (chamada e canonicalização
alinhada), os 2 arquivos de teste e este documento. Nada em E3, E4.4,
`PIA-8032`, `ErrorCategory`, migração, tabela, enum, `coverage.ini` ou
`pytest.ini`.

### Testes

| Arquivo | Cadeia 49 | Cadeia 50 | Δ |
|---|---|---|---|
| `tests/unit/memory/test_consolidation.py` | 130 | **150** | +20 |
| `tests/integration/memory/test_consolidation_integration.py` | 31 | **37** | +6 |
| **Total** | **161** | **187** | **+26** |

Classificação **obtida por execução** contra a cadeia 49 (com a função
nova substituída por um stub, senão o módulo nem coleta):

```text
FALHAM NA 49, PASSAM NA 50 ............ 15 unitários + 2 integração = 17
PASSAM NOS DOIS LADOS (guardas) ....... 5 unitários + 4 integração = 9
```

Os 9 guardas verificam comportamento que já existia — canonicalização
das fontes, evento-raiz sem predecessores, aceitação do writer real sem
adulteração, coexistência das duas verificações — e agora ficam travados
contra regressão.

### Dois defeitos meus nos testes, corrigidos

**(a)** O tamper de fontes trocava 3 fontes por 2, e o recibo da E3 —
que é dataclass com invariantes próprios — recusava via
`dataclasses.replace`. A adulteração precisa produzir um recibo
**estruturalmente válido e apenas infiel**, que é o defeito sob teste.
Também criei as fontes-isca antes do censo: criadas depois, apareciam
como "alvo órfão" no rollback.

**(b)** Dois testes passavam **por sorte**: asseravam ordem de UUIDs
aleatórios que coincide com a canônica em metade das execuções. Detectado
rodando os arquivos 6 vezes seguidas, não uma. Mesma lição da E3.4.2.1 —
teste que passa por acaso é pior que teste ausente.

### Resultados

```text
FULL_SUITE = 1638 passed / 1 skipped / 0 failed   (candidata: 1612)
RAW_SUITE  = 1415 passed / 224 skipped / 0 failed

E3 = 598/598   E3.4.2/.1 = 134/134   E4.1 = 40/40
E4.2 = 42/42   E4.3 = 108/108        E4.4 = 74/74     (todos delta 0)
E4.5 + E4.5.1 + E4.5.2 = 187 passed

GLOBAL_COVERAGE = 98,91%   (não reduziu)
APP_COGNITIVE_COVERAGE = 100%    APP_MEMORY_COVERAGE = 100%
RUFF = PASS   BLACK = PASS   MYPY_NEW_ERRORS = 0 (7 pré-existentes)
SCHEMA_ORM_DRIFT = 0   MIGRATION_HEAD = 4ca61776b982
```

```text
E4_5_2_IMPLEMENTATION = COMPLETE
E4_5_FINAL_STATUS     = AWAITING_INDEPENDENT_AUDIT
PATCH_CHAIN = 50
READY_FOR_E4_6 = FALSE
```
