"""
Schema da proteção humana contra PostgreSQL real (`E7.4-1 B1a`).

Aqui ficam as provas que só o banco pode dar: os `CHECK` de linha derivados, as
três FKs compostas, a idempotência sob concorrência real de duas conexões, os
gatilhos append-only e a coerência pai/filha avaliada no `COMMIT`.

```text
FAKE_PROVES_SERVICE_LOGIC
DATABASE_PROVES_ATOMICITY_AND_IMMUTABILITY
MUTATED_FILE != MUTATED_SCHEMA
```

Cada prova exercita a propriedade pretendida e é escrita para falhar **pela
guarda certa**: um caso positivo cuja fixture esteja incompleta falha por
chave estrangeira e parece medir o invariante.

```text
REFUSAL_BY_THE_WRONG_GUARD = UNPROVEN_INVARIANT
FIXTURE_INCOMPLETA = PROVA_QUE_FALHA_PELO_MOTIVO_ERRADO
```
"""

import threading
import uuid
from datetime import UTC, datetime, timedelta

import psycopg
import pytest
import sqlalchemy as sa

from app.database import migrations
from app.database.engine import engine
from app.orchestration.errors.exceptions import HumanProtectionGateUnavailableError
from app.orchestration.models.human_protection_event import CHECKS_DO_EVENTO
from app.orchestration.ports.governance_vocabulary import (
    BoundaryCapability,
    BoundaryEngagement,
    BoundaryOperation,
)
from app.orchestration.protection.decision import (
    CAMPOS_IMUTAVEIS_DA_APLICACAO,
    HumanProtectionApplication,
)
from app.orchestration.protection.vocabulary import (
    BINDING_ALGO_VERSION,
    FINGERPRINT_ALGO_VERSION,
    PRODUCER_REF,
    GatePosition,
    ProtectionOutcome,
)
from app.orchestration.repositories.human_protection_repository import (
    HumanProtectionRepository,
)
from app.repositories.unit_of_work import UnitOfWork

pytestmark = pytest.mark.integration

_REVISION_CHAIN124 = "f4c8b0d51e73"
_REVISION_B1A = "d7a4c1e93b28"

_EVENTOS = "human_protection_events"
_CAPACIDADES = "human_protection_event_capabilities"

_PRINCIPAL = "principal-hp"
_SCHEDULE = uuid.UUID("11111111-1111-1111-1111-111111111111")
_STEP = uuid.UUID("22222222-2222-2222-2222-222222222222")
_ATTEMPT = uuid.UUID("44444444-4444-4444-4444-444444444444")
_OBJETIVO = "a" * 64

_COLUNAS = (
    "id",
    *CAMPOS_IMUTAVEIS_DA_APLICACAO,
)


def _dsn() -> str:
    """DSN psycopg puro, para as duas conexões da prova de concorrência."""
    return engine.url.render_as_string(hide_password=False).replace(
        "postgresql+psycopg://", "postgresql://"
    )


def _limpar() -> None:
    with engine.begin() as conexao:
        for tabela in (_CAPACIDADES, _EVENTOS):
            conexao.execute(sa.text(f"ALTER TABLE {tabela} DISABLE TRIGGER USER"))
            conexao.execute(sa.text(f"DELETE FROM {tabela}"))
            conexao.execute(sa.text(f"ALTER TABLE {tabela} ENABLE TRIGGER USER"))
        conexao.execute(sa.text("DELETE FROM handoff_attempts"))
        conexao.execute(sa.text("DELETE FROM schedule_steps"))
        conexao.execute(sa.text("DELETE FROM schedules"))


@pytest.fixture(autouse=True)
def _base_limpa():
    _limpar()
    _fixtures_de_escopo()
    yield
    _limpar()


def _fixtures_de_escopo() -> None:
    """Schedule, etapa e tentativa reais.

    A tentativa recebe **todas** as colunas obrigatórias. Foi exatamente a
    omissão de uma delas que, no delta R10.1, fez o caso positivo de G3 falhar
    por chave estrangeira em vez de pela propriedade medida.
    """
    with engine.begin() as conexao:
        conexao.execute(
            sa.text(
                "INSERT INTO schedules (id, control_principal_ref, title, execution_mode, "
                "state, created_at, updated_at) VALUES (:i, :p, 't', 'manual_handoff', "
                "'active', now(), now())"
            ),
            {"i": _SCHEDULE, "p": _PRINCIPAL},
        )
        conexao.execute(
            sa.text(
                "INSERT INTO schedule_steps (id, schedule_id, position, role, instruction_ref, "
                "expected_output_contract, context_refs, constraints, state, created_at, "
                "updated_at) VALUES (:i, :s, 1, 'r', 'ref', "
                "'pia://orchestration/output/non-empty-text/v1', '[]', '{}', 'pending', "
                "now(), now())"
            ),
            {"i": _STEP, "s": _SCHEDULE},
        )
        conexao.execute(
            sa.text(
                "INSERT INTO handoff_attempts (id, schedule_id, step_id, attempt_number, "
                "envelope_version, content_sha256, state, created_at, updated_at) "
                "VALUES (:i, :s, :e, 1, '1', :h, 'open', now(), now())"
            ),
            {"i": _ATTEMPT, "s": _SCHEDULE, "e": _STEP, "h": "a" * 64},
        )


# --- fábricas ---------------------------------------------------------------


def _aplicacao(**extra: object) -> HumanProtectionApplication:
    campos: dict[str, object] = {
        "control_principal_ref": _PRINCIPAL,
        "schedule_id": _SCHEDULE,
        "step_id": _STEP,
        "attempt_id": None,
        "binding_attempt_id": None,
        "objective_sha256": _OBJETIVO,
        "decision_fingerprint": "d" * 64,
        "fingerprint_algo_version": FINGERPRINT_ALGO_VERSION,
        "binding_sha256": "b" * 64,
        "binding_algo_version": BINDING_ALGO_VERSION,
        "outcome": ProtectionOutcome.ALLOWED,
        "capability_engagement": None,
        "boundary_version": 1,
        "classifier_version": "iab-1",
        "cognitive_operation": BoundaryOperation.EXPOSE,
        "gate_position": GatePosition.G2,
        "producer_ref": PRODUCER_REF,
        "pause_applied": False,
        "delegations_revoked": 0,
        "blocked_capabilities": (),
    }
    campos.update(extra)
    return HumanProtectionApplication(**campos)  # type: ignore[arg-type]


def _bloqueio(**extra: object) -> HumanProtectionApplication:
    campos: dict[str, object] = {
        "outcome": ProtectionOutcome.BLOCKED,
        "capability_engagement": BoundaryEngagement.OPERATIONAL_ENABLEMENT,
        "pause_applied": True,
        "blocked_capabilities": (BoundaryCapability.CHILD_SEXUAL_EXPLOITATION,),
    }
    campos.update(extra)
    return _aplicacao(**campos)


def _gravar(aplicacao: HumanProtectionApplication) -> uuid.UUID | None:
    with UnitOfWork() as uow:
        criado = HumanProtectionRepository(uow.session).inserir_se_ausente(aplicacao)
        uow.commit()
    return criado


def _bruto(**valores: object) -> None:
    """`INSERT` por SQL cru, para medir o SCHEMA e não o value object.

    Sem isto, cada `CHECK` seria testado através de um dataclass que já
    recusa antes — e a prova mediria a camada errada.

    ```text
    APPLICATION_CHECK != DATABASE_GUARANTEE
    ```
    """
    padrao: dict[str, object] = {
        "id": uuid.uuid4(),
        "control_principal_ref": _PRINCIPAL,
        "schedule_id": _SCHEDULE,
        "step_id": _STEP,
        "attempt_id": None,
        "binding_attempt_id": None,
        "objective_sha256": _OBJETIVO,
        "decision_fingerprint": "d" * 64,
        "fingerprint_algo_version": "1",
        "binding_sha256": uuid.uuid4().hex + uuid.uuid4().hex,
        "binding_algo_version": "1",
        "outcome": "allowed",
        "capability_engagement": None,
        "boundary_version": 1,
        "classifier_version": "iab-1",
        "cognitive_operation": "expose",
        "gate_position": "g2",
        "producer_ref": PRODUCER_REF,
        "pause_applied": False,
        "delegations_revoked": 0,
    }
    padrao.update(valores)
    colunas = ", ".join(padrao)
    marcas = ", ".join(f":{c}" for c in padrao)
    with engine.begin() as conexao:
        conexao.execute(sa.text(f"INSERT INTO {_EVENTOS} ({colunas}) VALUES ({marcas})"), padrao)


# --- migration e inventário -------------------------------------------------


def test_hp_i01_a_migration_e_folha_unica_filha_do_parent_autorizado() -> None:
    config = migrations.get_alembic_config()
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(config)
    assert list(script.get_heads()) == [_REVISION_CHAIN124]
    assert script.get_revision(_REVISION_CHAIN124).down_revision == _REVISION_B1A


def test_hp_i02_inventario_literal_dos_constraints() -> None:
    """Contado no catálogo do PostgreSQL, nunca numa lista escrita à mão."""
    with engine.connect() as conexao:

        def conta(sql: str, **p: object) -> int:
            return conexao.execute(sa.text(sql), p).scalar_one()

        assert conta(
            "SELECT count(*) FROM pg_constraint WHERE conrelid = CAST(:t AS regclass) "
            "AND contype = 'c'",
            t=_EVENTOS,
        ) == len(CHECKS_DO_EVENTO)
        assert (
            conta(
                "SELECT count(*) FROM pg_constraint WHERE conrelid = CAST(:t AS regclass) "
                "AND contype = 'c'",
                t=_CAPACIDADES,
            )
            == 2
        )
        assert (
            conta(
                "SELECT count(*) FROM pg_constraint WHERE conrelid = CAST(:t AS regclass) "
                "AND contype = 'f'",
                t=_EVENTOS,
            )
            == 3
        )
        assert (
            conta(
                "SELECT count(*) FROM pg_constraint WHERE conrelid = CAST(:t AS regclass) "
                "AND contype = 'f'",
                t=_CAPACIDADES,
            )
            == 1
        )
        assert (
            conta(
                "SELECT count(*) FROM pg_trigger WHERE tgconstraint <> 0 AND NOT tgisinternal "
                "AND tgrelid IN (CAST(:a AS regclass), CAST(:b AS regclass))",
                a=_EVENTOS,
                b=_CAPACIDADES,
            )
            == 2
        )
        assert (
            conta("SELECT count(*) FROM pg_constraint WHERE conname = 'uq_schedules_id_principal'")
            == 1
        )


def test_hp_i03_a_fk_da_tentativa_e_diferida() -> None:
    """G3 escreve evento e tentativa na mesma transação."""
    with engine.connect() as conexao:
        diferida = conexao.execute(
            sa.text(
                "SELECT condeferrable AND condeferred FROM pg_constraint "
                "WHERE conname = 'fk_hpe_attempt'"
            )
        ).scalar_one()
    assert diferida is True


# --- CHECK de linha ---------------------------------------------------------


def test_hp_i04_g3_sem_binding_attempt_falha() -> None:
    with pytest.raises(Exception, match="ck_hpe_g3_has_binding_attempt"):
        _bruto(
            gate_position="g3",
            outcome="blocked",
            capability_engagement="unspecified",
            pause_applied=True,
        )


def test_hp_i05_gate_nao_g3_com_binding_attempt_falha() -> None:
    with pytest.raises(Exception, match="ck_hpe_non_g3_no_binding_attempt"):
        _bruto(binding_attempt_id=_ATTEMPT)


def test_hp_i06_tentativa_divergente_do_binding_falha() -> None:
    """`G3_APPLICATION_WITHOUT_ATTEMPT_ID = STALE_ATTEMPT_PROOF`, no schema."""
    with pytest.raises(Exception, match="ck_hpe_attempt_matches_binding"):
        _bruto(
            gate_position="g3",
            attempt_id=_ATTEMPT,
            binding_attempt_id=uuid.uuid4(),
        )


def test_hp_i07_g3_permitido_com_tentativa_coerente_passa() -> None:
    """O caso POSITIVO, com fixture completa — commita de verdade."""
    _bruto(gate_position="g3", attempt_id=_ATTEMPT, binding_attempt_id=_ATTEMPT)
    with engine.connect() as conexao:
        assert (
            conexao.execute(
                sa.text(f"SELECT count(*) FROM {_EVENTOS} WHERE gate_position = 'g3'")
            ).scalar_one()
            == 1
        )


def test_hp_i08_g1_com_schedule_falha() -> None:
    with pytest.raises(Exception, match="ck_hpe_g1_schedule_null"):
        _bruto(gate_position="g1", step_id=None)


def test_hp_i09_g1_valido_commita_com_capacidade_ordinal_zero() -> None:
    aplicacao = _bloqueio(
        gate_position=GatePosition.G1, schedule_id=None, step_id=None, pause_applied=False
    )
    evento = _gravar(aplicacao)
    assert evento is not None
    with engine.connect() as conexao:
        assert (
            conexao.execute(
                sa.text(f"SELECT ordinal FROM {_CAPACIDADES} WHERE event_id = :i"),
                {"i": evento},
            ).scalar_one()
            == 0
        )


def test_hp_i10_bloqueio_com_engajamento_analitico_falha() -> None:
    """`ANALYSIS != OPERATIONAL_ENABLEMENT`, imposto pelo banco."""
    with pytest.raises(Exception, match="ck_hpe_blocked_engagement"):
        _bruto(outcome="blocked", capability_engagement="analytical", pause_applied=True)


def test_hp_i10b_bloqueio_com_engajamento_nulo_falha_pelo_check_correto() -> None:
    with pytest.raises(Exception, match="ck_hpe_blocked_engagement"):
        _bruto(outcome="blocked", capability_engagement=None, pause_applied=True)


def test_hp_i10c_permissao_com_engajamento_falha_pelo_check_correto() -> None:
    with pytest.raises(Exception, match="ck_hpe_allowed_no_engagement"):
        _bruto(outcome="allowed", capability_engagement="operational_enablement")


def test_hp_i11_bloqueio_fora_de_g1_sem_pausa_falha() -> None:
    with pytest.raises(Exception, match="ck_hpe_blocked_pauses"):
        _bruto(outcome="blocked", capability_engagement="unspecified", pause_applied=False)


def test_hp_i12_produtor_desconhecido_falha() -> None:
    with pytest.raises(Exception, match="ck_hpe_producer_ref"):
        _bruto(producer_ref="outro.produtor")


def test_hp_i13_fingerprint_maiusculo_falha() -> None:
    with pytest.raises(Exception, match="ck_hpe_fingerprint_hex"):
        _bruto(decision_fingerprint="D" * 64)


def test_hp_i14_operacao_fora_de_expose_falha() -> None:
    """`SC-HP-25 = CLOSED`: G1..G4 são `EXPOSE`."""
    with pytest.raises(Exception, match="ck_hpe_cognitive_op"):
        _bruto(cognitive_operation="derive")


# --- FKs compostas ----------------------------------------------------------


def test_hp_i15_schedule_de_outro_principal_e_recusado() -> None:
    """`COHERENT_OWNER`: a FK prova dono, não só existência."""
    with pytest.raises(Exception, match="fk_hpe_schedule"):
        _bruto(control_principal_ref="outro-principal")


def test_hp_i16_etapa_de_outro_schedule_e_recusada() -> None:
    outro = uuid.uuid4()
    with engine.begin() as conexao:
        conexao.execute(
            sa.text(
                "INSERT INTO schedules (id, control_principal_ref, title, execution_mode, "
                "state, created_at, updated_at) VALUES (:i, :p, 't2', 'manual_handoff', "
                "'active', now(), now())"
            ),
            {"i": outro, "p": _PRINCIPAL},
        )
    with pytest.raises(Exception, match="fk_hpe_step"):
        _bruto(schedule_id=outro)


# --- coerência pai/filha no COMMIT ------------------------------------------


def test_hp_i17_bloqueio_sem_capacidade_falha_no_commit() -> None:
    """Constraint trigger DIFERIDO: a recusa vem no `COMMIT`, não no `INSERT`."""
    with pytest.raises(Exception, match="at least one capability"), engine.begin() as conexao:
        conexao.execute(
            sa.text(
                f"INSERT INTO {_EVENTOS} (id, control_principal_ref, schedule_id, step_id, "
                "objective_sha256, decision_fingerprint, fingerprint_algo_version, "
                "binding_sha256, binding_algo_version, outcome, capability_engagement, "
                "boundary_version, classifier_version, cognitive_operation, gate_position, "
                "producer_ref, pause_applied, delegations_revoked) VALUES "
                "(:i, :p, :s, :e, :o, :f, '1', :b, '1', 'blocked', 'unspecified', 1, 'iab-1', "
                "'expose', 'g2', :r, true, 0)"
            ),
            {
                "i": uuid.uuid4(),
                "p": _PRINCIPAL,
                "s": _SCHEDULE,
                "e": _STEP,
                "o": _OBJETIVO,
                "f": "d" * 64,
                "b": "e" * 64,
                "r": PRODUCER_REF,
            },
        )


def test_hp_i18_permitido_com_capacidade_falha_no_commit() -> None:
    evento = _gravar(_aplicacao())
    with pytest.raises(Exception, match="only blocked carries"), engine.begin() as conexao:
        conexao.execute(
            sa.text(f"INSERT INTO {_CAPACIDADES} VALUES (:i, 0, 'child_sexual_exploitation')"),
            {"i": evento},
        )


def test_hp_i19_buraco_no_ordinal_falha_no_commit() -> None:
    evento = _gravar(
        _bloqueio(
            blocked_capabilities=(
                BoundaryCapability.CHILD_SEXUAL_EXPLOITATION,
                BoundaryCapability.CATASTROPHIC_HARM_ENABLEMENT,
            )
        )
    )
    with engine.begin() as conexao:
        conexao.execute(sa.text(f"ALTER TABLE {_CAPACIDADES} DISABLE TRIGGER USER"))
        conexao.execute(
            sa.text(f"DELETE FROM {_CAPACIDADES} WHERE event_id = :i AND ordinal = 1"),
            {"i": evento},
        )
        conexao.execute(sa.text(f"ALTER TABLE {_CAPACIDADES} ENABLE TRIGGER USER"))
    with pytest.raises(Exception, match="ordinals must be"), engine.begin() as conexao:
        conexao.execute(
            sa.text(
                f"INSERT INTO {_CAPACIDADES} VALUES "
                "(:i, 2, 'weapon_of_mass_destruction_enablement')"
            ),
            {"i": evento},
        )


def test_hp_i20_duas_capacidades_persistem_com_ordinais_contiguos() -> None:
    evento = _gravar(
        _bloqueio(
            blocked_capabilities=(
                BoundaryCapability.MINOR_TARGETING_FOR_EXPLOITATION,
                BoundaryCapability.CHILD_SEXUAL_EXPLOITATION,
            )
        )
    )
    with engine.connect() as conexao:
        linhas = conexao.execute(
            sa.text(
                f"SELECT ordinal, critical_capability FROM {_CAPACIDADES} "
                "WHERE event_id = :i ORDER BY ordinal"
            ),
            {"i": evento},
        ).all()
    assert [linha[0] for linha in linhas] == [0, 1]
    assert linhas[0][1] == "minor_targeting_for_exploitation"


def test_hp_i21_a_mesma_capacidade_duas_vezes_e_recusada() -> None:
    evento = _gravar(_bloqueio())
    with pytest.raises(Exception, match="uq_hpec_event_capability"), engine.begin() as conexao:
        conexao.execute(
            sa.text(f"INSERT INTO {_CAPACIDADES} VALUES (:i, 1, 'child_sexual_exploitation')"),
            {"i": evento},
        )


# --- append-only: seis casos, e a distinção FK vs gatilho -------------------


def test_hp_i22_update_no_evento_e_recusado() -> None:
    evento = _gravar(_aplicacao())
    with pytest.raises(Exception, match="append-only"), engine.begin() as conexao:
        conexao.execute(
            sa.text(f"UPDATE {_EVENTOS} SET pause_applied = true WHERE id = :i"), {"i": evento}
        )


def test_hp_i23_delete_no_evento_e_recusado() -> None:
    evento = _gravar(_aplicacao())
    with pytest.raises(Exception, match="append-only"), engine.begin() as conexao:
        conexao.execute(sa.text(f"DELETE FROM {_EVENTOS} WHERE id = :i"), {"i": evento})


def test_hp_i24_truncate_do_evento_e_recusado_pela_fk_antes_do_gatilho() -> None:
    """`FK_REFUSAL != TRIGGER_REFUSAL` — a distinção que o R10 apagava."""
    _gravar(_aplicacao())
    with pytest.raises(Exception, match="foreign key|chave estrangeira"), engine.begin() as c:
        c.execute(sa.text(f"TRUNCATE {_EVENTOS}"))


def test_hp_i25_truncate_cascade_alcanca_o_gatilho_do_evento() -> None:
    _gravar(_aplicacao())
    with pytest.raises(Exception, match="append-only"), engine.begin() as conexao:
        conexao.execute(sa.text(f"TRUNCATE {_EVENTOS} CASCADE"))


def test_hp_i26_update_na_associacao_e_recusado() -> None:
    evento = _gravar(_bloqueio())
    with pytest.raises(Exception, match="append-only"), engine.begin() as conexao:
        conexao.execute(
            sa.text(f"UPDATE {_CAPACIDADES} SET ordinal = 9 WHERE event_id = :i"), {"i": evento}
        )


def test_hp_i27_delete_na_associacao_e_recusado() -> None:
    evento = _gravar(_bloqueio())
    with pytest.raises(Exception, match="append-only"), engine.begin() as conexao:
        conexao.execute(sa.text(f"DELETE FROM {_CAPACIDADES} WHERE event_id = :i"), {"i": evento})


def test_hp_i28_truncate_na_associacao_e_recusado() -> None:
    _gravar(_bloqueio())
    with pytest.raises(Exception, match="append-only"), engine.begin() as conexao:
        conexao.execute(sa.text(f"TRUNCATE {_CAPACIDADES}"))


# --- idempotência e vencedor ------------------------------------------------


def test_hp_i29_a_mesma_decisao_em_gates_distintos_gera_duas_linhas() -> None:
    """`2 linhas · 1 fingerprint · 2 bindings`."""
    _gravar(_aplicacao(binding_sha256="b" * 64))
    _gravar(_aplicacao(gate_position=GatePosition.G4, binding_sha256="c" * 64))
    with engine.connect() as conexao:
        linhas, fingerprints, bindings = conexao.execute(
            sa.text(
                f"SELECT count(*), count(DISTINCT decision_fingerprint), "
                f"count(DISTINCT binding_sha256) FROM {_EVENTOS}"
            )
        ).one()
    assert (linhas, fingerprints, bindings) == (2, 1, 2)


def test_hp_i30_retry_da_mesma_aplicacao_nao_duplica() -> None:
    aplicacao = _bloqueio()
    assert _gravar(aplicacao) is not None
    assert _gravar(aplicacao) is None
    with engine.connect() as conexao:
        assert conexao.execute(sa.text(f"SELECT count(*) FROM {_EVENTOS}")).scalar_one() == 1


def test_hp_i31_o_savepoint_do_perdedor_nao_desfaz_a_transacao_externa() -> None:
    """`SAVEPOINT_SCOPE != TRANSACTION_SCOPE`.

    Uma escrita anterior e não relacionada sobrevive ao `INSERT` perdedor.
    """
    aplicacao = _bloqueio()
    _gravar(aplicacao)
    outro = uuid.uuid4()
    with UnitOfWork() as uow:
        uow.session.execute(
            sa.text(
                "INSERT INTO schedules (id, control_principal_ref, title, execution_mode, "
                "state, created_at, updated_at) VALUES (:i, :p, 'sobrevive', "
                "'manual_handoff', 'active', now(), now())"
            ),
            {"i": outro, "p": _PRINCIPAL},
        )
        assert HumanProtectionRepository(uow.session).inserir_se_ausente(aplicacao) is None
        uow.commit()
    with engine.connect() as conexao:
        assert (
            conexao.execute(
                sa.text("SELECT count(*) FROM schedules WHERE id = :i"), {"i": outro}
            ).scalar_one()
            == 1
        )


def test_hp_i32_o_vencedor_e_comparado_em_dezenove_campos() -> None:
    """`WINNER_VERIFIED_BY_CAPABILITIES_ONLY = UNVERIFIED_APPLICATION`."""
    assert len(CAMPOS_IMUTAVEIS_DA_APLICACAO) == 19
    _gravar(_bloqueio())
    divergente = _bloqueio(delegations_revoked=3)
    with (
        UnitOfWork() as uow,
        pytest.raises(HumanProtectionGateUnavailableError, match="delegations_revoked"),
    ):
        HumanProtectionRepository(uow.session).confirmar_vencedor(divergente)


def test_hp_i33_capacidade_divergente_no_vencedor_e_falha_tecnica() -> None:
    _gravar(_bloqueio())
    divergente = _bloqueio(blocked_capabilities=(BoundaryCapability.CATASTROPHIC_HARM_ENABLEMENT,))
    with (
        UnitOfWork() as uow,
        pytest.raises(HumanProtectionGateUnavailableError, match="blocked_capabilities"),
    ):
        HumanProtectionRepository(uow.session).confirmar_vencedor(divergente)


def test_hp_i34_chave_sem_linha_legivel_e_falha_tecnica() -> None:
    with (
        UnitOfWork() as uow,
        pytest.raises(HumanProtectionGateUnavailableError, match="sem linha legível"),
    ):
        HumanProtectionRepository(uow.session).confirmar_vencedor(_bloqueio())


def test_hp_i35_o_vencedor_coincidente_e_aceito() -> None:
    aplicacao = _bloqueio()
    _gravar(aplicacao)
    with UnitOfWork() as uow:
        HumanProtectionRepository(uow.session).confirmar_vencedor(aplicacao)


def test_hp_i36_o_retorno_publico_sobrevive_ao_fim_da_unit_of_work() -> None:
    """Regressão de `DetachedInstanceError`, defeito reincidente desde a E4.5."""
    evento = _gravar(_bloqueio())
    assert evento is not None
    with UnitOfWork() as uow:
        lida = HumanProtectionRepository(uow.session).ler_aplicacao(
            decision_fingerprint="d" * 64,
            gate_position=GatePosition.G2,
            binding_sha256="b" * 64,
        )
    assert lida is not None
    assert [getattr(lida, campo) for campo in CAMPOS_IMUTAVEIS_DA_APLICACAO]
    assert lida.blocked_capabilities == (BoundaryCapability.CHILD_SEXUAL_EXPLOITATION,)


def test_hp_i37_chave_ausente_devolve_none() -> None:
    with UnitOfWork() as uow:
        assert (
            HumanProtectionRepository(uow.session).ler_aplicacao(
                decision_fingerprint="f" * 64,
                gate_position=GatePosition.G2,
                binding_sha256="b" * 64,
            )
            is None
        )


# --- concorrência real ------------------------------------------------------


def test_hp_i38_duas_conexoes_reais_um_vencedor_um_perdedor_uma_linha() -> None:
    """`RETRY_SEQUENCIAL != CONCORRENCIA`.

    Duas conexões PostgreSQL distintas disparam ao mesmo tempo. Exatamente
    uma cria pai e associação; a outra lê o vencedor e o compara
    integralmente antes de dar a operação por satisfeita.
    """
    aplicacao = _bloqueio()
    barreira = threading.Barrier(2)
    resultados: dict[str, str] = {}
    erros: list[BaseException] = []

    def tentar(nome: str) -> None:
        try:
            conexao = psycopg.connect(_dsn(), autocommit=False)
            with conexao, conexao.cursor() as cursor:
                barreira.wait(timeout=10)
                cursor.execute(
                    f"INSERT INTO {_EVENTOS} (id, control_principal_ref, schedule_id, "
                    "step_id, objective_sha256, decision_fingerprint, "
                    "fingerprint_algo_version, binding_sha256, binding_algo_version, "
                    "outcome, capability_engagement, boundary_version, classifier_version, "
                    "cognitive_operation, gate_position, producer_ref, pause_applied, "
                    "delegations_revoked) VALUES (%s,%s,%s,%s,%s,%s,'1',%s,'1','blocked',"
                    "'operational_enablement',1,'iab-1','expose','g2',%s,true,0) "
                    "ON CONFLICT (decision_fingerprint, gate_position, binding_sha256) "
                    "DO NOTHING RETURNING id",
                    (
                        uuid.uuid4(),
                        _PRINCIPAL,
                        _SCHEDULE,
                        _STEP,
                        _OBJETIVO,
                        aplicacao.decision_fingerprint,
                        aplicacao.binding_sha256,
                        PRODUCER_REF,
                    ),
                )
                linha = cursor.fetchone()
                if linha is not None:
                    cursor.execute(
                        f"INSERT INTO {_CAPACIDADES} VALUES (%s,0,%s)",
                        (linha[0], BoundaryCapability.CHILD_SEXUAL_EXPLOITATION.value),
                    )
                    conexao.commit()
                    resultados[nome] = "vencedor"
                    return
                conexao.rollback()
            resultados[nome] = "perdedor"
        except BaseException as falha:  # noqa: BLE001 - reportado ao teste
            erros.append(falha)

    fios = [threading.Thread(target=tentar, args=(f"t{i}",)) for i in (1, 2)]
    for fio in fios:
        fio.start()
    for fio in fios:
        fio.join(timeout=30)

    assert not erros, erros
    assert sorted(resultados.values()) == ["perdedor", "vencedor"]
    with engine.connect() as conexao:
        assert conexao.execute(sa.text(f"SELECT count(*) FROM {_EVENTOS}")).scalar_one() == 1

    # O perdedor confirma o vencedor com a comparação integral, e ela passa.
    with UnitOfWork() as uow:
        HumanProtectionRepository(uow.session).confirmar_vencedor(aplicacao)


# --- retenção declarada, sem executor ---------------------------------------


def test_hp_i39_nenhum_caminho_desta_entrega_apaga_evento() -> None:
    """`EXPIRACAO_DO_EVENTO = NOT_IMPLEMENTED`, medido e não afirmado."""
    evento = _gravar(_aplicacao())
    antigo = datetime.now(UTC) - timedelta(days=800)
    with engine.begin() as conexao:
        conexao.execute(sa.text(f"ALTER TABLE {_EVENTOS} DISABLE TRIGGER USER"))
        conexao.execute(
            sa.text(f"UPDATE {_EVENTOS} SET decided_at = :d WHERE id = :i"),
            {"d": antigo, "i": evento},
        )
        conexao.execute(sa.text(f"ALTER TABLE {_EVENTOS} ENABLE TRIGGER USER"))
    with pytest.raises(Exception, match="append-only"), engine.begin() as conexao:
        conexao.execute(sa.text(f"DELETE FROM {_EVENTOS} WHERE id = :i"), {"i": evento})
