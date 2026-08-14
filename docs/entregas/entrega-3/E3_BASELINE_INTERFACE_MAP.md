# E3 — Baseline Interface Map

Módulo E3.0 — Baseline Intake & Interface Freeze.

Este documento identifica **exclusivamente** as interfaces de E1/E2 já
aprovadas e efetivamente disponíveis para consumo pela Entrega 3
(Biblioteca Cognitiva / COUT-PIA). Não é uma auditoria de E1/E2 — E1 e
E2 são fato de engenharia (`PASS`), conforme `backend/BASELINE_FREEZE.md`.
Nenhuma interface aqui listada foi modificada para produzir este mapa.

Convenção da tabela: **restrições** descreve como a interface deve ser
usada corretamente; **dependências proibidas** descreve o que E3 nunca
deve fazer em torno dela.

## Persistência

| Interface | Origem | Responsabilidade | Uso por E3 | Restrições | Proibido |
|---|---|---|---|---|---|
| `Base` (declarative) | `app.database.base` | Base declarativa única do SQLAlchemy 2.x | Toda entidade ORM nova de E3 (`CognitiveObject`, `ProvenanceRecord`, etc.) herda de `Base` (via `app.models.base_model.BaseModel`) | Uma única hierarquia declarativa no projeto — não criar uma segunda `Base` | Declarar `DeclarativeBase` própria para o domínio cognitivo |
| `BaseModel`, `UUIDMixin`, `TimestampMixin` | `app.models.base_model`, `app.models.mixins` | PK UUID + `created_at`/`updated_at` | Toda entidade nova de E3 herda de `BaseModel`; compõe `SoftDeleteMixin`/`VersionMixin`/`AuditMixin` à la carte quando fizer sentido | Mixins são estrutura apenas — nenhuma lógica automática de soft delete/versionamento vem "de graça" | Reimplementar PK/timestamps manualmente em vez de herdar |
| `BaseRepository[ModelType]`, `Page[ModelType]` | `app.repositories.base_repository` | CRUD genérico + paginação sobre uma entidade ORM | Repositórios concretos de E3 (Object Repository/LIB-01, etc.) herdam ou compõem `BaseRepository` | Não commita a sessão — quem controla a transação é `UnitOfWork` | Repositório concreto de E3 que reimplementa `add`/`list`/`paginate` do zero |
| `RepositoryProtocol` | `app.repositories.repository_protocol` | Contrato estrutural mínimo de repositório | Permite (mais adiante, fora do escopo de E3.0) um repositório alternativo (ex.: cache/memória) para os mesmos serviços de domínio | Apenas assinaturas — nenhuma lógica | — |
| `UnitOfWork` | `app.repositories.unit_of_work` | Delimita transação sobre um ou mais repositórios | Ponto de entrada padrão para qualquer escrita de E3 que envolva múltiplas entidades (ex.: `CognitiveObject` + `ProvenanceRecord` na mesma transação) | Rollback-por-omissão — `commit()` é sempre explícito | Gerenciar sessão/transação manualmente fora de `UnitOfWork`/`session_scope` |
| `SessionLocal`, `get_db`, `get_async_db`, `session_scope`, `async_session_scope` | `app.database.session` | Fábricas de sessão sync/async + dependencies FastAPI | `get_db`/`get_async_db` para endpoints futuros de E3; `session_scope` para scripts/tarefas de background (ex.: sincronização, LIB-11) | `get_async_db`/`async_session_scope` existem mas nenhum endpoint atual é async-first — E3 decide caso a caso | Importar `engine`/`async_engine` diretamente para abrir conexão fora dessas fábricas |
| `RepositoryError`, `EntityNotFoundError`, `PersistenceError`, `TransactionError` | `app.repositories.exceptions` | Hierarquia de erro da camada de persistência | E3 captura/propaga estas exceções nos repositórios concretos; camada de serviço/domínio não deve depender de tipos do SQLAlchemy | Uso exclusivo da camada de repositório | Lançar `SQLAlchemyError` cru para fora de um repositório |
| Alembic (`backend/alembic/`) | `backend/alembic/env.py` | Migrações versionadas | Primeira migração real do projeto nasce com E3.1 (hoje `alembic/versions/` está vazio, só `.gitkeep`) | Migração aditiva — sem alterar tabelas de E1/E2 (nenhuma existe ainda) | Migração destrutiva sem Stop Condition explícita (ver §20 do prompt) |

## Erros e exceções

| Interface | Origem | Responsabilidade | Uso por E3 | Restrições | Proibido |
|---|---|---|---|---|---|
| `PIAOSException` | `app.exceptions.base` | Raiz de toda exceção estruturada do PIA-OS | Toda exceção de domínio de E3 (`CognitiveObjectNotFoundError`, `CausalIdentityConflictError`, etc.) herda de `PIAOSException` | Cada subclasse define `error_code` de classe | Levantar `Exception` genérica em código de domínio |
| Catálogo `ErrorCode` / `ALL_ERROR_CODES` | `app.core.error_codes` | Códigos oficiais `PIA-0xxx`…`PIA-7xxx` | `PIA-8xxx` é **proposta/reservada** para o domínio cognitivo (não incorporada ao catálogo) — E3 instancia seus próprios `ErrorCode` usando os tipos públicos, em catálogo separado dentro de `app.cognitive`, sem editar este arquivo (`ERROR_CODE_INTEGRATION_STATUS = RESOLVED` via Opção B — ver Dependency Map) | Código publicado é imutável — nunca reutilizar um código para erro diferente | Reaproveitar um `PIA-1xxx`/`PIA-3xxx` existente para um erro de domínio novo; editar `ALL_ERROR_CODES` para acomodar `PIA-8xxx` |
| `ExceptionRegistry`, `default_registry` | `app.exceptions.registry` | Registro extensível de handlers por tipo de exceção | Se E3 introduzir uma exceção não coberta por `PIAOSException` (não deveria — mas o ponto de extensão existe), registra via `default_registry.register(...)` | Registro duplicado do mesmo tipo levanta `ValueError` de propósito | Tocar em `main.py`/`handlers.py` para adicionar um handler novo |

## Observabilidade

| Interface | Origem | Responsabilidade | Uso por E3 | Restrições | Proibido |
|---|---|---|---|---|---|
| `get_logger` | `app.utils.logger` | Logger estruturado (JSON) | Todo log de E3 usa `get_logger("app.cognitive.<módulo>")` | Nunca `print()`/`logging.getLogger` cru | Logger próprio paralelo ao central |
| `LoggingContext`, `logging_context`, `ContextSnapshot` | `app.logging.context` | Propagação de `request_id`/`correlation_id`/`trace_id`/`session_id`/`user_id` via `contextvars` | **Ponto-chave para `ProvenanceRecord`**: `correlation_id`/`session_id` já disponíveis no contexto sem precisar passá-los manualmente por toda a call stack | Baseado em `contextvars` — seguro para código assíncrono | Criar um segundo mecanismo de correlação (ex.: `threading.local` próprio) |

## Configuração e runtime

| Interface | Origem | Responsabilidade | Uso por E3 | Restrições | Proibido |
|---|---|---|---|---|---|
| `Settings`, `settings`, `get_app_settings` | `app.config.settings`, `app.api.dependencies` | Configuração central via variáveis de ambiente | Qualquer parâmetro configurável de E3 (ex.: limites de paginação de busca, TTL de índice) vira campo de `Settings`, nunca `os.environ` direto | Toda variável nova precisa de validação (`app/config/validators.py`) e documentação | Ler `os.environ` fora de `app/config/settings.py` |
| `lifespan` | `app.core.lifespan` | Hooks de startup/shutdown da aplicação | Se E3 precisar inicializar algo no boot (ex.: warm-up de índice de busca — fora do escopo de E3.0), é aqui, não em código de rota | — | Lógica de inicialização espalhada em módulos individuais |

## API / HTTP

| Interface | Origem | Responsabilidade | Uso por E3 | Restrições | Proibido |
|---|---|---|---|---|---|
| `api_router`, `root_router`, `REGISTERED_MODULE_NAMES` | `app.api.router`, `app.api.module_registry` | Composição central de routers | Quando E3 expuser endpoints HTTP (fora do escopo de E3.0 — nenhuma feature LIB-01–11 implementada ainda), registra ali, mantendo o `assert` de sincronia entre router e registry | Nenhum endpoint é registrado direto em `main.py` | Router de E3 montado fora de `app/api/router.py` |
| `get_db_session`, `get_request_context`, `RequestContext`, `get_current_user` | `app.api.dependencies` | Dependency Injection central do FastAPI | `RequestContext` já tem `session_id`/`trace_id`/`user_id`/`tenant`/`provider` como campos preparados (hoje `None`) — E3 os populará quando os endpoints existirem | `get_current_user()` é placeholder — retorna sempre `None`, nenhuma autenticação implementada em E1/E2 | Endpoint de E3 que assume um usuário autenticado antes de E4/autenticação existir |
| `PaginationParams`, `SortParams`, `PaginationMeta`, `Metadata`, `Message` | `app.schemas.common` | Schemas Pydantic reutilizáveis | Base de qualquer listagem/busca de E3 (ex.: `LIB-08 Search Engine`) | Nenhum filtro de domínio aqui — E3 define os próprios filtros compondo estes schemas | Reimplementar paginação do zero |
| `SuccessResponse`, `MessageResponse`, `ErrorResponse`, `ErrorDetail` | `app.api.responses`, `app.schemas.error` | Envelopes padronizados de resposta | Todo endpoint futuro de E3 responde nesse formato | Resposta de erro já é automática via `ExceptionRegistry` — não reimplementar | Endpoint retornando schema "nu" sem envelope |

## Explicitamente fora do escopo de consumo por E3 nesta fase

| Interface | Origem | Por quê |
|---|---|---|
| `app.security.*` (CORS, CSRF, rate limit, trusted hosts, headers) | E2 | Infraestrutura transversal de borda HTTP — nada em E3.0 introduz endpoint novo; revisitar apenas quando LIB-01+ expuser rotas |
| `app.middleware.*` | E2 | Idem — cross-cutting HTTP, não domínio cognitivo |
| `app.docs.*` (OpenAPI metadata) | E2 | Só relevante quando existir endpoint de E3 a documentar |

## Adendo E3.4.2 — interface pública acrescentada após o congelamento

Registro mínimo e explícito da única interface pública que o corretivo
`E3.4.2 — Multi-Input Cognitive Transformation` acrescenta. Nenhuma
interface de E1/E2 listada acima foi modificada para produzi-lo.

| Interface | Origem | Responsabilidade | Restrições | Proibido |
|---|---|---|---|---|
| `MultiInputTransformationManager.derive_many()` | `app.cognitive.services.multi_input_transformation_manager` | Deriva um `CognitiveObject` novo a partir de **N fontes**, criando N `LineageEdge(MERGE)`, exatamente um `TransformationRecord` `DERIVATION` multi-input e a história causal do alvo | Não commita — participa da `UnitOfWork` do chamador, como todos os managers desde E3.3; exige ao menos duas fontes distintas e `declared_losses` não vazio; escreve apenas via repositórios | Usar `ClidManager.inherit()` nesta operação (geraria e gravaria CLID na fonte); mutar qualquer fonte; ampliar `TransformationKind`, `LineageRelation` ou `CausalEventType`; inferir predecessor causal |
| `MultiInputTransformationReceipt` | `app.cognitive.schemas.multi_input_transformation` | Recibo imutável da operação — apenas UUIDs e tuplas, nenhuma instância ORM | `frozen`, hashable, invariantes em `__post_init__`; consumível por `Protocol` estrutural definido do lado consumidor | Expor entidade ORM; importar qualquer coisa de `app.memory` |

A direção da dependência permanece intacta: `app/cognitive` é o único
dono do patrimônio cognitivo, e `app/memory` continua sem importar
`app.cognitive` (`G17` e `MD6` preservados).
