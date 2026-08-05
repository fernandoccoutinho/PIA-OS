# Banco de Dados — PIA-OS Backend

> Movido de `docs/DATABASE.md` para `docs/backend/database.md` no Módulo 2.12,
> como parte da consolidação da documentação técnica. Conteúdo relativo à
> camada ORM (Módulos 2.4/2.4.1) foi separado para [`docs/backend/orm.md`](orm.md).


Infraestrutura de persistência do PIA-OS (Módulo 2.3). Nenhuma tabela de
domínio, entidade de negócio ou algoritmo proprietário vive aqui — apenas
a fundação que os módulos futuros usarão.

## Regra arquitetural

**Nenhum componente fora de `app/repositories/` acessa SQLAlchemy
diretamente.** Todo acesso a dados passa por um repositório (herdando de
`BaseRepository`) ou pelo `UnitOfWork`, quando a operação envolve mais de
um repositório na mesma transação. Esta regra vale a partir deste módulo
para todo código de domínio futuro — a camada de infraestrutura
(`app/database/`) é a única exceção, por definição.

## Estrutura

```
app/database/
├── engine.py       # Engine única (sync + async), pool, logging de conexão
├── session.py       # Fábricas de sessão, dependencies do FastAPI, transações
├── base.py           # Base declarativa (SQLAlchemy 2.x)
├── health.py         # Health check dedicado do banco
└── migrations.py     # Wrapper programático sobre o Alembic

app/repositories/
├── base_repository.py  # CRUD genérico, parametrizado por tipo de entidade
└── unit_of_work.py     # Delimitação de transação (begin/commit/rollback)
```

## Engine e pool de conexões

Uma única engine sync (`app.database.engine.engine`) e uma engine async
preparada para uso futuro (`async_engine`) — ambas construídas a partir de
`settings.database_url` (Módulo 2.2), sem uma segunda fonte de
configuração para o driver assíncrono (a URL async é derivada trocando
`+psycopg` por `+asyncpg`).

**Reconexão automática:** `pool_pre_ping=True` testa cada conexão antes de
entregá-la; conexões mortas (após restart do Postgres, timeout de rede)
são descartadas e reabertas de forma transparente, sem erro para o
chamador.

## Sessões e transações

- `get_db` / `get_async_db` — dependencies do FastAPI, uma sessão por
  requisição, fechada ao final. **Não commitam automaticamente** — quem
  decide quando commitar é o `UnitOfWork` ou o código que usa a sessão.
- `session_scope()` / `async_session_scope()` — context managers para uso
  fora de uma requisição HTTP (scripts, tarefas). Commit automático ao
  sair sem erro; rollback automático em exceção.

## Repository Pattern

`BaseRepository[ModelType]` oferece `create`, `get_by_id`, `list`,
`update`, `delete`, `exists` — sem regra de negócio, sem commit (a
transação é responsabilidade de quem chama). Repositórios concretos de
entidades do domínio (módulos futuros) herdam ou compõem esta classe.

```python
repo = BaseRepository(session, MinhaEntidade)
entidade = repo.create(MinhaEntidade(...))
session.commit()  # ou via UnitOfWork
```

## Unit of Work

Delimita uma transação que pode envolver múltiplos repositórios:

```python
with UnitOfWork() as uow:
    repo_a = BaseRepository(uow.session, EntidadeA)
    repo_b = BaseRepository(uow.session, EntidadeB)
    repo_a.create(...)
    repo_b.create(...)
    uow.commit()  # ambas persistem juntas
# se uow.commit() não for chamado, ou se uma exceção ocorrer dentro do
# bloco, a transação inteira é revertida — nunca fica pela metade.
```

## Health check: por que `/status`, não `/health`

`/api/v1/health` é *liveness* — deve refletir apenas se o processo está
no ar. `/api/v1/status` é *readiness* — inclui a checagem real do banco
(`check_database_health()`, com tempo de resposta). Acoplar a checagem de
banco ao endpoint de liveness faria um orquestrador (Kubernetes, por
exemplo) reiniciar a aplicação por uma instabilidade momentânea do
PostgreSQL, o que é o comportamento errado — reiniciar o processo não
resolve um banco fora do ar, apenas gera reinícios em cascata.

## Migrações (Alembic)

Fluxo de trabalho:

```bash
# 1. Gerar uma nova migração a partir de mudanças nos modelos ORM
alembic revision --autogenerate -m "descrição da mudança"

# 2. Revisar o script gerado em alembic/versions/ (autogenerate não é infalível)

# 3. Aplicar
alembic upgrade head

# Reverter a última migração
alembic downgrade -1
```

`app/database/migrations.py` expõe as mesmas operações como funções
Python (`upgrade()`, `downgrade()`, `current_revision()`,
`head_revision()`, `has_pending_migrations()`) para uso em scripts ou
CI/CD — não substitui a CLI, apenas oferece a mesma capacidade
programaticamente.

Nenhuma migração foi gerada neste módulo — o metadata de `Base` continua
vazio de propósito (nenhuma tabela de domínio é criada aqui).


## Política de migrações (nomenclatura, revisão e aprovação)

Regras a seguir a partir do primeiro modelo de domínio real:

- **Nomenclatura:** mensagem da revisão em `snake_case`, verbo no
  infinitivo descrevendo a mudança — ex.: `criar_tabela_usuarios`,
  `adicionar_indice_email_usuarios`. Evitar mensagens genéricas como
  `update` ou `fix`.
- **Uma migração por mudança lógica.** Não agrupar alterações de tabelas
  não relacionadas na mesma revisão — dificulta rollback seletivo.
- **Revisão obrigatória do script gerado.** `--autogenerate` não é
  infalível (não detecta renomeações, constraints complexas, alguns tipos
  de índice) — todo script gerado é revisado manualmente antes do commit,
  nunca aplicado direto ao banco sem leitura.
- **Toda migração precisa de `downgrade()` funcional.** Migrações
  irreversíveis (ex.: drop de coluna com perda de dados) devem documentar
  explicitamente essa limitação no docstring da revisão.
- **Aprovação:** migração que altera uma tabela em produção passa por
  revisão de código como qualquer outra mudança (ver `CONTRIBUTING.md`) —
  nenhuma migração é aplicada em `staging`/`production` fora do pipeline
  de CI/CD.
- **Uma migração por Pull Request**, sempre que possível — facilita
  reverter uma mudança de schema isoladamente se necessário.

## Logging

Eventos registrados: abertura/fechamento de conexão, checkout/checkin do
pool, erros de banco, rollback de transação, e tempo de execução de
consultas (nível `WARNING` se > 500ms). **Nunca são logados os parâmetros
das queries** — apenas o tipo do statement (`SELECT`, `INSERT`, ...) e a
duração, para não expor dados potencialmente sensíveis nos logs.

## Segurança

Todo acesso via SQLAlchemy Core/ORM usa bind parameters automaticamente
(proteção nativa contra SQL Injection). `BaseRepository` não constrói SQL
por concatenação de strings em nenhum ponto.

## Limitações conhecidas desta entrega

- Testes de `BaseRepository`/`UnitOfWork` usam SQLite em memória, não
  PostgreSQL — validam a infraestrutura genérica, não o dialeto Postgres
  especificamente (isso é coberto pelos testes de `engine.py`/`health.py`,
  que apontam para `DATABASE_URL`).
- `migrations.upgrade()`, `downgrade()` e `current_revision()` exigem um
  PostgreSQL real acessível — não puderam ser exercitados neste ambiente
  de sandbox (sem banco disponível). Testados apenas os componentes que
  não dependem de conexão real (`get_alembic_config`, `head_revision`).
- `async_engine`/`AsyncSessionLocal` estão configurados e testados quanto
  à criação, mas nenhum endpoint os utiliza ainda — "preparados para uso
  futuro", conforme escopo do módulo.
