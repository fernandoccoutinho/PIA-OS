# Métricas do Projeto — PIA-OS Backend v1.0

Coletadas nesta etapa, diretamente do repositório (não estimadas).

| Métrica | Valor |
|---|---|
| Módulos de entrega | 13 (2.1–2.13) |
| Arquivos Python em `app/` | 89 |
| Linhas de código não-vazias/comentário em `app/` (aprox.) | 3621 |
| Arquivos de teste | 68 |
| Funções de teste | 440 |
| Testes passando | 454 |
| Testes com skip (documentado) | 1 |
| Cobertura de código | 96,36% |
| Endpoints da API | 5 |
| ADRs | 8 |
| Diagramas (pares Mermaid + .drawio) | 4 |
| Documentos Markdown em `docs/` | 39 |
| Dockerfiles | 3 |
| Arquivos Docker Compose | 4 |
| Scripts de deploy | 6 |
| Scripts utilitários (raiz) | 4 |
| Erros Ruff | 0 |
| Arquivos não conformes ao Black | 0 |
| Erros MyPy (--strict, informativo) | 7 (de 39 originais — ver CODE_QUALITY_REPORT.md) |

## Como regenerar

Todos os números acima vêm de comandos `find`/`grep`/`wc` diretos
contra o repositório, mais a saída de `pytest --cov`. Nenhum é
mantido manualmente — rode novamente após qualquer mudança relevante
para atualizar este arquivo.
