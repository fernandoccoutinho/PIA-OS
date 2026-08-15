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
| 8 | exatamente um `TRANSFORMATION_OUTPUT`, com a referência do recibo |
| 9 | conjunto de `CAUSAL_EVENT` igual aos `causal_event_ids` |
| 10 | CLID coerente entre assessment e recibo |

A verificação nº 7 não é redundante com a 5 e a 6: os dois conjuntos
podem bater com o **pareamento trocado**, e um teste dedicado
(`cs39c`) monta exatamente esse caso.

**A linhagem é casada por `reference` e `related_coid`, nunca por
`qualifier`.** A E3 persiste enums com duas convenções —
`lineage_edges.relation_type` grava o `.value` e
`causal_history_events.event_type` grava o NOME, achado registrado na
E4.4 — e casar por essa string faria a E4.5 herdar uma assimetria que
não é dela.

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
