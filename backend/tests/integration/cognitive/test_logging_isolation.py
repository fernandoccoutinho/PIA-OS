"""
LOG1/LOG2 (E3.6.1d) — regressão do vazamento de estado global de
logging causado por execução de Alembic dentro do processo do pytest.

Estes testes não asseveram nada sobre o domínio cognitivo. Eles
asseveram o invariante de harness:

    MIGRATION TEST MAY MUTATE DATABASE STATE
    MIGRATION TEST MUST NOT LEAK PROCESS-GLOBAL LOGGING STATE

Ambos exercitam caminhos reais de migração — os mesmos usados pelos
testes de guarda — e não substituem o Alembic por mock. Cada um
verifica primeiro que o vazamento *de fato acontece* dentro do trecho
protegido (senão a asserção de restauração seria vacuamente verdadeira,
o erro que E3.6.1b/E3.6.1c corrigiram nos testes de ancestralidade) e
só então que o estado voltou ao original.
"""

import logging

import pytest
import sqlalchemy as sa

from app.cognitive.models.cognitive_object import CognitiveObject
from app.cognitive.models.enums import ProvenanceActorType, ProvenanceSourceType
from app.cognitive.repositories.object_repository import ObjectRepository
from app.cognitive.repositories.provenance_repository import ProvenanceRepository
from app.cognitive.services.provenance_manager import ProvenanceManager
from app.database import migrations
from app.database.health import check_database_health
from app.repositories.unit_of_work import UnitOfWork
from tests.helpers.logging_state import LoggerState, preserved_logging_state

#: Logger real da aplicação, escolhido por ser exatamente um dos que os
#: testes E1/E2 quebrados observavam (`tests/unit/database/test_engine_listeners.py`).
_REFERENCE_LOGGER = "app.database.engine"

_PRE_PROVENANCE_REVISION = "f11551e97026"


def _database_available() -> bool:
    return check_database_health().available


pytestmark = pytest.mark.skipif(
    not _database_available(),
    reason="PostgreSQL real indisponível — LOG1/LOG2 exercitam migrações reais.",
)


def _assert_state_equal(observed: LoggerState, expected: LoggerState, what: str) -> None:
    assert observed.disabled == expected.disabled, f"{what}: disabled não restaurado"
    assert observed.level == expected.level, f"{what}: level não restaurado"
    assert observed.propagate == expected.propagate, f"{what}: propagate não restaurado"
    # Identidade e ordem, não equivalência aproximada.
    assert [id(h) for h in observed.handlers] == [
        id(h) for h in expected.handlers
    ], f"{what}: handlers não restaurados por identidade/ordem"


def test_log1_alembic_run_does_not_leak_logging_state():
    """LOG1 — um `upgrade` real executado in-process desliga os loggers
    da aplicação enquanto roda (comportamento do `fileConfig` do
    Alembic), e o mecanismo de isolamento devolve `disabled`, `level`,
    `propagate` e os handlers originais ao sair."""
    reference = logging.getLogger(_REFERENCE_LOGGER)
    root = logging.getLogger()

    before_reference = LoggerState.of(reference)
    before_root = LoggerState.of(root)
    assert before_reference.disabled is False, "pré-condição: logger de referência ativo"

    with preserved_logging_state():
        migrations.upgrade("head")
        # Não-vacuidade: sem isto, a asserção de restauração passaria
        # mesmo que o vazamento tivesse deixado de existir por acidente.
        assert reference.disabled is True, (
            "o vazamento não ocorreu — LOG1 perderia o poder de detecção; "
            "reveja o diagnóstico antes de confiar neste teste"
        )
        # `fileConfig` **substitui** os handlers do root (inclusive os do
        # próprio pytest) pelo console handler do `alembic.ini`; não os
        # acrescenta. É essa troca que este teste precisa observar.
        assert [id(h) for h in root.handlers] != [
            id(h) for h in before_root.handlers
        ], "o Alembic não reconfigurou o root — o caminho de migração pode não ter rodado"

    _assert_state_equal(LoggerState.of(reference), before_reference, _REFERENCE_LOGGER)
    _assert_state_equal(LoggerState.of(root), before_root, "root")


def test_log2_logging_state_is_restored_when_downgrade_is_blocked():
    """LOG2 — a restauração acontece no `finally`, inclusive quando a
    migração-guarda levanta `PROVENANCE_DOWNGRADE_SEMANTICALLY_BLOCKED`.
    A exceção semântica continua propagando, não é mascarada."""
    migrations.upgrade("head")

    with UnitOfWork() as uow:
        obj = ObjectRepository(uow.session).add(CognitiveObject())
        uow.commit()
        obj_id = obj.id

    with UnitOfWork() as uow:
        ProvenanceManager(ProvenanceRepository(uow.session)).record(
            coid=obj_id,
            source_type=ProvenanceSourceType.AGENT,
            actor_type=ProvenanceActorType.AGENT,
            trace_id="log2-trace",
        )
        uow.commit()

    reference = logging.getLogger(_REFERENCE_LOGGER)
    root = logging.getLogger()
    before_reference = LoggerState.of(reference)
    before_root = LoggerState.of(root)

    try:
        with preserved_logging_state():
            with pytest.raises(Exception) as exc_info:
                migrations.downgrade(_PRE_PROVENANCE_REVISION)
            assert "PROVENANCE_DOWNGRADE_SEMANTICALLY_BLOCKED" in str(exc_info.value)
            assert (
                reference.disabled is True
            ), "pré-condição: o caminho bloqueado passou pelo fileConfig"

        _assert_state_equal(LoggerState.of(reference), before_reference, _REFERENCE_LOGGER)
        _assert_state_equal(LoggerState.of(root), before_root, "root")
        assert migrations.current_revision() == migrations.head_revision()
    finally:
        # Mesmo padrão de limpeza de PD2: a fixture de Provenance criada
        # aqui não pode sobrar, senão a guarda passa a bloquear
        # legitimamente os testes de tabela vazia (PD1/PD5).
        with UnitOfWork() as uow:
            objs = ObjectRepository(uow.session)
            uow.session.execute(
                sa.text("DELETE FROM provenance_records WHERE coid = :c"), {"c": str(obj_id)}
            )
            leftover = objs.get_by_id(obj_id, include_deleted=True)
            if leftover is not None:
                objs.delete(leftover)
            uow.commit()
