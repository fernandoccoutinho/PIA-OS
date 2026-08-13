# E3.3 / LIB-03 — CLID Manager + Lineage Foundation

## Objetivo

Estabelecer formalmente a continuidade entre `CognitiveObject`s
distintos: `ClidManager` (geração/validação/atribuição/herança de
CLID) e a fundação de `LineageEdge` (relação direcionada entre dois
objetos).

## CLID representation found

`clid: UUID | None` (E3.1), imutabilidade já implementada
(`@validates("clid")`, E3.1.1): `None → valor` permitido uma vez,
`valor → valor` idempotente, `valor → outro valor` e `valor → None`
rejeitados (`CognitiveObjectClidAlreadySetError`/`PIA-8002`). E3.3
reutiliza esse guard integralmente — nenhuma lógica de imutabilidade é
duplicada em `ClidManager`.

## CLID semantics

```text
COID = identidade permanente de um objeto (único, nunca compartilhado)
CLID = identidade de continuidade (pode ser compartilhado por
       objetos COID-distintos que pertencem à mesma linhagem)

COID_A != COID_B  pode coexistir com  CLID_A == CLID_B
COID identity != CLID continuity
```

Nenhuma inferência automática: mesmo conteúdo, mesmo prompt, mesmo
provider, mesmo usuário — nada disso implica mesmo CLID. Continuidade
só nasce de uma operação explícita (`assign`/`inherit`).

## LineageEdge contract

Contrato base: `E3_DOMAIN_MODEL_DRAFT.md`, "8. LineageEdge" — taxonomia
`LineageRelation` (6 valores: `PARENT`, `CHILD`, `BRANCH`, `MERGE`,
`DERIVED_FROM`, `TRANSFORMED_FROM`) usada sem alteração.

**Concretização** (documentada, não conflito): `from_ref`/`to_ref`
(`COID | distinction_id` no Draft) tornam-se `parent_coid`/`child_coid`
(`UUID`, FK para `cognitive_objects.id`) — `CognitiveDistinction` está
`DEFERRED` desde E3.1, então COID é o único referente real hoje.
`transformation_ref` não foi implementado (nenhuma FK para uma tabela
que não existe — `TransformationRecord` é E3.4).

**Armazenamento direcionado único** (decisão delegada a E3.3 pelo
próprio Draft: "decisão de E3.3 sobre se ambos [PARENT e CHILD] são
persistidos ou um é derivado em leitura"): uma linha por relação real,
`parent_coid`/`child_coid` já codificam a direção. Consequência: as
edges que `ClidManager.inherit()` cria usam `DERIVED_FROM` como
relação padrão — `PARENT`/`CHILD` permanecem no vocabulário do enum
para uso futuro (armazenamento simétrico, se algum módulo posterior
precisar), mas não são os valores que E3.3 produz.

```text
LineageEdge
  id: UUID (PK própria)
  parent_coid: UUID  (FK -> cognitive_objects.id, sem cascade)
  child_coid: UUID   (FK -> cognitive_objects.id, sem cascade)
  relation_type: LineageRelation
  created_at, updated_at  (herdado de BaseModel)

  CHECK(parent_coid != child_coid)
  UNIQUE(parent_coid, child_coid, relation_type)
```

Append-only: nenhum método de update/delete de edge existe em
`LineageRepository` — não há requisito documentado para isso.

## CYCLE_PROTECTION = SELF_ONLY

Justificativa: nenhum documento canônico (Domain Model, EDR,
Implementation Sequence) exige detecção de ciclo indireto (`A→B→C→A`)
nesta fase. `A→A` é rejeitado em duas camadas (domínio, antes de
qualquer escrita; `CHECK` constraint, defesa em profundidade). Ciclos
indiretos **não são bloqueados** — testado e documentado
explicitamente (`test_cy1_self_link_is_the_only_cycle_protection_enforced`),
não é uma lacuna descoberta por acidente. Candidato natural a
`LIB-10 Integrity Manager` (E3.10), que existe justamente para validar
consistência sobre o que já existe — implementar `FULL_DAG` aqui
exigiria travessia de grafo sem necessidade demonstrada (§41 do
módulo: "não fazer scan global... se implementar FULL_DAG, documentar
complexidade" — a ausência de exigência documental foi o critério
usado para não implementar).

## Arquivos

| Arquivo | Papel |
|---|---|
| `app/cognitive/models/enums.py` | +`LineageRelation` |
| `app/cognitive/models/lineage_edge.py` | `LineageEdge` (ORM) |
| `app/cognitive/repositories/lineage_repository.py` | `LineageRepository` |
| `app/cognitive/services/clid_manager.py` | `ClidManager`, `ImportedClidStatus`, `ImportedClidValidation` |
| `app/cognitive/errors/codes.py` | +`PIA-8005`..`PIA-8008` |
| `app/cognitive/errors/exceptions.py` | +`ClidInvalidError`, `LineageSelfLinkError`, `LineageDuplicateEdgeError`, `LineageEndpointNotFoundError` |
| `alembic/versions/4f56e1a4936c_*.py` | Migração `lineage_edges` |
| `tests/unit/cognitive/conftest.py` | +`LineageEdge` na fixture, `PRAGMA foreign_keys=ON` (necessário a partir de E3.3) |

## Error codes reused/created

| Código | Situação |
|---|---|
| `PIA-8002` (reutilizado) | Child com CLID incompatível durante `inherit()` — mesmo guard de mutação do modelo |
| `PIA-8005` (novo) | CLID com formato inválido |
| `PIA-8006` (novo) | Self-link (`parent_coid == child_coid`) |
| `PIA-8007` (novo) | Edge duplicada (mesma tripla) |
| `PIA-8008` (novo) | `parent_coid`/`child_coid` não corresponde a nenhum `CognitiveObject` (violação de FK traduzida) |

`PIA-8001`, `PIA-8003`, `PIA-8004` foram inspecionados e não se
aplicam a nenhum caso novo deste módulo.

## Detecção de violação de integridade (mesmo princípio de E3.2.1)

`LineageRepository._classify_lineage_integrity_violation()` usa sinal
estruturado do driver — nunca parsing de mensagem — validado
empiricamente contra os dois backends antes da implementação:

- **PostgreSQL** (psycopg 3): `orig.sqlstate` — `23505` (unique) →
  `LineageDuplicateEdgeError`; `23503` (foreign_key) →
  `LineageEndpointNotFoundError`.
- **SQLite** (stdlib, Python 3.11+): `orig.sqlite_errorname` —
  `SQLITE_CONSTRAINT_UNIQUE` → duplicata; `SQLITE_CONSTRAINT_FOREIGNKEY`
  → endpoint inexistente.

**Decisão deliberada de não-refatoração**: esta é uma implementação
própria em `lineage_repository.py`, não uma extração de
`object_repository._is_unique_or_pk_violation` (E3.2.1) para um
módulo compartilhado. A instrução de E3.3 foi explícita — "não
refatore E3.1/E3.2 sem necessidade demonstrada" — e o objetivo deste
módulo não exige tocar em `object_repository.py`, já auditado e
corrigido duas vezes. Custo aceito: ~15 linhas de duplicação.

**Limitação conhecida**: quando a violação é de FK, não é possível
determinar a partir do driver qual dos dois COIDs (`parent`/`child`)
especificamente não existe — `LineageEndpointNotFoundError` reporta
`child_coid` por melhor esforço. Refinamento (query de existência
antes do erro, se necessário) fica para quando um caso real exigir.

## Migration

`4f56e1a4936c_create_lineage_edges_table_e3_3_lib_03.py` — aditiva,
testada `upgrade → downgrade → upgrade` contra PostgreSQL 16 real, com
verificação de schema via `psql \d` entre os passos e confirmação de
que `cognitive_objects` permanece intacta durante todo o ciclo.
Nenhum bug de `values_callable` (diferente de E3.1) — já apliquei o
`values_callable` desde a primeira versão do modelo, evitando o mesmo
problema encontrado e corrigido em E3.1.

`alembic/env.py` **não precisou ser tocado** — já importa
`app.cognitive.models` como pacote inteiro (desde E3.1); atualizar
`app/cognitive/models/__init__.py` para também exportar `LineageEdge`
foi suficiente para o autogenerate enxergar o modelo novo.

## Repository status

`LineageRepository(BaseRepository[LineageEdge])` — `add_edge`,
`list_children`, `list_parents` (ambos com filtro opcional por
`relation_type`, ordenados deterministicamente por
`created_at ASC, id ASC` — mesma convenção de E3.1.2, sem repetir o
débito lá corrigido), `edge_exists`. Não substitui `BaseRepository`;
`ObjectRepository` continua responsável por `CognitiveObject`.

## Transaction/rollback result

`ClidManager.inherit()` não commita em nenhum passo interno —
`ObjectRepository.update()`/`LineageRepository.add_edge()` só fazem
`flush()`. Testado com `UnitOfWork` real: uma falha no meio da
operação (child com CLID incompatível) não deixa o parent com CLID
parcialmente atribuído após rollback (`INH5`/`INH6`, testados também
com SQLite e confirmados via cenário completo de `UnitOfWork`).

## Multi-IA readiness

```
COMPETITIVE_READY = TRUE
COMPLEMENTARY_READY = TRUE
SEQUENTIAL_READY = TRUE
```

Testado estruturalmente: `MIA1` (COIDs distintos coexistem), `MIA2`
(CLID compartilhado só por operação explícita — nunca automático),
`MIA3` (cadeia `A→B→C` compartilhando um CLID, sem sobrescrever
nenhum objeto anterior), `MIA4` (nenhum método público de
`ClidManager` aceita `provider`/`model`/`agent`, verificado por
introspecção), `MIA5` (nenhum objeto anterior é sobrescrito por
`inherit()`).

## API status

`DEFERRED` — nenhuma evidência de exigência de endpoint HTTP nesta
fase.

## Testes

61 testes novos (56 unitários + 5 de integração):

- **Model** (`test_lineage_edge.py`): criação, os 6 valores de
  `LineageRelation`, self-link rejeitado por `CHECK`, duplicata
  rejeitada por `UNIQUE`, relação diferente entre o mesmo par
  permitida, FK rejeita endpoint inexistente.
- **Repository** (`test_lineage_repository.py`): `LIN1`-`LIN10`,
  `CY1`, classificação de violação de integridade isolada (sinal
  estruturado, incluindo o ramo "causa não reconhecida → relança sem
  reinterpretar").
- **ClidManager** (`test_clid_manager.py`): `CL1`-`CL8`,
  `assert_assignable` puramente de leitura (correção durante o
  desenvolvimento — a primeira versão mutava a entidade para "testar",
  corrigido), `INH1`-`INH6`, `MIA1`-`MIA5`, import
  (`VALID`/`INVALID`/`INCOMPATIBLE`, sem auto-remap).
- **Integração contra PostgreSQL real** (`test_lineage_clid_integration.py`):
  round-trip completo de `inherit()` com CLID compartilhado, self-link,
  duplicate edge, FK violation, imutabilidade de CLID — **todos os 5
  testes executados e confirmados contra Postgres real**, não apenas
  SQLite.

Total: 100% de cobertura de linha em todo `app/cognitive/` (171 testes
unitários + 5 de integração antes desta correção final de cobertura;
todos os ramos de `_classify_lineage_integrity_violation` e
`ClidManager.validate()` cobertos explicitamente).

## Non-regression

`E1/E2`: intacto — nenhum arquivo protegido tocado. `E3.1
FINAL`/`E3.2 FINAL`: os 171 testes anteriores continuam passando sem
modificação de comportamento (o único arquivo pré-existente de E3
tocado foi `tests/unit/cognitive/conftest.py`, para adicionar
`LineageEdge` à fixture e habilitar `PRAGMA foreign_keys=ON` no
SQLite — sem isso, os testes de FK deste módulo não seriam realistas,
já que PostgreSQL impõe FK por padrão mas SQLite não). Suíte completa:
626 passed, 8 skipped (sem `.env` local — mesmo padrão gracioso de
sempre), 97,04%.

## Decisões

1. `parent_coid`/`child_coid` concretizam `from_ref`/`to_ref` do
   Domain Model Draft como COID puro (não `distinction_id`) —
   `CognitiveDistinction` está deferida.
2. Armazenamento direcionado único (não simétrico PARENT+CHILD) —
   decisão explicitamente delegada a E3.3 pelo Draft.
3. `inherit()` usa `DERIVED_FROM` como relação padrão — sensata para
   "child continua a partir do parent"; outros valores continuam
   disponíveis via parâmetro `relation_type`.
4. `assert_assignable()` reimplementa a condição de leitura em vez de
   tentar-e-reverter uma atribuição real — decisão corrigida durante o
   desenvolvimento após identificar que a primeira abordagem mutava a
   entidade como efeito colateral de uma checagem que deveria ser
   pura.
5. FK sem `ON DELETE CASCADE` — soft delete de `CognitiveObject` não
   remove a linha fisicamente, então a FK nunca é violada por soft
   delete; cascade automático não teria base documental (§32 do
   módulo).

## Limitações

- `LineageEndpointNotFoundError` não distingue, a partir do driver,
  se foi `parent_coid` ou `child_coid` que violou a FK — reporta
  `child_coid` por melhor esforço.
- Ciclos indiretos não são detectados (`CYCLE_PROTECTION = SELF_ONLY`,
  ver seção dedicada acima) — débito explícito, não descoberto por
  acidente.
- `_classify_lineage_integrity_violation` duplica ~15 linhas de
  `object_repository._is_unique_or_pk_violation` (E3.2.1) por decisão
  deliberada de não-refatoração.

## Itens deferidos

- `TransformationRecord`, Version Manager: `E3.4`.
- Metadata/Provenance/Accessibility completos: `E3.6`.
- Index/Search Manager: `E3.7`/`E3.8`.
- Detecção de ciclo indireto (`FULL_DAG`): candidato a `E3.10`
  (Integrity Manager).
- Synchronization Manager completo (import/export, remapeamento
  auditável de CLID/COID colidente): `E3.11`.
- Endpoints HTTP: nenhuma evidência de exigência nesta fase.
