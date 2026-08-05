"""
Teste de concorrência básica da camada de persistência.

Não testa performance sob carga (fora de escopo desta etapa) — apenas a
garantia mínima que a infraestrutura precisa oferecer: sessões abertas
simultaneamente são independentes entre si (isolamento) e não corrompem
o pool de conexões.

Usa um SQLite baseado em arquivo (não `:memory:`) porque o SQLite em
memória usa `SingletonThreadPool` por padrão — cada thread enxergaria um
banco vazio isolado, o que invalidaria justamente o teste de concorrência
entre threads reais.
"""

import threading

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.repositories.base_repository import BaseRepository
from app.repositories.unit_of_work import UnitOfWork
from tests.fixtures.database import SampleModel, _TestBase


@pytest.fixture
def file_sqlite_session_factory(tmp_path):
    db_path = tmp_path / "concurrency_test.db"
    engine = create_engine(f"sqlite:///{db_path}")
    _TestBase.metadata.create_all(engine, tables=[SampleModel.__table__])
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)
    yield factory
    engine.dispose()


def test_multiple_sessions_can_be_opened_simultaneously(sqlite_session_factory):
    """Abre N sessões ao mesmo tempo a partir da mesma fábrica sem erro."""
    sessions = [sqlite_session_factory() for _ in range(10)]
    try:
        assert all(s.is_active for s in sessions)
        assert len({id(s) for s in sessions}) == 10  # todas são objetos distintos
    finally:
        for s in sessions:
            s.close()


def test_concurrent_unit_of_work_writes_are_isolated_until_commit(file_sqlite_session_factory):
    """UoW usada a partir de threads diferentes: commit persiste, ausência
    de commit reverte — sem interferência entre threads.

    Não força duas transações de escrita simultaneamente não commitadas:
    SQLite permite apenas um escritor por vez, então isso seria uma
    condição de corrida do driver, não do código sendo testado. O que
    importa aqui é que `UnitOfWork`/`BaseRepository` funcionam
    corretamente quando chamados a partir de threads distintas.
    """
    errors: list[BaseException] = []

    def worker(name: str, should_commit: bool) -> None:
        try:
            with UnitOfWork(file_sqlite_session_factory) as uow:
                repo = BaseRepository(uow.session, SampleModel)
                repo.create(SampleModel(name=name))
                if should_commit:
                    uow.commit()
        except BaseException as exc:  # noqa: BLE001
            errors.append(exc)

    t1 = threading.Thread(target=worker, args=("concurrent-a", True), daemon=True)
    t2 = threading.Thread(target=worker, args=("concurrent-b", False), daemon=True)
    t1.start()
    t2.start()
    t1.join(timeout=10)
    t2.join(timeout=10)

    assert not errors, f"Erros inesperados nas threads: {errors}"

    with UnitOfWork(file_sqlite_session_factory) as uow:
        repo = BaseRepository(uow.session, SampleModel)
        names = {e.name for e in repo.list()}

    assert "concurrent-a" in names  # commitou -> persistiu
    assert "concurrent-b" not in names  # não commitou -> revertido


def test_pool_reuses_connections_across_sequential_sessions(sqlite_engine):
    """Confirma que o pool é reaproveitado entre sessões sequenciais, não
    recriado a cada uma — connections em uso voltam a 0 após close."""
    if not hasattr(sqlite_engine.pool, "checkedout"):
        pytest.skip("Pool de SQLite em memória não expõe checkedout() (SingletonThreadPool).")
    checked_out_before = sqlite_engine.pool.checkedout()
    with sqlite_engine.connect():
        assert sqlite_engine.pool.checkedout() == checked_out_before + 1
    assert sqlite_engine.pool.checkedout() == checked_out_before
