import pytest
from pydantic import ValidationError

from app.api.responses import ErrorDetail, ErrorResponse, MessageResponse, SuccessResponse
from app.schemas.common import Message, PaginationMeta, PaginationParams, SortOrder, SortParams
from app.schemas.error import ValidationErrorItem, ValidationResponse


def test_success_response_wraps_arbitrary_data():
    response = SuccessResponse[dict](data={"id": 1}, message="criado")
    assert response.data == {"id": 1}
    assert response.message == "criado"


def test_success_response_message_defaults_to_none():
    response = SuccessResponse[str](data="ok")
    assert response.message is None


def test_message_response_requires_text():
    response = MessageResponse(message="operação concluída")
    assert response.message == "operação concluída"


def test_error_response_matches_exception_handler_envelope_shape():
    response = ErrorResponse(
        error=ErrorDetail(
            message="not_found",
            detail="recurso ausente",
            status_code=404,
            request_id="req-1",
            path="/api/v1/x",
            code="PIA-1002",
            category="api",
            severity="warning",
        )
    )
    dumped = response.model_dump()
    assert dumped["error"]["status_code"] == 404
    assert dumped["error"]["path"] == "/api/v1/x"
    assert dumped["error"]["code"] == "PIA-1002"
    assert dumped["success"] is False


def test_validation_response_holds_field_errors():
    response = ValidationResponse(
        error=ErrorDetail(
            message="validation_error",
            status_code=422,
            path="/x",
            code="PIA-2001",
            category="validation",
            severity="warning",
        ),
        errors=[
            ValidationErrorItem(loc=["body", "email"], msg="campo obrigatório", type="missing")
        ],
    )
    assert len(response.errors) == 1
    assert response.errors[0].loc == ["body", "email"]


def test_pagination_params_defaults():
    params = PaginationParams()
    assert params.page == 1
    assert params.page_size == 20


def test_pagination_params_rejects_invalid_values():
    with pytest.raises(ValidationError):
        PaginationParams(page=0)
    with pytest.raises(ValidationError):
        PaginationParams(page_size=1000)


def test_sort_params_defaults_to_ascending():
    params = SortParams()
    assert params.order == SortOrder.ASC
    assert params.sort_by is None


def test_pagination_meta_holds_all_fields():
    meta = PaginationMeta(
        page=1, page_size=20, total=45, total_pages=3, has_next=True, has_previous=False
    )
    assert meta.total_pages == 3


def test_message_schema():
    msg = Message(text="olá")
    assert msg.text == "olá"
