# Mapa de Dependências (pacotes Python) — PIA-OS Backend

Mais granular que [`module_map.md`](module_map.md) — reflete os imports
reais entre pacotes de `app/`, não a numeração de módulos de entrega.

| Pacote | Depende de | Não depende de (propositalmente) |
|---|---|---|
| `app/config/` | — (base de tudo) | Qualquer outro pacote de `app/` |
| `app/logging/` | `app/config/` | `app/database/`, `app/api/` |
| `app/database/` | `app/config/`, `app/logging/` | `app/repositories/`, `app/api/` |
| `app/models/` | `app/database/` (só `Base`) | `app/repositories/` |
| `app/repositories/` | `app/database/`, `app/models/` | `app/api/`, `app/routers/` |
| `app/exceptions/` | `app/config/`, `app/logging/`, `app/core/error_codes.py` | `app/repositories/`, `app/database/` |
| `app/security/` | `app/config/`, `app/logging/`, `app/exceptions/` | `app/routers/` |
| `app/api/` | `app/config/`, `app/logging/`, `app/database/`, `app/exceptions/`, `app/docs/` | `app/security/` (exceto `main.py`, que monta tudo) |
| `app/routers/` | `app/api/`, `app/database/`, `app/config/`, `app/docs/` | `app/repositories/` diretamente (nenhum endpoint de negócio existe ainda) |
| `app/docs/` | `app/config/`, `app/schemas/`, `app/exceptions/` (para exemplos) | `app/routers/` |
| `app/middleware/` | `app/logging/`, `app/exceptions/` | `app/security/` |
| `app/core/` | Praticamente tudo (é o ponto de composição — `lifespan.py`, `security.py`, `logging.py`, `error_codes.py`) | — |
| `main.py` | `app/core/`, `app/api/`, `app/security/`, `app/logging/`, `app/middleware/` | Nada importa `main.py` de volta |

## Regra observada

`app/config/` é a única "folha" verdadeira do grafo — todo o resto pode
depender dela, ela não depende de nada dentro de `app/`. `app/core/` é o
oposto: o ponto de composição que conhece quase tudo, porque sua função
é montar a aplicação (`main.py` delega a ele).

## Import circular conhecido e como foi evitado

`app/repositories/exceptions.py` (Módulo 2.3/2.4, específicas de
persistência) é uma hierarquia **separada** de `app/exceptions/`
(Módulo 2.7, hierarquia HTTP/global) justamente para não criar uma
dependência circular entre a camada de persistência e a camada de API —
ver [`docs/backend/exceptions.md`](../backend/exceptions.md), seção
"Relação com `app.repositories.exceptions`".

## Como manter atualizado

Ao adicionar um import novo entre pacotes, confira esta tabela — se o
import violar uma coluna "Não depende de", é um sinal de possível
problema arquitetural (mesmo critério do
[`docs/diagrams/module_dependencies.md`](../diagrams/module_dependencies.md)).
