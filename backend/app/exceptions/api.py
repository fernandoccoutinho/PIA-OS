"""
Exceções da camada de API (HTTP) — evolução do Módulo 2.5.

Mesmo nome de classe e mesma convenção de chamada de antes
(`NotFoundException(detail=...)`, `.status_code`, `.message`) — apenas a
implementação passou a herdar de `PIAOSException` e carregar um
`ErrorCode` do catálogo oficial. `app.core.exceptions` (Módulo 2.5)
continua funcionando como reexport, não uma segunda implementação.
"""

from app.core.error_codes import (
    PIA_0002_INTERNAL_ERROR,
    PIA_1001_BAD_REQUEST,
    PIA_1002_NOT_FOUND,
    PIA_1003_METHOD_NOT_ALLOWED,
    PIA_1004_CONFLICT,
    PIA_1006_PAYLOAD_TOO_LARGE,
    PIA_1007_UNSUPPORTED_MEDIA_TYPE,
    PIA_1008_TOO_MANY_REQUESTS,
    PIA_1009_UNTRUSTED_HOST,
    PIA_7001_AUTHENTICATION_ERROR,
)
from app.exceptions.base import PIAOSException


class APIException(PIAOSException):
    """Base de toda exceção HTTP customizada (400-499 tipicamente)."""

    error_code = PIA_0002_INTERNAL_ERROR


class BadRequestException(APIException):
    error_code = PIA_1001_BAD_REQUEST


class NotFoundException(APIException):
    error_code = PIA_1002_NOT_FOUND


class MethodNotAllowedException(APIException):
    error_code = PIA_1003_METHOD_NOT_ALLOWED


class ConflictException(APIException):
    error_code = PIA_1004_CONFLICT


class InternalServerException(APIException):
    error_code = PIA_0002_INTERNAL_ERROR


class PayloadTooLargeException(APIException):
    error_code = PIA_1006_PAYLOAD_TOO_LARGE


class UnsupportedMediaTypeException(APIException):
    error_code = PIA_1007_UNSUPPORTED_MEDIA_TYPE


class TooManyRequestsException(APIException):
    error_code = PIA_1008_TOO_MANY_REQUESTS


class UntrustedHostException(APIException):
    error_code = PIA_1009_UNTRUSTED_HOST


class AuthenticationException(PIAOSException):
    """Estrutura apenas — nenhum endpoint desta etapa a utiliza.

    Não herda de `APIException` de propósito: a especificação do
    Módulo 2.7 posiciona `AuthenticationException` como irmã direta de
    `APIException` na hierarquia (ambas sob `PIAOSException`), não como
    uma subcategoria dela — autenticação é uma preocupação transversal
    distinta de "erro de requisição HTTP genérico".
    """

    error_code = PIA_7001_AUTHENTICATION_ERROR
