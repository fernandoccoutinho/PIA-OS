from app.docs.examples import (
    EXAMPLE_ERROR_GENERIC,
    EXAMPLE_ERROR_INTERNAL,
    EXAMPLE_ERROR_NOT_FOUND,
    EXAMPLE_ERROR_VALIDATION,
    EXAMPLE_SUCCESS_MESSAGE,
)
from app.schemas.error import ErrorResponse, ValidationResponse


def test_error_examples_validate_against_error_response_schema():
    for example in (EXAMPLE_ERROR_GENERIC, EXAMPLE_ERROR_NOT_FOUND, EXAMPLE_ERROR_INTERNAL):
        ErrorResponse.model_validate(example)  # não lança se o exemplo bater com o schema


def test_validation_example_validates_against_validation_response_schema():
    ValidationResponse.model_validate(EXAMPLE_ERROR_VALIDATION)


def test_all_error_examples_have_success_false():
    for example in (
        EXAMPLE_ERROR_GENERIC,
        EXAMPLE_ERROR_NOT_FOUND,
        EXAMPLE_ERROR_VALIDATION,
        EXAMPLE_ERROR_INTERNAL,
    ):
        assert example["success"] is False


def test_success_message_example_has_message_key():
    assert "message" in EXAMPLE_SUCCESS_MESSAGE
