# Guia de Contribuição — PIA-OS Backend

## Convenções de nomenclatura

- **Arquivos e módulos:** `snake_case.py` (ex.: `routes_health.py`).
- **Classes:** `PascalCase` (ex.: `RequestIDMiddleware`, `Settings`).
- **Funções e variáveis:** `snake_case` (ex.: `get_settings`, `database_url`).
- **Constantes:** `UPPER_SNAKE_CASE` (ex.: `REQUEST_ID_HEADER`).
- **Routers:** um arquivo por domínio de rota, nomeado `routes_<dominio>.py`.
- **Testes:** espelham o módulo testado — `test_<modulo>.py`, funções `test_<comportamento>`.

## Estrutura de camadas

Cada nova funcionalidade deve respeitar a camada correta:

| Camada         | Pode conter                                   | Não pode conter                     |
|----------------|------------------------------------------------|--------------------------------------|
| `api/`         | Definição de rotas, validação de entrada       | Regra de negócio, acesso direto a DB |
| `services/`    | Regras de negócio, orquestração                | Chamadas SQL diretas                 |
| `repositories/`| Acesso a dados (queries, ORM)                  | Regra de negócio                     |
| `models/`      | Entidades ORM                                  | Lógica de aplicação                  |
| `schemas/`     | Modelos Pydantic (request/response)            | Lógica de negócio                    |

**Regra de acesso a dados (a partir do Módulo 2.3):** nenhum código fora
de `app/repositories/` (e da própria `app/database/`) pode importar
SQLAlchemy para consultar ou persistir dados — sempre via
`BaseRepository`/`UnitOfWork`. Ver [`docs/backend/database.md`](docs/backend/database.md).

**Regra de endpoints (a partir do Módulo 2.5):** nenhum endpoint é
registrado diretamente em `main.py` — sempre via `app/api/router.py`.
Erros de negócio usam subclasses de `APIException`
(`app/core/exceptions.py`), nunca um dict de erro manual. Ver
[`docs/backend/api.md`](docs/backend/api.md) para como adicionar um novo endpoint.

**Regra de logging (a partir do Módulo 2.6):** proibido criar loggers
isolados (`logging.getLogger(...)` direto fora de `app/logging/`) —
sempre `from app.logging import get_logger`. Para eventos, prefira
`events.log_event(...)` com uma constante de `app/logging/events.py` a
uma mensagem livre. Ver [`docs/backend/logging.md`](docs/backend/logging.md).

**Regra de erros (a partir do Módulo 2.7):** toda exceção estruturada
herda de `PIAOSException` (`app/exceptions/`) e carrega um `ErrorCode`
do catálogo oficial (`app/core/error_codes.py`) — nunca levante uma
`Exception` genérica ou um `HTTPException` cru para sinalizar um erro
esperado. Novos handlers globais passam pelo Registry
(`app/exceptions/registry.py`), nunca direto em `main.py`. Ver
[`docs/backend/exceptions.md`](docs/backend/exceptions.md) para como criar uma nova exceção.

**Regra de segurança (a partir do Módulo 2.8):** exceções levantadas
dentro de um middleware não passam pelos handlers globais automaticamente
— capture `PIAOSException` e chame `piaos_exception_handler(request, exc)`
diretamente (ver `docs/backend/security.md`). Toda configuração de segurança
(CORS, hosts confiáveis, rate limit) vem de `Settings` — nunca hardcode
ou leia `os.environ` fora de `app/config/`.

**Regra de documentação (a partir do Módulo 2.9):** todo endpoint novo
leva `summary`, `description`, `tags` (do catálogo em
`app/docs/tags.py`) e `responses=` (reaproveitando `app/docs/responses.py`).
Todo schema público leva `Field(description=...)` em cada campo e é
registrado em `app/docs/schemas.py::PUBLIC_SCHEMAS`. Rode
`make check-api-docs` antes de abrir um PR — ver
[`docs/backend/api.md`](docs/backend/api.md).

**Regra de testes (a partir do Módulo 2.10):** novo teste vai em
`tests/unit/<camada>/` (isolado) ou `tests/integration/<camada>/` (sobe
o app real) — nunca solto na raiz de `tests/`. Reaproveite fixtures/
factories/helpers existentes antes de escrever um mock do zero. Ver
[`docs/backend/testing.md`](docs/backend/testing.md).

Não criar diretórios ou abstrações (ex.: `common/`) preventivamente — apenas
quando houver código real e repetido a compartilhar.

## Fluxo de trabalho

1. Crie uma branch a partir de `main`: `feature/<descricao-curta>` ou `fix/<descricao-curta>`.
2. Rode `make check` antes de abrir um Pull Request (lint + format + testes).
3. Todo PR passa pelo pipeline de CI (lint, format, testes) antes de merge.
4. Mudanças de schema de banco exigem migração Alembic correspondente.

## Padrões de código

- Tipagem completa (type hints) obrigatória em toda função pública.
- Docstrings em português, curtas e objetivas — apenas onde o código não é autoexplicativo.
- Sem lógica de negócio em `api/`, `middleware/`, `config/` ou `database/`.
- Toda variável de ambiente nova deve ser adicionada em `app/config/settings.py` e em `.env.example`.

## Testes

- Todo endpoint novo precisa de teste correspondente em `tests/unit/` ou
  `tests/integration/` (ver [`docs/backend/testing.md`](docs/backend/testing.md)).
- Testes não devem depender de um PostgreSQL real estar rodando, exceto os
  explicitamente marcados como testes de integração.

## Configuração

Toda configuração da aplicação passa pelo Sistema Central de Configuração
(`app/config/`). Nunca leia `os.environ` fora desse módulo. Veja
[`docs/backend/configuration.md`](docs/backend/configuration.md) para a estrutura completa,
os ambientes suportados e como adicionar uma nova variável.

## Deploy

Imagens Docker, Compose por ambiente, Nginx e scripts operacionais vivem
em `deploy/` (Módulo 2.11) — nunca duplique o `Dockerfile` ou o
`docker-compose.yml`; evolua os existentes. Nova variável de ambiente
específica de deploy (não de aplicação) vai em `deploy/env/.env.<ambiente>`
como overlay, nunca reescrevendo `backend/.env.example` por completo. Ver
[`deploy/README_DEPLOY.md`](deploy/README_DEPLOY.md).
