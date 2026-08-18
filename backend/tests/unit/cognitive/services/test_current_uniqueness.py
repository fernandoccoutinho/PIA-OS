"""
Testes do invariante `COUNT(CURRENT) <= 1` por CLID — correção E3.4.1
(débitos U1-U5, cenário adversarial do prompt corretivo).
"""

import uuid

import pytest

from app.cognitive.errors.exceptions import RevisionCurrentUniquenessViolationError
from app.cognitive.models.cognitive_object import CognitiveObject
from app.cognitive.models.enums import RevisionStatus
from app.cognitive.repositories.lineage_repository import LineageRepository
from app.cognitive.repositories.object_repository import ObjectRepository
from app.cognitive.repositories.transformation_repository import TransformationRepository
from app.cognitive.services.clid_manager import ClidManager
from app.cognitive.services.version_manager import VersionManager


@pytest.fixture
def objects(cognitive_session):
    return ObjectRepository(cognitive_session)


@pytest.fixture
def lineage(cognitive_session):
    return LineageRepository(cognitive_session)


@pytest.fixture
def transformations(cognitive_session):
    return TransformationRepository(cognitive_session)


@pytest.fixture
def clid_manager(objects, lineage):
    return ClidManager(objects, lineage)


@pytest.fixture
def version_manager(objects, clid_manager, transformations):
    return VersionManager(objects, clid_manager, transformations)


# --- U1: escopo semântico documentado/testável ---


def test_u1_current_uniqueness_scope_is_clid(objects, version_manager, cognitive_session):
    """O escopo de `COUNT(CURRENT) <= 1` é o CLID — verificado
    diretamente: duas revisões de linhas com CLID **diferentes** podem
    ambas ser `CURRENT` simultaneamente (não é um invariante global do
    sistema, é por CLID)."""
    source_1 = objects.add(CognitiveObject())
    source_2 = objects.add(CognitiveObject())
    cognitive_session.commit()

    current_1, _, _ = version_manager.revise(source_1, operation_type="revise")
    current_2, _, _ = version_manager.revise(source_2, operation_type="revise")
    cognitive_session.commit()

    assert current_1.clid != current_2.clid
    assert current_1.revision_status == RevisionStatus.CURRENT
    assert current_2.revision_status == RevisionStatus.CURRENT  # dois CURRENT, CLIDs diferentes


# --- U2: revise() com source errado não cria um segundo CURRENT ---


def test_u2_wrong_source_revise_cannot_create_second_current(
    objects, version_manager, cognitive_session
):
    """Cenário adversarial exato do prompt corretivo: `A` é `CURRENT`;
    `B` compartilha o mesmo CLID mas não tem `revision_status`
    (branch de `DERIVATION`). `revise(B)` não pode produzir um segundo
    `CURRENT` para o mesmo CLID."""
    a = objects.add(CognitiveObject())
    cognitive_session.commit()
    a.revision_status = RevisionStatus.CURRENT
    cognitive_session.commit()

    b, _, _ = version_manager.derive(a, operation_type="summarize")
    cognitive_session.commit()
    assert b.clid == a.clid
    assert b.revision_status is None

    with pytest.raises(RevisionCurrentUniquenessViolationError) as exc_info:
        version_manager.revise(b, operation_type="malicious revise")
    assert exc_info.value.code == "PIA-8012"
    cognitive_session.rollback()


def test_u2_rejection_happens_before_any_write(objects, version_manager, cognitive_session):
    """A pré-checagem rejeita antes mesmo de criar `target` — nenhum
    objeto órfão é criado pela tentativa adversarial."""
    a = objects.add(CognitiveObject())
    cognitive_session.commit()
    a.revision_status = RevisionStatus.CURRENT
    cognitive_session.commit()

    b, _, _ = version_manager.derive(a, operation_type="summarize")
    cognitive_session.commit()
    count_before = len(objects.list())

    with pytest.raises(RevisionCurrentUniquenessViolationError):
        version_manager.revise(b, operation_type="malicious revise")

    assert len(objects.list()) == count_before  # nenhum target criado


# --- U3: adversarial sequencial preserva unicidade ---


def test_u3_sequential_adversarial_revise_preserves_uniqueness(
    objects, version_manager, cognitive_session
):
    """Múltiplas tentativas sequenciais de `revise()` sobre diferentes
    branches do mesmo CLID nunca produzem mais de um `CURRENT`."""
    a = objects.add(CognitiveObject())
    cognitive_session.commit()
    a.revision_status = RevisionStatus.CURRENT
    cognitive_session.commit()

    b, _, _ = version_manager.derive(a, operation_type="summarize")
    c, _, _ = version_manager.derive(a, operation_type="translate")
    cognitive_session.commit()

    for branch in (b, c):
        with pytest.raises(RevisionCurrentUniquenessViolationError):
            version_manager.revise(branch, operation_type="malicious")
        cognitive_session.rollback()

    # o fluxo legítimo continua funcionando após as tentativas rejeitadas
    a_reloaded = objects.get_by_id(a.id)
    d, _, _ = version_manager.revise(a_reloaded, operation_type="legitimate revise")
    cognitive_session.commit()

    all_objects = objects.list()
    currents = [
        o for o in all_objects if o.clid == a.clid and o.revision_status == RevisionStatus.CURRENT
    ]
    assert len(currents) == 1
    assert currents[0].id == d.id


# --- U5: banco rejeita CURRENT duplicado mesmo com bypass da pré-checagem ---


def test_u5_database_level_invariant_rejects_duplicate_current_bypassing_precheck(
    objects, cognitive_session
):
    """Mesmo contornando `VersionManager` inteiramente (manipulação
    direta do modelo, como no exemplo adversarial do prompt corretivo)
    — a autoridade final é o índice único parcial no banco, não a
    pré-checagem do serviço."""
    shared_clid = uuid.uuid4()
    a = CognitiveObject()
    a.clid = shared_clid
    a.revision_status = RevisionStatus.CURRENT
    cognitive_session.add(a)
    cognitive_session.commit()

    b = CognitiveObject()
    b.clid = shared_clid
    cognitive_session.add(b)
    cognitive_session.commit()

    b.revision_status = RevisionStatus.CURRENT
    with pytest.raises(Exception) as exc_info:  # IntegrityError — nível de banco, não de domínio
        cognitive_session.commit()
    assert "unique" in str(exc_info.value).lower() or "UNIQUE" in str(exc_info.value)
    cognitive_session.rollback()


def test_derivation_branches_are_never_constrained_by_the_current_index(
    objects, version_manager, cognitive_session
):
    """Confirma explicitamente que o índice não afeta `DERIVATION`:
    múltiplos branches do mesmo CLID, todos sem `revision_status`,
    coexistem livremente — não há limite de quantidade."""
    a = objects.add(CognitiveObject())
    cognitive_session.commit()

    branches = [version_manager.derive(a, operation_type=f"op{i}")[0] for i in range(5)]
    cognitive_session.commit()

    assert all(b.clid == a.clid for b in branches)
    assert all(b.revision_status is None for b in branches)
    assert len({b.id for b in branches}) == 5  # todos distintos, todos coexistindo


# --- Classificação de violação (sinal estruturado, isolado) ---


class _FakeDriverError:
    def __init__(self, *, sqlstate: str | None = None, sqlite_errorname: str | None = None):
        if sqlstate is not None:
            self.sqlstate = sqlstate
        if sqlite_errorname is not None:
            self.sqlite_errorname = sqlite_errorname


def _build_persistence_error(orig: object | None):
    from app.repositories.exceptions import PersistenceError

    cause = Exception()
    if orig is not None:
        cause.orig = orig  # type: ignore[attr-defined]
    try:
        raise PersistenceError("falha simulada") from cause
    except PersistenceError as exc:
        return exc


def test_classify_postgres_unique_violation_as_current_uniqueness():
    from app.cognitive.services.version_manager import _is_current_uniqueness_violation

    exc = _build_persistence_error(_FakeDriverError(sqlstate="23505"))
    assert _is_current_uniqueness_violation(exc) is True


def test_classify_sqlite_unique_violation_as_current_uniqueness():
    from app.cognitive.services.version_manager import _is_current_uniqueness_violation

    exc = _build_persistence_error(_FakeDriverError(sqlite_errorname="SQLITE_CONSTRAINT_UNIQUE"))
    assert _is_current_uniqueness_violation(exc) is True


def test_classify_unrelated_sqlstate_returns_false():
    from app.cognitive.services.version_manager import _is_current_uniqueness_violation

    exc = _build_persistence_error(_FakeDriverError(sqlstate="23502"))  # not_null
    assert _is_current_uniqueness_violation(exc) is False


def test_classify_orig_none_returns_false():
    from app.cognitive.services.version_manager import _is_current_uniqueness_violation

    exc = _build_persistence_error(None)
    assert _is_current_uniqueness_violation(exc) is False


# --- Autoridade final do banco (pré-checagem contornada — TOCTOU simulado) ---


def test_database_level_fallback_fires_when_precheck_is_bypassed(
    objects, version_manager, cognitive_session, monkeypatch
):
    """Simula uma corrida real (TOCTOU): a pré-checagem
    (`get_current_by_clid`) não encontra conflito (mockada para
    retornar `None`), mas o `UPDATE` real ainda colide com o índice
    único parcial — a tradução via `_is_current_uniqueness_violation`
    no `except` de `revise()` é quem efetivamente rejeita."""
    a = objects.add(CognitiveObject())
    cognitive_session.commit()
    a.revision_status = RevisionStatus.CURRENT
    cognitive_session.commit()

    b, _, _ = version_manager.derive(a, operation_type="summarize")
    cognitive_session.commit()

    # força a pré-checagem a "não ver" o conflito real (simula TOCTOU)
    monkeypatch.setattr(objects, "get_current_by_clid", lambda clid: None)

    with pytest.raises(RevisionCurrentUniquenessViolationError) as exc_info:
        version_manager.revise(b, operation_type="malicious via toctou")
    assert exc_info.value.code == "PIA-8012"
    cognitive_session.rollback()


def test_unrelated_persistence_error_during_current_update_is_not_reclassified(
    objects, version_manager, cognitive_session, monkeypatch
):
    """Um `PersistenceError` não relacionado a unicidade, ocorrendo no
    mesmo `update()` que seta `target.revision_status = CURRENT`,
    continua propagando sem reinterpretação — mesmo princípio de
    E3.2.1 (não classificar por eliminação). Identifica a chamada
    certa por critério semântico (`entity.revision_status ==
    CURRENT`), não por contagem — `inherit()` também chama `update()`
    internamente para propagar CLID, então a posição numérica da
    chamada não é estável."""
    from app.cognitive.models.enums import RevisionStatus as _RS
    from app.repositories.base_repository import BaseRepository
    from app.repositories.exceptions import PersistenceError

    a = objects.add(CognitiveObject())
    cognitive_session.commit()

    fake_cause = Exception()
    fake_cause.orig = _FakeDriverError(sqlstate="23502")  # not_null, não unicidade

    original_update = BaseRepository.update

    def _raise_when_setting_current(self, entity):
        if getattr(entity, "revision_status", None) == _RS.CURRENT:
            raise PersistenceError("falha simulada não relacionada") from fake_cause
        return original_update(self, entity)

    monkeypatch.setattr(BaseRepository, "update", _raise_when_setting_current)

    with pytest.raises(PersistenceError) as exc_info:
        version_manager.revise(a, operation_type="revise")
    assert not isinstance(exc_info.value, RevisionCurrentUniquenessViolationError)
