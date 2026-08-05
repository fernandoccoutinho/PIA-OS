"""
Compatibilidade com o Módulo 2.5.

A hierarquia oficial agora vive em `app.exceptions` (Módulo 2.7) — este
módulo reexporta as mesmas classes, com a mesma convenção de chamada
(`NotFoundException(detail=...)`, `.status_code`, `.message`), não uma
segunda implementação. Código que já fazia
`from app.core.exceptions import NotFoundException` continua funcionando
sem alteração.
"""

from app.exceptions.api import (
    APIException,
    BadRequestException,
    InternalServerException,
    NotFoundException,
)
from app.exceptions.validation import ValidationException

__all__ = [
    "APIException",
    "BadRequestException",
    "InternalServerException",
    "NotFoundException",
    "ValidationException",
]
