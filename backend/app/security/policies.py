"""
Políticas de segurança por ambiente.

Cada ambiente (Módulo 2.2 — `Environment`) tem exigências de segurança
diferentes. `expose_error_details` deriva diretamente de
`settings.debug` (não é um segundo interruptor independente — evita
dois lugares que poderiam divergir sobre a mesma decisão).
"""

from dataclasses import dataclass

from app.config.environment import Environment, is_production_like
from app.config.settings import Settings


@dataclass(frozen=True)
class SecurityPolicy:
    enforce_https: bool
    expose_error_details: bool
    strict_cors: bool
    csp_enabled: bool


def get_security_policy(config: Settings) -> SecurityPolicy:
    """Deriva a política de segurança ativa a partir do ambiente e da
    configuração atual — não hardcoda por ambiente sozinho, porque
    `expose_error_details` já é controlado por `settings.debug`
    independentemente do ambiente nominal (permite, por exemplo, ligar
    debug temporariamente em staging para investigar um problema)."""
    production_like = is_production_like(config.environment)
    return SecurityPolicy(
        enforce_https=production_like,
        expose_error_details=config.debug,
        strict_cors=production_like,
        csp_enabled=production_like and config.csp_policy is not None,
    )


# Referência de leitura — não usada em código, documenta a intenção por
# ambiente mencionada na especificação do Módulo 2.8.
POLICY_NOTES: dict[Environment, str] = {
    Environment.DEVELOPMENT: "HTTPS não exigido, detalhes de erro visíveis, CORS permissivo.",
    Environment.TESTING: "Mesma postura de development — ambiente de testes automatizados.",
    Environment.STAGING: "Postura de produção, mas com possibilidade de debug pontual.",
    Environment.PRODUCTION: "HTTPS exigido, nenhum detalhe de erro exposto, CORS restrito.",
}
