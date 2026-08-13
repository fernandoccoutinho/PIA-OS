"""
Teste de integração de `VersionManager`/`TransformationRepository` —
exercita `UnitOfWork` com a fábrica de sessão REAL da aplicação e a
migração real de `transformation_records` (`2832894b5cb2`) contra
PostgreSQL.

Mesmo padrão gracioso dos demais arquivos de integração — pula se
PostgreSQL/a migração não estiverem disponíveis.
"""

import threading
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker

from app.cognitive.models.cognitive_object import CognitiveObject
from app.cognitive.models.enums import LineageRelation
from app.cognitive.repositories.lineage_repository import LineageRepository
from app.cognitive.repositories.object_repository import ObjectRepository
from app.cognitive.repositories.transformation_repository import TransformationRepository
from app.cognitive.services.clid_manager import ClidManager
from app.cognitive.services.version_manager import VersionManager
from app.database.health import check_database_health
from app.repositories.unit_of_work import UnitOfWork


def _postgres_available_with_transformation_records_table() -> bool:
    health = check_database_health()
    if not health.available:
        return False
    from sqlalchemy import inspect

    from app.database.engine import engine

    tables = inspect(engine).get_table_names()
    return {"cognitive_objects", "lineage_edges", "transformation_records"}.issubset(tables)


pytestmark = pytest.mark.skipif(
    not _postgres_available_with_transformation_records_table(),
    reason=(
        "PostgreSQL real indisponível ou migração 2832894b5cb2 "
        "(transformation_records) não aplicada neste ambiente."
    ),
)


def _make_managers(session):
    objs = ObjectRepository(session)
    lin = LineageRepository(session)
    trans = TransformationRepository(session)
    clid = ClidManager(objs, lin)
    version = VersionManager(objs, clid, trans)
    return objs, lin, trans, clid, version


def test_derive_round_trip_against_real_database():
    """Round-trip completo: source → derive() → target/CLID/edge/record,
    todos confirmados persistidos contra PostgreSQL real."""
    with UnitOfWork() as uow:
        objs, lin, trans, clid, version = _make_managers(uow.session)
        source = objs.add(CognitiveObject())
        uow.commit()
        source_id = source.id

    try:
        with UnitOfWork() as uow:
            objs, lin, trans, clid, version = _make_managers(uow.session)
            src = objs.get_by_id(source_id)
            target, edge, record = version.derive(src, operation_type="summarize")
            uow.commit()
            target_id, record_id = target.id, record.id

        with UnitOfWork() as uow:
            objs, lin, trans, clid, version = _make_managers(uow.session)

            reloaded_source = objs.get_by_id(source_id)
            reloaded_target = objs.get_by_id(target_id)
            assert reloaded_source.clid is not None
            assert reloaded_target.clid == reloaded_source.clid

            assert lin.edge_exists(source_id, target_id, LineageRelation.TRANSFORMED_FROM)

            reloaded_record = trans.get_by_id(record_id)
            assert reloaded_record is not None
            assert reloaded_record.input_refs == [str(source_id)]
            assert reloaded_record.output_refs == [str(target_id)]
    finally:
        with UnitOfWork() as uow:
            objs, lin, trans, clid, version = _make_managers(uow.session)
            uow.session.execute(
                sa.text("DELETE FROM lineage_edges WHERE parent_coid = :s"),
                {"s": str(source_id)},
            )
            uow.session.execute(
                sa.text("DELETE FROM transformation_records WHERE id = :r"),
                {"r": str(record_id)},
            )
            for coid in (source_id, target_id):
                leftover = objs.get_by_id(coid, include_deleted=True)
                if leftover is not None:
                    objs.delete(leftover)
            uow.commit()


def test_transformation_record_is_append_only_against_real_database():
    from app.cognitive.errors.exceptions import TransformationRecordImmutableError

    with UnitOfWork() as uow:
        objs, lin, trans, clid, version = _make_managers(uow.session)
        source = objs.add(CognitiveObject())
        uow.commit()
        source_id = source.id

    try:
        with UnitOfWork() as uow:
            objs, lin, trans, clid, version = _make_managers(uow.session)
            src = objs.get_by_id(source_id)
            target, edge, record = version.derive(src, operation_type="derive")
            uow.commit()
            target_id, record_id = target.id, record.id

        with UnitOfWork() as uow:
            objs, lin, trans, clid, version = _make_managers(uow.session)
            reloaded_record = trans.get_by_id(record_id)
            with pytest.raises(TransformationRecordImmutableError):
                trans.update(reloaded_record)
            with pytest.raises(TransformationRecordImmutableError):
                trans.delete(reloaded_record)
            uow.rollback()
    finally:
        with UnitOfWork() as uow:
            objs, lin, trans, clid, version = _make_managers(uow.session)
            uow.session.execute(
                sa.text("DELETE FROM lineage_edges WHERE parent_coid = :s"),
                {"s": str(source_id)},
            )
            uow.session.execute(
                sa.text("DELETE FROM transformation_records WHERE id = :r"),
                {"r": str(record_id)},
            )
            for coid in (source_id, target_id):
                leftover = objs.get_by_id(coid, include_deleted=True)
                if leftover is not None:
                    objs.delete(leftover)
            uow.commit()


def test_v6_concurrent_derive_from_same_source_does_not_corrupt_clid():
    """V6 (concorrência): duas threads reais, cada uma com sua própria
    sessão/conexão, chamando `derive()` a partir do MESMO `source`
    simultaneamente. Reutiliza a proteção de E3.3.1
    (`refresh_for_update` dentro de `ClidManager.inherit`, chamado por
    `derive`) — nenhuma corrupção de CLID esperada: cada `target` é
    sempre uma linha nova (sem conflito de PK entre threads), mas
    ambos devem herdar o **mesmo** CLID de `source`, já que o CLID de
    `source` só pode ser resolvido/commitado uma vez (a segunda
    transação bloqueia em `FOR UPDATE` até a primeira liberar `source`,
    então enxerga o CLID já commitado)."""
    from app.database.engine import engine

    SessionFactory = sessionmaker(
        bind=engine, autocommit=False, autoflush=False, expire_on_commit=False
    )

    with UnitOfWork() as uow:
        objs, lin, trans, clid, version = _make_managers(uow.session)
        source = objs.add(CognitiveObject())
        uow.commit()
        source_id = source.id

    results: dict[str, tuple[str, object]] = {}
    barrier = threading.Barrier(2)

    def worker(name: str) -> None:
        session = SessionFactory()
        try:
            objs_l = ObjectRepository(session)
            lin_l = LineageRepository(session)
            trans_l = TransformationRepository(session)
            clid_l = ClidManager(objs_l, lin_l)
            version_l = VersionManager(objs_l, clid_l, trans_l)

            src = objs_l.get_by_id(source_id)
            barrier.wait()
            target, _, _ = version_l.derive(src, operation_type="derive")
            session.commit()
            results[name] = ("committed", (target.id, src.clid))
        except Exception as exc:
            session.rollback()
            results[name] = ("failed", type(exc).__name__)
        finally:
            session.close()

    target_ids: list[uuid.UUID] = []
    try:
        t1 = threading.Thread(target=worker, args=("T1",))
        t2 = threading.Thread(target=worker, args=("T2",))
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        outcomes = [results.get("T1"), results.get("T2")]
        committed = [o for o in outcomes if o is not None and o[0] == "committed"]

        # ambas as transformações podem legitimamente commitar (cada
        # uma cria seu PRÓPRIO target, sem conflito de PK entre elas)
        assert len(committed) >= 1, f"esperado ao menos 1 commit, obtido: {outcomes}"

        clids_seen = {c[1] for _, c in committed}
        # nenhuma corrupção: todas as transformações que commitaram
        # enxergam exatamente o mesmo CLID de source (nunca dois CLIDs
        # diferentes atribuídos a source)
        assert len(clids_seen) == 1, f"CLID de source divergiu entre threads: {clids_seen}"

        target_ids = [c[0] for _, c in committed]

        with UnitOfWork() as uow:
            objs, lin, trans, clid, version = _make_managers(uow.session)
            final_source = objs.get_by_id(source_id)
            assert final_source.clid == list(clids_seen)[0]
            for tid in target_ids:
                target = objs.get_by_id(tid)
                assert target is not None
                assert target.clid == final_source.clid
    finally:
        with UnitOfWork() as uow:
            objs, lin, trans, clid, version = _make_managers(uow.session)
            uow.session.execute(
                sa.text("DELETE FROM transformation_records WHERE input_refs::text LIKE :pattern"),
                {"pattern": f"%{source_id}%"},
            )
            uow.session.execute(
                sa.text("DELETE FROM lineage_edges WHERE parent_coid = :s"), {"s": str(source_id)}
            )
            for tid in target_ids:
                leftover = objs.get_by_id(tid, include_deleted=True)
                if leftover is not None:
                    objs.delete(leftover)
            leftover_source = objs.get_by_id(source_id, include_deleted=True)
            if leftover_source is not None:
                objs.delete(leftover_source)
            uow.commit()


def test_rc_concurrent_revise_on_same_current_does_not_leave_two_current():
    """RC1-RC4 (correção E3.4.0): duas threads reais, duas sessões/
    conexões distintas, ambas chamando `revise()` a partir do MESMO
    `source` (`CURRENT`) simultaneamente. Reutiliza a proteção de
    E3.3.1 (`refresh_for_update` dentro de `revise()`, sobre `source`).

    Esperado: exatamente uma transação commita (a que adquire o lock
    primeiro e vê `source.revision_status == CURRENT`); a outra
    bloqueia, ao continuar vê `source.revision_status == SUPERSEDED`
    (já transicionado pela primeira) e é corretamente rejeitada por
    `RevisionStatusInvalidTransitionError` — nunca dois `CURRENT`
    simultâneos, nunca last-write-wins silencioso.
    """
    from app.database.engine import engine

    SessionFactory = sessionmaker(
        bind=engine, autocommit=False, autoflush=False, expire_on_commit=False
    )

    with UnitOfWork() as uow:
        objs, lin, trans, clid, version = _make_managers(uow.session)
        source = objs.add(CognitiveObject())
        uow.commit()
        source_id = source.id

    with UnitOfWork() as uow:
        objs, lin, trans, clid, version = _make_managers(uow.session)
        src = objs.get_by_id(source_id)
        src.revision_status = "current"
        objs.update(src)
        uow.commit()

    results: dict[str, tuple[str, object]] = {}
    barrier = threading.Barrier(2)

    def worker(name: str) -> None:
        session = SessionFactory()
        try:
            objs_l = ObjectRepository(session)
            lin_l = LineageRepository(session)
            trans_l = TransformationRepository(session)
            clid_l = ClidManager(objs_l, lin_l)
            version_l = VersionManager(objs_l, clid_l, trans_l)

            src = objs_l.get_by_id(source_id)
            barrier.wait()
            target, _, _ = version_l.revise(src, operation_type="revise")
            session.commit()
            results[name] = ("committed", target.id)
        except Exception as exc:
            session.rollback()
            results[name] = ("failed", type(exc).__name__)
        finally:
            session.close()

    target_ids: list[uuid.UUID] = []
    try:
        t1 = threading.Thread(target=worker, args=("T1",))
        t2 = threading.Thread(target=worker, args=("T2",))
        t1.start()
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        outcomes = [results.get("T1"), results.get("T2")]
        committed = [o for o in outcomes if o is not None and o[0] == "committed"]
        rejected = [o for o in outcomes if o is not None and o[0] == "failed"]

        # RC1/RC2: nunca duas transações commitam uma revisão
        assert len(committed) == 1, f"esperado exatamente 1 commit, obtido: {outcomes}"
        # RC3: a outra é controlada (rejeitada), não ignorada
        assert len(rejected) == 1, f"esperado exatamente 1 rejeição, obtido: {outcomes}"
        assert rejected[0][1] == "RevisionStatusInvalidTransitionError"

        target_ids = [committed[0][1]]

        # RC4: estado final consistente — exatamente 1 CURRENT
        with UnitOfWork() as uow:
            objs, lin, trans, clid, version = _make_managers(uow.session)
            all_objects = [objs.get_by_id(source_id)] + [objs.get_by_id(t) for t in target_ids]
            currents = [o for o in all_objects if o is not None and o.revision_status == "current"]
            supersededs = [
                o for o in all_objects if o is not None and o.revision_status == "superseded"
            ]
            assert len(currents) == 1
            assert len(supersededs) == 1
            assert currents[0].id == target_ids[0]
            assert supersededs[0].id == source_id
    finally:
        with UnitOfWork() as uow:
            objs, lin, trans, clid, version = _make_managers(uow.session)
            uow.session.execute(
                sa.text("DELETE FROM transformation_records WHERE input_refs::text LIKE :pattern"),
                {"pattern": f"%{source_id}%"},
            )
            uow.session.execute(
                sa.text("DELETE FROM lineage_edges WHERE parent_coid = :s"), {"s": str(source_id)}
            )
            for tid in target_ids:
                leftover = objs.get_by_id(tid, include_deleted=True)
                if leftover is not None:
                    objs.delete(leftover)
            leftover_source = objs.get_by_id(source_id, include_deleted=True)
            if leftover_source is not None:
                objs.delete(leftover_source)
            uow.commit()
