"""
Configuração centralizada da aplicação — Sistema Central de Configuração.

Toda variável de ambiente do sistema é declarada e validada aqui. Nenhuma
outra camada deve ler variáveis de ambiente diretamente (os.environ) —
apenas importar `settings` (instância única, cacheada).

Compatibilidade com a Entrega 2.1: os atributos flat usados por
`main.py`, `app/database/session.py`, `app/core/lifespan.py` e pelos
middlewares (`settings.app_name`, `settings.database_url`,
`settings.log_level`, `settings.log_json`, etc.) permanecem inalterados.
Os grupos exigidos pela especificação do Módulo 2.2 (`AppGroup`,
`DatabaseGroup`, `LogGroup`, `APIGroup`, `SecurityGroup`, `DockerGroup`)
são expostos como propriedades computadas (`settings.app`,
`settings.database`, ...) que derivam dos mesmos campos — evita duplicar
a fonte de verdade e quebrar a arquitetura já validada na Entrega 2.1.
"""

from functools import lru_cache

from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.config import constants
from app.config.environment import Environment, is_production_like
from app.config.validators import (
    validate_database_url,
    validate_jwt_algorithm,
    validate_log_destination,
    validate_log_format,
    validate_log_level,
    validate_non_empty_name,
    validate_port,
)

# Re-exportado para compatibilidade com código existente que importa
# `Environment` a partir de `app.config.settings` (ex.: app/config/config.py).
__all__ = ["Environment", "Settings", "get_settings", "settings"]


# ---------------------------------------------------------------------------
# Classes de grupo — uma por domínio de configuração, conforme especificado.
# São modelos de leitura (não fontes de verdade): construídas a partir dos
# campos de `Settings` para oferecer uma API agrupada sem duplicar estado.
# ---------------------------------------------------------------------------


class AppGroup(BaseModel):
    name: str
    version: str
    environment: Environment
    debug: bool


class DatabaseGroup(BaseModel):
    url: str
    pool_size: int
    max_overflow: int
    pool_recycle: int
    pool_timeout: int
    echo: bool


class LogGroup(BaseModel):
    level: str
    format: str
    destination: str
    file_path: str | None
    rotation_max_bytes: int
    rotation_backup_count: int


class APIGroup(BaseModel):
    prefix: str
    version: str
    docs_url: str
    redoc_url: str
    openapi_url: str


class SecurityGroup(BaseModel):
    jwt_algorithm: str
    jwt_expiration_minutes: int
    # secret_key deliberadamente omitido — grupo é usado para inspeção/
    # documentação e não deve expor segredos, mesmo internamente em logs.


class CORSGroup(BaseModel):
    allowed_origins: list[str]
    allowed_methods: list[str]
    allowed_headers: list[str]
    allow_credentials: bool


class TrustedHostsGroup(BaseModel):
    allowed_hosts: list[str]


class RateLimitGroup(BaseModel):
    enabled: bool
    requests: int
    window_seconds: int


class RequestValidationGroup(BaseModel):
    max_request_size_bytes: int
    allowed_content_types: list[str]


class DockerGroup(BaseModel):
    docker_env: bool


# ---------------------------------------------------------------------------
# Settings — classe principal, fonte única de verdade.
# ---------------------------------------------------------------------------


class Settings(BaseSettings):
    """Configuração global, carregada a partir de variáveis de ambiente / .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    # --- Aplicação ---
    app_name: str = constants.APP_NAME
    app_version: str = constants.APP_VERSION
    environment: Environment = Environment.DEVELOPMENT
    debug: bool = False

    # --- API ---
    api_prefix: str = constants.API_PREFIX
    api_version: str = constants.API_VERSION
    docs_url: str = "/docs"
    redoc_url: str = "/redoc"
    openapi_url: str = "/openapi.json"

    # --- Banco de dados ---
    # DATABASE_URL é a fonte de verdade quando fornecida explicitamente
    # (compatibilidade com a Entrega 2.1). Os campos DB_* abaixo permitem
    # composição a partir de partes (exigido pelo Módulo 2.2) e são usados
    # para montar a URL apenas quando DATABASE_URL não é definida no ambiente.
    database_url: str = Field(default="postgresql+psycopg://pia_user:pia_password@db:5432/pia_os")
    db_host: str | None = None
    db_port: int | None = None
    db_name: str | None = None
    db_user: str | None = None
    db_password: str | None = None

    database_pool_size: int = 5
    database_max_overflow: int = 10
    database_pool_recycle: int = 1800
    database_pool_timeout: int = 30
    database_echo: bool = False

    # --- Logging ---
    log_level: str = "INFO"
    log_format: str = "json"
    # Destinos combináveis, separados por vírgula: "console", "file", "syslog".
    # "file" só tem efeito se log_file_path também estiver definido.
    log_destination: str = "console"
    log_file_path: str | None = None
    log_rotation_max_bytes: int = 10 * 1024 * 1024  # 10 MiB
    log_rotation_backup_count: int = 5

    # --- Segurança (estrutura apenas — sem implementação nesta etapa) ---
    secret_key: str = Field(default="change-me-in-env")
    jwt_algorithm: str = constants.DEFAULT_JWT_ALGORITHM
    # Campo em código é explícito (unidade nos minutos); variável de ambiente
    # segue o nome pedido na especificação do Módulo 2.2 (JWT_EXPIRATION).
    jwt_expiration_minutes: int = Field(
        default=constants.DEFAULT_JWT_EXPIRATION_MINUTES,
        validation_alias="JWT_EXPIRATION",
    )

    # --- CORS (Módulo 2.8) ---
    cors_allowed_origins: str = "*"
    cors_allowed_methods: str = "GET,POST,PUT,PATCH,DELETE,OPTIONS"
    cors_allowed_headers: str = "*"
    cors_allow_credentials: bool = False

    # --- Trusted Hosts (Módulo 2.8) ---
    # "*" (padrão de desenvolvimento) aceita qualquer host — em produção,
    # sempre defina uma lista explícita via TRUSTED_HOSTS.
    trusted_hosts: str = "*"

    # --- Rate Limiting (Módulo 2.8 — estrutura, sem Redis) ---
    rate_limit_enabled: bool = False
    rate_limit_requests: int = 100
    rate_limit_window_seconds: int = 60

    # --- Validação de Requisição (Módulo 2.8) ---
    max_request_size_bytes: int = 10 * 1024 * 1024  # 10 MiB
    allowed_content_types: str = "application/json,application/x-www-form-urlencoded"

    # --- CSP (Módulo 2.8 — estrutura apenas, sem política definitiva) ---
    csp_policy: str | None = None

    # --- Docker ---
    docker_env: bool = False

    # -- Validadores --

    @field_validator("app_name")
    @classmethod
    def _validate_app_name(cls, v: str) -> str:
        return validate_non_empty_name(v, field_name="APP_NAME")

    @field_validator("db_port")
    @classmethod
    def _validate_db_port(cls, v: int | None) -> int | None:
        return validate_port(v) if v is not None else v

    @field_validator("log_level")
    @classmethod
    def _validate_log_level(cls, v: str) -> str:
        return validate_log_level(v)

    @field_validator("log_format")
    @classmethod
    def _validate_log_format(cls, v: str) -> str:
        return validate_log_format(v)

    @field_validator("log_destination")
    @classmethod
    def _validate_log_destination(cls, v: str) -> str:
        return validate_log_destination(v)

    @field_validator("jwt_algorithm")
    @classmethod
    def _validate_jwt_algorithm(cls, v: str) -> str:
        return validate_jwt_algorithm(v)

    @field_validator("database_url")
    @classmethod
    def _validate_database_url(cls, v: str) -> str:
        return validate_database_url(v)

    @model_validator(mode="after")
    def _compose_database_url_from_parts(self) -> "Settings":
        """Se DATABASE_URL não foi definida explicitamente mas DB_HOST foi,
        monta a URL a partir das partes discretas (DB_HOST/PORT/NAME/USER/PASSWORD).
        Preserva compatibilidade: quando só DATABASE_URL é fornecida (como na
        Entrega 2.1), o comportamento é idêntico ao anterior.
        """
        explicit = self.model_fields_set
        if "db_host" in explicit and "database_url" not in explicit:
            port = self.db_port or constants.DEFAULT_DB_PORT
            user = self.db_user or "pia_user"
            password = self.db_password or ""
            name = self.db_name or "pia_os"
            auth = f"{user}:{password}" if password else user
            self.database_url = f"postgresql+psycopg://{auth}@{self.db_host}:{port}/{name}"
        return self

    # -- Propriedades derivadas (compatibilidade com Entrega 2.1) --

    @property
    def is_production(self) -> bool:
        return self.environment is Environment.PRODUCTION

    @property
    def is_testing(self) -> bool:
        return self.environment is Environment.TESTING

    @property
    def is_staging(self) -> bool:
        return self.environment is Environment.STAGING

    @property
    def is_production_like(self) -> bool:
        return is_production_like(self.environment)

    @property
    def log_json(self) -> bool:
        """Compatibilidade com a Entrega 2.1 (`configure_logging(json_format=...)`)."""
        return self.log_format == "json"

    @property
    def log_destinations(self) -> list[str]:
        """Lista de destinos de log ativos (a partir de `log_destination`)."""
        return self.log_destination.split(",")

    @property
    def cors_allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allowed_origins.split(",") if o.strip()]

    @property
    def cors_allowed_methods_list(self) -> list[str]:
        return [m.strip() for m in self.cors_allowed_methods.split(",") if m.strip()]

    @property
    def cors_allowed_headers_list(self) -> list[str]:
        return [h.strip() for h in self.cors_allowed_headers.split(",") if h.strip()]

    @property
    def trusted_hosts_list(self) -> list[str]:
        return [h.strip() for h in self.trusted_hosts.split(",") if h.strip()]

    @property
    def allowed_content_types_list(self) -> list[str]:
        return [c.strip() for c in self.allowed_content_types.split(",") if c.strip()]

    # -- Grupos (exigidos pela especificação do Módulo 2.2) --

    @property
    def app(self) -> AppGroup:
        return AppGroup(
            name=self.app_name,
            version=self.app_version,
            environment=self.environment,
            debug=self.debug,
        )

    @property
    def database(self) -> DatabaseGroup:
        return DatabaseGroup(
            url=self.database_url,
            pool_size=self.database_pool_size,
            max_overflow=self.database_max_overflow,
            pool_recycle=self.database_pool_recycle,
            pool_timeout=self.database_pool_timeout,
            echo=self.database_echo,
        )

    @property
    def log(self) -> LogGroup:
        return LogGroup(
            level=self.log_level,
            format=self.log_format,
            destination=self.log_destination,
            file_path=self.log_file_path,
            rotation_max_bytes=self.log_rotation_max_bytes,
            rotation_backup_count=self.log_rotation_backup_count,
        )

    @property
    def api(self) -> APIGroup:
        return APIGroup(
            prefix=self.api_prefix,
            version=self.api_version,
            docs_url=self.docs_url,
            redoc_url=self.redoc_url,
            openapi_url=self.openapi_url,
        )

    @property
    def security(self) -> SecurityGroup:
        return SecurityGroup(
            jwt_algorithm=self.jwt_algorithm,
            jwt_expiration_minutes=self.jwt_expiration_minutes,
        )

    @property
    def cors(self) -> CORSGroup:
        return CORSGroup(
            allowed_origins=self.cors_allowed_origins_list,
            allowed_methods=self.cors_allowed_methods_list,
            allowed_headers=self.cors_allowed_headers_list,
            allow_credentials=self.cors_allow_credentials,
        )

    @property
    def trusted_hosts_group(self) -> TrustedHostsGroup:
        return TrustedHostsGroup(allowed_hosts=self.trusted_hosts_list)

    @property
    def rate_limit(self) -> RateLimitGroup:
        return RateLimitGroup(
            enabled=self.rate_limit_enabled,
            requests=self.rate_limit_requests,
            window_seconds=self.rate_limit_window_seconds,
        )

    @property
    def request_validation(self) -> RequestValidationGroup:
        return RequestValidationGroup(
            max_request_size_bytes=self.max_request_size_bytes,
            allowed_content_types=self.allowed_content_types_list,
        )

    @property
    def docker(self) -> DockerGroup:
        return DockerGroup(docker_env=self.docker_env)


@lru_cache
def get_settings() -> Settings:
    """Retorna a instância única (cacheada) das configurações.

    O carregamento efetivo do arquivo .env correto por ambiente é
    responsabilidade de `app.config.loader`; esta função apenas garante
    que `Settings()` seja instanciada uma única vez por processo.
    """
    from app.config.loader import build_settings

    return build_settings()


settings = get_settings()
