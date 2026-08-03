# Arquitetura

!!! note "Escopo desta página"
    Visão de engenharia da **Entrega 1**. A arquitetura funcional detalhada
    (modelo de memória, versionamento e governança de acesso) é definida pelo
    responsável do projeto e será incorporada nas entregas seguintes.

## Componentes

| Componente | Tecnologia | Papel |
|------------|-----------|-------|
| API | FastAPI (ASGI, via Uvicorn) | Camada HTTP e orquestração |
| Persistência | PostgreSQL 16 | Armazena a memória local (Entrega 2+) |
| Configuração | pydantic-settings | Configuração por variáveis de ambiente |
| Empacotamento | Docker + Compose | Ambiente reproduzível |

## Organização do código

```text
src/pia_os/
├── __init__.py     # versão do pacote
├── config.py       # Settings (variáveis de ambiente, prefixo PIA_)
├── main.py         # application factory (create_app) + instância app
└── api/            # roteadores HTTP
    └── health.py   # /health e checagens de saúde
tests/              # testes automatizados (pytest)
docs/               # documentação (MkDocs)
```

## Padrões adotados

- **Application factory** (`create_app`) — facilita testes e configuração por
  ambiente.
- **Layout `src/`** — evita imports acidentais e reforça a instalação como pacote.
- **Configuração 12-Factor** — todo o comportamento configurável vem de
  variáveis de ambiente (prefixo `PIA_`).

## Roadmap de arquitetura

As próximas entregas adicionam, sobre esta base:

- **Entrega 2** — camada de banco (SQLAlchemy), migrações (Alembic), logging e
  tratamento de erros.
- **Entrega 3** — modelos de dados da memória, CRUD, versionamento e metadados.
- **Entrega 4** — sessões e a interface padronizada de integração com IA.
