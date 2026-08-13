# Changelog da API — PIA-OS

## 0.1.0 — Módulo 2.5 — APIs Básicas

- Endpoint raiz GET / com informações da plataforma.
- GET /api/v1/health (liveness).
- GET /api/v1/status (readiness).
- GET /api/v1/version.
- GET /api/v1/metrics.
- Envelope de erro padronizado para toda a API.

## 0.1.0 — Módulo 2.6 — Sistema de Logs

- Cabeçalhos X-Request-ID e X-Response-Time-Ms em toda resposta.

## 0.1.0 — Módulo 2.7 — Tratamento Global de Erros

- Envelope de erro ganhou campos: success, code, category, severity, correlation_id, trace_id, timestamp, details.
- Catálogo oficial de códigos de erro (PIA-XXXX).

## 0.1.0 — Módulo 2.8 — Segurança Base

- Cabeçalhos de segurança em toda resposta.
- CORS centralizado e configurável.
- Novos códigos de erro: PIA-1006 a PIA-1009 (payload grande, media type não suportado, rate limit, host não confiável).

## 0.1.0 — Módulo 2.9 — Documentação OpenAPI

- Todos os endpoints documentados com resumo, descrição, tags e responses.
- Tags organizadas em grupos (System, Health, Status, Version, Metrics + placeholders para módulos futuros).
- Metadados de versão embutidos no schema OpenAPI.
