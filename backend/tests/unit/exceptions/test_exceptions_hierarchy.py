from app.core.error_codes import PIA_1002_NOT_FOUND, PIA_2001_VALIDATION_ERROR
from app.exceptions.api import (
    APIException,
    AuthenticationException,
    BadRequestException,
    ConflictException,
    InternalServerException,
    MethodNotAllowedException,
    NotFoundException,
)
from app.exceptions.base import PIAOSException
from app.exceptions.configuration import ConfigurationException
from app.exceptions.database import DatabaseException, DatabaseUnavailableException
from app.exceptions.external import ExternalServiceException
from app.exceptions.infrastructure import InfrastructureException
from app.exceptions.validation import ValidationException


def test_piaos_exception_uses_error_code_default_message():
    exc = PIAOSException()
    assert exc.message == exc.error_code.default_message


def test_piaos_exception_custom_message_overrides_default():
    exc = PIAOSException(message="mensagem customizada")
    assert exc.message == "mensagem customizada"


def test_piaos_exception_exposes_code_category_severity_status():
    exc = NotFoundException()
    assert exc.code == "PIA-1002"
    assert exc.category == "api"
    assert exc.severity == "warning"
    assert exc.status_code == 404


def test_piaos_exception_can_override_error_code_per_instance():
    exc = PIAOSException(error_code=PIA_1002_NOT_FOUND)
    assert exc.code == "PIA-1002"
    assert exc.status_code == 404


def test_piaos_exception_str_is_the_message():
    exc = NotFoundException(message="recurso ausente")
    assert str(exc) == "recurso ausente"


def test_full_hierarchy_all_inherit_from_piaos_exception():
    for exc_type in (
        APIException,
        BadRequestException,
        NotFoundException,
        MethodNotAllowedException,
        ConflictException,
        InternalServerException,
        AuthenticationException,
        ValidationException,
        ConfigurationException,
        DatabaseException,
        DatabaseUnavailableException,
        InfrastructureException,
        ExternalServiceException,
    ):
        assert issubclass(exc_type, PIAOSException)


def test_authentication_exception_is_sibling_not_subclass_of_api_exception():
    assert not issubclass(AuthenticationException, APIException)
    assert issubclass(AuthenticationException, PIAOSException)


def test_database_unavailable_is_subclass_of_database_exception():
    assert issubclass(DatabaseUnavailableException, DatabaseException)


def test_each_concrete_exception_has_distinct_default_status():
    statuses = {
        BadRequestException().status_code,
        NotFoundException().status_code,
        MethodNotAllowedException().status_code,
        ConflictException().status_code,
    }
    assert len(statuses) == 4  # cada um com seu próprio status


def test_validation_exception_carries_field_errors():
    exc = ValidationException(
        field_errors=[{"field": "email", "message": "obrigatório"}],
    )
    assert exc.field_errors == [{"field": "email", "message": "obrigatório"}]
    assert exc.error_code == PIA_2001_VALIDATION_ERROR


def test_validation_exception_defaults_to_empty_field_errors():
    assert ValidationException().field_errors == []
