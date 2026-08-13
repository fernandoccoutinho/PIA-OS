# E3.5.2 / LIB-05 — COUT Data Preservation / Safe Downgrade

Correção incremental de `E3_5_LIB05_RELATIONSHIP_ENGINE.md`/
`E3_5_1_LIB05_...` (documento não existe separadamente — E3.5.1 usou
uma seção dedicada dentro do documento principal). Não reimplementa
E3.5, não edita E3.5.1 retroativamente.

## Objetivo

Fechar o problema identificado na auditoria da migração `63d205dec996`
(E3.5.1): o lifecycle de `Relationship` permite legitimamente múltiplas
gerações históricas da mesma tripla `(source_coid, target_coid,
relationship_type)` — uma `retired`, uma `active`. O schema anterior a
essa migração exigia unicidade incondicional sobre todas as linhas;
depois desse estado ter sido produzido, um downgrade convencional não
conseguiria recriar o schema anterior sem perder distinções
históricas.

## COUT Data Preservation Rule

Formalizada em `EDR_COUT_PIA_E3.md` (ver seção dedicada lá) como
princípio arquitetural geral — não uma regra específica de
`Relationship`:

```text
HISTORICAL PRESERVATION > DOWNGRADE CONVENIENCE
SCHEMA REVERSIBILITY != HISTORICAL ERASURE
```

## Decisão sobre editar `63d205dec996`

`63d205dec996` já havia sido gerada e **entregue** ao usuário como
parte do patch `e3-5-1-lib05-active-uniqueness-symmetric-guarantee.patch`
na correção anterior. Pela mesma disciplina seguida em toda a cadeia
de correções desta entrega (E3.1.1, E3.1.2, E3.2.1, E3.3.1, E3.4.0,
E3.4.1, E3.4.1a, E3.5.1) — nunca editar um arquivo de migração já
entregue em um patch anterior, sempre criar um arquivo novo — decidi
**não editar `63d205dec996` retroativamente**.

## Solução: migração-guarda

Uma nova migração aditiva, `f11551e97026`, cujo `upgrade()` é
literalmente no-op (nenhuma alteração de schema — o schema já está
correto desde `63d205dec996`) e cujo `downgrade()` executa a checagem
de segurança:

```sql
SELECT source_coid, target_coid, relationship_type, COUNT(*) AS n
FROM relationships
GROUP BY source_coid, target_coid, relationship_type
HAVING COUNT(*) > 1
```

Se existir qualquer resultado: levanta `RelationshipDowngradeUnsafeError`
com mensagem clara (`DOWNGRADE_SEMANTICALLY_BLOCKED`) — **antes** de
qualquer alteração estrutural.

**Por que isso funciona sem tocar `63d205dec996`**: o Alembic processa
downgrades multi-passo em ordem reversa, uma migração por vez, cada
passo em sua própria transação. Como `f11551e97026` está posicionada
**depois** de `63d205dec996` na cadeia, um `alembic downgrade` a partir
da head atual executa primeiro o `downgrade()` de `f11551e97026` — se
ele abortar, a transação daquele passo é revertida integralmente e o
Alembic **nunca chega a processar** o `downgrade()` de `63d205dec996`.
Nenhuma edição do arquivo original foi necessária.

## Downgrade Semantics

`MIGRATION_REVERSIBILITY = CONDITIONALLY_REVERSIBLE`, classificação
que se aplica à cadeia `63d205dec996 → f11551e97026` como um todo:

- **CASO A** (estado compatível — nenhum histórico incompatível
  produzido): downgrade prossegue normalmente através de
  `f11551e97026` e `63d205dec996` até o schema anterior a E3.5.1.
- **CASO B** (múltiplas gerações da mesma tripla existem):
  `DOWNGRADE_SEMANTICALLY_BLOCKED` — abortado em `f11551e97026`, antes
  de alcançar `63d205dec996`.

## Proibições respeitadas

Nenhuma das operações proibidas pelo prompt corretivo foi implementada:
sem `DELETE` de registros retirados, sem escolha arbitrária de geração,
sem merge, sem sobrescrita de histórico, sem alteração de COID/
endpoints/`relationship_type`/`retired_at`, sem deduplicação
automática. A única ação do `downgrade()` de `f11551e97026`, no caso
incompatível, é **levantar uma exceção** — nenhuma escrita no banco
ocorre.

## Precondition Check

Implementado exatamente como especificado (§5 do prompt corretivo) —
`GROUP BY ... HAVING COUNT(*) > 1`, verificado antes de restaurar a
`UniqueConstraint` incondicional. Não depende do erro genérico que o
próprio `CREATE UNIQUE CONSTRAINT` produziria ao encontrar duplicatas
— a checagem é feita explicitamente, com mensagem clara identificando
a tripla e a quantidade de gerações envolvidas.

## Atomicidade da recusa

Testado (`D2`-`D5`) e confirmado empiricamente contra PostgreSQL real,
repetido 3 vezes para estabilidade: após `DOWNGRADE_SEMANTICALLY_BLOCKED`,
todos os registros de `Relationship` permanecem presentes, `retired_at`
permanece intacto na linha antiga, a relação `active` permanece
intacta, o índice único parcial e o `CheckConstraint` de simetria
continuam existindo (confirmado indiretamente: uma tentativa de criar
uma duplicata ativa após o bloqueio continua sendo rejeitada — prova
de que o schema E3.5.1 está genuinamente íntegro, não apenas
aparentemente), nenhuma migração parcial fica aplicada, e o Alembic
permanece exatamente na revisão `f11551e97026` (nunca retrocede).

## Testes

2 testes de integração novos (`test_relationship_downgrade_safety.py`),
usando `app.database.migrations` (wrapper programático já existente
sobre o Alembic — não uma ferramenta nova) para orquestrar
`upgrade`/`downgrade` reais:

- `test_d1_compatible_downgrade_succeeds` — `D1`: nenhum histórico
  incompatível, downgrade funciona normalmente, ciclo completo até a
  migração anterior e de volta à head confirmado.
- `test_d2_d3_d4_d5_incompatible_historical_downgrade_is_blocked_without_data_loss`
  — `D2` (bloqueio explícito, mensagem contém
  `DOWNGRADE_SEMANTICALLY_BLOCKED`), `D3` (R0/R1 continuam presentes
  com os estados corretos), `D4` (revisão Alembic não retrocede;
  schema íntegro, confirmado via rejeição de duplicata ativa), `D5`
  (nenhum estado parcial, confirmado indiretamente pela integridade de
  D3/D4).

Executados contra PostgreSQL real 3 vezes para confirmar estabilidade
— nenhuma flakiness observada.

## Correção documental da contagem de testes

**Inspeção real do repositório** (não aritmética anterior — a
contagem documentada em `E3_5_LIB05_RELATIONSHIP_ENGINE.md` estava
incorreta): via `grep -c "^def test_"` em cada arquivo e confirmado por
`pytest --collect-only`:

```text
test_relationship.py                     7
test_relationship_repository.py         36  (documentado incorretamente como 46)
test_relationship_active_uniqueness.py   7
test_relationship_engine.py             10
test_relationship_integration.py         5  (4 de E3.5 + 1 de E3.5.1, U2)
                                        ----
                                         65 testes novos (E3.5 + E3.5.1 combinados)
```

`E3_5_LIB05_RELATIONSHIP_ENGINE.md` corrigido de "82 testes novos ao
todo" para o número real, **65** — não os 83 sugeridos mecanicamente
pelo prompt corretivo (que partia da contagem original, também
incorreta, de 75). O prompt corretivo (§10) foi explícito: "não
corrigir números mecanicamente se o repositório mostrar contagem
diferente" — a contagem real prevalece.

## Non-Regression

777 passed, 21 skipped (sem `.env` local — mesmo padrão gracioso de
sempre; 2 a mais que antes, os novos testes de integração), 97,54%
(mantido). Revalidado explicitamente: active duplicate rejection,
retire→redeclare, retired history recovery, canonicalização de
`RELATED_TO`, garantia de simetria em nível de banco, concorrência,
`Relationship` vs `Lineage`, invariantes de E3.1-E3.4, suíte completa.
Nenhuma mudança de comportamento funcional do `RelationshipEngine` —
confirmado por diff (nenhum arquivo de `app/cognitive/models/relationship.py`,
`relationship_repository.py` ou `relationship_engine.py` foi tocado
nesta correção).

## Files Modified

```
alembic/versions/f11551e97026_guard_relationship_downgrade_safety_.py   [novo]
tests/integration/cognitive/test_relationship_downgrade_safety.py       [novo]
docs/entregas/entrega-3/EDR_COUT_PIA_E3.md                              [seção nova]
```

Nenhum arquivo de E3.1-E3.5.1 foi modificado. Nenhum arquivo protegido
tocado.
