"""
Base declarativa do SQLAlchemy 2.x.

Todos os modelos ORM (camada `app/models`) devem herdar de `Base`.
Nenhum modelo é definido nesta etapa — apenas a fundação.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Classe base declarativa para todas as entidades ORM do sistema."""

    pass
