"""Configuração da aplicação.

As configurações são carregadas de variáveis de ambiente (e de um arquivo
``.env`` em desenvolvimento). Veja ``.env.example`` para a lista completa.
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Configurações centrais do PIA-OS."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="PIA_",
        extra="ignore",
    )

    # Identidade / ambiente
    app_name: str = "PIA-OS"
    environment: Literal["development", "test", "production"] = "development"
    debug: bool = False

    # Servidor HTTP
    host: str = "0.0.0.0"
    port: int = 8000

    # Banco de dados (configurado na Entrega 1; utilizado a partir da Entrega 2)
    database_url: str = "postgresql+psycopg://pia:pia@localhost:5432/pia_os"


@lru_cache
def get_settings() -> Settings:
    """Retorna a instância singleton de configurações (cacheada)."""
    return Settings()
