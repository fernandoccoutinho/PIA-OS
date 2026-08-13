from app.docs.schemas import PUBLIC_SCHEMAS, fields_missing_description
from app.schemas.health import HealthResponse


def test_all_public_schemas_are_fully_documented():
    for schema in PUBLIC_SCHEMAS:
        missing = fields_missing_description(schema)
        assert missing == [], f"{schema.__name__} tem campos sem description: {missing}"


def test_public_schemas_registry_is_not_empty():
    assert len(PUBLIC_SCHEMAS) > 0
    assert HealthResponse in PUBLIC_SCHEMAS


def test_fields_missing_description_detects_undocumented_field():
    from pydantic import BaseModel

    class _Undocumented(BaseModel):
        x: int

    assert fields_missing_description(_Undocumented) == ["x"]


def test_fields_missing_description_empty_for_fully_documented_model():
    from pydantic import BaseModel, Field

    class _Documented(BaseModel):
        x: int = Field(description="um número")

    assert fields_missing_description(_Documented) == []
