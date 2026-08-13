"""Testes de `TransformationRepository` — append-only e consultas."""

import pytest

from app.cognitive.errors.exceptions import TransformationRecordImmutableError
from app.cognitive.models.cognitive_object import CognitiveObject
from app.cognitive.models.enums import TransformationKind
from app.cognitive.models.transformation_record import TransformationRecord
from app.cognitive.repositories.object_repository import ObjectRepository
from app.cognitive.repositories.transformation_repository import TransformationRepository


@pytest.fixture
def objects(cognitive_session):
    return ObjectRepository(cognitive_session)


@pytest.fixture
def transformations(cognitive_session):
    return TransformationRepository(cognitive_session)


def test_add_persists_a_record(objects, transformations, cognitive_session):
    source = objects.add(CognitiveObject())
    target = objects.add(CognitiveObject())
    cognitive_session.commit()

    record = transformations.add(
        TransformationRecord(
            operation_type="derive",
            input_refs=[str(source.id)],
            transformation_kind=TransformationKind.DERIVATION,
            output_refs=[str(target.id)],
        )
    )
    cognitive_session.commit()
    assert record.id is not None


def test_update_is_rejected(objects, transformations, cognitive_session):
    source = objects.add(CognitiveObject())
    target = objects.add(CognitiveObject())
    cognitive_session.commit()
    record = transformations.add(
        TransformationRecord(
            operation_type="derive",
            input_refs=[str(source.id)],
            transformation_kind=TransformationKind.DERIVATION,
            output_refs=[str(target.id)],
        )
    )
    cognitive_session.commit()

    with pytest.raises(TransformationRecordImmutableError) as exc_info:
        transformations.update(record)
    assert exc_info.value.code == "PIA-8010"


def test_delete_is_rejected(objects, transformations, cognitive_session):
    source = objects.add(CognitiveObject())
    target = objects.add(CognitiveObject())
    cognitive_session.commit()
    record = transformations.add(
        TransformationRecord(
            operation_type="derive",
            input_refs=[str(source.id)],
            transformation_kind=TransformationKind.DERIVATION,
            output_refs=[str(target.id)],
        )
    )
    cognitive_session.commit()

    with pytest.raises(TransformationRecordImmutableError) as exc_info:
        transformations.delete(record)
    assert exc_info.value.code == "PIA-8010"


def test_record_intact_after_rejected_mutation_attempts(
    objects, transformations, cognitive_session
):
    source = objects.add(CognitiveObject())
    target = objects.add(CognitiveObject())
    cognitive_session.commit()
    record = transformations.add(
        TransformationRecord(
            operation_type="derive",
            input_refs=[str(source.id)],
            transformation_kind=TransformationKind.DERIVATION,
            output_refs=[str(target.id)],
        )
    )
    cognitive_session.commit()
    record_id, original_operation = record.id, record.operation_type

    with pytest.raises(TransformationRecordImmutableError):
        transformations.update(record)
    with pytest.raises(TransformationRecordImmutableError):
        transformations.delete(record)

    reloaded = cognitive_session.get(TransformationRecord, record_id)
    assert reloaded is not None
    assert reloaded.operation_type == original_operation


def test_list_by_input_coid_finds_matching_records(objects, transformations, cognitive_session):
    source = objects.add(CognitiveObject())
    target = objects.add(CognitiveObject())
    other_target = objects.add(CognitiveObject())
    cognitive_session.commit()

    transformations.add(
        TransformationRecord(
            operation_type="summarize",
            transformation_kind=TransformationKind.DERIVATION,
            input_refs=[str(source.id)],
            output_refs=[str(target.id)],
        )
    )
    transformations.add(
        TransformationRecord(
            operation_type="translate",
            transformation_kind=TransformationKind.DERIVATION,
            input_refs=[str(source.id)],
            output_refs=[str(other_target.id)],
        )
    )
    cognitive_session.commit()

    found = transformations.list_by_input_coid(source.id)
    assert len(found) == 2
    assert {r.operation_type for r in found} == {"summarize", "translate"}


def test_list_by_output_coid_finds_matching_record(objects, transformations, cognitive_session):
    source = objects.add(CognitiveObject())
    target = objects.add(CognitiveObject())
    cognitive_session.commit()

    transformations.add(
        TransformationRecord(
            operation_type="derive",
            input_refs=[str(source.id)],
            transformation_kind=TransformationKind.DERIVATION,
            output_refs=[str(target.id)],
        )
    )
    cognitive_session.commit()

    found = transformations.list_by_output_coid(target.id)
    assert len(found) == 1
    assert found[0].output_refs == [str(target.id)]


def test_list_by_input_coid_ordering_is_deterministic(objects, transformations, cognitive_session):
    source = objects.add(CognitiveObject())
    cognitive_session.commit()

    for i in range(5):
        target = objects.add(CognitiveObject())
        cognitive_session.commit()
        transformations.add(
            TransformationRecord(
                operation_type=f"op{i}",
                transformation_kind=TransformationKind.DERIVATION,
                input_refs=[str(source.id)],
                output_refs=[str(target.id)],
            )
        )
        cognitive_session.commit()

    run_1 = [r.id for r in transformations.list_by_input_coid(source.id)]
    run_2 = [r.id for r in transformations.list_by_input_coid(source.id)]
    assert run_1 == run_2
