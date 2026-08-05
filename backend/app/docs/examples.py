"""
Exemplos padronizados para a documentação OpenAPI.

Usados por `app/docs/responses.py` e por schemas públicos (`model_config`/
`json_schema_extra`) — a mesma forma de erro em todo lugar que a API a
documenta, coerente com o envelope real gerado por
`app.exceptions.handlers` (Módulo 2.7).
"""

from typing import Any

EXAMPLE_ERROR_GENERIC: dict[str, Any] = {
    "success": False,
    "error": {
        "code": "PIA-1001",
        "message": "bad_request",
        "category": "api",
        "severity": "warning",
        "status_code": 400,
        "request_id": "5cd5e166-3b2e-4b7a-9c1a-2f8e6a1d4c3b",
        "correlation_id": None,
        "trace_id": None,
        "path": "/api/v1/recurso",
        "timestamp": "2026-01-15T12:00:00+00:00",
        "detail": None,
        "details": {},
    },
}

EXAMPLE_ERROR_NOT_FOUND: dict[str, Any] = {
    "success": False,
    "error": {
        "code": "PIA-1002",
        "message": "not_found",
        "category": "api",
        "severity": "warning",
        "status_code": 404,
        "request_id": "5cd5e166-3b2e-4b7a-9c1a-2f8e6a1d4c3b",
        "correlation_id": None,
        "trace_id": None,
        "path": "/api/v1/recurso/42",
        "timestamp": "2026-01-15T12:00:00+00:00",
        "detail": "id=42",
        "details": {"value": "id=42"},
    },
}

EXAMPLE_ERROR_VALIDATION: dict[str, Any] = {
    "success": False,
    "error": {
        "code": "PIA-2001",
        "message": "validation_error",
        "category": "validation",
        "severity": "warning",
        "status_code": 422,
        "request_id": "5cd5e166-3b2e-4b7a-9c1a-2f8e6a1d4c3b",
        "correlation_id": None,
        "trace_id": None,
        "path": "/api/v1/recurso",
        "timestamp": "2026-01-15T12:00:00+00:00",
        "detail": [
            {"loc": ["body", "email"], "msg": "campo obrigatório", "type": "missing"},
        ],
        "details": {},
    },
}

EXAMPLE_ERROR_INTERNAL: dict[str, Any] = {
    "success": False,
    "error": {
        "code": "PIA-0002",
        "message": "internal_server_error",
        "category": "system",
        "severity": "critical",
        "status_code": 500,
        "request_id": "5cd5e166-3b2e-4b7a-9c1a-2f8e6a1d4c3b",
        "correlation_id": None,
        "trace_id": None,
        "path": "/api/v1/recurso",
        "timestamp": "2026-01-15T12:00:00+00:00",
        "detail": "Ocorreu um erro interno inesperado.",
        "details": {"value": "Ocorreu um erro interno inesperado."},
    },
}

EXAMPLE_SUCCESS_MESSAGE: dict[str, Any] = {"message": "Operação concluída com sucesso."}
