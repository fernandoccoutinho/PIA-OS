"""
Captura e restauração do estado global de logging (E3.6.1d).

Motivo — `alembic/env.py` chama `logging.config.fileConfig(...)`, e o
comportamento padrão de `fileConfig` é `disable_existing_loggers=True`.
Qualquer teste que execute Alembic *dentro do processo do pytest*
(os testes de guarda de downgrade de `Relationship` e `Provenance`)
portanto desliga todos os loggers da aplicação já instanciados, e os
testes E1/E2 que asseveram emissão de log passam a falhar conforme a
ordem de coleta.

Invariante que este helper existe para sustentar:

    MIGRATION TEST MAY MUTATE DATABASE STATE
    MIGRATION TEST MUST NOT LEAK PROCESS-GLOBAL LOGGING STATE

Escopo deliberado: isto é infraestrutura **de teste**. Nada aqui altera
o logging de produção, `alembic.ini`, `alembic/env.py` ou o
comportamento real do Alembic — a chamada real a `fileConfig` continua
acontecendo exatamente como em produção; apenas o processo de teste
volta ao estado anterior depois.

Atributos restaurados (levantados empiricamente, não por suposição):
`level`, `disabled`, `propagate` e a lista `handlers` de cada logger
existente, mais o root logger. Loggers criados *durante* o trecho
protegido não são removidos do `Logger.manager` — objetos de
terceiros (SQLAlchemy, psycopg) guardam referência direta a eles, e
removê-los faria um `getLogger()` posterior devolver um objeto
diferente daquele em uso. Em vez disso, voltam ao estado pristino de
um logger recém-criado, que é o que um teste posterior observaria se
o trecho protegido nunca tivesse rodado.
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass

#: Estado de um logger recém-criado — o que `logging.getLogger(nome)`
#: devolveria se o nome nunca tivesse sido tocado.
_PRISTINE_LEVEL = logging.NOTSET
_PRISTINE_DISABLED = False
_PRISTINE_PROPAGATE = True


@dataclass(frozen=True)
class LoggerState:
    """Estado restaurável de um único logger.

    `handlers` guarda os **objetos originais**, não cópias: o objetivo é
    `restore state`, não `reconstruct approximately equivalent logging
    configuration`.
    """

    level: int
    disabled: bool
    propagate: bool
    handlers: tuple[logging.Handler, ...]

    @classmethod
    def of(cls, logger: logging.Logger) -> LoggerState:
        return cls(
            level=logger.level,
            disabled=logger.disabled,
            propagate=logger.propagate,
            handlers=tuple(logger.handlers),
        )

    def apply_to(self, logger: logging.Logger) -> None:
        logger.disabled = self.disabled
        logger.propagate = self.propagate
        # `handlers[:]` preserva a identidade da lista e dos handlers
        # originais; nenhum handler é fechado ou recriado.
        logger.handlers[:] = list(self.handlers)
        # `setLevel` por último: além de gravar o nível, ele limpa o
        # cache interno de `isEnabledFor` (`manager._clear_cache()`),
        # que de outro modo continuaria refletindo o estado anterior.
        logger.setLevel(self.level)


_PRISTINE_STATE = LoggerState(
    level=_PRISTINE_LEVEL,
    disabled=_PRISTINE_DISABLED,
    propagate=_PRISTINE_PROPAGATE,
    handlers=(),
)


@dataclass(frozen=True)
class LoggingSnapshot:
    """Fotografia do estado global de logging em um instante."""

    root: LoggerState
    loggers: dict[str, LoggerState]
    known_names: frozenset[str]


def capture_logging_state() -> LoggingSnapshot:
    """Fotografa o root logger e todos os loggers já existentes."""
    logger_dict = logging.Logger.manager.loggerDict
    return LoggingSnapshot(
        root=LoggerState.of(logging.getLogger()),
        loggers={
            name: LoggerState.of(obj)
            for name, obj in logger_dict.items()
            if isinstance(obj, logging.Logger)
        },
        known_names=frozenset(logger_dict),
    )


def restore_logging_state(snapshot: LoggingSnapshot) -> None:
    """Restaura fielmente o estado fotografado por `capture_logging_state`."""
    snapshot.root.apply_to(logging.getLogger())

    logger_dict = logging.Logger.manager.loggerDict
    for name, state in snapshot.loggers.items():
        obj = logger_dict.get(name)
        if isinstance(obj, logging.Logger):
            state.apply_to(obj)

    # Loggers que nasceram durante o trecho protegido (`alembic`,
    # `sqlalchemy.engine`, ...) voltam ao estado pristino — sem handlers
    # herdados da configuração do Alembic, sem nível imposto por ela.
    for name, obj in list(logger_dict.items()):
        if name in snapshot.known_names or not isinstance(obj, logging.Logger):
            continue
        _PRISTINE_STATE.apply_to(obj)


@contextmanager
def preserved_logging_state() -> Iterator[LoggingSnapshot]:
    """Executa o bloco e restaura o estado de logging em `finally`.

    O `finally` é o ponto central: os testes de guarda de downgrade
    provocam deliberadamente `DOWNGRADE_SEMANTICALLY_BLOCKED`, e a
    restauração precisa acontecer também nesse caminho — sem mascarar
    a exceção, que continua propagando.
    """
    snapshot = capture_logging_state()
    try:
        yield snapshot
    finally:
        restore_logging_state(snapshot)
