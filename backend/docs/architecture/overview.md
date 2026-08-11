# Visão Geral da Arquitetura — PIA-OS Backend

## O que é

Backend do PIA-OS (Persistent Intelligence Architecture Operating
System). Até o Módulo 2.12, exclusivamente infraestrutura — nenhuma
funcionalidade de domínio do PIA-OS (Objetos Cognitivos, IA, usuários)
está implementada. O objetivo desta fase foi construir uma fundação
completa e madura o suficiente para que módulos de domínio futuros não
precisem de retrabalho estrutural.

## Responsabilidades por camada

| Camada | Responsabilidade | Nunca faz |
|---|---|---|
| `app/api/` + `app/routers/` | Roteamento HTTP, validação de entrada via Pydantic | Regra de negócio, acesso a banco |
| `app/config/` | Única fonte de configuração (`Settings`) | — |
| `app/database/` | Engine, sessão, health check, migrações | Regra de negócio |
| `app/models/` | Entidades ORM reutilizáveis (`BaseModel`, mixins) | Lógica de aplicação |
| `app/repositories/` | Único ponto de acesso ao SQLAlchemy | Regra de negócio |
| `app/schemas/` | Contratos de entrada/saída (Pydantic) | Lógica |
| `app/logging/` | Logger Central, contexto de requisição | — |
| `app/exceptions/` + `app/core/error_codes.py` | Hierarquia oficial de erros, catálogo de códigos | — |
| `app/security/` | Headers, CORS, hosts confiáveis, rate limit (estrutura) | Autenticação/autorização (módulos futuros) |
| `app/docs/` | Metadata OpenAPI, tags, exemplos | — |
| `deploy/` | Containerização, orquestração, operação | Lógica de aplicação |

## Fluxo da aplicação

```
Requisição HTTP
  → CORS → RequestID → Security → RateLimit(opcional) → Timing → Logging
  → Roteamento (app/api/router.py → app/routers/*)
  → Dependências (app/api/dependencies.py, se o endpoint precisar)
  → Handler do endpoint
      → (se precisar de dados) Repository/UnitOfWork → SQLAlchemy → PostgreSQL
      → (se der erro) exceções da hierarquia PIAOSException → Handler Global → log + envelope padrão
  → Resposta (sempre com X-Request-ID, X-Response-Time-Ms, headers de segurança)
```

Ver a versão diagramada em
[`docs/diagrams/request_flow.md`](../diagrams/request_flow.md).

## Módulos existentes

Ver [`docs/architecture/module_map.md`](module_map.md) para a tabela
completa (responsabilidade + dependências de cada módulo).

## Princípios seguidos consistentemente

- **Configuração centralizada** (Módulo 2.2) — nenhum código lê
  `os.environ` fora de `app/config/settings.py`.
- **Acesso a dados só via repositório** (Módulo 2.3) — nenhum SQLAlchemy
  fora de `app/repositories/`.
- **Logger único** (Módulo 2.6) — proibido `logging.getLogger()` direto
  fora de `app/logging/`.
- **Erros estruturados** (Módulo 2.7) — toda exceção esperada herda de
  `PIAOSException` e carrega um código do catálogo oficial.
- **Documentação como código** (Módulos 2.9, 2.12) — a documentação é
  gerada/mantida junto do código que descreve, não à parte.

## Decisões arquiteturais relevantes

Ver [`docs/adr/index.md`](../adr/index.md) — 8 decisões documentadas com
contexto, justificativa e alternativas descartadas.
