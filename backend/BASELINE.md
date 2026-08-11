# BASELINE — PIA-OS Backend v1.0

Referência oficial da versão. Gerada ao final do Módulo 2.13.

| Campo | Valor |
|---|---|
| Versão do backend | 0.1.0 (`app_version` em `Settings`, `pyproject.toml`) |
| Versão da API | v1 |
| Versão da plataforma PIA-OS | 1.0.0 (`PIA_OS_VERSION`) |
| Versão desta baseline de infraestrutura | 1.0.0 |
| Data de congelamento | 2026-08-05 |
| Commit/hash | Não disponível — nenhum repositório Git inicializado neste ambiente de sandbox |
| Módulos incluídos | 2.1 a 2.13 (Entrega 2 completa) |
| Cobertura de testes | 96,36% (meta ≥95%) |
| Testes | 454 passando, 1 skip documentado, 0 falhas |
| Status de lint/formatação | Ruff: 0 erros · Black: 0 arquivos não conformes |
| Status MyPy | 7 erros informativos restantes (de 39), documentados em `Developer_Build_Kit/Auditorias/CODE_QUALITY_REPORT.md` — não bloqueantes |

## Dependências principais

Python 3.12+, FastAPI 0.115.6, SQLAlchemy 2.0.36, Pydantic 2.10.4,
PostgreSQL 16 (via `psycopg`/`asyncpg`), Alembic 1.14.0, Docker/Docker
Compose, Nginx 1.27, Gunicorn 23.0.0 (produção) — versões exatas em
`requirements/{base,dev,prod}.txt`.

## Plataformas suportadas

Cloud (SaaS, container OCI padrão), Desktop (backend local, sem
alteração), Self-Hosted (`docker compose up`, sem dependência externa
obrigatória) — ver `Developer_Build_Kit/Auditorias/DEPLOY_REPORT.md` e `deploy/README_DEPLOY.md`.

## Status da release

**Baseline oficial da Entrega 2 — Infraestrutura do Backend.**
Nenhuma funcionalidade de domínio (autenticação, IA, Objetos
Cognitivos, frontend) está incluída — ver `KNOWN_LIMITATIONS.md`.
Pronta para servir de fundação da Entrega 3.

## Assinatura da baseline

Esta baseline foi produzida por consolidação, auditoria e empacotamento
do trabalho realizado nos Módulos 2.1–2.12, sem introdução de nenhuma
funcionalidade nova — apenas correções de consistência documentadas
individualmente em `Developer_Build_Kit/Auditorias/GLOBAL_ARCHITECTURE_AUDIT.md`
e `Developer_Build_Kit/Auditorias/CODE_QUALITY_REPORT.md`. Ver `BASELINE_FREEZE.md` para os termos do
congelamento.
