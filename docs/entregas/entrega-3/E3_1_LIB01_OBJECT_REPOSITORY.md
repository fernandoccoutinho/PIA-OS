# E3.1 / LIB-01 — Cognitive Object + Object Repository

## Objetivo

Implementar a unidade persistente fundamental da Biblioteca Cognitiva
(`CognitiveObject`) e seu mecanismo de armazenamento (`ObjectRepository`),
sobre a baseline E1/E2 congelada.

## Arquitetura

Bounded context `app.cognitive` (decisão `BOUNDED_CONTEXT_APP_COGNITIVE`,
`EDR_E3_COGNITIVE_PACKAGING.md`), organizado por camada internamente:

```text
app/cognitive/
    models/
        enums.py            # AccessibilityState (estrutural mínimo)
        cognitive_object.py # ORM
    schemas/
        cognitive_object.py # Create / Read / Update (Pydantic)
    repositories/
        object_repository.py
    errors/
        codes.py             # PIA-8001, PIA-8002
        exceptions.py
```

**Nenhuma camada `services/` foi criada.** `ObjectRepository` cobre
integralmente o que LIB-01 precisa; não havia responsabilidade real
sobrando para uma camada de serviço (§4 do módulo E3.1: "não crie
service vazio apenas por simetria estrutural").

## Arquivos

| Arquivo | Papel |
|---|---|
| `app/cognitive/models/enums.py` | `AccessibilityState` (4 valores) |
| `app/cognitive/models/cognitive_object.py` | ORM `CognitiveObject` + guards de imutabilidade |
| `app/cognitive/schemas/cognitive_object.py` | `CognitiveObjectCreate`/`Read`/`Update` |
| `app/cognitive/repositories/object_repository.py` | `ObjectRepository(BaseRepository[CognitiveObject])` |
| `app/cognitive/errors/codes.py` | `PIA_8001_IDENTITY_IMMUTABLE`, `PIA_8002_CLID_ALREADY_SET` |
| `app/cognitive/errors/exceptions.py` | `CognitiveObjectIdentityImmutableError`, `CognitiveObjectClidAlreadySetError` |
| `alembic/versions/257dc8c23ab1_*.py` | Primeira migração real do projeto |

## Schemas

- `CognitiveObjectCreate`: só `clid` (opcional). `accessibility` não é
  aceito — todo objeto nasce `ACTIVE`.
- `CognitiveObjectRead`: espelha as colunas persistidas (`id`, `clid`,
  `accessibility`, `created_at`, `updated_at`, `deleted_at`, `is_deleted`).
- `CognitiveObjectUpdate`: só `clid`, obrigatório no payload (não faz
  sentido um update vazio) — mas só é aceito pelo modelo se o `clid`
  atual for `None` (ver "Regras de identidade" abaixo). Nem `id` nem
  `accessibility` são campos aceitos aqui.

## Tabela / Model

```
cognitive_objects
  id              UUID PK           (= COID; UUIDMixin/BaseModel — sem 2º mecanismo de PK)
  clid            UUID NULL
  accessibility   VARCHAR(32) NOT NULL DEFAULT 'active'
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
  deleted_at      TIMESTAMPTZ NULL    (SoftDeleteMixin)
```

Nenhum campo de conteúdo/payload — ver "Limitações" abaixo.

## Repository contract

`ObjectRepository` estende `BaseRepository[CognitiveObject]` sem
reimplementar CRUD genérico. Adiciona apenas o que a base genuinamente
não pode saber:

- `get_by_id(entity_id, *, include_deleted=False)` — exclui soft
  deleted por padrão, filtrado no SQL (`WHERE deleted_at IS NULL`).
- `list(*, limit=None, offset=None, include_deleted=False)` — idem,
  filtro aplicado antes de `LIMIT`/`OFFSET`.
- `paginate(*, page=1, page_size=20, include_deleted=False, **filters)`
  — idem; reutiliza o mecanismo público `**filters` de
  `BaseRepository.paginate()` (`deleted_at=None` → `IS NULL`, sem
  nenhuma mudança em `BaseRepository`). `Page.total` reflete
  corretamente apenas os itens ativos.
- `soft_delete(entity)` — marca `deleted_at`, não remove a linha.
  `delete()` (físico, herdado) continua disponível, não é o caminho
  recomendado.

**Correção E3.1.1 (débito C1)**: a versão original de E3.1 filtrava
soft-deleted **em memória, depois** da consulta ao banco — bug real
(`Page.total` contava soft-deleted; `LIMIT`/`OFFSET` operavam sobre a
tabela inteira antes do filtro, podendo devolver páginas
artificialmente curtas). Corrigido para filtrar no SQL, antes de
`LIMIT`/`OFFSET`/`COUNT`, em todos os três métodos. Ver testes
`SD1`–`SD7` na seção Testes.

Não controla commit — quem decide é o chamador via `UnitOfWork`.

## Regras de identidade

- **COID (`id`)**: atribuído uma única vez pelo banco (`UUIDMixin`).
  Uma tentativa de reatribuição após persistência é rejeitada por um
  listener de evento `before_update` do SQLAlchemy, que levanta
  `CognitiveObjectIdentityImmutableError` (`PIA-8001`) antes que o
  UPDATE chegue ao banco.
- **CLID (`clid`)**: pode ser `None` → valor uma única vez. Depois
  disso, **imutável** — decisão canônica registrada em
  `EDR_COUT_PIA_E3.md` (correção E3.1.1): nem um valor *diferente* nem
  `None` são aceitos. Ambos os casos levantam
  `CognitiveObjectClidAlreadySetError` (`PIA-8002`) via `@validates`
  do SQLAlchemy. Resetar para o **mesmo** valor é idempotente (não
  levanta). Uma transformação futura que representar mudança de
  identidade causal suficiente para justificar outro CLID **não muta
  este objeto** — cria um novo objeto/estado e relaciona os dois via
  `LineageEdge`/`TransformationRecord` (E3.3/E3.4). A versão original
  de E3.1 tinha duas lacunas aqui, corrigidas nesta versão: (a) o
  guard não rejeitava `CLID_A → None`; (b) o comentário do código e o
  parágrafo correspondente do `E3_DOMAIN_MODEL_DRAFT.md` sugeriam
  ambiguamente que `TransformationRecord`/`LineageEdge` poderiam
  futuramente mutar o CLID do *mesmo* objeto — corrigido para deixar
  claro que essa relação vive entre dois objetos, nunca dentro de um
  único registro. Ver testes `CL1`–`CL7`.

Ambos os mecanismos foram validados empiricamente contra SQLite e
PostgreSQL reais antes/depois de escrever os testes automatizados (ver
seção Testes).

## Error codes criados

| Código | Categoria | HTTP | Situação |
|---|---|---|---|
| `PIA-8001` | VALIDATION | 409 | Reatribuição de COID após persistência |
| `PIA-8002` | VALIDATION | 409 | Sobrescrita de CLID já atribuído |

`ERROR_CODE_INTEGRATION_STATUS = RESOLVED` (Opção B, decidido em
E3.0/E3.0.1): catálogo próprio em `app.cognitive.errors`, usando os
tipos públicos `ErrorCode`/`ErrorCategory`/`ErrorSeverity` de
`app.core.error_codes`, sem editar `error_codes.py` nem
`ALL_ERROR_CODES`. Confirmado por teste
(`test_cognitive_error_codes_do_not_collide_with_baseline_catalog`).

## Migration

`257dc8c23ab1_create_cognitive_objects_table_e3_1_lib_.py` — cria a
tabela `cognitive_objects`. Testada de ponta a ponta contra PostgreSQL
16 real: `upgrade → downgrade → upgrade`, com verificação de schema via
`psql \d` entre os passos. Aditiva — nenhuma tabela de E1/E2 é tocada
(nenhuma existia antes).

**Nota sobre um bug corrigido durante o desenvolvimento**: a primeira
geração via `alembic revision --autogenerate` produziu
`server_default='active'` (minúsculo, o `.value` do enum Python) mas
`sa.Enum(AccessibilityState)` por padrão persiste o **nome** do membro
(`'ACTIVE'`, maiúsculo) em inserções mediadas pelo ORM — os dois
caminhos de default gravariam valores diferentes. Corrigido com
`values_callable` no `mapped_column`, forçando a coluna a persistir
`.value` de forma consistente nos dois caminhos; migração regenerada.

`alembic/env.py` recebeu uma linha de import
(`import app.cognitive.models`) para que o autogenerate enxergasse o
modelo novo — sem essa linha, `Base.metadata` continuaria vazio de
modelos de domínio e o autogenerate não geraria nada. Não está na
lista de arquivos protegidos do módulo E3.1 e é exigido pelo próprio
objetivo do módulo (§13: "a primeira migration real de E3 poderá
nascer neste módulo").

## Testes

- **Model** (`tests/unit/cognitive/models/test_cognitive_object.py`):
  criação, defaults, UUID/PK, timestamps, serialização via
  `CognitiveObjectRead`, imutabilidade de COID, regras de CLID, TEST
  C1 (conteúdo idêntico ≠ mesmo objeto), TEST C2 (provider/modelo não
  obrigatório), TEST C3 (nenhum campo `cout_score`), objeto sem
  provenance.
- **Repository** (`tests/unit/cognitive/repositories/test_object_repository.py`):
  CREATE/GET/LIST/PAGINATE/UPDATE/SOFT DELETE/NOT FOUND, rollback via
  `UnitOfWork`, transação compartilhada entre múltiplas escritas, TEST
  C4 (nenhum método de ranking/seleção), TEST C6 (dois objetos
  idênticos preservados).
- **Schemas** (`tests/unit/cognitive/schemas/`): campos aceitos/
  rejeitados em cada schema.
- **Errors** (`tests/unit/cognitive/errors/`): catálogo, não-colisão
  com `ALL_ERROR_CODES`, propriedades das exceções.
- **Multi-IA-readiness** (`tests/unit/cognitive/test_multi_ai_readiness.py`):
  duas saídas de agentes distintas coexistindo, ausência de coluna de
  agente/provider único, ausência de unique constraint que amarraria
  objetos a uma "tarefa". Nenhum SDK de IA instalado ou necessário.
- **Integração** (`tests/integration/cognitive/test_object_repository_integration.py`):
  ciclo completo create → persist → retrieve → soft delete contra
  PostgreSQL real, via `UnitOfWork()` com a fábrica de sessão real da
  aplicação (não injetada). Pula graciosamente se Postgres não estiver
  acessível — mesmo padrão de tolerância já usado em
  `tests/integration/database/test_database_connectivity.py`.
  **Executado e passou contra um PostgreSQL 16 real neste
  desenvolvimento.**

Total: 57 testes novos em `app.cognitive` (100% de cobertura de linha
nesse pacote — 8 testes adicionados na correção E3.1.1: SD4-SD7, CL4-CL7)
+ 1 teste de integração.

## Rastreabilidade de baseline (correção E3.1.1, débito C3)

O relatório original de E3.1 declarou `BASELINE FILES MODIFIED = NONE`
sem diferenciar "contrato público alterado" de "arquivo pré-existente
tocado para integração" — impreciso. Classificação corrigida:

```
BASELINE_PUBLIC_CONTRACTS_MODIFIED = NO
PRE_EXISTING_BASELINE_FILES_TOUCHED =
  - backend/alembic/env.py
  - backend/tests/unit/database/test_migrations.py
CLASSIFICATION = MINIMAL_ADDITIVE_E3_INTEGRATION_TOUCHPOINTS
```

- **`alembic/env.py`**: recebeu 1 linha de import
  (`import app.cognitive.models`) para que `CognitiveObject`
  registrasse sua tabela em `Base.metadata` antes do autogenerate —
  sem isso, `alembic revision --autogenerate` não veria nenhum modelo
  de domínio. Nenhuma semântica existente foi alterada, nenhuma tabela
  de E1/E2 foi tocada (nenhuma existe), nenhuma configuração quebrada
  — estritamente aditivo. Classificado como **E3 INTEGRATION
  TOUCHPOINT**, não mudança de contrato de baseline.
- **`tests/unit/database/test_migrations.py`**: 1 teste (`test_head_revision_is_none_when_no_migrations_exist`)
  assumia, pelo próprio comentário original, que nenhuma migração
  jamais existiria — premissa que deixou de ser verdadeira porque
  criar a primeira migração real é o objetivo declarado de E3.1.
  Corrigido para testar o contrato real da função `head_revision()`
  (ver seção seguinte). Nenhuma linha de `app/database/migrations.py`
  (código de produção) foi tocada — apenas o teste. Classificado como
  **E3 INTEGRATION TOUCHPOINT**.

## Correção em teste pré-existente (não-regressão)

`tests/unit/database/test_migrations.py::test_head_revision_is_none_when_no_migrations_exist`
assumia que nenhuma migração jamais existiria no projeto (verdade
apontada explicitamente no próprio comentário do teste como situação
do Módulo 2.3). Como a criação da primeira migração real é o objetivo
declarado de E3.1, esse teste ficou stale por construção — corrigido
para testar o contrato real da função `head_revision()`
(retorna a head quando scripts existem) e mantendo, isolado via
`tmp_path`/`monkeypatch`, o teste do caso `None` para um diretório de
scripts vazio — cobertura estritamente melhor que a original, que
dependia de um estado incidental do repositório em vez do contrato da
função. Nenhuma linha de `app/database/migrations.py` foi alterada.

## Decisões

1. `CognitiveObject` não tem campo de conteúdo/payload — o
   `E3_DOMAIN_MODEL_DRAFT.md` não define um, e §6 do módulo E3.1
   proíbe inventar campos fora do contrato aprovado.
2. `coid` é uma propriedade de leitura que retorna `id` — não um
   segundo mecanismo de identidade.
3. `AccessibilityState` definido aqui apenas como enum estrutural (4
   valores, sem política de transição) — permitido explicitamente
   pelo §22 do módulo E3.1 ("referência estrutural expressamente
   exigida pelo Domain Model"); a elaboração completa é de E3.6.
4. Imutabilidade de COID via evento `before_update` (não `@validates`)
   — evita interferência com a geração do valor default no primeiro
   INSERT; `@validates` usado para `clid`, que não tem essa
   complicação de timing.
5. `get_by_id`/`list`/`paginate` excluem soft-deleted por padrão, com
   `include_deleted=True` explícito para o caso contrário —
   comportamento que `BaseRepository` genérico não poderia ter (não
   sabe sobre `SoftDeleteMixin`).

## Limitações

- `CognitiveObject` é, nesta fase, puramente identidade + ciclo de
  vida — sem campo de conteúdo. Onde/como o conteúdo real será
  anexado (novo campo em módulo futuro? entidade relacionada?) não é
  decidido por este módulo; documentado aqui para que a ausência seja
  reconhecida como intencional, não descuido.
- Filtro de soft delete em `list()`/`paginate()` é aplicado em memória
  após a query (não em SQL) — aceitável no volume esperado de LIB-01;
  candidato a otimização quando `LIB-07 Index Manager` existir.
- `CognitiveObjectUpdate` só permite `clid`, e só quando ainda `None`
  — não há, nesta fase, nenhum campo de `CognitiveObject` atualizável
  livremente após a criação (reflexo direto do modelo mínimo do
  Domain Model Draft, não uma limitação de implementação).

## Itens deferidos

- `CognitiveDistinction`: **DEFERRED** (ver `COGNITIVE_DISTINCTION_STATUS`
  no relatório final) — nada no contrato de `CognitiveObject` exige
  sua existência nesta fase.
- COID Manager completo (geração assistida, unicidade além da PK,
  políticas de emissão): `E3.2`.
- CLID Manager completo (geração, branching, merge, reconstrução de
  lineage): `E3.3`.
- Version Manager, Relationship Engine, Metadata/Provenance/
  Accessibility completos, Index/Search, Knowledge Provenance/
  CausalHistory, Integrity/Synchronization Managers: `E3.4`–`E3.11`.
- Endpoints HTTP: `API_STATUS = DEFERRED` — nenhuma evidência de que o
  backlog canônico exige API nesta fase.
