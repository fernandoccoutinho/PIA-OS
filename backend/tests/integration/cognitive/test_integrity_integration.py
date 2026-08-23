"""
Testes de integração de `E3.10`/`LIB-10` contra PostgreSQL real.

Cobrem o que SQLite não prova:

- o **read-only strong gate** (§49): censo completo do patrimônio,
  listener SQL contando `INSERT`/`UPDATE`/`DELETE`/`TRUNCATE`,
  auditoria executada, censo idêntico depois;
- detecção sobre corrupção **injetada por SQL direto** (§50) — estado
  que as APIs autorizadas impedem, mas que patrimônio legado,
  importado ou manipulado por fora poderia apresentar. A injeção
  acontece exclusivamente em fixture de teste, em banco descartável, e
  não constitui autorização arquitetural de bypass;
- que cenários legítimos sobre patrimônio real não viram falso
  positivo.
"""

import uuid
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from sqlalchemy import event

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
from app.cognitive.repositories.integrity_repository import IntegrityRepository
from app.cognitive.repositories.lineage_repository import LineageRepository
from app.cognitive.repositories.object_repository import ObjectRepository
from app.cognitive.repositories.provenance_repository import ProvenanceRepository
from app.cognitive.repositories.relationship_repository import RelationshipRepository
from app.cognitive.schemas.integrity import IntegrityCode, IntegrityStatus
from app.cognitive.services.causal_history_manager import CausalHistoryManager
from app.cognitive.services.integrity_manager import IntegrityManager
from app.cognitive.services.provenance_manager import ProvenanceManager
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


def _available() -> bool:
    return check_database_health().available


pytestmark = pytest.mark.skipif(
    not _available(), reason="PostgreSQL real indisponível — E3.10 audita patrimônio real."
)


@pytest.fixture(autouse=True)
def _head_and_clean_slate():
    migrations.upgrade("head")
    _truncate()
    yield
    _truncate()


def _truncate() -> None:
    with engine.begin() as conn:
        conn.execute(sa.text(f"TRUNCATE {', '.join(_ALL_TABLES)} CASCADE"))


def _census() -> dict[str, list[tuple]]:
    census: dict[str, list[tuple]] = {}
    with engine.connect() as conn:
        for table in _ALL_TABLES:
            rows = conn.execute(sa.text(f"SELECT * FROM {table} ORDER BY id")).all()
            census[table] = [tuple(row) for row in rows]
    return census


def _seed_rich_patrimony() -> dict[str, uuid.UUID]:
    """Patrimônio amplo e **inteiramente legítimo**: revisões
    `CURRENT`/`SUPERSEDED`, os quatro estados de acessibilidade,
    linhagem em DAG, relações simétricas e contraditórias, relação
    retirada e recriada, proveniência sem provider/model, história
    causal com ramificação e predecessor entre histórias.
    """
    refs: dict[str, uuid.UUID] = {}
    with UnitOfWork() as uow:
        objects = ObjectRepository(uow.session)
        clid = uuid.uuid4()
        superseded = objects.add(
            CognitiveObject(clid=clid, revision_status=RevisionStatus.SUPERSEDED)
        )
        current = objects.add(CognitiveObject(clid=clid, revision_status=RevisionStatus.CURRENT))
        extinct = objects.add(CognitiveObject(accessibility=AccessibilityState.CAUSALLY_EXTINCT))
        latent = objects.add(CognitiveObject(accessibility=AccessibilityState.LATENT))
        uow.session.flush()

        lineage = LineageRepository(uow.session)
        lineage.add_edge(
            parent_coid=superseded.id,
            child_coid=current.id,
            relation_type=LineageRelation.DERIVED_FROM,
        )
        lineage.add_edge(
            parent_coid=current.id, child_coid=latent.id, relation_type=LineageRelation.BRANCH
        )

        relationships = RelationshipRepository(uow.session)
        relationships.add_relationship(
            source_coid=current.id,
            target_coid=latent.id,
            relationship_type=RelationshipType.RELATED_TO,
        )
        relationships.add_relationship(
            source_coid=current.id,
            target_coid=latent.id,
            relationship_type=RelationshipType.SUPPORTS,
        )
        relationships.add_relationship(
            source_coid=current.id,
            target_coid=latent.id,
            relationship_type=RelationshipType.CONTRADICTS,
        )
        retired = relationships.add_relationship(
            source_coid=latent.id,
            target_coid=extinct.id,
            relationship_type=RelationshipType.REFERENCES,
        )
        uow.session.flush()
        relationships.retire(retired)
        relationships.add_relationship(
            source_coid=latent.id,
            target_coid=extinct.id,
            relationship_type=RelationshipType.REFERENCES,
        )

        ProvenanceManager(ProvenanceRepository(uow.session)).record(
            coid=current.id,
            source_type=ProvenanceSourceType.AGENT,
            actor_type=ProvenanceActorType.AGENT,
        )

        causal = CausalHistoryManager(CausalHistoryRepository(uow.session))
        origin = causal.record(
            subject_coid=superseded.id,
            event_type=CausalEventType.CREATED,
            occurred_at=datetime(1998, 5, 1, tzinfo=UTC),
        )
        causal.record(
            subject_coid=current.id, event_type=CausalEventType.ACCESSED, predecessor=origin
        )
        causal.record(
            subject_coid=superseded.id, event_type=CausalEventType.COMPARED, predecessor=origin
        )
        causal.record(subject_coid=extinct.id, event_type=CausalEventType.TRANSFORMED)
        uow.commit()

        refs = {
            "superseded": superseded.id,
            "current": current.id,
            "extinct": extinct.id,
            "latent": latent.id,
            "origin_event": origin.id,
        }
    return refs


def _audit() -> object:
    with UnitOfWork() as uow:
        return IntegrityManager(IntegrityRepository(uow.session)).audit()


def test_ia1_legitimate_patrimony_audits_clean():
    """IA1 (§48) — false-positive gate contra banco real: patrimônio
    amplo e legítimo audita `PASS`.

    Inclui Galaxy Trace (`SUPERSEDED` referenciável enquanto outro é
    `CURRENT`), Broken Glass (`CAUSALLY_EXTINCT` com história
    preservada), `INACCESSIBLE`, ciclo de `Relationship` permitido,
    relações contraditórias, tripla recriada após retirada,
    `provider_id`/`model_id` ausentes, `occurred_at=None`, predecessor
    entre histórias e ramificação causal.
    """
    _seed_rich_patrimony()

    report = _audit()

    assert report.status is IntegrityStatus.PASS, report.findings
    assert report.counts == {}


def test_ia2_audit_is_strictly_read_only():
    """IA2 (§25/§49) — read-only strong gate: censo completo antes,
    listener SQL durante, censo completo depois.

    ```text
    INSERT = UPDATE = DELETE = TRUNCATE = 0
    PATRIMONY_AFTER == PATRIMONY_BEFORE
    ```
    """
    _seed_rich_patrimony()
    before = _census()
    writes: list[str] = []

    @event.listens_for(engine, "before_cursor_execute")
    def _record_writes(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        head = statement.lstrip().split(None, 1)[0].upper() if statement.strip() else ""
        if head in {"INSERT", "UPDATE", "DELETE", "TRUNCATE"}:
            writes.append(head)

    try:
        first = _audit()
        second = _audit()
    finally:
        event.remove(engine, "before_cursor_execute", _record_writes)

    assert writes == [], writes
    assert _census() == before
    assert first.status is IntegrityStatus.PASS
    assert second.status is IntegrityStatus.PASS


def test_ia3_indirect_lineage_cycle_is_detected_with_real_edges():
    """IA3 (§11) — `FULL_DAG`: ciclo indireto de linhagem, criado
    pelas APIs autorizadas (o banco só barra o self-link), é detectado
    com `cycle_path`, `involved_coids` e `involved_edge_ids`."""
    with UnitOfWork() as uow:
        objects = ObjectRepository(uow.session)
        a, b, c = (objects.add(CognitiveObject()) for _ in range(3))
        uow.session.flush()
        lineage = LineageRepository(uow.session)
        lineage.add_edge(parent_coid=a.id, child_coid=b.id, relation_type=LineageRelation.PARENT)
        lineage.add_edge(parent_coid=b.id, child_coid=c.id, relation_type=LineageRelation.PARENT)
        lineage.add_edge(parent_coid=c.id, child_coid=a.id, relation_type=LineageRelation.PARENT)
        uow.commit()
        coids = {str(a.id), str(b.id), str(c.id)}

    report = _audit()

    assert report.status is IntegrityStatus.FAIL
    (finding,) = [f for f in report.findings if f.code is IntegrityCode.LINEAGE_CYCLE]
    assert set(finding.evidence["involved_coids"]) == coids
    assert finding.evidence["cycle_length"] == 3
    assert len(finding.evidence["involved_edge_ids"]) == 3


def test_ia4_injected_causal_cycle_is_detected():
    """IA4 (§13/§50) — corrupção **injetada por SQL direto**: um ciclo
    causal que a API autorizada não consegue produzir (append-only +
    predecessor preexistente) mas que o banco não impede
    (`DB_LEVEL_GLOBAL_DAG_GUARANTEE = FALSE`).

    A injeção é fixture de teste em banco descartável — capacidade
    diagnóstica, não autorização de bypass. E o achado **não** altera
    a classificação de `E3.9.1a`: `INTEGRITY_AUDIT != DB_CONSTRAINT`.
    """
    with UnitOfWork() as uow:
        subject = ObjectRepository(uow.session).add(CognitiveObject())
        uow.session.flush()
        causal = CausalHistoryManager(CausalHistoryRepository(uow.session))
        first = causal.record(subject_coid=subject.id, event_type=CausalEventType.CREATED)
        second = causal.record(
            subject_coid=subject.id, event_type=CausalEventType.TRANSFORMED, predecessor=first
        )
        uow.commit()
        first_id, second_id = first.id, second.id

    assert _audit().status is IntegrityStatus.PASS

    with engine.begin() as conn:
        conn.execute(
            sa.text("UPDATE causal_history_events SET predecessor_event_id = :s WHERE id = :f"),
            {"s": second_id, "f": first_id},
        )

    report = _audit()

    assert report.status is IntegrityStatus.FAIL
    (finding,) = [f for f in report.findings if f.code is IntegrityCode.CAUSAL_CYCLE]
    assert set(finding.evidence["involved_event_ids"]) == {str(first_id), str(second_id)}


def test_ia5_injected_multiple_current_is_detected():
    """IA5 (§17) — `COUNT(CURRENT) <= 1` por CLID auditado mesmo
    havendo índice único no banco: a injeção precisa derrubar o índice
    temporariamente, o que é exatamente o cenário de patrimônio
    restaurado/importado que a auditoria existe para diagnosticar."""
    clid = uuid.uuid4()
    with UnitOfWork() as uow:
        objects = ObjectRepository(uow.session)
        objects.add(CognitiveObject(clid=clid, revision_status=RevisionStatus.CURRENT))
        uow.commit()

    with engine.begin() as conn:
        conn.execute(sa.text("DROP INDEX uq_cognitive_objects_one_current_per_clid"))
        conn.execute(
            sa.text(
                "INSERT INTO cognitive_objects "
                "(id, clid, accessibility, revision_status, created_at, updated_at) "
                "VALUES (gen_random_uuid(), :c, 'active', 'current', now(), now())"
            ),
            {"c": clid},
        )
    try:
        report = _audit()
    finally:
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "DELETE FROM cognitive_objects WHERE clid = :c AND revision_status='current'"
                ),
                {"c": clid},
            )
            conn.execute(
                sa.text(
                    "CREATE UNIQUE INDEX uq_cognitive_objects_one_current_per_clid "
                    "ON cognitive_objects (clid) WHERE revision_status = 'current'"
                )
            )

    assert report.status is IntegrityStatus.FAIL
    (finding,) = [
        f for f in report.findings if f.code is IntegrityCode.VERSION_MULTIPLE_CURRENT_PER_CLID
    ]
    assert finding.evidence["clids"] == [{"clid": str(clid), "current_count": 2}]


def test_ia6_empty_patrimony_audits_clean():
    """IA6 — patrimônio vazio é `PASS`: ausência de dado não é
    corrupção (`NOT_FOUND != NEVER_EXISTED` vale nos dois sentidos)."""
    report = _audit()

    assert report.status is IntegrityStatus.PASS
    assert report.findings == ()


def test_ia7_audit_creates_no_tables_and_stores_nothing():
    """IA7 (§43) — nenhuma persistência: o conjunto de tabelas é o
    mesmo de `E3.9`, sem tabela de finding, report, audit ou
    conformance."""
    _seed_rich_patrimony()
    _audit()

    tables = set(sa.inspect(engine).get_table_names())

    # ATUALIZADO PELA E7.3: `audit_opinions` é parecer de ORQUESTRAÇÃO,
    # produzido por autoridade própria e autorizado pelo addendum R1. O que
    # esta guarda protege é a auditoria de INTEGRIDADE da E3 não persistir
    # nada — e isso segue valendo. Casar por substring "audit" alcançaria
    # qualquer tabela futura com esse nome, o que é falso positivo.
    _AUDITORIA_DE_ORQUESTRACAO = {"audit_opinions"}
    assert not {
        t
        for t in tables - _AUDITORIA_DE_ORQUESTRACAO
        if "integrity" in t or "finding" in t or "audit" in t or "conform" in t
    }
    assert tables >= set(_ALL_TABLES)


def test_ia8_transformation_dangling_actor_ref_is_detected_on_postgres():
    """IA8 (`E3.10.1`) — `TransformationRecord.actor_ref` sem FK: um
    valor que não resolve para `ProvenanceRecord` é fisicamente
    gravável e a auditoria o encontra. `actor_ref` nulo e `actor_ref`
    resolvível continuam `PASS`."""
    with UnitOfWork() as uow:
        subject = ObjectRepository(uow.session).add(CognitiveObject())
        uow.session.flush()
        provenance = ProvenanceManager(ProvenanceRepository(uow.session)).record(
            coid=subject.id,
            source_type=ProvenanceSourceType.HUMAN,
            actor_type=ProvenanceActorType.HUMAN,
        )
        uow.session.flush()
        uow.session.add(
            TransformationRecord(
                operation_type="revise",
                transformation_kind=TransformationKind.REVISION,
                input_refs=[str(subject.id)],
                output_refs=[str(subject.id)],
                actor_ref=provenance.id,
            )
        )
        uow.session.add(
            TransformationRecord(
                operation_type="derive",
                transformation_kind=TransformationKind.DERIVATION,
                input_refs=[],
                output_refs=[],
            )
        )
        uow.commit()

    assert _audit().status is IntegrityStatus.PASS

    with UnitOfWork() as uow:
        orphan = TransformationRecord(
            operation_type="derive",
            transformation_kind=TransformationKind.DERIVATION,
            input_refs=[str(uuid.uuid4())],
            output_refs=[],
            actor_ref=uuid.uuid4(),
        )
        uow.session.add(orphan)
        uow.commit()
        orphan_id = orphan.id

    report = _audit()

    assert report.status is IntegrityStatus.FAIL
    (finding,) = [
        f for f in report.findings if f.code is IntegrityCode.TRANSFORMATION_DANGLING_ACTOR_REF
    ]
    assert finding.entity_refs == (orphan_id,)


def test_ia9_invalid_accessibility_value_is_detected_on_postgres():
    """IA9 (`E3.10.1`) — a coluna `accessibility` é `VARCHAR` sem
    `CHECK` no PostgreSQL, então um valor fora do vocabulário é
    gravável por SQL direto. A auditoria o diagnostica sem que o ORM
    precise carregar a entidade corrompida."""
    with UnitOfWork() as uow:
        objects = ObjectRepository(uow.session)
        for state in AccessibilityState:
            objects.add(CognitiveObject(accessibility=state))
        uow.commit()

    assert _audit().status is IntegrityStatus.PASS

    with engine.begin() as conn:
        corrupted = conn.execute(
            sa.text(
                "UPDATE cognitive_objects SET accessibility = 'unknown_state' "
                "WHERE accessibility = 'latent' RETURNING id"
            )
        ).scalar_one()

    report = _audit()

    assert report.status is IntegrityStatus.FAIL
    (finding,) = [
        f for f in report.findings if f.code is IntegrityCode.IDENTITY_INVALID_ACCESSIBILITY_STATE
    ]
    assert finding.evidence["invalid_states"] == [
        {"coid": str(corrupted), "accessibility": "unknown_state"}
    ]
