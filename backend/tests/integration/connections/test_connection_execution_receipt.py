"""
Provas comportamentais permanentes do recibo de execução (`E7.4-1`).

```text
NEW_MANUAL_ATTEMPT             = EXACTLY_ONE_RECEIPT
LEGACY_ATTEMPT_WITHOUT_RECEIPT != FABRICATE_HISTORY
PROFILE_DESCREVE_CONFIGURAÇÃO  != RECIBO_DESCREVE_EXECUÇÃO
TWO_VALID_REFERENCES           != ONE_COHERENT_REFERENCE
APPLICATION_CHECK              != DATABASE_GUARANTEE
```

Doze provas, contra PostgreSQL real. Nenhuma delas passa por acidente:
onde a garantia é do banco, o teste chega por **SQL bruto**, que não
passa pelo repositório; onde a garantia é do serviço, o teste força a
falha em vez de esperar que ela não ocorra.

`FULL_SUITE_GREEN != PROPERTY_PROVEN` — este arquivo existe porque a
suíte inteira já passava antes de qualquer uma destas propriedades ser
verificada.
"""

import threading
import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.exc import IntegrityError

from app.connections.models.enums import ConnectionMethod, ModelAttestationLevel
from app.connections.repositories.connection_repository import ConnectionRepository
from app.connections.services.connection_execution_receipt_service import (
    ConnectionExecutionReceiptService,
)
from app.connections.services.connection_profile_service import ConnectionProfileService
from app.database.engine import engine
from app.database.health import check_database_health
from app.orchestration.adapters.manual_transport import ManualTransport
from app.orchestration.models.enums import HandoffMode
from app.orchestration.repositories.orchestration_repository import OrchestrationRepository
from app.orchestration.schemas.envelope import ScheduleDraft, StepDraft
from app.orchestration.schemas.output_contract import OUTPUT_NON_EMPTY_TEXT_V1
from app.orchestration.services.command_receipt_service import CommandReceiptService
from app.orchestration.services.handoff_service import HandoffService
from app.orchestration.services.manual_handoff_export_service import ManualHandoffExportService
from app.orchestration.services.return_validation_service import ReturnValidationService
from app.orchestration.services.schedule_service import ScheduleService
from app.repositories.unit_of_work import UnitOfWork

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not check_database_health().available,
        reason="PostgreSQL real indisponível — FK composta e UNIQUE são a prova.",
    ),
]

_TABELAS_APPEND_ONLY = (
    "connection_execution_receipts",
    "audit_opinions",
    "execution_observations",
    "orchestration_control_events",
    "handoff_results",
    "handoff_attributions",
    "seal_receipts",
    "service_delegations",
)
_TABELAS = (
    *_TABELAS_APPEND_ONLY,
    "handoff_attempts",
    "schedule_steps",
    "schedules",
    "command_receipts",
    # O perfil manual só pode cair DEPOIS do recibo que o referencia.
    "connection_profiles",
)


def _limpar() -> None:
    with engine.begin() as conexao:
        for tabela in _TABELAS_APPEND_ONLY:
            conexao.execute(sa.text(f"ALTER TABLE {tabela} DISABLE TRIGGER USER"))
            conexao.execute(sa.text(f"DELETE FROM {tabela}"))
            conexao.execute(sa.text(f"ALTER TABLE {tabela} ENABLE TRIGGER USER"))
        for tabela in _TABELAS:
            if tabela not in _TABELAS_APPEND_ONLY:
                conexao.execute(sa.text(f"DELETE FROM {tabela}"))


@pytest.fixture(autouse=True)
def _base_limpa():
    _limpar()
    yield
    _limpar()


class _Contexto:
    """Composição completa sobre UMA sessão — como o router faz."""

    def __init__(self, uow: UnitOfWork, transporte=None) -> None:  # noqa: ANN001
        self.repositorio = OrchestrationRepository(uow.session)
        self.conexoes = ConnectionRepository(uow.session)
        self.agendas = ScheduleService(self.repositorio)
        self.handoff = HandoffService(self.repositorio)
        self.perfis = ConnectionProfileService(self.conexoes)
        self.recibos = ConnectionExecutionReceiptService(self.conexoes)
        self.exportacao = ManualHandoffExportService(
            self.repositorio,
            self.handoff,
            transporte or ManualTransport(),
            connection_profiles=self.perfis,
            connection_receipts=self.recibos,
        )
        self.validacao = ReturnValidationService(self.repositorio)
        self.comandos = CommandReceiptService(
            self.repositorio, self.agendas, self.handoff, self.exportacao, self.validacao
        )


def _rascunho() -> ScheduleDraft:
    return ScheduleDraft(
        title="t",
        steps=(
            StepDraft(
                role="reviewer",
                instruction_ref="i://1",
                expected_output_contract=OUTPUT_NON_EMPTY_TEXT_V1,
            ),
        ),
    )


def _preparar(principal: str = "p") -> tuple[uuid.UUID, uuid.UUID]:
    schedule_id = uuid.uuid4()
    with UnitOfWork() as uow:
        ctx = _Contexto(uow)
        ctx.agendas.create_schedule(
            schedule_id=schedule_id,
            control_principal_ref=principal,
            draft=_rascunho(),
            execution_mode=HandoffMode.MANUAL_HANDOFF,
        )
        vista = ctx.agendas.activate(control_principal_ref=principal, schedule_id=schedule_id)
        uow.commit()
    return schedule_id, vista.steps[0].step_id


def _exportar(
    schedule_id: uuid.UUID,
    step_id: uuid.UUID,
    principal: str = "p",
    command_key: str | None = None,
    transporte=None,  # noqa: ANN001
) -> tuple[object, object]:
    with UnitOfWork() as uow:
        ctx = _Contexto(uow, transporte)
        recibo, saida = ctx.comandos.export_handoff_once(
            technical_principal_ref=principal,
            command_key=command_key or f"e-{uuid.uuid4()}",
            schedule_id=schedule_id,
            step_id=step_id,
            sealer_ref=principal,
        )
        uow.commit()
    return recibo, saida


def _recibos_de_conexao() -> list[dict[str, object]]:
    with engine.connect() as conexao:
        return [
            dict(linha._mapping)
            for linha in conexao.execute(
                sa.text(
                    "SELECT id, control_principal_ref, schedule_id, step_id, attempt_id, "
                    "connection_id, connection_method, access_provider, requested_model, "
                    "observed_model, model_attestation_level, observed_at "
                    "FROM connection_execution_receipts ORDER BY observed_at, id"
                )
            )
        ]


def _contar(tabela: str) -> int:
    with engine.connect() as conexao:
        return conexao.execute(sa.text(f"SELECT count(*) FROM {tabela}")).scalar_one()


# --- 1. exatamente um recibo por Attempt manual -----------------------------


def test_e741p01_attempt_manual_cria_exatamente_um_recibo() -> None:
    """`NEW_MANUAL_ATTEMPT = EXACTLY_ONE_RECEIPT`.

    Não-vacuidade explícita: a prova falharia se o recibo simplesmente
    não existisse, então ela também afirma que a Attempt existe e que o
    recibo aponta para ela.
    """
    schedule_id, step_id = _preparar()
    _, saida = _exportar(schedule_id, step_id)
    attempt_id = saida.exported.attempt_id

    recibos = _recibos_de_conexao()
    assert len(recibos) == 1, recibos
    assert _contar("handoff_attempts") == 1
    assert recibos[0]["attempt_id"] == attempt_id
    assert recibos[0]["schedule_id"] == schedule_id
    assert recibos[0]["step_id"] == step_id
    assert recibos[0]["connection_method"] == ConnectionMethod.MANUAL_HANDOFF.value


# --- 2 e 12. campos copiados no ato; perfil alterado não reescreve história --


def test_e741p02_campos_sao_copiados_e_nao_mudam_com_alteracao_do_perfil() -> None:
    """Provas 31, 32 — cópia no ato, e não derivação por join na leitura.

    O perfil é alterado **depois** do recibo, por SQL bruto, e o recibo
    tem de continuar dizendo por onde a execução passou. Se algum campo
    fosse derivado por join, ele mudaria aqui — e a história de ontem
    passaria a depender da configuração de hoje.
    """
    schedule_id, step_id = _preparar()
    _exportar(schedule_id, step_id)
    antes = _recibos_de_conexao()[0]

    with engine.begin() as conexao:
        conexao.execute(
            sa.text(
                "UPDATE connection_profiles SET display_name = 'renomeado', "
                "state = 'revoked' WHERE id = :cid"
            ),
            {"cid": antes["connection_id"]},
        )
        perfil = conexao.execute(
            sa.text("SELECT state, display_name FROM connection_profiles WHERE id = :cid"),
            {"cid": antes["connection_id"]},
        ).one()
    assert perfil.state == "revoked", "o tamper precisa ter EFEITO, senão a prova é vazia"

    depois = _recibos_de_conexao()[0]
    assert depois == antes, "algum campo do recibo é derivado do perfil na leitura"


# --- 3. o perfil usado pertence ao mesmo principal --------------------------


def test_e741p03_o_perfil_usado_pertence_ao_mesmo_principal() -> None:
    """Dois principals, dois perfis manuais, nenhum cruzamento."""
    s_a, step_a = _preparar("principal-a")
    s_b, step_b = _preparar("principal-b")
    _exportar(s_a, step_a, principal="principal-a")
    _exportar(s_b, step_b, principal="principal-b")

    with engine.connect() as conexao:
        pares = conexao.execute(
            sa.text(
                "SELECT r.control_principal_ref AS dono_recibo, "
                "p.control_principal_ref AS dono_perfil "
                "FROM connection_execution_receipts r "
                "JOIN connection_profiles p ON p.id = r.connection_id"
            )
        ).all()
    assert len(pares) == 2
    assert all(par.dono_recibo == par.dono_perfil for par in pares)
    assert {par.dono_recibo for par in pares} == {"principal-a", "principal-b"}


# --- 4. replay sequencial devolve o recibo original -------------------------


def test_e741p04_replay_sequencial_nao_duplica_o_recibo() -> None:
    """`REPLAY != NEW_REQUEST`.

    A mesma `command_key` não roda o efeito de novo, então não há segundo
    recibo. A prova compara o **snapshot completo** da linha antes e
    depois: contar linhas provaria menos, porque uma reescrita silenciosa
    manteria a contagem.
    """
    schedule_id, step_id = _preparar()
    chave = f"e-{uuid.uuid4()}"
    _exportar(schedule_id, step_id, command_key=chave)
    antes = _recibos_de_conexao()

    recibo_replay, saida = _exportar(schedule_id, step_id, command_key=chave)
    assert recibo_replay.replayed is True
    assert saida is None, "replay não pode rodar o efeito"

    depois = _recibos_de_conexao()
    assert depois == antes, "o replay alterou ou duplicou o recibo"
    assert len(depois) == 1


# --- 5. concorrência produz um efeito ---------------------------------------


def test_e741p05_concorrencia_produz_um_efeito_e_os_demais_sao_replay() -> None:
    """Quatro chamadores, mesma chave: um efeito, um recibo, quatro respostas."""
    schedule_id, step_id = _preparar()
    chave = f"e-{uuid.uuid4()}"
    resultados: list[object] = []
    erros: list[BaseException] = []
    barreira = threading.Barrier(4)

    def chamar() -> None:
        try:
            barreira.wait(timeout=10)
            resultados.append(_exportar(schedule_id, step_id, command_key=chave)[0])
        except BaseException as erro:  # noqa: BLE001
            erros.append(erro)

    fios = [threading.Thread(target=chamar) for _ in range(4)]
    for fio in fios:
        fio.start()
    for fio in fios:
        fio.join(timeout=30)

    assert not erros, erros
    assert len(resultados) == 4
    assert sum(1 for r in resultados if not r.replayed) == 1, "mais de um efeito"
    assert len(_recibos_de_conexao()) == 1
    assert _contar("handoff_attempts") == 1


# --- 6. falha do recibo reverte o conjunto inteiro --------------------------


def test_e741p06_falha_do_recibo_deixa_zero_de_tudo_e_zero_transporte() -> None:
    """A prova mais importante: o recibo é parte da mesma unidade atômica.

    ```text
    falha no recibo = 0 Attempt + 0 SealReceipt + 0 CommandReceipt
                      + 0 ConnectionExecutionReceipt + 0 chamada ao transporte
    ```

    A falha é forçada **dentro** do serviço de recibo, depois de a
    Attempt e o `SealReceipt` já existirem na transação — se fosse
    forçada antes, o teste provaria apenas que nada começou.
    """
    schedule_id, step_id = _preparar()

    class _TransporteContado:
        mode = "manual_handoff"

        def __init__(self) -> None:
            self.chamadas = 0

        def export(self, handoff):  # noqa: ANN001, ANN202
            self.chamadas += 1
            return handoff

        def receive(self, *, attempt_id):  # noqa: ANN001, ANN202
            raise AssertionError("não usado")

    transporte = _TransporteContado()

    class _ReciboQueFalha(ConnectionExecutionReceiptService):
        def record_execution(self, **kwargs):  # noqa: ANN003, ANN201
            raise RuntimeError("falha forçada na gravação do recibo")

    with pytest.raises(RuntimeError, match="falha forçada"), UnitOfWork() as uow:
        if True:
            ctx = _Contexto(uow, transporte)
            ctx.exportacao = ManualHandoffExportService(
                ctx.repositorio,
                ctx.handoff,
                transporte,
                connection_profiles=ctx.perfis,
                connection_receipts=_ReciboQueFalha(ctx.conexoes),
            )
            comandos = CommandReceiptService(
                ctx.repositorio, ctx.agendas, ctx.handoff, ctx.exportacao, ctx.validacao
            )
            comandos.export_handoff_once(
                technical_principal_ref="p",
                command_key=f"e-{uuid.uuid4()}",
                schedule_id=schedule_id,
                step_id=step_id,
                sealer_ref="p",
            )
            uow.commit()

    assert _contar("handoff_attempts") == 0
    assert _contar("seal_receipts") == 0
    assert _contar("command_receipts") == 0
    assert _contar("connection_execution_receipts") == 0
    assert transporte.chamadas == 0, "o transporte rodou antes da recusa"


# --- 7. atestação honesta no manual -----------------------------------------


def test_e741p07_manual_grava_observed_model_nulo_e_atestacao_unknown() -> None:
    """Prova 33 aplicada ao manual — nunca um modelo presumido.

    ```text
    GATEWAY_OPACO -> NULL, jamais um palpite
    ```

    Quem transporta é a pessoa: não há operador, não há modelo
    solicitado e não há modelo observado. `unknown` é a verdade.
    """
    schedule_id, step_id = _preparar()
    _exportar(schedule_id, step_id)
    recibo = _recibos_de_conexao()[0]
    assert recibo["access_provider"] is None
    assert recibo["requested_model"] is None
    assert recibo["observed_model"] is None
    assert recibo["model_attestation_level"] == ModelAttestationLevel.UNKNOWN.value


# --- 8. cruzamento de principal recusado por SQL bruto ----------------------


def test_e741p08_recibo_de_a_nao_liga_a_conexao_de_b_por_sql_bruto() -> None:
    """Prova 35 — `TWO_VALID_REFERENCES != ONE_COHERENT_REFERENCE`.

    O ataque chega por SQL bruto, que não passa pelo repositório: cada
    referência é válida sozinha, e só a FK **composta** recusa o par.
    """
    s_a, step_a = _preparar("principal-a")
    s_b, step_b = _preparar("principal-b")
    _exportar(s_a, step_a, principal="principal-a")
    _exportar(s_b, step_b, principal="principal-b")

    with engine.connect() as conexao:
        conexao_de_b = conexao.execute(
            sa.text(
                "SELECT id FROM connection_profiles " "WHERE control_principal_ref = 'principal-b'"
            )
        ).scalar_one()
        attempt_de_a = conexao.execute(
            sa.text(
                "SELECT a.id, a.step_id, a.schedule_id FROM handoff_attempts a "
                "JOIN schedules s ON s.id = a.schedule_id "
                "WHERE s.control_principal_ref = 'principal-a'"
            )
        ).one()

    # A Attempt de A JÁ tem recibo — toda Attempt manual tem. Sem liberar
    # o `UNIQUE(attempt_id)`, o INSERT abaixo seria recusado pela guarda
    # ERRADA, e a prova continuaria verde com a FK composta removida.
    #
    # ```text
    # REFUSAL_BY_THE_WRONG_GUARD = UNPROVEN_INVARIANT
    # ```
    #
    # Achado do mutante `M-FK`: a primeira versão desta prova media o
    # `UNIQUE`, não a coerência bilateral.
    with engine.begin() as conexao:
        conexao.execute(sa.text("ALTER TABLE connection_execution_receipts DISABLE TRIGGER USER"))
        conexao.execute(
            sa.text("DELETE FROM connection_execution_receipts WHERE attempt_id = :aid"),
            {"aid": attempt_de_a.id},
        )
        conexao.execute(sa.text("ALTER TABLE connection_execution_receipts ENABLE TRIGGER USER"))

    with (
        pytest.raises(
            IntegrityError, match="fk_connection_execution_receipts_connection_within_principal"
        ),
        engine.begin() as conexao,
    ):
        conexao.execute(
            sa.text(
                "INSERT INTO connection_execution_receipts "
                "(id, control_principal_ref, schedule_id, step_id, attempt_id, "
                " connection_id, connection_method, model_attestation_level, observed_at) "
                "VALUES (gen_random_uuid(), 'principal-a', :sid, :stid, :aid, "
                " :cid, 'manual_handoff', 'unknown', now())"
            ),
            {
                "sid": attempt_de_a.schedule_id,
                "stid": attempt_de_a.step_id,
                "aid": attempt_de_a.id,
                "cid": conexao_de_b,
            },
        )

    # Não-vacuidade: a MESMA linha, com a conexão do PRÓPRIO dono, entra.
    with engine.connect() as conexao:
        conexao_de_a = conexao.execute(
            sa.text(
                "SELECT id FROM connection_profiles " "WHERE control_principal_ref = 'principal-a'"
            )
        ).scalar_one()
    with engine.begin() as conexao:
        conexao.execute(
            sa.text(
                "INSERT INTO connection_execution_receipts "
                "(id, control_principal_ref, schedule_id, step_id, attempt_id, "
                " connection_id, connection_method, model_attestation_level, observed_at) "
                "VALUES (gen_random_uuid(), 'principal-a', :sid, :stid, :aid, "
                " :cid, 'manual_handoff', 'unknown', now())"
            ),
            {
                "sid": attempt_de_a.schedule_id,
                "stid": attempt_de_a.step_id,
                "aid": attempt_de_a.id,
                "cid": conexao_de_a,
            },
        )


# --- 9. UNIQUE e bicondicional, com caso negativo e não-vacuidade -----------


def test_e741p09a_unique_attempt_recusa_o_segundo_recibo() -> None:
    """Prova 36 — um recibo por Attempt, imposto pelo banco."""
    schedule_id, step_id = _preparar()
    _exportar(schedule_id, step_id)
    original = _recibos_de_conexao()[0]

    with pytest.raises(IntegrityError), engine.begin() as conexao:
        conexao.execute(
            sa.text(
                "INSERT INTO connection_execution_receipts "
                "(id, control_principal_ref, schedule_id, step_id, attempt_id, "
                " connection_id, connection_method, model_attestation_level, observed_at) "
                "VALUES (gen_random_uuid(), :ref, :sid, :stid, :aid, :cid, "
                " 'manual_handoff', 'unknown', now())"
            ),
            {
                "ref": original["control_principal_ref"],
                "sid": original["schedule_id"],
                "stid": original["step_id"],
                "aid": original["attempt_id"],
                "cid": original["connection_id"],
            },
        )
    assert len(_recibos_de_conexao()) == 1


@pytest.mark.parametrize(
    ("atestacao", "observado", "aceita"),
    [
        ("attested", "modelo-x", True),
        ("attested", None, False),
        ("unknown", "modelo-x", False),
        ("self_declared", "modelo-x", False),
        ("unknown", None, True),
        ("self_declared", None, True),
    ],
)
def test_e741p09b_bicondicional_da_atestacao(atestacao, observado, aceita) -> None:  # noqa: ANN001
    """Prova 39 — `attested` ⇔ `observed_model IS NOT NULL`.

    Os seis casos, e não só o negativo: sem os três que **passam**, a
    prova não distinguiria "o CHECK recusa o errado" de "o CHECK recusa
    tudo" — que é a não-vacuidade que este programa já exigiu antes.
    """
    schedule_id, step_id = _preparar()
    _exportar(schedule_id, step_id)
    base = _recibos_de_conexao()[0]

    parametros = {
        "ref": base["control_principal_ref"],
        "sid": base["schedule_id"],
        "stid": base["step_id"],
        "aid": uuid.uuid4(),
        "cid": base["connection_id"],
        "nivel": atestacao,
        "modelo": observado,
    }
    comando = sa.text(
        "INSERT INTO connection_execution_receipts "
        "(id, control_principal_ref, schedule_id, step_id, attempt_id, "
        " connection_id, connection_method, model_attestation_level, "
        " observed_model, observed_at) "
        "VALUES (gen_random_uuid(), :ref, :sid, :stid, :aid, :cid, "
        " 'manual_handoff', :nivel, :modelo, now())"
    )
    # A FK da Attempt é DEFERRABLE: o `attempt_id` inventado só é cobrado
    # no commit. O CHECK, que é o alvo aqui, age no INSERT — por isso os
    # casos ACEITOS morrem na FK e os RECUSADOS morrem no CHECK.
    esperado = "fk_connection_execution_receipts_attempt" if aceita else "attestation_bicondicional"
    with pytest.raises(IntegrityError, match=esperado), engine.begin() as conexao:
        conexao.execute(comando, parametros)


# --- 10. perfil manual idempotente sob quatro chamadores --------------------


def test_e741p10_perfil_manual_idempotente_sob_quatro_chamadores() -> None:
    """Prova 37 — a prova obrigatória do plano, literal.

    ```text
    4 chamadores concorrentes
    4 retornos bem-sucedidos
    1 connection_id distinto
    1 linha no banco
    0 IntegrityError exposto
    ```
    """
    retornos: list[object] = []
    erros: list[BaseException] = []
    barreira = threading.Barrier(4)

    def chamar() -> None:
        try:
            barreira.wait(timeout=10)
            with UnitOfWork() as uow:
                servico = ConnectionProfileService(ConnectionRepository(uow.session))
                resultado = servico.ensure_manual_profile(control_principal_ref="concorrente")
                uow.commit()
            retornos.append(resultado)
        except BaseException as erro:  # noqa: BLE001
            erros.append(erro)

    fios = [threading.Thread(target=chamar) for _ in range(4)]
    for fio in fios:
        fio.start()
    for fio in fios:
        fio.join(timeout=30)

    assert not erros, f"IntegrityError exposto ao chamador: {erros}"
    assert len(retornos) == 4
    assert len({r.profile.connection_id for r in retornos}) == 1
    assert sum(1 for r in retornos if r.created) == 1, "mais de uma criação efetiva"

    with engine.connect() as conexao:
        linhas = conexao.execute(
            sa.text(
                "SELECT id, endpoint_ref, state, method FROM connection_profiles "
                "WHERE control_principal_ref = 'concorrente'"
            )
        ).all()
    assert len(linhas) == 1
    assert linhas[0].endpoint_ref is None
    assert linhas[0].state == "available"
    assert linhas[0].method == "manual_handoff"


# --- 11. Attempt legada permanece sem recibo --------------------------------


def test_e741p11_attempt_legada_permanece_sem_recibo_e_nada_e_fabricado() -> None:
    """`LEGACY_ATTEMPT_WITHOUT_RECEIPT != FABRICATE_HISTORY`.

    Uma Attempt anterior à E7.4-1 é simulada apagando **apenas** o
    recibo, com o trigger desabilitado — o que a deixa exatamente no
    estado em que uma Attempt histórica está. Nenhum caminho do sistema
    a preenche depois: atribuir uma rota que ninguém observou seria
    inventar história.
    """
    schedule_id, step_id = _preparar()
    _, saida = _exportar(schedule_id, step_id)
    legada = saida.exported.attempt_id

    with engine.begin() as conexao:
        conexao.execute(sa.text("ALTER TABLE connection_execution_receipts DISABLE TRIGGER USER"))
        conexao.execute(
            sa.text("DELETE FROM connection_execution_receipts WHERE attempt_id = :aid"),
            {"aid": legada},
        )
        conexao.execute(sa.text("ALTER TABLE connection_execution_receipts ENABLE TRIGGER USER"))
    assert _recibos_de_conexao() == []

    # Nenhum caminho público reconstrói a atribuição da legada: listar
    # perfis, que é a leitura mais próxima disso, não a alcança.
    with UnitOfWork() as uow:
        ctx = _Contexto(uow)
        vista = ctx.perfis.list_profiles(control_principal_ref="p")
        uow.commit()
    assert len(vista) == 1, "o perfil manual continua único"

    recibos = _recibos_de_conexao()
    assert recibos == [], "algo preencheu a Attempt legada retroativamente"
