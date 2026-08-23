"""
Núcleo da orquestração contra PostgreSQL real (`E7.1`).

Aqui ficam as provas que só o banco pode dar: unicidade composta,
atomicidade sob concorrência real, trigger append-only, `CHECK` que
recusa `context_ref` sem hash mesmo por SQL bruto, e o round trip da
migration.

```text
FAKE_PROVES_SERVICE_LOGIC
DATABASE_PROVES_ATOMICITY_AND_IMMUTABILITY
```
"""

import dataclasses
import threading
import uuid

import pytest
import sqlalchemy as sa

from app.database import migrations
from app.database.engine import engine
from app.database.session import SessionLocal
from app.orchestration.errors.exceptions import OrchestrationScopeViolationError
from app.orchestration.models.command_receipt import CommandReceipt
from app.orchestration.models.enums import CommandOperation, HandoffMode
from app.orchestration.repositories.orchestration_repository import OrchestrationRepository
from app.orchestration.schemas.envelope import ContextRef, ScheduleDraft, StepDraft
from app.orchestration.services.command_receipt_service import (
    CommandOutcome,
    CommandReceiptService,
)
from app.orchestration.services.handoff_service import HandoffService
from app.orchestration.services.schedule_service import ScheduleService
from app.repositories.unit_of_work import UnitOfWork

pytestmark = pytest.mark.integration

_REVISION_E71 = "a7f31c05be24"
_PARENT_REVISION = "b4d71c58ae02"
_HASH = "d" * 64

_TABELAS_E71 = (
    "schedules",
    "schedule_steps",
    "handoff_attempts",
    "seal_receipts",
    "command_receipts",
)


def _limpar() -> None:
    """Remove tudo da E7.1 na ordem das dependências.

    `seal_receipts` tem trigger de `DELETE`: a limpeza desabilita a
    trigger de sessão em vez de contorná-la por SQL privilegiado
    permanente — o append-only continua valendo para todo o resto.
    """
    with engine.begin() as conexao:
        conexao.execute(sa.text("ALTER TABLE seal_receipts DISABLE TRIGGER USER"))
        conexao.execute(sa.text("DELETE FROM seal_receipts"))
        conexao.execute(sa.text("ALTER TABLE seal_receipts ENABLE TRIGGER USER"))
        conexao.execute(sa.text("DELETE FROM handoff_attempts"))
        conexao.execute(sa.text("DELETE FROM schedule_steps"))
        conexao.execute(sa.text("DELETE FROM schedules"))
        conexao.execute(sa.text("DELETE FROM command_receipts"))


@pytest.fixture(autouse=True)
def _base_limpa():
    _limpar()
    yield
    _limpar()


def _rascunho(titulo: str = "revisão cruzada") -> ScheduleDraft:
    return ScheduleDraft(
        title=titulo,
        steps=(
            StepDraft(
                role="reviewer",
                instruction_ref="instr://1",
                expected_output_contract="contract://parecer",
                context_refs=(ContextRef(uri="art://a", sha256=_HASH, bytes=7),),
                constraints={"idioma": "pt-BR"},
            ),
            StepDraft(
                role="auditor",
                instruction_ref="instr://2",
                expected_output_contract="contract://auditoria",
            ),
        ),
    )


class _Contexto:
    """Serviços compostos sobre a MESMA sessão, como em produção."""

    def __init__(self, uow: UnitOfWork) -> None:
        self.repositorio = OrchestrationRepository(uow.session)
        self.agendas = ScheduleService(self.repositorio)
        self.handoff = HandoffService(self.repositorio)
        self.comandos = CommandReceiptService(self.repositorio, self.agendas, self.handoff)


def _criar_agenda_ativa(principal: str = "principal-a") -> tuple[uuid.UUID, uuid.UUID]:
    schedule_id = uuid.uuid4()
    with UnitOfWork() as uow:
        contexto = _Contexto(uow)
        contexto.agendas.create_schedule(
            schedule_id=schedule_id,
            control_principal_ref=principal,
            draft=_rascunho(),
            execution_mode=HandoffMode.MANUAL_HANDOFF,
        )
        vista = contexto.agendas.activate(control_principal_ref=principal, schedule_id=schedule_id)
        uow.commit()
    return schedule_id, vista.steps[0].step_id


# --- schema e migration -----------------------------------------------------


def test_e71i01_head_unico_e_filha_de_b4d71c58ae02() -> None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(Config("alembic.ini"))
    assert tuple(script.get_heads()) == (_REVISION_E71,)
    assert script.get_revision(_REVISION_E71).down_revision == _PARENT_REVISION
    assert migrations.current_revision() == _REVISION_E71


def test_e71i02_as_cinco_tabelas_existem() -> None:
    tabelas = set(sa.inspect(engine).get_table_names())
    assert set(_TABELAS_E71) <= tabelas


def test_e71i03_round_trip_upgrade_downgrade_upgrade_em_postgres_real() -> None:
    """Base vazia: `downgrade` derruba as cinco e `upgrade` as recria."""
    migrations.downgrade(_PARENT_REVISION)
    assert migrations.current_revision() == _PARENT_REVISION
    tabelas = set(sa.inspect(engine).get_table_names())
    assert not (set(_TABELAS_E71) & tabelas)
    migrations.upgrade("head")
    assert migrations.current_revision() == _REVISION_E71
    assert set(_TABELAS_E71) <= set(sa.inspect(engine).get_table_names())


def test_e71i04_downgrade_com_recibo_recusa_antes_de_qualquer_ddl() -> None:
    """História append-only não é apagada por conveniência de rollback."""
    schedule_id, step_id = _criar_agenda_ativa()
    with UnitOfWork() as uow:
        _Contexto(uow).handoff.seal_step(
            attempt_id=uuid.uuid4(),
            control_principal_ref="principal-a",
            schedule_id=schedule_id,
            step_id=step_id,
            sealer_ref="selador",
        )
        uow.commit()
    with pytest.raises(RuntimeError, match="downgrade recusado"):
        migrations.downgrade(_PARENT_REVISION)
    assert migrations.current_revision() == _REVISION_E71
    assert set(_TABELAS_E71) <= set(sa.inspect(engine).get_table_names())


def test_e71i05_sem_drift_entre_orm_e_schema() -> None:
    import app.cognitive.models  # noqa: F401
    import app.memory.models  # noqa: F401
    import app.orchestration.models  # noqa: F401
    import app.predictive_accessibility.reconfiguration  # noqa: F401
    from alembic.autogenerate import compare_metadata
    from alembic.migration import MigrationContext
    from app.database.base import Base

    with engine.connect() as conexao:
        diferencas = compare_metadata(MigrationContext.configure(conexao), Base.metadata)
    reais = [d for d in diferencas if "test_" not in str(d)]
    assert reais == [], f"schema/ORM drift: {reais}"


# --- append-only de seal_receipts -------------------------------------------


def _um_recibo() -> uuid.UUID:
    schedule_id, step_id = _criar_agenda_ativa()
    with UnitOfWork() as uow:
        resultado = _Contexto(uow).handoff.seal_step(
            attempt_id=uuid.uuid4(),
            control_principal_ref="principal-a",
            schedule_id=schedule_id,
            step_id=step_id,
            sealer_ref="selador",
        )
        uow.commit()
    return resultado.receipt_id


def test_e71i06_trigger_impede_update_de_seal_receipts() -> None:
    receipt_id = _um_recibo()
    with pytest.raises(Exception, match="append-only"), engine.begin() as conexao:
        conexao.execute(
            sa.text("UPDATE seal_receipts SET sealer_ref = 'outro' WHERE id = :i"),
            {"i": receipt_id},
        )


def test_e71i07_trigger_impede_delete_de_seal_receipts() -> None:
    receipt_id = _um_recibo()
    with pytest.raises(Exception, match="append-only"), engine.begin() as conexao:
        conexao.execute(sa.text("DELETE FROM seal_receipts WHERE id = :i"), {"i": receipt_id})


def test_e71i08_trigger_impede_truncate_de_seal_receipts() -> None:
    _um_recibo()
    with pytest.raises(Exception, match="append-only"), engine.begin() as conexao:
        conexao.execute(sa.text("TRUNCATE seal_receipts"))


# --- context_ref sem hash ---------------------------------------------------


def test_e71i09_context_ref_sem_hash_e_recusado_antes_da_persistencia() -> None:
    """A recusa acontece no value object: nenhuma linha chega a existir."""
    with pytest.raises(ValueError, match="sha256"):
        StepDraft(
            role="reviewer",
            instruction_ref="instr://1",
            expected_output_contract="contract://x",
            context_refs=({"uri": "art://a", "sha256": "", "bytes": 1},),
        )
    with engine.connect() as conexao:
        assert conexao.execute(sa.text("SELECT count(*) FROM schedule_steps")).scalar_one() == 0


@pytest.mark.parametrize(
    "payload",
    [
        '[{"uri": "art://a", "sha256": "", "bytes": 1}]',
        '[{"uri": "art://a", "sha256": "nao-e-hash", "bytes": 1}]',
        '[{"uri": "art://a", "bytes": 1}]',
        '[{"uri": "art://a", "sha256": "' + _HASH + '", "bytes": -1}]',
        '[{"uri": "  ", "sha256": "' + _HASH + '", "bytes": 1}]',
        '[{"uri": "art://a", "sha256": "' + _HASH + '", "bytes": 1, "inline": "x"}]',
        '"conteudo cru"',
    ],
)
def test_e71i10_o_banco_recusa_context_refs_fora_do_contrato(payload: str) -> None:
    """`APP_TYPED_BOUNDARY != DATABASE_INTEGRITY` — SQL bruto também é recusado."""
    schedule_id = uuid.uuid4()
    with engine.begin() as conexao:
        conexao.execute(
            sa.text(
                "INSERT INTO schedules (id, title, state, execution_mode, "
                "control_principal_ref) VALUES (:i, 't', 'draft', 'manual_handoff', 'p')"
            ),
            {"i": schedule_id},
        )
    with (
        pytest.raises(Exception, match="context_refs_canonical|invalid input"),
        engine.begin() as conexao,
    ):
        conexao.execute(
            sa.text(
                "INSERT INTO schedule_steps (id, schedule_id, position, role, "
                "instruction_ref, context_refs, expected_output_contract, constraints, state) "
                "VALUES (:i, :s, 1, 'r', 'instr://1', CAST(:c AS jsonb), 'contract://x', "
                "CAST('{}' AS jsonb), 'pending')"
            ),
            {"i": uuid.uuid4(), "s": schedule_id, "c": payload},
        )


# --- selamento, tentativas e recibos ----------------------------------------


def test_e71i11_dois_selamentos_do_mesmo_conteudo_um_hash_dois_recibos() -> None:
    schedule_id, step_id = _criar_agenda_ativa()
    resultados = []
    for _ in range(2):
        with UnitOfWork() as uow:
            resultados.append(
                _Contexto(uow).handoff.seal_step(
                    attempt_id=uuid.uuid4(),
                    control_principal_ref="principal-a",
                    schedule_id=schedule_id,
                    step_id=step_id,
                    sealer_ref="selador",
                )
            )
            uow.commit()
    primeiro, segundo = resultados
    assert primeiro.content_sha256 == segundo.content_sha256
    assert primeiro.receipt_id != segundo.receipt_id
    with engine.connect() as conexao:
        recibos = conexao.execute(
            sa.text("SELECT count(*), count(DISTINCT content_sha256) FROM seal_receipts")
        ).one()
        tentativas = conexao.execute(
            sa.text("SELECT count(*), count(DISTINCT content_sha256) FROM handoff_attempts")
        ).one()
    assert tuple(recibos) == (2, 1)
    assert tuple(tentativas) == (2, 1)


def test_e71i12_o_hash_nao_muda_com_o_instante_do_selamento() -> None:
    """Dois recibos com `sealed_at` distintos e o mesmo `content_sha256`."""
    schedule_id, step_id = _criar_agenda_ativa()
    for _ in range(2):
        with UnitOfWork() as uow:
            _Contexto(uow).handoff.seal_step(
                attempt_id=uuid.uuid4(),
                control_principal_ref="principal-a",
                schedule_id=schedule_id,
                step_id=step_id,
                sealer_ref="selador",
            )
            uow.commit()
    with engine.connect() as conexao:
        instantes = conexao.execute(
            sa.text(
                "SELECT count(DISTINCT sealed_at), count(DISTINCT content_sha256) "
                "FROM seal_receipts"
            )
        ).one()
    assert instantes[1] == 1


def test_e71i13_apenas_um_recibo_por_tentativa() -> None:
    receipt_id = _um_recibo()
    with engine.connect() as conexao:
        attempt_id = conexao.execute(
            sa.text("SELECT attempt_id FROM seal_receipts WHERE id = :i"), {"i": receipt_id}
        ).scalar_one()
    with pytest.raises(Exception, match="uq_seal_receipts_attempt"), engine.begin() as conexao:
        conexao.execute(
            sa.text(
                "INSERT INTO seal_receipts (id, attempt_id, content_sha256, sealed_at, "
                "sealer_ref) VALUES (:i, :a, :h, now(), 'outro')"
            ),
            {"i": uuid.uuid4(), "a": attempt_id, "h": _HASH},
        )


# --- escopo por principal de controle ---------------------------------------


def test_e71i14_principal_b_nao_le_nem_altera_schedule_do_principal_a() -> None:
    schedule_id, step_id = _criar_agenda_ativa(principal="principal-a")
    with UnitOfWork() as uow:
        repositorio = OrchestrationRepository(uow.session)
        assert (
            repositorio.get_schedule(control_principal_ref="principal-b", schedule_id=schedule_id)
            is None
        )
        assert (
            repositorio.get_step(
                control_principal_ref="principal-b",
                schedule_id=schedule_id,
                step_id=step_id,
            )
            is None
        )
        assert (
            repositorio.list_steps(control_principal_ref="principal-b", schedule_id=schedule_id)
            == []
        )
        assert (
            repositorio.list_attempts(control_principal_ref="principal-b", schedule_id=schedule_id)
            == []
        )
        assert (
            repositorio.lock_schedule(control_principal_ref="principal-b", schedule_id=schedule_id)
            is None
        )
    with UnitOfWork() as uow:
        contexto = _Contexto(uow)
        with pytest.raises(OrchestrationScopeViolationError):
            contexto.comandos.seal_handoff_once(
                technical_principal_ref="principal-b",
                command_key="cmd-b",
                schedule_id=schedule_id,
                step_id=step_id,
                sealer_ref="selador",
            )
    with engine.connect() as conexao:
        assert conexao.execute(sa.text("SELECT count(*) FROM handoff_attempts")).scalar_one() == 0


# --- idempotência de comando ------------------------------------------------


def test_e71i15_mesma_tripla_devolve_o_mesmo_recibo_e_um_unico_efeito() -> None:
    schedule_id, step_id = _criar_agenda_ativa()
    recibos = []
    for _ in range(3):
        with UnitOfWork() as uow:
            recibos.append(
                _Contexto(uow).comandos.seal_handoff_once(
                    technical_principal_ref="principal-a",
                    command_key="cmd-1",
                    schedule_id=schedule_id,
                    step_id=step_id,
                    sealer_ref="selador",
                )
            )
            uow.commit()
    assert len({r.receipt_id for r in recibos}) == 1
    assert len({r.outcome_ref for r in recibos}) == 1
    assert [r.replayed for r in recibos] == [False, True, True]
    with engine.connect() as conexao:
        assert conexao.execute(sa.text("SELECT count(*) FROM handoff_attempts")).scalar_one() == 1
        assert conexao.execute(sa.text("SELECT count(*) FROM seal_receipts")).scalar_one() == 1


def test_e71i16_mesma_chave_em_principais_diferentes_nao_colide() -> None:
    with UnitOfWork() as uow:
        a = _Contexto(uow).comandos.create_schedule_once(
            technical_principal_ref="principal-a", command_key="k", draft=_rascunho()
        )
        uow.commit()
    with UnitOfWork() as uow:
        b = _Contexto(uow).comandos.create_schedule_once(
            technical_principal_ref="principal-b", command_key="k", draft=_rascunho()
        )
        uow.commit()
    assert a.outcome_ref != b.outcome_ref
    assert (a.replayed, b.replayed) == (False, False)
    with engine.connect() as conexao:
        assert conexao.execute(sa.text("SELECT count(*) FROM schedules")).scalar_one() == 2
        assert conexao.execute(sa.text("SELECT count(*) FROM command_receipts")).scalar_one() == 2


def test_e71i17_mesma_chave_em_operacoes_diferentes_nao_colide() -> None:
    schedule_id, step_id = _criar_agenda_ativa()
    with UnitOfWork() as uow:
        contexto = _Contexto(uow)
        criacao = contexto.comandos.create_schedule_once(
            technical_principal_ref="principal-a", command_key="k", draft=_rascunho()
        )
        uow.commit()
    with UnitOfWork() as uow:
        selamento = _Contexto(uow).comandos.seal_handoff_once(
            technical_principal_ref="principal-a",
            command_key="k",
            schedule_id=schedule_id,
            step_id=step_id,
            sealer_ref="selador",
        )
        uow.commit()
    assert criacao.receipt_id != selamento.receipt_id
    assert selamento.replayed is False
    # `get_command_receipt` é do REPOSITÓRIO e devolve entidade ORM — legítimo,
    # e por isso os valores são extraídos DENTRO da sessão. Conservar a
    # entidade além do bloco foi o defeito e71i17 do checkpoint anterior.
    with UnitOfWork() as uow:
        repositorio = OrchestrationRepository(uow.session)
        persistidos = {}
        for operacao in CommandOperation:
            recibo = repositorio.get_command_receipt(
                technical_principal_ref="principal-a",
                operation=operacao.value,
                command_key="k",
            )
            assert recibo is not None, operacao
            persistidos[operacao.value] = (recibo.outcome_ref, recibo.operation)
    assert len(persistidos) == 2
    assert len({outcome for outcome, _ in persistidos.values()}) == 2
    assert persistidos[CommandOperation.CREATE_SCHEDULE.value] == (
        criacao.outcome_ref,
        CommandOperation.CREATE_SCHEDULE.value,
    )
    assert persistidos[CommandOperation.SEAL_HANDOFF.value] == (
        selamento.outcome_ref,
        CommandOperation.SEAL_HANDOFF.value,
    )


def test_e71i18_retry_com_chave_nova_cria_tentativa_nova_e_preserva_a_anterior() -> None:
    schedule_id, step_id = _criar_agenda_ativa()
    for chave in ("cmd-1", "cmd-2"):
        with UnitOfWork() as uow:
            _Contexto(uow).comandos.seal_handoff_once(
                technical_principal_ref="principal-a",
                command_key=chave,
                schedule_id=schedule_id,
                step_id=step_id,
                sealer_ref="selador",
            )
            uow.commit()
    with engine.connect() as conexao:
        numeros = [
            linha[0]
            for linha in conexao.execute(
                sa.text("SELECT attempt_number FROM handoff_attempts ORDER BY attempt_number")
            )
        ]
        hashes = conexao.execute(
            sa.text("SELECT count(DISTINCT content_sha256) FROM handoff_attempts")
        ).scalar_one()
    assert numeros == [1, 2]
    assert hashes == 1


def test_e71i19_a_unicidade_composta_existe_no_banco() -> None:
    with UnitOfWork() as uow:
        _Contexto(uow).comandos.create_schedule_once(
            technical_principal_ref="principal-a", command_key="k", draft=_rascunho()
        )
        uow.commit()
    with pytest.raises(Exception, match="uq_command_receipts"), engine.begin() as conexao:
        conexao.execute(
            sa.text(
                "INSERT INTO command_receipts (id, technical_principal_ref, operation, "
                "command_key, outcome_ref) VALUES (:i, 'principal-a', :o, 'k', 'x')"
            ),
            {"i": uuid.uuid4(), "o": CommandOperation.CREATE_SCHEDULE.value},
        )


def test_e71i20_efeito_que_falha_nao_deixa_recibo_de_comando_commitado() -> None:
    """A reivindicação e o efeito vivem na mesma transação.

    Sem isso, uma chave ficaria "consumida" apontando para um efeito que
    nunca existiu, e o retry legítimo com a mesma chave devolveria um
    recibo órfão.
    """
    schedule_id, step_id = _criar_agenda_ativa()
    with UnitOfWork() as uow:
        contexto = _Contexto(uow)
        with pytest.raises(OrchestrationScopeViolationError):
            contexto.comandos.seal_handoff_once(
                technical_principal_ref="principal-a",
                command_key="cmd-falha",
                schedule_id=schedule_id,
                step_id=uuid.uuid4(),  # etapa inexistente: o efeito falha
                sealer_ref="selador",
            )
    with engine.connect() as conexao:
        assert conexao.execute(sa.text("SELECT count(*) FROM command_receipts")).scalar_one() == 0
    with UnitOfWork() as uow:
        resultado = _Contexto(uow).comandos.seal_handoff_once(
            technical_principal_ref="principal-a",
            command_key="cmd-falha",
            schedule_id=schedule_id,
            step_id=step_id,
            sealer_ref="selador",
        )
        uow.commit()
    assert resultado.replayed is False


def test_e71i21_concorrencia_real_nao_duplica_o_efeito_idempotente() -> None:
    """Duas threads, duas conexões, a mesma tripla — um efeito só."""
    schedule_id, step_id = _criar_agenda_ativa()
    barreira = threading.Barrier(2)
    resultados: list[CommandOutcome] = []
    erros: list[BaseException] = []

    def selar() -> None:
        try:
            with UnitOfWork(session_factory=SessionLocal) as uow:
                contexto = _Contexto(uow)
                barreira.wait(timeout=10)
                resultados.append(
                    contexto.comandos.seal_handoff_once(
                        technical_principal_ref="principal-a",
                        command_key="cmd-concorrente",
                        schedule_id=schedule_id,
                        step_id=step_id,
                        sealer_ref="selador",
                    )
                )
                uow.commit()
        except BaseException as exc:  # noqa: BLE001 - o teste inspeciona a falha
            erros.append(exc)

    linhas = [threading.Thread(target=selar) for _ in range(2)]
    for linha in linhas:
        linha.start()
    for linha in linhas:
        linha.join(timeout=30)

    assert erros == [], erros
    assert len(resultados) == 2
    with engine.connect() as conexao:
        tentativas = conexao.execute(sa.text("SELECT count(*) FROM handoff_attempts")).scalar_one()
        recibos = conexao.execute(sa.text("SELECT count(*) FROM seal_receipts")).scalar_one()
        comandos = conexao.execute(sa.text("SELECT count(*) FROM command_receipts")).scalar_one()
    assert (tentativas, recibos, comandos) == (1, 1, 1)
    assert len({r.outcome_ref for r in resultados}) == 1


def test_e71i22_o_outcome_ref_aponta_para_a_tentativa_realmente_criada() -> None:
    schedule_id, step_id = _criar_agenda_ativa()
    with UnitOfWork() as uow:
        resultado = _Contexto(uow).comandos.seal_handoff_once(
            technical_principal_ref="principal-a",
            command_key="cmd-1",
            schedule_id=schedule_id,
            step_id=step_id,
            sealer_ref="selador",
        )
        uow.commit()
    with UnitOfWork() as uow:
        recibo = uow.session.get(CommandReceipt, resultado.receipt_id)
        assert recibo is not None
        persistido = (recibo.outcome_ref, recibo.operation)
        tentativa = uow.session.execute(sa.text("SELECT id FROM handoff_attempts")).scalar_one()
    assert persistido == (str(tentativa), CommandOperation.SEAL_HANDOFF.value)
    assert resultado.outcome_ref == str(tentativa)


# --- ordem e persistência ---------------------------------------------------


def test_e71i23_as_etapas_sao_persistidas_em_ordem_com_o_contexto_declarado() -> None:
    schedule_id, _ = _criar_agenda_ativa()
    with UnitOfWork() as uow:
        vista = _Contexto(uow).agendas.get_schedule(
            control_principal_ref="principal-a", schedule_id=schedule_id
        )
    assert [etapa.position for etapa in vista.steps] == [1, 2]
    assert [etapa.role for etapa in vista.steps] == ["reviewer", "auditor"]
    assert vista.steps[0].context_refs[0].sha256 == _HASH
    assert vista.steps[1].context_refs == ()
    assert vista.steps[0].constraints == (("idioma", "pt-BR"),)


def test_e71i24_o_sealed_at_vem_do_relogio_do_banco() -> None:
    schedule_id, step_id = _criar_agenda_ativa()
    with UnitOfWork() as uow:
        contexto = _Contexto(uow)
        antes = contexto.repositorio.database_now()
        resultado = contexto.handoff.seal_step(
            attempt_id=uuid.uuid4(),
            control_principal_ref="principal-a",
            schedule_id=schedule_id,
            step_id=step_id,
            sealer_ref="selador",
        )
        depois = contexto.repositorio.database_now()
        uow.commit()
    assert antes <= resultado.sealed_at <= depois
    assert resultado.sealed_at.tzinfo is not None


# --- fronteira de sessão: o que a API pública devolve ------------------------


def test_e71i25_todo_retorno_publico_de_service_sobrevive_ao_fim_da_unit_of_work() -> None:
    """Regressão da classificação dos defeitos e71i17/e71i22.

    ```text
    SERVICE_RETURN = FROZEN_DTO
    SERVICE_RETURN != ORM_INSTANCE
    ```

    Os sete métodos públicos dos três serviços devolvem `dataclass`
    congelada. O teste consome **todos** os campos depois que a sessão
    fechou: se algum retorno voltasse a ser instância ORM ou coleção
    lazy, este teste levantaria `DetachedInstanceError` em vez de passar.
    """
    schedule_id = uuid.uuid4()
    with UnitOfWork() as uow:
        contexto = _Contexto(uow)
        criada = contexto.agendas.create_schedule(
            schedule_id=schedule_id,
            control_principal_ref="principal-a",
            draft=_rascunho(),
            execution_mode=HandoffMode.MANUAL_HANDOFF,
        )
        lida = contexto.agendas.get_schedule(
            control_principal_ref="principal-a", schedule_id=schedule_id
        )
        ativada = contexto.agendas.activate(
            control_principal_ref="principal-a", schedule_id=schedule_id
        )
        step_id = ativada.steps[0].step_id
        conteudo = contexto.handoff.build_envelope_content(
            control_principal_ref="principal-a", schedule_id=schedule_id, step_id=step_id
        )
        selado = contexto.handoff.seal_step(
            attempt_id=uuid.uuid4(),
            control_principal_ref="principal-a",
            schedule_id=schedule_id,
            step_id=step_id,
            sealer_ref="selador",
        )
        comando = contexto.comandos.seal_handoff_once(
            technical_principal_ref="principal-a",
            command_key="cmd-fronteira",
            schedule_id=schedule_id,
            step_id=step_id,
            sealer_ref="selador",
        )
        uow.commit()

    retornos = (criada, lida, ativada, conteudo, selado, comando)

    # Nenhum é entidade ORM, nem carrega estado de sessão.
    for retorno in retornos:
        assert not hasattr(retorno, "_sa_instance_state"), type(retorno).__name__
        assert dataclasses.is_dataclass(retorno), type(retorno).__name__
        assert type(retorno).__dataclass_params__.frozen, type(retorno).__name__

    # Todo campo é lido DEPOIS do fim da transação, incluindo os aninhados.
    for retorno in retornos:
        for campo in dataclasses.fields(retorno):
            getattr(retorno, campo.name)
    for etapa in ativada.steps:
        assert not hasattr(etapa, "_sa_instance_state")
        for referencia in etapa.context_refs:
            assert referencia.sha256 == _HASH
        assert etapa.constraints in ((("idioma", "pt-BR"),), ())
    assert conteudo.content_sha256() == selado.content_sha256
    assert comando.outcome_ref != selado.content_sha256


# --- protocolo do ON CONFLICT DO UPDATE -------------------------------------


_COLUNAS_RECIBO = (
    "id",
    "technical_principal_ref",
    "operation",
    "command_key",
    "outcome_ref",
    "created_at",
    "updated_at",
)


def _snapshot_recibos() -> list[tuple[object, ...]]:
    """Todas as colunas de todos os recibos de comando, em ordem estável."""
    with engine.connect() as conexao:
        return [
            tuple(linha)
            for linha in conexao.execute(
                sa.text(
                    f"SELECT {', '.join(_COLUNAS_RECIBO)} FROM command_receipts "
                    "ORDER BY created_at, id"
                )
            )
        ]


def _snapshot_efeitos() -> tuple[int, int, int, list[tuple[object, ...]]]:
    with engine.connect() as conexao:
        tentativas = conexao.execute(sa.text("SELECT count(*) FROM handoff_attempts")).scalar_one()
        recibos = conexao.execute(sa.text("SELECT count(*) FROM seal_receipts")).scalar_one()
        comandos = conexao.execute(sa.text("SELECT count(*) FROM command_receipts")).scalar_one()
        selos = [
            tuple(linha)
            for linha in conexao.execute(
                sa.text(
                    "SELECT id, attempt_id, content_sha256, sealed_at, sealer_ref "
                    "FROM seal_receipts ORDER BY id"
                )
            )
        ]
    return tentativas, recibos, comandos, selos


def test_e71i26_replay_sequencial_nao_muta_nenhum_campo_do_recibo() -> None:
    """`DO UPDATE` é no-op observável: nenhuma coluna do recibo muda.

    ```text
    NOOP_UPDATE_TAKES_THE_ROW_LOCK
    NOOP_UPDATE_CHANGES_NO_COLUMN
    ```

    O `DO UPDATE` existe para bloquear o segundo chamador até o commit do
    primeiro — não para atualizar coisa alguma. Se ele mexesse em
    `updated_at`, `created_at` ou `outcome_ref`, o recibo deixaria de
    descrever o comando original e o replay viraria uma escrita.
    """
    schedule_id, step_id = _criar_agenda_ativa()
    with UnitOfWork() as uow:
        primeiro = _Contexto(uow).comandos.seal_handoff_once(
            technical_principal_ref="principal-a",
            command_key="cmd-replay",
            schedule_id=schedule_id,
            step_id=step_id,
            sealer_ref="selador",
        )
        uow.commit()

    antes_recibos = _snapshot_recibos()
    antes_efeitos = _snapshot_efeitos()
    assert len(antes_recibos) == 1

    repetidos = []
    for _ in range(3):
        with UnitOfWork() as uow:
            repetidos.append(
                _Contexto(uow).comandos.seal_handoff_once(
                    technical_principal_ref="principal-a",
                    command_key="cmd-replay",
                    schedule_id=schedule_id,
                    step_id=step_id,
                    sealer_ref="selador",
                )
            )
            uow.commit()

    assert _snapshot_recibos() == antes_recibos
    assert _snapshot_efeitos() == antes_efeitos
    assert all(resultado.replayed for resultado in repetidos)
    assert {resultado.receipt_id for resultado in repetidos} == {primeiro.receipt_id}
    assert {resultado.outcome_ref for resultado in repetidos} == {primeiro.outcome_ref}
    assert _snapshot_efeitos()[:3] == (1, 1, 1)


def test_e71i27_replay_concorrente_nao_muta_o_recibo_nem_duplica_efeito() -> None:
    """O mesmo snapshot, agora sob duas transações reais simultâneas."""
    schedule_id, step_id = _criar_agenda_ativa()
    with UnitOfWork() as uow:
        original = _Contexto(uow).comandos.seal_handoff_once(
            technical_principal_ref="principal-a",
            command_key="cmd-replay-concorrente",
            schedule_id=schedule_id,
            step_id=step_id,
            sealer_ref="selador",
        )
        uow.commit()

    antes_recibos = _snapshot_recibos()
    antes_efeitos = _snapshot_efeitos()

    barreira = threading.Barrier(2)
    resultados: list[CommandOutcome] = []
    erros: list[BaseException] = []

    def repetir() -> None:
        try:
            with UnitOfWork(session_factory=SessionLocal) as uow:
                contexto = _Contexto(uow)
                barreira.wait(timeout=10)
                resultados.append(
                    contexto.comandos.seal_handoff_once(
                        technical_principal_ref="principal-a",
                        command_key="cmd-replay-concorrente",
                        schedule_id=schedule_id,
                        step_id=step_id,
                        sealer_ref="selador",
                    )
                )
                uow.commit()
        except BaseException as exc:  # noqa: BLE001 - o teste inspeciona a falha
            erros.append(exc)

    linhas = [threading.Thread(target=repetir) for _ in range(2)]
    for linha in linhas:
        linha.start()
    for linha in linhas:
        linha.join(timeout=30)

    assert erros == [], erros
    assert len(resultados) == 2
    assert _snapshot_recibos() == antes_recibos
    assert _snapshot_efeitos() == antes_efeitos
    assert {r.receipt_id for r in resultados} == {original.receipt_id}
    assert {r.outcome_ref for r in resultados} == {original.outcome_ref}
    assert all(r.replayed for r in resultados)
    assert _snapshot_efeitos()[:3] == (1, 1, 1)
