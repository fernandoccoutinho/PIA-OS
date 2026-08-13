"""
Testes de `ObjectRepository` — §30, §31, §32 (C4, C6), §33 do módulo
E3.1; §5 do módulo E3.1.2 (D1-D6, ordenação determinística).
"""

import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import text

from app.cognitive.models.cognitive_object import CognitiveObject
from app.cognitive.repositories.object_repository import ObjectRepository
from app.repositories.exceptions import EntityNotFoundError
from app.repositories.unit_of_work import UnitOfWork


@pytest.fixture
def repo(cognitive_session):
    return ObjectRepository(cognitive_session)


# --- CREATE / GET BY ID ---


def test_create_and_get_by_id(repo, cognitive_session):
    created = repo.add(CognitiveObject())
    cognitive_session.commit()

    fetched = repo.get_by_id(created.id)
    assert fetched is not None
    assert fetched.id == created.id


def test_get_by_id_not_found_returns_none(repo):
    assert repo.get_by_id(uuid.uuid4()) is None


def test_get_by_id_or_raise_raises_entity_not_found(repo):
    with pytest.raises(EntityNotFoundError):
        repo.get_by_id_or_raise(uuid.uuid4())


# --- LIST / PAGINATION ---


def test_list_returns_created_objects(repo, cognitive_session):
    repo.add(CognitiveObject())
    repo.add(CognitiveObject())
    cognitive_session.commit()

    assert len(repo.list()) == 2


def test_list_respects_limit_and_offset(repo, cognitive_session):
    for _ in range(5):
        repo.add(CognitiveObject())
    cognitive_session.commit()

    assert len(repo.list(limit=2, offset=1)) == 2


def test_paginate_returns_page_with_total(repo, cognitive_session):
    for _ in range(3):
        repo.add(CognitiveObject())
    cognitive_session.commit()

    page = repo.paginate(page=1, page_size=2)
    assert len(page.items) == 2
    assert page.total == 3
    assert page.has_next is True


def test_paginate_rejects_page_below_one(repo):
    """Validação preservada explicitamente (correção E3.1.2): desde que
    `paginate()` parou de delegar a `BaseRepository.paginate()` para
    poder ordenar deterministicamente, a validação de `page`/`page_size`
    passou a ser responsabilidade própria de `ObjectRepository` — não
    deve ser perdida silenciosamente."""
    with pytest.raises(ValueError, match="page deve ser >= 1"):
        repo.paginate(page=0)


def test_paginate_rejects_page_size_below_one(repo):
    with pytest.raises(ValueError, match="page_size deve ser >= 1"):
        repo.paginate(page_size=0)


# --- UPDATE ---


def test_update_persists_clid_change(repo, cognitive_session):
    entity = repo.add(CognitiveObject())
    cognitive_session.commit()

    new_clid = uuid.uuid4()
    entity.clid = new_clid
    repo.update(entity)
    cognitive_session.commit()

    fetched = repo.get_by_id(entity.id)
    assert fetched.clid == new_clid


# --- SOFT DELETE — §8 do módulo E3.1, correção E3.1.1 ---


def test_soft_delete_marks_deleted_at_without_removing_row(repo, cognitive_session):
    entity = repo.add(CognitiveObject())
    cognitive_session.commit()

    repo.soft_delete(entity)
    cognitive_session.commit()

    assert entity.deleted_at is not None
    assert entity.is_deleted is True


def test_sd1_soft_deleted_object_excluded_from_get_by_id_by_default(repo, cognitive_session):
    entity = repo.add(CognitiveObject())
    cognitive_session.commit()
    repo.soft_delete(entity)
    cognitive_session.commit()

    assert repo.get_by_id(entity.id) is None
    assert repo.get_by_id(entity.id, include_deleted=True) is not None


def test_sd2_soft_deleted_object_excluded_from_list_by_default(repo, cognitive_session):
    kept = repo.add(CognitiveObject())
    deleted = repo.add(CognitiveObject())
    cognitive_session.commit()
    repo.soft_delete(deleted)
    cognitive_session.commit()

    active_ids = {o.id for o in repo.list()}
    assert kept.id in active_ids
    assert deleted.id not in active_ids
    assert len(repo.list(include_deleted=True)) == 2


def test_sd3_soft_deleted_object_excluded_from_paginate_by_default(repo, cognitive_session):
    repo.add(CognitiveObject())
    deleted = repo.add(CognitiveObject())
    cognitive_session.commit()
    repo.soft_delete(deleted)
    cognitive_session.commit()

    page = repo.paginate(page=1, page_size=10)
    assert len(page.items) == 1

    page_all = repo.paginate(page=1, page_size=10, include_deleted=True)
    assert len(page_all.items) == 2


def test_sd4_page_total_excludes_soft_deleted(repo, cognitive_session):
    """Correção E3.1.1 (C1): antes, `Page.total` refletia a contagem
    SEM excluir soft-deleted — regressão coberta explicitamente aqui."""
    for _ in range(3):
        repo.add(CognitiveObject())
    deleted = repo.add(CognitiveObject())
    cognitive_session.commit()
    repo.soft_delete(deleted)
    cognitive_session.commit()

    page = repo.paginate(page=1, page_size=2)
    assert page.total == 3  # não 4

    page_all = repo.paginate(page=1, page_size=2, include_deleted=True)
    assert page_all.total == 4


def test_sd5_limit_offset_operate_over_the_correct_active_set(repo, cognitive_session):
    """`list(limit=, offset=)` deve operar sobre o conjunto de ativos
    já filtrado no SQL — não sobre a tabela inteira seguida de corte
    em memória (correção E3.1.1, C1)."""
    objs = [repo.add(CognitiveObject()) for _ in range(6)]
    cognitive_session.commit()
    # soft-delete os 3 primeiros por created_at (não necessariamente os
    # primeiros na ordem de retorno do banco, mas suficiente para o teste)
    for o in objs[:3]:
        repo.soft_delete(o)
    cognitive_session.commit()

    active_ids = {o.id for o in objs[3:]}
    page1 = repo.list(limit=2, offset=0)
    page2 = repo.list(limit=2, offset=2)
    combined_ids = {o.id for o in page1} | {o.id for o in page2}

    assert len(page1) == 2
    assert len(page2) == 1  # só restam 3 ativos no total
    assert combined_ids == active_ids


def test_sd6_page_is_not_artificially_short_due_to_in_memory_filtering(repo, cognitive_session):
    """Cenário exato do §4 do prompt corretivo: 20 registros
    selecionados pelo banco, metade soft-deleted — uma página não deve
    ficar artificialmente curta por filtragem posterior em memória.
    Como o filtro agora é aplicado no SQL, `page_size` itens ativos são
    sempre retornados enquanto houver ativos suficientes."""
    objs = [repo.add(CognitiveObject()) for _ in range(20)]
    cognitive_session.commit()
    for o in objs[::2]:  # 10 soft-deleted, intercalados
        repo.soft_delete(o)
    cognitive_session.commit()

    page = repo.paginate(page=1, page_size=10)
    assert len(page.items) == 10  # todos os 10 ativos, não menos
    assert page.total == 10
    assert all(not item.is_deleted for item in page.items)


def test_sd7_interleaved_deletions_do_not_corrupt_pagination(repo, cognitive_session):
    """Objetos soft-deleted intercalados com ativos não corrompem a
    paginação — cada página soma exatamente `page_size` (exceto a
    última) e a união de todas as páginas é exatamente o conjunto
    ativo, sem duplicatas nem lacunas."""
    objs = [repo.add(CognitiveObject()) for _ in range(9)]
    cognitive_session.commit()
    for i in (0, 2, 4, 6, 8):  # 5 soft-deleted intercalados, 4 ativos
        repo.soft_delete(objs[i])
    cognitive_session.commit()

    expected_active_ids = {objs[i].id for i in (1, 3, 5, 7)}

    seen_ids: set = set()
    page_number = 1
    while True:
        page = repo.paginate(page=page_number, page_size=3)
        if not page.items:
            break
        seen_ids.update(o.id for o in page.items)
        if not page.has_next:
            break
        page_number += 1

    assert seen_ids == expected_active_ids


def test_hard_delete_still_available_when_genuinely_needed(repo, cognitive_session):
    """`delete()` (herdado de BaseRepository) continua disponível — não
    removido, apenas não é o caminho recomendado para CognitiveObject
    (§14)."""
    entity = repo.add(CognitiveObject())
    cognitive_session.commit()
    entity_id = entity.id

    repo.delete(entity)
    cognitive_session.commit()

    assert repo.get_by_id(entity_id, include_deleted=True) is None


# --- TRANSAÇÕES / ROLLBACK — repositório não commita indevidamente ---


def test_repository_does_not_commit_implicitly(cognitive_session):
    repo_local = ObjectRepository(cognitive_session)
    repo_local.add(CognitiveObject())
    cognitive_session.rollback()  # nunca commitado

    assert cognitive_session.query(CognitiveObject).count() == 0


def test_transaction_failure_rolls_back_via_unit_of_work(cognitive_sqlite_session_factory):
    with pytest.raises(ValueError), UnitOfWork(cognitive_sqlite_session_factory) as uow:
        repo_uow = ObjectRepository(uow.session)
        repo_uow.add(CognitiveObject())
        raise ValueError("falha simulada dentro da transação")

    with UnitOfWork(cognitive_sqlite_session_factory) as uow:
        repo_uow = ObjectRepository(uow.session)
        assert len(repo_uow.list()) == 0


def test_multiple_creates_share_one_transaction_via_unit_of_work(
    cognitive_sqlite_session_factory,
):
    with UnitOfWork(cognitive_sqlite_session_factory) as uow:
        repo_uow = ObjectRepository(uow.session)
        repo_uow.add(CognitiveObject())
        repo_uow.add(CognitiveObject())
        uow.commit()

    with UnitOfWork(cognitive_sqlite_session_factory) as uow:
        repo_uow = ObjectRepository(uow.session)
        assert len(repo_uow.list()) == 2


# --- TEST C6: repositório preserva dois objetos independentes com
#     payload idêntico (aqui, ausência de payload) ---


def test_repository_preserves_two_independently_created_identical_objects(repo, cognitive_session):
    a = repo.add(CognitiveObject())
    b = repo.add(CognitiveObject())
    cognitive_session.commit()

    assert a.id != b.id
    assert repo.get_by_id(a.id) is not None
    assert repo.get_by_id(b.id) is not None
    assert len(repo.list()) == 2


# --- TEST C4: nenhum comportamento automático de vencedor/ranking ---


def test_no_ranking_or_winner_selection_method_exists_on_repository():
    """`ObjectRepository` não expõe nenhum método de ranking/seleção
    automática de "melhor" objeto (§21, TEST C4)."""
    forbidden_method_names = {
        "best_object",
        "rank",
        "select_winner",
        "cout_score",
        "get_best",
    }
    repo_methods = {name for name in dir(ObjectRepository) if not name.startswith("_")}
    assert repo_methods.isdisjoint(forbidden_method_names)


# --- ORDENAÇÃO DETERMINÍSTICA (correção E3.1.2) ---


def test_d1_multiple_objects_always_return_in_the_same_order(repo, cognitive_session):
    for _ in range(10):
        repo.add(CognitiveObject())
    cognitive_session.commit()

    first_call = [o.id for o in repo.list()]
    second_call = [o.id for o in repo.list()]
    assert first_call == second_call


def test_d2_objects_with_same_created_at_are_tie_broken_by_id(repo, cognitive_session):
    """Quando `created_at` coincide (ex.: dois objetos gravados na
    mesma transação/mesmo instante), `id` desempata deterministicamente."""
    a = repo.add(CognitiveObject())
    b = repo.add(CognitiveObject())
    cognitive_session.commit()

    same_timestamp = datetime(2026, 1, 1, tzinfo=UTC)
    cognitive_session.execute(
        text("UPDATE cognitive_objects SET created_at = :ts"), {"ts": same_timestamp}
    )
    cognitive_session.commit()

    ids = [o.id for o in repo.list()]
    assert ids == sorted([a.id, b.id])


def test_d3_pagination_across_pages_does_not_duplicate_objects(repo, cognitive_session):
    for _ in range(9):
        repo.add(CognitiveObject())
    cognitive_session.commit()

    page1 = repo.paginate(page=1, page_size=4)
    page2 = repo.paginate(page=2, page_size=4)
    page3 = repo.paginate(page=3, page_size=4)

    all_ids = (
        [o.id for o in page1.items] + [o.id for o in page2.items] + [o.id for o in page3.items]
    )
    assert len(all_ids) == len(set(all_ids))


def test_d4_pagination_across_pages_does_not_lose_objects(repo, cognitive_session):
    created = [repo.add(CognitiveObject()) for _ in range(9)]
    cognitive_session.commit()

    page1 = repo.paginate(page=1, page_size=4)
    page2 = repo.paginate(page=2, page_size=4)
    page3 = repo.paginate(page=3, page_size=4)

    all_ids = (
        {o.id for o in page1.items} | {o.id for o in page2.items} | {o.id for o in page3.items}
    )
    assert all_ids == {o.id for o in created}


def test_d3_d4_pagination_sequence_matches_list_sequence_exactly(repo, cognitive_session):
    """Junta D3+D4 numa comparação de sequência real (não `set`): a
    concatenação das páginas deve ser EXATAMENTE igual à sequência de
    `list()` — não apenas o mesmo conjunto (§6 do prompt: não mascarar
    ordem com `set`/`sorted`)."""
    for _ in range(9):
        repo.add(CognitiveObject())
    cognitive_session.commit()

    full_sequence = [o.id for o in repo.list()]

    paged_sequence: list = []
    for page_number in (1, 2, 3):
        page = repo.paginate(page=page_number, page_size=4)
        paged_sequence.extend(o.id for o in page.items)

    assert paged_sequence == full_sequence


def test_d5_soft_deleted_objects_do_not_break_order_stability(repo, cognitive_session):
    objs = [repo.add(CognitiveObject()) for _ in range(10)]
    cognitive_session.commit()

    full_sequence_before = [o.id for o in repo.list()]

    for o in objs[::3]:  # soft-delete intercalado
        repo.soft_delete(o)
    cognitive_session.commit()

    deleted_ids = {o.id for o in objs[::3]}
    expected_sequence = [i for i in full_sequence_before if i not in deleted_ids]

    assert [o.id for o in repo.list()] == expected_sequence


def test_d6_two_consecutive_executions_return_the_same_id_sequence(repo, cognitive_session):
    for _ in range(7):
        repo.add(CognitiveObject())
    cognitive_session.commit()

    run_1 = [o.id for o in repo.list()]
    run_2 = [o.id for o in repo.list()]
    run_3 = [o.id for o in repo.paginate(page=1, page_size=100).items]

    assert run_1 == run_2 == run_3


# --- CLASSIFICAÇÃO DE COLISÃO (correção E3.2.1, débito C1) ---


class _FakeDriverError:
    """Stand-in mínimo para o objeto `.orig` de um driver — expõe só
    os atributos que `_is_unique_or_pk_violation` inspeciona."""

    def __init__(self, *, sqlstate: str | None = None, sqlite_errorname: str | None = None):
        if sqlstate is not None:
            self.sqlstate = sqlstate
        if sqlite_errorname is not None:
            self.sqlite_errorname = sqlite_errorname


def test_is_unique_or_pk_violation_true_for_postgres_unique_sqlstate():
    from app.cognitive.repositories.object_repository import _is_unique_or_pk_violation

    exc = _build_cause_exc(_FakeDriverError(sqlstate="23505"))
    assert _is_unique_or_pk_violation(exc) is True


def test_is_unique_or_pk_violation_false_for_postgres_not_null_sqlstate():
    """SQLSTATE 23502 = not_null_violation — não é unicidade (C1.2)."""
    from app.cognitive.repositories.object_repository import _is_unique_or_pk_violation

    exc = _build_cause_exc(_FakeDriverError(sqlstate="23502"))
    assert _is_unique_or_pk_violation(exc) is False


def test_is_unique_or_pk_violation_true_for_sqlite_primary_key():
    from app.cognitive.repositories.object_repository import _is_unique_or_pk_violation

    exc = _build_cause_exc(_FakeDriverError(sqlite_errorname="SQLITE_CONSTRAINT_PRIMARYKEY"))
    assert _is_unique_or_pk_violation(exc) is True


def test_is_unique_or_pk_violation_true_for_sqlite_unique():
    from app.cognitive.repositories.object_repository import _is_unique_or_pk_violation

    exc = _build_cause_exc(_FakeDriverError(sqlite_errorname="SQLITE_CONSTRAINT_UNIQUE"))
    assert _is_unique_or_pk_violation(exc) is True


def test_is_unique_or_pk_violation_false_for_sqlite_foreign_key():
    """SQLITE_CONSTRAINT_FOREIGNKEY não é unicidade (C1.2)."""
    from app.cognitive.repositories.object_repository import _is_unique_or_pk_violation

    exc = _build_cause_exc(_FakeDriverError(sqlite_errorname="SQLITE_CONSTRAINT_FOREIGNKEY"))
    assert _is_unique_or_pk_violation(exc) is False


def test_is_unique_or_pk_violation_false_when_orig_is_none():
    from app.cognitive.repositories.object_repository import _is_unique_or_pk_violation

    exc = _build_cause_exc(None)
    assert _is_unique_or_pk_violation(exc) is False


def test_is_unique_or_pk_violation_false_when_no_cause_chain():
    """`PersistenceError` sem `__cause__` (cenário hipotético,
    não deve ocorrer via `BaseRepository`, mas a função não deve
    quebrar)."""
    from app.cognitive.repositories.object_repository import _is_unique_or_pk_violation
    from app.repositories.exceptions import PersistenceError

    exc = PersistenceError("sem causa")
    assert _is_unique_or_pk_violation(exc) is False


def _build_cause_exc(orig: object | None):
    from app.repositories.exceptions import PersistenceError

    cause = Exception()
    if orig is not None:
        cause.orig = orig  # type: ignore[attr-defined]
    try:
        raise PersistenceError("falha simulada") from cause
    except PersistenceError as exc:
        return exc


def test_c1_1_pk_unique_collision_becomes_coid_collision_error(repo, cognitive_session):
    from app.cognitive.errors.exceptions import CoidCollisionError

    existing = repo.add(CognitiveObject())
    cognitive_session.commit()

    duplicate = CognitiveObject()
    duplicate.id = existing.id
    with pytest.raises(CoidCollisionError) as exc_info:
        repo.add(duplicate)
    assert exc_info.value.code == "PIA-8004"
    cognitive_session.rollback()


def test_c1_2_unrelated_persistence_error_is_not_reclassified(monkeypatch, repo):
    """Simula, via monkeypatch de `BaseRepository.add`, um
    `PersistenceError` cuja causa não é violação de unicidade — deve
    continuar propagando como `PersistenceError`, nunca virar
    `CoidCollisionError`. Não é possível construir esse cenário de
    ponta a ponta contra o schema real de `cognitive_objects` hoje
    (nenhuma constraint além da PK, e `default=` do SQLAlchemy
    reaplica o valor mesmo quando um atributo NOT NULL é setado
    explicitamente para `None` — confirmado empiricamente durante o
    desenvolvimento desta correção) — a classificação em si já está
    coberta isoladamente pelos testes `_is_unique_or_pk_violation`
    acima; este teste cobre o caminho completo de `add()`."""
    from app.cognitive.errors.exceptions import CoidCollisionError
    from app.repositories.base_repository import BaseRepository
    from app.repositories.exceptions import PersistenceError

    fake_cause = Exception()
    fake_cause.orig = _FakeDriverError(sqlstate="23502")  # not_null, não unicidade

    def _raise_unrelated_persistence_error(self, entity):
        raise PersistenceError("falha simulada não relacionada a unicidade") from fake_cause

    monkeypatch.setattr(BaseRepository, "add", _raise_unrelated_persistence_error)

    with pytest.raises(PersistenceError) as exc_info:
        repo.add(CognitiveObject())
    assert not isinstance(exc_info.value, CoidCollisionError)


def test_c1_3_existing_object_is_not_altered_on_collision(repo, cognitive_session):
    existing = repo.add(CognitiveObject())
    cognitive_session.commit()
    original_created_at = existing.created_at

    duplicate = CognitiveObject()
    duplicate.id = existing.id
    from app.cognitive.errors.exceptions import CoidCollisionError

    with pytest.raises(CoidCollisionError):
        repo.add(duplicate)
    cognitive_session.rollback()

    reloaded = repo.get_by_id(existing.id)
    assert reloaded is not None
    assert reloaded.created_at == original_created_at


def test_c1_4_rollback_remains_correct_after_collision(cognitive_sqlite_session_factory):
    from app.cognitive.errors.exceptions import CoidCollisionError
    from app.repositories.unit_of_work import UnitOfWork

    with UnitOfWork(cognitive_sqlite_session_factory) as uow:
        repo_uow = ObjectRepository(uow.session)
        existing = repo_uow.add(CognitiveObject())
        uow.commit()
        existing_id = existing.id

    with pytest.raises(CoidCollisionError), UnitOfWork(cognitive_sqlite_session_factory) as uow:
        repo_uow = ObjectRepository(uow.session)
        duplicate = CognitiveObject()
        duplicate.id = existing_id
        repo_uow.add(duplicate)

    with UnitOfWork(cognitive_sqlite_session_factory) as uow:
        repo_uow = ObjectRepository(uow.session)
        assert len(repo_uow.list()) == 1
