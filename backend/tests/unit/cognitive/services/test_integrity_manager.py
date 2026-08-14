"""
Testes unitários de `E3.10`/`LIB-10` — Integrity Manager.

Três blocos:

1. `find_cycle()` como **função pura** — grafos sintéticos, incluindo
   ciclos que nenhuma API do PIA conseguiria criar. É o que permite
   cobrir exaustivamente o detector sem corromper banco.
2. o `IntegrityManager` sobre um repositório falso, cobrindo o
   caminho de *reporte* de cada invariante — inclusive os que o
   PostgreSQL impede de produzir de verdade (FK, CHECK, índice
   único). Fingir que esses estados são criáveis seria mentira; não
   testar o reporte deles seria pior.
3. o `IntegrityManager` sobre patrimônio real em SQLite, provando o
   **false-positive gate**: cenários legítimos que não podem virar
   corrupção.
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest

from app.cognitive.models.causal_history import CausalHistory, CausalHistoryEvent
from app.cognitive.models.cognitive_object import CognitiveObject
from app.cognitive.models.enums import (
    AccessibilityState,
    CausalEventType,
    LineageRelation,
    ProvenanceActorType,
    ProvenanceSourceType,
    RelationshipType,
    RevisionStatus,
)
from app.cognitive.repositories.causal_history_repository import CausalHistoryRepository
from app.cognitive.repositories.integrity_repository import IntegrityRepository
from app.cognitive.repositories.lineage_repository import LineageRepository
from app.cognitive.repositories.object_repository import ObjectRepository
from app.cognitive.repositories.provenance_repository import ProvenanceRepository
from app.cognitive.repositories.relationship_repository import RelationshipRepository
from app.cognitive.schemas.integrity import (
    IntegrityCategory,
    IntegrityCode,
    IntegrityFinding,
    IntegrityReport,
    IntegrityStatus,
)
from app.cognitive.services.causal_history_manager import CausalHistoryManager
from app.cognitive.services.integrity_manager import IntegrityManager, find_cycle
from app.cognitive.services.provenance_manager import ProvenanceManager
from app.core.error_codes import ErrorSeverity

# ---------------------------------------------------------------------
# 1. find_cycle — função pura
# ---------------------------------------------------------------------


def _ids(n: int) -> list[uuid.UUID]:
    return [uuid.uuid4() for _ in range(n)]


def test_ig1_acyclic_graph_has_no_cycle():
    """IG1 — DAG válido não produz ciclo."""
    a, b, c, d = _ids(4)

    assert find_cycle({a: [b, c], b: [d], c: [d], d: []}) is None
    assert find_cycle({}) is None


def test_ig2_two_node_cycle_is_detected_with_its_path():
    """IG2 — `A → B → A`, com o caminho fechado real."""
    a, b = _ids(2)

    cycle = find_cycle({a: [b], b: [a]})

    assert cycle is not None
    assert cycle[0] == cycle[-1]
    assert set(cycle) == {a, b}


def test_ig3_three_node_cycle_is_detected():
    """IG3 — `A → B → C → A`."""
    a, b, c = _ids(3)

    cycle = find_cycle({a: [b], b: [c], c: [a]})

    assert cycle is not None
    assert cycle[0] == cycle[-1]
    assert len(cycle) == 4


def test_ig4_long_cycle_is_detected_without_recursion_error():
    """IG4 — ciclo longo (1000 nós): o DFS iterativo atravessa sem
    `RecursionError`, que é a razão de ele não ser recursivo."""
    nodes = _ids(1000)
    adjacency = {node: [nodes[(i + 1) % len(nodes)]] for i, node in enumerate(nodes)}

    cycle = find_cycle(adjacency)

    assert cycle is not None
    assert len(cycle) == len(nodes) + 1


def test_ig5_cycle_path_is_a_real_walk_through_the_graph():
    """IG5 — o caminho devolvido é percorrível: cada passo é uma
    aresta que existe."""
    a, b, c, d = _ids(4)
    adjacency = {a: [b], b: [c], c: [d], d: [b]}

    cycle = find_cycle(adjacency)

    assert cycle is not None
    for origin, destination in zip(cycle[:-1], cycle[1:], strict=True):
        assert destination in adjacency[origin]


def test_ig6_only_the_corrupted_component_is_reported():
    """IG6 — com vários componentes, o ciclo apontado pertence ao
    componente corrompido; o componente acíclico não é envolvido."""
    a, b = _ids(2)
    x, y, z = _ids(3)
    adjacency = {a: [b], b: [], x: [y], y: [z], z: [x]}

    cycle = find_cycle(adjacency)

    assert cycle is not None
    assert set(cycle) == {x, y, z}
    assert a not in cycle and b not in cycle


def test_ig7_self_loop_is_detected_as_a_cycle():
    """IG7 — auto-aresta é ciclo de comprimento 1."""
    a = uuid.uuid4()

    cycle = find_cycle({a: [a]})

    assert cycle == [a, a]


def test_detection_is_deterministic_for_the_same_input():
    """O mesmo grafo devolve sempre o mesmo ciclo — auditoria
    reproduzível."""
    a, b, c = _ids(3)
    adjacency = {a: [b], b: [c], c: [a]}

    assert find_cycle(adjacency) == find_cycle(adjacency)


# ---------------------------------------------------------------------
# 2. IntegrityManager sobre repositório falso — caminho de reporte
# ---------------------------------------------------------------------


@dataclass
class FakeIntegrityRepository:
    """Repositório de auditoria controlado.

    Existe para cobrir o reporte de invariantes que o PostgreSQL
    **impede** de acontecer (FK, CHECK, índice único parcial). Não é
    afirmação de que esses estados sejam alcançáveis pelas APIs — é o
    contrário: são justamente os que só apareceriam em patrimônio
    legado, importado ou manipulado por fora.
    """

    lineage: list[tuple[uuid.UUID, uuid.UUID, uuid.UUID]] = field(default_factory=list)
    causal: list[tuple[uuid.UUID, uuid.UUID]] = field(default_factory=list)
    lineage_self: list[uuid.UUID] = field(default_factory=list)
    relationship_self: list[uuid.UUID] = field(default_factory=list)
    causal_self: list[uuid.UUID] = field(default_factory=list)
    multiple_current: list[tuple[uuid.UUID, int]] = field(default_factory=list)
    multiple_histories: list[tuple[uuid.UUID, int]] = field(default_factory=list)
    duplicate_active: list = field(default_factory=list)
    non_canonical: list[uuid.UUID] = field(default_factory=list)
    lineage_dangling: list[uuid.UUID] = field(default_factory=list)
    relationship_dangling: list[uuid.UUID] = field(default_factory=list)
    provenance_dangling: list[uuid.UUID] = field(default_factory=list)
    causal_dangling_subject: list[uuid.UUID] = field(default_factory=list)
    causal_dangling_predecessor: list[uuid.UUID] = field(default_factory=list)

    def lineage_edges(self):
        return self.lineage

    def causal_edges(self):
        return self.causal

    def lineage_self_links(self):
        return self.lineage_self

    def relationship_self_links(self):
        return self.relationship_self

    def causal_self_predecessors(self):
        return self.causal_self

    def clids_with_multiple_current(self):
        return self.multiple_current

    def subjects_with_multiple_histories(self):
        return self.multiple_histories

    def duplicate_active_relationships(self):
        return self.duplicate_active

    def non_canonical_symmetric_relationships(self):
        return self.non_canonical

    def lineage_dangling_endpoints(self):
        return self.lineage_dangling

    def relationship_dangling_endpoints(self):
        return self.relationship_dangling

    def provenance_dangling_coids(self):
        return self.provenance_dangling

    def causal_dangling_subjects(self):
        return self.causal_dangling_subject

    def causal_dangling_predecessors(self):
        return self.causal_dangling_predecessor


def _audit(**kwargs) -> IntegrityReport:
    return IntegrityManager(FakeIntegrityRepository(**kwargs)).audit()  # type: ignore[arg-type]


def _codes(report: IntegrityReport) -> set[IntegrityCode]:
    return {finding.code for finding in report.findings}


def test_clean_patrimony_reports_pass():
    """Patrimônio sem violação: `PASS`, zero findings, contagens
    vazias."""
    report = _audit()

    assert report.status is IntegrityStatus.PASS
    assert report.findings == ()
    assert report.counts == {}
    assert report.scope == "full"
    assert report.audited_at <= datetime.now(UTC)


def test_lineage_cycle_finding_carries_diagnostic_evidence():
    """O finding de ciclo de linhagem traz `cycle_path`,
    `involved_coids` e `involved_edge_ids` — nunca só
    `cycle = true`."""
    a, b = _ids(2)
    edge_ab, edge_ba = _ids(2)

    report = _audit(lineage=[(edge_ab, a, b), (edge_ba, b, a)])

    assert report.status is IntegrityStatus.FAIL
    (finding,) = [f for f in report.findings if f.code is IntegrityCode.LINEAGE_CYCLE]
    assert finding.category is IntegrityCategory.LINEAGE
    assert finding.severity is ErrorSeverity.ERROR
    assert set(finding.entity_refs) == {edge_ab, edge_ba}
    assert finding.evidence["cycle_length"] == 2
    assert len(finding.evidence["cycle_path"]) == 3
    assert set(finding.evidence["involved_coids"]) == {str(a), str(b)}


def test_causal_cycle_finding_carries_event_path():
    """Ciclo causal global também é diagnosticado com caminho."""
    first, second = _ids(2)

    report = _audit(causal=[(first, second), (second, first)])

    (finding,) = [f for f in report.findings if f.code is IntegrityCode.CAUSAL_CYCLE]
    assert finding.category is IntegrityCategory.CAUSAL_HISTORY
    assert set(finding.entity_refs) == {first, second}
    assert finding.evidence["cycle_length"] == 2


def test_every_structural_invariant_has_a_reporting_path():
    """Cada invariante auditado produz seu finding quando violado —
    inclusive os que o banco normalmente impede."""
    ids = _ids(8)
    report = _audit(
        lineage_self=[ids[0]],
        relationship_self=[ids[1]],
        causal_self=[ids[2]],
        multiple_current=[(ids[3], 2)],
        multiple_histories=[(ids[4], 2)],
        duplicate_active=[(ids[5], ids[6], RelationshipType.REFERENCES, 2)],
        non_canonical=[ids[7]],
        lineage_dangling=[ids[0]],
        relationship_dangling=[ids[1]],
        provenance_dangling=[ids[2]],
        causal_dangling_subject=[ids[3]],
        causal_dangling_predecessor=[ids[4]],
    )

    assert report.status is IntegrityStatus.FAIL
    assert _codes(report) == {
        IntegrityCode.LINEAGE_SELF_LINK,
        IntegrityCode.LINEAGE_DANGLING_ENDPOINT,
        IntegrityCode.RELATIONSHIP_SELF_LINK,
        IntegrityCode.RELATIONSHIP_NON_CANONICAL_SYMMETRIC,
        IntegrityCode.RELATIONSHIP_DUPLICATE_ACTIVE,
        IntegrityCode.RELATIONSHIP_DANGLING_ENDPOINT,
        IntegrityCode.VERSION_MULTIPLE_CURRENT_PER_CLID,
        IntegrityCode.PROVENANCE_DANGLING_COID,
        IntegrityCode.CAUSAL_SELF_PREDECESSOR,
        IntegrityCode.CAUSAL_MULTIPLE_HISTORIES_PER_SUBJECT,
        IntegrityCode.CAUSAL_DANGLING_REFERENCE,
    }
    assert report.counts[IntegrityCategory.LINEAGE] == 2
    assert report.counts[IntegrityCategory.RELATIONSHIP] == 4


def test_duplicate_active_relationship_evidence_is_structured():
    """A evidência de duplicidade ativa identifica a tripla e a
    contagem, e o texto lembra que relação retirada pode repetir a
    tripla legitimamente."""
    source, target = _ids(2)

    report = _audit(duplicate_active=[(source, target, RelationshipType.SUPPORTS, 3)])

    (finding,) = report.findings
    (duplicate,) = finding.evidence["duplicates"]
    assert duplicate["source_coid"] == str(source)
    assert duplicate["active_count"] == 3
    assert "retiradas" in finding.message


def test_multiple_current_evidence_lists_the_contaminated_clids():
    clid = uuid.uuid4()

    report = _audit(multiple_current=[(clid, 2)])

    (finding,) = report.findings
    assert finding.evidence["clids"] == [{"clid": str(clid), "current_count": 2}]
    assert "SUPERSEDED" in finding.message


def test_finding_has_no_cognitive_identity():
    """Finding é diagnóstico: sem COID, sem CLID, sem lifecycle, sem
    persistência."""
    fields = set(IntegrityFinding.__dataclass_fields__)

    assert fields == {
        "code",
        "category",
        "severity",
        "entity_type",
        "entity_refs",
        "message",
        "evidence",
    }
    assert not {"coid", "clid", "id", "created_at"} & fields
    assert not hasattr(IntegrityFinding, "__tablename__")
    assert not hasattr(IntegrityReport, "__tablename__")


def test_report_status_is_derived_not_declared():
    """`status` deriva dos findings — o chamador não pode declarar
    `PASS`."""
    assert "status" not in IntegrityReport.__dataclass_fields__

    empty = IntegrityReport(findings=(), audited_at=datetime.now(UTC))
    with_finding = IntegrityReport(
        findings=(
            IntegrityFinding(
                code=IntegrityCode.LINEAGE_CYCLE,
                category=IntegrityCategory.LINEAGE,
                severity=ErrorSeverity.ERROR,
                entity_type="LineageEdge",
                entity_refs=(),
                message="x",
            ),
        ),
        audited_at=datetime.now(UTC),
    )

    assert empty.status is IntegrityStatus.PASS
    assert with_finding.status is IntegrityStatus.FAIL


# ---------------------------------------------------------------------
# 3. False-positive gate sobre patrimônio real
# ---------------------------------------------------------------------


@pytest.fixture
def integrity(cognitive_session):
    session = cognitive_session
    return session, ObjectRepository(session), IntegrityManager(IntegrityRepository(session))


def _obj(objects, session, **kwargs) -> CognitiveObject:
    obj = objects.add(CognitiveObject(**kwargs))
    session.flush()
    return obj


def test_fp_gate_galaxy_trace_is_not_corruption(integrity):
    """False-positive gate — **Galaxy Trace**: o estado histórico
    permanece `SUPERSEDED` e causalmente referenciável enquanto o
    estado corrente é outro. Isso é o rastro arqueológico funcionando,
    não corrupção.

    `PRESERVED_TRACE != CORRUPTION`
    """
    session, objects, manager = integrity
    clid = uuid.uuid4()
    s0 = _obj(objects, session, clid=clid, revision_status=RevisionStatus.SUPERSEDED)
    s1 = _obj(objects, session, clid=clid, revision_status=RevisionStatus.CURRENT)
    causal = CausalHistoryManager(CausalHistoryRepository(session))
    causal.record(
        subject_coid=s0.id,
        event_type=CausalEventType.CREATED,
        occurred_at=datetime(1999, 1, 1, tzinfo=UTC),
    )
    session.flush()

    report = manager.audit()

    assert report.status is IntegrityStatus.PASS, report.findings
    assert s1.revision_status is RevisionStatus.CURRENT


def test_fp_gate_broken_glass_is_not_corruption(integrity):
    """False-positive gate — **Broken Glass**: a distinção deixou de
    persistir, o sujeito está `CAUSALLY_EXTINCT`, e a história
    continua registrada.

    `DISTINCTION_EXTINCTION != CORRUPTION`
    `HISTORICAL_EXISTENCE != CURRENT_EXISTENCE`
    """
    session, objects, manager = integrity
    g0 = _obj(objects, session, accessibility=AccessibilityState.CAUSALLY_EXTINCT)
    fragments = [
        _obj(objects, session, accessibility=AccessibilityState.INACCESSIBLE) for _ in range(3)
    ]
    causal = CausalHistoryManager(CausalHistoryRepository(session))
    previous = causal.record(subject_coid=g0.id, event_type=CausalEventType.CREATED)
    for _ in fragments:
        previous = causal.record(
            subject_coid=g0.id, event_type=CausalEventType.TRANSFORMED, predecessor=previous
        )
    session.flush()

    report = manager.audit()

    assert report.status is IntegrityStatus.PASS, report.findings


def test_fp_gate_legitimate_patrimony_is_not_corruption(integrity):
    """False-positive gate consolidado: nada disto é corrupção por si
    só — ciclo de `Relationship` permitido, relações contraditórias,
    predecessor entre histórias, múltiplos caminhos causais,
    `occurred_at=None`, `provider_id`/`model_id` ausentes,
    `SUPERSEDED`, `INACCESSIBLE`, `CAUSALLY_EXTINCT`, e a limitação
    deferida de `input_refs`/`output_refs`.
    """
    session, objects, manager = integrity
    a = _obj(objects, session, accessibility=AccessibilityState.INACCESSIBLE)
    b = _obj(objects, session, accessibility=AccessibilityState.LATENT)

    # Relationship: ciclo legítimo (RELATED_TO é simétrico) e relações
    # contraditórias entre os mesmos objetos — o contrato permite.
    relationships = RelationshipRepository(session)
    relationships.add_relationship(
        source_coid=a.id, target_coid=b.id, relationship_type=RelationshipType.RELATED_TO
    )
    relationships.add_relationship(
        source_coid=a.id, target_coid=b.id, relationship_type=RelationshipType.SUPPORTS
    )
    relationships.add_relationship(
        source_coid=a.id, target_coid=b.id, relationship_type=RelationshipType.CONTRADICTS
    )
    retired = relationships.add_relationship(
        source_coid=b.id, target_coid=a.id, relationship_type=RelationshipType.REFERENCES
    )
    session.flush()
    relationships.retire(retired)
    # ... e recriar a mesma tripla depois de retirar é o lifecycle previsto.
    relationships.add_relationship(
        source_coid=b.id, target_coid=a.id, relationship_type=RelationshipType.REFERENCES
    )

    # Lineage: DAG legítimo.
    LineageRepository(session).add_edge(
        parent_coid=a.id, child_coid=b.id, relation_type=LineageRelation.DERIVED_FROM
    )

    # Provenance sem provider_id/model_id — opcionais por contrato.
    ProvenanceManager(ProvenanceRepository(session)).record(
        coid=a.id,
        source_type=ProvenanceSourceType.AGENT,
        actor_type=ProvenanceActorType.AGENT,
    )

    # Causal: predecessor entre histórias + ramificação, occurred_at=None.
    causal = CausalHistoryManager(CausalHistoryRepository(session))
    origin = causal.record(subject_coid=a.id, event_type=CausalEventType.CREATED)
    causal.record(subject_coid=b.id, event_type=CausalEventType.ACCESSED, predecessor=origin)
    causal.record(subject_coid=a.id, event_type=CausalEventType.COMPARED, predecessor=origin)
    session.flush()

    report = manager.audit()

    assert report.status is IntegrityStatus.PASS, report.findings


def test_real_lineage_cycle_is_detected_on_persisted_patrimony(integrity):
    """Ciclo indireto de linhagem é criável pelas APIs normais — o
    banco só impede o self-link — e a auditoria o encontra. Este é o
    débito que `E3.3` deixou explicitamente para `E3.10`."""
    session, objects, manager = integrity
    a = _obj(objects, session)
    b = _obj(objects, session)
    lineage = LineageRepository(session)
    lineage.add_edge(parent_coid=a.id, child_coid=b.id, relation_type=LineageRelation.DERIVED_FROM)
    lineage.add_edge(parent_coid=b.id, child_coid=a.id, relation_type=LineageRelation.DERIVED_FROM)
    session.flush()

    report = manager.audit()

    assert report.status is IntegrityStatus.FAIL
    (finding,) = [f for f in report.findings if f.code is IntegrityCode.LINEAGE_CYCLE]
    assert set(finding.evidence["involved_coids"]) == {str(a.id), str(b.id)}


def test_audit_does_not_write_to_the_patrimony(integrity):
    """A auditoria não escreve: censo idêntico antes e depois."""
    session, objects, manager = integrity
    a = _obj(objects, session)
    b = _obj(objects, session)
    LineageRepository(session).add_edge(
        parent_coid=a.id, child_coid=b.id, relation_type=LineageRelation.PARENT
    )
    CausalHistoryManager(CausalHistoryRepository(session)).record(
        subject_coid=a.id, event_type=CausalEventType.CREATED
    )
    session.flush()

    def census() -> dict[str, int]:
        return {
            model.__name__: session.query(model).count()
            for model in (CognitiveObject, CausalHistory, CausalHistoryEvent)
        }

    before = census()
    manager.audit()
    manager.audit()
    session.flush()

    assert census() == before
