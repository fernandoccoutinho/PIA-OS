"""
Exceção de infraestrutura — categoria genérica para falhas que não são
especificamente de banco, configuração, ou serviço externo (ex.: um
futuro sistema de arquivos, fila de mensagens, cache). Nenhum uso
concreto nesta etapa — apenas a classe, pronta para módulos futuros.
"""

from app.core.error_codes import PIA_5001_INFRASTRUCTURE_ERROR
from app.exceptions.base import PIAOSException


class InfrastructureException(PIAOSException):
    error_code = PIA_5001_INFRASTRUCTURE_ERROR
