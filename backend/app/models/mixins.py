"""
Mixins reutilizáveis para futuras entidades ORM.

Cada mixin é independente e componível por herança múltipla — nenhum
depende dos outros, e nenhum contém regra de negócio. Entidades futuras
combinam apenas os mixins de que precisam:

    class Documento(BaseModel, SoftDeleteMixin):
        __tablename__ = "documentos"
        titulo: Mapped[str]

`SoftDeleteMixin` e `VersionMixin` são "estrutura apenas": os campos
existem, mas nenhuma lógica de filtragem automática (soft delete) ou de
bloqueio otimista (versionamento) está implementada nesta etapa — isso é
responsabilidade de quem consumir os campos em módulos futuros.
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import Mapped, mapped_column


class UUIDMixin:
    """Chave primária UUID, gerada na aplicação (`uuid.uuid4`) no momento
    do `flush` (não na construção do objeto — esse é o comportamento padrão
    de `default=` no SQLAlchemy: o valor só é resolvido ao montar o INSERT).

    Gerada no lado da aplicação (não `server_default=gen_random_uuid()`)
    de propósito: funciona identicamente em qualquer backend suportado
    pelos testes (SQLite inclusive), sem depender de uma função específica
    do PostgreSQL.
    """

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)


class TimestampMixin:
    """`created_at` / `updated_at`, mantidos pelo próprio banco (não pela
    aplicação) — evita relógios de aplicação divergentes entre instâncias."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class SoftDeleteMixin:
    """Estrutura para exclusão lógica — apenas o campo, sem filtragem
    automática de queries nem sobrescrita de `delete()`. Um módulo futuro
    que precisar de soft delete real implementa a lógica usando este campo
    como base, sem precisar alterar o schema.
    """

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )

    @property
    def is_deleted(self) -> bool:
        return self.deleted_at is not None


class VersionMixin:
    """Estrutura para bloqueio otimista futuro — apenas o campo contador.

    Nenhum incremento automático nem checagem de conflito é feita aqui
    (isso exigiria interceptar `flush`/`update` no nível do repositório,
    o que é regra de negócio da camada de persistência de um módulo
    específico, fora do escopo desta infraestrutura genérica).
    """

    version: Mapped[int] = mapped_column(default=1, server_default="1", nullable=False)


class AuditMixin:
    """Estrutura para auditoria futura — apenas os campos.

    Deliberadamente `str | None` sem chave estrangeira para uma tabela de
    usuários: essa tabela não existe ainda (Módulo 2.4 não cria entidades
    de domínio) e uma FK prematura acoplaria a camada ORM genérica a um
    módulo de autenticação que ainda não foi projetado. Nenhum valor é
    preenchido automaticamente — isso exigiria contexto de requisição
    (usuário autenticado), inexistente nesta camada.
    """

    created_by: Mapped[str | None] = mapped_column(nullable=True, default=None)
    updated_by: Mapped[str | None] = mapped_column(nullable=True, default=None)
