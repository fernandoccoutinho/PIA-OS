"""
Catálogo do kernel — quatro identidades que **nunca** colapsam.

```text
FAMÍLIA != RELEASE != PROVEDOR_DE_ACESSO != CONEXÃO
```

Colapsar as quatro é o erro que faz "tenho plano pago" virar "posso
chamar a API", e "endpoint compatível" virar "é a marca X". Cada uma tem
tabela própria, chave própria e ciclo próprio:

```text
ProviderFamily  slug curado, estável            1..N ModelFamily
ModelFamily     slug + família                  1..N ModelRelease
ModelRelease    id oficial do provedor          pertence a 1 família; TTL
AccessProvider  slug do operador do endpoint    serve 0..N releases
```

Não há enum de marcas e não há lista estática de releases: marcas são
linhas curadas e releases são **descobertos**, com validade. Um enum de
marcas exigiria migração a cada operador novo e transformaria curadoria
em schema.
"""

import uuid
from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.connections.models.enums import CapabilitySource, GenericEndpointType
from app.models.base_model import BaseModel

MAX_SLUG_LENGTH = 128
"""Slug curado. Curto o bastante para ser lido, longo o bastante para ser único."""

MAX_DISPLAY_NAME_LENGTH = 255

MAX_RELEASE_ID_LENGTH = 255
"""Identificador **oficial** do provedor, preservado byte a byte."""


class ProviderFamily(BaseModel):
    """Família de provedor — unidade de navegação humana, curada.

    Existe para o olho, não para a autoridade: a curadoria orienta a
    escolha e **não** prova entitlement, disponibilidade nem identidade
    de operador.
    """

    __tablename__ = "connection_provider_families"

    __table_args__ = (
        UniqueConstraint("slug", name="uq_connection_provider_families_slug"),
        CheckConstraint(
            "length(btrim(slug)) > 0",
            name="ck_connection_provider_families_slug_not_blank",
        ),
        CheckConstraint(
            "length(btrim(display_name)) > 0",
            name="ck_connection_provider_families_display_name_not_blank",
        ),
    )

    slug: Mapped[str] = mapped_column(String(MAX_SLUG_LENGTH), nullable=False)
    display_name: Mapped[str] = mapped_column(String(MAX_DISPLAY_NAME_LENGTH), nullable=False)


class ModelFamily(BaseModel):
    """Família de modelos dentro de uma família de provedor.

    Chave natural `(provider_family_id, slug)`: dois provedores podem
    curar famílias homônimas, e forçar unicidade global de slug faria a
    curadoria de um limitar a do outro.
    """

    __tablename__ = "connection_model_families"

    __table_args__ = (
        UniqueConstraint(
            "provider_family_id", "slug", name="uq_connection_model_families_family_slug"
        ),
        CheckConstraint(
            "length(btrim(slug)) > 0", name="ck_connection_model_families_slug_not_blank"
        ),
        Index("ix_connection_model_families_provider", "provider_family_id"),
    )

    provider_family_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("connection_provider_families.id", name="fk_connection_model_families_provider"),
        nullable=False,
    )
    slug: Mapped[str] = mapped_column(String(MAX_SLUG_LENGTH), nullable=False)
    display_name: Mapped[str] = mapped_column(String(MAX_DISPLAY_NAME_LENGTH), nullable=False)


class ModelRelease(BaseModel):
    """Release concreto, **descoberto** e com validade.

    ```text
    fonte oficial > cache dentro do TTL > cache vencido (DEGRADED) > nada
    ```

    `discovered_at` e `valid_until` existem para que "cache vencido"
    tenha como ser reconhecido sem worker: a validade é comparada na
    leitura, e vencer **degrada**, nunca substitui nem inventa.

    `provider_release_id` guarda o identificador do provedor exatamente
    como ele veio — normalizar aqui faria o kernel afirmar um nome que o
    operador não usa.
    """

    __tablename__ = "connection_model_releases"

    __table_args__ = (
        UniqueConstraint(
            "model_family_id",
            "provider_release_id",
            name="uq_connection_model_releases_family_release",
        ),
        CheckConstraint(
            "length(btrim(provider_release_id)) > 0",
            name="ck_connection_model_releases_release_id_not_blank",
        ),
        CheckConstraint(
            "valid_until > discovered_at",
            name="ck_connection_model_releases_ttl_positive",
        ),
        Index("ix_connection_model_releases_family", "model_family_id"),
    )

    model_family_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("connection_model_families.id", name="fk_connection_model_releases_family"),
        nullable=False,
    )
    provider_release_id: Mapped[str] = mapped_column(String(MAX_RELEASE_ID_LENGTH), nullable=False)
    discovered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    valid_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    discovery_source: Mapped[CapabilitySource] = mapped_column(
        SAEnum(
            CapabilitySource,
            name="connection_capability_source",
            native_enum=False,
            length=32,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )


class AccessProvider(BaseModel):
    """Operador do endpoint — quem serve, que não é quem fabricou o modelo.

    ```text
    endpoint compatível NÃO falsifica operador nem marca
    ```

    `endpoint_type` é o tipo **genérico** observado. Ele descreve
    protocolo, e protocolo é tudo que ele prova.
    """

    __tablename__ = "connection_access_providers"

    __table_args__ = (
        UniqueConstraint("slug", name="uq_connection_access_providers_slug"),
        CheckConstraint(
            "length(btrim(slug)) > 0", name="ck_connection_access_providers_slug_not_blank"
        ),
    )

    slug: Mapped[str] = mapped_column(String(MAX_SLUG_LENGTH), nullable=False)
    display_name: Mapped[str] = mapped_column(String(MAX_DISPLAY_NAME_LENGTH), nullable=False)
    endpoint_type: Mapped[GenericEndpointType] = mapped_column(
        SAEnum(
            GenericEndpointType,
            name="connection_generic_endpoint_type",
            native_enum=False,
            length=40,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
    )
