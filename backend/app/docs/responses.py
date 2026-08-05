"""
Documentação centralizada de responses HTTP para o OpenAPI.

Cada função retorna o dict no formato que o parâmetro `responses=` dos
decorators de rota do FastAPI espera. Endpoints reutilizam estas
definições em vez de escrever a documentação de erro repetidamente —
mesmo texto, mesmo schema, em toda a API.

401/403 são "estrutura apenas": documentados para quando autenticação/
autorização existirem (módulos futuros), mas nenhum endpoint atual os
usa, porque nenhum endpoint atual exige login.
"""

from typing import Any

from app.docs.examples import (
    EXAMPLE_ERROR_GENERIC,
    EXAMPLE_ERROR_INTERNAL,
    EXAMPLE_ERROR_NOT_FOUND,
    EXAMPLE_ERROR_VALIDATION,
)
from app.schemas.error import ErrorResponse, ValidationResponse


def response_200(description: str = "Sucesso.") -> dict[int | str, dict[str, Any]]:
    return {200: {"description": description}}


def response_201(
    description: str = "Recurso criado com sucesso.",
) -> dict[int | str, dict[str, Any]]:
    return {201: {"description": description}}


def response_204(
    description: str = "Sucesso, sem conteúdo de resposta.",
) -> dict[int | str, dict[str, Any]]:
    return {204: {"description": description}}


def response_400(description: str = "Requisição inválida.") -> dict[int | str, dict[str, Any]]:
    return {
        400: {
            "model": ErrorResponse,
            "description": description,
            "content": {"application/json": {"example": EXAMPLE_ERROR_GENERIC}},
        }
    }


def response_401(
    description: str = "Não autenticado. (estrutura — sem uso nesta etapa)",
) -> dict[int | str, dict[str, Any]]:
    return {401: {"model": ErrorResponse, "description": description}}


def response_403(
    description: str = "Não autorizado. (estrutura — sem uso nesta etapa)",
) -> dict[int | str, dict[str, Any]]:
    return {403: {"model": ErrorResponse, "description": description}}


def response_404(description: str = "Recurso não encontrado.") -> dict[int | str, dict[str, Any]]:
    return {
        404: {
            "model": ErrorResponse,
            "description": description,
            "content": {"application/json": {"example": EXAMPLE_ERROR_NOT_FOUND}},
        }
    }


def response_409(
    description: str = "Conflito com o estado atual do recurso.",
) -> dict[int | str, dict[str, Any]]:
    return {409: {"model": ErrorResponse, "description": description}}


def response_422(
    description: str = "Erro de validação da requisição.",
) -> dict[int | str, dict[str, Any]]:
    return {
        422: {
            "model": ValidationResponse,
            "description": description,
            "content": {"application/json": {"example": EXAMPLE_ERROR_VALIDATION}},
        }
    }


def response_500(description: str = "Erro interno inesperado.") -> dict[int | str, dict[str, Any]]:
    return {
        500: {
            "model": ErrorResponse,
            "description": description,
            "content": {"application/json": {"example": EXAMPLE_ERROR_INTERNAL}},
        }
    }


# Conjunto padrão para a maioria dos endpoints de leitura (GET) desta etapa:
# apenas erro inesperado é realmente possível — os demais estão disponíveis
# individualmente para endpoints que precisarem deles.
STANDARD_READ_RESPONSES: dict[int | str, dict[str, Any]] = {**response_500()}
