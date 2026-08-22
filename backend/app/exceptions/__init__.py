"""
Sistema Global de Tratamento de Erros do PIA-OS (Módulo 2.7).

Hierarquia oficial:

    PIAOSException
    ├── APIException (+ BadRequestException, NotFoundException,
    │                   MethodNotAllowedException, ConflictException,
    │                   InternalServerException)
    ├── ValidationException
    ├── ConfigurationException
    ├── DatabaseException (+ DatabaseUnavailableException)
    ├── InfrastructureException
    ├── ExternalServiceException
    └── AuthenticationException (estrutura apenas)

Uso recomendado:

    from app.exceptions import NotFoundException
    raise NotFoundException(detail=f"id={entity_id}")
"""

from app.exceptions.api import (
    APIException,
    AuthenticationException,
    BadRequestException,
    ConflictException,
    InsufficientScopeException,
    InternalServerException,
    MethodNotAllowedException,
    NotFoundException,
    PayloadTooLargeException,
    TooManyRequestsException,
    UnsupportedMediaTypeException,
    UntrustedHostException,
)
from app.exceptions.base import PIAOSException
from app.exceptions.configuration import ConfigurationException
from app.exceptions.database import DatabaseException, DatabaseUnavailableException
from app.exceptions.external import ExternalServiceException
from app.exceptions.infrastructure import InfrastructureException
from app.exceptions.registry import ExceptionRegistry, default_registry
from app.exceptions.validation import ValidationException

__all__ = [
    "APIException",
    "AuthenticationException",
    "BadRequestException",
    "ConfigurationException",
    "ConflictException",
    "DatabaseException",
    "DatabaseUnavailableException",
    "ExceptionRegistry",
    "ExternalServiceException",
    "InfrastructureException",
    "InsufficientScopeException",
    "InternalServerException",
    "MethodNotAllowedException",
    "NotFoundException",
    "PIAOSException",
    "PayloadTooLargeException",
    "TooManyRequestsException",
    "UnsupportedMediaTypeException",
    "UntrustedHostException",
    "ValidationException",
    "default_registry",
]
