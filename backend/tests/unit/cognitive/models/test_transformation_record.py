"""Testes de `TransformationRecord` — validação estrutural mínima."""

from app.cognitive.models.cognitive_object import CognitiveObject
from app.cognitive.models.enums import TransformationKind
from app.cognitive.models.transformation_record import TransformationRecord


def test_creates_with_required_fields(cognitive_session):
    source = CognitiveObject()
    target = CognitiveObject()
    cognitive_session.add_all([source, target])
    cognitive_session.commit()

    record = TransformationRecord(
        operation_type="summarize",
        transformation_kind=TransformationKind.DERIVATION,
        input_refs=[str(source.id)],
        output_refs=[str(target.id)],
    )
    cognitive_session.add(record)
    cognitive_session.commit()
    cognitive_session.refresh(record)

    assert record.id is not None
    assert record.transformation_id == record.id
    assert record.operation_type == "summarize"
    assert record.input_refs == [str(source.id)]
    assert record.output_refs == [str(target.id)]
    assert record.created_at is not None


def test_declared_preservations_and_losses_default_to_empty_list(cognitive_session):
    source = CognitiveObject()
    target = CognitiveObject()
    cognitive_session.add_all([source, target])
    cognitive_session.commit()

    record = TransformationRecord(
        operation_type="translate",
        transformation_kind=TransformationKind.DERIVATION,
        input_refs=[str(source.id)],
        output_refs=[str(target.id)],
    )
    cognitive_session.add(record)
    cognitive_session.commit()
    cognitive_session.refresh(record)

    assert record.declared_preservations == []
    assert record.declared_losses == []


def test_declared_preservations_and_losses_persist(cognitive_session):
    source = CognitiveObject()
    target = CognitiveObject()
    cognitive_session.add_all([source, target])
    cognitive_session.commit()

    record = TransformationRecord(
        operation_type="compress",
        transformation_kind=TransformationKind.DERIVATION,
        input_refs=[str(source.id)],
        output_refs=[str(target.id)],
        declared_preservations=["sentido geral"],
        declared_losses=["detalhes secundários"],
    )
    cognitive_session.add(record)
    cognitive_session.commit()
    cognitive_session.refresh(record)

    assert record.declared_preservations == ["sentido geral"]
    assert record.declared_losses == ["detalhes secundários"]


def test_actor_ref_defaults_to_none(cognitive_session):
    """`actor_ref` é obrigatório no Domain Model Draft, mas
    `ProvenanceRecord` não existe ainda (E3.6) — implementado como
    nulo por padrão."""
    source = CognitiveObject()
    target = CognitiveObject()
    cognitive_session.add_all([source, target])
    cognitive_session.commit()

    record = TransformationRecord(
        operation_type="derive",
        transformation_kind=TransformationKind.DERIVATION,
        input_refs=[str(source.id)],
        output_refs=[str(target.id)],
    )
    cognitive_session.add(record)
    cognitive_session.commit()
    cognitive_session.refresh(record)

    assert record.actor_ref is None


def test_input_refs_and_output_refs_support_multiple_entries(cognitive_session):
    """O contrato do Draft é `list[COID]` — suporta N-para-M, mesmo
    que `VersionManager` (E3.4) só exercite 1-para-1 nesta fase."""
    a = CognitiveObject()
    b = CognitiveObject()
    merged = CognitiveObject()
    cognitive_session.add_all([a, b, merged])
    cognitive_session.commit()

    record = TransformationRecord(
        operation_type="merge",
        transformation_kind=TransformationKind.DERIVATION,
        input_refs=[str(a.id), str(b.id)],
        output_refs=[str(merged.id)],
    )
    cognitive_session.add(record)
    cognitive_session.commit()
    cognitive_session.refresh(record)

    assert set(record.input_refs) == {str(a.id), str(b.id)}
    assert record.output_refs == [str(merged.id)]
