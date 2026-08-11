# PIA-OS Backend

Fundação arquitetural do backend do **PIA-OS (Persistent Intelligence Architecture
Operating System)**.

- **Módulo 2.1** — infraestrutura arquitetural (FastAPI, PostgreSQL, Docker, Alembic).
- **Módulo 2.2** — Sistema Central de Configuração (ver [`docs/backend/configuration.md`](docs/backend/configuration.md)).
- **Módulo 2.3** — Infraestrutura de Persistência (ver [`docs/backend/database.md`](docs/backend/database.md)).
- **Módulo 2.4** — Camada ORM: `BaseModel`, mixins, Repository Protocol, exceções (ver [`docs/backend/orm.md`](docs/backend/orm.md)).
- **Módulo 2.5** — APIs Básicas: roteador central, DI, respostas padronizadas, `/`, `/health`, `/status`, `/version` (ver [`docs/backend/api.md`](docs/backend/api.md)).
- **Módulo 2.6** — Sistema de Logs e Observabilidade: Logger Central, contexto de requisição, eventos padronizados (ver [`docs/backend/logging.md`](docs/backend/logging.md)).
- **Módulo 2.7** — Sistema Global de Tratamento de Erros: hierarquia `PIAOSException`, catálogo de códigos, Registry (ver [`docs/backend/exceptions.md`](docs/backend/exceptions.md)).
- **Módulo 2.8** — Segurança Base: headers, CORS, trusted hosts, validação de requisição, rate limiting (estrutura) (ver [`docs/backend/security.md`](docs/backend/security.md)).
- **Módulo 2.9** — Documentação OpenAPI e Padronização da API: tags, responses centralizadas, exemplos, verificador de consistência (ver [`docs/backend/api.md`](docs/backend/api.md)).
- **Módulo 2.10** — Infraestrutura de Testes e Garantia de Qualidade: suíte reorganizada (`tests/unit`, `tests/integration`), fixtures/factories/helpers centralizados, 95%+ de cobertura (ver [`docs/backend/testing.md`](docs/backend/testing.md)).
- **Módulo 2.11** — Containerização, Deploy e Operação: imagens dev/prod, Compose por ambiente, Nginx, scripts operacionais, backup/restore (ver [`deploy/README_DEPLOY.md`](deploy/README_DEPLOY.md)).
- **Módulo 2.12** — Documentação Técnica do Backend: arquitetura, ADRs, diagramas, rastreabilidade (ver [`README_BACKEND.md`](README_BACKEND.md), o índice geral).

> Escopo destas entregas: infraestrutura, configuração e persistência apenas.
> Nenhuma regra de negócio, autenticação, IA ou memória cognitiva foi implementada.

## Stack

- Python 3.12+
- FastAPI
- PostgreSQL + SQLAlchemy 2.x + Alembic
- Pydantic v2
- Docker / Docker Compose / Nginx (ver [`deploy/`](deploy/))
- Pytest, Ruff, Black

## Estrutura do projeto

```
backend/
├── app/
│   ├── api/            # Roteador central, DI, respostas padronizadas (ver docs/backend/api.md)
│   ├── routers/         # Endpoints (root, health, status, version, metrics)
│   ├── logging/          # Sistema de Logs e Observabilidade (ver docs/backend/logging.md)
│   ├── exceptions/        # Sistema Global de Tratamento de Erros (ver docs/backend/exceptions.md)
│   ├── security/           # Segurança Base — headers, CORS, rate limit (ver docs/backend/security.md)
│   ├── docs/                # Documentação OpenAPI — tags, responses, exemplos (ver docs/backend/api.md)
│   ├── core/            # Startup/shutdown (lifespan), catálogo de códigos de erro, bootstrap de logging/segurança
│   ├── config/          # Sistema Central de Configuração (ver docs/backend/configuration.md)
│   ├── database/        # Engine, sessão, Base declarativa, health check, migrações
│   ├── models/           # BaseModel + mixins reutilizáveis (ver docs/backend/orm.md)
│   ├── middleware/       # Request ID, timing, handler de exceções
│   ├── repositories/     # BaseRepository, UnitOfWork (ver docs/backend/orm.md)
│   ├── schemas/          # Modelos Pydantic
│   └── utils/            # Shim de compatibilidade do logger (ver docs/backend/logging.md)
├── tests/                 # Suíte unit/integration (ver docs/backend/testing.md)
├── deploy/                  # Docker, Compose, Nginx, scripts, env (ver deploy/README_DEPLOY.md)
├── alembic/               # Migrações (nenhuma tabela de sistema criada)
├── docs/
├── scripts/               # check_api_docs.py, generate_changelog.py, run_ci_checks.sh
├── requirements/          # base.txt / dev.txt / prod.txt
├── main.py                # App factory (entrypoint)
└── pyproject.toml         # Config de Black, Ruff, mypy
```

## Guia de instalação (local, sem Docker)

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
make install-dev
cp .env.example .env
```

## Configuração e ambientes

Consulte [`docs/backend/configuration.md`](docs/backend/configuration.md) para a estrutura
completa do Sistema Central de Configuração. Resumo rápido:

```bash
export ENVIRONMENT=development   # development | testing | staging | production
```

O arquivo `.env` correto é resolvido automaticamente (`.env.<ambiente>` ou
`.env` padrão). Em `staging`/`production`, a aplicação recusa iniciar sem
`SECRET_KEY` e `DATABASE_URL` reais — isso é proposital (fail-fast).

## Guia de execução

```bash
make run
# equivalente a: uvicorn main:app --reload
```

- Swagger: http://localhost:8000/docs
- Redoc: http://localhost:8000/redoc
- OpenAPI JSON: http://localhost:8000/openapi.json

Endpoints básicos (prefixo `/api/v1`):

| Rota                | Finalidade                              |
|----------------------|------------------------------------------|
| `GET /`               | Informações da plataforma (nome, versão, ambiente, timestamp) |
| `GET /api/v1/health`  | Liveness — a aplicação está no ar         |
| `GET /api/v1/version` | Versão do backend, da API, do banco e do PIA-OS |
| `GET /api/v1/status`  | Readiness — banco, ORM, configuração, uptime |
| `GET /api/v1/metrics` | Uptime do processo                       |

## Guia Docker

```bash
make docker-up
# equivalente a: bash deploy/scripts/start.sh dev
```

Sobe `api` (FastAPI, com hot reload) e `db` (PostgreSQL 16). Para
produção, staging ou self-hosted, ver
[`deploy/README_DEPLOY.md`](deploy/README_DEPLOY.md) — imagens
dev/prod separadas, Nginx como proxy reverso, scripts de backup/restore
e guias de operação (reinício, atualização, rollback, recuperação de
desastre).

## Guia de testes

```bash
make test
```

Suíte reorganizada em `tests/unit/` e `tests/integration/`, com
fixtures/factories/helpers centralizados e 95%+ de cobertura — ver
[`docs/backend/testing.md`](docs/backend/testing.md) para a estrutura completa. `/api/v1/status`
reporta `degraded` caso o PostgreSQL não esteja acessível — isso é
esperado ao rodar os testes sem o container `db` ativo.

## Qualidade de código

```bash
ruff check .
black --check .
```

## Migrações (Alembic)

Estrutura pronta para uso; nenhuma migração de tabela de sistema foi gerada
nesta etapa (nenhum modelo ORM foi definido ainda).

```bash
alembic revision --autogenerate -m "descrição"
alembic upgrade head
```

## Fora do escopo desta etapa

Biblioteca Cognitiva, Kernel Cognitivo, PIAP, Hypervisor, Desktop, SDK,
interface, usuários, autenticação, permissões, memória, workflow, IA,
algoritmos proprietários e qualquer regra de negócio.
