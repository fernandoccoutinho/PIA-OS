"""
Testes dos mixins ORM.

Usa subclasses concretas definidas apenas neste módulo, com SQLite em
arquivo temporário — nunca o `DATABASE_URL` do Postgres real. As tabelas
de teste registram-se no `Base` real (a mesma usada pelo Alembic) porque
o próprio objetivo aqui é provar que os mixins funcionam quando compostos
com o `Base` da aplicação — não há chamada a `alembic autogenerate` no
mesmo processo dos testes, então esse registro é inerte.
"""

import uuid
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker

from app.database.base import Base
from app.models.mixins import AuditMixin, SoftDeleteMixin, TimestampMixin, UUIDMixin, VersionMixin


class _MixinFixtureEntity(
    Base, UUIDMixin, TimestampMixin, SoftDeleteMixin, VersionMixin, AuditMixin
):
    __tablename__ = "test_mixin_fixture_entity"

    label: Mapped[str] = mapped_column(nullable=False)


@pytest.fixture
def mixin_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine, tables=[_MixinFixtureEntity.__table__])
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)
    session: Session = factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(engine, tables=[_MixinFixtureEntity.__table__])
        engine.dispose()


def test_uuid_mixin_generates_uuid_on_flush(mixin_session):
    entity = _MixinFixtureEntity(label="a")
    mixin_session.add(entity)
    mixin_session.flush()
    assert isinstance(entity.id, uuid.UUID)


def test_uuid_mixin_generates_distinct_ids(mixin_session):
    a = _MixinFixtureEntity(label="a")
    b = _MixinFixtureEntity(label="b")
    mixin_session.add_all([a, b])
    mixin_session.flush()
    assert a.id != b.id


def test_uuid_mixin_id_is_none_before_flush():
    # Documenta o comportamento real (não o que o docstring dizia antes de
    # ser corrigido): `default=` do SQLAlchemy só resolve no flush.
    entity = _MixinFixtureEntity(label="a")
    assert entity.id is None


def test_timestamp_mixin_sets_created_and_updated_at(mixin_session):
    entity = _MixinFixtureEntity(label="a")
    mixin_session.add(entity)
    mixin_session.commit()
    mixin_session.refresh(entity)

    assert isinstance(entity.created_at, datetime)
    assert isinstance(entity.updated_at, datetime)


def test_soft_delete_mixin_defaults_to_not_deleted():
    entity = _MixinFixtureEntity(label="a")
    assert entity.deleted_at is None
    assert entity.is_deleted is False


def test_soft_delete_mixin_is_deleted_reflects_field():
    entity = _MixinFixtureEntity(label="a")
    entity.deleted_at = datetime.now()
    assert entity.is_deleted is True


def test_version_mixin_defaults_to_one(mixin_session):
    entity = _MixinFixtureEntity(label="a")
    mixin_session.add(entity)
    mixin_session.commit()
    mixin_session.refresh(entity)
    assert entity.version == 1


def test_audit_mixin_fields_default_to_none():
    entity = _MixinFixtureEntity(label="a")
    assert entity.created_by is None
    assert entity.updated_by is None


def test_audit_mixin_fields_are_settable():
    entity = _MixinFixtureEntity(label="a")
    entity.created_by = "system"
    assert entity.created_by == "system"
