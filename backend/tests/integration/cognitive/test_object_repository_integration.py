"""
Teste de integração de `ObjectRepository` — exercita `UnitOfWork` com a
fábrica de sessão REAL da aplicação (`app.database.session.SessionLocal`),
não injetada, e a migração real de `cognitive_objects`.

Segue o mesmo padrão gracioso de
`tests/integration/database/test_database_connectivity.py`: não assume
que um PostgreSQL real está acessível neste ambiente de sandbox/CI —
verifica via `check_database_health()` e pula com uma mensagem clara
quando indisponível, em vez de falhar. Quando um Postgres real está
acessível (ex.: `docker compose up db`, ou o ambiente de
desenvolvimento local) e a migração `257dc8c23ab1` já foi aplicada
(`alembic upgrade head`), este teste valida o ciclo completo
create → persist → retrieve → soft delete contra o banco de fato.
"""

import pytest

from app.cognitive.models.cognitive_object import CognitiveObject
from app.cognitive.repositories.object_repository import ObjectRepository
from app.database.health import check_database_health
from app.repositories.unit_of_work import UnitOfWork


def _postgres_available_with_cognitive_objects_table() -> bool:
    health = check_database_health()
    if not health.available:
        return False
    from sqlalchemy import inspect

    from app.database.engine import engine

    return "cognitive_objects" in inspect(engine).get_table_names()


pytestmark = pytest.mark.skipif(
    not _postgres_available_with_cognitive_objects_table(),
    reason=(
        "PostgreSQL real indisponível ou migração 257dc8c23ab1 "
        "(cognitive_objects) não aplicada neste ambiente — mesmo padrão de "
        "tolerância de tests/integration/database/test_database_connectivity.py."
    ),
)


def test_create_persist_retrieve_soft_delete_round_trip_against_real_database():
    with UnitOfWork() as uow:  # session_factory real (SessionLocal / Postgres)
        repo = ObjectRepository(uow.session)
        created = repo.add(CognitiveObject())
        uow.commit()
        created_id = created.id

    with UnitOfWork() as uow:
        repo = ObjectRepository(uow.session)
        fetched = repo.get_by_id(created_id)
        assert fetched is not None
        assert fetched.id == created_id
        assert fetched.is_deleted is False

        repo.soft_delete(fetched)
        uow.commit()

    with UnitOfWork() as uow:
        repo = ObjectRepository(uow.session)
        assert repo.get_by_id(created_id) is None
        assert repo.get_by_id(created_id, include_deleted=True) is not None
        # limpeza — remove fisicamente o registro de teste do banco real
        leftover = repo.get_by_id(created_id, include_deleted=True)
        repo.delete(leftover)
        uow.commit()


def test_coid_collision_is_rejected_by_the_real_database_constraint():
    """Correção E3.2: a constraint de PK do PostgreSQL real é a
    autoridade final de unicidade de COID — uma tentativa de persistir
    um segundo `CognitiveObject` com o mesmo `id` de um já commitado
    deve ser rejeitada pelo banco de fato (não apenas pela pré-checagem
    em memória de `CoidManager.assert_unique`, que sozinha não cobre
    TOCTOU)."""
    from app.cognitive.errors.exceptions import CoidCollisionError

    with UnitOfWork() as uow:
        repo = ObjectRepository(uow.session)
        original = repo.add(CognitiveObject())
        uow.commit()
        original_id = original.id

    try:
        with UnitOfWork() as uow:
            repo = ObjectRepository(uow.session)
            duplicate = CognitiveObject()
            duplicate.id = original_id
            with pytest.raises(CoidCollisionError) as exc_info:
                repo.add(duplicate)
            assert exc_info.value.code == "PIA-8004"
            uow.rollback()
    finally:
        # limpeza — remove o registro de teste do banco real
        with UnitOfWork() as uow:
            repo = ObjectRepository(uow.session)
            leftover = repo.get_by_id(original_id, include_deleted=True)
            if leftover is not None:
                repo.delete(leftover)
                uow.commit()
