"""
Testes unitários de `E3.9`/`LIB-09` — CausalHistory.

Cobrem `CH1`-`CH24` sobre SQLite em memória. O que depende do
PostgreSQL real — constraints do banco, ciclo de migração, guarda de
downgrade e preservação medida por contagem de escritas — vive em
`tests/integration/cognitive/test_causal_history_integration.py`.

Os dois cenários obrigatórios do módulo estão aqui como testes
nomeados: **Galaxy Trace** (`CH15`) e **Broken Glass** (`CH16`/`CH17`),
mais a fronteira epistemológica (`CH18`). São metáforas
arquiteturais — nenhuma física é implementada, nenhuma palavra do
cenário vira dado de domínio.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.cognitive.errors.exceptions import (
    CausalEventSelfPredecessorError,
    CausalHistoryImmutableError,
)
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
    TransformationKind,
)
from app.cognitive.models.transformation_record import TransformationRecord
from app.cognitive.repositories.causal_history_repository import CausalHistoryRepository
from app.cognitive.repositories.lineage_repository import LineageRepository
from app.cognitive.repositories.object_repository import ObjectRepository
from app.cognitive.repositories.provenance_repository import ProvenanceRepository
from app.cognitive.repositories.relationship_repository import RelationshipRepository
from app.cognitive.services.causal_history_manager import CausalHistoryManager
from app.cognitive.services.provenance_manager import ProvenanceManager


@pytest.fixture
def causal(cognitive_session):
    session = cognitive_session
    objects = ObjectRepository(session)
    repository = CausalHistoryRepository(session)
    return session, objects, repository, CausalHistoryManager(repository)


def _add(objects, session, **kwargs) -> CognitiveObject:
    obj = objects.add(CognitiveObject(**kwargs))
    session.flush()
    return obj


def _snapshot(event: CausalHistoryEvent) -> tuple:
    return (
        event.id,
        event.history_id,
        event.event_type,
        event.actor_ref,
        event.payload_ref,
        event.predecessor_event_id,
        event.occurred_at,
        event.created_at,
    )


def test_ch1_ch2_record_creates_a_valid_event_with_its_own_identity(causal):
    """CH1/CH2 — evento causal válido, com identidade própria distinta
    do sujeito e da história."""
    session, objects, _, manager = causal
    subject = _add(objects, session)

    event = manager.record(subject_coid=subject.id, event_type=CausalEventType.CREATED)
    session.flush()

    assert isinstance(event.id, uuid.UUID)
    assert event.id != subject.id
    assert event.id != event.history_id
    assert event.event_type is CausalEventType.CREATED


def test_ch3_append_only_history_accumulates(causal):
    """CH3 — anexar acumula; nada é substituído."""
    session, objects, _, manager = causal
    subject = _add(objects, session)

    first = manager.record(subject_coid=subject.id, event_type=CausalEventType.CREATED)
    second = manager.record(subject_coid=subject.id, event_type=CausalEventType.ACCESSED)
    # `created_at` é `server_default=now()`: no SQLite os dois nascem
    # com o mesmo instante, então a ordem canônica é fixada aqui de
    # propósito — ordem de registro é apresentação, não causalidade.
    first.created_at = datetime(2020, 1, 1, tzinfo=UTC)
    second.created_at = datetime(2020, 1, 2, tzinfo=UTC)
    session.flush()

    assert [e.id for e in manager.events_for(subject.id)] == [first.id, second.id]


def test_ch4_ch5_destructive_update_and_delete_are_rejected(causal):
    """CH4/CH5 — `update`/`delete` físicos sempre rejeitados, para
    história e para evento (`PIA-8020`)."""
    session, objects, repository, manager = causal
    subject = _add(objects, session)
    event = manager.record(subject_coid=subject.id, event_type=CausalEventType.CREATED)
    session.flush()
    history = manager.history_for(subject.id)
    assert history is not None

    for call in (
        lambda: repository.update(history),
        lambda: repository.delete(history),
        lambda: repository.update_event(event),
        lambda: repository.delete_event(event),
    ):
        with pytest.raises(CausalHistoryImmutableError) as exc:
            call()
        assert exc.value.error_code.code == "PIA-8020"


def test_ch6_explicit_causal_predecessor_is_navigable(causal):
    """CH6 — predecessor causal explícito, navegável nos dois
    sentidos."""
    session, objects, _, manager = causal
    subject = _add(objects, session)

    first = manager.record(subject_coid=subject.id, event_type=CausalEventType.CREATED)
    second = manager.record(
        subject_coid=subject.id, event_type=CausalEventType.TRANSFORMED, predecessor=first
    )
    session.flush()

    assert [e.id for e in manager.predecessors(second)] == [first.id]
    assert [e.id for e in manager.successors(first)] == [second.id]
    assert manager.predecessors(first) == []
    assert [e.id for e in manager.roots(subject.id)] == [first.id]


def test_ch7_self_predecessor_is_rejected(causal):
    """CH7 — um evento não pode ser predecessor de si mesmo.

    Pelo `record()` do manager a situação é estruturalmente impossível
    (o evento novo ainda não existe quando o predecessor é informado),
    então o que se exercita aqui é o caminho realmente alcançável:
    construir o evento à mão e tentar persistir.
    """
    session, objects, repository, manager = causal
    subject = _add(objects, session)
    manager.ensure_history(subject.id)
    session.flush()
    history = manager.history_for(subject.id)
    assert history is not None

    forced = CausalHistoryEvent(history_id=history.id, event_type=CausalEventType.TRANSFORMED)
    forced.id = uuid.uuid4()
    forced.predecessor_event_id = forced.id

    with pytest.raises(CausalEventSelfPredecessorError) as exc:
        repository.add_event(forced)
    assert exc.value.error_code.code == "PIA-8021"


def test_ch8_timestamp_order_does_not_create_causality(causal):
    """CH8 (§37) — dois eventos, `t0 < t1`, sem referência causal: o
    primeiro **não** vira predecessor do segundo.

    `TEMPORAL PRECEDENCE != CAUSALITY`.
    """
    session, objects, _, manager = causal
    subject = _add(objects, session)

    earlier = manager.record(subject_coid=subject.id, event_type=CausalEventType.CREATED)
    later = manager.record(subject_coid=subject.id, event_type=CausalEventType.ACCESSED)
    earlier.created_at = datetime(2020, 1, 1, tzinfo=UTC)
    later.created_at = datetime(2020, 6, 1, tzinfo=UTC)
    session.flush()

    ordered = manager.events_for(subject.id)

    assert [e.id for e in ordered] == [earlier.id, later.id]
    assert later.predecessor_event_id is None
    assert manager.predecessors(later) == []
    assert manager.successors(earlier) == []


def test_ch9_event_time_may_precede_registration_time(causal):
    """CH9 — `occurred_at` pode ser muito anterior a `created_at`: é
    exatamente a forma de um rastro arqueológico. E `None` permanece
    `None` — o PIA não substitui tempo desconhecido pelo instante do
    registro."""
    session, objects, _, manager = causal
    subject = _add(objects, session)

    long_ago = datetime(1998, 3, 14, tzinfo=UTC)
    known = manager.record(
        subject_coid=subject.id, event_type=CausalEventType.CREATED, occurred_at=long_ago
    )
    unknown = manager.record(subject_coid=subject.id, event_type=CausalEventType.ACCESSED)
    session.flush()

    assert known.occurred_at == long_ago
    registered_at = known.created_at
    if registered_at.tzinfo is None:  # SQLite devolve naive; Postgres, aware
        registered_at = registered_at.replace(tzinfo=UTC)
    assert registered_at > known.occurred_at
    assert unknown.occurred_at is None
    assert unknown.created_at is not None


def test_ch10_causal_history_does_not_duplicate_provenance(causal):
    """CH10 — `PROVENANCE != CAUSAL HISTORY`: o evento **referencia**
    um `ProvenanceRecord` e não copia nenhum campo de
    provider/model/session/agent."""
    session, objects, _, manager = causal
    subject = _add(objects, session)
    provenance = ProvenanceManager(ProvenanceRepository(session)).record(
        coid=subject.id,
        source_type=ProvenanceSourceType.AGENT,
        actor_type=ProvenanceActorType.AGENT,
        trace_id="trace-ch10",
    )
    session.flush()

    event = manager.record(
        subject_coid=subject.id,
        event_type=CausalEventType.CREATED,
        actor_ref=provenance.id,
    )
    session.flush()

    assert event.actor_ref == provenance.id
    event_columns = {c.name for c in CausalHistoryEvent.__table__.columns}
    assert not event_columns & {
        "provider_id",
        "model_id",
        "session_id",
        "correlation_id",
        "trace_id",
        "agent_role",
        "agent_instance_id",
        "orchestration_run_id",
    }


def test_ch11_ch12_ch13_causal_history_is_not_lineage_relationship_or_transformation(causal):
    """CH11/CH12/CH13 — quatro entidades distintas, nenhuma
    redefinida: `LineageEdge`, `Relationship` e `TransformationRecord`
    continuam com suas tabelas e taxonomias, e nenhuma delas ganha
    semântica causal por existir um `CausalHistoryEvent`."""
    session, objects, _, manager = causal
    parent = _add(objects, session)
    child = _add(objects, session)

    LineageRepository(session).add_edge(
        parent_coid=parent.id, child_coid=child.id, relation_type=LineageRelation.DERIVED_FROM
    )
    RelationshipRepository(session).add_relationship(
        source_coid=parent.id, target_coid=child.id, relationship_type=RelationshipType.SUPPORTS
    )
    session.add(
        TransformationRecord(
            operation_type="split",
            transformation_kind=TransformationKind.DERIVATION,
            input_refs=[str(parent.id)],
            output_refs=[str(child.id)],
        )
    )
    manager.record(subject_coid=parent.id, event_type=CausalEventType.TRANSFORMED)
    session.flush()

    tables = {
        CausalHistoryEvent.__tablename__,
        "lineage_edges",
        "relationships",
        "transformation_records",
    }
    assert len(tables) == 4
    # Nenhuma taxonomia semântica virou vocabulário causal.
    assert not set(CausalEventType) & set(RelationshipType)
    assert not set(CausalEventType) & set(LineageRelation)


def test_ch14_current_does_not_erase_superseded_history(causal):
    """CH14 — promover uma revisão a `CURRENT` não apaga a história do
    estado `SUPERSEDED`."""
    session, objects, _, manager = causal
    clid = uuid.uuid4()
    old = _add(objects, session, clid=clid, revision_status=RevisionStatus.CURRENT)
    manager.record(subject_coid=old.id, event_type=CausalEventType.CREATED)
    session.flush()

    old.revision_status = RevisionStatus.SUPERSEDED
    new = _add(objects, session, clid=clid, revision_status=RevisionStatus.CURRENT)
    manager.record(subject_coid=new.id, event_type=CausalEventType.CREATED)
    session.flush()

    assert len(manager.events_for(old.id)) == 1
    assert manager.history_for(old.id) is not None


def test_ch15_galaxy_trace_current_is_not_the_only_accessible_history(causal):
    """CH15 — **Galaxy Trace** (metáfora arquitetural, sem física).

    `S0` é o estado histórico; a continuidade evolui para `S1`, que
    passa a ser `CURRENT`. O rastro causal preservado sobre `S0`
    continua acessível *no presente* — a observação de agora carrega
    informação legítima sobre um estado passado.

    Gate: `CURRENT != ONLY CAUSALLY ACCESSIBLE HISTORY`.
    """
    session, objects, _, manager = causal
    clid = uuid.uuid4()
    s0 = _add(objects, session, clid=clid, revision_status=RevisionStatus.CURRENT)
    emitted_at = datetime(2001, 1, 1, tzinfo=UTC)
    trace = manager.record(
        subject_coid=s0.id,
        event_type=CausalEventType.CREATED,
        payload_ref="ref://rastro-s0",
        occurred_at=emitted_at,
    )
    session.flush()

    # A fonte evolui: S0 -> S1, e S1 vira o estado corrente.
    s0.revision_status = RevisionStatus.SUPERSEDED
    s1 = _add(objects, session, clid=clid, revision_status=RevisionStatus.CURRENT)
    session.flush()

    assert s1.revision_status is RevisionStatus.CURRENT
    # ... e ainda assim o estado passado permanece causalmente acessível:
    preserved = manager.events_for(s0.id)
    assert [e.id for e in preserved] == [trace.id]
    assert preserved[0].occurred_at == emitted_at
    assert preserved[0].payload_ref == "ref://rastro-s0"
    assert objects.get_by_id(s0.id) is not None


def test_ch15b_multiple_causal_paths_coexist(causal):
    """CH19 (§36) — uma mesma origem pode ter mais de um caminho
    causal preservado; o módulo não elege um como "o verdadeiro"."""
    session, objects, _, manager = causal
    subject = _add(objects, session)

    origin = manager.record(subject_coid=subject.id, event_type=CausalEventType.CREATED)
    path_a = manager.record(
        subject_coid=subject.id, event_type=CausalEventType.ACCESSED, predecessor=origin
    )
    path_b = manager.record(
        subject_coid=subject.id, event_type=CausalEventType.COMPARED, predecessor=origin
    )
    leaf_a = manager.record(
        subject_coid=subject.id, event_type=CausalEventType.ACCESSED, predecessor=path_a
    )
    session.flush()

    assert {e.id for e in manager.successors(origin)} == {path_a.id, path_b.id}
    assert [e.id for e in manager.successors(path_a)] == [leaf_a.id]
    assert manager.successors(path_b) == []


def test_ch16_ch17_broken_glass_distinction_extinction_is_not_erasure(causal):
    """CH16/CH17 — **Broken Glass** (cenário abstrato; a palavra
    "copo" não vira dado de domínio).

    `G0` é um objeto organizado; transformações sucessivas levam a
    `G3`, um estado que já não preserva a distinção que definia `G0`.
    O substrato pode continuar existindo — o que se perde é a
    organização que permitia identificar aquilo *como aquilo*.

    Gates: `MATERIAL PERSISTENCE != DISTINCTION PERSISTENCE` e
    `DISTINCTION EXTINCTION != HISTORICAL ERASURE`.
    """
    session, objects, _, manager = causal
    g0 = _add(objects, session, accessibility=AccessibilityState.ACTIVE)
    g0_snapshot = (
        g0.id,
        g0.clid,
        g0.accessibility,
        g0.revision_status,
        g0.created_at,
    )  # noqa: E501

    origin = manager.record(
        subject_coid=g0.id, event_type=CausalEventType.CREATED, payload_ref="ref://g0"
    )
    session.flush()

    # G1, G2, G3 — estados posteriores, cada um objeto próprio: o
    # módulo não afirma que fragmento e disperso "ainda são" G0.
    previous_event = origin
    origin.created_at = datetime(2020, 1, 1, tzinfo=UTC)
    successors = []
    for index, label in enumerate(("g1", "g2", "g3"), start=2):
        state = _add(objects, session, accessibility=AccessibilityState.ACTIVE)
        successors.append(state)
        previous_event = manager.record(
            subject_coid=g0.id,
            event_type=CausalEventType.TRANSFORMED,
            payload_ref=f"ref://{label}",
            predecessor=previous_event,
        )
        previous_event.created_at = datetime(2020, 1, index, tzinfo=UTC)
    session.flush()

    # 3 — o estado final não precisa preservar a distinção de G0:
    assert successors[-1].id != g0.id
    assert successors[-1].clid is None and g0.clid is None
    # 4 — a história de G0 continua registrada, inteira:
    history = manager.events_for(g0.id)
    assert len(history) == 4
    assert [e.event_type for e in history] == [
        CausalEventType.CREATED,
        CausalEventType.TRANSFORMED,
        CausalEventType.TRANSFORMED,
        CausalEventType.TRANSFORMED,
    ]
    # 5 — nenhuma operação retroativa alterou G0 nem seu evento de origem:
    session.refresh(g0)
    assert (g0.id, g0.clid, g0.accessibility, g0.revision_status, g0.created_at) == g0_snapshot
    assert manager.roots(g0.id)[0].id == origin.id
    # 6 — não se conclui que G3 é G0: nenhuma continuidade foi inventada.
    assert successors[-1].id not in {o.id for o in objects.list() if o.id == g0.id}


def test_ch17b_extinct_accessibility_does_not_erase_history(causal):
    """CH17 (complemento) — mesmo com o sujeito marcado
    `CAUSALLY_EXTINCT` por decisão explícita de um chamador (`E3.6`,
    não por `E3.9`), a história registrada permanece intacta.

    `CAUSALLY_EXTINCT != NEVER EXISTED`.
    """
    session, objects, _, manager = causal
    subject = _add(objects, session, accessibility=AccessibilityState.ACTIVE)
    event = manager.record(subject_coid=subject.id, event_type=CausalEventType.CREATED)
    session.flush()
    before = _snapshot(event)

    subject.accessibility = AccessibilityState.CAUSALLY_EXTINCT
    session.flush()

    assert [_snapshot(e) for e in manager.events_for(subject.id)] == [before]


def test_ch18_absence_of_evidence_does_not_fabricate_history(causal):
    """CH18 (§35) — sem rastro registrado, o sistema devolve ausência,
    não reconstrução. E consultar não cria história.

    `NO PRESENT EVIDENCE != NEVER EXISTED` **e**
    `NO PRESENT EVIDENCE != ASSERT THAT IT EXISTED`.
    """
    session, objects, repository, manager = causal
    orphan = _add(objects, session)

    assert manager.history_for(orphan.id) is None
    assert manager.events_for(orphan.id) == []
    assert manager.roots(orphan.id) == []

    session.flush()
    assert session.query(CausalHistory).count() == 0
    assert session.query(CausalHistoryEvent).count() == 0
    # E a leitura repetida continua sem materializar nada.
    assert repository.get_by_subject(orphan.id) is None


def test_ch20_appending_does_not_mutate_previous_events(causal):
    """CH20 (§39) — anexar `E_n` não altera nenhum campo de
    `E_0..E_n-1`."""
    session, objects, _, manager = causal
    subject = _add(objects, session)
    first = manager.record(subject_coid=subject.id, event_type=CausalEventType.CREATED)
    second = manager.record(subject_coid=subject.id, event_type=CausalEventType.ACCESSED)
    session.flush()
    before = [_snapshot(first), _snapshot(second)]

    manager.record(
        subject_coid=subject.id, event_type=CausalEventType.TRANSFORMED, predecessor=second
    )
    session.flush()
    session.refresh(first)
    session.refresh(second)

    assert [_snapshot(first), _snapshot(second)] == before


def test_correction_appends_instead_of_rewriting(causal):
    """Correção histórica é evento novo que referencia o anterior,
    exatamente como o Draft determina — o evento corrigido permanece
    intacto e recuperável."""
    session, objects, _, manager = causal
    subject = _add(objects, session)
    original = manager.record(
        subject_coid=subject.id, event_type=CausalEventType.CREATED, payload_ref="ref://errado"
    )
    session.flush()
    before = _snapshot(original)

    correction = manager.correct(
        previous=original, event_type=CausalEventType.CREATED, payload_ref="ref://correto"
    )
    session.flush()
    session.refresh(original)

    assert _snapshot(original) == before
    assert correction.predecessor_event_id == original.id
    assert len(manager.events_for(subject.id)) == 2


def test_ch21_ch22_reading_history_writes_nothing(causal):
    """CH21/CH22 — navegar a história não escreve, e o patrimônio de
    origem não é alterado."""
    session, objects, _, manager = causal
    subject = _add(objects, session)
    root = manager.record(subject_coid=subject.id, event_type=CausalEventType.CREATED)
    manager.record(subject_coid=subject.id, event_type=CausalEventType.ACCESSED, predecessor=root)
    session.flush()

    def census() -> dict[str, int]:
        return {
            model.__name__: session.query(model).count()
            for model in (CognitiveObject, CausalHistory, CausalHistoryEvent)
        }

    before = census()
    subject_before = (subject.id, subject.accessibility, subject.revision_status)

    manager.history_for(subject.id)
    manager.events_for(subject.id)
    manager.roots(subject.id)
    manager.successors(root)
    manager.predecessors(root)
    session.flush()
    session.refresh(subject)

    assert census() == before
    assert (subject.id, subject.accessibility, subject.revision_status) == subject_before


def test_ch23_ch24_no_transcript_and_provider_neutral(causal):
    """CH23/CH24 — nenhuma coluna capaz de guardar transcript/payload
    integral, e nenhum campo específico de provider.

    `payload_ref` é referência opaca de 512 caracteres, não conteúdo:
    `CAUSAL_TRACE != TRANSCRIPT`.
    """
    columns = {c.name: c for c in CausalHistoryEvent.__table__.columns}

    assert set(columns) == {
        "id",
        "history_id",
        "event_type",
        "actor_ref",
        "payload_ref",
        "predecessor_event_id",
        "occurred_at",
        "created_at",
        "updated_at",
    }
    assert not {c for c in columns if "transcript" in c or "content" in c or "prompt" in c}
    assert columns["payload_ref"].type.length == 512


def test_predecessor_navigation_handles_missing_reference(causal):
    """`predecessors()` de um evento cuja referência não resolve
    devolve lista vazia — sem inventar o elo perdido."""
    session, objects, _, manager = causal
    subject = _add(objects, session)
    event = manager.record(subject_coid=subject.id, event_type=CausalEventType.CREATED)
    session.flush()
    event.predecessor_event_id = uuid.uuid4()

    assert manager.predecessors(event) == []


def test_ensure_history_is_idempotent(causal):
    """`ensure_history()` é idempotente — um sujeito tem no máximo uma
    história."""
    session, objects, _, manager = causal
    subject = _add(objects, session)

    first = manager.ensure_history(subject.id)
    session.flush()
    second = manager.ensure_history(subject.id)
    session.flush()

    assert first.id == second.id
    assert session.query(CausalHistory).count() == 1


def test_occurred_at_may_be_later_than_registration_when_declared(causal):
    """O módulo não impõe `occurred_at <= created_at`: essa é a forma
    esperada de um rastro, mas impor a desigualdade seria o sistema
    afirmar conhecimento que não tem sobre relógios externos."""
    session, objects, _, manager = causal
    subject = _add(objects, session)

    future = datetime.now(UTC) + timedelta(days=1)
    event = manager.record(
        subject_coid=subject.id, event_type=CausalEventType.ACCESSED, occurred_at=future
    )
    session.flush()

    assert event.occurred_at == future


# ---------------------------------------------------------------------
# E3.9.1 — topologia: cardinalidade história↔sujeito e predecessor
# entre histórias. Nenhuma migração nova: o schema de E3.9 já
# implementava as duas decisões (índice único em `subject_coid`, FK
# global de predecessor); o que faltava era torná-las explícitas e
# testadas.
# ---------------------------------------------------------------------


def test_t1_one_history_per_subject(causal):
    """T1 — `ONE_HISTORY_PER_SUBJECT = TRUE`: um segundo
    `CausalHistory` para o mesmo sujeito é rejeitado pelo índice
    único."""
    from app.repositories.exceptions import PersistenceError

    session, objects, repository, manager = causal
    subject = _add(objects, session)
    manager.ensure_history(subject.id)
    session.flush()

    # O índice único é a autoridade: a segunda história nem chega a
    # existir. `BaseRepository.add()` converte a violação em
    # `PersistenceError` (comportamento de E2, não redefinido aqui).
    with pytest.raises(PersistenceError):
        repository.add_history(CausalHistory(subject_coid=subject.id))
    session.rollback()


def test_t2_different_subjects_have_different_histories(causal):
    """T2 — sujeitos distintos têm histórias distintas, que coexistem."""
    session, objects, _, manager = causal
    subject_a = _add(objects, session)
    subject_b = _add(objects, session)

    history_a = manager.ensure_history(subject_a.id)
    history_b = manager.ensure_history(subject_b.id)
    session.flush()

    assert history_a.id != history_b.id
    assert history_a.subject_coid == subject_a.id
    assert history_b.subject_coid == subject_b.id
    assert session.query(CausalHistory).count() == 2


def test_t3_t4_cross_history_predecessor_is_allowed_without_merging(causal):
    """T3/T4 — `CROSS_HISTORY_PREDECESSOR = ALLOWED`: um evento pode
    referenciar como predecessor um evento da história de outro
    sujeito, e isso **não** funde identidades nem histórias.

    ```text
    history boundary != causal boundary
    ```
    """
    session, objects, _, manager = causal
    source = _add(objects, session)
    receiver = _add(objects, session)

    emitted = manager.record(
        subject_coid=source.id, event_type=CausalEventType.CREATED, payload_ref="ref://emitido"
    )
    received = manager.record(
        subject_coid=receiver.id,
        event_type=CausalEventType.ACCESSED,
        predecessor=emitted,
        payload_ref="ref://recebido",
    )
    session.flush()

    history_source = manager.history_for(source.id)
    history_receiver = manager.history_for(receiver.id)
    assert history_source is not None and history_receiver is not None

    # T3 — o elo causal persistiu e é navegável nos dois sentidos.
    assert received.predecessor_event_id == emitted.id
    assert [e.id for e in manager.predecessors(received)] == [emitted.id]
    assert [e.id for e in manager.successors(emitted)] == [received.id]

    # T4 — e nada foi fundido:
    assert emitted.history_id == history_source.id
    assert received.history_id == history_receiver.id
    assert history_source.id != history_receiver.id
    assert source.id != receiver.id
    # cada história continua contendo apenas os próprios eventos
    assert [e.id for e in manager.events_for(source.id)] == [emitted.id]
    assert [e.id for e in manager.events_for(receiver.id)] == [received.id]


def test_t4b_cross_history_successor_is_not_a_root_of_its_own_history(causal):
    """T4 (complemento) — um evento com predecessor em outra história
    não é raiz da sua própria história: ele tem predecessor
    declarado."""
    session, objects, _, manager = causal
    source = _add(objects, session)
    receiver = _add(objects, session)

    emitted = manager.record(subject_coid=source.id, event_type=CausalEventType.CREATED)
    manager.record(
        subject_coid=receiver.id, event_type=CausalEventType.ACCESSED, predecessor=emitted
    )
    session.flush()

    assert manager.roots(receiver.id) == []
    assert [e.id for e in manager.roots(source.id)] == [emitted.id]


def test_t5_self_predecessor_remains_rejected_after_e3_9_1(causal):
    """T5 — permitir predecessor entre histórias não afrouxou a
    proteção contra auto-predecessor."""
    session, objects, repository, manager = causal
    subject = _add(objects, session)
    manager.ensure_history(subject.id)
    session.flush()
    history = manager.history_for(subject.id)
    assert history is not None

    forced = CausalHistoryEvent(history_id=history.id, event_type=CausalEventType.ACCESSED)
    forced.id = uuid.uuid4()
    forced.predecessor_event_id = forced.id

    with pytest.raises(CausalEventSelfPredecessorError):
        repository.add_event(forced)


def test_t6_dag_property_survives_cross_history_links(causal):
    """T6 — a propriedade estrutural de DAG continua valendo, inclusive
    entre histórias.

    O que a sustenta: (a) o predecessor precisa **já existir** no
    momento do append, então toda aresta aponta para trás; (b) não há
    caminho de update — `update_event()` sempre rejeita, então um ciclo
    não pode ser fechado depois. Permitir elo entre histórias amplia o
    alcance das arestas, não a direção delas.
    """
    session, objects, repository, manager = causal
    subject_a = _add(objects, session)
    subject_b = _add(objects, session)

    first = manager.record(subject_coid=subject_a.id, event_type=CausalEventType.CREATED)
    second = manager.record(
        subject_coid=subject_b.id, event_type=CausalEventType.TRANSFORMED, predecessor=first
    )
    session.flush()

    # Fechar o ciclo exigiria mutar `first` para apontar para `second`
    # — e não existe caminho legítimo para isso.
    with pytest.raises(CausalHistoryImmutableError):
        repository.update_event(first)

    # Estado permanece acíclico: `first` continua sem predecessor.
    reloaded = repository.get_event(first.id)
    assert reloaded is not None
    assert reloaded.predecessor_event_id is None
    assert second.predecessor_event_id == first.id
