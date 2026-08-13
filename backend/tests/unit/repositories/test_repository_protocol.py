from app.repositories.base_repository import BaseRepository
from app.repositories.repository_protocol import RepositoryProtocol
from tests.fixtures.database import SampleModel


def test_base_repository_satisfies_the_protocol(sqlite_session):
    repo = BaseRepository(sqlite_session, SampleModel)
    assert isinstance(repo, RepositoryProtocol)


def test_protocol_requires_all_five_methods():
    required = {"get_by_id", "list", "add", "update", "delete"}
    declared = {name for name in dir(RepositoryProtocol) if not name.startswith("_")}
    assert required.issubset(declared)


class _FakeRepository:
    """Implementação mínima e independente — não herda de BaseRepository —
    usada para provar que o Protocol é estrutural (duck typing), não
    nominal."""

    def get_by_id(self, entity_id):
        return None

    def list(self, *, limit=None, offset=None):
        return []

    def add(self, entity):
        return entity

    def update(self, entity):
        return entity

    def delete(self, entity):
        return None


def test_structurally_compatible_class_satisfies_protocol_without_inheritance():
    assert isinstance(_FakeRepository(), RepositoryProtocol)


def test_incomplete_implementation_does_not_satisfy_protocol():
    class _Incomplete:
        def get_by_id(self, entity_id):
            return None

    assert isinstance(_Incomplete(), RepositoryProtocol) is False
