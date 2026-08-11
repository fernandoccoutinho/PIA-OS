"""
Exceção de banco de dados — face HTTP da hierarquia global.

Distinta de `app.repositories.exceptions.RepositoryError` (Módulo 2.3/2.4):
aquela é um sinal interno da camada de repositório — nunca deveria
cruzar para a camada HTTP diretamente; um endpoint que capturar
`EntityNotFoundError` relança como `NotFoundException` (ver
`docs/API.md`). `DatabaseException` (aqui) é o que o handler global usa
para envolver um `SQLAlchemyError` cru que escapou *sem* ter sido
capturado/traduzido por código de aplicação — dá a esse caso uma resposta
estruturada em vez de um 500 genérico sem contexto.
"""

from app.core.error_codes import PIA_3001_DATABASE_ERROR, PIA_3002_DATABASE_UNAVAILABLE
from app.exceptions.base import PIAOSException


class DatabaseException(PIAOSException):
    error_code = PIA_3001_DATABASE_ERROR


class DatabaseUnavailableException(DatabaseException):
    error_code = PIA_3002_DATABASE_UNAVAILABLE
