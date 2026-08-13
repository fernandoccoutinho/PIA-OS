# Matriz de Rastreabilidade — PIA-OS Backend v1.0

Liga cada módulo a: código, documentação, ADRs, testes, prompt original,
auditoria e relatórios. Complementa (não duplica)
[`docs/architecture/traceability_matrix.md`](docs/architecture/traceability_matrix.md)
(Módulo 2.12, que cobre módulo×doc×ADR×testes×auditoria em prosa) com as
colunas de prompt e relatório exigidas pela Etapa 9 do Módulo 2.13.

| Módulo | Código principal | Documentação | ADRs | Testes | Prompt | Auditoria/Relatórios |
|---|---|---|---|---|---|---|
| 2.1 | `main.py`, `app/core/lifespan.py` | `docs/architecture/overview.md` | — | `tests/unit/config/`, `tests/unit/database/` | `Developer_Build_Kit/Prompts/prompt-2.1.md` | `Developer_Build_Kit/Auditorias/GLOBAL_ARCHITECTURE_AUDIT.md` |
| 2.2 | `app/config/` | `docs/backend/configuration.md` | — | `tests/unit/config/` | `prompt-2.2.md` | idem |
| 2.3 | `app/database/`, `app/repositories/` | `docs/backend/database.md` | ADR-001 | `tests/unit/database/`, `tests/unit/repositories/` | `prompt-2.3.md` | idem |
| 2.4 | `app/models/` | `docs/backend/orm.md` | ADR-002 | `tests/unit/models/`, `tests/unit/repositories/` | `prompt-2.4.md` | idem |
| 2.5 | `app/api/`, `app/routers/` | `docs/backend/api.md` | ADR-001, ADR-004 | `tests/unit/api/`, `tests/integration/api/` | `prompt-2.5.md` | idem |
| 2.6 | `app/logging/` | `docs/backend/logging.md` | ADR-007 | `tests/unit/logging/`, `tests/integration/logging/` | `prompt-2.6.md` | idem |
| 2.7 | `app/exceptions/`, `app/core/error_codes.py` | `docs/backend/exceptions.md` | ADR-003, ADR-004 | `tests/unit/exceptions/` | `prompt-2.7.md` | idem |
| 2.8 | `app/security/` | `docs/backend/security.md` | ADR-003, ADR-005, ADR-006 | `tests/unit/security/` | `prompt-2.8.md` | idem |
| 2.9 | `app/docs/` | `docs/backend/api.md` (parte 2) | — | `tests/unit/api/` (test_docs_*) | `prompt-2.9.md` | `Developer_Build_Kit/Auditorias/OPENAPI_REPORT.md` |
| 2.10 | `tests/`, `pytest.ini`, `coverage.ini` | `docs/backend/testing.md` | — | (é a própria suíte) | `prompt-2.10.md` | `Developer_Build_Kit/Auditorias/TEST_REPORT.md` |
| 2.11 | `deploy/` | `docs/backend/deployment.md`, `deploy/README_DEPLOY.md` | ADR-008 | `tests/unit/deploy/` | `prompt-2.11.md` | `Developer_Build_Kit/Auditorias/DEPLOY_REPORT.md` |
| 2.12 | `docs/`, `scripts/check_docs_consistency.py` | `README_BACKEND.md` | — | `tests/unit/docs/` | `prompt-2.12.md` | `Developer_Build_Kit/Auditorias/DOCUMENTATION_REPORT.md` |
| 2.13 | `Developer_Build_Kit/`, relatórios de release | `BASELINE.md` | — | (revalida toda a suíte) | `prompt-2.13.md` | Este conjunto de relatórios |

## Como usar esta matriz

Para investigar qualquer módulo: comece pela linha correspondente, siga
para `Developer_Build_Kit/02_Entrega_2/<módulo>/index.md`, que por sua
vez linka cada célula desta tabela ao arquivo real.
