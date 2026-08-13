"""
Validação de requisição — tamanho máximo e Content-Type.

Funções puras (sem efeito colateral) — o `SecurityMiddleware`
(`app/security/middleware.py`) as chama e decide o que fazer com o
resultado (logar + levantar a exceção correspondente).
"""

from dataclasses import dataclass

from starlette.requests import Request

from app.config.settings import Settings
from app.core.error_codes import (
    PIA_1006_PAYLOAD_TOO_LARGE,
    PIA_1007_UNSUPPORTED_MEDIA_TYPE,
    ErrorCode,
)

# Métodos para os quais um corpo de requisição não é esperado — sem
# Content-Type a validar.
_METHODS_WITHOUT_BODY = frozenset({"GET", "HEAD", "OPTIONS", "DELETE"})


@dataclass(frozen=True)
class RequestViolation:
    reason: str
    error_code: ErrorCode


def validate_request_size(request: Request, settings: Settings) -> RequestViolation | None:
    """Rejeita requisições cujo `Content-Length` declarado excede o limite
    configurado. Não lê o corpo (isso exigiria consumir o stream) —
    confia no header declarado pelo cliente, suficiente para o caso comum
    de proteção contra payloads grandes por engano ou abuso simples.
    """
    content_length = request.headers.get("content-length")
    if content_length is None:
        return None
    try:
        size = int(content_length)
    except ValueError:
        return None
    if size > settings.max_request_size_bytes:
        return RequestViolation(reason="payload_too_large", error_code=PIA_1006_PAYLOAD_TOO_LARGE)
    return None


def validate_content_type(request: Request, settings: Settings) -> RequestViolation | None:
    """Rejeita um Content-Type fora da lista permitida — apenas para
    métodos que tipicamente carregam corpo, e apenas se um Content-Type
    foi de fato enviado (sua ausência é responsabilidade da validação de
    schema do endpoint, via Pydantic — Módulo 2.5)."""
    if request.method in _METHODS_WITHOUT_BODY:
        return None
    raw_content_type = request.headers.get("content-type")
    if not raw_content_type:
        return None
    content_type = raw_content_type.split(";")[0].strip().lower()
    allowed = {c.lower() for c in settings.allowed_content_types_list}
    if content_type not in allowed:
        return RequestViolation(
            reason="unsupported_media_type", error_code=PIA_1007_UNSUPPORTED_MEDIA_TYPE
        )
    return None


def validate_request(request: Request, settings: Settings) -> RequestViolation | None:
    """Roda todas as validações de requisição, retornando a primeira
    violação encontrada (ou None)."""
    return validate_request_size(request, settings) or validate_content_type(request, settings)
