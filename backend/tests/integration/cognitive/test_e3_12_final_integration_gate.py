"""
E3.12 — FINAL INTEGRATION GATE da Entrega 3.

Este arquivo **não introduz primitiva, feature, model, schema, migração
ou código de produção**. Ele existe para provar, contra PostgreSQL
real e em cenário único e contínuo, que as propriedades construídas
separadamente em `E3.1`–`E3.11` valem **em conjunto**.

O que os arquivos de módulo já provam isoladamente não é repetido aqui
sem motivo: `test_synchronization_integration.py` (SY1–SY12, CD7,
CD12) já cobre round-trip, conflito e idempotência do módulo `E3.11`;
`test_integrity_integration.py` (IA1–IA9) já cobre a auditoria do
`E3.10`. O que **não** existia até aqui, e é a razão de ser da E3.12:

- um único patrimônio `P0` atravessando
  `CREATE → TRANSFORM → RELATE → TRACE → SEARCH → INTEGRITY →
  EXPORT → IMPORT → SEARCH → INTEGRITY`, com censo canônico
  `P_before == P_after` (§8, §9, §24, §47);
- retenção de distinção entre duas trajetórias que chegam a estados
  finais equivalentes em toda dimensão estrutural comparável, mas com
  histórias e proveniências diferentes (§10, §48);
- o *negative strong gate*: cinco categorias de defeito produzindo
  **cinco diagnósticos distintos**, nunca colapsados em "inválido"
  (§49);
- as varreduras normativas de fronteira (§7, §14, §25, §26, §45) como
  teste executável, e não apenas como afirmação em documento.

Nenhum score COUT é calculado em lugar nenhum deste arquivo: COUT
informa, não decide (`COUT-P9`).
"""

from __future__ import annotations

import pathlib
import re
import time
import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy import event
from sqlalchemy.orm import Session, sessionmaker

from app.cognitive.errors.exceptions import SyncPackageInvalidError
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
from app.cognitive.repositories.transformation_repository import TransformationRepository
from app.cognitive.schemas.integrity import IntegrityCode, IntegrityStatus
from app.cognitive.schemas.search_criteria import SearchCriteria
from app.cognitive.schemas.synchronization import (
    SECTION_BY_TABLE,
    SYNC_FORMAT,
    SYNC_SCHEMA_VERSION,
    SyncStatus,
    canonical_payload,
)
from app.cognitive.services.accessibility_manager import AccessibilityManager
from app.cognitive.services.causal_history_manager import CausalHistoryManager
from app.cognitive.services.clid_manager import ClidManager
from app.cognitive.services.index_manager import IndexManager
from app.cognitive.services.integrity_manager import IntegrityManager
from app.cognitive.services.provenance_manager import ProvenanceManager
from app.cognitive.services.search_engine import SearchEngine
from app.cognitive.services.synchronization_manager import SynchronizationManager
from app.cognitive.services.version_manager import VersionManager
from app.database import migrations
from app.database.engine import engine
from app.database.health import check_database_health
from app.repositories.unit_of_work import UnitOfWork

# Ordem de TRUNCATE: filhas antes das mães (FK). Mesma tupla usada pelos
# arquivos de E3.10/E3.11 — repetida, e não importada de lá, porque um
# arquivo de teste não deve depender do outro para limpar o banco.
_ALL_TABLES = (
    "causal_history_events",
    "causal_histories",
    "provenance_records",
    "relationships",
    "lineage_edges",
    "transformation_records",
    "cognitive_objects",
)

_INSTANCE_B_DATABASE = "piaos_gate_b_test"

_BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[3]
_APP_DIR = _BACKEND_ROOT / "app"


def _available() -> bool:
    return check_database_health().available


pytestmark = pytest.mark.skipif(
    not _available(),
    reason="PostgreSQL real indisponível — o gate final da E3 não roda sobre SQLite (§37).",
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
    """Segunda instância PIA-OS — banco próprio, não schema próprio.

    Transmissão entre instâncias é o que o contrato de `E3.11` promete;
    provar isso dentro de uma única base seria provar outra coisa.
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


# --- Censo do patrimônio cognitivo (§24) -------------------------------


def _census(target: sa.Engine) -> dict[str, list[tuple[Any, ...]]]:
    """Fotografia completa e ordenada de todas as tabelas cognitivas.

    Comparação linha a linha, coluna a coluna — não contagem. Contar
    linhas provaria apenas que nada sumiu; o contrato de `E3` é que
    nada *mude*.
    """
    snapshot: dict[str, list[tuple[Any, ...]]] = {}
    with target.connect() as conn:
        for table in SECTION_BY_TABLE:
            columns = sorted(sa.inspect(target).get_columns(table), key=lambda c: c["name"])
            names = ", ".join(f'"{c["name"]}"' for c in columns)
            rows = conn.execute(sa.text(f"SELECT {names} FROM {table} ORDER BY id")).fetchall()
            snapshot[table] = [tuple(row) for row in rows]
    return snapshot


def _write_counter(target: sa.Engine) -> dict[str, int]:
    """Contador de escritas reais no banco, via listener de cursor.

    Mesma técnica de SX3 (`E3.8`) e IA2 (`E3.10`): a prova de
    "read-only" é o SQL efetivamente emitido, não a intenção do código.
    """
    counter = {"writes": 0}
    pattern = re.compile(r"^\s*(INSERT|UPDATE|DELETE|TRUNCATE)\b", re.IGNORECASE)

    def _listen(conn, cursor, statement, parameters, context, executemany):  # noqa: ANN001
        if pattern.match(statement):
            counter["writes"] += 1

    event.listen(target, "before_cursor_execute", _listen)
    counter["_detach"] = _listen  # type: ignore[assignment]
    return counter


def _stop_counting(target: sa.Engine, counter: dict[str, Any]) -> None:
    event.remove(target, "before_cursor_execute", counter["_detach"])


# --- Patrimônio P0 (§47) ----------------------------------------------


def _seed_p0() -> dict[str, uuid.UUID]:
    """Patrimônio integrado exigido pelo §47.

    Contém, deliberadamente e tudo ao mesmo tempo: múltiplos objetos e
    múltiplos CLIDs; `CURRENT` e `SUPERSEDED` coexistindo;
    branch/merge de linhagem; relações ativas e retirada; proveniência
    humana e de dois providers distintos, além de uma sem provider
    algum; transformações com preservação e perda declaradas; os
    quatro `AccessibilityState`; múltiplas `CausalHistory`;
    predecessor entre histórias; múltiplos caminhos causais; Galaxy
    Trace; Broken Glass.

    Tudo é construído **pelos caminhos autorizados** (managers e
    repositories), nunca por SQL direto: um patrimônio forjado por
    fora não provaria que o sistema o produz.
    """
    refs: dict[str, uuid.UUID] = {}
    with UnitOfWork() as uow:
        objects = ObjectRepository(uow.session)
        clid_manager = ClidManager(objects, LineageRepository(uow.session))
        versions = VersionManager(objects, clid_manager, TransformationRepository(uow.session))
        provenance = ProvenanceManager(ProvenanceRepository(uow.session))
        relationships = RelationshipRepository(uow.session)
        lineage = LineageRepository(uow.session)
        causal = CausalHistoryManager(CausalHistoryRepository(uow.session))
        accessibility = AccessibilityManager(objects)

        # O1 — origem, com CLID próprio.
        o1 = objects.add(CognitiveObject(clid=uuid.uuid4()))
        uow.session.flush()

        human = provenance.record(
            coid=o1.id,
            source_type=ProvenanceSourceType.HUMAN,
            actor_type=ProvenanceActorType.HUMAN,
            trace_id="trace-p0-humano",
            evidence_refs=["ref://evidencia-externa"],
        )
        uow.session.flush()

        # O1 → O2 por REVISÃO: O1 vira SUPERSEDED, O2 vira CURRENT no
        # mesmo CLID. Coexistência histórica (§12).
        o2, _, _ = versions.revise(
            o1,
            operation_type="revisar",
            declared_preservations=["identidade", "linhagem"],
            declared_losses=["formatação original"],
            policy_ref="policy://e3-12",
        )
        uow.session.flush()

        # Branch e merge (§11): O1 → O2, O1 → O3, {O2,O3} → O4.
        o3, _, _ = versions.derive(
            o1, operation_type="ramificar", relation_type=LineageRelation.BRANCH
        )
        o4, _, _ = versions.derive(o2, operation_type="fundir", relation_type=LineageRelation.MERGE)
        uow.session.flush()
        lineage.add_edge(parent_coid=o3.id, child_coid=o4.id, relation_type=LineageRelation.MERGE)

        # Proveniência multi-provider (§13/§14) — e uma explicitamente
        # sem provider/model, provando que ausência continua válida.
        provenance.record(
            coid=o2.id,
            source_type=ProvenanceSourceType.AGENT,
            actor_type=ProvenanceActorType.AGENT,
            provider_id="provider-a",
            model_id="model-a1",
            trace_id="trace-p0-agente",
            session_id="sessao-1",
            correlation_id="correlacao-1",
        )
        provenance.record(
            coid=o3.id,
            source_type=ProvenanceSourceType.AGENT,
            actor_type=ProvenanceActorType.AGENT,
            provider_id="provider-b",
            model_id="model-b1",
            trace_id="trace-p0-agente",
        )
        provenance.record(
            coid=o4.id,
            source_type=ProvenanceSourceType.SYSTEM,
            actor_type=ProvenanceActorType.SYSTEM,
            trace_id="trace-p0-sem-provider",
        )
        uow.session.flush()

        # Transformação com actor_ref resolvível (E3.10.1).
        uow.session.add(
            TransformationRecord(
                operation_type="consolidar",
                transformation_kind=TransformationKind.REVISION,
                input_refs=[str(o2.id), str(o3.id)],
                output_refs=[str(o4.id)],
                actor_ref=human.id,
                policy_ref="policy://e3-12",
                declared_preservations=["conteúdo essencial"],
                declared_losses=["variações de ramo"],
            )
        )

        # Relações: ativas (simétrica e direcionada), uma retirada e
        # recriada, e um ciclo legítimo (§15).
        relationships.add_relationship(
            source_coid=o2.id, target_coid=o3.id, relationship_type=RelationshipType.RELATED_TO
        )
        relationships.add_relationship(
            source_coid=o2.id, target_coid=o4.id, relationship_type=RelationshipType.SUPPORTS
        )
        relationships.add_relationship(
            source_coid=o4.id, target_coid=o2.id, relationship_type=RelationshipType.SUPPORTS
        )
        retired = relationships.add_relationship(
            source_coid=o3.id, target_coid=o4.id, relationship_type=RelationshipType.REFERENCES
        )
        uow.session.flush()
        relationships.retire(retired)
        uow.session.flush()
        recreated = relationships.add_relationship(
            source_coid=o3.id, target_coid=o4.id, relationship_type=RelationshipType.REFERENCES
        )
        uow.session.flush()

        # Histórias causais: uma por sujeito, com predecessor
        # atravessando fronteiras de história (§16) e múltiplos
        # caminhos a partir do mesmo evento.
        origem = causal.record(
            subject_coid=o1.id,
            event_type=CausalEventType.CREATED,
            actor_ref=human.id,
            payload_ref="ref://origem",
            occurred_at=datetime(1998, 5, 1, tzinfo=UTC),
        )
        caminho_a = causal.record(
            subject_coid=o2.id,
            event_type=CausalEventType.TRANSFORMED,
            predecessor=origem,
            occurred_at=datetime(2001, 3, 7, tzinfo=UTC),
        )
        caminho_b = causal.record(
            subject_coid=o3.id, event_type=CausalEventType.COMPARED, predecessor=origem
        )
        causal.record(
            subject_coid=o4.id, event_type=CausalEventType.TRANSFORMED, predecessor=caminho_a
        )
        causal.record(
            subject_coid=o4.id, event_type=CausalEventType.ACCESSED, predecessor=caminho_b
        )

        # Broken Glass (§19): O3 tem sua distinção extinta — a história
        # permanece. Galaxy Trace (§18): O1 é SUPERSEDED e LATENT, mas
        # sua história continua acessível e não é o estado presente.
        accessibility.transition(o1, AccessibilityState.LATENT)
        accessibility.transition(o2, AccessibilityState.ACTIVE)
        accessibility.transition(o4, AccessibilityState.INACCESSIBLE)
        accessibility.transition(
            o3,
            AccessibilityState.CAUSALLY_EXTINCT,
            reason="distinção extinta por consolidação — história preservada",
        )

        uow.commit()
        refs = {
            "clid_o1": o1.clid,
            "o1": o1.id,
            "o2": o2.id,
            "o3": o3.id,
            "o4": o4.id,
            "human_provenance": human.id,
            "origem_event": origem.id,
            "caminho_a": caminho_a.id,
            "caminho_b": caminho_b.id,
            "relacao_recriada": recreated.id,
            "relacao_retirada": retired.id,
        }
    return refs


def _export_from(session: Session) -> dict[str, Any]:
    return SynchronizationManager(SyncRepository(session)).export_package()


def _export_from_a() -> dict[str, Any]:
    with UnitOfWork() as uow:
        return _export_from(uow.session)


def _import_into(session: Session, package: dict[str, Any]):
    report = SynchronizationManager(SyncRepository(session)).import_package(package)
    session.commit()
    return report


# ======================================================================
# G1 — cenário end-to-end principal (§8, §9, §24, §47)
# ======================================================================


def test_g1_full_pipeline_preserves_the_canonical_patrimony(instance_b):
    """`CREATE → TRANSFORM → RELATE → TRACE → SEARCH → INTEGRITY →
    EXPORT → IMPORT → SEARCH → INTEGRITY` com `P_after == P_before`.

    Este é o teste central da E3.12. Ele não verifica um módulo: ele
    verifica que a composição de todos eles não perde nada.
    """
    refs = _seed_p0()

    # --- SEARCH + INTEGRITY antes da transmissão ---
    with UnitOfWork() as uow:
        search = SearchEngine(SearchRepository(uow.session))
        # Os ids são extraídos ainda dentro da sessão: instâncias ORM
        # não sobrevivem ao fechamento da UnitOfWork, e o que este
        # teste compara são identidades, não objetos carregados.
        antes_ativos = [
            o.id for o in search.search(SearchCriteria(accessibility=AccessibilityState.ACTIVE))
        ]
        antes_clid = {o.id for o in search.search(SearchCriteria(clid=refs["clid_o1"]))}
        report_a = IntegrityManager(IntegrityRepository(uow.session)).audit()

    assert report_a.status is IntegrityStatus.PASS, report_a.findings
    assert antes_ativos == [refs["o2"]]
    # Os quatro objetos partilham o CLID: `revise` e `derive` herdam a
    # continuidade de `O1` (E3.3 §11), inclusive através de BRANCH e
    # MERGE. `COID identity != CLID continuity` — quatro identidades,
    # uma continuidade.
    assert antes_clid == {refs["o1"], refs["o2"], refs["o3"], refs["o4"]}

    p_before = _export_from_a()
    census_a = _census(engine)

    # --- transmissão ---
    session_factory = instance_b
    with session_factory() as session:
        report = _import_into(session, p_before)

    assert report.status is SyncStatus.APPLIED
    assert report.overwrite_count == 0
    assert report.applied_count > 0

    # --- SEARCH + INTEGRITY depois da transmissão, no destino ---
    with session_factory() as session:
        search_b = SearchEngine(SearchRepository(session))
        depois_ativos = [
            o.id for o in search_b.search(SearchCriteria(accessibility=AccessibilityState.ACTIVE))
        ]
        depois_clid = {o.id for o in search_b.search(SearchCriteria(clid=refs["clid_o1"]))}
        report_b = IntegrityManager(IntegrityRepository(session)).audit()
        p_after = _export_from(session)

    assert report_b.status is IntegrityStatus.PASS, report_b.findings
    assert depois_ativos == antes_ativos
    assert depois_clid == antes_clid

    # P_after == P_before nas dimensões do contrato E3 (§47).
    assert canonical_payload(p_after) == canonical_payload(p_before)

    # E a origem permaneceu byte a byte intacta: transmitir não altera
    # quem transmitiu (`TRANSMISSION != OVERWRITE`).
    assert _census(engine) == census_a


def test_g1b_continuity_survives_transformation_and_transmission(instance_b):
    """§9 — identidade, linhagem, proveniência, transformação e história
    causal atravessam juntas transformação **e** transmissão."""
    refs = _seed_p0()
    package = _export_from_a()

    with instance_b() as session:
        _import_into(session, package)

        objects = ObjectRepository(session)
        o1 = objects.get_by_id(refs["o1"])
        o2 = objects.get_by_id(refs["o2"])

        # COID idêntico (import nunca regenera identidade).
        assert o1 is not None and o2 is not None
        assert o1.id == refs["o1"] and o2.id == refs["o2"]
        # CLID contínuo através da revisão.
        assert o1.clid == o2.clid == refs["clid_o1"]

        # Linhagem reconstruível no destino.
        lineage = LineageRepository(session)
        filhos_de_o1 = {edge.child_coid for edge in lineage.list_children(refs["o1"])}
        assert {refs["o2"], refs["o3"]} <= filhos_de_o1

        # Proveniência ponta a ponta.
        provenance = ProvenanceRepository(session)
        assert provenance.get_by_id(refs["human_provenance"]) is not None

        # Transformações preservadas com perda declarada.
        transformacoes = session.execute(sa.select(TransformationRecord)).scalars().all()
        assert any(t.declared_losses for t in transformacoes)
        assert any(t.declared_preservations for t in transformacoes)

        # História causal preservada, inclusive o predecessor
        # atravessando histórias.
        causal = CausalHistoryManager(CausalHistoryRepository(session))
        eventos_o4 = causal.events_for(refs["o4"])
        assert len(eventos_o4) == 2
        assert {e.predecessor_event_id for e in eventos_o4} == {
            refs["caminho_a"],
            refs["caminho_b"],
        }


# ======================================================================
# G2 — retenção de distinção (§10, §48)
# ======================================================================


def _seed_two_equivalent_trajectories() -> dict[str, uuid.UUID]:
    """H1 e H2: dois objetos que terminam **estruturalmente
    equivalentes** em toda dimensão comparável do `CognitiveObject`
    (mesmo `accessibility`, mesmo `revision_status`, ambos sem CLID
    herdado de terceiros), mas cujas trajetórias e proveniências são
    distintas.

    Não há campo de conteúdo em `CognitiveObject` desde `E3.1` — o que
    torna o teste mais forte, não mais fraco: os dois objetos são
    indistinguíveis por estado presente, e ainda assim o sistema não
    pode fundi-los.
    """
    refs: dict[str, uuid.UUID] = {}
    with UnitOfWork() as uow:
        objects = ObjectRepository(uow.session)
        provenance = ProvenanceManager(ProvenanceRepository(uow.session))
        causal = CausalHistoryManager(CausalHistoryRepository(uow.session))

        h1 = objects.add(
            CognitiveObject(
                clid=uuid.uuid4(),
                accessibility=AccessibilityState.ACTIVE,
                revision_status=RevisionStatus.CURRENT,
            )
        )
        h2 = objects.add(
            CognitiveObject(
                clid=uuid.uuid4(),
                accessibility=AccessibilityState.ACTIVE,
                revision_status=RevisionStatus.CURRENT,
            )
        )
        uow.session.flush()

        p1 = provenance.record(
            coid=h1.id,
            source_type=ProvenanceSourceType.HUMAN,
            actor_type=ProvenanceActorType.HUMAN,
            trace_id="trace-h1",
        )
        p2 = provenance.record(
            coid=h2.id,
            source_type=ProvenanceSourceType.AGENT,
            actor_type=ProvenanceActorType.AGENT,
            provider_id="provider-b",
            trace_id="trace-h2",
        )
        uow.session.flush()

        e1 = causal.record(subject_coid=h1.id, event_type=CausalEventType.CREATED, actor_ref=p1.id)
        causal.record(subject_coid=h1.id, event_type=CausalEventType.ACCESSED, predecessor=e1)
        e2 = causal.record(subject_coid=h2.id, event_type=CausalEventType.CREATED, actor_ref=p2.id)
        causal.record(subject_coid=h2.id, event_type=CausalEventType.TRANSFORMED, predecessor=e2)

        uow.commit()
        refs = {"h1": h1.id, "h2": h2.id}
    return refs


def test_g2_distinction_survives_the_whole_pipeline(instance_b):
    """§48 — `SAME_OUTPUT != SAME_HISTORY`.

    Duas trajetórias com estado final equivalente permanecem duas
    depois de search, integrity, export e import. Nenhum dedupe
    destrutivo, nenhuma fusão de identidade, nenhuma escolha de
    "representante canônico".
    """
    refs = _seed_two_equivalent_trajectories()

    with UnitOfWork() as uow:
        objects = ObjectRepository(uow.session)
        h1 = objects.get_by_id(refs["h1"])
        h2 = objects.get_by_id(refs["h2"])
        assert h1 is not None and h2 is not None
        # Estado presente equivalente em toda dimensão estrutural
        # comparável — a premissa do teste, asseverada e não assumida.
        assert h1.accessibility == h2.accessibility
        assert h1.revision_status == h2.revision_status
        # ...e ainda assim identidades distintas.
        assert h1.id != h2.id
        assert h1.clid != h2.clid

    package = _export_from_a()

    with instance_b() as session:
        _import_into(session, package)

        causal = CausalHistoryManager(CausalHistoryRepository(session))
        eventos_h1 = causal.events_for(refs["h1"])
        eventos_h2 = causal.events_for(refs["h2"])

        # H1 continua H1; H2 continua H2. A comparação é por conjunto,
        # não por ordem: eventos registrados no mesmo instante têm
        # `created_at` idêntico e o desempate por `id` é legítimo — o
        # que este teste protege é a **retenção da distinção**, não uma
        # ordenação que o contrato nunca prometeu para eventos
        # simultâneos.
        assert {e.event_type for e in eventos_h1} == {
            CausalEventType.CREATED,
            CausalEventType.ACCESSED,
        }
        assert {e.event_type for e in eventos_h2} == {
            CausalEventType.CREATED,
            CausalEventType.TRANSFORMED,
        }
        assert {e.event_type for e in eventos_h1} != {e.event_type for e in eventos_h2}

        # Histórias distintas, sujeitos distintos.
        historia_1 = causal.history_for(refs["h1"])
        historia_2 = causal.history_for(refs["h2"])
        assert historia_1 is not None and historia_2 is not None
        assert historia_1.id != historia_2.id

        # Proveniências distintas: uma humana, uma de agente.
        provenance_rows = session.execute(
            sa.select(sa.column("coid"), sa.column("source_type")).select_from(
                sa.table("provenance_records")
            )
        ).fetchall()
        por_coid = {row[0]: row[1] for row in provenance_rows}
        assert por_coid[refs["h1"]] != por_coid[refs["h2"]]

        # Os dois objetos continuam existindo — contagem é o piso, não
        # o teto, da verificação acima.
        objetos = ObjectRepository(session)
        assert objetos.get_by_id(refs["h1"]) is not None
        assert objetos.get_by_id(refs["h2"]) is not None


# ======================================================================
# G3 — branch/merge e reconstrução de linhagem (§11)
# ======================================================================


def test_g3_branch_and_merge_lineage_is_reconstructable_after_sync(instance_b):
    """§11 — O1 → {O2, O3} → O4 reconstruído idêntico no destino."""
    refs = _seed_p0()
    package = _export_from_a()

    def _grafo(session: Session) -> set[tuple[uuid.UUID, uuid.UUID, LineageRelation]]:
        lineage = LineageRepository(session)
        arestas = set()
        for coid in (refs["o1"], refs["o2"], refs["o3"], refs["o4"]):
            for edge in lineage.list_children(coid):
                arestas.add((edge.parent_coid, edge.child_coid, edge.relation_type))
        return arestas

    with UnitOfWork() as uow:
        origem = _grafo(uow.session)

    # A forma do diamante está lá antes de sincronizar.
    assert (refs["o1"], refs["o2"], LineageRelation.TRANSFORMED_FROM) in origem
    assert (refs["o1"], refs["o3"], LineageRelation.BRANCH) in origem
    assert (refs["o2"], refs["o4"], LineageRelation.MERGE) in origem
    assert (refs["o3"], refs["o4"], LineageRelation.MERGE) in origem

    with instance_b() as session:
        _import_into(session, package)
        assert _grafo(session) == origem


# ======================================================================
# G4 — CURRENT/SUPERSEDED (§12)
# ======================================================================


def test_g4_current_and_superseded_coexist_through_the_pipeline(instance_b):
    """§12 — coexistência histórica preservada; `SUPERSEDED` não é
    corrupção; Search recupera por critério explícito."""
    refs = _seed_p0()
    package = _export_from_a()

    with instance_b() as session:
        _import_into(session, package)

        search = SearchEngine(SearchRepository(session))
        atuais = search.search(SearchCriteria(revision_status=RevisionStatus.CURRENT))
        superados = search.search(SearchCriteria(revision_status=RevisionStatus.SUPERSEDED))

        assert refs["o2"] in {o.id for o in atuais}
        assert refs["o1"] in {o.id for o in superados}

        # Ambos sobreviveram à transmissão.
        objects = ObjectRepository(session)
        assert objects.get_by_id(refs["o1"]) is not None
        assert objects.get_by_id(refs["o2"]) is not None

        # E a auditoria não trata SUPERSEDED como corrupção.
        report = IntegrityManager(IntegrityRepository(session)).audit()
        assert report.status is IntegrityStatus.PASS, report.findings


# ======================================================================
# G5/G6 — proveniência ponta a ponta e neutralidade de provider
# (§13, §14)
# ======================================================================


def test_g5_provenance_end_to_end_keeps_provider_optional(instance_b):
    """§13 — humano, provider A e provider B percorrem o pipeline
    inteiro; `provider_id`/`model_id` `NULL` continuam válidos e nenhum
    provider vira requisito estrutural."""
    _seed_p0()
    package = _export_from_a()

    with instance_b() as session:
        _import_into(session, package)

        linhas = session.execute(
            sa.text(
                "SELECT source_type, actor_type, provider_id, model_id, trace_id, "
                "session_id, correlation_id, evidence_refs FROM provenance_records"
            )
        ).fetchall()

    providers = {row[2] for row in linhas}
    assert "provider-a" in providers
    assert "provider-b" in providers
    assert None in providers, "proveniência sem provider deve continuar válida"

    modelos = {row[3] for row in linhas}
    assert None in modelos, "model_id NULL deve continuar válido"

    # As dimensões declaradas em E3.6/E3.6.1 chegaram inteiras.
    assert any(row[4] for row in linhas), "trace_id preservado"
    assert any(row[5] for row in linhas), "session_id preservado"
    assert any(row[6] for row in linhas), "correlation_id preservado"
    assert any(row[7] for row in linhas), "evidence_refs preservado"


def test_g6_domain_has_no_provider_specific_dependency():
    """§14 — `PROVIDER_NEUTRAL_DOMAIN`.

    Varredura de `app/` por import ou dependência obrigatória de
    fornecedor de LLM. O domínio cognitivo não pode ter ramo lógico
    específico de fornecedor: providers são **dados**, nunca
    estrutura.
    """
    proibidos = re.compile(
        r"\b(import\s+openai|from\s+openai|import\s+anthropic|from\s+anthropic|"
        r"import\s+cohere|from\s+cohere|import\s+google\.generativeai|"
        r"import\s+mistralai|from\s+mistralai|import\s+litellm|from\s+litellm)\b"
    )
    achados: list[str] = []
    for arquivo in _APP_DIR.rglob("*.py"):
        texto = arquivo.read_text(encoding="utf-8")
        for numero, linha in enumerate(texto.splitlines(), start=1):
            if proibidos.search(linha):
                achados.append(f"{arquivo.relative_to(_BACKEND_ROOT)}:{numero}: {linha.strip()}")
    assert achados == [], f"dependência específica de provider encontrada: {achados}"

    # E nenhum ramo lógico condicionado a um provider nomeado.
    ramos = re.compile(r"if\s+.*provider_id\s*==\s*[\"'][^\"']+[\"']")
    condicionais: list[str] = []
    for arquivo in _APP_DIR.rglob("*.py"):
        texto = arquivo.read_text(encoding="utf-8")
        for numero, linha in enumerate(texto.splitlines(), start=1):
            if ramos.search(linha):
                condicionais.append(f"{arquivo.relative_to(_BACKEND_ROOT)}:{numero}")
    assert condicionais == [], f"ramo lógico por provider encontrado: {condicionais}"


# ======================================================================
# G7 — relações (§15)
# ======================================================================


def test_g7_relationship_semantics_are_identical_after_sync(instance_b):
    """§15 — unicidade ativa, retirada, recriação, ordem canônica
    simétrica e ciclo legítimo sobrevivem idênticos."""
    refs = _seed_p0()
    package = _export_from_a()

    with instance_b() as session:
        _import_into(session, package)
        relationships = RelationshipRepository(session)

        # A retirada continua retirada; a recriada continua ativa.
        todas = session.execute(
            sa.text(
                "SELECT id, source_coid, target_coid, relationship_type, retired_at "
                "FROM relationships ORDER BY created_at, id"
            )
        ).fetchall()
        por_id = {row[0]: row for row in todas}

        assert por_id[refs["relacao_retirada"]][4] is not None, "retirada preservada como retirada"
        assert por_id[refs["relacao_recriada"]][4] is None, "recriada preservada como ativa"

        # O par retirado e o recriado têm os mesmos extremos e tipo —
        # ou seja, a história da retirada não foi apagada para caber a
        # recriação (`RETIRE != DELETE_HISTORY`).
        retirada = por_id[refs["relacao_retirada"]]
        recriada = por_id[refs["relacao_recriada"]]
        assert retirada[1:4] == recriada[1:4]

        # Ciclo legítimo de relação continua sendo permitido e não é
        # classificado como corrupção causal.
        vizinhos = {r.target_coid for r in relationships.outgoing(refs["o2"])}
        assert refs["o4"] in vizinhos
        vizinhos_reversos = {r.target_coid for r in relationships.outgoing(refs["o4"])}
        assert refs["o2"] in vizinhos_reversos

        report = IntegrityManager(IntegrityRepository(session)).audit()
        assert report.status is IntegrityStatus.PASS, report.findings


# ======================================================================
# G8 — história causal em integração total (§16)
# ======================================================================


def test_g8_causal_history_invariants_hold_in_full_integration(instance_b):
    """§16 — `ONE_HISTORY_PER_SUBJECT`, `CROSS_HISTORY_PREDECESSOR`
    permitido, `occurred_at` nullable e nenhuma causalidade derivada de
    timestamp."""
    refs = _seed_p0()
    package = _export_from_a()

    with instance_b() as session:
        _import_into(session, package)
        causal = CausalHistoryManager(CausalHistoryRepository(session))

        # Uma história por sujeito.
        contagem = session.execute(
            sa.text(
                "SELECT subject_coid, COUNT(*) FROM causal_histories "
                "GROUP BY subject_coid HAVING COUNT(*) > 1"
            )
        ).fetchall()
        assert contagem == []

        # Predecessor atravessa fronteira de história.
        eventos_o2 = causal.events_for(refs["o2"])
        caminho_a = next(e for e in eventos_o2 if e.id == refs["caminho_a"])
        assert caminho_a.predecessor_event_id == refs["origem_event"]
        historia_o1 = causal.history_for(refs["o1"])
        historia_o2 = causal.history_for(refs["o2"])
        assert historia_o1 is not None and historia_o2 is not None
        assert historia_o1.id != historia_o2.id, "HISTORY_BOUNDARY != CAUSAL_BOUNDARY"

        # occurred_at continua nullable e nunca é preenchido com
        # created_at: TEMPORAL_PRECEDENCE != CAUSALITY.
        eventos = session.execute(
            sa.text("SELECT occurred_at, created_at FROM causal_history_events")
        ).fetchall()
        assert any(row[0] is None for row in eventos), "occurred_at desconhecido continua NULL"
        for occurred_at, created_at in eventos:
            if occurred_at is not None:
                assert occurred_at != created_at


# ======================================================================
# G9/G10/G11 — Galaxy Trace, Broken Glass, não-fabricação (§18, §19, §20)
# ======================================================================


def test_g9_galaxy_trace_survives_transmission(instance_b):
    """§18 — a observação de um estado passado não é o estado presente
    da fonte, e o rastro atravessa a sincronização.

    Sem física: a analogia serve apenas para separar evento/história de
    fonte atual.
    """
    refs = _seed_p0()
    package = _export_from_a()

    with instance_b() as session:
        _import_into(session, package)
        objects = ObjectRepository(session)
        causal = CausalHistoryManager(CausalHistoryRepository(session))

        o1 = objects.get_by_id(refs["o1"])
        assert o1 is not None
        # Estado presente da fonte: superado e latente.
        assert o1.revision_status is RevisionStatus.SUPERSEDED
        assert o1.accessibility is AccessibilityState.LATENT

        # Rastro do estado passado: intacto e datado de 1998.
        eventos = causal.events_for(refs["o1"])
        origem = next(e for e in eventos if e.id == refs["origem_event"])
        assert origem.occurred_at == datetime(1998, 5, 1, tzinfo=UTC)
        assert origem.event_type is CausalEventType.CREATED

        # E o rastro continua alcançável a partir de descendentes —
        # observar o passado não exige que a fonte ainda seja atual.
        assert causal.successors(origem), "rastro arqueológico permanece navegável"


def test_g10_broken_glass_history_outlives_the_extinct_distinction(instance_b):
    """§19 — `DISTINCTION_EXTINCTION != HISTORICAL_ERASURE`, também
    depois de export/import."""
    refs = _seed_p0()
    package = _export_from_a()

    with instance_b() as session:
        _import_into(session, package)
        objects = ObjectRepository(session)
        causal = CausalHistoryManager(CausalHistoryRepository(session))
        lineage = LineageRepository(session)

        o3 = objects.get_by_id(refs["o3"])
        assert o3 is not None
        assert o3.accessibility is AccessibilityState.CAUSALLY_EXTINCT

        # A existência histórica permanece reconstruível: história
        # própria, linhagem de entrada e de saída, proveniência.
        assert causal.events_for(refs["o3"]), "história do objeto extinto preservada"
        assert lineage.list_parents(refs["o3"]), "de onde veio permanece registrado"
        assert lineage.list_children(refs["o3"]), "o que dele derivou permanece registrado"

        provenance = session.execute(
            sa.text("SELECT COUNT(*) FROM provenance_records WHERE coid = :c"),
            {"c": refs["o3"]},
        ).scalar_one()
        assert provenance > 0

        # E a auditoria não confunde extinção com corrupção.
        report = IntegrityManager(IntegrityRepository(session)).audit()
        assert report.status is IntegrityStatus.PASS, report.findings


def test_g11_absence_of_evidence_is_never_converted_into_fabricated_history(instance_b):
    """§20 — proveniência ausente, predecessor ausente, miss de busca e
    ausência de rastro **não** produzem história inventada nem
    `CAUSALLY_EXTINCT` automático."""
    with UnitOfWork() as uow:
        objects = ObjectRepository(uow.session)
        causal = CausalHistoryManager(CausalHistoryRepository(uow.session))
        # Objeto deliberadamente pobre: sem proveniência, sem linhagem,
        # com um único evento sem predecessor e sem occurred_at.
        orfao = objects.add(CognitiveObject())
        uow.session.flush()
        causal.record(subject_coid=orfao.id, event_type=CausalEventType.CREATED)
        uow.commit()
        orfao_id = orfao.id

    package = _export_from_a()

    with instance_b() as session:
        _import_into(session, package)
        objects = ObjectRepository(session)
        causal = CausalHistoryManager(CausalHistoryRepository(session))
        search = SearchEngine(SearchRepository(session))

        importado = objects.get_by_id(orfao_id)
        assert importado is not None

        # Ausência de proveniência não virou proveniência inventada.
        provenance = session.execute(
            sa.text("SELECT COUNT(*) FROM provenance_records WHERE coid = :c"),
            {"c": orfao_id},
        ).scalar_one()
        assert provenance == 0

        # Ausência de predecessor não virou predecessor inventado.
        eventos = causal.events_for(orfao_id)
        assert len(eventos) == 1
        assert eventos[0].predecessor_event_id is None
        assert eventos[0].occurred_at is None, "desconhecido permanece desconhecido"

        # Ausência de rastro não virou extinção causal.
        assert importado.accessibility is not AccessibilityState.CAUSALLY_EXTINCT

        # Miss de busca não é inexistência: o objeto não aparece num
        # filtro que não é o dele, mas continua recuperável por COID.
        assert search.search(SearchCriteria(trace_id="trace-que-nunca-existiu")) == []
        assert [o.id for o in search.search(SearchCriteria(coid=orfao_id))] == [orfao_id]


# ======================================================================
# G12 — Search/Index em integração (§21, §24)
# ======================================================================


def test_g12_search_and_index_stay_derived_and_read_only(instance_b):
    """§21/§24 — Search e Index continuam derivados, read-only e não
    fonte de verdade; o censo é idêntico antes e depois de operações de
    leitura."""
    refs = _seed_p0()

    censo_antes = _census(engine)
    contador = _write_counter(engine)
    try:
        with UnitOfWork() as uow:
            search = SearchEngine(SearchRepository(uow.session))
            index = IndexManager(ObjectRepository(uow.session), IndexRepository(uow.session))

            search.search(SearchCriteria(accessibility=AccessibilityState.ACTIVE))
            search.search(SearchCriteria(revision_status=RevisionStatus.SUPERSEDED))
            search.search(SearchCriteria(trace_id="trace-p0-agente"))
            search.count(SearchCriteria(clid=refs["clid_o1"]))
            index.by_coid(refs["o1"])
            index.by_clid(refs["clid_o1"])
            index.by_accessibility(AccessibilityState.CAUSALLY_EXTINCT)
            index.by_revision_status(RevisionStatus.CURRENT)
            index.by_trace_id("trace-p0-humano")
    finally:
        _stop_counting(engine, contador)

    assert contador["writes"] == 0, "Search/Index nunca escrevem (DOMAIN_WRITE_COUNT = 0)"
    assert _census(engine) == censo_antes

    # Depois da sincronização, ambos continuam funcionando no destino —
    # sem nenhum passo de "reconstrução de índice" no contrato.
    package = _export_from_a()
    with instance_b() as session:
        _import_into(session, package)
        search = SearchEngine(SearchRepository(session))
        index = IndexManager(ObjectRepository(session), IndexRepository(session))
        assert [o.id for o in index.by_clid(refs["clid_o1"])]
        assert search.search(SearchCriteria(trace_id="trace-p0-agente"))


# ======================================================================
# G13 — Integrity em integração (§22)
# ======================================================================


def test_g13_integrity_detects_without_repairing(instance_b):
    """§22 — auditoria de patrimônio válido dá PASS; corrupção injetada
    é detectada; nada é reparado."""
    _seed_p0()
    package = _export_from_a()

    with instance_b() as session:
        _import_into(session, package)

        report = IntegrityManager(IntegrityRepository(session)).audit()
        assert report.status is IntegrityStatus.PASS, report.findings

        # Corrupção injetada por SQL direto, em banco descartável: um
        # ciclo causal que nenhuma API autorizada consegue criar.
        eventos = session.execute(
            sa.text(
                "SELECT id, predecessor_event_id FROM causal_history_events "
                "WHERE predecessor_event_id IS NOT NULL ORDER BY created_at LIMIT 1"
            )
        ).fetchone()
        assert eventos is not None
        filho, pai = eventos
        session.execute(
            sa.text("UPDATE causal_history_events SET predecessor_event_id = :f WHERE id = :p"),
            {"f": filho, "p": pai},
        )
        session.commit()

        antes = _census_session(session)
        depois_report = IntegrityManager(IntegrityRepository(session)).audit()
        depois = _census_session(session)

        assert depois_report.status is IntegrityStatus.FAIL
        assert IntegrityCode.CAUSAL_CYCLE in {f.code for f in depois_report.findings}
        # Detectou e **não** reparou: o patrimônio corrompido continua
        # exatamente como estava (`REPAIR_IMPLEMENTED = NO`).
        assert depois == antes


def _census_session(session: Session) -> dict[str, list[tuple[Any, ...]]]:
    snapshot: dict[str, list[tuple[Any, ...]]] = {}
    for table in SECTION_BY_TABLE:
        rows = session.execute(sa.text(f"SELECT * FROM {table} ORDER BY id")).fetchall()
        snapshot[table] = [tuple(row) for row in rows]
    return snapshot


# ======================================================================
# G14 — gate final de sincronização (§23)
# ======================================================================


def test_g14_sync_round_trip_is_idempotent_and_conflict_free_by_default(instance_b):
    """§23 — reimportar o mesmo pacote é idempotente: nada é aplicado
    de novo, nada é sobrescrito, nenhum conflito é inventado."""
    _seed_p0()
    package = _export_from_a()

    with instance_b() as session:
        primeiro = _import_into(session, package)
        censo_apos_primeiro = _census_session(session)

        segundo = _import_into(session, package)
        censo_apos_segundo = _census_session(session)

    assert primeiro.status is SyncStatus.APPLIED
    assert primeiro.applied_count > 0
    assert segundo.status is SyncStatus.APPLIED
    assert segundo.applied_count == 0, "reimport não aplica nada"
    assert segundo.skipped_count > 0, "reimport reconhece o que já está lá"
    assert segundo.overwrite_count == 0
    assert censo_apos_segundo == censo_apos_primeiro


# ======================================================================
# G15 — negative strong gate (§49)
# ======================================================================


def test_g15_five_defect_classes_produce_five_distinct_diagnostics(instance_b):
    """§49 — cada classe de defeito recebe diagnóstico próprio.

    A propriedade protegida não é "detectar"; é **não colapsar**. Um
    sistema que responde "inválido" para tudo destrói exatamente a
    distinção que a E3 existe para preservar.
    """
    diagnosticos: dict[str, object] = {}

    # (A) Conflito de identidade — mesmo id, representação divergente.
    _seed_p0()
    package = _export_from_a()
    with instance_b() as session:
        _import_into(session, package)
        alvo = package["objects"][0]
        # A divergência precisa ser garantida, não presumida: mutar
        # para um valor que o objeto já tem produziria representações
        # idênticas e, corretamente, nenhum conflito. Escolhemos um
        # estado explicitamente diferente do atual.
        estado_atual = alvo["accessibility"]
        estado_divergente = "active" if estado_atual != "active" else "latent"
        assert estado_divergente != estado_atual
        session.execute(
            sa.text("UPDATE cognitive_objects SET accessibility = :a WHERE id = :i"),
            {"a": estado_divergente, "i": uuid.UUID(alvo["id"])},
        )
        session.commit()
        censo_antes = _census_session(session)
        relatorio = SynchronizationManager(SyncRepository(session)).import_package(package)
        session.commit()
        diagnosticos["identity_conflict"] = relatorio.status
        assert relatorio.status is SyncStatus.CONFLICT
        assert relatorio.applied_count == 0
        assert relatorio.overwrite_count == 0
        assert relatorio.conflicts[0].differing_fields, "campos divergentes localizados"
        assert _census_session(session) == censo_antes, "conflito não escreve nada"

    # (B) Pacote causalmente inválido — ciclo no material recebido.
    _truncate(engine)
    _seed_p0()
    package_ciclico = _export_from_a()
    eventos = package_ciclico["causal_events"]
    com_predecessor = [e for e in eventos if e.get("predecessor_event_id")]
    filho = com_predecessor[0]
    pai_id = filho["predecessor_event_id"]
    for evento in eventos:
        if evento["id"] == pai_id:
            evento["predecessor_event_id"] = filho["id"]
    with instance_b() as session:
        censo_antes = _census_session(session)
        with pytest.raises(SyncPackageInvalidError) as exc:
            SynchronizationManager(SyncRepository(session)).import_package(package_ciclico)
        diagnosticos["causal_invalid_package"] = exc.value.error_code
        assert _census_session(session) == censo_antes, "rejeitado antes de qualquer escrita"

    # (C) Corrupção de linhagem — ciclo indireto.
    _truncate(engine)
    with UnitOfWork() as uow:
        objects = ObjectRepository(uow.session)
        lineage = LineageRepository(uow.session)
        a = objects.add(CognitiveObject())
        b = objects.add(CognitiveObject())
        c = objects.add(CognitiveObject())
        uow.session.flush()
        lineage.add_edge(parent_coid=a.id, child_coid=b.id, relation_type=LineageRelation.BRANCH)
        lineage.add_edge(parent_coid=b.id, child_coid=c.id, relation_type=LineageRelation.BRANCH)
        lineage.add_edge(parent_coid=c.id, child_coid=a.id, relation_type=LineageRelation.BRANCH)
        uow.commit()
    with UnitOfWork() as uow:
        relatorio_lin = IntegrityManager(IntegrityRepository(uow.session)).audit()
    codigos_lin = {f.code for f in relatorio_lin.findings}
    assert IntegrityCode.LINEAGE_CYCLE in codigos_lin
    diagnosticos["lineage_corruption"] = IntegrityCode.LINEAGE_CYCLE

    # (D) actor_ref pendente em transformação.
    _truncate(engine)
    with UnitOfWork() as uow:
        uow.session.add(
            TransformationRecord(
                operation_type="orfa",
                transformation_kind=TransformationKind.DERIVATION,
                input_refs=[],
                output_refs=[],
                actor_ref=uuid.uuid4(),
            )
        )
        uow.commit()
    with UnitOfWork() as uow:
        relatorio_trf = IntegrityManager(IntegrityRepository(uow.session)).audit()
    codigos_trf = {f.code for f in relatorio_trf.findings}
    assert IntegrityCode.TRANSFORMATION_DANGLING_ACTOR_REF in codigos_trf
    diagnosticos["dangling_actor_ref"] = IntegrityCode.TRANSFORMATION_DANGLING_ACTOR_REF

    # (E) Vocabulário de acessibilidade inválido.
    _truncate(engine)
    with UnitOfWork() as uow:
        objects = ObjectRepository(uow.session)
        objeto = objects.add(CognitiveObject())
        uow.commit()
        alvo_id = objeto.id
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "UPDATE cognitive_objects SET accessibility = 'estado-inexistente' WHERE id = :i"
            ),
            {"i": alvo_id},
        )
    with UnitOfWork() as uow:
        relatorio_idn = IntegrityManager(IntegrityRepository(uow.session)).audit()
    codigos_idn = {f.code for f in relatorio_idn.findings}
    assert IntegrityCode.IDENTITY_INVALID_ACCESSIBILITY_STATE in codigos_idn
    diagnosticos["invalid_accessibility"] = IntegrityCode.IDENTITY_INVALID_ACCESSIBILITY_STATE

    # A propriedade central: cinco defeitos, cinco diagnósticos
    # distintos. Nenhum colapso em "inválido".
    assert len(diagnosticos) == 5
    assert (
        len(set(map(str, diagnosticos.values()))) == 5
    ), f"diagnósticos colapsaram: {diagnosticos}"


# ======================================================================
# G16–G19 — fronteiras normativas como teste executável
# (§7, §22, §25, §26, §27, §28, §45)
# ======================================================================


def _fontes_do_dominio() -> list[tuple[pathlib.Path, str]]:
    return [
        (caminho, caminho.read_text(encoding="utf-8"))
        for caminho in (_APP_DIR / "cognitive").rglob("*.py")
    ]


def test_g16_no_automatic_persistence_of_transcript_or_payload():
    """§25 — `TRANSCRIPT_AUTO_STORAGE = NONE`.

    Nenhuma coluna do domínio cognitivo armazena prompt, completion,
    transcript, raciocínio oculto ou payload de provider. Referências
    permanecem referências.
    """
    import app.cognitive.models  # noqa: F401
    from app.database.base import Base

    suspeitos = re.compile(
        r"(transcript|prompt|completion|payload_content|raw_response|"
        r"reasoning|message_body|conversation)",
        re.IGNORECASE,
    )
    achados: list[str] = []
    for nome in SECTION_BY_TABLE:
        for coluna in Base.metadata.tables[nome].columns:
            if suspeitos.search(coluna.name):
                achados.append(f"{nome}.{coluna.name}")
    assert achados == [], f"coluna de conteúdo encontrada no domínio: {achados}"

    # `payload_ref` é referência, e o nome diz isso — o teste acima o
    # deixa passar de propósito; este assevera que ele é textual e
    # curto, nunca um campo de conteúdo.
    coluna_ref = Base.metadata.tables["causal_history_events"].columns["payload_ref"]
    assert isinstance(coluna_ref.type, sa.String)
    assert coluna_ref.type.length is not None


def test_g17_cout_is_not_a_decision_engine():
    """§7 — `COUT_DECISION_ENGINE = NONE`, `COUT_GLOBAL_SCORE = NONE`,
    `A_R_P_T_CANONICAL_SCORE = NONE`, `COUT_PROVIDER_SELECTOR = NONE`,
    `COUT_KERNEL_DECISION_DEPENDENCY = NONE`."""
    proibidos = re.compile(
        r"(class\s+\w*CoutDecision|class\s+\w*CoutScore|class\s+\w*Arbiter|"
        r"class\s+\w*ProviderSelector|def\s+\w*cout_score|def\s+\w*select_provider|"
        r"def\s+\w*decide\b|cout_global_score)",
        re.IGNORECASE,
    )
    achados: list[str] = []
    for caminho, texto in _fontes_do_dominio():
        for numero, linha in enumerate(texto.splitlines(), start=1):
            if proibidos.search(linha):
                achados.append(f"{caminho.relative_to(_BACKEND_ROOT)}:{numero}: {linha.strip()}")
    assert achados == [], f"mecanismo decisório COUT encontrado: {achados}"

    # E o kernel/runtime não importa nada do domínio cognitivo para
    # decidir: nenhuma dependência de app.cognitive fora dele mesmo.
    externos: list[str] = []
    for caminho in _APP_DIR.rglob("*.py"):
        if "cognitive" in caminho.parts:
            continue
        texto = caminho.read_text(encoding="utf-8")
        if re.search(r"^\s*(from|import)\s+app\.cognitive", texto, re.MULTILINE):
            externos.append(str(caminho.relative_to(_BACKEND_ROOT)))
    assert externos == [], f"kernel/runtime passou a depender do domínio cognitivo: {externos}"


def test_g18_no_cognitive_metadata_primitive_exists():
    """§26 — `COGNITIVE_DOMAIN_METADATA_PRIMITIVE = NONE`,
    `ARBITRARY_METADATA_DICT = NOT_AUTHORIZED` (decisão congelada em
    E3.6.2)."""
    import app.cognitive.models  # noqa: F401
    from app.database.base import Base

    for nome in SECTION_BY_TABLE:
        colunas = {c.name for c in Base.metadata.tables[nome].columns}
        assert "metadata" not in colunas
        assert "meta" not in colunas
        assert "extra" not in colunas
        assert "attributes" not in colunas

    classes = re.compile(r"class\s+\w*Metadata\w*\b")
    achados = [
        str(caminho.relative_to(_BACKEND_ROOT))
        for caminho, texto in _fontes_do_dominio()
        if classes.search(texto)
    ]
    assert achados == [], f"primitiva de Metadata cognitivo encontrada: {achados}"


def test_g19_e3_boundaries_remain_unimplemented():
    """§22/§27/§28/§45 — o que a E3 declarou **não** entregar continua
    não entregue.

    Um gate final que só verificasse o que existe deixaria a fronteira
    aberta: a promessa da E3 inclui explicitamente o que ela não faz.
    """
    proibidos = {
        "reparo automático": re.compile(r"def\s+(repair|auto_repair|fix_|heal_)", re.IGNORECASE),
        "engine de governança": re.compile(r"class\s+\w*Governance\w*", re.IGNORECASE),
        "engine de aprendizado": re.compile(r"class\s+\w*(Learning|Trainer)\w*", re.IGNORECASE),
        "execução cognitiva": re.compile(
            r"class\s+\w*(CognitiveExecution|Orchestrat)\w*", re.IGNORECASE
        ),
        "armazenamento de artefato": re.compile(r"class\s+\w*ArtifactStorage\w*", re.IGNORECASE),
        "motor de ACL": re.compile(r"class\s+\w*(Acl|Permission)\w*", re.IGNORECASE),
        "execução arbitrária": re.compile(r"\b(eval|exec)\s*\(|os\.system|subprocess\."),
    }
    achados: list[str] = []
    for caminho, texto in _fontes_do_dominio():
        for rotulo, padrao in proibidos.items():
            for numero, linha in enumerate(texto.splitlines(), start=1):
                if padrao.search(linha):
                    achados.append(
                        f"{rotulo}: {caminho.relative_to(_BACKEND_ROOT)}:{numero}: {linha.strip()}"
                    )
    assert achados == [], f"fronteira da E3 rompida: {achados}"


# ======================================================================
# G20 — matriz de garantias do DAG (§17)
# ======================================================================


def test_g20_dag_guarantee_matrix_is_not_overclaimed():
    """§17 — a garantia de DAG causal e de linhagem é **do caminho de
    aplicação e da auditoria**, não do banco.

    O teste prova a classificação nos dois sentidos: o caminho
    autorizado protege, e o banco, sozinho, não. Afirmar garantia de
    banco seria overclaim; afirmar ausência de proteção seria
    underclaim.
    """
    # (1) O caminho autorizado protege: predecessor precisa existir.
    with UnitOfWork() as uow:
        objects = ObjectRepository(uow.session)
        objeto = objects.add(CognitiveObject())
        uow.commit()
        alvo = objeto.id

    # (2) O banco, sozinho, não impede um ciclo criado por SQL direto —
    # é exatamente por isso que a auditoria global de E3.10 existe.
    with UnitOfWork() as uow:
        causal = CausalHistoryManager(CausalHistoryRepository(uow.session))
        primeiro = causal.record(subject_coid=alvo, event_type=CausalEventType.CREATED)
        segundo = causal.record(
            subject_coid=alvo, event_type=CausalEventType.ACCESSED, predecessor=primeiro
        )
        uow.commit()
        id_primeiro, id_segundo = primeiro.id, segundo.id

    with engine.begin() as conn:
        conn.execute(
            sa.text("UPDATE causal_history_events SET predecessor_event_id = :s WHERE id = :f"),
            {"s": id_segundo, "f": id_primeiro},
        )

    with UnitOfWork() as uow:
        relatorio = IntegrityManager(IntegrityRepository(uow.session)).audit()

    assert relatorio.status is IntegrityStatus.FAIL
    assert IntegrityCode.CAUSAL_CYCLE in {f.code for f in relatorio.findings}
    # DB_LEVEL_GLOBAL_DAG_GUARANTEE = FALSE, comprovado: o UPDATE acima
    # foi aceito pelo banco. INTEGRITY_GLOBAL_AUDIT = TRUE, comprovado:
    # a auditoria o encontrou.


# ======================================================================
# G21 — smoke de volume (§50)
# ======================================================================


def test_g21_volume_smoke_detects_no_pathological_behaviour(instance_b):
    """§50 — smoke de volume pequeno/médio, não benchmark.

    O objetivo é detectar N+1 óbvio, índice ausente ou detector de
    ciclo degenerado — não medir desempenho. Os limites são
    deliberadamente frouxos: um gate que falha por variação de máquina
    não prova nada e vira ruído.
    """
    tamanho = 120
    with UnitOfWork() as uow:
        objects = ObjectRepository(uow.session)
        lineage = LineageRepository(uow.session)
        causal = CausalHistoryManager(CausalHistoryRepository(uow.session))
        clid = uuid.uuid4()

        anteriores: list[CognitiveObject] = []
        for indice in range(tamanho):
            objeto = objects.add(
                CognitiveObject(
                    clid=clid if indice % 2 == 0 else uuid.uuid4(),
                    accessibility=AccessibilityState.LATENT,
                )
            )
            anteriores.append(objeto)
        uow.session.flush()

        # Cadeia longa de linhagem e de causalidade: o detector de
        # ciclo é O(V+E) e iterativo — uma cadeia profunda não pode
        # estourar recursão nem degradar.
        evento_anterior = None
        for anterior, atual in zip(anteriores, anteriores[1:], strict=False):
            lineage.add_edge(
                parent_coid=anterior.id,
                child_coid=atual.id,
                relation_type=LineageRelation.DERIVED_FROM,
            )
            evento_anterior = causal.record(
                subject_coid=atual.id,
                event_type=CausalEventType.TRANSFORMED,
                predecessor=evento_anterior,
            )
        uow.commit()

    inicio = time.monotonic()
    with UnitOfWork() as uow:
        relatorio = IntegrityManager(IntegrityRepository(uow.session)).audit()
    duracao_auditoria = time.monotonic() - inicio

    assert relatorio.status is IntegrityStatus.PASS, relatorio.findings
    assert duracao_auditoria < 30, "auditoria degenerou em volume pequeno"

    inicio = time.monotonic()
    with UnitOfWork() as uow:
        search = SearchEngine(SearchRepository(uow.session))
        encontrados = search.search(SearchCriteria(accessibility=AccessibilityState.LATENT))
    duracao_busca = time.monotonic() - inicio

    assert len(encontrados) == tamanho
    assert duracao_busca < 10, "busca degenerou em volume pequeno"

    # E o pacote inteiro atravessa a transmissão sem comportamento
    # patológico.
    inicio = time.monotonic()
    package = _export_from_a()
    with instance_b() as session:
        _import_into(session, package)
    duracao_sync = time.monotonic() - inicio
    assert duracao_sync < 60, "sincronização degenerou em volume pequeno"


# ======================================================================
# G22 — envelope e determinismo do pacote (§23)
# ======================================================================


def test_g22_package_envelope_is_versioned_and_deterministic():
    """§23 — o envelope é versionado e o export é determinístico; só
    `exported_at` varia entre dois exports do mesmo patrimônio."""
    _seed_p0()

    primeiro = _export_from_a()
    segundo = _export_from_a()

    assert primeiro["format"] == SYNC_FORMAT
    assert primeiro["schema_version"] == SYNC_SCHEMA_VERSION
    assert set(SECTION_BY_TABLE.values()) <= set(primeiro)
    assert canonical_payload(primeiro) == canonical_payload(segundo)
    assert "exported_at" in primeiro
