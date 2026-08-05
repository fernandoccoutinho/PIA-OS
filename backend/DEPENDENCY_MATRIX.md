# Matriz de Dependências — PIA-OS Backend v1.0

Formato exigido pela Etapa 13 do Módulo 2.13 — dependência por número de
módulo de entrega. Para o grafo de dependências real entre pacotes
Python (mais granular), ver
[`docs/architecture/dependency_map.md`](docs/architecture/dependency_map.md).

| Módulo | Depende de |
|---|---|
| 2.1 | — |
| 2.2 | 2.1 |
| 2.3 | 2.2 |
| 2.4 | 2.3 |
| 2.5 | 2.2, 2.4 |
| 2.6 | 2.2 |
| 2.7 | 2.5, 2.6 |
| 2.8 | 2.2, 2.6, 2.7 |
| 2.9 | 2.5, 2.7 |
| 2.10 | 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8 (testa tudo) |
| 2.11 | 2.2, 2.5 |
| 2.12 | 2.1–2.11 (documenta tudo) |
| 2.13 | 2.1–2.12 (audita e empacota tudo) |

## Regra observada

Nenhuma dependência "para trás" (um módulo anterior nunca depende de um
posterior) — confirmado por
`docs/diagrams/module_dependencies.md` e pela ausência de qualquer
import de `app/security/`, `app/docs/`, `deploy/` dentro de
`app/config/`, `app/database/`, `app/logging/` (checado nesta auditoria
via `grep`).
