# Matriz de Rastreabilidade — PIA-OS Backend

Liga cada módulo à sua documentação, ADRs relevantes, localização dos
testes, e se recebeu auditoria/code review externo antes da aprovação.

| Módulo | Documentação | ADRs | Testes | Auditoria recebida |
|---|---|---|---|---|
| 2.1 Arquitetura | `docs/architecture/`, `README.md` | — | `tests/unit/config/`, `tests/unit/database/` (parcial) | Sim — 2 rodadas |
| 2.2 Configuração Central | `docs/backend/configuration.md` | — | `tests/unit/config/` | Sim — 1 rodada |
| 2.3 Persistência | `docs/backend/database.md` | ADR-001 (parcial) | `tests/unit/database/`, `tests/unit/repositories/` | Sim — 1 rodada |
| 2.4 ORM | `docs/backend/orm.md` | ADR-002 | `tests/unit/models/`, `tests/unit/repositories/` | Sim — 2 rodadas (2.4 e 2.4.1) |
| 2.5 APIs REST | `docs/backend/api.md` | ADR-001, ADR-004 | `tests/unit/api/`, `tests/integration/api/` | Sim — 1 rodada |
| 2.6 Sistema de Logs | `docs/backend/logging.md` | ADR-007 | `tests/unit/logging/`, `tests/integration/logging/` | Sim — 1 rodada |
| 2.7 Tratamento Global de Erros | `docs/backend/exceptions.md` | ADR-003 (origem), ADR-004 | `tests/unit/exceptions/` | Sim — 1 rodada |
| 2.8 Segurança Base | `docs/backend/security.md` | ADR-003, ADR-005, ADR-006 | `tests/unit/security/` | Não recebeu rodada de auditoria externa registrada |
| 2.9 Documentação OpenAPI | `docs/backend/api.md` (parte 2) | — | `tests/unit/api/` (test_docs_*) | Não recebeu rodada de auditoria externa registrada |
| 2.10 Infraestrutura de Testes | `docs/backend/testing.md` | — | (é a própria suíte — `tests/test_infrastructure.py` testa a infraestrutura de teste) | Não recebeu rodada de auditoria externa registrada |
| 2.11 Containerização/Deploy | `docs/backend/deployment.md`, `deploy/README_DEPLOY.md` | ADR-008 | `tests/unit/deploy/` | Não recebeu rodada de auditoria externa registrada |
| 2.12 Documentação Técnica | Este conjunto de documentos | — (documenta ADRs anteriores, não cria novos) | `tests/unit/docs/` (verificador de consistência) | Em andamento |

## Como interpretar "Auditoria recebida"

Reflete apenas se uma rodada de revisão externa (auditoria/code review)
foi registrada explicitamente antes de o módulo ser considerado
aprovado — não é um indicador de qualidade por si só. Módulos sem
auditoria externa registrada ainda passaram pela validação interna
padrão (testes, lint, verificação manual descrita nos relatórios de
cada entrega).

## Rastreabilidade reversa: de um teste para o módulo

Todo diretório de teste (`tests/unit/<camada>/`,
`tests/integration/<camada>/`) corresponde 1:1 a um pacote de `app/` —
ver [`docs/architecture/dependency_map.md`](dependency_map.md) para a
correspondência exata pacote → camada.

## Como manter atualizado

Ao concluir um módulo novo, adicione uma linha aqui antes de considerá-lo
encerrado — é o mesmo momento em que o relatório final do módulo é
escrito, não um passo à parte.
