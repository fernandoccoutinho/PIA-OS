# API — PIA-OS Backend

> Consolidado de `docs/API.md` (Módulo 2.5) e `docs/API_DOCUMENTATION.md`
> (Módulo 2.9) em `docs/backend/api.md` no Módulo 2.12 — mesma informação,
> um único lugar, sem duplicação entre os dois documentos anteriores.

## Parte 1 — Infraestrutura REST (Módulo 2.5)


Infraestrutura REST do PIA-OS (Módulo 2.5). Nenhum endpoint funcional de
domínio é definido aqui — apenas a base que os módulos futuros usarão.

## Estrutura

```
app/
├── api/
│   ├── router.py            # Roteador central — root_router + api_router
│   ├── module_registry.py    # Lista canônica de módulos (evita import circular)
│   ├── dependencies.py       # DI centralizada
│   └── responses.py          # Envelopes padronizados de resposta
├── routers/
│   ├── root.py                # GET /
│   ├── health.py              # GET /api/v1/health (liveness)
│   ├── status.py              # GET /api/v1/status (readiness)
│   ├── version.py             # GET /api/v1/version
│   └── metrics.py             # GET /api/v1/metrics (herdado do Módulo 2.1)
├── schemas/
│   ├── health.py               # Schemas dos endpoints de infraestrutura
│   ├── common.py               # Paginação, ordenação, metadados (genéricos)
│   └── error.py                # Formato padrão de erro
├── middleware/
│   ├── request_id.py
│   ├── timing.py
│   ├── logging_middleware.py
│   └── exception_handler.py    # Handlers globais — inclui APIException
└── core/
    ├── lifespan.py
    └── exceptions.py           # Hierarquia de exceções da camada de API
```

## Fluxo de uma requisição

```
Requisição
  → RequestLoggingMiddleware (log de entrada/saída)
  → TimingMiddleware (mede duração, header X-Response-Time-Ms)
  → RequestIDMiddleware (gera/propaga X-Request-ID)
  → Router (app/api/router.py → app/routers/*.py)
  → Dependencies (app/api/dependencies.py, se o endpoint precisar)
  → Handler do endpoint
  → (erro?) → Exception Handler (app/middleware/exception_handler.py) → envelope padrão
  → Resposta
```

Nenhum endpoint é registrado diretamente em `main.py` — tudo passa por
`app.api.router` (`root_router` montado na raiz; `api_router` montado sob
`settings.api_prefix`).

## ADR — `/health` (liveness) separado de `/status` (readiness)

**Contexto:** a especificação do Módulo 2.5 pedia que `/health` verificasse
aplicação, banco, ORM e configuração. A especificação do Módulo 2.3 já
havia levantado a mesma questão para o então único endpoint de saúde.

**Decisão:** `/health` permanece uma verificação de liveness pura —
responde `{"status": "ok"}` se o processo está no ar, sem consultar
dependências externas. Todas as verificações ricas (banco, ORM,
configuração) ficam em `/status`, que é readiness.

**Justificativa:** liveness e readiness respondem perguntas diferentes.
Liveness pergunta "o processo deveria ser reiniciado?" — a resposta correta
quando o PostgreSQL está temporariamente indisponível é **não**: reiniciar
o processo da aplicação não conserta o banco, e ainda arrisca reinícios em
cascata (o novo processo também falharia a checagem, seria morto de novo,
e assim por diante) exatamente quando o sistema já está sob estresse.
Readiness pergunta "esta instância deveria receber tráfego agora?" — aí sim
a resposta pode ser não, e o orquestrador tira a instância do balanceamento
sem matá-la, permitindo recuperação automática assim que o banco voltar.
Esse é o comportamento padrão recomendado por Kubernetes, Docker e a
literatura de sistemas distribuídos em geral.

**Consequência:** `/status` faz mais trabalho (consulta banco, abre uma
sessão ORM, valida configuração) e por isso é mais lento e menos
apropriado como probe de altíssima frequência — é o endpoint certo para
readiness probes (intervalo maior) e para dashboards operacionais, não
para liveness probes (intervalo curto).

**Status:** aceito. Validado em auditoria técnica do Módulo 2.3 e
reconfirmado na auditoria do Módulo 2.5.

## Padronização de respostas

Toda resposta de erro usa o mesmo envelope (`ErrorResponse` /
`app/schemas/error.py`), aplicado automaticamente por
`app.middleware.exception_handler.register_exception_handlers` para:

- `APIException` e subclasses (`app/core/exceptions.py`)
- `HTTPException` do Starlette/FastAPI
- `RequestValidationError` (validação automática do Pydantic)
- Qualquer exceção não tratada (vira 500, nunca vaza stack trace ao cliente)

```json
{
  "error": {
    "message": "not_found",
    "detail": "id=42",
    "status_code": 404,
    "request_id": "5cd5e166-...",
    "path": "/api/v1/recurso/42"
  }
}
```

Para sucesso, `SuccessResponse[T]` (`app/api/responses.py`) e
`MessageResponse` estão disponíveis para endpoints funcionais futuros —
nenhum endpoint desta etapa os usa diretamente porque os schemas de
`root`/`health`/`status`/`version` já são específicos o bastante.

## Exceções: API vs Repositório

`app.core.exceptions.APIException` (camada HTTP) é uma hierarquia
distinta de `app.repositories.exceptions.RepositoryError` (camada de
persistência, Módulo 2.4). Um endpoint futuro que capturar
`EntityNotFoundError` do repositório deve relançar como
`NotFoundException` da API — a tradução é responsabilidade do endpoint,
não automática, para não acoplar a camada HTTP aos detalhes da
persistência:

```python
from app.repositories.exceptions import EntityNotFoundError
from app.core.exceptions import NotFoundException

try:
    entity = repo.get_by_id_or_raise(entity_id)
except EntityNotFoundError as exc:
    raise NotFoundException(detail=str(exc)) from exc
```

## Dependency Injection

`app/api/dependencies.py` centraliza:

- `get_db_session` — sessão de banco por requisição (reexport de
  `app.database.session.get_db`, não uma segunda implementação)
- `get_app_settings` — configuração (permite override em testes via
  `app.dependency_overrides`)
- `get_request_context` — `RequestContext` com `request_id` (preenchido
  hoje) e campos preparados para observabilidade futura
  (`correlation_id`, `session_id`, `trace_id`, `user_id`, `tenant`,
  `provider` — todos `None` nesta etapa)
- `get_current_user` — placeholder; autenticação não implementada nesta
  etapa, retorna sempre `None`

## Como adicionar um novo endpoint

1. Crie o schema de request/response em `app/schemas/` (nunca aceite
   `dict` sem tipagem).
2. Crie o router em `app/routers/<nome>.py`, com `APIRouter(tags=[...])`.
3. Registre o router em `app/api/router.py` (adicione a
   `_API_ROUTERS` e, se for um módulo novo, em
   `app/api/module_registry.py::REGISTERED_MODULE_NAMES` — os dois
   precisam ficar sincronizados, há um `assert` que falha se não
   estiverem).
4. Use `Depends(get_db_session)` para acesso a banco — nunca importe
   `SessionLocal`/`engine` diretamente num handler de rota.
5. Erros de negócio: levante uma subclasse de `APIException`
   (`app/core/exceptions.py`) — não retorne um dict de erro manualmente.
6. Adicione testes em `app/tests/test_<nome>.py`.

## Fora do escopo desta etapa

Login, autenticação, autorização, CRUD, usuários, Objetos Cognitivos, IA,
sessões, cache, upload de arquivos, WebSockets — pertencem a módulos
posteriores, conforme o próprio prompt do Módulo 2.5 define.

## Melhorias registradas (não implementadas nesta etapa)

- Renomear `app/routers/metrics.py` para `observability.py`, agrupando
  métricas, tracing e profiling na mesma camada quando esses recursos
  existirem — sugestão registrada, não obrigatória para a V1.0.

---

## Parte 2 — Documentação OpenAPI e Padronização (Módulo 2.9)


Consolidação da documentação da API (Módulo 2.9). Nenhuma funcionalidade
nova — reaproveita integralmente responses, exceções e schemas dos
Módulos 2.5–2.8.

## Estrutura

```
app/docs/
├── openapi.py       # Config central (título, descrição, licença, contato, servidores, tags)
├── tags.py            # Catálogo de tags (ativas + placeholders)
├── examples.py         # Exemplos padronizados de erro/sucesso
├── responses.py          # Responses documentadas por status HTTP (200-500)
├── schemas.py              # Registro de schemas públicos + checador de description
└── metadata.py               # Versões + timestamp, injetados como x-metadata no OpenAPI

app/api/
└── documentation.py    # Verificador automático de consistência (ConsistencyReport)

scripts/
├── check_api_docs.py     # Roda o verificador, sai com código 1 se houver problema
└── generate_changelog.py  # Regenera CHANGELOG_API.md a partir de app/docs/changelog.py
```

## Tags

| Tag | Status | Endpoints |
|---|---|---|
| System | ativa | `GET /` |
| Health | ativa | `GET /api/v1/health` |
| Status | ativa | `GET /api/v1/status` |
| Version | ativa | `GET /api/v1/version` |
| Metrics | ativa | `GET /api/v1/metrics` |
| Administration | placeholder | — |
| Authentication | placeholder | — |
| Objects | placeholder | — |
| Sessions | placeholder | — |

Os placeholders aparecem no Swagger/ReDoc desde já (organização final
visível antes dos módulos existirem), mas nenhum endpoint os usa.

## Endpoints documentados (5)

| Método | Rota | Tag | Resumo |
|---|---|---|---|
| GET | `/` | System | Informações da plataforma |
| GET | `/api/v1/health` | Health | Liveness do processo |
| GET | `/api/v1/status` | Status | Readiness detalhada |
| GET | `/api/v1/version` | Version | Versões da plataforma |
| GET | `/api/v1/metrics` | Metrics | Métricas de processo |

Todos com `summary`, `description` e `responses=response_500()` (mínimo
comum — nenhum destes endpoints tem outro modo de falha documentável
além de erro interno inesperado, já que não recebem parâmetros).

## Schemas públicos documentados (16)

`HealthResponse`, `ComponentStatus`, `VersionResponse`, `StatusResponse`,
`MetricsResponse`, `RootResponse`, `ErrorDetail`, `ErrorResponse`,
`ValidationErrorItem`, `ValidationResponse`, `PaginationParams`,
`SortParams`, `PaginationMeta`, `Message`, `MessageResponse`,
`SuccessResponse` — todos com `description` em 100% dos campos
(verificado automaticamente por `app/docs/schemas.py::fields_missing_description`,
testado em `test_docs_schemas.py`).

## Metadados no OpenAPI

`info.x-metadata` (extensão padrão OpenAPI, prefixo `x-`) traz
`api_version`, `backend_version`, `pia_os_version`, `generated_at` —
recalculado a cada chamada de `/openapi.json` (não fica preso ao
momento do startup).

## Changelog da API

`app/docs/changelog.py::API_CHANGELOG` é a fonte única — uma entrada por
módulo que alterou a API publicamente. `CHANGELOG_API.md` (raiz do
projeto) e o rodapé da descrição OpenAPI são ambos gerados a partir
dela. Depois de adicionar uma entrada nova:

```bash
make generate-changelog
```

## Verificador de consistência

`app/api/documentation.py::check_endpoint_documentation(app)` inspeciona
as rotas **reais** registradas (não uma lista mantida à parte, que
poderia divergir) e relata: endpoints sem `summary`/`description`/`tags`,
tags fora do catálogo oficial, endpoints sem nenhuma response de erro
documentada, e schemas públicos com campos sem `description`.

```bash
make check-api-docs
```

Testado em `test_api_documentation.py` — inclusive que o app real
(`main.py`) está limpo (`test_real_app_has_clean_documentation`).

## Como adicionar um novo endpoint documentado

1. Escolha a tag certa em `app/docs/tags.py` (ou proponha uma nova, se
   nenhuma existente se aplicar).
2. No decorator da rota, sempre inclua `summary=`, `description=`, e
   `responses=` (reaproveitando `app/docs/responses.py` — não escreva a
   documentação de erro na mão):

   ```python
   from app.docs.responses import response_404, response_500
   from app.docs.tags import TAG_HEALTH

   @router.get(
       "/algo/{id}",
       response_model=AlgoResponse,
       tags=[TAG_HEALTH.name],
       summary="Resumo curto",
       description="Descrição completa do que o endpoint faz.",
       responses={**response_404(), **response_500()},
   )
   def get_algo(id: int) -> AlgoResponse: ...
   ```
3. Rode `make check-api-docs` — deve continuar limpo.

## Como documentar um Schema

Todo campo leva `Field(description="...")`; schemas de resposta levam
`model_config = ConfigDict(json_schema_extra={"example": {...}})`:

```python
from pydantic import BaseModel, ConfigDict, Field

class AlgoResponse(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {"id": 1, "nome": "x"}})

    id: int = Field(description="Identificador único.")
    nome: str = Field(description="Nome do recurso.")
```

Registre o schema novo em `app/docs/schemas.py::PUBLIC_SCHEMAS` para que
o verificador de consistência o cubra automaticamente.

## Como criar um exemplo

Reaproveite `app/docs/examples.py` para erros — o formato já bate com o
envelope real gerado por `app.exceptions.handlers` (Módulo 2.7). Para um
exemplo de sucesso novo, siga o padrão de `EXAMPLE_SUCCESS_MESSAGE` e
valide contra o schema real em teste (`Schema.model_validate(exemplo)`),
como feito em `test_docs_examples.py` — um exemplo que não valida contra
o próprio schema é pior que nenhum exemplo.

## Preparação para SDKs

O schema OpenAPI 3.1 gerado (`/openapi.json`) é a fonte que geradores de
SDK (`openapi-generator`, `openapi-python-client`, etc.) consumem
diretamente — nenhuma transformação adicional é necessária. Tags,
`operationId` (gerado automaticamente pelo FastAPI a partir do nome da
função), exemplos e descrições completas de campo já ficam disponíveis
para qualquer gerador. Nenhum SDK é gerado nesta etapa — apenas a base
está pronta.

## Fora do escopo desta etapa

Novos endpoints, autenticação, autorização, geração de SDK, GraphQL,
gRPC, site de documentação pública externa — conforme o próprio prompt
do Módulo 2.9 define.
