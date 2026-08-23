"""
Provas PostgreSQL do núcleo da E7.3 — gate no banco, FK diferida e ciclo
de vida da delegação.

```text
APP_TYPED_BOUNDARY != DATABASE_INTEGRITY
TERMINAL -> ANY_OTHER_STATE = FORBIDDEN
```

Tudo aqui é por **SQL bruto**, deliberadamente. O value object e o DTO
recusam antes; o que este arquivo mede é o que sobra quando ninguém passa
por eles.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import DatabaseError, IntegrityError

from app.database.engine import engine
from app.database.health import check_database_health

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not check_database_health().available,
        reason="PostgreSQL real indisponível — funções, triggers e FK diferida são a prova.",
    ),
]

_HASH = "a" * 64
_OUTRO_HASH = "b" * 64

_APPEND_ONLY = (
    "audit_opinions",
    "execution_observations",
    "orchestration_control_events",
    "handoff_results",
    "handoff_attributions",
    "seal_receipts",
)


def _limpar() -> None:
    with engine.begin() as conexao:
        for tabela in (*_APPEND_ONLY, "service_delegations"):
            conexao.execute(sa.text(f"ALTER TABLE {tabela} DISABLE TRIGGER USER"))
            conexao.execute(sa.text(f"DELETE FROM {tabela}"))
            conexao.execute(sa.text(f"ALTER TABLE {tabela} ENABLE TRIGGER USER"))
        for tabela in ("handoff_attempts", "schedule_steps", "schedules", "command_receipts"):
            conexao.execute(sa.text(f"DELETE FROM {tabela}"))


@pytest.fixture(autouse=True)
def _base_limpa():
    _limpar()
    yield
    _limpar()


_INSERT_SCHEDULE = (
    "INSERT INTO schedules (id, title, state, execution_mode, control_principal_ref) "
    "VALUES (:i, 't', 'active', 'manual_handoff', 'p')"
)
_INSERT_STEP = (
    "INSERT INTO schedule_steps (id, schedule_id, position, role, instruction_ref, "
    "context_refs, expected_output_contract, constraints, state) "
    "VALUES (:i, :s, :n, 'r', 'i://1', '[]'::jsonb, 'c', CAST(:c AS jsonb), 'pending')"
)
_INSERT_ATTEMPT = (
    "INSERT INTO handoff_attempts (id, schedule_id, step_id, attempt_number, "
    "envelope_version, content_sha256, state) "
    "VALUES (:i, :s, :p, :n, '1', :h, 'open')"
)
_INSERT_DELEGATION = (
    "INSERT INTO service_delegations (id, schedule_id, step_id, content_sha256, scope, "
    "granted_by_principal_ref, valid_until, state) "
    "VALUES (:i, :s, :p, :h, 'dispatch', 'p', :v, 'active')"
)


def _cenario(constraints: str = "{}") -> tuple[uuid.UUID, uuid.UUID]:
    schedule_id, step_id = uuid.uuid4(), uuid.uuid4()
    with engine.begin() as conexao:
        conexao.execute(sa.text(_INSERT_SCHEDULE), {"i": schedule_id})
        conexao.execute(
            sa.text(_INSERT_STEP), {"i": step_id, "s": schedule_id, "n": 1, "c": constraints}
        )
    return schedule_id, step_id


# --- 1. gate na camada do banco ---------------------------------------------


@pytest.mark.parametrize(
    ("nome", "constraints"),
    [
        (
            "valor human, reprovado no R1",
            '{"pia.gate.required":"human","pia.gate.scope":"dispatch"}',
        ),
        ("valor none", '{"pia.gate.required":"none","pia.gate.scope":"dispatch"}'),
        ("chave reservada desconhecida", '{"pia.gate.mode":"x"}'),
        (
            "chave desconhecida junto das válidas",
            '{"pia.gate.required":"service_delegation","pia.gate.scope":"dispatch",'
            '"pia.gate.extra":"y"}',
        ),
        ("declaração incompleta: só required", '{"pia.gate.required":"service_delegation"}'),
        ("declaração incompleta: só scope", '{"pia.gate.scope":"dispatch"}'),
        (
            "scope diferente de dispatch",
            '{"pia.gate.required":"service_delegation","pia.gate.scope":"review"}',
        ),
        (
            "valor vazio",
            '{"pia.gate.required":"","pia.gate.scope":"dispatch"}',
        ),
    ],
)
def test_e73p01_o_banco_recusa_marcador_de_gate_invalido(nome: str, constraints: str) -> None:
    """SQL bruto não passa pelo value object nem pelo DTO."""
    schedule_id = uuid.uuid4()
    with engine.begin() as conexao:
        conexao.execute(sa.text(_INSERT_SCHEDULE), {"i": schedule_id})
    with pytest.raises(IntegrityError, match="gate_marker"), engine.begin() as conexao:
        conexao.execute(
            sa.text(_INSERT_STEP),
            {"i": uuid.uuid4(), "s": schedule_id, "n": 1, "c": constraints},
        )


@pytest.mark.parametrize(
    ("nome", "constraints"),
    [
        ("ausência = sem gate, retrocompatível", "{}"),
        ("outras restrições sem gate", '{"idioma":"pt-BR"}'),
        (
            "gate técnico",
            '{"pia.gate.required":"service_delegation","pia.gate.scope":"dispatch"}',
        ),
        (
            "gate técnico + humano",
            '{"pia.gate.required":"service_delegation_and_human",' '"pia.gate.scope":"dispatch"}',
        ),
        (
            "gate técnico junto de outra restrição",
            '{"idioma":"pt-BR","pia.gate.required":"service_delegation",'
            '"pia.gate.scope":"dispatch"}',
        ),
    ],
)
def test_e73p02_o_banco_aceita_ausencia_e_as_duas_formas_validas(
    nome: str, constraints: str
) -> None:
    """Não-vacuidade: a função recusa o inválido, não tudo."""
    schedule_id = uuid.uuid4()
    with engine.begin() as conexao:
        conexao.execute(sa.text(_INSERT_SCHEDULE), {"i": schedule_id})
        conexao.execute(
            sa.text(_INSERT_STEP),
            {"i": uuid.uuid4(), "s": schedule_id, "n": 1, "c": constraints},
        )
    with engine.connect() as conexao:
        assert conexao.execute(sa.text("SELECT count(*) FROM schedule_steps")).scalar_one() == 1


# --- 2. FK composta realmente diferida --------------------------------------


def test_e73p03_consumo_antes_da_attempt_passa_no_commit() -> None:
    """A ordem real do despacho: consumir e só então criar a Attempt.

    ```text
    DEFERRABLE INITIALLY DEFERRED
    ```

    Uma FK imediata falharia no `UPDATE`. Diferida, a coerência é exigida
    **no commit** — que é exatamente onde a transação já terá criado a
    Attempt correspondente.
    """
    schedule_id, step_id = _cenario()
    delegation_id, attempt_id = uuid.uuid4(), uuid.uuid4()
    validade = datetime.now(UTC) + timedelta(hours=1)
    with engine.begin() as conexao:
        conexao.execute(
            sa.text(_INSERT_DELEGATION),
            {"i": delegation_id, "s": schedule_id, "p": step_id, "h": _HASH, "v": validade},
        )
    with engine.begin() as conexao:
        conexao.execute(
            sa.text(
                "UPDATE service_delegations SET state = 'consumed', consumed_at = now(), "
                "consumed_by_attempt_id = :a WHERE id = :d AND state = 'active'"
            ),
            {"a": attempt_id, "d": delegation_id},
        )
        # A Attempt ainda NÃO existe neste ponto — e a transação continua.
        conexao.execute(
            sa.text(_INSERT_ATTEMPT),
            {"i": attempt_id, "s": schedule_id, "p": step_id, "n": 1, "h": _HASH},
        )
    with engine.connect() as conexao:
        estado = conexao.execute(
            sa.text("SELECT state, consumed_by_attempt_id FROM service_delegations WHERE id = :d"),
            {"d": delegation_id},
        ).one()
    assert estado.state == "consumed"
    assert estado.consumed_by_attempt_id == attempt_id


def test_e73p04_consumo_sem_attempt_alguma_falha_no_commit() -> None:
    """Diferida não é ausente: o commit cobra a coerência."""
    schedule_id, step_id = _cenario()
    delegation_id = uuid.uuid4()
    validade = datetime.now(UTC) + timedelta(hours=1)
    with engine.begin() as conexao:
        conexao.execute(
            sa.text(_INSERT_DELEGATION),
            {"i": delegation_id, "s": schedule_id, "p": step_id, "h": _HASH, "v": validade},
        )
    with pytest.raises(IntegrityError, match="consumed_attempt"), engine.begin() as conexao:
        conexao.execute(
            sa.text(
                "UPDATE service_delegations SET state = 'consumed', consumed_at = now(), "
                "consumed_by_attempt_id = :a WHERE id = :d AND state = 'active'"
            ),
            {"a": uuid.uuid4(), "d": delegation_id},
        )
    with engine.connect() as conexao:
        assert (
            conexao.execute(
                sa.text("SELECT state FROM service_delegations WHERE id = :d"), {"d": delegation_id}
            ).scalar_one()
            == "active"
        ), "a transação inteira reverteu"


def test_e73p05_consumo_com_attempt_de_outra_step_falha_no_commit() -> None:
    """`TWO_VALID_REFERENCES != ONE_COHERENT_REFERENCE`.

    A Attempt existe e a delegação existe; o que não existe é o vínculo
    entre as duas na mesma etapa. Só a FK **composta** enxerga isso.
    """
    schedule_id, step_id = _cenario()
    outro_step = uuid.uuid4()
    attempt_alheia = uuid.uuid4()
    delegation_id = uuid.uuid4()
    validade = datetime.now(UTC) + timedelta(hours=1)
    with engine.begin() as conexao:
        conexao.execute(
            sa.text(_INSERT_STEP), {"i": outro_step, "s": schedule_id, "n": 2, "c": "{}"}
        )
        conexao.execute(
            sa.text(_INSERT_ATTEMPT),
            {"i": attempt_alheia, "s": schedule_id, "p": outro_step, "n": 1, "h": _HASH},
        )
        conexao.execute(
            sa.text(_INSERT_DELEGATION),
            {"i": delegation_id, "s": schedule_id, "p": step_id, "h": _HASH, "v": validade},
        )
    with pytest.raises(IntegrityError, match="consumed_attempt"), engine.begin() as conexao:
        conexao.execute(
            sa.text(
                "UPDATE service_delegations SET state = 'consumed', consumed_at = now(), "
                "consumed_by_attempt_id = :a WHERE id = :d AND state = 'active'"
            ),
            {"a": attempt_alheia, "d": delegation_id},
        )


# --- 3. os três caminhos positivos do ciclo de vida -------------------------


def _delegacao(schedule_id: uuid.UUID, step_id: uuid.UUID, *, validade: datetime) -> uuid.UUID:
    delegation_id = uuid.uuid4()
    with engine.begin() as conexao:
        conexao.execute(
            sa.text(_INSERT_DELEGATION),
            {"i": delegation_id, "s": schedule_id, "p": step_id, "h": _HASH, "v": validade},
        )
    return delegation_id


def test_e73p06_active_para_consumed() -> None:
    schedule_id, step_id = _cenario()
    delegation_id = _delegacao(
        schedule_id, step_id, validade=datetime.now(UTC) + timedelta(hours=1)
    )
    attempt_id = uuid.uuid4()
    with engine.begin() as conexao:
        conexao.execute(
            sa.text(
                "UPDATE service_delegations SET state='consumed', consumed_at=now(), "
                "consumed_by_attempt_id=:a WHERE id=:d AND state='active'"
            ),
            {"a": attempt_id, "d": delegation_id},
        )
        conexao.execute(
            sa.text(_INSERT_ATTEMPT),
            {"i": attempt_id, "s": schedule_id, "p": step_id, "n": 1, "h": _HASH},
        )
    with engine.connect() as conexao:
        assert (
            conexao.execute(
                sa.text("SELECT state FROM service_delegations WHERE id=:d"), {"d": delegation_id}
            ).scalar_one()
            == "consumed"
        )


def test_e73p07_active_para_revoked() -> None:
    """Revogação: substituição de binding, sem Attempt envolvida."""
    schedule_id, step_id = _cenario()
    delegation_id = _delegacao(
        schedule_id, step_id, validade=datetime.now(UTC) + timedelta(hours=1)
    )
    with engine.begin() as conexao:
        conexao.execute(
            sa.text(
                "UPDATE service_delegations SET state='revoked' WHERE id=:d AND state='active'"
            ),
            {"d": delegation_id},
        )
    with engine.connect() as conexao:
        linha = conexao.execute(
            sa.text(
                "SELECT state, consumed_at, consumed_by_attempt_id "
                "FROM service_delegations WHERE id=:d"
            ),
            {"d": delegation_id},
        ).one()
    assert linha.state == "revoked"
    assert linha.consumed_at is None and linha.consumed_by_attempt_id is None


def test_e73p08_active_para_expired() -> None:
    """Expiração é materializada **sincronicamente**, não por sweeper.

    ```text
    EXPIRED = DERIVED_AT_EVALUATION_TIME, WRITTEN_UNDER_LOCK
    EXPIRY_SWEEPER = NOT_IMPLEMENTED
    ```
    """
    schedule_id, step_id = _cenario()
    delegation_id = _delegacao(
        schedule_id, step_id, validade=datetime.now(UTC) - timedelta(seconds=1)
    )
    with engine.begin() as conexao:
        atualizadas = conexao.execute(
            sa.text(
                "UPDATE service_delegations SET state='expired' "
                "WHERE id=:d AND state='active' AND valid_until <= now()"
            ),
            {"d": delegation_id},
        ).rowcount
    assert atualizadas == 1
    with engine.connect() as conexao:
        assert (
            conexao.execute(
                sa.text("SELECT state FROM service_delegations WHERE id=:d"), {"d": delegation_id}
            ).scalar_one()
            == "expired"
        )


@pytest.mark.parametrize("terminal", ["consumed", "revoked", "expired"])
def test_e73p09_nenhum_estado_terminal_retorna(terminal: str) -> None:
    """Os três terminais são terminais — não só o primeiro."""
    schedule_id, step_id = _cenario()
    delegation_id = _delegacao(
        schedule_id, step_id, validade=datetime.now(UTC) + timedelta(hours=1)
    )
    attempt_id = uuid.uuid4()
    with engine.begin() as conexao:
        if terminal == "consumed":
            conexao.execute(
                sa.text(
                    "UPDATE service_delegations SET state='consumed', consumed_at=now(), "
                    "consumed_by_attempt_id=:a WHERE id=:d"
                ),
                {"a": attempt_id, "d": delegation_id},
            )
            conexao.execute(
                sa.text(_INSERT_ATTEMPT),
                {"i": attempt_id, "s": schedule_id, "p": step_id, "n": 1, "h": _HASH},
            )
        else:
            conexao.execute(
                sa.text("UPDATE service_delegations SET state=:t WHERE id=:d"),
                {"t": terminal, "d": delegation_id},
            )
    for destino in ("active", "consumed", "revoked", "expired"):
        if destino == terminal:
            continue
        with pytest.raises(DatabaseError, match="terminal"), engine.begin() as conexao:
            conexao.execute(
                sa.text("UPDATE service_delegations SET state=:t WHERE id=:d"),
                {"t": destino, "d": delegation_id},
            )


def test_e73p10_uma_ativa_por_trinca_mas_terminal_libera_a_proxima() -> None:
    """O índice parcial protege sem aprisionar a Step.

    Unicidade por `step_id` sozinha impediria substituir uma delegação
    vencida ou ligada a hash antigo. Por trinca, e só sobre `active`, o
    terminal abre espaço para a próxima.
    """
    schedule_id, step_id = _cenario()
    primeira = _delegacao(schedule_id, step_id, validade=datetime.now(UTC) + timedelta(hours=1))
    with pytest.raises(IntegrityError, match="single_active"), engine.begin() as conexao:
        conexao.execute(
            sa.text(_INSERT_DELEGATION),
            {
                "i": uuid.uuid4(),
                "s": schedule_id,
                "p": step_id,
                "h": _OUTRO_HASH,
                "v": datetime.now(UTC) + timedelta(hours=1),
            },
        )
    with engine.begin() as conexao:
        conexao.execute(
            sa.text("UPDATE service_delegations SET state='revoked' WHERE id=:d"), {"d": primeira}
        )
    segunda = _delegacao(schedule_id, step_id, validade=datetime.now(UTC) + timedelta(hours=1))
    with engine.connect() as conexao:
        ativas = conexao.execute(
            sa.text("SELECT count(*) FROM service_delegations WHERE state='active'")
        ).scalar_one()
    assert ativas == 1
    assert segunda != primeira
