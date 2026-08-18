# E3.4 / LIB-04 — Version Manager + TransformationRecord

## Objetivo

Implementar o mecanismo de versionamento cognitivo: `VersionManager`
cria um novo `CognitiveObject` a partir de um existente por
transformação explícita, preservando identidade individual (COID),
continuidade causal (CLID), lineage e um histórico append-only
(`TransformationRecord`) — distinguindo formalmente **revisão
controlada** de **derivação livre** (correção E3.4.0).

## Workspace vs Controlled Asset

```text
WORKSPACE                              CONTROLLED ASSET
material transitório de trabalho:      conhecimento explicitamente
- chat, rascunhos, tentativas,         consolidado/promovido:
  respostas intermediárias, críticas,  - procedimento aprovado,
  alternativas, outputs de agentes       relatório consolidado,
  ainda não consolidados                 decisão técnica, especificação
```

**Chat/workspace não é automaticamente um controlled asset.**
`VersionManager` não promove nada por conta própria — chamar
`derive()`/`revise()` é sempre uma decisão explícita do chamador.
Criar um `CognitiveObject` simples (`ObjectRepository.add()`) nunca,
por si só, o torna parte de uma cadeia de revisão controlada:
`revision_status` nasce `None` e só um `revise()` explícito o move
(`W1`-`W2`, testados). Nenhum SDK de IA é necessário neste módulo, e
nenhuma conversa/dado de provider é persistido por ele (`W3`-`W4`,
testados por inspeção de colunas e de código-fonte).

`PROMOTION_POLICY_STATUS = DEFERRED` — a política completa de
promoção Workspace→Asset (quem decide, com que aprovação, sob qual
policy/arbiter) pertence a uma fase posterior (§18 do prompt
corretivo E3.4.0). Este módulo só fornece o mecanismo (`revise()`),
não decide quando ele deve ser usado.

## Revision vs Derivation

```text
REVISION                                DERIVATION
nova revisão controlada do MESMO        novo objeto derivado de outro,
patrimônio lógico:                      sem suceder o source:
  Asset X Rev.1 -> Asset X Rev.2        resumo, tradução, crítica,
  target vira CURRENT                   análise, adaptação, síntese
  source (se CURRENT) vira SUPERSEDED   source continua CURRENT/válido
```

As duas nunca se confundem automaticamente — a classificação vem
sempre de qual método o chamador invoca: `VersionManager.derive()`
(`DERIVATION`) ou `VersionManager.revise()` (`REVISION`). Nenhuma
heurística infere uma a partir da outra (§20 do prompt corretivo:
"COUT preserva história e relações; não decide sozinho qual conteúdo
deve substituir outro").

`DERIVATION` pode gerar branches naturalmente (`A` derivando `B` e
`C` simultaneamente, `D7`) — não exige `CURRENT`/`SUPERSEDED` entre
elas. `REVISION` é uma cadeia: `A Rev.1 -> B Rev.2 -> C Rev.3`, onde só
uma é vigente por vez.

## Current vs Superseded

`RevisionStatus` (`CURRENT` | `SUPERSEDED`) — os dois únicos estados
implementados (§6 do prompt corretivo: `ARCHIVED`/`DELETED`/
`EXPIRED`/`RETIRED`/`OBSOLETE` não são implementados nesta fase).

**Local do campo — decisão documentada, não por conveniência** (§8 do
prompt corretivo): `revision_status: RevisionStatus | None`, campo
**nulo em `CognitiveObject`**, não uma entidade nova
("Revision"/"ControlledAsset"). Critérios considerados:

- **Não polui `CognitiveObject`**: mesmo padrão já aceito para `clid`
  (dimensão opcional — a maioria dos objetos, todo `DERIVATION`/
  workspace, nunca toca este campo, permanece `None`).
- **Não antecipa Metadata Manager (E3.6)**: nenhuma entidade de
  metadado genérico foi inventada para isso.
- **Consulta eficiente**: permite `WHERE clid = X AND revision_status
  = 'current'` diretamente, sem join.
- Uma entidade "Revision"/"ControlledAsset" separada seria arquitetura
  nova não demandada pelo Domain Model — rejeitada por esse motivo.

**Não é `AccessibilityState`** (§7 do prompt corretivo) — os dois
campos são independentes; testado explicitamente
(`test_revision_status_independent_of_accessibility`): um objeto pode
ter `revision_status = SUPERSEDED` e `accessibility = ACTIVE`
simultaneamente — uma revisão antiga pode continuar plenamente
acessível para auditoria.

**SUPERSEDED != DELETED** (§17 do prompt corretivo): uma revisão
superseded continua identificável, auditável, rastreável, ligada por
lineage e por `TransformationRecord` — ela apenas deixa de ser a
representação vigente do asset. `R5` testa exatamente isso:
`source` continua recuperável por COID após `revise()`.

### Transições permitidas

```text
None -> CURRENT           permitido (primeira promoção, via revise())
None -> SUPERSEDED         permitido (entrada implícita - ver Open Decisions)
CURRENT -> SUPERSEDED      permitido (supersessão normal)
valor -> mesmo valor       permitido (idempotente)

SUPERSEDED -> CURRENT      REJEITADO (PIA-8011) - não é possível "reativar"
SUPERSEDED -> None         REJEITADO (PIA-8011)
CURRENT -> None            REJEITADO (PIA-8011)
```

Aplicado por `@validates("revision_status")` em `CognitiveObject` —
mesma técnica já usada para `clid` (E3.1.1) e `id` (E3.1). Testado
exaustivamente em `test_revision_status.py`.

## Controlled Revision Semantics (`revise()`)

`VersionManager.revise(source, *, operation_type, ...)`:

1. `ObjectRepository.refresh_for_update(source)` — bloqueia e
   recarrega `source` (reaproveita a proteção de E3.3.1).
2. Se `source.revision_status == SUPERSEDED` pós-lock: rejeita
   (`RevisionStatusInvalidTransitionError`, `PIA-8011`) — não é
   possível criar a "próxima revisão" a partir de uma já superada
   (evita uma segunda linha de revisão para a mesma continuidade).
3. `target` é criado e persistido — COID novo.
4. `ClidManager.inherit(source, target, relation_type=...)` — CLID +
   `LineageEdge`, reaproveitado integralmente.
5. `target.revision_status = CURRENT`; `source.revision_status =
   SUPERSEDED`.
6. `TransformationRecord` criado (`transformation_kind=REVISION`).

Nenhum passo commita — commit permanece do chamador via `UnitOfWork`.

**Invariante formal** (§12 do prompt corretivo): para uma linha de
revisão controlada, `COUNT(CURRENT) <= 1`. Garantido estruturalmente
pelo par de transições atômicas do passo 5 (nunca um sem o outro) e
testado (`R9`): depois de uma cadeia `Rev.0 -> Rev.1 -> Rev.2`, existe
exatamente 1 `CognitiveObject` com `revision_status = CURRENT` no
sistema todo.

**Número de revisão explícito**: `REVISION_NUMBER_STATUS = DEFERRED`
— o Domain Model atual não exige um contador (`Rev.0`, `Rev.1`, ...);
lineage + `TransformationRecord` + `CURRENT`/`SUPERSEDED` já
representam a cadeia de forma suficiente e consultável (via
`LineageRepository.list_parents`/`list_children`). Nenhum contador
sequencial foi introduzido — evitaria o mesmo problema de concorrência
já resolvido para CLID/revision_status, sem necessidade demonstrada.

## Derivation Semantics (`derive()`)

Inalterado em relação à implementação original de E3.4 (reaproveitado
por inteiro) — ver seção "COID/CLID/Lineage result" abaixo. Única
adição: `TransformationRecord` criado por `derive()` agora tem
`transformation_kind = DERIVATION` explicitamente.
`source.revision_status` nunca é tocado por `derive()` — testado
mesmo quando `source` já é `CURRENT` (`D3`,
`test_d3_derive_does_not_supersede_a_current_source`): permanece
`CURRENT` depois da derivação.

## Version semantics (comum às duas operações)

```text
A --transformação--> B

COID_A != COID_B                    (sempre)
CLID_A == CLID_B                    (sempre - revise() e derive() usam
                                      inherit(), que garante isso)

A permanece preservado - B é um novo CognitiveObject.
A.id = B.id é proibido.
```

Não há caminho no código que permita `A.id = B.id`: o COID de `target`
vem exclusivamente de `UUIDMixin.default=uuid.uuid4`, nunca copiado de
`A`.

## TransformationRecord contract

Contrato base: `E3_DOMAIN_MODEL_DRAFT.md`, seção "6. TransformationRecord".

```text
TransformationRecord
  transformation_id: UUID
  operation_type: str
  transformation_kind: REVISION | DERIVATION      # novo - correção E3.4.0
  input_refs: list[COID | distinction_id]
  output_refs: list[COID | distinction_id]
  actor_ref: ProvenanceRecord ref
  policy_ref: str?
  declared_preservations: list[str]
  declared_losses: list[str]
  timestamp: datetime
```

`transformation_kind` é a única adição estrutural desta correção ao
contrato — obrigatório (toda transformação criada por `VersionManager`
sabe explicitamente qual é), preserva `operation_type` livre/aberto
sem transformá-lo em enum rígido (§10 do prompt corretivo: "preserve
isso se possível... não invente taxonomia extensa para operation_type").

**Concretizações preexistentes** (E3.4 original, inalteradas):
`transformation_id`=`id`, `timestamp`=`created_at`, `actor_ref`
opcional (nulo — `ProvenanceRecord` é `E3.6`), `input_refs`/
`output_refs` como `JSON` (lista polimórfica, sem FK).

## COID / CLID / Lineage result

Idêntico à implementação original — reaproveitado por `revise()`
também, sem duplicação:

- **COID**: `target` sempre `ObjectRepository.add(CognitiveObject())`
  — COID novo, nunca copiado de `source`. `VersionManager` não gera
  mecanismo paralelo de COID.
- **CLID**: ambas as operações chamam `ClidManager.inherit()` — CLID
  sempre propagado/preservado, nunca duplicado por lógica própria.
- **Lineage**: ambas criam a `LineageEdge` via `inherit()`, com
  `relation_type` default `LineageRelation.TRANSFORMED_FROM` (mesmo
  valor para `derive()` e `revise()` — a distinção REVISION/DERIVATION
  vive em `TransformationRecord.transformation_kind`, não na
  taxonomia de lineage, que **não foi alterada**).

**Correlação `LineageEdge` <-> `TransformationRecord`**: continua por
COID compartilhado, não por FK direta — `lineage_edges` não recebeu
coluna `transformation_ref` (evitaria Stop Condition sobre tabela já
congelada de E3.3).

## Atomicity result

`derive()` — ordem inalterada (ver versão anterior deste documento).

`revise()` — ordem atômica (nenhum passo commita):

```text
source (bloqueado via refresh_for_update)
   |
[rejeita se já SUPERSEDED]
   |
target criado + persistido
   |
CLID resolvido + LineageEdge criada (inherit)
   |
target.revision_status = CURRENT; source.revision_status = SUPERSEDED
   |
TransformationRecord criado (transformation_kind=REVISION)
```

Testado (`R8`): falha forçada na última etapa
(`TransformationRepository.add`, via monkeypatch) restaura, após
rollback, `source.revision_status == CURRENT` — nenhum estado parcial
com `target` `CURRENT` e `source` `SUPERSEDED` sem o
`TransformationRecord` correspondente sobrevive.

## Concurrency result

`derive()`: inalterado (ver `V6`, já documentado — nunca bloqueia mais
de um objeto pré-existente).

`revise()`: reaproveita a mesma proteção (`refresh_for_update` sobre
`source`, reavaliação pós-lock antes de qualquer transição de
`revision_status`) — mesmo princípio de E3.3.1, nenhuma técnica nova
introduzida.

**Validado com concorrência genuína contra PostgreSQL real**
(`RC1`-`RC4`, `test_rc_concurrent_revise_on_same_current_does_not_leave_two_current`):
duas threads, duas sessões/conexões distintas, `threading.Barrier`,
ambas chamando `revise()` a partir do **mesmo** `source` (`CURRENT`)
simultaneamente. Resultado, em todas as execuções (4+, incluindo a
suíte automatizada): exatamente **uma** transação commita; a outra
bloqueia em `FOR UPDATE`, ao continuar vê `source.revision_status ==
SUPERSEDED` (já transicionado pela primeira) e é corretamente
rejeitada por `RevisionStatusInvalidTransitionError` — nunca dois
`CURRENT` simultâneos, nunca last-write-wins silencioso, estado final
sempre consistente (exatamente 1 `CURRENT` + 1 `SUPERSEDED`).

## Append-only result

Inalterado — `TransformationRepository.update()`/`.delete()` continuam
sempre rejeitando (`PIA-8010`), revalidado nesta correção (não
enfraquecido).

## Storage Principle

**Congelado documentalmente** (§16 do prompt corretivo E3.4.0):
`LOGICAL IMMUTABILITY != PHYSICAL DUPLICATION`. E3.4 preserva
histórico **lógico** (identidade, continuidade, lineage,
`TransformationRecord`) — isso não obriga o PIA-OS a manter todos os
payloads completos no storage ativo para sempre. Políticas futuras
poderão usar deduplicação física, content-addressed storage, delta
storage, cold storage, retention, archival, compactação — **nada
disso é implementado por este módulo**. `CognitiveObject` não tem
sequer campo de conteúdo/payload nesta fase (ver
`E3_1_LIB01_OBJECT_REPOSITORY.md`), então a distinção é hoje puramente
arquitetural/preparatória — vale para quando um módulo futuro
adicionar armazenamento de conteúdo.

## Migration result

Duas migrações (decisão explícita — ver "Migration decision" abaixo):

1. `f3e7e2b98ce3_add_revision_status_to_cognitive_.py` — `ALTER TABLE
   cognitive_objects ADD COLUMN revision_status` (nullable, aditiva).
2. `2832894b5cb2_create_transformation_records_table_e3_.py` — tabela
   nova, já nascendo com `transformation_kind` incluído.

**Migration decision**: a migração original de `transformation_records`
(também `2832894b5cb2`) foi **editada no lugar** — permitido pelo §21
do prompt corretivo, já que nenhum patch de E3.4 havia sido
gerado/aplicado oficialmente. `revision_status` exigiu uma migração
**nova e separada** sobre `cognitive_objects`, porque essa tabela é de
E3.1, cujas migrações (`257dc8c23ab1`, e a de E3.3 `4f56e1a4936c`) já
foram publicadas em patches anteriores e não são tocadas — apenas
estendidas de forma aditiva. Cadeia final:
`257dc8c23ab1 -> 4f56e1a4936c -> f3e7e2b98ce3 -> 2832894b5cb2`.

Testado `upgrade -> downgrade -> upgrade` do ciclo completo (as duas
novas migrações em sequência) contra PostgreSQL 16 real, com
`lineage_edges` e as colunas preexistentes de `cognitive_objects`
confirmadas intactas em todo o ciclo. `alembic/env.py` não precisou
ser tocado.

## Error codes

| Código | Situação |
|---|---|
| `PIA-8010` | Tentativa de `update`/`delete` de `TransformationRecord` já persistido (E3.4 original) |
| `PIA-8011` (novo, correção E3.4.0) | Transição inválida de `revision_status` — usado tanto pelo guard do modelo quanto por `revise()` quando `source` já está `SUPERSEDED` |

`PIA-8001`-`PIA-8009` inspecionados; nenhum se aplica.

## Idempotência / duplicação

Inalterado quanto a `derive()` (cada chamada produz transformação
distinta, estruturalmente). Para `revise()`: chamar `revise()` duas
vezes sobre o mesmo `source` produz uma segunda revisão **apenas** na
primeira vez — na segunda tentativa, `source` já está `SUPERSEDED` e a
operação é rejeitada (não é uma "duplicata silenciosa", é um erro
explícito, `PIA-8011`).

## Multi-IA readiness

```
COMPETITIVE_READY = TRUE
COMPLEMENTARY_READY = TRUE
SEQUENTIAL_READY = TRUE
```

Nos três modos futuros, outputs intermediários podem permanecer no
workspace — só objetos selecionados/promovidos entram na cadeia
controlada de revisão via `revise()` explícito (§19 do prompt
corretivo E3.4.0). Nenhum método público de `VersionManager` aceita
`provider`/`model`/`agent` (`V7`/`W4`, introspecção de assinatura +
inspeção de código-fonte).

## Testes

Total após a correção E3.4.0: **65 testes novos** (62 unitários + 4 de
integração — `V6` do módulo original + `RC1`-`RC4` desta correção):

- **Model**: `test_transformation_record.py` (5, atualizados com
  `transformation_kind`), `test_revision_status.py` (9, novo —
  transições de `revision_status`).
- **Repository**: `test_transformation_repository.py` (7, atualizados).
- **VersionManager**: `test_version_manager.py` (18, `V1`-`V7`
  originais, ainda válidos), `test_revision_derivation.py` (32, novo —
  `D1`-`D7`, `R1`-`R9`, `W1`-`W4`).
- **Integração contra PostgreSQL real**:
  `test_version_transformation_integration.py` (4 — round-trip,
  append-only, `V6` concorrência de `derive()`, `RC1`-`RC4`
  concorrência de `revise()`).

**100% de cobertura de linha em todo `app/cognitive/`** (243 testes
unitários).

## Non-regression

`E1/E2`/`E3.1`-`E3.3.1`: 698 passed, 13 skipped (sem `.env` local —
mesmo padrão gracioso de sempre), 97,23% (acima do anterior, 97,17%).
Nenhum arquivo protegido tocado; nenhuma migração anterior (E3.1,
E3.3) alterada; `ObjectRepository`, `ClidManager`, `CoidManager`,
`LineageEdge`, `LineageRepository` — todos intocados nesta correção
(confirmado por `git diff --stat`).

## Decisões abertas (Open Decisions)

1. `derive()`/`revise()` sempre estabelecem continuidade (`CLID_A ==
   CLID_B`). O caso "transformação sem continuidade" continua
   indefinido (mesma decisão aberta da versão original de E3.4).
2. `revise()` trata `source.revision_status is None` como entrada
   **implícita** na cadeia controlada — equivalente a uma "Rev.0"
   nunca formalmente marcada `CURRENT`, que vai direto para
   `SUPERSEDED` na primeira chamada. Alternativa não escolhida: exigir
   uma etapa explícita de "promoção inicial" (`None -> CURRENT`) antes
   de permitir `revise()`. Optou-se pela entrada implícita porque
   `PROMOTION_POLICY_STATUS = DEFERRED` — não há política de promoção
   ainda para exigir essa etapa formalmente, e o guard de transição já
   permite `None -> SUPERSEDED` sem violar nenhum invariante.
3. `revise()` confia que o chamador passa o `source` correto (o objeto
   atualmente `CURRENT` da linha de revisão) — não busca "o CURRENT"
   por CLID sozinho. Mesma convenção já usada por
   `inherit(parent, child)` (E3.3), que também recebe objetos
   pré-carregados, não COIDs crus. Se o chamador passar um `source`
   errado (não o `CURRENT` real), o guard de `revision_status` ainda
   protege contra os casos observáveis (rejeita se já `SUPERSEDED`),
   mas não pode detectar um erro de programação do chamador que ignore
   um `CURRENT` diferente por completo.

## Limitações

Preexistentes (E3.4 original, inalteradas): ausência de FK direta
`LineageEdge`<->`TransformationRecord`; `input_refs`/`output_refs` sem
integridade referencial; `list_by_input_coid`/`list_by_output_coid`
filtram em memória.

Novas: `REVISION_NUMBER_STATUS = DEFERRED` — nenhum número de revisão
explícito (`Rev.0`, `Rev.1`, ...); consultável via lineage +
`revision_status`, mas não exibível como um contador direto sem
percorrer a cadeia.

## Itens deferidos

- `ProvenanceRecord` completo: `E3.6`.
- Política de promoção Workspace->Controlled Asset
  (`PROMOTION_POLICY_STATUS`): fase posterior, não numerada
  explicitamente na sequência atual — decisão de política/arbiter.
- Storage optimization (deduplicação física, content-addressed
  storage, delta storage, cold storage, retention, archival): fases
  futuras, ver seção Storage Principle.
- Detecção de ciclo indireto em lineage (`FULL_DAG`): `E3.10`.
- Número de revisão explícito: `REVISION_NUMBER_STATUS = DEFERRED`,
  ver Limitações.
- Metadata/Index/Search/Integrity/Synchronization Managers: módulos
  posteriores.
- Endpoints HTTP: nenhuma evidência de exigência nesta fase.
