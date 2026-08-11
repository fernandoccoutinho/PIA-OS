# Mapa de Módulos — PIA-OS Backend

| Módulo | Responsabilidade | Dependências |
|---|---|---|
| 2.1 Arquitetura | Estrutura de diretórios, FastAPI, Docker, Alembic, ferramentas de qualidade | — |
| 2.2 Configuração Central | `Settings` única fonte de configuração, ambientes (dev/test/staging/prod) | 2.1 |
| 2.3 Persistência | Engine, sessão, `BaseRepository`, `UnitOfWork`, health check do banco | 2.2 |
| 2.4 ORM | `BaseModel`, mixins (`UUIDMixin`, `TimestampMixin`, etc.), `RepositoryProtocol` | 2.3 |
| 2.5 APIs REST | Roteador central, DI, respostas padronizadas, endpoints `/`, `/health`, `/status`, `/version`, `/metrics` | 2.2, 2.4 |
| 2.6 Sistema de Logs | Logger Central, `LoggingContext`, eventos padronizados, middleware de requisição | 2.2 |
| 2.7 Tratamento Global de Erros | Hierarquia `PIAOSException`, catálogo `PIA-XXXX`, Registry de handlers | 2.5, 2.6 |
| 2.8 Segurança Base | Headers, CORS, hosts confiáveis, validação de requisição, rate limit (estrutura) | 2.2, 2.6, 2.7 |
| 2.9 Documentação OpenAPI | Tags, responses centralizadas, exemplos, verificador de consistência automático | 2.5, 2.7 |
| 2.10 Infraestrutura de Testes | Suíte `tests/unit` + `tests/integration`, fixtures/factories/helpers, 96%+ cobertura | 2.2–2.9 (testa tudo) |
| 2.11 Containerização/Deploy | Docker (dev/prod), Compose por ambiente, Nginx, scripts operacionais | 2.2, 2.5 |
| 2.12 Documentação Técnica | Este conjunto de documentos — consolidação, ADRs, diagramas, rastreabilidade | 2.1–2.11 (documenta tudo) |

## Como este mapa é mantido

Atualizado manualmente a cada módulo novo — não gerado automaticamente
a partir do código (o grafo de imports Python real é mais granular que
esta visão por módulo de entrega; ver
[`docs/architecture/dependency_map.md`](dependency_map.md) para a
versão mais próxima do código real).
