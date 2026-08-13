"""
Schemas Pydantic para os endpoints básicos de infraestrutura.

Compatibilidade: todos os campos existentes desde o Módulo 2.1/2.3
(`HealthResponse.status`, `StatusResponse.database_connected`, etc.)
permanecem inalterados — o Módulo 2.9 apenas adiciona `description` e
exemplos (`json_schema_extra`), sem alterar nomes, tipos ou defaults.
"""

from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    model_config = ConfigDict(json_schema_extra={"example": {"status": "ok"}})

    status: str = Field(default="ok", description="Sempre 'ok' se o processo está no ar.")


class ComponentStatus(BaseModel):
    """Status de um componente individual verificado por `/status`."""

    model_config = ConfigDict(
        json_schema_extra={"example": {"name": "database", "healthy": True, "detail": None}}
    )

    name: str = Field(description="Nome do componente verificado (ex.: 'database', 'orm').")
    healthy: bool = Field(description="Se o componente está saudável no momento da checagem.")
    detail: str | None = Field(
        default=None, description="Detalhe do problema, presente apenas quando healthy=false."
    )


class VersionResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "app_name": "PIA-OS Backend",
                "version": "0.1.0",
                "environment": "production",
                "api_version": "v1",
                "pia_os_version": "1.0.0",
                "database_version": "PostgreSQL 16.4",
            }
        }
    )

    app_name: str = Field(description="Nome do backend.")
    version: str = Field(description="Versão do backend (componente).")
    environment: str = Field(description="Ambiente ativo (development/testing/staging/production).")
    api_version: str = Field(description="Versão da API REST (ex.: 'v1').")
    pia_os_version: str = Field(description="Versão da plataforma PIA-OS como um todo.")
    database_version: str | None = Field(
        default=None, description="Versão do servidor PostgreSQL, ou null se inacessível."
    )


class StatusResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "ok",
                "database_connected": True,
                "database_response_time_ms": 2.34,
                "environment": "production",
                "uptime_seconds": 3600.5,
                "api_version": "v1",
                "modules_loaded": 4,
                "components": [
                    {"name": "application", "healthy": True, "detail": None},
                    {"name": "database", "healthy": True, "detail": None},
                ],
            }
        }
    )

    status: str = Field(
        description="'ok' se todos os componentes estão saudáveis, 'degraded' caso contrário."
    )
    database_connected: bool = Field(description="Se o banco de dados está acessível.")
    database_response_time_ms: float | None = Field(
        default=None, description="Tempo de resposta do banco em milissegundos, se acessível."
    )
    environment: str = Field(description="Ambiente ativo.")
    uptime_seconds: float = Field(
        description="Tempo, em segundos, desde que este router foi carregado."
    )
    api_version: str = Field(description="Versão da API REST.")
    modules_loaded: int = Field(description="Número de módulos de API registrados.")
    components: list[ComponentStatus] = Field(
        default=[], description="Status individual de cada componente verificado."
    )


class MetricsResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={"example": {"uptime_seconds": 3600.5, "environment": "production"}}
    )

    uptime_seconds: float = Field(
        description="Tempo, em segundos, desde que este router foi carregado."
    )
    environment: str = Field(description="Ambiente ativo.")


class RootResponse(BaseModel):
    """Resposta de `GET /` — cartão de visitas da plataforma."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "name": "PIA-OS Backend",
                "version": "0.1.0",
                "environment": "production",
                "timestamp": "2026-01-15T12:00:00+00:00",
                "docs_url": "/docs",
                "redoc_url": "/redoc",
            }
        }
    )

    name: str = Field(description="Nome da plataforma.")
    version: str = Field(description="Versão do backend.")
    environment: str = Field(description="Ambiente ativo.")
    timestamp: str = Field(description="Timestamp atual do servidor, em ISO 8601.")
    docs_url: str | None = Field(description="Caminho do Swagger UI, ou null se desativado.")
    redoc_url: str | None = Field(description="Caminho do ReDoc, ou null se desativado.")
