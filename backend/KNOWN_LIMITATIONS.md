# Limitações Conhecidas — PIA-OS Backend v1.0

Funcionalidades **deliberadamente adiadas**, não pendências ou defeitos.
Cada uma pertence explicitamente a uma entrega futura, conforme
declarado nos próprios prompts dos Módulos 2.1–2.13.

## Planejadas para a Entrega 3 (Domínio da Plataforma)

- **Autenticação** — login, sessões, tokens (JWT/OAuth2). Estrutura já
  preparada: tag `Authentication` no OpenAPI (Módulo 2.9), classe
  `AuthenticationException` (Módulo 2.7), campos `SECRET_KEY`/
  `JWT_ALGORITHM`/`JWT_EXPIRATION_MINUTES` já em `Settings` (Módulo 2.2).
- **Usuários e RBAC** — nenhum modelo de usuário existe. `tests/fixtures/users.py`
  já preparado como estrutura para quando existir.
- **IA e Objetos Cognitivos** — nenhuma lógica de domínio do PIA-OS.
  Tag `Objects` e `Sessions` já reservadas no catálogo OpenAPI.
- **Frontend Web** — fora do escopo integralmente.
- **Desktop (Electron/Tauri)** — o backend já funciona localmente sem
  alteração (pré-condição documentada em `docs/backend/deployment.md`),
  mas nenhum empacotamento Electron/Tauri foi feito.
- **SDKs (Python/JavaScript)** — o schema OpenAPI 3.1 já é a fonte que
  um gerador de SDK consumiria diretamente (Módulo 2.9), mas nenhum SDK
  foi gerado.

## Planejadas para quando a infraestrutura de operação amadurecer

- **Kubernetes / Helm / Terraform** — Módulo 2.11 entrega Docker Compose
  deliberadamente, não orquestração de cluster.
- **Certificados HTTPS reais** — bloco `server` do Nginx já existe,
  comentado, pronto para receber um certificado real (Let's Encrypt ou
  gerenciado pela nuvem).
- **Redis ativo** — serviço já presente nos `docker-compose.*.yml` atrás
  de `profiles: with-redis`, mas nenhum código da aplicação se conecta
  a ele ainda.
- **OpenTelemetry / monitoramento distribuído** — `app/logging/` produz
  logs estruturados prontos para um coletor, mas nenhuma integração
  ativa de tracing/métricas externas existe.
- **Balanceamento de carga** — um único `nginx` por deployment nesta
  baseline, sem multi-instância.

## Não são limitações — são decisões arquiteturais definitivas

Para não confundir com a lista acima: a separação `/health`/`/status`
(ADR-001), a composição de mixins do `BaseModel` (ADR-002), e as demais
decisões em `docs/adr/` **não são adiamentos** — são a arquitetura
pretendida, revisitável apenas por um novo ADR que a substitua
explicitamente.
