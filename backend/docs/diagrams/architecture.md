# Diagrama — Arquitetura Geral

Versão textual (Mermaid) de `architecture.drawio` — mantidas em sincronia
manualmente; esta é a fonte de revisão preferida (revisável em texto/PR),
o `.drawio` é para quem quiser editar visualmente.

```mermaid
graph TB
    subgraph Entrada
        CORS[CORSMiddleware]
        REQID[RequestIDMiddleware]
        SEC[SecurityMiddleware]
        RATE[RateLimitMiddleware opcional]
        TIME[TimingMiddleware]
        LOG[LoggingMiddleware]
    end

    subgraph API["Camada de API - 2.5, 2.9"]
        ROUTER[api/router.py]
        ROUTES[routers/*]
        DEPS[api/dependencies.py]
        DOCS[docs/ - OpenAPI]
    end

    subgraph ERR["Tratamento de Erros - 2.7"]
        REG[exceptions/registry.py]
        HAND[exceptions/handlers.py]
        HIER[PIAOSException e hierarquia]
    end

    subgraph PERSIST["Persistencia e ORM - 2.3, 2.4"]
        REPO[repositories/*]
        UOW[UnitOfWork]
        MODELS[models/ - BaseModel, mixins]
        DB[database/ - engine, session]
    end

    subgraph CONFIG["Configuracao Central - 2.2"]
        SETTINGS[config/settings.py]
    end

    subgraph OBS["Observabilidade - 2.6, 2.8"]
        LOGGER[logging/ - Logger Central]
        SECMOD[security/ - headers, CORS, etc.]
    end

    CORS --> REQID --> SEC --> RATE --> TIME --> LOG --> ROUTER
    ROUTER --> ROUTES
    ROUTES --> DEPS
    ROUTES -->|erro| HAND
    HAND --> HIER
    REG --> HAND
    ROUTES --> REPO
    REPO --> UOW
    REPO --> MODELS
    UOW --> DB
    DB --> PG[(PostgreSQL)]

    SETTINGS -.configura.-> API
    SETTINGS -.configura.-> ERR
    SETTINGS -.configura.-> PERSIST
    SETTINGS -.configura.-> OBS

    LOGGER -.usado por.-> API
    LOGGER -.usado por.-> ERR
    LOGGER -.usado por.-> PERSIST
    SECMOD -.usado por.-> SEC
```

## Como manter atualizado

Ao adicionar uma camada nova (ex.: um módulo de autenticação), adicione
um `subgraph` novo e as arestas de dependência reais — não redesenhe do
zero. Atualize `architecture.drawio` visualmente para refletir a mesma
mudança (ou peça a quem for editar visualmente que sincronize os dois).
