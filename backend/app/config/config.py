"""
Validação de invariantes de configuração por ambiente.

Este módulo não redefine valores — apenas valida que a combinação de
`Settings` carregada é coerente com o ambiente declarado. É a barreira
que faz a aplicação falhar cedo (na inicialização) se uma configuração
crítica estiver ausente ou incorreta em produção/staging.
"""

from app.config.environment import Environment, is_production_like
from app.config.settings import Settings, settings


class ConfigurationError(RuntimeError):
    """Erro de configuração crítica ausente ou inválida para o ambiente ativo."""


def validate_environment(config: Settings = settings) -> None:
    """Valida invariantes mínimas de configuração por ambiente.

    Lança ConfigurationError se a configuração carregada for incoerente
    com o ambiente declarado. Chamado no startup da aplicação (ver
    `app/core/lifespan.py`) — uma configuração crítica ausente deve
    impedir a aplicação de subir, com mensagem clara.
    """
    errors: list[str] = []

    if is_production_like(config.environment):
        if config.secret_key == "change-me-in-env":
            errors.append(
                "SECRET_KEY não pode usar o valor padrão em ambientes "
                f"'{config.environment.value}'. Defina uma chave real via variável de ambiente."
            )
        if config.debug:
            errors.append(f"DEBUG deve estar desativado em '{config.environment.value}'.")
        if "change-me" in config.database_url or "pia_password" in config.database_url:
            errors.append(
                f"DATABASE_URL parece usar credenciais padrão de desenvolvimento em "
                f"'{config.environment.value}'. Defina credenciais reais."
            )

    testing_db_missing_marker = (
        "pia_os" not in config.database_url and "test" not in config.database_url
    )
    if config.environment is Environment.TESTING and testing_db_missing_marker:
        errors.append(
            "Ambiente 'testing' deveria apontar para um banco de teste "
            "(DATABASE_URL não parece ser de teste)."
        )

    if errors:
        details = "\n  - ".join(errors)
        raise ConfigurationError(
            f"Configuração inválida para o ambiente '{config.environment.value}':\n  - {details}"
        )


ENVIRONMENT_DESCRIPTIONS = {
    Environment.DEVELOPMENT: "Ambiente local de desenvolvimento — debug ativo, reload ativo.",
    Environment.TESTING: "Ambiente de execução de testes automatizados (pytest).",
    Environment.STAGING: "Ambiente de homologação — espelha produção, sem dados reais de clientes.",
    Environment.PRODUCTION: "Ambiente de produção — debug desativado, segredo obrigatório.",
}
