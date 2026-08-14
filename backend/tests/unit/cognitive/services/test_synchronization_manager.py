"""
Testes unitários de `E3.11`/`LIB-11` — codec, validação de envelope e
ordenação topológica de eventos.

O round-trip real entre duas instâncias PostgreSQL vive em
`tests/integration/cognitive/test_synchronization_integration.py`; aqui
ficam as partes que se testam melhor isoladas: a codificação campo a
campo, a recusa de pacotes inutilizáveis e a ordenação que faz o
predecessor causal entrar antes do sucessor.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa

from app.cognitive.errors.exceptions import SyncPackageInvalidError
from app.cognitive.models.causal_history import CausalHistoryEvent
from app.cognitive.models.cognitive_object import CognitiveObject
from app.cognitive.models.enums import AccessibilityState, CausalEventType, RevisionStatus
from app.cognitive.repositories.sync_repository import (
    SyncRepository,
    ordered_tables,
    topologically_ordered_events,
)
from app.cognitive.schemas.synchronization import (
    SECTION_BY_TABLE,
    SYNC_FORMAT,
    SYNC_SCHEMA_VERSION,
    SyncConflict,
    SyncReport,
    SyncStatus,
    canonical_payload,
    decode_value,
    encode_value,
)
from app.cognitive.services.synchronization_manager import SynchronizationManager


def _empty_package() -> dict:
    package: dict = {
        "format": SYNC_FORMAT,
        "schema_version": SYNC_SCHEMA_VERSION,
        "exported_at": datetime.now(UTC).isoformat(),
    }
    for section in SECTION_BY_TABLE.values():
        package[section] = []
    return package


# --- Codec ------------------------------------------------------------


def test_encode_preserves_uuid_datetime_enum_and_null():
    """S3/S4/S5 — cada tipo tem representação canônica própria, e
    `None` continua `None` em vez de virar string vazia ou default."""
    identifier = uuid.uuid4()
    moment = datetime(2001, 2, 3, 4, 5, 6, tzinfo=UTC)

    assert encode_value(identifier) == str(identifier)
    assert encode_value(moment) == moment.isoformat()
    assert encode_value(AccessibilityState.CAUSALLY_EXTINCT) == "causally_extinct"
    assert encode_value(None) is None
    assert encode_value("texto") == "texto"
    assert encode_value(["a", "b"]) == ["a", "b"]


def test_decode_uses_the_real_column_type():
    """A decodificação é dirigida pelo **tipo da coluna**, não por
    heurística sobre o conteúdo — é o que torna o round-trip
    verificável."""
    columns = CognitiveObject.__table__.c
    identifier = uuid.uuid4()
    moment = datetime(2001, 2, 3, 4, 5, 6, tzinfo=UTC)

    assert decode_value(columns.id, str(identifier)) == identifier
    assert decode_value(columns.created_at, moment.isoformat()) == moment
    assert decode_value(columns.accessibility, "latent") is AccessibilityState.LATENT
    assert decode_value(columns.revision_status, "current") is RevisionStatus.CURRENT
    assert decode_value(columns.clid, None) is None


def test_decode_is_idempotent_for_already_typed_values():
    """Valores já tipados atravessam sem dupla conversão — importante
    porque nem todo dialeto devolve tudo como texto."""
    columns = CognitiveObject.__table__.c
    identifier = uuid.uuid4()
    moment = datetime(2020, 1, 1, tzinfo=UTC)

    assert decode_value(columns.id, identifier) == identifier
    assert decode_value(columns.created_at, moment) == moment


def test_canonical_payload_excludes_only_the_transport_field():
    """`exported_at` é o único campo transportacional: dois exports do
    mesmo patrimônio precisam ser canonicamente iguais."""
    package = _empty_package()
    other = {**package, "exported_at": "2030-01-01T00:00:00+00:00"}

    assert canonical_payload(package) == canonical_payload(other)
    assert "exported_at" not in canonical_payload(package)
    assert set(canonical_payload(package)) == {"format", "schema_version"} | set(
        SECTION_BY_TABLE.values()
    )


# --- Ordem de importação ----------------------------------------------


def test_import_order_is_derived_from_real_foreign_keys():
    """§11 — a ordem vem de `Base.metadata.sorted_tables`, não de
    intuição: toda tabela aparece depois daquelas de que depende."""
    names = [table.name for table in ordered_tables()]

    assert set(names) == set(SECTION_BY_TABLE)
    assert names.index("cognitive_objects") < names.index("lineage_edges")
    assert names.index("cognitive_objects") < names.index("provenance_records")
    assert names.index("causal_histories") < names.index("causal_history_events")
    assert names.index("provenance_records") < names.index("causal_history_events")


def test_events_are_ordered_so_predecessors_come_first():
    """A FK de `predecessor_event_id` é validada linha a linha, então
    um evento precisa entrar depois do seu predecessor — inclusive
    quando o pacote lista o sucessor primeiro."""
    first, second, third = (uuid.uuid4() for _ in range(3))
    rows = [
        {"id": third, "predecessor_event_id": second},
        {"id": second, "predecessor_event_id": first},
        {"id": first, "predecessor_event_id": None},
    ]

    ordered = [row["id"] for row in topologically_ordered_events(rows)]

    assert ordered == [first, second, third]


def test_events_with_external_predecessor_are_not_postponed():
    """Evento cujo predecessor **não está no pacote** (já presente no
    destino, por exemplo) entra na ordem natural — a FK do banco
    decide, e adiar indefinidamente seria inventar política."""
    external = uuid.uuid4()
    local = uuid.uuid4()
    rows = [{"id": local, "predecessor_event_id": external}]

    ordered = [row["id"] for row in topologically_ordered_events(rows)]

    assert ordered == [local]


def test_event_ordering_terminates_even_with_a_cyclic_package():
    """Um pacote corrompido com ciclo causal não trava a ordenação: ela
    termina e devolve todos os registros. Detectar ciclo é do
    `IntegrityManager` (`E3.10`), não desta função — e o banco recusa a
    inserção de qualquer forma."""
    first, second = uuid.uuid4(), uuid.uuid4()
    rows = [
        {"id": first, "predecessor_event_id": second},
        {"id": second, "predecessor_event_id": first},
    ]

    ordered = topologically_ordered_events(rows)

    assert len(ordered) == 2
    assert {row["id"] for row in ordered} == {first, second}


# --- Envelope ---------------------------------------------------------


@pytest.fixture
def manager(cognitive_session):
    return SynchronizationManager(SyncRepository(cognitive_session))


def test_unusable_packages_are_rejected_before_any_write(manager):
    """S23 — cada forma de pacote inutilizável tem recusa própria e
    explícita, antes de escrever qualquer coisa."""
    package = _empty_package()

    cases = [
        ("não é um objeto", ["não", "é", "dict"]),
        ("formato desconhecido", {**package, "format": "outro"}),
        ("versão de schema", {**package, "schema_version": "0.1"}),
        ("seção ausente", {k: v for k, v in package.items() if k != "lineage"}),
        ("não é uma lista", {**package, "objects": {"id": "x"}}),
    ]
    for expected, broken in cases:
        with pytest.raises(SyncPackageInvalidError, match=expected):
            manager.import_package(broken)  # type: ignore[arg-type]


def test_rows_without_id_are_rejected(manager):
    package = {**_empty_package(), "objects": [{"clid": None}]}

    with pytest.raises(SyncPackageInvalidError, match="sem 'id'"):
        manager.import_package(package)


def test_invalid_uuid_is_rejected(manager):
    package = {**_empty_package(), "objects": [{"id": "não-é-uuid"}]}

    with pytest.raises(SyncPackageInvalidError, match="id inválido"):
        manager.import_package(package)


def test_unknown_field_is_rejected(manager):
    package = {
        **_empty_package(),
        "objects": [{"id": str(uuid.uuid4()), "campo_inventado": 1}],
    }

    with pytest.raises(SyncPackageInvalidError, match="campo desconhecido"):
        manager.import_package(package)


def test_invalid_enum_value_is_rejected(manager):
    package = {
        **_empty_package(),
        "objects": [
            {
                "id": str(uuid.uuid4()),
                "accessibility": "estado_inexistente",
                "created_at": datetime.now(UTC).isoformat(),
                "updated_at": datetime.now(UTC).isoformat(),
            }
        ],
    }

    with pytest.raises(SyncPackageInvalidError, match="valor inválido"):
        manager.import_package(package)


def test_empty_package_round_trip_is_a_no_op(manager, cognitive_session):
    """S6 — vazio → export/import → vazio: nada é aplicado e nada é
    inventado."""
    report = manager.import_package(_empty_package())

    assert report.status is SyncStatus.APPLIED
    assert report.applied_count == 0
    assert report.skipped_count == 0
    assert cognitive_session.query(CognitiveObject).count() == 0


def test_export_of_empty_patrimony_has_every_section(manager):
    """O pacote sempre declara todas as seções, mesmo vazias — um
    destino nunca precisa adivinhar se a seção faltou ou estava
    vazia."""
    package = manager.export_package()

    assert package["format"] == SYNC_FORMAT
    assert set(SECTION_BY_TABLE.values()) <= set(package)
    assert all(package[section] == [] for section in SECTION_BY_TABLE.values())
    # Primitivas ainda DEFERRED não ganham seção fantasma.
    assert not {s for s in package if "distinction" in s or "comparison" in s}


# --- Relatório --------------------------------------------------------


def test_conflict_reports_the_differing_fields():
    """O conflito localiza **quais** campos divergem — evidência, não
    apenas "há conflito"."""
    entity = uuid.uuid4()
    conflict = SyncConflict(
        section="objects",
        entity_id=entity,
        incoming={"id": str(entity), "accessibility": "active", "clid": None},
        existing={"id": str(entity), "accessibility": "latent", "clid": None},
    )

    assert conflict.differing_fields == ("accessibility",)


def test_report_status_and_counts_are_derived():
    """`status` deriva dos conflitos, e `overwrite_count` existe para
    ser verificavelmente zero."""
    clean = SyncReport(applied={"objects": 2}, skipped={"lineage": 1})
    conflicted = SyncReport(
        conflicts=(
            SyncConflict(section="objects", entity_id=uuid.uuid4(), incoming={}, existing={}),
        )
    )

    assert clean.status is SyncStatus.APPLIED
    assert clean.applied_count == 2
    assert clean.skipped_count == 1
    assert clean.overwrite_count == 0
    assert conflicted.status is SyncStatus.CONFLICT
    assert conflicted.overwrite_count == 0


def test_encode_row_uses_the_result_mapping():
    """`encode_row` serializa a linha inteira pelo mapping do
    resultado, sem depender da ordem das colunas."""
    row = sa.select(
        sa.literal(str(uuid.uuid4())).label("id"), sa.literal(None).label("clid")
    ).subquery()
    result = sa.create_engine("sqlite://").connect().execute(sa.select(row)).one()

    from app.cognitive.schemas.synchronization import encode_row

    encoded = encode_row(result)

    assert set(encoded) == {"id", "clid"}
    assert encoded["clid"] is None


def test_causal_event_table_is_the_only_one_needing_topological_order():
    """Só `causal_history_events` tem auto-referência — por isso é a
    única tabela com ordenação interna própria."""
    self_referencing = [
        table.name
        for table in ordered_tables()
        if any(fk.column.table is table for column in table.c for fk in column.foreign_keys)
    ]

    assert self_referencing == [CausalHistoryEvent.__tablename__]
    assert CausalEventType is not None  # vocabulário fechado permanece em uso
