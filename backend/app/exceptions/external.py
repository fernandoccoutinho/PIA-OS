"""
Exceção de serviço externo — para futuras integrações (APIs de
terceiros, provedores de IA, gateways). Nenhum uso concreto nesta etapa
— apenas a classe, pronta para módulos futuros de integração.
"""

from app.core.error_codes import PIA_6001_EXTERNAL_SERVICE_ERROR
from app.exceptions.base import PIAOSException


class ExternalServiceException(PIAOSException):
    error_code = PIA_6001_EXTERNAL_SERVICE_ERROR
