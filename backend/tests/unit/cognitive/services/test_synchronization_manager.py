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
    termina e devolve todos os registros.

    **`ORDERING != VALIDATION`** (`E3.11.1`): esta função ordena, não
    valida. Quem rejeita ciclo é o preflight causal do
    `SynchronizationManager`, **antes** de qualquer escrita — e a
    rejeição não é delegada ao PostgreSQL, que garante FK e
    auto-predecessor mas **não** aciclicidade global
    (`DB_LEVEL_GLOBAL_DAG_GUARANTEE = FALSE`). Terminar diante de um
    ciclo é robustez desta função, nunca garantia de integridade
    causal."""
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


# ---------------------------------------------------------------------
# E3.11.1 — preflight causal: o novo caminho autorizado de escrita não
# pode enfraquecer APPLICATION_STRUCTURAL_DAG.
# ---------------------------------------------------------------------


def _causal_package(events: list[dict[str, object]]) -> dict[str, object]:
    package = _empty_package()
    package["causal_events"] = events
    return package


def test_cd1_valid_causal_package_passes_preflight(manager):
    """CD1 — cadeia simples `E3 → E2 → E1` passa: o preflight rejeita
    ciclo, não profundidade."""
    first, second, third = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    manager._assert_causal_acyclicity(
        _causal_package(
            [
                {"id": str(first), "predecessor_event_id": None},
                {"id": str(second), "predecessor_event_id": str(first)},
                {"id": str(third), "predecessor_event_id": str(second)},
            ]
        )
    )


def test_cd1b_branching_and_multiple_paths_pass_preflight(manager):
    """CD2/CD3 — ramificação (`E2 → E1`, `E3 → E1`) e múltiplos
    caminhos causais não são ciclo. Nenhuma trajetória é colapsada."""
    origin, branch_a, branch_b, leaf = (uuid.uuid4() for _ in range(4))

    manager._assert_causal_acyclicity(
        _causal_package(
            [
                {"id": str(origin), "predecessor_event_id": None},
                {"id": str(branch_a), "predecessor_event_id": str(origin)},
                {"id": str(branch_b), "predecessor_event_id": str(origin)},
                {"id": str(leaf), "predecessor_event_id": str(branch_a)},
            ]
        )
    )


def test_cd2_two_event_cycle_in_the_package_is_rejected(manager):
    """CD2 — ciclo de dois eventos dentro do pacote é rejeitado com
    `PIA-8022`, antes de qualquer escrita."""
    first, second = uuid.uuid4(), uuid.uuid4()

    with pytest.raises(SyncPackageInvalidError) as exc:
        manager._assert_causal_acyclicity(
            _causal_package(
                [
                    {"id": str(first), "predecessor_event_id": str(second)},
                    {"id": str(second), "predecessor_event_id": str(first)},
                ]
            )
        )

    assert exc.value.error_code.code == "PIA-8022"
    assert "ciclo" in str(exc.value)


def test_cd3_three_event_cycle_in_the_package_is_rejected(manager):
    """CD3 — ciclo de três eventos também é rejeitado."""
    first, second, third = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    with pytest.raises(SyncPackageInvalidError):
        manager._assert_causal_acyclicity(
            _causal_package(
                [
                    {"id": str(first), "predecessor_event_id": str(second)},
                    {"id": str(second), "predecessor_event_id": str(third)},
                    {"id": str(third), "predecessor_event_id": str(first)},
                ]
            )
        )


def test_cd4_cycle_closed_only_by_combining_destination_and_package(monkeypatch, manager):
    """CD4 — o grafo candidato é `destino ∪ pacote`, não só o pacote.

    Cenário construído para que **cada metade seja acíclica sozinha** e
    o ciclo só apareça na composição: o destino contém `D → P`, o
    pacote contém `P → D`. O preflight enxerga porque monta o grafo
    global.

    Nota honesta de alcançabilidade: por importação *insert-only*, com
    conflito abortando tudo, uma aresta do destino apontando para um
    evento que ainda não existe é impedida pela própria FK — então este
    cenário exige forjar o lado do destino. O teste prova que a
    verificação é **global**, que é a propriedade que protege caminhos
    de escrita futuros; não afirma que a composição seja alcançável
    hoje pelo import.
    """
    destination_event, package_event = uuid.uuid4(), uuid.uuid4()
    monkeypatch.setattr(
        manager._repository,
        "read_causal_edges",
        lambda: {str(destination_event): str(package_event)},
    )

    # O pacote, sozinho, é acíclico: um único evento com predecessor externo.
    with pytest.raises(SyncPackageInvalidError):
        manager._assert_causal_acyclicity(
            _causal_package(
                [{"id": str(package_event), "predecessor_event_id": str(destination_event)}]
            )
        )


def test_cd5_cross_history_predecessor_passes_preflight(manager):
    """CD5 — predecessor entre histórias continua válido: o preflight é
    global de propósito (`HISTORY_BOUNDARY != CAUSAL_BOUNDARY`) e não
    marca elo entre histórias como corrupção."""
    history_a, history_b = uuid.uuid4(), uuid.uuid4()
    origin, received = uuid.uuid4(), uuid.uuid4()

    manager._assert_causal_acyclicity(
        _causal_package(
            [
                {
                    "id": str(origin),
                    "history_id": str(history_a),
                    "predecessor_event_id": None,
                },
                {
                    "id": str(received),
                    "history_id": str(history_b),
                    "predecessor_event_id": str(origin),
                },
            ]
        )
    )


def test_cd6_predecessor_already_in_destination_passes_preflight(monkeypatch, manager):
    """CD6 — predecessor já presente no destino, filho novo no pacote:
    o caso normal de sincronização incremental. Passa."""
    existing = uuid.uuid4()
    child = uuid.uuid4()
    monkeypatch.setattr(manager._repository, "read_causal_edges", lambda: {str(existing): None})

    manager._assert_causal_acyclicity(
        _causal_package([{"id": str(child), "predecessor_event_id": str(existing)}])
    )


def test_cd8_malformed_event_id_does_not_break_the_preflight(manager):
    """CD8 — id malformado não derruba o preflight: ele não entra no
    grafo e a rejeição específica vem depois, na decodificação.

    O preflight verifica **aciclicidade**, não sintaxe.
    """
    manager._assert_causal_acyclicity(
        _causal_package([{"id": "não-é-uuid", "predecessor_event_id": None}])
    )

    with pytest.raises(SyncPackageInvalidError):
        manager.import_package(
            _causal_package([{"id": "não-é-uuid", "predecessor_event_id": None}])
        )


def test_cd8b_event_without_id_is_rejected_by_the_preflight_path(manager):
    """CD8 (complemento) — evento sem `id` é rejeitado já dentro do
    preflight, pela mesma validação de envelope que cobre todas as
    seções. Nada é escrito, e a mensagem é específica."""
    with pytest.raises(SyncPackageInvalidError, match="sem 'id'"):
        manager._assert_causal_acyclicity(_causal_package([{"predecessor_event_id": None}]))

    with pytest.raises(SyncPackageInvalidError, match="sem 'id'"):
        manager.import_package(_causal_package([{"predecessor_event_id": None}]))


def test_cd8c_uuid_instances_pass_through_the_preflight_unchanged(manager):
    """Um pacote já decodificado (ids como `UUID`, não strings) é
    aceito: o grafo candidato normaliza identificadores por `str()`,
    então texto do pacote e `UUID` do destino convivem sem
    ambiguidade."""
    first, second = uuid.uuid4(), uuid.uuid4()

    manager._assert_causal_acyclicity(
        _causal_package(
            [
                {"id": first, "predecessor_event_id": None},
                {"id": second, "predecessor_event_id": first},
            ]
        )
    )


def test_cd8d_malformed_predecessor_is_ignored_by_the_preflight(manager):
    """CD8 (complemento) — predecessor malformado também não participa
    do grafo: o preflight não confunde sintaxe com aciclicidade. A
    rejeição específica vem da decodificação."""
    event = uuid.uuid4()

    manager._assert_causal_acyclicity(
        _causal_package([{"id": str(event), "predecessor_event_id": "não-é-uuid"}])
    )

    with pytest.raises(SyncPackageInvalidError):
        manager.import_package(
            _causal_package([{"id": str(event), "predecessor_event_id": "não-é-uuid"}])
        )
