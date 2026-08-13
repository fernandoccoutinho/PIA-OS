"""
Exceções específicas da camada de repositório/persistência.

Uso exclusivo desta camada (`app/repositories/`) — código de outras
camadas nunca deve lançar estas exceções diretamente; ele captura
exceções do SQLAlchemy (se acessar a sessão via `UnitOfWork`) ou, mais
comumente, apenas propaga as exceções levantadas por um repositório.

Hierarquia:

    RepositoryError
    ├── EntityNotFoundError
    ├── PersistenceError
    └── TransactionError
"""


class RepositoryError(Exception):
    """Erro base de todas as exceções da camada de repositório."""


class EntityNotFoundError(RepositoryError):
    """Uma entidade esperada não foi encontrada pela chave informada."""

    def __init__(self, model_name: str, entity_id: object) -> None:
        self.model_name = model_name
        self.entity_id = entity_id
        super().__init__(f"{model_name} com id={entity_id!r} não encontrado(a).")


class PersistenceError(RepositoryError):
    """Falha ao persistir dados (constraint violada, erro do driver, etc.).

    Envolve a exceção original do SQLAlchemy/driver (`__cause__`) — o
    chamador pode inspecioná-la se precisar, mas a camada de domínio não
    deve depender de tipos de exceção do SQLAlchemy diretamente.
    """


class TransactionError(RepositoryError):
    """Falha ao iniciar, commitar ou reverter uma transação."""
