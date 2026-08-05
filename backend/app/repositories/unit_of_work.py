"""
Unit of Work — infraestrutura de controle de transação.

Delimita uma transação que pode envolver um ou mais repositórios,
garantindo que todas as operações dentro do bloco sejam commitadas juntas
ou revertidas juntas. Sem lógica de negócio — apenas begin/commit/rollback
e o context manager.

**Padrão preferencial (Módulo 2.4.1):** para qualquer operação que
escreve no banco, prefira `UnitOfWork` a `session_scope()` direto — mesmo
para um único repositório. `UnitOfWork` garante rollback-por-omissão
(se `commit()` não for chamado, nada persiste) e é o único ponto que
sabe compor múltiplos repositórios na mesma transação sem duplicar
gerenciamento de sessão em cada um. `session_scope()`
(`app/database/session.py`) continua existindo para o caso legítimo de
scripts/tarefas fora do padrão de repositório — não foi removido, apenas
deixou de ser o caminho recomendado para escrita via repositório.
"""

from types import TracebackType
from typing import TypeVar

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database.base import Base
from app.database.session import SessionLocal
from app.repositories.base_repository import BaseRepository
from app.repositories.exceptions import TransactionError
from app.utils.logger import get_logger

logger = get_logger("app.database.uow")

ModelType = TypeVar("ModelType", bound=Base)


class UnitOfWork:
    """Delimita uma transação. Uso recomendado via context manager:

    with UnitOfWork() as uow:
        repo = uow.repository(AlgumModelo)
        repo.add(entidade)
        uow.commit()
    # rollback automático se `commit()` não for chamado, ou se uma
    # exceção for lançada dentro do bloco `with`.

    Múltiplos repositórios na mesma transação compartilham `uow.session`
    automaticamente — cada chamada a `uow.repository(Modelo)` cria um
    `BaseRepository` novo, mas todos operam sobre a mesma sessão/transação:

    with UnitOfWork() as uow:
        uow.repository(EntidadeA).add(a)
        uow.repository(EntidadeB).add(b)
        uow.commit()  # A e B persistem juntas, ou nenhuma persiste
    """

    def __init__(self, session_factory: type[Session] | None = None) -> None:
        self._session_factory = session_factory or SessionLocal
        self._session: Session | None = None
        self._committed = False

    @property
    def session(self) -> Session:
        if self._session is None:
            raise RuntimeError("UnitOfWork usado fora do context manager (chame __enter__ antes).")
        return self._session

    def repository(self, model: type[ModelType]) -> BaseRepository[ModelType]:
        """Atalho para `BaseRepository(uow.session, model)` — reduz o
        boilerplate de instanciar o repositório manualmente e reforça
        `UnitOfWork` como o ponto de entrada padrão para transações."""
        return BaseRepository(self.session, model)

    def __enter__(self) -> "UnitOfWork":
        self._session = self._session_factory()
        self._committed = False
        return self

    def commit(self) -> None:
        """Confirma a transação. Deve ser chamado explicitamente pelo chamador.

        Levanta `TransactionError` se o commit falhar (ex.: constraint
        violada só detectada no fim da transação) — a sessão é revertida
        automaticamente antes de propagar o erro.
        """
        try:
            self.session.commit()
            self._committed = True
        except SQLAlchemyError as exc:
            self.session.rollback()
            logger.error("unit_of_work_commit_failed", extra={"error_type": type(exc).__name__})
            raise TransactionError(f"Falha ao commitar transação: {exc}") from exc

    def rollback(self) -> None:
        """Reverte a transação explicitamente.

        Levanta `TransactionError` se o próprio rollback falhar (raro —
        geralmente indica uma conexão já perdida).
        """
        try:
            self.session.rollback()
        except SQLAlchemyError as exc:
            logger.error("unit_of_work_rollback_failed", extra={"error_type": type(exc).__name__})
            raise TransactionError(f"Falha ao reverter transação: {exc}") from exc

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        try:
            if exc_type is not None:
                self.session.rollback()
                logger.error(
                    "unit_of_work_rolled_back_due_to_exception",
                    extra={"exception_type": exc_type.__name__},
                )
            elif not self._committed:
                # Commit não foi chamado explicitamente — rollback por segurança
                # (evita commits implícitos e acidentais de transações parciais).
                self.session.rollback()
                logger.debug("unit_of_work_rolled_back_no_explicit_commit")
        finally:
            self.session.close()
            self._session = None
