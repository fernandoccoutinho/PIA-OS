"""
Infraestrutura de Segurança Base do PIA-OS (Módulo 2.8).

Sem login, usuários, OAuth, JWT ou permissões — isso pertence a módulos
futuros. Esta camada prepara a plataforma: cabeçalhos de segurança,
CORS centralizado, hosts confiáveis, validação de requisição,
sanitização, rate limiting (estrutura, sem Redis), CSRF (estrutura),
gestão de segredos e políticas por ambiente.
"""

from app.security.middleware import SecurityMiddleware
from app.security.rate_limit import InMemoryRateLimiter, RateLimiter, RateLimitMiddleware
from app.security.secrets import SecretsManager, secrets_manager

__all__ = [
    "InMemoryRateLimiter",
    "RateLimitMiddleware",
    "RateLimiter",
    "SecretsManager",
    "SecurityMiddleware",
    "secrets_manager",
]
