"""
Teste de integração de `RelationshipEngine`/`RelationshipRepository` —
exercita `UnitOfWork` com a fábrica de sessão REAL da aplicação e a
migração real de `relationships` (`2826ce7fa4dc`) contra PostgreSQL.

Mesmo padrão gracioso dos demais arquivos de integração — pula se
PostgreSQL/a migração não estiverem disponíveis.
"""

import threading

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from app.cognitive.errors.exceptions import (
    RelationshipDuplicateError,
    RelationshipEndpointNotFoundError,
    RelationshipSelfLinkError,
)
from app.cognitive.models.cognitive_object import CognitiveObject
from app.cognitive.models.enums import RelationshipType
from app.cognitive.repositories.object_repository import ObjectRepository
from app.cognitive.repositories.relationship_repository import RelationshipRepository
from app.cognitive.services.relationship_engine import RelationshipEngine
from app.database.health import check_database_health
from app.repositories.unit_of_work import UnitOfWork


def _postgres_available_with_relationships_table() -> bool:
    health = check_database_health()
    if not health.available:
        return False
    from sqlalchemy import inspect

    from app.database.engine import engine

    tables = inspect(engine).get_table_names()
    return {"cognitive_objects", "relationships"}.issubset(tables)


pytestmark = pytest.mark.skipif(
    not _postgres_available_with_relationships_table(),
    reason=(
        "PostgreSQL real indisponível ou migração 2826ce7fa4dc "
        "(relationships) não aplicada neste ambiente."
    ),
)


def _make_managers(session):
    objs = ObjectRepository(session)
    rels = RelationshipRepository(session)
    engine = RelationshipEngine(rels)
    return objs, rels, engine


def test_pg1_and_pg2_round_trip_with_referential_integrity():
    """PG1 (migration já testada acima) + PG2 (FK/integridade de
    endpoint) contra PostgreSQL real."""
    with UnitOfWork() as uow:
        objs, rels, engine = _make_managers(uow.session)
        a = objs.add(CognitiveObject())
        b = objs.add(CognitiveObject())
        uow.commit()
        a_id, b_id = a.id, b.id

    try:
        with UnitOfWork() as uow:
            objs, rels, engine = _make_managers(uow.session)
            rel = engine.create(
                source_coid=a_id, target_coid=b_id, relationship_type=RelationshipType.SUPPORTS
            )
            uow.commit()
            rel_id = rel.id

        with UnitOfWork() as uow:
            objs, rels, engine = _make_managers(uow.session)
            reloaded = rels.get_by_id(rel_id)
            assert reloaded is not None
            assert reloaded.source_coid == a_id
            assert reloaded.target_coid == b_id

        with UnitOfWork() as uow:
            objs, rels, engine = _make_managers(uow.session)
            import uuid

            with pytest.raises(RelationshipEndpointNotFoundError):
                engine.create(
                    source_coid=a_id,
                    target_coid=uuid.uuid4(),
                    relationship_type=RelationshipType.REFERENCES,
                )
            uow.rollback()
    finally:
        with UnitOfWork() as uow:
            objs, rels, engine = _make_managers(uow.session)
            uow.session.execute(
                sa.text("DELETE FROM relationships WHERE source_coid = :a OR target_coid = :a"),
                {"a": str(a_id)},
            )
            for coid in (a_id, b_id):
                leftover = objs.get_by_id(coid, include_deleted=True)
                if leftover is not None:
                    objs.delete(leftover)
            uow.commit()


def test_pg3_duplicate_protection_against_real_database():
    with UnitOfWork() as uow:
        objs, rels, engine = _make_managers(uow.session)
        a = objs.add(CognitiveObject())
        b = objs.add(CognitiveObject())
        uow.commit()
        a_id, b_id = a.id, b.id

    try:
        with UnitOfWork() as uow:
            objs, rels, engine = _make_managers(uow.session)
            engine.create(
                source_coid=a_id, target_coid=b_id, relationship_type=RelationshipType.SUPPORTS
            )
            uow.commit()

        with UnitOfWork() as uow:
            objs, rels, engine = _make_managers(uow.session)
            with pytest.raises(RelationshipDuplicateError) as exc_info:
                engine.create(
                    source_coid=a_id,
                    target_coid=b_id,
                    relationship_type=RelationshipType.SUPPORTS,
                )
            assert exc_info.value.code == "PIA-8014"
            uow.rollback()
    finally:
        with UnitOfWork() as uow:
            objs, rels, engine = _make_managers(uow.session)
            uow.session.execute(
                sa.text("DELETE FROM relationships WHERE source_coid = :a"), {"a": str(a_id)}
            )
            for coid in (a_id, b_id):
                leftover = objs.get_by_id(coid, include_deleted=True)
                if leftover is not None:
                    objs.delete(leftover)
            uow.commit()


def test_pg4_rollback_against_real_database():
    with UnitOfWork() as uow:
        objs, rels, engine = _make_managers(uow.session)
        a = objs.add(CognitiveObject())
        cognitive_id = a.id
        uow.commit()

    try:
        with UnitOfWork() as uow:
            objs, rels, engine = _make_managers(uow.session)
            with pytest.raises(RelationshipSelfLinkError):
                engine.create(
                    source_coid=cognitive_id,
                    target_coid=cognitive_id,
                    relationship_type=RelationshipType.SUPPORTS,
                )
            uow.rollback()

        with UnitOfWork() as uow:
            objs, rels, engine = _make_managers(uow.session)
            assert engine.outgoing(cognitive_id) == []
    finally:
        with UnitOfWork() as uow:
            objs, rels, engine = _make_managers(uow.session)
            leftover = objs.get_by_id(cognitive_id, include_deleted=True)
            if leftover is not None:
                objs.delete(leftover)
            uow.commit()


def test_pg5_concurrent_duplicate_creation_preserves_uniqueness():
    """PG5 — concorrência real de criação duplicada: duas threads,
    duas sessões/conexões distintas, ambas tentando criar a MESMA
    relação (`(A, B, SUPPORTS)`) simultaneamente. Apenas uma pode
    commitar; a outra é rejeitada pela `UniqueConstraint` no banco
    (não simulado apenas em SQLite)."""
    from app.database.engine import engine as db_engine

    SessionFactory = sessionmaker(
        bind=db_engine, autocommit=False, autoflush=False, expire_on_commit=False
    )

    with UnitOfWork() as uow:
        objs, rels, engine_svc = _make_managers(uow.session)
        a = objs.add(CognitiveObject())
        b = objs.add(CognitiveObject())
        uow.commit()
        a_id, b_id = a.id, b.id

    results: dict[str, tuple[str, object]] = {}
    barrier = threading.Barrier(2)

    def worker(name: str) -> None:
        session = SessionFactory()
        try:
            rels_l = RelationshipRepository(session)
            engine_l = RelationshipEngine(rels_l)
            barrier.wait()
            rel = engine_l.create(
                source_coid=a_id, target_coid=b_id, relationship_type=RelationshipType.SUPPORTS
            )
            session.commit()
            results[name] = ("committed", rel.id)
        except Exception as exc:
            session.rollback()
            results[name] = ("failed", type(exc).__name__)
        finally:
            session.close()

    try:
        t1 = threading.Thread(target=worker, args=("T1",))
        t2 = threading.Thread(target=worker, args=("T2",))
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        outcomes = [results.get("T1"), results.get("T2")]
        committed = [o for o in outcomes if o is not None and o[0] == "committed"]
        assert len(committed) == 1, f"esperado exatamente 1 commit, obtido: {outcomes}"

        with UnitOfWork() as uow:
            objs, rels, engine_svc = _make_managers(uow.session)
            all_rels = rels.outgoing(a_id)
            assert len(all_rels) == 1
    finally:
        with UnitOfWork() as uow:
            objs, rels, engine_svc = _make_managers(uow.session)
            uow.session.execute(
                sa.text("DELETE FROM relationships WHERE source_coid = :a"), {"a": str(a_id)}
            )
            for coid in (a_id, b_id):
                leftover = objs.get_by_id(coid, include_deleted=True)
                if leftover is not None:
                    objs.delete(leftover)
            uow.commit()
