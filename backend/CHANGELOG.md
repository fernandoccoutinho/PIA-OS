# Changelog — PIA-OS Backend

Changelog de infraestrutura (todos os módulos). Para mudanças
especificamente de contrato de API, ver [`CHANGELOG_API.md`](CHANGELOG_API.md)
(fonte gerada a partir de `app/docs/changelog.py`, Módulo 2.9).

## v1.0.0 — Baseline da Entrega 2 (Módulos 2.1–2.13)

### Adicionado
- Arquitetura FastAPI + PostgreSQL + SQLAlchemy 2.x + Alembic (2.1)
- Sistema Central de Configuração, multi-ambiente (2.2)
- Camada de Persistência: engine, sessão, Repository Pattern, UnitOfWork (2.3)
- Camada ORM: BaseModel + mixins composáveis (2.4, hardening em 2.4.1)
- APIs REST: roteador central, DI, respostas padronizadas (2.5)
- Sistema de Logs e Observabilidade: Logger Central, contexto de requisição (2.6)
- Tratamento Global de Erros: hierarquia PIAOSException, catálogo PIA-XXXX (2.7)
- Segurança Base: headers, CORS, hosts confiáveis, rate limit (estrutura) (2.8)
- Documentação OpenAPI completa e padronizada (2.9)
- Infraestrutura de Testes: suíte unit/integration, 96%+ cobertura (2.10)
- Containerização, Deploy e Operação: Docker, Compose, Nginx, scripts (2.11)
- Documentação Técnica completa: arquitetura, ADRs, diagramas (2.12)
- Baseline oficial v1.0, Developer Build Kit, relatórios de release (2.13)

### Não incluído nesta versão
Ver [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md).
