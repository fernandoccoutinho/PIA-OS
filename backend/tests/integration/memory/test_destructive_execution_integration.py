"""
Integração real da composição destrutiva (`E4.9.9.d`).

```text
FLUSHED_CONSUMPTION != DURABLE_CONSUMPTION
EFFECT_BEFORE_CONSUMPTION_COMMIT = FORBIDDEN
```

A prova central desta fatia **não pode** ser feita com dublê: exige uma
segunda sessão PostgreSQL, aberta de fora da transação do serviço,
observando o estado no instante exato em que o adaptador de efeito é
chamado. Um `flush` sem commit seria invisível para ela — e é
precisamente essa a diferença que o contrato at-most-once exige.
"""

import uuid
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.database import migrations
from app.database.engine import engine
from app.database.health import check_database_health
from app.database.session import SessionLocal
from app.memory.errors.exceptions import (
    ApprovalRecordNotUsableError,
    DestructiveExecutionUnknownMaterialStateError,
    ErasureReceiptNotPersistedError,
)
from app.memory.models.approval_lifecycle_enums import (
    ApprovalLifecycleState,
    ApprovalUsageRefusalReason,
)
from app.memory.models.erasure_effect_enums import MaterialAttemptRefusalReason
from app.memory.models.erasure_enums import ErasureOutcome, ErasureTargetClass
from app.memory.repositories.approval_record_repository import ApprovalRecordRepository
from app.memory.schemas.destructive_execution import (
    ApprovalConsumptionRefusal,
    DestructiveExecutionReport,
    DestructiveExecutionRequest,
)
from app.memory.schemas.erasure_effect import (
    MaterialAttemptNotStarted,
    ObservedAttemptResult,
)
from app.memory.services.destructive_execution_service import DestructiveExecutionService
from app.repositories.exceptions import TransactionError
from app.repositories.unit_of_work import UnitOfWork
from tests.helpers.destructive_execution import (
    SUJEITO_A,
    SUJEITO_B,
    descritor,
    envelope,
    instante,
    procedencia,
    referencia,
    resolucao,
    snapshot,
)


def _disponivel() -> bool:
    return check_database_health().available


pytestmark = pytest.mark.skipif(
    not _disponivel(),
    reason="PostgreSQL real indisponível — a composição exige commit durável observável.",
)


@pytest.fixture(autouse=True)
def _limpar():
    migrations.upgrade("head")
    _truncar()
    yield
    _truncar()


def _truncar() -> None:
    with engine.begin() as conn:
        conn.execute(sa.text("TRUNCATE approval_records CASCADE"))
        conn.execute(sa.text("TRUNCATE erasure_records CASCADE"))


def _persistir(aprovado) -> None:  # noqa: ANN001
    with Session(engine) as sessao:
        ApprovalRecordRepository(sessao).append_approved(aprovado)
        sessao.commit()


def _estado_em_sessao_nova(approval_id: uuid.UUID) -> str | None:
    """Lê o ciclo de vida numa SEGUNDA sessão, fora da transação do serviço.

    A comparação é contra `.name`, não `.value`: a coluna guarda o NOME
    do membro. É a mesma assimetria de serialização de enums que a E4.4
    mediu na E3 e que a E4.5.1 pagou para aprender — o token persistido é
    lido **sem normalização**.
    """
    with Session(engine) as observadora:
        return observadora.execute(
            sa.select(sa.column("state"))
            .select_from(sa.table("approval_records"))
            .where(sa.column("id") == approval_id)
        ).scalar_one_or_none()


def _recibos() -> list[tuple[str, str, str]]:
    with Session(engine) as sessao:
        return [
            (linha[0], linha[1], linha[2])
            for linha in sessao.execute(
                sa.text(
                    "SELECT subject_identifier, outcome, governance_rule_id "
                    "FROM erasure_records ORDER BY attempted_at, id"
                )
            )
        ]


class ResolvedorFixo:
    def __init__(self, descritores) -> None:  # noqa: ANN001
        self._descritores = list(descritores)
        self.chamadas = 0

    def resolve_target(self, reference):  # noqa: ANN001, ANN201
        self.chamadas += 1
        return self._descritores.pop(0)


class EfeitoObservador:
    """Observa o banco por uma SEGUNDA sessão no instante da tentativa.

    O registro é feito **dentro** de `attempt_effect`, e não antes nem
    depois: o que importa provar é o estado no momento em que o efeito
    material poderia começar.
    """

    def __init__(self, desfechos) -> None:  # noqa: ANN001
        self._desfechos = list(desfechos)
        self.estados_observados: list[str | None] = []
        self.recibos_no_instante: list[int] = []
        self.chamadas = 0

    def attempt_effect(self, request):  # noqa: ANN001, ANN201
        self.chamadas += 1
        self.estados_observados.append(_estado_em_sessao_nova(request.authorization.approval_id))
        with Session(engine) as observadora:
            self.recibos_no_instante.append(
                observadora.execute(sa.text("SELECT count(*) FROM erasure_records")).scalar_one()
            )
        proximo = self._desfechos.pop(0)
        if isinstance(proximo, BaseException):
            raise proximo
        return proximo


def _observado(
    aprovacao: uuid.UUID,
    *,
    sujeito: uuid.UUID = SUJEITO_A,
    outcome: ErasureOutcome = ErasureOutcome.SUCCEEDED,
) -> ObservedAttemptResult:
    agora = datetime.now(UTC).replace(microsecond=0)
    return ObservedAttemptResult(
        approval_id=aprovacao,
        subject_coid=sujeito,
        target_class=ErasureTargetClass.PIA_MANAGED_ARTIFACT,
        outcome=outcome,
        executor_ref="executor:integracao",
        attempted_at=agora,
        completed_at=agora,
        failure_code=None if outcome is ErasureOutcome.SUCCEEDED else "provider_denied",
    )


def _servico(descritores, desfechos, *, fabrica=None):  # noqa: ANN001, ANN202
    efeito = EfeitoObservador(desfechos)
    servico = DestructiveExecutionService(
        unit_of_work_factory=fabrica or UnitOfWork,
        target_resolver=ResolvedorFixo(descritores),
        effect_port=efeito,
    )
    return servico, efeito


# ----------------------------------------------------------------------
# A prova central — consumo durável antes do efeito
# ----------------------------------------------------------------------


def test_i01_segunda_sessao_ve_consumed_antes_do_efeito():
    """`FLUSHED_CONSUMPTION != DURABLE_CONSUMPTION`."""
    aprovado = envelope()
    _persistir(aprovado)
    assert _estado_em_sessao_nova(aprovado.approval_id) == ApprovalLifecycleState.ACTIVE.name

    servico, efeito = _servico([descritor()], [_observado(aprovado.approval_id)])
    resultado = servico.execute(DestructiveExecutionRequest(aprovado, (referencia(),)))

    assert isinstance(resultado, DestructiveExecutionReport)
    assert efeito.estados_observados == [ApprovalLifecycleState.CONSUMED.name]


def test_i02_nenhum_recibo_existe_no_instante_da_tentativa():
    """O recibo nasce DEPOIS do desfecho observado, nunca antes."""
    aprovado = envelope()
    _persistir(aprovado)
    servico, efeito = _servico([descritor()], [_observado(aprovado.approval_id)])
    servico.execute(DestructiveExecutionRequest(aprovado, (referencia(),)))

    assert efeito.recibos_no_instante == [0]
    assert len(_recibos()) == 1


def test_i03_o_recibo_commita_em_transacao_propria_por_alvo():
    """Um lote de dois: o segundo alvo já vê o recibo do primeiro."""
    aprovado = envelope(alvos=(snapshot(), snapshot(subject_coid=SUJEITO_B, origin=procedencia(1))))
    _persistir(aprovado)
    servico, efeito = _servico(
        [descritor(), descritor(subject_coid=SUJEITO_B, origin=procedencia(1))],
        [
            _observado(aprovado.approval_id),
            _observado(aprovado.approval_id, sujeito=SUJEITO_B),
        ],
    )
    servico.execute(
        DestructiveExecutionRequest(
            aprovado,
            (referencia(), referencia(subject_coid=SUJEITO_B, origin=procedencia(1))),
        )
    )
    assert efeito.recibos_no_instante == [0, 1]
    assert len(_recibos()) == 2


def test_i04_falha_no_commit_do_consumo_impede_qualquer_efeito():
    """Se o commit falhar, nenhum efeito pode ser chamado."""
    aprovado = envelope()
    _persistir(aprovado)

    class UoWQueFalhaNoCommit(UnitOfWork):
        def commit(self) -> None:
            raise TransactionError("commit do consumo falhou")

    servico, efeito = _servico(
        [descritor()], [_observado(aprovado.approval_id)], fabrica=UoWQueFalhaNoCommit
    )
    with pytest.raises(TransactionError):
        servico.execute(DestructiveExecutionRequest(aprovado, (referencia(),)))

    assert efeito.chamadas == 0
    assert _recibos() == []
    # Sem commit, a UoW reverte: a aprovação continua ACTIVE e utilizável.
    assert _estado_em_sessao_nova(aprovado.approval_id) == ApprovalLifecycleState.ACTIVE.name


def test_i05_replay_recusa_sem_segunda_chamada_ao_efeito():
    """`REPLAY_WITH_SAME_APPROVAL = REFUSED`."""
    aprovado = envelope()
    _persistir(aprovado)

    primeiro, efeito_um = _servico([descritor()], [_observado(aprovado.approval_id)])
    assert isinstance(
        primeiro.execute(DestructiveExecutionRequest(aprovado, (referencia(),))),
        DestructiveExecutionReport,
    )

    segundo, efeito_dois = _servico([descritor()], [_observado(aprovado.approval_id)])
    resultado = segundo.execute(DestructiveExecutionRequest(aprovado, (referencia(),)))

    assert isinstance(resultado, ApprovalConsumptionRefusal)
    assert resultado.reason is ApprovalUsageRefusalReason.ALREADY_CONSUMED
    assert efeito_um.chamadas == 1
    assert efeito_dois.chamadas == 0
    assert len(_recibos()) == 1


def test_i06_aprovacao_vencida_nao_chega_ao_efeito():
    """Envelope legítimo cuja janela já passou — nada é adulterado.

    A trigger da E4.9.9.a torna `expires_at` imutável depois do INSERT,
    então mexer na linha seria impossível **e** seria a adulteração que
    o projeto proíbe. O envelope nasce vencido por construção.
    """
    from datetime import timedelta

    aprovado = envelope(confirmado_ha_horas=5, janela=timedelta(hours=1))
    _persistir(aprovado)

    servico, efeito = _servico([descritor()], [_observado(aprovado.approval_id)])
    resultado = servico.execute(DestructiveExecutionRequest(aprovado, (referencia(),)))
    assert isinstance(resultado, ApprovalConsumptionRefusal)
    assert resultado.reason is ApprovalUsageRefusalReason.EXPIRED
    assert efeito.chamadas == 0


def test_i07_aprovacao_ausente_recusa_antes_do_efeito():
    """Envelope válido que nunca foi persistido — nada a consumir."""
    aprovado = envelope()
    servico, efeito = _servico([descritor()], [_observado(aprovado.approval_id)])
    resultado = servico.execute(DestructiveExecutionRequest(aprovado, (referencia(),)))
    assert isinstance(resultado, ApprovalConsumptionRefusal)
    assert resultado.reason is ApprovalUsageRefusalReason.NOT_FOUND
    assert efeito.chamadas == 0


# ----------------------------------------------------------------------
# Fase A contra o banco — nada é escrito
# ----------------------------------------------------------------------


def test_i08_divergencia_de_protecao_nao_consome_no_banco():
    """Proteção alterada entre aprovação e re-resolução."""
    from app.memory.models.target_resolution_enums import LegacyProtectionState

    aprovado = envelope(alvos=(snapshot(),))
    _persistir(aprovado)
    servico, efeito = _servico(
        [descritor(legacy_protection_state=LegacyProtectionState.PROTECTED)], []
    )
    servico.execute(DestructiveExecutionRequest(aprovado, (referencia(),)))

    assert _estado_em_sessao_nova(aprovado.approval_id) == ApprovalLifecycleState.ACTIVE.name
    assert efeito.chamadas == 0
    assert _recibos() == []


def test_i09_version_etag_alterado_nao_consome_no_banco():
    aprovado = envelope()
    _persistir(aprovado)
    servico, efeito = _servico([descritor(version_etag='W/"v2"')], [])
    servico.execute(DestructiveExecutionRequest(aprovado, (referencia(),)))

    assert _estado_em_sessao_nova(aprovado.approval_id) == ApprovalLifecycleState.ACTIVE.name
    assert efeito.chamadas == 0
    assert _recibos() == []


# ----------------------------------------------------------------------
# Fase C contra o banco
# ----------------------------------------------------------------------


def test_i10_nao_tentativa_nao_grava_recibo_e_o_lote_segue():
    aprovado = envelope(alvos=(snapshot(), snapshot(subject_coid=SUJEITO_B, origin=procedencia(1))))
    _persistir(aprovado)
    servico, _ = _servico(
        [descritor(), descritor(subject_coid=SUJEITO_B, origin=procedencia(1))],
        [
            MaterialAttemptNotStarted(
                approval_id=aprovado.approval_id,
                subject_coid=SUJEITO_A,
                reason=MaterialAttemptRefusalReason.OPERATION_NOT_SUPPORTED,
                observed_at=instante(0),
            ),
            _observado(aprovado.approval_id, sujeito=SUJEITO_B),
        ],
    )
    resultado = servico.execute(
        DestructiveExecutionRequest(
            aprovado,
            (referencia(), referencia(subject_coid=SUJEITO_B, origin=procedencia(1))),
        )
    )
    assert resultado.not_attempted == 1
    assert [linha[0] for linha in _recibos()] == [str(SUJEITO_B)]


@pytest.mark.parametrize(
    "desfecho", [ErasureOutcome.SUCCEEDED, ErasureOutcome.FAILED, ErasureOutcome.PARTIAL]
)
def test_i11_cada_desfecho_observado_grava_um_recibo_coerente(desfecho):
    aprovado = envelope()
    _persistir(aprovado)
    servico, _ = _servico([descritor()], [_observado(aprovado.approval_id, outcome=desfecho)])
    resultado = servico.execute(DestructiveExecutionRequest(aprovado, (referencia(),)))

    persistidos = _recibos()
    assert len(persistidos) == 1
    assert persistidos[0][1] == desfecho.value
    assert len(resultado.receipts_persisted) == 1


def test_i12_o_identificador_textual_de_regra_persiste_literal():
    """`OPAQUE_RULE_REFERENCE != UUID` — do serviço à coluna."""
    regra = "rule-Ação-2026/v1"
    aprovado = envelope(governanca=resolucao(matched_rule_id=regra))
    _persistir(aprovado)
    servico, _ = _servico([descritor()], [_observado(aprovado.approval_id)])
    servico.execute(DestructiveExecutionRequest(aprovado, (referencia(),)))
    assert _recibos()[0][2] == regra


def test_i13_excecao_da_porta_preserva_consumo_e_recibos_anteriores():
    """`EFFECT_EXCEPTION -> UNKNOWN_STATE, NEVER_INVENTED_RECEIPT`."""
    aprovado = envelope(alvos=(snapshot(), snapshot(subject_coid=SUJEITO_B, origin=procedencia(1))))
    _persistir(aprovado)
    servico, _ = _servico(
        [descritor(), descritor(subject_coid=SUJEITO_B, origin=procedencia(1))],
        [_observado(aprovado.approval_id), TimeoutError("provedor não respondeu")],
    )
    with pytest.raises(DestructiveExecutionUnknownMaterialStateError) as capturado:
        servico.execute(
            DestructiveExecutionRequest(
                aprovado,
                (referencia(), referencia(subject_coid=SUJEITO_B, origin=procedencia(1))),
            )
        )

    assert _estado_em_sessao_nova(aprovado.approval_id) == ApprovalLifecycleState.CONSUMED.name
    assert [linha[0] for linha in _recibos()] == [str(SUJEITO_A)]
    assert capturado.value.evidence.receipts_persisted == 1


def test_i14_falha_no_commit_do_recibo_nao_alega_recibo():
    """Nem alega recibo, nem desfaz o efeito observado."""
    aprovado = envelope()
    _persistir(aprovado)

    class UoWQueFalhaNoSegundoCommit(UnitOfWork):
        commits = 0

        def commit(self) -> None:
            type(self).commits += 1
            if type(self).commits >= 2:
                raise TransactionError("commit do recibo falhou")
            super().commit()

    servico, efeito = _servico(
        [descritor()],
        [_observado(aprovado.approval_id)],
        fabrica=UoWQueFalhaNoSegundoCommit,
    )
    with pytest.raises(ErasureReceiptNotPersistedError) as capturado:
        servico.execute(DestructiveExecutionRequest(aprovado, (referencia(),)))

    assert capturado.value.outcome is ErasureOutcome.SUCCEEDED
    assert efeito.chamadas == 1
    assert _recibos() == []
    # O consumo NÃO é desfeito: o efeito ocorreu.
    assert _estado_em_sessao_nova(aprovado.approval_id) == ApprovalLifecycleState.CONSUMED.name


# ----------------------------------------------------------------------
# SQL bruto e migration
# ----------------------------------------------------------------------


def test_i15_sql_bruto_nao_altera_recibo_nem_aprovacao_consumida():
    aprovado = envelope()
    _persistir(aprovado)
    servico, _ = _servico([descritor()], [_observado(aprovado.approval_id)])
    servico.execute(DestructiveExecutionRequest(aprovado, (referencia(),)))

    for comando in (
        "UPDATE erasure_records SET outcome = 'failed'",
        "DELETE FROM erasure_records",
        "UPDATE approval_records SET state = 'ACTIVE'",
        "DELETE FROM approval_records",
    ):
        with pytest.raises(Exception), engine.begin() as conn:  # noqa: B017, PT011
            conn.execute(sa.text(comando))

    assert len(_recibos()) == 1
    assert _estado_em_sessao_nova(aprovado.approval_id) == ApprovalLifecycleState.CONSUMED.name


def test_i16_single_head_e_round_trip_da_migration():
    assert migrations.head_revision() == "f8a91c2d4e60"
    assert migrations.current_revision() == "f8a91c2d4e60"
    migrations.downgrade("a1f7c2d40e93")
    migrations.upgrade("head")
    assert migrations.current_revision() == "f8a91c2d4e60"


def test_i17_a_conversao_preserva_o_uuid_literal_existente():
    """Um recibo antigo com UUID continua citando exatamente aquele texto."""
    antigo = "3fa85f64-5717-4562-b3fc-2c963f66afa6"
    with engine.begin() as conn:
        conn.execute(
            sa.text(
                "INSERT INTO erasure_records (id, subject_identifier, target_class, "
                "scope_token, outcome, governance_policy_id, governance_policy_key, "
                "governance_policy_version, governance_rule_id, governance_resolution_ref, "
                "approval_ref, executor_ref, attempted_at, completed_at, created_at, "
                "updated_at) VALUES (gen_random_uuid(), 'antigo', 'pia_managed_artifact', "
                "'move_to_trash', 'succeeded', gen_random_uuid(), 'gov', 1, :regra, 'res', "
                "'appr', 'exec', now(), now(), now(), now())"
            ),
            {"regra": antigo},
        )

    migrations.downgrade("a1f7c2d40e93")
    with Session(engine) as sessao:
        na_volta = sessao.execute(
            sa.text("SELECT governance_rule_id::text FROM erasure_records")
        ).scalar_one()
    assert na_volta == antigo

    migrations.upgrade("head")
    with Session(engine) as sessao:
        de_novo = sessao.execute(
            sa.text("SELECT governance_rule_id FROM erasure_records")
        ).scalar_one()
    assert de_novo == antigo


def test_i18_downgrade_recusa_antes_de_alterar_o_schema():
    """`REFUSE_BEFORE_ALTER, NEVER_MID_MIGRATION`.

    Com dado textual não-UUID, a volta é impossível sem destruir a
    identidade da regra. A migration recusa **antes** de qualquer DDL, e
    o teste prova que schema e dados ficam intactos.
    """
    aprovado = envelope(governanca=resolucao(matched_rule_id="rule-1"))
    _persistir(aprovado)
    servico, _ = _servico([descritor()], [_observado(aprovado.approval_id)])
    servico.execute(DestructiveExecutionRequest(aprovado, (referencia(),)))

    with pytest.raises(RuntimeError, match="downgrade recusado"):
        migrations.downgrade("a1f7c2d40e93")

    with Session(engine) as sessao:
        tipo = sessao.execute(
            sa.text(
                "SELECT data_type FROM information_schema.columns WHERE "
                "table_name = 'erasure_records' AND column_name = 'governance_rule_id'"
            )
        ).scalar_one()
        restricao = sessao.execute(
            sa.text(
                "SELECT count(*) FROM pg_constraint WHERE conname = "
                "'ck_erasure_records_governance_rule_id_not_blank'"
            )
        ).scalar_one()
    assert tipo == "character varying"
    assert restricao == 1
    assert _recibos()[0][2] == "rule-1"
    assert migrations.current_revision() == "f8a91c2d4e60"


def test_i19_nenhuma_funcao_ou_trigger_orfa_apos_o_round_trip():
    migrations.downgrade("a1f7c2d40e93")
    with Session(engine) as sessao:
        orfas = sessao.execute(
            sa.text(
                "SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON p.pronamespace = n.oid "
                "WHERE n.nspname = 'public' AND proname LIKE '%rule_id%'"
            )
        ).scalar_one()
    assert orfas == 0
    migrations.upgrade("head")


def test_i20_o_consumo_e_o_recibo_vivem_em_transacoes_distintas():
    """Transação única faria a falha do último alvo descartar os anteriores."""
    aprovado = envelope()
    _persistir(aprovado)

    abertas: list[int] = []

    class UoWContada(UnitOfWork):
        def __enter__(self):  # noqa: ANN204
            abertas.append(1)
            return super().__enter__()

    servico, _ = _servico([descritor()], [_observado(aprovado.approval_id)], fabrica=UoWContada)
    servico.execute(DestructiveExecutionRequest(aprovado, (referencia(),)))
    assert sum(abertas) == 2


def test_i21_consumo_concorrente_produz_um_unico_efeito():
    """Duas execuções da MESMA aprovação: um vencedor, um efeito.

    Sem `sleep` e sem probabilidade — a segunda execução começa depois
    que a primeira commitou, e o comando atômico da E4.9.9.a decide.
    """
    aprovado = envelope()
    _persistir(aprovado)

    chamadas: list[int] = []

    class EfeitoContado(EfeitoObservador):
        def attempt_effect(self, request):  # noqa: ANN001, ANN201
            chamadas.append(1)
            return super().attempt_effect(request)

    for _ in range(2):
        servico = DestructiveExecutionService(
            unit_of_work_factory=UnitOfWork,
            target_resolver=ResolvedorFixo([descritor()]),
            effect_port=EfeitoContado([_observado(aprovado.approval_id)]),
        )
        servico.execute(DestructiveExecutionRequest(aprovado, (referencia(),)))

    assert sum(chamadas) == 1
    assert len(_recibos()) == 1


def test_i22_o_repositorio_de_aprovacao_recusa_consumo_direto_apos_uso():
    """Guarda de premissa: a atomicidade é do repositório, não do serviço."""
    aprovado = envelope()
    _persistir(aprovado)
    with UnitOfWork() as uow:
        ApprovalRecordRepository(uow.session).consume_once(aprovado)
        uow.commit()

    with UnitOfWork() as uow, pytest.raises(ApprovalRecordNotUsableError):
        ApprovalRecordRepository(uow.session).consume_once(aprovado)


def test_i23_nenhuma_escrita_ocorre_quando_a_fase_a_recusa():
    """Censo de linhas antes e depois — `DATABASE_WRITES = 0`."""
    aprovado = envelope()
    _persistir(aprovado)

    def _censo() -> tuple[int, int]:
        with Session(engine) as sessao:
            return (
                sessao.execute(sa.text("SELECT count(*) FROM approval_records")).scalar_one(),
                sessao.execute(sa.text("SELECT count(*) FROM erasure_records")).scalar_one(),
            )

    antes = _censo()
    servico, _ = _servico([descritor(version_etag='W/"v9"')], [])
    servico.execute(DestructiveExecutionRequest(aprovado, (referencia(),)))
    assert _censo() == antes


def test_i24_sessao_do_servico_nao_vaza_entre_transacoes():
    """Repositórios são instanciados DENTRO de cada UoW.

    ## Manutenção de instrumento (autorizada na E4.10)

    ```text
    OBJECT_IDENTITY_OVER_TIME != MEMORY_ADDRESS
    ```

    A versão original media `id(resultado.session)` e comparava o
    tamanho do conjunto. `id()` é endereço, e endereço é **reciclável**:
    quando a primeira `Session` era coletada antes de a segunda existir,
    o alocador devolvia o mesmo endereço e duas sessões genuinamente
    distintas produziam `id` idêntico. MEDIDO: 1 falha em 10 execuções
    isoladas.

    A correção guarda **referência forte** às duas sessões — o que
    impede a coleta durante a medição — e compara identidade real com
    `is not`. Nada de `id()`, `hash`, endereço ou coleta manual: são
    todas aproximações do que se quer afirmar.

    O comportamento sob teste nunca esteve em questão. O defeito era do
    instrumento.
    """
    aprovado = envelope()
    _persistir(aprovado)
    sessoes: list[Session] = []

    class UoWRegistrada(UnitOfWork):
        def __enter__(self):  # noqa: ANN204
            resultado = super().__enter__()
            sessoes.append(resultado.session)
            return resultado

    servico, _ = _servico([descritor()], [_observado(aprovado.approval_id)], fabrica=UoWRegistrada)
    servico.execute(DestructiveExecutionRequest(aprovado, (referencia(),)))
    assert len(sessoes) == 2
    assert sessoes[0] is not sessoes[1]


def test_i25_o_recibo_persistido_nao_contem_localizador():
    """Censo textual da linha inteira, não só dos campos esperados."""
    marcador = "LOCALIZADOR-SECRETO-91af"
    aprovado = envelope()
    _persistir(aprovado)
    servico, _ = _servico(
        [descritor(transient_locator=f"s3://pia-storage/w1/{marcador}")],
        [_observado(aprovado.approval_id)],
    )
    servico.execute(DestructiveExecutionRequest(aprovado, (referencia(),)))

    with Session(engine) as sessao:
        linha = sessao.execute(
            sa.text("SELECT erasure_records::text FROM erasure_records")
        ).scalar_one()
    assert marcador not in linha


def test_i26_sessionlocal_continua_sendo_a_fabrica_padrao():
    """Guarda de premissa dos testes acima: `UnitOfWork` usa `SessionLocal`."""
    with UnitOfWork() as uow:
        assert isinstance(uow.session, SessionLocal().__class__)
