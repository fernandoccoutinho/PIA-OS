# Estrutura de Diretórios — PIA-OS Backend

Gerado a partir da árvore real do repositório (não digitado de memória)
para evitar divergência — se este documento ficar desatualizado, é sinal
de que precisa ser regenerado, não de que a estrutura real mudou de
propósito sem documentação.

```
backend/
├── app/
│   ├── api/            # Roteador central, DI, respostas padronizadas, verificador de consistência OpenAPI
│   ├── config/          # Settings — única fonte de configuração (Módulo 2.2)
│   ├── core/              # Ponto de composição: lifespan, error_codes, bootstrap de logging/segurança
│   ├── database/            # Engine, sessão, Base declarativa, health check, migrações
│   ├── docs/                  # Metadata OpenAPI: tags, responses, exemplos, schemas, changelog
│   ├── exceptions/               # Hierarquia PIAOSException, Registry, handlers globais
│   ├── logging/                     # Logger Central, LoggingContext, eventos padronizados
│   ├── middleware/                     # RequestID, Timing, exception_handler (shim)
│   ├── models/                            # BaseModel + mixins reutilizáveis
│   ├── repositories/                         # BaseRepository, UnitOfWork — único acesso a SQLAlchemy
│   ├── routers/                                 # Endpoints: root, health, status, version, metrics
│   ├── schemas/                                    # Contratos Pydantic (common, error, health)
│   ├── security/                                      # Headers, CORS, hosts, rate limit, sanitização
│   ├── services/                                         # Reservado — ainda não usado (nenhum serviço de domínio existe)
│   └── utils/                                                # logger.py — shim de compatibilidade (2.1-2.5)
├── deploy/                # Containerização e operação (Módulo 2.11)
│   ├── docker/               # 3 Dockerfiles + .dockerignore (documentado)
│   ├── compose/                  # 4 arquivos docker-compose por ambiente
│   ├── nginx/                        # Proxy reverso — estrutura, sem certificado real
│   ├── scripts/                          # start/stop/healthcheck/wait_for_db/backup/restore
│   ├── env/                                  # .env.example (ponteiro) + overlays por ambiente
│   └── README_DEPLOY.md                          # Guia operacional completo
├── docs/                   # Documentação técnica (Módulo 2.12 — este conjunto)
│   ├── architecture/          # Visão geral, mapas de módulo/dependência, esta estrutura
│   ├── backend/                   # Um doc por camada: api, config, database, orm, logging, exceptions, security, deployment, testing
│   ├── development/                   # Coding standards, workflow, contribuição, release
│   ├── diagrams/                          # Mermaid (fonte de revisão) + .drawio por diagrama
│   └── adr/                                   # Architecture Decision Records + índice
├── tests/                    # Suíte reorganizada (Módulo 2.10)
│   ├── unit/                     # Isolado, por camada (api, config, database, deploy, exceptions, logging, middleware, models, repositories, security)
│   ├── integration/                  # Via TestClient contra o app real (api, database, logging)
│   ├── fixtures/                         # database, application, settings, users
│   ├── factories/                            # Geração de dados de teste
│   └── helpers/                                  # Assertions e mocks reutilizáveis
├── alembic/                 # Migrações (nenhuma tabela de domínio criada ainda)
├── requirements/               # base.txt / dev.txt / prod.txt
├── scripts/                       # check_api_docs.py, generate_changelog.py, run_ci_checks.sh
├── .github/workflows/                 # CI (chama `make check`)
├── main.py                               # App factory — ponto de entrada
├── pytest.ini / coverage.ini                # Configuração de testes
├── pyproject.toml                               # Black, Ruff, mypy
├── Makefile                                        # Comandos padronizados
├── README.md / CONTRIBUTING.md / CHANGELOG_API.md      # Documentação de topo
└── .dockerignore                                          # Funcional (raiz do contexto de build)
```

## Como regenerar

```bash
find app -maxdepth 1 -type d | sort   # confirma os pacotes de app/
find . -maxdepth 1 -type d | sort     # confirma os diretórios de topo
```

Se a saída divergir do que está documentado acima, atualize este
arquivo manualmente — não existe automação de sincronização nesta etapa.
