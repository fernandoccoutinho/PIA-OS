"""
Schema padronizado de erro — Sistema Global de Tratamento de Erros (2.7).

Usado por `app.exceptions.handlers` para toda resposta de erro da API —
HTTP genérico, validação, ou qualquer `PIAOSException`. Um único formato
de erro em toda a plataforma.

Compatibilidade com o Módulo 2.5: `message`, `detail`, `status_code`,
`request_id`, `path` continuam presentes com o mesmo significado — o
Módulo 2.7 apenas ADICIONA campos (`code`, `category`, `severity`,
`correlation_id`, `trace_id`, `timestamp`, `details`), nunca removeu ou
renomeou um campo existente. Módulo 2.9 apenas adiciona `description` e
exemplos — nenhum campo, tipo ou default muda.
"""

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from app.docs.examples import EXAMPLE_ERROR_NOT_FOUND, EXAMPLE_ERROR_VALIDATION


class ErrorDetail(BaseModel):
    # --- Campos desde o Módulo 2.5 (compatibilidade) ---
    message: str = Field(
        description="Identificador curto e estável do tipo de erro (ex.: 'not_found')."
    )
    detail: object = Field(
        default=None, description="Detalhe livre do erro — forma varia por tipo."
    )
    status_code: int = Field(description="Código de status HTTP da resposta.")
    request_id: str | None = Field(
        default=None, description="ID único da requisição (header X-Request-ID)."
    )
    path: str = Field(description="Caminho da requisição que gerou o erro.")

    # --- Campos novos do Módulo 2.7 ---
    code: str = Field(description="Código oficial do catálogo PIA-OS (ex.: 'PIA-1002').")
    category: str = Field(description="Categoria do erro (api, validation, database, ...).")
    severity: str = Field(description="Severidade: warning, error ou critical.")
    correlation_id: str | None = Field(
        default=None, description="ID de correlação entre serviços, se enviado."
    )
    trace_id: str | None = Field(
        default=None, description="ID de rastreamento distribuído, se disponível."
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="Timestamp do erro, em ISO 8601.",
    )
    details: dict[str, object] = Field(
        default_factory=dict, description="Forma estruturada (dict) de `detail`, sempre presente."
    )


class ErrorResponse(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": EXAMPLE_ERROR_NOT_FOUND})

    success: bool = Field(default=False, description="Sempre false em uma resposta de erro.")
    error: ErrorDetail = Field(description="Detalhes estruturados do erro.")


class ValidationErrorItem(BaseModel):
    """Um item de erro de validação — mesmo formato usado pelo Pydantic/
    FastAPI em `RequestValidationError.errors()`."""

    loc: list[str | int] = Field(
        description="Caminho até o campo inválido (ex.: ['body', 'email'])."
    )
    msg: str = Field(description="Mensagem de validação legível.")
    type: str = Field(description="Tipo do erro de validação (ex.: 'missing', 'string_type').")


class ValidationResponse(BaseModel):
    """Formato do corpo de erro para respostas 422 — usado para
    documentação OpenAPI e por `ValidationException` quando um endpoint
    precisar formatar um erro de validação de domínio no mesmo padrão."""

    model_config = ConfigDict(json_schema_extra={"example": EXAMPLE_ERROR_VALIDATION})

    success: bool = Field(default=False, description="Sempre false em uma resposta de erro.")
    error: ErrorDetail = Field(description="Detalhes estruturados do erro.")
    errors: list[ValidationErrorItem] = Field(
        default=[], description="Lista de campos inválidos, um item por campo."
    )
