# Camada ORM — PIA-OS Backend

> Movido de `docs/DATABASE.md` (seções "Camada ORM" e "Hardening da camada
> ORM") para `docs/backend/orm.md` no Módulo 2.12. Infraestrutura de conexão/
> sessão/migrações fica em [`docs/backend/database.md`](database.md).

## Camada ORM (Módulo 2.4)

`app/models/` fornece a infraestrutura reutilizável para entidades
futuras — nenhuma entidade de domínio é definida aqui.

### `BaseModel` e mixins

`BaseModel` (`app/models/base_model.py`) herda de `app.database.base.Base`
— a mesma Base usada pelo Alembic — e inclui apenas `UUIDMixin` +
`TimestampMixin` (o mínimo que praticamente toda entidade precisa).
`SoftDeleteMixin`, `VersionMixin` e `AuditMixin` (`app/models/mixins.py`)
são opcionais, compostos à la carte:

```python
from app.models import BaseModel, SoftDeleteMixin
from sqlalchemy.orm import Mapped, mapped_column

class Documento(BaseModel, SoftDeleteMixin):
    __tablename__ = "documentos"
    titulo: Mapped[str] = mapped_column(nullable=False)
```

Isso é deliberado: forçar todo mixin dentro de uma única `BaseModel`
violaria Interface Segregation (SOLID) — uma entidade que nunca precisará
de soft delete não deveria carregar a coluna `deleted_at`.

| Mixin              | Campo(s)                        | Lógica implementada?          |
|---------------------|-----------------------------------|-------------------------------|
| `UUIDMixin`         | `id` (UUID, gerado no flush)      | Sim — geração do valor         |
| `TimestampMixin`    | `created_at`, `updated_at`        | Sim — mantidos pelo banco       |
| `SoftDeleteMixin`   | `deleted_at`, `is_deleted`        | Não — só o campo/propriedade   |
| `VersionMixin`      | `version` (default 1)             | Não — sem bloqueio otimista    |
| `AuditMixin`        | `created_by`, `updated_by`        | Não — sem preenchimento auto.  |

**Atenção:** `id` (via `UUIDMixin`) só é preenchido no `flush()`, não na
construção do objeto Python — comportamento padrão do SQLAlchemy para
`default=` de coluna. `entity.id` é `None` até `session.add(entity)` +
`flush()`/`commit()`.

### Como criar uma nova entidade

1. Herde de `BaseModel` (e, se precisar, componha com os mixins opcionais).
2. Defina `__tablename__` e as colunas específicas com `Mapped[...]`.
3. Gere a migração: `alembic revision --autogenerate -m "criar_tabela_x"`.
4. Revise o script gerado (ver "Política de migrações" abaixo).

### Como criar um novo repositório

Para a maioria dos casos, `BaseRepository[MinhaEntidade]` já é suficiente:

```python
repo = BaseRepository(session, MinhaEntidade)
```

Para um repositório com métodos específicos de domínio (consultas
próprias), herde de `BaseRepository`:

```python
class DocumentoRepository(BaseRepository[Documento]):
    def find_by_titulo(self, titulo: str) -> Documento | None:
        stmt = select(Documento).where(Documento.titulo == titulo)
        return self._session.execute(stmt).scalar_one_or_none()
```

Qualquer repositório (concreto ou uma implementação alternativa, ex. um
fake em memória para testes) que implemente `get_by_id`, `list`, `add`,
`update`, `delete` satisfaz `RepositoryProtocol`
(`app/repositories/repository_protocol.py`) — verificável via
`isinstance(repo, RepositoryProtocol)`, sem exigir herança.

### Exceções da camada de repositório

`app/repositories/exceptions.py` define `RepositoryError` (base),
`EntityNotFoundError`, `PersistenceError`, `TransactionError`. Uso
exclusivo desta camada — `BaseRepository.add/update/delete` capturam
`SQLAlchemyError` e relançam como `PersistenceError`;
`UnitOfWork.commit/rollback` relançam falhas como `TransactionError`.
Código de domínio futuro nunca deve capturar exceções do SQLAlchemy
diretamente — apenas estas.

## Hardening da camada ORM (Módulo 2.4.1)

Três reforços sobre o Módulo 2.4, sem alterar nenhum comportamento
existente:

### `UnitOfWork` como caminho preferencial

Para qualquer escrita via repositório, prefira `UnitOfWork` a
`session_scope()` — mesmo para um único repositório:

```python
with UnitOfWork() as uow:
    uow.repository(MinhaEntidade).add(entidade)
    uow.commit()
```

`uow.repository(Modelo)` é um atalho para
`BaseRepository(uow.session, Modelo)` — múltiplas chamadas dentro do
mesmo bloco compartilham a mesma sessão/transação (rollback em cascata:
se qualquer operação falhar antes do `commit()`, nenhuma persiste).
`session_scope()` continua existindo para scripts/tarefas fora do padrão
de repositório — não foi removido, apenas deixou de ser o caminho
recomendado para escrita via repositório.

### `BaseRepository`: `exists_by`, `count`, `paginate`

```python
repo.count(status="ativo")           # -> int
repo.exists_by(email="a@b.com")      # -> bool
repo.paginate(page=1, page_size=20, status="ativo")  # -> Page[ModelType]
```

`Page` (dataclass) traz `items`, `total`, `page`, `page_size`,
`total_pages`, `has_next`. Os três métodos aceitam apenas filtros de
igualdade simples (`campo=valor`, combinados com AND) — um campo
inexistente no modelo levanta `ValueError` imediatamente, em vez de
falhar silenciosamente. Consultas mais elaboradas (OR, joins,
comparações) pertencem a um repositório concreto de domínio.

### Transações aninhadas (savepoints)

Já suportadas hoje via `Session.begin_nested()` do próprio SQLAlchemy —
nenhuma API nova foi criada, apenas testado e documentado
(`test_nested_transactions.py`):

```python
with UnitOfWork() as uow:
    uow.repository(EntidadeA).add(a)
    savepoint = uow.session.begin_nested()
    try:
        uow.repository(EntidadeB).add(b)
    except AlgumErro:
        savepoint.rollback()  # reverte só o savepoint, não a transação externa
    uow.commit()
```

### Fora do escopo do 2.4.1 (registrado como roadmap, não pendência)

Abstração `Session` sync/async unificada no repositório, UUID/ULID
alternativo, e savepoints como API de primeira classe (em vez de uso
direto do SQLAlchemy) — evoluções arquiteturais válidas, mas não
requisitos da V1.0.

