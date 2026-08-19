# PIA-OS Backend — Índice Geral da Documentação

Ponto de entrada para toda a documentação técnica do backend
(Módulo 2.12). Para instalação/execução rápida, ver
[`README.md`](README.md) — este documento é o mapa completo, não um
guia de início rápido.

## Arquitetura

- [Visão Geral](docs/architecture/overview.md) — responsabilidades por
  camada, fluxo da aplicação, princípios seguidos.
- [Mapa de Módulos](docs/architecture/module_map.md) — responsabilidade
  e dependências de cada módulo (2.1–2.12).
- [Mapa de Dependências](docs/architecture/dependency_map.md) — grafo de
  imports real entre pacotes Python.
- [Estrutura de Diretórios](docs/architecture/directory_structure.md) —
  árvore completa, gerada a partir do repositório real.
- [Matriz de Rastreabilidade](docs/architecture/traceability_matrix.md)
  — módulo × documentação × ADR × testes × auditoria.

## Documentação por camada

- [API](docs/backend/api.md) — infraestrutura REST + documentação OpenAPI
- [Configuração](docs/backend/configuration.md)
- [Banco de Dados](docs/backend/database.md)
- [ORM](docs/backend/orm.md)
- [Logging](docs/backend/logging.md)
- [Tratamento de Erros](docs/backend/exceptions.md)
- [Segurança](docs/backend/security.md)
- [Deploy](docs/backend/deployment.md)
- [Testes](docs/backend/testing.md)

## Entregas

- [E4.9.9.d — Composição Final da E4.9](docs/entregas/entrega-4/E4_9_9_D_DESTRUCTIVE_EXECUTION_COMPOSITION.md)
  — `DestructiveExecutionService`, alinhamento textual do identificador
  de regra do recibo e validação prática em sandbox.
- [E4.10 — Compliance Boundary](docs/entregas/entrega-4/E4_10_COMPLIANCE_BOUNDARY.md)
  — avaliação de estado ou ação contra política versionada, produzindo
  diagnóstico e evidência transitórios.

## Diagramas

Cada diagrama tem uma versão Mermaid (revisável em texto/PR) e uma
versão `.drawio` (edição visual) — mantidas em sincronia manualmente.

- [Arquitetura Geral](docs/diagrams/architecture.md)
- [Dependência entre Módulos](docs/diagrams/module_dependencies.md)
- [Fluxo de Requisição](docs/diagrams/request_flow.md) (inclui
  tratamento de exceção e logging)
- [Deploy](docs/diagrams/deployment.md)

## Decisões Arquiteturais (ADRs)

[Índice completo](docs/adr/index.md) — 8 decisões documentadas, cada
uma com contexto, justificativa, impacto e alternativas descartadas.

## Guia do Desenvolvedor

- [Coding Standards](docs/development/coding_standards.md)
- [Workflow](docs/development/workflow.md)
- [Contribuindo](docs/development/contributing.md) (aponta para
  [`CONTRIBUTING.md`](CONTRIBUTING.md))
- [Processo de Release](docs/development/release_process.md)

## Deploy e Operação

[`deploy/README_DEPLOY.md`](deploy/README_DEPLOY.md) — guia operacional
completo (instalação, ambientes, backup/restore, rollback, recuperação
de desastre, Cloud/Desktop/Self-Hosted).

## Como esta documentação é mantida

- **Consolidação, não duplicação:** cada assunto tem exatamente um lugar
  canônico. Onde um documento precisaria repetir algo que já existe em
  outro, ele referencia em vez de copiar.
- **Rastreada a partir do código real** onde possível — a estrutura de
  diretórios e o mapa de dependências são gerados a partir do
  repositório, não digitados de memória.
- **Verificação automática:** `scripts/check_docs_consistency.py`
  detecta links quebrados, documentos órfãos, diagramas sem par
  Mermaid/`.drawio`, e ADRs não referenciados no índice.

```bash
make check-docs
```

## Baseline Oficial v1.0 (Módulo 2.13)

- [`BASELINE.md`](BASELINE.md) — versão, cobertura, dependências, plataformas suportadas.
- [`BASELINE_FREEZE.md`](BASELINE_FREEZE.md) — termos do congelamento da Entrega 2.
- [`CHANGELOG.md`](CHANGELOG.md) — changelog de infraestrutura (todos os módulos).
- [`PROJECT_METRICS.md`](PROJECT_METRICS.md) — métricas reais, coletadas do repositório.
- [`KNOWN_LIMITATIONS.md`](KNOWN_LIMITATIONS.md) — funcionalidades deliberadamente adiadas.
- [`TRACEABILITY_MATRIX.md`](TRACEABILITY_MATRIX.md) — módulo × código × doc × ADR × teste × prompt × relatório.
- [`DEPENDENCY_MATRIX.md`](DEPENDENCY_MATRIX.md) — dependência entre módulos de entrega.
- [`STRUCTURE_MANIFEST.md`](STRUCTURE_MANIFEST.md) — árvore completa, gerada do repositório real.
- [`FINAL_CHECKLIST.md`](FINAL_CHECKLIST.md) — checklist de conformidade do Módulo 2.13.
- [`Developer_Build_Kit/00_START_HERE/README.md`](Developer_Build_Kit/00_START_HERE/README.md) — ponto de entrada para quem não participou da implementação original.
- Relatórios de auditoria: [`Developer_Build_Kit/Auditorias/`](Developer_Build_Kit/Auditorias/) —
  [`GLOBAL_ARCHITECTURE_AUDIT.md`](Developer_Build_Kit/Auditorias/GLOBAL_ARCHITECTURE_AUDIT.md),
  [`CODE_QUALITY_REPORT.md`](Developer_Build_Kit/Auditorias/CODE_QUALITY_REPORT.md),
  [`TEST_REPORT.md`](Developer_Build_Kit/Auditorias/TEST_REPORT.md),
  [`DEPLOY_REPORT.md`](Developer_Build_Kit/Auditorias/DEPLOY_REPORT.md),
  [`OPENAPI_REPORT.md`](Developer_Build_Kit/Auditorias/OPENAPI_REPORT.md),
  [`DOCUMENTATION_REPORT.md`](Developer_Build_Kit/Auditorias/DOCUMENTATION_REPORT.md),
  [`BUILD_KIT_REPORT.md`](Developer_Build_Kit/Auditorias/BUILD_KIT_REPORT.md).

## Fora do escopo desta documentação

Manual do usuário final, documentação comercial, documentação da
interface Web, documentação do aplicativo Desktop, documentação da
camada de IA — pertencem a entregas futuras, quando essas camadas
existirem.
