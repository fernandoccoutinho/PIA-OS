from app.repositories.base_repository import BaseRepository
from tests.fixtures.database import SampleModel


def test_create_and_get_by_id(sqlite_session):
    repo = BaseRepository(sqlite_session, SampleModel)
    created = repo.create(SampleModel(name="alpha"))
    sqlite_session.commit()

    fetched = repo.get_by_id(created.id)
    assert fetched is not None
    assert fetched.name == "alpha"


def test_get_by_id_returns_none_when_missing(sqlite_session):
    repo = BaseRepository(sqlite_session, SampleModel)
    assert repo.get_by_id(9999) is None


def test_list_returns_all_entities(sqlite_session):
    repo = BaseRepository(sqlite_session, SampleModel)
    repo.create(SampleModel(name="a"))
    repo.create(SampleModel(name="b"))
    sqlite_session.commit()

    results = repo.list()
    assert {r.name for r in results} == {"a", "b"}


def test_list_respects_limit_and_offset(sqlite_session):
    repo = BaseRepository(sqlite_session, SampleModel)
    for i in range(5):
        repo.create(SampleModel(name=f"item-{i}"))
    sqlite_session.commit()

    page = repo.list(limit=2, offset=1)
    assert len(page) == 2


def test_update_persists_changes(sqlite_session):
    repo = BaseRepository(sqlite_session, SampleModel)
    entity = repo.create(SampleModel(name="original"))
    sqlite_session.commit()

    entity.name = "changed"
    repo.update(entity)
    sqlite_session.commit()

    fetched = repo.get_by_id(entity.id)
    assert fetched.name == "changed"


def test_delete_removes_entity(sqlite_session):
    repo = BaseRepository(sqlite_session, SampleModel)
    entity = repo.create(SampleModel(name="to-delete"))
    sqlite_session.commit()
    entity_id = entity.id

    repo.delete(entity)
    sqlite_session.commit()

    assert repo.get_by_id(entity_id) is None


def test_exists_true_and_false(sqlite_session):
    repo = BaseRepository(sqlite_session, SampleModel)
    entity = repo.create(SampleModel(name="exists-check"))
    sqlite_session.commit()

    assert repo.exists(entity.id) is True
    assert repo.exists(9999) is False
