"""
Exceção de validação de domínio.

Distinta de `RequestValidationError` (gerada automaticamente pelo
FastAPI/Pydantic a partir dos schemas de entrada) — esta é para regras de
validação que não cabem num schema Pydantic simples (ex.: uma checagem
que depende de estado, verificada manualmente por um endpoint ou
serviço futuro). Continua sem regra de negócio concreta nesta etapa —
apenas a classe e a estrutura de campos.
"""

from app.core.error_codes import PIA_2001_VALIDATION_ERROR
from app.exceptions.base import PIAOSException


class ValidationException(PIAOSException):
    """Erro de validação levantado manualmente (fora do ciclo automático
    de validação de request do FastAPI)."""

    error_code = PIA_2001_VALIDATION_ERROR

    def __init__(
        self,
        message: str | None = None,
        detail: object = None,
        field_errors: list[dict[str, str]] | None = None,
    ) -> None:
        super().__init__(message=message, detail=detail)
        self.field_errors = field_errors or []
