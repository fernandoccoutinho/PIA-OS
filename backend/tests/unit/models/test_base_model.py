import uuid
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Mapped, mapped_column, sessionmaker

from app.database.base import Base
from app.models.base_model import BaseModel
from app.models.mixins import SoftDeleteMixin


def test_base_model_is_abstract():
    assert BaseModel.__abstract__ is True


def test_base_model_shares_the_real_declarative_base():
    assert issubclass(BaseModel, Base)


class _ConcreteEntity(BaseModel):
    __tablename__ = "test_base_model_concrete_entity"

    name: Mapped[str] = mapped_column(nullable=False)


class _ConcreteEntityWithSoftDelete(BaseModel, SoftDeleteMixin):
    __tablename__ = "test_base_model_soft_delete_entity"

    name: Mapped[str] = mapped_column(nullable=False)


@pytest.fixture
def base_model_session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[_ConcreteEntity.__table__, _ConcreteEntityWithSoftDelete.__table__],
    )
    factory = sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(
            engine,
            tables=[_ConcreteEntity.__table__, _ConcreteEntityWithSoftDelete.__table__],
        )
        engine.dispose()


def test_concrete_entity_has_id_and_timestamps(base_model_session):
    entity = _ConcreteEntity(name="x")
    base_model_session.add(entity)
    base_model_session.commit()
    base_model_session.refresh(entity)

    assert isinstance(entity.id, uuid.UUID)
    assert isinstance(entity.created_at, datetime)
    assert isinstance(entity.updated_at, datetime)


def test_concrete_entity_without_soft_delete_mixin_has_no_deleted_at():
    assert not hasattr(_ConcreteEntity(name="x"), "deleted_at")


def test_concrete_entity_composed_with_soft_delete_has_the_field(base_model_session):
    entity = _ConcreteEntityWithSoftDelete(name="x")
    base_model_session.add(entity)
    base_model_session.commit()
    base_model_session.refresh(entity)

    assert entity.deleted_at is None
    assert entity.is_deleted is False
