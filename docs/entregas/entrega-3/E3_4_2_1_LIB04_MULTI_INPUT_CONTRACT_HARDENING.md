# E3_4_2_1_LIB04_MULTI_INPUT_CONTRACT_HARDENING

**Módulo:** E3.4.2.1 — Multi-Input Transformation Contract Hardening
**Natureza:** corretivo estritamente limitado sobre a E3.4.2 (entrega
Claude 0). Cinco lacunas da auditoria independente, nada além.
**Baseline candidata:** `PATCH_CHAIN = 46` · HEAD `0e4d8c6e9f17…` ✓ ·
PARENT `3f500701a0cd…` ✓ · TREE `4faf88d62336…` ✓ ·
PATCH_ID `e40fcf27fd67…` ✓ · bundle SHA-256 `618de183…9360` ✓ ·
patch SHA-256 `9a6c3f00…f169` ✓ · migration head `4ca61776b982` ✓ ·
`git status` limpo ✓
**Patch:** `e3-4-2-1-multi-input-contract-hardening.patch` (47º)

Reprodução da cadeia confirmada: o patch 46 aplica sobre a baseline 45
(`3f500701`) e reproduz `4faf88d6…` exatamente. Suíte da candidata
reexecutada antes de qualquer alteração: **1439 passed / 1 skipped /
0 failed**.

---

## 1. Duas divergências registradas, não corrigidas em silêncio

**(a) O ZIP não foi anexado.** Usei o bundle e o patch da E3.4.2, cujos
SHA-256 conferem exatamente com os declarados no §2 do prompt — mesma
árvore por identidade criptográfica, não por suposição.

**(b) Caminhos de teste.** O §12 lista
`tests/unit/cognitive/test_multi_input_transformation.py`; na árvore
real são `tests/unit/cognitive/schemas/…` e
`tests/unit/cognitive/services/…`. O próprio §12 diz "sujeito à
inspeção real", então os caminhos reais prevalecem — mover arquivos
ampliaria o patch sem necessidade.

---

## 2. Defeitos reproduzidos **antes** de corrigir

| # | Defeito | Reprodução contra o patch 46 |
|---|---|---|
| 1 | `policy_ref` sem limite de comprimento | `_preflight_opcionais(None, "x"*256, None)` passou, com a coluna em `String(255)` |
| 2 | recibo construível fora da ordem canônica | `MultiInputTransformationReceipt(source_coids=(maior, menor))` aceito, `source_coids == (maior, menor)` |

---

## 3. Correção 1 — limite de `policy_ref`

```text
policy_ref informado:  1 <= len(policy_ref) <= 255
```

`_POLICY_REF_MAX_LENGTH = 255`, validado no preflight ao lado do limite
já existente de `operation_type`. Sem ele, o desfecho de um valor longo
demais dependeria do banco ou do driver — truncar em silêncio, recusar,
ou variar por dialeto — e a exigência de validação integral antes da
primeira escrita ficaria furada exatamente no campo mais fácil de passar
despercebido.

Continuam inválidos: string vazia, string só de espaços, tipo diferente
de `str`.

**Nada é normalizado.** O `.strip()` é apenas predicado para detectar
branco; o valor persistido é byte a byte o que o chamador forneceu,
espaços de borda inclusive — provado por teste dedicado.

```text
DECLARED VALUE != NORMALIZED VALUE
```

Erro: `ValueError`, taxonomia existente. **Nenhum error code novo** — o
§5 do prompt anterior proíbe reservar código sem consumidor, e um
`PIA-8032` aqui seria código morto do tipo que a exigência de 100% já
revelou cinco vezes neste projeto. Próximo livre segue `PIA-8032`.

---

## 4. Correção 2 — ordem canônica do recibo

```text
CANONICAL INPUT     → ACCEPT
NON-CANONICAL INPUT → ERROR
```

O manager já ordenava antes de construir, mas o construtor público
aceitava qualquer ordem — o value object podia existir em estado não
canônico.

**A recusa não reordena, e isso é o ponto.** `lineage_edge_ids` mantém
correspondência **posicional** com `source_coids`. Reordenar apenas os
COIDs separaria cada fonte da sua respectiva edge e fabricaria um
pareamento que nunca existiu — silenciosamente. Recusar é a única
correção que não inventa dado.

O manager continua canonicalizando; todos os caminhos que ele produz
permanecem válidos, verificado com três ordens de entrada distintas,
inclusive a inversa.

### 4.1 Efeito colateral legítimo nos testes existentes

O invariante novo quebrou sete testes da E3.4.2 — porque o helper
`_ids()` gera UUIDs em **ordem aleatória**, e metade das execuções
passava por acaso. Isso não era cobertura, era sorte.

Acrescentei `_fontes(n)`, que devolve fontes em ordem canônica, e o usei
onde a ordem não é o objeto do teste. Onde a ordem não canônica **é** o
objeto, ela é construída explicitamente. O arquivo foi rodado **oito
vezes seguidas** para confirmar que a intermitência acabou — um teste
que passa por sorte é pior que um teste ausente, porque parece
cobertura.

---

## 5. Correção 3 — quarta injeção de falha

`ClidManager.assign` entra como quarto caso do teste parametrizado de
rollback, com diagnósticos independentes preservados.

O cenário usa `_criar_fontes(3, clid=clid)` — fontes que **compartilham
CLID não nulo**. Isso é obrigatório, não decorativo: com CLIDs
divergentes o alvo nasceria com `clid=None` e `assign()` nunca seria
chamado, tornando a injeção uma prova vazia.

Para que isso não dependa de leitura atenta, o teste passou a exigir
explicitamente que a injeção tenha sido alcançada:

```python
assert chamadas["n"] > 0, f"a etapa '{etapa}' nunca foi alcançada — prova vazia"
```

Essa asserção protege os quatro casos, não só o novo.

Comprovado após rollback, contra PostgreSQL real:

```text
EXCEPTION_PROPAGATED   = TRUE
ORPHAN_TARGET          = 0
PARTIAL_LINEAGE        = 0
PARTIAL_TRANSFORMATION = 0
PARTIAL_CAUSAL_HISTORY = 0   (eventos e histórias, contados separadamente)
SOURCE_MUTATION        = 0   (censo linha a linha)
SOURCE_CLID_MUTATION   = 0   (asserção própria, além do censo)
INTERNAL_COMMIT        = 0   (o manager não commita; o rollback é do chamador)
```

`SOURCE_CLID_MUTATION` ganhou asserção própria em vez de ficar diluída
no censo, para que o diagnóstico não dependa de comparar uma tupla
inteira.

---

## 6. Correção 4 — prova PostgreSQL de `actor_ref`

A propagação estava correta no código, mas sem prova contra o estado
**persistido**. Agora:

1. `ProvenanceRecord` real criado e commitado;
2. seu id usado como `actor_ref`;
3. transformação multi-input executada;
4. estado consultado **direto no banco** por SQL de leitura, não pelo
   objeto que o manager devolveu;
5. igualdade tripla comprovada:

```text
TransformationRecord.actor_ref == CausalHistoryEvent.actor_ref == requested_actor_ref
```

A FK de `causal_history_events.actor_ref` para `provenance_records.id`
continua sendo a autoridade final. Nenhum ator fictício foi criado,
`actor_ref` não foi removido para contornar a restrição, o schema não
mudou e nenhuma migração foi criada.

Um segundo teste cobre o outro lado: `actor_ref` ausente permanece
`NULL` nos dois registros.

```text
MISSING PROVENANCE != AUTHORIZATION TO INVENT PROVENANCE
PROVENANCE         != CAUSAL HISTORY
```

---

## 7. Correção 5 — contagens

A E3.4.2 declarou 69 testes de manager e total 121. A coleta real era
**70** e **122** — o número foi contado à mão em vez de coletado. O
auditor está certo, e o erro é meu.

**Contagem real, obtida de `pytest --collect-only`:**

| Arquivo | Antes (46) | Depois (47) | Δ |
|---|---|---|---|
| `tests/unit/cognitive/schemas/test_multi_input_transformation.py` | 32 | **36** | +4 |
| `tests/unit/cognitive/services/test_multi_input_transformation_manager.py` | 70 | **75** | +5 |
| `tests/integration/cognitive/test_multi_input_transformation_integration.py` | 20 | **23** | +3 |
| **Total** | **122** | **134** | **+12** |

Unitários: 102 → 111. Integração: 20 → 23 (o §9 exigia ao menos 22).

Os +3 de integração são: o quarto caso parametrizado (`clid`) e os dois
testes de `actor_ref`.

### 7.1 Classificação — obtida por execução, não por afirmação

Os doze testes novos foram efetivamente **executados contra o patch
46**, com o código de produção antigo.

**DEFECT-PROVING (5) — falham no 46, passam no 47:**

```text
test_e3421_receipt_rejects_non_canonical_source_order
test_e3421_receipt_does_not_silently_reorder_sources
test_e3421_receipt_rejects_non_canonical_order_with_three_sources
test_e3421_policy_ref_with_256_characters_is_rejected
test_e3421_oversized_policy_ref_writes_nothing
```

**REGRESSION / TRANSACTION PROOF (7) — passam nos dois lados:**

```text
test_e3421_receipt_accepts_canonical_source_order
test_e3421_policy_ref_with_255_characters_is_accepted
test_e3421_policy_ref_is_persisted_exactly_as_given
test_e3421_receipt_from_the_manager_is_always_canonical
test_e3421_actor_ref_is_propagated_to_both_persisted_records
test_e3421_absent_actor_ref_stays_absent_in_both_persisted_records
rollback_after_injected_failure[clid-ClidManager.assign]
```

E isso é **correto**, não uma falha do corretivo: os quatro primeiros
comprovam comportamento que já existia e agora fica travado; os dois de
`actor_ref` comprovam propagação que já funcionava e faltava provar; e a
quarta injeção comprova uma propriedade transacional que já valia e
ainda não estava coberta. Nenhum deles é apresentado como provador de
defeito, conforme o §13 exige.

---

## 8. Resultados

```text
FULL_SUITE = 1451 passed / 1 skipped / 0 failed     (candidata: 1439)
RAW_SUITE  = 1265 passed / 187 skipped / 0 failed

E3_REGRESSION_DELTA   = 0   (598/598)
E4_1_REGRESSION_DELTA = 0   (40/40)
E4_2_REGRESSION_DELTA = 0   (42/42)
E4_3_REGRESSION_DELTA = 0   (108/108)
E4_4_REGRESSION_DELTA = 0   (74/74)
E3_4_2 + E3_4_2_1     = 134 passed

GLOBAL_COVERAGE = 98,85%
APP_COGNITIVE_COVERAGE = 100%    APP_MEMORY_COVERAGE = 100%
RUFF = PASS   BLACK = PASS
MYPY_TOTAL_ERRORS = 7 (idênticos à baseline)   MYPY_NEW_ERRORS = 0
git diff --check = limpo
SCHEMA_ORM_DRIFT = 0
MIGRATION_HEAD = 4ca61776b982 (inalterada, single-head)
NEW MIGRATION / TABLE / COLUMN / INDEX / PERSISTENT ENTITY = NO
ENUM PERSISTIDO ALTERADO = NO
PostgreSQL 16.14 real
```

Trees preservados byte a byte: `backend/app/memory = c5cec4ae…`,
`backend/alembic = f01a1f81…`, `docs/entregas/entrega-4 = 27fd09fa…`.

---

## 9. Escopo

Produção (2): `schemas/multi_input_transformation.py`,
`services/multi_input_transformation_manager.py`.
Testes (3): os três arquivos da E3.4.2.
Docs (2): `E3_4_2_LIB04_…` (contagens) e este.

Nada em `app/memory`, `alembic/`, `docs/entregas/entrega-4`,
`coverage.ini` ou `pytest.ini`. Nenhum arquivo da E4.1/E4.2/E4.3/E4.4.
A documentação permanece na Entrega 3, como o §12 determina.

---

## 10. Stop Conditions

```text
STOP_CONDITIONS = NONE
```

Nenhuma das 15 do §15 ocorreu. Em particular: nenhuma migração, tabela
ou coluna; nenhum enum persistido alterado; nenhum contrato congelado da
E3 modificado; nenhuma fonte mutada; semântica `MERGE` intacta; um único
`TransformationRecord`; nenhum predecessor implícito; nenhuma perda,
proveniência ou história fabricada; `app/memory` intocado; nenhum error
code sem consumidor; nenhuma dívida histórica corrigida fora do escopo;
E4.5 não iniciada; PostgreSQL real validado.

---

## 11. Gate

```text
E3_4_2_1_IMPLEMENTATION = COMPLETE
E3_4_2_FINAL_STATUS     = AWAITING_INDEPENDENT_AUDIT
PATCH_CHAIN_CANDIDATE   = 47

E4_5_IMPLEMENTATION = NOT_STARTED
E4_5_STATUS         = BLOCKED_PENDING_E3_4_2_1_AUDIT
READY_FOR_E4_5      = FALSE
READY_FOR_E4_6      = FALSE
```

A cadeia canônica pública permanece congelada em **45** até a auditoria
independente aceitar conjuntamente a E3.4.2 e a E3.4.2.1.
