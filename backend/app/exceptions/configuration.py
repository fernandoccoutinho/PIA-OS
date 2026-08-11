"""
Exceção de configuração — face HTTP da hierarquia global.

Distinta de `app.config.config.ConfigurationError` (Módulo 2.2): aquela é
levantada apenas no *startup* (`validate_environment`), fora de qualquer
ciclo de requisição, e nunca chega a um handler HTTP — ela impede a
aplicação de subir. `ConfigurationException` (aqui) é para o caso raro de
uma configuração inválida ser detectada *durante* o processamento de uma
requisição (ex.: uma feature flag mal configurada, checada sob demanda) —
precisa de uma resposta HTTP estruturada, não de abortar o processo.
"""

from app.core.error_codes import PIA_4001_CONFIGURATION_ERROR
from app.exceptions.base import PIAOSException


class ConfigurationException(PIAOSException):
    error_code = PIA_4001_CONFIGURATION_ERROR
