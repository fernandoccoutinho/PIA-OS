"""
Testes de integração de `E3.11`/`LIB-11` — Synchronization Manager,
contra PostgreSQL real.

O round-trip precisa de dois patrimônios independentes. Em vez de
simular, este arquivo usa **dois bancos PostgreSQL de verdade** —
`instance A` (o banco de teste corrente) e `instance B` (um banco
descartável criado pela fixture, com o mesmo schema aplicado por
Alembic). É a única forma honesta de provar
`EXPORT(A) → IMPORT(B)`: transmitir entre instâncias, não entre
transações da mesma.

Executa Alembic in-process; o isolamento de logging de `E3.6.1d` vem da
fixture autouse de `conftest.py` deste diretório.
"""

from __future__ import annotations

import threading
import uuid
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session, sessionmaker

from app.cognitive.models.cognitive_object import CognitiveObject
from app.cognitive.models.enums import (
    AccessibilityState,
    CausalEventType,
    LineageRelation,
    ProvenanceActorType,
    ProvenanceSourceType,
    RelationshipType,
    RevisionStatus,
    TransformationKind,
)
from app.cognitive.models.transformation_record import TransformationRecord
from app.cognitive.repositories.causal_history_repository import CausalHistoryRepository
from app.cognitive.repositories.index_repository import IndexRepository
from app.cognitive.repositories.integrity_repository import IntegrityRepository
from app.cognitive.repositories.lineage_repository import LineageRepository
from app.cognitive.repositories.object_repository import ObjectRepository
from app.cognitive.repositories.provenance_repository import ProvenanceRepository
from app.cognitive.repositories.relationship_repository import RelationshipRepository
from app.cognitive.repositories.search_repository import SearchRepository
from app.cognitive.repositories.sync_repository import SyncRepository
from app.cognitive.schemas.integrity import IntegrityStatus
from app.cognitive.schemas.search_criteria import SearchCriteria
from app.cognitive.schemas.synchronization import (
    SECTION_BY_TABLE,
    SYNC_FORMAT,
    SYNC_SCHEMA_VERSION,
    SyncStatus,
    canonical_payload,
)
from app.cognitive.services.causal_history_manager import CausalHistoryManager
from app.cognitive.services.index_manager import IndexManager
from app.cognitive.services.integrity_manager import IntegrityManager
from app.cognitive.services.provenance_manager import ProvenanceManager
from app.cognitive.services.search_engine import SearchEngine
from app.cognitive.services.synchronization_manager import SynchronizationManager
from app.database import migrations
from app.database.engine import engine
from app.database.health import check_database_health
from app.repositories.unit_of_work import UnitOfWork

_ALL_TABLES = (
    "causal_history_events",
    "causal_histories",
    "provenance_records",
    "relationships",
    "lineage_edges",
    "transformation_records",
    "cognitive_objects",
)

_INSTANCE_B_DATABASE = "piaos_sync_b_test"


def _available() -> bool:
    return check_database_health().available


pytestmark = pytest.mark.skipif(
    not _available(), reason="PostgreSQL real indisponível — E3.11 exige duas instâncias reais."
)


@pytest.fixture(autouse=True)
def _clean_instance_a():
    migrations.upgrade("head")
    _truncate(engine)
    yield
    _truncate(engine)


def _truncate(target: sa.Engine) -> None:
    with target.begin() as conn:
        conn.execute(sa.text(f"TRUNCATE {', '.join(_ALL_TABLES)} CASCADE"))


@pytest.fixture
def instance_b():
    """Segunda instância PIA-OS: banco próprio, schema criado a partir
    dos mesmos modelos.

    Um banco separado, e não um schema separado: o objetivo é provar
    transmissão **entre instâncias**, com identidade preservada de um
    lado ao outro.
    """
    admin_url = engine.url.set(database="postgres")
    admin = sa.create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(sa.text(f'DROP DATABASE IF EXISTS "{_INSTANCE_B_DATABASE}"'))
        conn.execute(sa.text(f'CREATE DATABASE "{_INSTANCE_B_DATABASE}"'))
    admin.dispose()

    target = sa.create_engine(engine.url.set(database=_INSTANCE_B_DATABASE))
    import app.cognitive.models  # noqa: F401
    from app.database.base import Base

    Base.metadata.create_all(
        target, tables=[Base.metadata.tables[name] for name in SECTION_BY_TABLE]
    )
    factory = sessionmaker(bind=target, autocommit=False, autoflush=False, expire_on_commit=False)
    try:
        yield factory
    finally:
        target.dispose()
        admin = sa.create_engine(admin_url, isolation_level="AUTOCOMMIT")
        with admin.connect() as conn:
            conn.execute(
                sa.text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                    "WHERE datname = :d AND pid <> pg_backend_pid()"
                ),
                {"d": _INSTANCE_B_DATABASE},
            )
            conn.execute(sa.text(f'DROP DATABASE IF EXISTS "{_INSTANCE_B_DATABASE}"'))
        admin.dispose()


def _seed_full_patrimony() -> dict[str, uuid.UUID]:
    """Patrimônio amplo, exigido pelo gate COUT (§26): múltiplos COIDs,
    CLIDs compartilhados e distintos, `CURRENT` + `SUPERSEDED`,
    provenance, transformações, linhagem com ramificação e merge,
    relações (inclusive uma retirada), os quatro estados de
    acessibilidade, histórias causais, predecessor entre histórias e
    múltiplos caminhos causais."""
    refs: dict[str, uuid.UUID] = {}
    with UnitOfWork() as uow:
        objects = ObjectRepository(uow.session)
        clid = uuid.uuid4()
        superseded = objects.add(
            CognitiveObject(
                clid=clid,
                revision_status=RevisionStatus.SUPERSEDED,
                accessibility=AccessibilityState.LATENT,
            )
        )
        current = objects.add(
            CognitiveObject(
                clid=clid,
                revision_status=RevisionStatus.CURRENT,
                accessibility=AccessibilityState.ACTIVE,
            )
        )
        branch = objects.add(
            CognitiveObject(clid=uuid.uuid4(), accessibility=AccessibilityState.INACCESSIBLE)
        )
        extinct = objects.add(CognitiveObject(accessibility=AccessibilityState.CAUSALLY_EXTINCT))
        uow.session.flush()

        lineage = LineageRepository(uow.session)
        lineage.add_edge(
            parent_coid=superseded.id,
            child_coid=current.id,
            relation_type=LineageRelation.DERIVED_FROM,
        )
        lineage.add_edge(
            parent_coid=current.id, child_coid=branch.id, relation_type=LineageRelation.BRANCH
        )
        lineage.add_edge(
            parent_coid=branch.id, child_coid=extinct.id, relation_type=LineageRelation.MERGE
        )

        provenance_manager = ProvenanceManager(ProvenanceRepository(uow.session))
        human = provenance_manager.record(
            coid=current.id,
            source_type=ProvenanceSourceType.HUMAN,
            actor_type=ProvenanceActorType.HUMAN,
            trace_id="trace-humano",
        )
        provenance_manager.record(
            coid=current.id,
            source_type=ProvenanceSourceType.AGENT,
            actor_type=ProvenanceActorType.AGENT,
            provider_id="provider-a",
            model_id="model-1",
            trace_id="trace-agente",
        )
        provenance_manager.record(
            coid=branch.id,
            source_type=ProvenanceSourceType.AGENT,
            actor_type=ProvenanceActorType.AGENT,
            provider_id="provider-b",
            trace_id="trace-agente",
        )
        uow.session.flush()

        uow.session.add(
            TransformationRecord(
                operation_type="revise",
                transformation_kind=TransformationKind.REVISION,
                input_refs=[str(superseded.id)],
                output_refs=[str(current.id)],
                actor_ref=human.id,
                policy_ref="policy://none",
                declared_preservations=["identidade"],
                declared_losses=["formatação"],
            )
        )

        relationships = RelationshipRepository(uow.session)
        relationships.add_relationship(
            source_coid=current.id,
            target_coid=branch.id,
            relationship_type=RelationshipType.RELATED_TO,
        )
        relationships.add_relationship(
            source_coid=current.id,
            target_coid=branch.id,
            relationship_type=RelationshipType.CONTRADICTS,
        )
        retired = relationships.add_relationship(
            source_coid=branch.id,
            target_coid=extinct.id,
            relationship_type=RelationshipType.REFERENCES,
        )
        uow.session.flush()
        relationships.retire(retired)

        causal = CausalHistoryManager(CausalHistoryRepository(uow.session))
        origin = causal.record(
            subject_coid=superseded.id,
            event_type=CausalEventType.CREATED,
            actor_ref=human.id,
            payload_ref="ref://origem",
            occurred_at=datetime(1998, 5, 1, tzinfo=UTC),
        )
        path_a = causal.record(
            subject_coid=current.id, event_type=CausalEventType.ACCESSED, predecessor=origin
        )
        causal.record(
            subject_coid=branch.id, event_type=CausalEventType.COMPARED, predecessor=origin
        )
        causal.record(
            subject_coid=extinct.id, event_type=CausalEventType.TRANSFORMED, predecessor=path_a
        )
        uow.commit()

        refs = {
            "clid": clid,
            "superseded": superseded.id,
            "current": current.id,
            "branch": branch.id,
            "extinct": extinct.id,
            "origin_event": origin.id,
        }
    return refs


def _export_from_a() -> dict:
    with UnitOfWork() as uow:
        return SynchronizationManager(SyncRepository(uow.session)).export_package()


def _export_from(session: Session) -> dict:
    return SynchronizationManager(SyncRepository(session)).export_package()


def _import_into(session: Session, package: dict):
    report = SynchronizationManager(SyncRepository(session)).import_package(package)
    session.commit()
    return report


def test_sy1_package_is_versioned_and_deterministic():
    """S1/S2 — envelope versionado e export determinístico: exportar
    duas vezes o mesmo patrimônio produz pacotes canonicamente
    idênticos (só `exported_at` difere, e é transportacional)."""
    _seed_full_patrimony()

    first = _export_from_a()
    second = _export_from_a()

    assert first["format"] == SYNC_FORMAT
    assert first["schema_version"] == SYNC_SCHEMA_VERSION
    assert canonical_payload(first) == canonical_payload(second)
    assert first["exported_at"] != "" and "exported_at" not in canonical_payload(first)


def test_sy2_round_trip_preserves_the_whole_patrimony(instance_b):
    """S3-S16 + §26 — gate COUT central: `EXPORT(A) → IMPORT(B vazio)`
    e `canonical(P_A) == canonical(P_B)`.

    Preserva identidade (COID), continuidade (CLID), provenance,
    linhagem, relações, transformações, história causal e
    accessibility — sem regenerar um único identificador.
    """
    refs = _seed_full_patrimony()
    package = _export_from_a()

    session = instance_b()
    try:
        report = _import_into(session, package)
        assert report.status is SyncStatus.APPLIED
        assert report.overwrite_count == 0
        assert report.applied_count > 0

        exported_from_b = _export_from(session)
    finally:
        session.close()

    assert canonical_payload(package) == canonical_payload(exported_from_b)

    # Identidade e continuidade explicitamente, além da igualdade canônica.
    ids_a = {row["id"] for row in package["objects"]}
    ids_b = {row["id"] for row in exported_from_b["objects"]}
    assert ids_a == ids_b
    assert str(refs["current"]) in ids_b
    clids = {row["clid"] for row in exported_from_b["objects"] if row["clid"]}
    assert str(refs["clid"]) in clids


def test_sy3_import_is_idempotent(instance_b):
    """S17/S18 — importar o mesmo pacote duas vezes não duplica nada:
    o segundo import não aplica registro algum e não gera conflito.

    `same ID + same representation → idempotente`.
    """
    _seed_full_patrimony()
    package = _export_from_a()

    session = instance_b()
    try:
        first = _import_into(session, package)
        census_1 = _census(session)
        second = _import_into(session, package)
        census_2 = _census(session)
    finally:
        session.close()

    assert first.status is SyncStatus.APPLIED
    assert second.status is SyncStatus.APPLIED
    assert second.applied_count == 0
    assert second.skipped_count == first.applied_count
    assert census_1 == census_2


def _census(session: Session) -> dict[str, int]:
    return {
        table: int(session.execute(sa.text(f"SELECT count(*) FROM {table}")).scalar_one())
        for table in _ALL_TABLES
    }


def test_sy4_divergent_state_produces_explicit_conflict_without_overwriting(instance_b):
    """S19-S21 + §26 — mesmo id, estado divergente: **conflito
    explícito**, zero sobrescrita, zero resolução silenciosa.

    E o destino permanece exatamente como estava: nenhum lado "vence".
    """
    refs = _seed_full_patrimony()
    package = _export_from_a()

    session = instance_b()
    try:
        _import_into(session, package)

        # Divergência deliberada em B, para um id que já existe.
        session.execute(
            sa.text("UPDATE cognitive_objects SET accessibility = 'latent' WHERE id = :i"),
            {"i": refs["current"]},
        )
        session.commit()
        before = _snapshot(session)

        report = SynchronizationManager(SyncRepository(session)).import_package(package)
        session.rollback()
        after = _snapshot(session)
    finally:
        session.close()

    assert report.status is SyncStatus.CONFLICT
    assert report.overwrite_count == 0
    assert report.applied == {}
    (conflict,) = [c for c in report.conflicts if c.entity_id == refs["current"]]
    assert conflict.section == "objects"
    assert "accessibility" in conflict.differing_fields
    # As duas representações continuam legíveis no relatório — nenhuma
    # das duas é apagada do diagnóstico.
    assert conflict.incoming["accessibility"] == "active"
    assert conflict.existing["accessibility"] == "latent"
    assert after == before


def _snapshot(session: Session) -> dict[str, list[tuple]]:
    return {
        table: [
            tuple(row)
            for row in session.execute(sa.text(f"SELECT * FROM {table} ORDER BY id")).all()
        ]
        for table in _ALL_TABLES
    }


def test_sy5_conflict_aborts_the_whole_import(instance_b):
    """S22 + §10 — atomicidade: havendo conflito, **nada** é aplicado,
    nem os registros que estavam perfeitamente válidos.

    Import parcial deixaria linhagem incompleta, provenance pela metade
    ou eventos causais órfãos.
    """
    refs = _seed_full_patrimony()
    package = _export_from_a()

    session = instance_b()
    try:
        # B recebe só um dos objetos, com estado divergente.
        session.execute(
            sa.text(
                "INSERT INTO cognitive_objects (id, accessibility, created_at, updated_at) "
                "VALUES (:i, 'inaccessible', now(), now())"
            ),
            {"i": refs["current"]},
        )
        session.commit()

        report = SynchronizationManager(SyncRepository(session)).import_package(package)
        session.rollback()
        census = _census(session)
    finally:
        session.close()

    assert report.status is SyncStatus.CONFLICT
    assert census["cognitive_objects"] == 1  # só o que já estava lá
    assert census["lineage_edges"] == 0
    assert census["provenance_records"] == 0
    assert census["causal_history_events"] == 0


def test_sy6_galaxy_trace_and_cross_history_survive_the_round_trip(instance_b):
    """S24/S25/S26 — Galaxy Trace: múltiplos caminhos causais e
    predecessor entre histórias sobrevivem intactos.

    Nenhuma trajetória é colapsada, e nenhuma aresta causal é inferida
    de timestamp — o predecessor explícito é o que viaja.
    """
    refs = _seed_full_patrimony()
    package = _export_from_a()

    session = instance_b()
    try:
        _import_into(session, package)
        events = session.execute(
            sa.text(
                "SELECT e.id, e.predecessor_event_id, h.subject_coid "
                "FROM causal_history_events e JOIN causal_histories h ON h.id = e.history_id"
            )
        ).all()
    finally:
        session.close()

    successors_of_origin = [
        row for row in events if row[1] is not None and row[1] == refs["origin_event"]
    ]
    subjects = {row[2] for row in successors_of_origin}

    # Dois caminhos distintos a partir da mesma origem, cada um na
    # história do seu próprio sujeito.
    assert len(successors_of_origin) == 2
    assert len(subjects) == 2
    assert refs["superseded"] not in subjects  # a origem é do superseded
    assert len(events) == 4


def test_sy7_broken_glass_history_survives_extinct_distinction(instance_b):
    """S27 — Broken Glass: o sujeito chega em `CAUSALLY_EXTINCT` e a
    história dele chega junto.

    `DISTINCTION_EXTINCTION != HISTORICAL_ERASURE`.
    """
    refs = _seed_full_patrimony()
    package = _export_from_a()

    session = instance_b()
    try:
        _import_into(session, package)
        state = session.execute(
            sa.text("SELECT accessibility FROM cognitive_objects WHERE id = :i"),
            {"i": refs["extinct"]},
        ).scalar_one()
        events = session.execute(
            sa.text(
                "SELECT count(*) FROM causal_history_events e "
                "JOIN causal_histories h ON h.id = e.history_id WHERE h.subject_coid = :i"
            ),
            {"i": refs["extinct"]},
        ).scalar_one()
    finally:
        session.close()

    assert state == "causally_extinct"
    assert events == 1


def test_sy8_absence_in_the_package_never_becomes_extinction(instance_b):
    """S28 + §14 — não-fabricação: um pacote que não menciona um objeto
    do destino **não** o altera, não o marca `CAUSALLY_EXTINCT` e não
    inventa história para ele.

    `NO TRACE != AUTHORIZATION TO FABRICATE HISTORY`.
    """
    package = _export_from_a()  # patrimônio vazio em A

    session = instance_b()
    try:
        native_id = uuid.uuid4()
        session.execute(
            sa.text(
                "INSERT INTO cognitive_objects (id, accessibility, created_at, updated_at) "
                "VALUES (:i, 'active', now(), now())"
            ),
            {"i": native_id},
        )
        session.commit()
        before = _snapshot(session)

        report = _import_into(session, package)
        after = _snapshot(session)
    finally:
        session.close()

    assert report.status is SyncStatus.APPLIED
    assert report.applied_count == 0
    assert after == before


def test_sy9_integrity_search_and_index_work_after_import(instance_b):
    """S29/S30/S31 — depois de um import válido: `IntegrityManager`
    audita `PASS`, `SearchEngine` recupera o patrimônio pelos mesmos
    critérios de antes, e o índice continua derivado (nenhuma tabela de
    índice/busca foi criada)."""
    refs = _seed_full_patrimony()
    package = _export_from_a()

    session = instance_b()
    try:
        _import_into(session, package)

        report = IntegrityManager(IntegrityRepository(session)).audit()
        search = SearchEngine(SearchRepository(session))
        by_clid = search.search(SearchCriteria(clid=refs["clid"]))
        by_trace = search.search(SearchCriteria(trace_id="trace-agente"))
        index = IndexManager(ObjectRepository(session), IndexRepository(session))
        located = index.by_coid(refs["current"])

        tables = set(sa.inspect(session.get_bind()).get_table_names())
    finally:
        session.close()

    assert report.status is IntegrityStatus.PASS, report.findings
    assert {o.id for o in by_clid} == {refs["superseded"], refs["current"]}
    assert {o.id for o in by_trace} == {refs["current"], refs["branch"]}
    assert located is not None
    assert not {t for t in tables if "index" in t or "search" in t or "sync" in t}


def test_sy10_provider_neutral_package(instance_b):
    """S32/S33 — o mesmo pacote transporta patrimônio de providers
    diferentes, de humano e de origem sem provider, sem alterar a
    semântica de identidade. E nenhum transcript viaja."""
    _seed_full_patrimony()
    package = _export_from_a()

    providers = {row["provider_id"] for row in package["provenance"]}
    assert providers == {"provider-a", "provider-b", None}

    session = instance_b()
    try:
        _import_into(session, package)
        rows = session.execute(
            sa.text("SELECT provider_id, model_id, actor_type FROM provenance_records")
        ).all()
    finally:
        session.close()

    assert {row[0] for row in rows} == {"provider-a", "provider-b", None}
    assert {row[1] for row in rows} == {"model-1", None}
    # Nenhuma seção do pacote carrega conteúdo/transcript.
    for section in SECTION_BY_TABLE.values():
        for row in package[section]:
            assert not {k for k in row if "transcript" in k or "content" in k or "prompt" in k}


def test_sy11_concurrent_imports_do_not_duplicate_patrimony(instance_b):
    """§18 — invariante concorrente real: dois imports simultâneos do
    **mesmo** pacote não podem duplicar patrimônio.

    Nenhum lock foi adicionado: a chave primária já é a autoridade. O
    que se testa é o resultado observável — uma das transações aplica,
    a outra falha ou não aplica nada, e o censo final é exatamente o do
    pacote.
    """
    _seed_full_patrimony()
    package = _export_from_a()
    expected = {section: len(package[section]) for section in SECTION_BY_TABLE.values()}

    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def worker() -> None:
        session = instance_b()
        try:
            manager = SynchronizationManager(SyncRepository(session))
            barrier.wait(timeout=10)
            manager.import_package(package)
            session.commit()
            outcomes.append("applied")
        except Exception:
            session.rollback()
            outcomes.append("rejected")
        finally:
            session.close()

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)

    session = instance_b()
    try:
        census = _census(session)
    finally:
        session.close()

    assert "applied" in outcomes
    assert census["cognitive_objects"] == expected["objects"]
    assert census["causal_history_events"] == expected["causal_events"]
    assert census["provenance_records"] == expected["provenance"]


def test_sy12_malformed_packages_are_rejected_before_writing(instance_b):
    """S23 — pacote malformado é recusado antes de qualquer escrita:
    formato desconhecido, versão não suportada, seção ausente, registro
    sem `id` e campo desconhecido."""
    from app.cognitive.errors.exceptions import SyncPackageInvalidError

    _seed_full_patrimony()
    package = _export_from_a()

    session = instance_b()
    try:
        for broken, _reason in (
            ({**package, "format": "outro"}, "formato"),
            ({**package, "schema_version": "999"}, "versão"),
            ({k: v for k, v in package.items() if k != "objects"}, "seção ausente"),
            ({**package, "objects": [{"clid": None}]}, "sem id"),
            (
                {**package, "objects": [{**package["objects"][0], "campo_novo": 1}]},
                "campo desconhecido",
            ),
        ):
            with pytest.raises(SyncPackageInvalidError):
                SynchronizationManager(SyncRepository(session)).import_package(broken)
            session.rollback()

        census = _census(session)
    finally:
        session.close()

    assert all(count == 0 for count in census.values())
