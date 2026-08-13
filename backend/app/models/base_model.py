"""
Classe base reutilizável para entidades ORM futuras.

Decisão de design: `BaseModel` inclui apenas `UUIDMixin` +
`TimestampMixin` — os dois que praticamente toda entidade de domínio
precisa. `SoftDeleteMixin`, `VersionMixin` e `AuditMixin` (ver
`app/models/mixins.py`) são deliberadamente **não** incluídos aqui, e
ficam disponíveis para composição à la carte:

    class Documento(BaseModel, SoftDeleteMixin):
        __tablename__ = "documentos"
        titulo: Mapped[str]

Por quê: forçar todo mixin dentro de `BaseModel` violaria a própria
exigência da especificação de que os mixins sejam "independentes e
reutilizáveis" — uma entidade que nunca precisará de soft delete não
deveria carregar a coluna `deleted_at` só porque herdou de uma base
monolítica. Isso é a aplicação direta de SOLID (Interface Segregation)
já mencionado como princípio obrigatório do módulo.

`BaseModel` herda de `app.database.base.Base` — a mesma Base declarativa
usada pelo Alembic (Módulo 2.1/2.3). Não existe uma segunda hierarquia
declarativa paralela.
"""

from app.database.base import Base
from app.models.mixins import TimestampMixin, UUIDMixin


class BaseModel(Base, UUIDMixin, TimestampMixin):
    """Base para entidades ORM de domínio (nenhuma é definida neste módulo).

    Fornece `id` (UUID) e `created_at`/`updated_at`. Para soft delete,
    versionamento ou auditoria, combine com os mixins correspondentes de
    `app.models.mixins` na entidade concreta.
    """

    __abstract__ = True
