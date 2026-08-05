from app.docs.responses import (
    STANDARD_READ_RESPONSES,
    response_200,
    response_400,
    response_401,
    response_403,
    response_404,
    response_409,
    response_422,
)


def test_response_200_has_only_description():
    result = response_200()
    assert result == {200: {"description": "Sucesso."}}


def test_response_400_includes_model_and_example():
    result = response_400()
    assert 400 in result
    assert "model" in result[400]
    assert "example" in result[400]["content"]["application/json"]


def test_response_404_example_matches_not_found_code():
    result = response_404()
    example = result[404]["content"]["application/json"]["example"]
    assert example["error"]["code"] == "PIA-1002"


def test_response_422_uses_validation_response_model():
    from app.schemas.error import ValidationResponse

    result = response_422()
    assert result[422]["model"] is ValidationResponse


def test_response_401_and_403_are_structural_placeholders():
    r401 = response_401()
    r403 = response_403()
    assert "estrutura" in r401[401]["description"]
    assert "estrutura" in r403[403]["description"]


def test_response_500_present_in_standard_read_responses():
    assert 500 in STANDARD_READ_RESPONSES


def test_response_409_has_model():
    result = response_409()
    assert 409 in result
    assert "model" in result[409]


def test_custom_description_overrides_default():
    result = response_400(description="mensagem customizada")
    assert result[400]["description"] == "mensagem customizada"
