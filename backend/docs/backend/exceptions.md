# Sistema Global de Tratamento de Erros — PIA-OS Backend

> Movido de `docs/ERRORS.md` para `docs/backend/exceptions.md` no Módulo 2.12 (renomeado para bater com o nome de arquivo pedido pela especificação).


Infraestrutura única de tratamento de erros do PIA-OS (Módulo 2.7).
Consolida e evolui as exceções criadas nos Módulos 2.5 (`app.core.exceptions`)
e 2.3/2.4 (`app.repositories.exceptions`) — não as substitui, e não
reimplementa o que já existia.

## Fluxo

```
Erro
  ↓
Exceção específica (PIAOSException ou subclasse)
  ↓
Handler Global (app/exceptions/handlers.py, via Registry)
  ↓
Logger Central (Módulo 2.6) — request_id, correlation_id, trace_id,
                                módulo, rota, método, código do erro,
                                stack trace (dev apenas)
  ↓
Resposta padronizada (ErrorResponse)
```

Nenhuma exceção escapa direto para o usuário — o catch-all
`Exception -> unhandled_exception_handler` garante isso mesmo para
erros totalmente imprevistos.

## Hierarquia oficial

```
PIAOSException
├── APIException
│   ├── BadRequestException        (400)
│   ├── NotFoundException          (404)
│   ├── MethodNotAllowedException  (405)
│   ├── ConflictException          (409)
│   └── InternalServerException    (500)
├── ValidationException            (422 — irmã de APIException, não subclasse)
├── ConfigurationException         (500)
├── DatabaseException              (500)
│   └── DatabaseUnavailableException (503)
├── InfrastructureException        (503)
├── ExternalServiceException       (502)
└── AuthenticationException        (401 — estrutura apenas, sem uso ainda)
```

**`ValidationException` é irmã de `APIException`, não subclasse** —
decisão explícita da especificação do Módulo 2.7, mesmo tendo sido
`APIException` no Módulo 2.5. O comportamento HTTP observável (status
422, mesma mensagem, mesmo formato de resposta) não mudou — só a
relação de herança em Python.

### Relação com `app.repositories.exceptions` (Módulo 2.3/2.4)

`RepositoryError`/`EntityNotFoundError`/`PersistenceError`/`TransactionError`
continuam existindo e **não pertencem a esta hierarquia** — são sinais
internos da camada de persistência, nunca devem cruzar para HTTP
diretamente. Um endpoint que capturar `EntityNotFoundError` relança como
`NotFoundException`:

```python
from app.repositories.exceptions import EntityNotFoundError
from app.exceptions import NotFoundException

try:
    entity = repo.get_by_id_or_raise(entity_id)
except EntityNotFoundError as exc:
    raise NotFoundException(detail=str(exc)) from exc
```

### Relação com `app.config.config.ConfigurationError` (Módulo 2.2)

`ConfigurationError` é levantada apenas no *startup* (`validate_environment`),
fora de qualquer ciclo de requisição — nunca chega a um handler HTTP,
porque impede a aplicação de subir. `ConfigurationException` (2.7) é a
face HTTP, para o caso raro de uma configuração inválida ser detectada
*durante* o processamento de uma requisição.

## Catálogo de códigos de erro

`app/core/error_codes.py`. Cada `ErrorCode` tem: `code`, `default_message`,
`category`, `http_status`, `severity`. Faixas numéricas por categoria:

| Faixa | Categoria | Exemplos |
|---|---|---|
| PIA-0xxx | system | `PIA-0001` desconhecido, `PIA-0002` erro interno |
| PIA-1xxx | api | `PIA-1001` bad request, `PIA-1002` not found, `PIA-1003` method not allowed, `PIA-1004` conflict, `PIA-1005` http genérico |
| PIA-2xxx | validation | `PIA-2001` erro de validação |
| PIA-3xxx | database | `PIA-3001` erro de banco, `PIA-3002` banco indisponível |
| PIA-4xxx | configuration | `PIA-4001` erro de configuração |
| PIA-5xxx | infrastructure | `PIA-5001` erro de infraestrutura |
| PIA-6xxx | external | `PIA-6001` erro de serviço externo |
| PIA-7xxx | authentication | `PIA-7001` erro de autenticação (estrutura apenas) |

**Um código, uma vez publicado, é imutável.** Não reutilize `PIA-1002`
para um erro diferente — crie `PIA-1006` (ou o próximo livre na faixa).

## Formato de resposta

```json
{
  "success": false,
  "error": {
    "code": "PIA-1002",
    "message": "not_found",
    "category": "api",
    "severity": "warning",
    "status_code": 404,
    "request_id": "5cd5e166-...",
    "correlation_id": null,
    "trace_id": null,
    "path": "/api/v1/recurso/42",
    "timestamp": "2026-08-04T01:52:40.624333+00:00",
    "detail": "id=42",
    "details": {"value": "id=42"}
  }
}
```

**Compatibilidade com o Módulo 2.5:** `message`, `detail`, `status_code`,
`request_id`, `path` têm exatamente o mesmo significado de antes — o
2.7 apenas *adicionou* campos (`success` no nível superior; `code`,
`category`, `severity`, `correlation_id`, `trace_id`, `timestamp`,
`details` dentro de `error`). `detail` (singular, valor original) e
`details` (plural, sempre um dict — envolve `detail` em `{"value": ...}`
quando ele não é naturalmente um dict) coexistem de propósito: o
primeiro por compatibilidade, o segundo porque é o formato sugerido
explicitamente pela especificação do Módulo 2.7.

**Stack trace nunca aparece na resposta HTTP**, em nenhum ambiente — só
no log do servidor, e mesmo assim só quando `settings.debug` está ativo.

## Handlers globais

`app/exceptions/handlers.py`, registrados via `app/exceptions/registry.py`:

| Exceção | Handler | Código típico |
|---|---|---|
| `PIAOSException` (+ toda a hierarquia) | `piaos_exception_handler` | o `error_code` da própria exceção |
| `StarletteHTTPException` | `http_exception_handler` | inferido do status via `error_code_for_http_status` |
| `RequestValidationError` | `validation_exception_handler` | `PIA-2001` |
| `SQLAlchemyError` | `sqlalchemy_exception_handler` | `PIA-3001` — nunca expõe a mensagem do driver/SQL |
| `Exception` (catch-all) | `unhandled_exception_handler` | `PIA-0002` |

## Registry — evita duplicação, facilita extensão

```python
from app.exceptions.registry import default_registry

default_registry.register(MinhaExcecaoFutura, meu_handler)  # ValueError se já registrado
```

`ExceptionRegistry.register()` levanta `ValueError` se o tipo já tiver
um handler — registro duplicado é tratado como erro de programação, não
silenciosamente ignorado ou sobrescrito.

## Como criar uma nova exceção

1. Escolha (ou crie) o `ErrorCode` em `app/core/error_codes.py`, na faixa
   numérica da categoria certa. Adicione a `ALL_ERROR_CODES`.
2. Crie a classe em `app/exceptions/<categoria>.py`, herdando de
   `PIAOSException` (ou de uma subclasse existente, se fizer sentido
   semanticamente — ex.: `DatabaseUnavailableException(DatabaseException)`):

   ```python
   class MinhaExcecao(PIAOSException):
       error_code = PIA_XXXX_MEU_ERRO
   ```
3. Exporte em `app/exceptions/__init__.py`.
4. Levante normalmente — o handler global (`piaos_exception_handler`)
   já sabe tratar qualquer `PIAOSException`, sem precisar de um handler
   novo:

   ```python
   from app.exceptions import MinhaExcecao
   raise MinhaExcecao(detail={"campo": "valor"})
   ```

## Ambiente (dev/test/prod)

Controlado inteiramente por `settings.debug` (Módulo 2.2):

- `settings.debug = True` (development) — stack trace incluída no
  **log** (nunca na resposta HTTP).
- `settings.debug = False` (testing/staging/production) — nenhuma
  stack trace, nem no log nem na resposta.

## Logging — o que cada erro registra

Via `events.log_event` (Logger Central, Módulo 2.6): `error_code`,
`category`, `severity`, `request_id`, `correlation_id`, `trace_id`,
`user_id` (sempre `None` nesta etapa — sem autenticação; o campo já
existe em `LoggingContext` para quando houver), `route`, `method`,
`exception_type`, `exception_message`, e `exc_info` (dev apenas).

## Testado

- Toda a hierarquia (`test_exceptions_hierarchy.py`)
- Catálogo de códigos — unicidade, formato, faixas por categoria
  (`test_error_codes.py`)
- Registry — deduplicação, aplicação (`test_exceptions_registry.py`)
- Handlers globais, incluindo `SQLAlchemyError` nunca vazando mensagem
  do driver (`test_exceptions_handlers.py`)
- Comportamento dev vs. produção — stack trace só no log, nunca na
  resposta, em nenhum ambiente (`test_exceptions_environment_behavior.py`)

**Nota técnica encontrada durante os testes:** `TestClient` do Starlette
sempre relança exceções não tratadas pela `ServerErrorMiddleware`
(mesmo com handler registrado — a resposta HTTP real é gerada
corretamente em produção, mas o cliente de teste interrompe o teste),
a menos que seja construído com `raise_server_exceptions=False`. Todo
teste que provoca deliberadamente uma exceção genérica não tratada usa
essa opção — sem ela, os testes de `unhandled_exception_handler`
falhavam por um motivo puramente de configuração do cliente de teste,
não do código sendo testado.
