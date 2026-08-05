"""
Gestão de segredos.

Segredos já são centralizados em `Settings` (Módulo 2.2) — nenhum código
lê `os.environ` diretamente fora dali. Este módulo adiciona uma segunda
camada, mais estreita: um ponto único e nomeado para acessar
especificamente os valores *sensíveis* (`secret_key`, credenciais
embutidas na `database_url`), com uma forma segura de exibi-los
mascarados (logs, mensagens de diagnóstico) sem nunca expor o valor
completo.
"""

from app.config.settings import Settings, settings
from app.security.sanitization import mask_sensitive_value


class SecretsManager:
    """Ponto único de acesso a segredos — não lê variáveis de ambiente
    diretamente, sempre via `Settings`."""

    def __init__(self, config: Settings) -> None:
        self._config = config

    def get_secret_key(self) -> str:
        return self._config.secret_key

    def get_database_url(self) -> str:
        return self._config.database_url

    def get_masked_secret_key(self) -> str:
        return mask_sensitive_value(self._config.secret_key)

    def get_masked_database_url(self) -> str:
        """Mascara a URL do banco inteira (não só a senha) — mesmo o
        host/nome do banco pode ser informação sensível dependendo do
        contexto de exibição."""
        return mask_sensitive_value(self._config.database_url, visible_chars=8)


secrets_manager = SecretsManager(settings)
