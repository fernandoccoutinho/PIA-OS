"""
A composição destrutiva, medida com dublês observacionais (`E4.9.9.d`).

```text
A  resolver todos e comparar os sete campos    sem escrita alguma
B  consume_once em UoW exclusivo e COMMIT      antes de qualquer efeito
C  attempt_effect por alvo                     recibo só após observação
```

Os dublês **contam** chamadas e escritas. Um teste que só verificasse o
valor devolvido não distinguiria "não consumiu" de "consumiu e voltou
atrás", e é exatamente essa distinção que a fase A existe para garantir.
"""

import uuid
from datetime import UTC, datetime

import pytest

from app.memory.models.approval_enums import DestructiveOperation
from app.memory.models.approval_lifecycle_enums import ApprovalUsageRefusalReason
from app.memory.models.destructive_execution_enums import (
    AdapterContractViolation,
    PreConsumptionRefusalReason,
    SnapshotDivergenceField,
)
from app.memory.models.erasure_effect_enums import MaterialAttemptRefusalReason
from app.memory.models.erasure_enums import ErasureOutcome, ErasureTargetClass
from app.memory.models.governance_enums import GovernanceOutcome
from app.memory.models.target_resolution_enums import (
    LegacyProtectionState,
    ReferenceOrigin,
    TargetResolutionRefusalReason,
)
from app.memory.schemas.destructive_approval import OPERACAO_DE_GOVERNANCA
from app.memory.schemas.destructive_execution import (
    ApprovalConsumptionRefusal,
    DestructiveExecutionRequest,
    PreConsumptionRefusal,
)
from app.memory.schemas.erasure_effect import (
    MaterialAttemptNotStarted,
    ObservedAttemptResult,
)
from app.memory.schemas.erasure_target import (
    ControlScope,
    CustodyNamespace,
    ReferenceProvenance,
    TargetResolutionRefusal,
)
from app.memory.schemas.governance import GovernanceResolution
from app.memory.services.destructive_execution_service import (
    CAMPOS_DO_BINDING,
    DestructiveExecutionService,
)
from tests.helpers.destructive_execution import (
    DOMINIO,
    FINALIDADE,
    POLICY_ID,
    PRINCIPAL,
    SUJEITO_A,
    SUJEITO_B,
    TENANT,
    WORKSPACE,
    custodia,
    descritor,
    envelope,
    instante,
    procedencia,
    referencia,
    resolucao,
    snapshot,
)

MARCADOR = "SEGREDO-COMPOSTO-4c19"


# ----------------------------------------------------------------------
# Dublês — observacionais, e que CONTAM
# ----------------------------------------------------------------------


class ResolvedorDuble:
    """Devolve resultados programados e registra o que foi pedido.

    Não escreve, não persiste e não tem sessão — `RESOLUTION_IS_
    OBSERVATIONAL`. A contagem existe para que nenhuma prova seja vazia.
    """

    def __init__(self, resultados: list[object]) -> None:
        self._resultados = list(resultados)
        self.chamadas: list[uuid.UUID] = []

    def resolve_target(self, reference):  # noqa: ANN001, ANN201
        self.chamadas.append(reference.subject_coid)
        return self._resultados.pop(0)


class EfeitoDuble:
    """Devolve desfechos programados; uma entrada pode ser uma exceção."""

    def __init__(self, desfechos: list[object]) -> None:
        self._desfechos = list(desfechos)
        self.chamadas: list[uuid.UUID] = []

    def attempt_effect(self, request):  # noqa: ANN001, ANN201
        self.chamadas.append(request.descriptor.subject_coid)
        proximo = self._desfechos.pop(0)
        if isinstance(proximo, BaseException):
            raise proximo
        return proximo


class RepositorioFalso:
    """Registra transações abertas e commitadas, sem tocar em banco."""

    def __init__(self) -> None:
        self.aberturas = 0
        self.commits = 0
        self.consumos: list[uuid.UUID] = []
        self.recibos: list[object] = []


class UoWFalsa:
    def __init__(self, registro: RepositorioFalso) -> None:
        self._registro = registro
        self.session = registro

    def __enter__(self):  # noqa: ANN204
        self._registro.aberturas += 1
        return self

    def __exit__(self, *_: object) -> bool:
        return False

    def commit(self) -> None:
        self._registro.commits += 1


def observado(
    aprovacao: uuid.UUID,
    *,
    sujeito: uuid.UUID = SUJEITO_A,
    outcome: ErasureOutcome = ErasureOutcome.SUCCEEDED,
    target_class: ErasureTargetClass = ErasureTargetClass.PIA_MANAGED_ARTIFACT,
    executor: str = "executor:sandbox",
) -> ObservedAttemptResult:
    inicio = datetime(2026, 8, 19, 10, 0, tzinfo=UTC)
    return ObservedAttemptResult(
        approval_id=aprovacao,
        subject_coid=sujeito,
        target_class=target_class,
        outcome=outcome,
        executor_ref=executor,
        attempted_at=inicio,
        completed_at=inicio,
        failure_code=None if outcome is ErasureOutcome.SUCCEEDED else "provider_denied",
    )


def nao_iniciada(aprovacao: uuid.UUID, *, sujeito: uuid.UUID = SUJEITO_A):  # noqa: ANN201
    return MaterialAttemptNotStarted(
        approval_id=aprovacao,
        subject_coid=sujeito,
        reason=MaterialAttemptRefusalReason.ADAPTER_UNAVAILABLE,
        observed_at=instante(0),
    )


@pytest.fixture
def montar(monkeypatch):  # noqa: ANN201
    """Monta o serviço com dublês e intercepta os dois repositórios.

    A interceptação é dos **repositórios**, não do serviço: o fluxo real
    do serviço é executado inteiro, e o que se substitui é a fronteira de
    persistência — que os testes de integração exercitam de verdade.
    """

    def _montar(resolucoes, desfechos, *, consumo=None, recibo=None):  # noqa: ANN001, ANN202
        registro = RepositorioFalso()
        estado: dict[str, object] = {"consumido_em": instante(0)}

        class ConsumoFalso:
            def __init__(self, sessao):  # noqa: ANN001
                pass

            def consume_once(self, expected):  # noqa: ANN001, ANN202
                registro.consumos.append(expected.approval_id)
                if consumo is not None:
                    raise consumo

                class Linha:
                    consumed_at = estado["consumido_em"]

                return Linha()

        class ReciboFalso:
            def __init__(self, sessao):  # noqa: ANN001
                pass

            def append_observed(self, entrada):  # noqa: ANN001, ANN202
                registro.recibos.append(entrada)
                if recibo is not None:
                    raise recibo

                class Linha:
                    id = uuid.uuid4()

                return Linha()

        modulo = "app.memory.services.destructive_execution_service"
        monkeypatch.setattr(f"{modulo}.ApprovalRecordRepository", ConsumoFalso)
        monkeypatch.setattr(f"{modulo}.ErasureRecordRepository", ReciboFalso)

        resolvedor = ResolvedorDuble(resolucoes)
        efeito = EfeitoDuble(desfechos)
        servico = DestructiveExecutionService(
            unit_of_work_factory=lambda: UoWFalsa(registro),
            target_resolver=resolvedor,
            effect_port=efeito,
        )
        return servico, resolvedor, efeito, registro

    return _montar


def pedido(aprovado=None, referencias=None):  # noqa: ANN001, ANN201
    aprovado = aprovado or envelope()
    return DestructiveExecutionRequest(aprovado, referencias or (referencia(),))


# ----------------------------------------------------------------------
# Construtor
# ----------------------------------------------------------------------


def test_s01_dependencias_sao_injetadas_e_tipadas():
    with pytest.raises(TypeError, match="unit_of_work_factory"):
        DestructiveExecutionService(
            unit_of_work_factory="fabrica",  # type: ignore[arg-type]
            target_resolver=ResolvedorDuble([]),
            effect_port=EfeitoDuble([]),
        )


def test_s02_porta_de_resolucao_incompativel_e_recusada():
    with pytest.raises(TypeError, match="ErasureTargetResolverPort"):
        DestructiveExecutionService(
            unit_of_work_factory=lambda: None,  # type: ignore[arg-type,return-value]
            target_resolver=object(),  # type: ignore[arg-type]
            effect_port=EfeitoDuble([]),
        )


def test_s03_porta_de_efeito_incompativel_e_recusada():
    with pytest.raises(TypeError, match="ErasureEffectPort"):
        DestructiveExecutionService(
            unit_of_work_factory=lambda: None,  # type: ignore[arg-type,return-value]
            target_resolver=ResolvedorDuble([]),
            effect_port=object(),  # type: ignore[arg-type]
        )


def test_s04_execute_recusa_entrada_nao_tipada(montar):
    servico, _, efeito, registro = montar([], [])
    with pytest.raises(TypeError, match="DestructiveExecutionRequest"):
        servico.execute({"envelope": envelope()})
    assert registro.consumos == []
    assert efeito.chamadas == []


# ----------------------------------------------------------------------
# Fase A — nenhuma escrita, nenhum efeito, nenhum recibo
# ----------------------------------------------------------------------


def _sem_escrita(registro, efeito) -> None:
    """`NO_CONSUMPTION`, `NO_EFFECT`, `NO_RECEIPT` — as três medidas."""
    assert registro.consumos == []
    assert registro.commits == 0
    assert registro.recibos == []
    assert efeito.chamadas == []


def test_s05_cardinalidade_divergente_para_antes_de_tudo(montar):
    aprovado = envelope(alvos=(snapshot(),))
    servico, resolvedor, efeito, registro = montar([], [])
    resultado = servico.execute(
        pedido(aprovado, (referencia(), referencia(subject_coid=SUJEITO_B)))
    )
    assert isinstance(resultado, PreConsumptionRefusal)
    assert resultado.reason is PreConsumptionRefusalReason.BATCH_CARDINALITY_MISMATCH
    assert resolvedor.chamadas == []
    _sem_escrita(registro, efeito)


def test_s06_duplicata_de_sujeito_para_antes_de_resolver(montar):
    aprovado = envelope(alvos=(snapshot(), snapshot(subject_coid=SUJEITO_B, origin=procedencia(1))))
    servico, resolvedor, efeito, registro = montar([], [])
    resultado = servico.execute(pedido(aprovado, (referencia(), referencia())))
    assert resultado.reason is PreConsumptionRefusalReason.DUPLICATE_SUBJECT_IN_BATCH
    assert resultado.position == 1
    assert resolvedor.chamadas == []
    _sem_escrita(registro, efeito)


def test_s07_referencia_de_outro_sujeito_e_recusada(montar):
    servico, resolvedor, efeito, registro = montar([], [])
    resultado = servico.execute(pedido(referencias=(referencia(subject_coid=SUJEITO_B),)))
    assert resultado.reason is PreConsumptionRefusalReason.REFERENCE_DOES_NOT_MATCH_APPROVED_TARGET
    assert resolvedor.chamadas == []
    _sem_escrita(registro, efeito)


def test_s08_referencia_de_outro_controle_e_recusada(montar):
    servico, _, efeito, registro = montar([], [])
    outro = ControlScope(WORKSPACE, TENANT, "principal:outro")
    resultado = servico.execute(pedido(referencias=(referencia(control_scope=outro),)))
    assert resultado.reason is PreConsumptionRefusalReason.REFERENCE_DOES_NOT_MATCH_APPROVED_TARGET
    _sem_escrita(registro, efeito)


def test_s09_referencia_de_outra_origem_e_recusada(montar):
    servico, _, efeito, registro = montar([], [])
    outra = ReferenceProvenance(ReferenceOrigin.INPUT_REFS, 0)
    resultado = servico.execute(pedido(referencias=(referencia(origin=outra),)))
    assert resultado.reason is PreConsumptionRefusalReason.REFERENCE_DOES_NOT_MATCH_APPROVED_TARGET
    _sem_escrita(registro, efeito)


def test_s10_namespace_esperado_divergente_e_recusado(montar):
    servico, _, efeito, registro = montar([], [])
    resultado = servico.execute(
        pedido(referencias=(referencia(expected_namespace=custodia("workspace/w9/z")),))
    )
    assert resultado.reason is PreConsumptionRefusalReason.REFERENCE_DOES_NOT_MATCH_APPROVED_TARGET
    _sem_escrita(registro, efeito)


def test_s11_namespace_esperado_ausente_e_legitimo(montar):
    """A maior parte das referências da E3 não diz onde o conteúdo vive."""
    aprovado = envelope()
    servico, _, efeito, registro = montar([descritor()], [observado(aprovado.approval_id)])
    resultado = servico.execute(pedido(aprovado, (referencia(expected_namespace=None),)))
    assert resultado.attempts_observed == 1
    assert len(efeito.chamadas) == 1


class ResolucaoDeProveniencia(GovernanceResolution):
    """Subclasse **controlada** que alcança a segunda camada.

    ```text
    SECOND_LAYER_UNREACHABLE_BY_CANONICAL_ENVELOPE
    UNREACHABLE_TODAY != UNNECESSARY
    ```

    MEDIDO nesta fatia, e é um achado: `GovernanceResolution` já exige
    proveniência local completa quando o desfecho é `ADMISSIBLE`, e a
    proposta destrutiva exige `ADMISSIBLE`. Logo **nenhum envelope
    canônico** chega ao serviço com um dos quatro campos ausente, e a
    checagem da fase A é hoje inalcançável por essa via.

    Ela permanece porque é a camada que impede o recibo de citar uma
    regra inexistente: se a E4.3 relaxar a exigência amanhã, a composição
    não herda o relaxamento em silêncio — recusa antes do efeito. É a
    mesma disciplina que a E4.9.9.b aplicou à verificação de capacidade
    (`u15`/`u48`).

    Subclasse é **construção legítima**, não bypass: nenhum
    `object.__setattr__`, nenhum monkeypatch, nenhum estado que os
    construtores públicos recusariam por si.
    """

    def __post_init__(self) -> None:  # noqa: D105
        return


@pytest.mark.parametrize(
    "faltante",
    ["policy_id", "policy_key", "policy_version", "matched_rule_id"],
)
def test_s12_governanca_incompleta_recusa_na_fase_a(montar, faltante):
    """`MISSING_GOVERNANCE_PROVENANCE -> REFUSE_BEFORE_EFFECT`.

    Os quatro campos são opcionais no tipo e obrigatórios aqui, porque o
    recibo os cita. Completar com default gravaria uma proveniência que
    ninguém aplicou — e o recibo é append-only.
    """
    campos = {
        "policy_id": POLICY_ID,
        "policy_key": "gov.erasure",
        "policy_version": 3,
        "matched_rule_id": "rule-1",
    }
    campos[faltante] = None
    incompleta = ResolucaoDeProveniencia(
        outcome=GovernanceOutcome.ADMISSIBLE,
        operation=OPERACAO_DE_GOVERNANCA[DestructiveOperation.MOVE_TO_TRASH],
        context_domain_ids=(DOMINIO,),
        context_actor_ref=PRINCIPAL,
        context_purpose=FINALIDADE,
        safety_boundary_version=1,
        safety_rationale="titular pediu remoção",
        **campos,
    )
    aprovado = envelope(governanca=incompleta)
    servico, resolvedor, efeito, registro = montar([], [])
    resultado = servico.execute(pedido(aprovado))
    assert isinstance(resultado, PreConsumptionRefusal)
    assert resultado.reason is PreConsumptionRefusalReason.GOVERNANCE_PROVENANCE_INCOMPLETE
    assert resultado.position is None
    assert resolvedor.chamadas == []
    _sem_escrita(registro, efeito)


def test_s12_1_a_proveniencia_completa_e_exigida_pela_propria_e4_3():
    """Guarda de premissa do teste anterior — a primeira camada existe.

    Sem esta medição, `s12` poderia ser lido como prova de que a fase A é
    a única defesa. Ela é a segunda.
    """
    with pytest.raises(ValueError, match="proveniência"):
        resolucao(matched_rule_id=None)


def test_s13_recusa_de_resolucao_invalida_o_lote_inteiro(montar):
    """A recusa de UM alvo invalida o lote: não é o lote aprovado."""
    aprovado = envelope(alvos=(snapshot(), snapshot(subject_coid=SUJEITO_B, origin=procedencia(1))))
    recusa = TargetResolutionRefusal(
        reason=TargetResolutionRefusalReason.STALE_RESOLUTION,
        subject_coid=SUJEITO_B,
        origin=procedencia(1),
    )
    servico, resolvedor, efeito, registro = montar([descritor(), recusa], [])
    resultado = servico.execute(
        pedido(
            aprovado,
            (referencia(), referencia(subject_coid=SUJEITO_B, origin=procedencia(1))),
        )
    )
    assert resultado.reason is PreConsumptionRefusalReason.TARGET_RESOLUTION_REFUSED
    assert resultado.position == 1
    assert resultado.resolution_refusal is TargetResolutionRefusalReason.STALE_RESOLUTION
    assert len(resolvedor.chamadas) == 2
    _sem_escrita(registro, efeito)


# ----------------------------------------------------------------------
# Os sete campos do binding — bilateral
# ----------------------------------------------------------------------

DIVERGENCIAS = {
    SnapshotDivergenceField.TARGET_CLASS: {
        "target_class": ErasureTargetClass.AUTHORIZED_CONNECTOR_REFERENT
    },
    SnapshotDivergenceField.SUBJECT_COID: {"subject_coid": SUJEITO_B},
    SnapshotDivergenceField.CONTROL_SCOPE: {
        "control_scope": ControlScope(WORKSPACE, TENANT, "principal:outro")
    },
    SnapshotDivergenceField.CUSTODY_NAMESPACE: {
        "custody_namespace": CustodyNamespace("pia-storage", "workspace/w1/OUTRO")
    },
    SnapshotDivergenceField.ORIGIN: {"origin": ReferenceProvenance(ReferenceOrigin.INPUT_REFS, 0)},
    SnapshotDivergenceField.LEGACY_PROTECTION_STATE: {
        "legacy_protection_state": LegacyProtectionState.PROTECTED
    },
    SnapshotDivergenceField.VERSION_ETAG: {"version_etag": 'W/"v2"'},
}


@pytest.mark.parametrize("campo", list(DIVERGENCIAS))
def test_s14_cada_campo_do_binding_divergente_recusa_antes_do_consumo(montar, campo):
    """Sete campos, sete divergências, sete recusas — e nenhuma escrita.

    ```text
    FRESH_DESCRIPTOR != APPROVED_SNAPSHOT -> NO_CONSUMPTION
    ```
    """
    aprovado = envelope(alvos=(snapshot(),))
    fresco = descritor(**DIVERGENCIAS[campo])
    servico, _, efeito, registro = montar([fresco], [])
    referencias = (referencia(),)
    if campo is SnapshotDivergenceField.SUBJECT_COID:
        # A referência tem de casar com o APROVADO; quem diverge é a
        # resolução fresca, que é exatamente o caso sob teste.
        referencias = (referencia(),)
    resultado = servico.execute(pedido(aprovado, referencias))
    assert isinstance(resultado, PreConsumptionRefusal)
    assert resultado.reason is PreConsumptionRefusalReason.FRESH_SNAPSHOT_DIVERGED
    assert resultado.diverged_field is campo
    _sem_escrita(registro, efeito)


@pytest.mark.parametrize("campo", list(DIVERGENCIAS))
def test_s15_cada_campo_do_binding_igual_permite_o_consumo(montar, campo):
    """O outro lado do bilateral: igual em todos os sete, segue adiante.

    O aprovado é montado COM o valor divergente, e a re-resolução devolve
    o mesmo — provando que a recusa anterior vinha da diferença, e não do
    valor em si.
    """
    alterado = DIVERGENCIAS[campo]
    # O principal do envelope acompanha o do alvo: sem modelo de
    # delegação, só o próprio controlador forma envelope, e um lote
    # aprovado com principal estranho seria INCONSTRUTÍVEL.
    principal = (
        alterado["control_scope"].control_principal_ref
        if campo is SnapshotDivergenceField.CONTROL_SCOPE
        else PRINCIPAL
    )
    aprovado = envelope(alvos=(snapshot(**alterado),), principal=principal)
    fresco = descritor(**alterado)
    servico, _, efeito, registro = montar(
        [fresco],
        [
            observado(
                aprovado.approval_id, sujeito=fresco.subject_coid, target_class=fresco.target_class
            )
        ],
    )
    resultado = servico.execute(
        pedido(
            aprovado,
            (
                referencia(
                    subject_coid=fresco.subject_coid,
                    control_scope=fresco.control_scope,
                    origin=fresco.origin,
                ),
            ),
        )
    )
    assert resultado.attempts_observed == 1
    assert registro.commits == 2


def test_s16_a_protecao_de_legado_diverge_nos_dois_sentidos(montar):
    """`LEGACY_PROTECTED_CHANGED_IN_EITHER_DIRECTION -> NO_CONSUMPTION`."""
    for aprovada, fresca in (
        (LegacyProtectionState.NOT_PROTECTED, LegacyProtectionState.PROTECTED),
        (LegacyProtectionState.PROTECTED, LegacyProtectionState.NOT_PROTECTED),
    ):
        aprovado = envelope(alvos=(snapshot(legacy_protection_state=aprovada),))
        servico, _, efeito, registro = montar([descritor(legacy_protection_state=fresca)], [])
        resultado = servico.execute(pedido(aprovado))
        assert resultado.diverged_field is SnapshotDivergenceField.LEGACY_PROTECTION_STATE
        _sem_escrita(registro, efeito)


def test_s17_a_lista_de_campos_comparados_e_a_do_snapshot():
    """Enumeração literal, e uma guarda que a fixa contra o contrato real."""
    from app.memory.schemas.destructive_approval import SafeTargetSnapshot

    comparados = [atributo for _, atributo in CAMPOS_DO_BINDING]
    assert comparados == list(SafeTargetSnapshot.__dataclass_fields__)


# ----------------------------------------------------------------------
# Fase B — consumo durável
# ----------------------------------------------------------------------


def test_s18_o_consumo_commita_antes_de_qualquer_efeito(montar):
    """Ordem observada por contagem, não por leitura do código."""
    aprovado = envelope()
    ordem: list[str] = []
    servico, _, efeito, registro = montar([descritor()], [observado(aprovado.approval_id)])

    commit_original = UoWFalsa.commit

    def commit_observado(self):  # noqa: ANN001, ANN202
        ordem.append("commit")
        commit_original(self)

    attempt_original = EfeitoDuble.attempt_effect

    def attempt_observado(self, request):  # noqa: ANN001, ANN202
        ordem.append("attempt_effect")
        return attempt_original(self, request)

    UoWFalsa.commit = commit_observado  # type: ignore[method-assign]
    EfeitoDuble.attempt_effect = attempt_observado  # type: ignore[method-assign]
    try:
        servico.execute(pedido(aprovado))
    finally:
        UoWFalsa.commit = commit_original  # type: ignore[method-assign]
        EfeitoDuble.attempt_effect = attempt_original  # type: ignore[method-assign]

    assert ordem[0] == "commit"
    assert ordem.index("commit") < ordem.index("attempt_effect")


def test_s19_replay_recusa_sem_chamar_o_efeito(montar):
    """`REPLAY_WITH_SAME_APPROVAL = REFUSED`."""
    from app.memory.errors.exceptions import ApprovalRecordNotUsableError

    aprovado = envelope()
    servico, _, efeito, registro = montar(
        [descritor()],
        [],
        consumo=ApprovalRecordNotUsableError(
            aprovado.approval_id, ApprovalUsageRefusalReason.ALREADY_CONSUMED
        ),
    )
    resultado = servico.execute(pedido(aprovado))
    assert isinstance(resultado, ApprovalConsumptionRefusal)
    assert resultado.reason is ApprovalUsageRefusalReason.ALREADY_CONSUMED
    assert efeito.chamadas == []
    assert registro.recibos == []


@pytest.mark.parametrize(
    "motivo",
    [
        ApprovalUsageRefusalReason.EXPIRED,
        ApprovalUsageRefusalReason.REVOKED,
        ApprovalUsageRefusalReason.BINDING_MISMATCH,
        ApprovalUsageRefusalReason.NOT_FOUND,
    ],
)
def test_s20_todo_motivo_de_recusa_impede_o_efeito(montar, motivo):
    from app.memory.errors.exceptions import ApprovalRecordNotUsableError

    aprovado = envelope()
    servico, _, efeito, _ = montar(
        [descritor()], [], consumo=ApprovalRecordNotUsableError(aprovado.approval_id, motivo)
    )
    resultado = servico.execute(pedido(aprovado))
    assert resultado.reason is motivo
    assert efeito.chamadas == []


def test_s21_falha_no_commit_do_consumo_impede_o_efeito(montar):
    """Se o commit falhar, nenhum efeito pode ser chamado."""
    from app.repositories.exceptions import TransactionError

    aprovado = envelope()
    servico, _, efeito, registro = montar([descritor()], [observado(aprovado.approval_id)])

    commit_original = UoWFalsa.commit

    def commit_que_falha(self):  # noqa: ANN001, ANN202
        raise TransactionError("commit do consumo falhou")

    UoWFalsa.commit = commit_que_falha  # type: ignore[method-assign]
    try:
        with pytest.raises(TransactionError):
            servico.execute(pedido(aprovado))
    finally:
        UoWFalsa.commit = commit_original  # type: ignore[method-assign]

    assert efeito.chamadas == []
    assert registro.recibos == []


# ----------------------------------------------------------------------
# Fase C — efeito e recibo
# ----------------------------------------------------------------------


def test_s22_nao_tentativa_continua_o_lote_sem_recibo(montar):
    """`NO_MATERIAL_ATTEMPT -> NO_ERASURE_RECORD`, e o lote prossegue."""
    aprovado = envelope(alvos=(snapshot(), snapshot(subject_coid=SUJEITO_B, origin=procedencia(1))))
    servico, _, efeito, registro = montar(
        [descritor(), descritor(subject_coid=SUJEITO_B, origin=procedencia(1))],
        [
            nao_iniciada(aprovado.approval_id),
            observado(aprovado.approval_id, sujeito=SUJEITO_B),
        ],
    )
    resultado = servico.execute(
        pedido(
            aprovado,
            (referencia(), referencia(subject_coid=SUJEITO_B, origin=procedencia(1))),
        )
    )
    assert resultado.not_attempted == 1
    assert resultado.attempts_observed == 1
    assert len(registro.recibos) == 1
    assert len(efeito.chamadas) == 2


@pytest.mark.parametrize(
    "desfecho", [ErasureOutcome.SUCCEEDED, ErasureOutcome.FAILED, ErasureOutcome.PARTIAL]
)
def test_s23_todo_desfecho_observado_gera_exatamente_um_recibo(montar, desfecho):
    """`OBSERVED_ATTEMPT -> EXACTLY_ONE_ERASURE_RECORD`."""
    aprovado = envelope()
    servico, _, _, registro = montar(
        [descritor()], [observado(aprovado.approval_id, outcome=desfecho)]
    )
    resultado = servico.execute(pedido(aprovado))
    assert len(registro.recibos) == 1
    assert len(resultado.receipts_persisted) == 1
    assert registro.recibos[0].outcome is desfecho


def test_s24_o_recibo_cita_as_fontes_do_mapeamento(montar):
    """Mapeamento fiel do §6.1 — cada campo de uma fonte existente."""
    aprovado = envelope()
    servico, _, _, registro = montar([descritor()], [observado(aprovado.approval_id)])
    servico.execute(pedido(aprovado))

    entrada = registro.recibos[0]
    governanca = aprovado.proposal.governance_resolution
    assert entrada.subject_identifier == str(SUJEITO_A)
    assert entrada.scope_token == aprovado.proposal.operation.value
    assert entrada.governance_policy_id == governanca.policy_id
    assert entrada.governance_policy_key == governanca.policy_key
    assert entrada.governance_policy_version == governanca.policy_version
    assert entrada.governance_rule_id == governanca.matched_rule_id
    assert (
        entrada.governance_resolution_ref
        == f"approval:{aprovado.approval_id}:governance-resolution"
    )
    assert entrada.approval_ref == str(aprovado.approval_id)


def test_s25_o_identificador_de_regra_e_preservado_byte_a_byte(montar):
    """`OPAQUE_RULE_REFERENCE != UUID` — nada convertido, nada derivado."""
    regra = "rule-Ação-2026/v1"
    aprovado = envelope(governanca=resolucao(matched_rule_id=regra))
    servico, _, _, registro = montar([descritor()], [observado(aprovado.approval_id)])
    servico.execute(pedido(aprovado))
    assert registro.recibos[0].governance_rule_id == regra


def test_s26_o_trio_de_retencao_e_nulo_nesta_composicao(montar):
    """`RETENTION_ASSESSMENT != DELETION_AUTHORITY` — nada a citar."""
    aprovado = envelope()
    servico, _, _, registro = montar([descritor()], [observado(aprovado.approval_id)])
    servico.execute(pedido(aprovado))
    entrada = registro.recibos[0]
    assert entrada.retention_policy_id is None
    assert entrada.retention_policy_key is None
    assert entrada.retention_policy_version is None


def test_s27_o_localizador_nunca_chega_ao_recibo(montar):
    """O localizador não sobrevive ao efeito."""
    aprovado = envelope()
    localizador = f"s3://pia-storage/workspace/w1/{MARCADOR}"
    servico, _, _, registro = montar(
        [descritor(transient_locator=localizador)], [observado(aprovado.approval_id)]
    )
    servico.execute(pedido(aprovado))
    assert MARCADOR not in registro.recibos[0].model_dump_json()


def test_s28_a_ordem_do_lote_e_preservada(montar):
    aprovado = envelope(alvos=(snapshot(), snapshot(subject_coid=SUJEITO_B, origin=procedencia(1))))
    servico, _, efeito, _ = montar(
        [descritor(), descritor(subject_coid=SUJEITO_B, origin=procedencia(1))],
        [
            observado(aprovado.approval_id),
            observado(aprovado.approval_id, sujeito=SUJEITO_B),
        ],
    )
    resultado = servico.execute(
        pedido(
            aprovado,
            (referencia(), referencia(subject_coid=SUJEITO_B, origin=procedencia(1))),
        )
    )
    assert efeito.chamadas == [SUJEITO_A, SUJEITO_B]
    assert [alvo.subject_coid for alvo in resultado.targets] == [SUJEITO_A, SUJEITO_B]


# ----------------------------------------------------------------------
# Erros tipados — PIA-8047, PIA-8048, PIA-8049
# ----------------------------------------------------------------------


def test_s29_excecao_da_porta_vira_estado_desconhecido_tipado(montar):
    """`EFFECT_EXCEPTION -> UNKNOWN_STATE, NEVER_INVENTED_RECEIPT`."""
    from app.memory.errors.exceptions import DestructiveExecutionUnknownMaterialStateError

    aprovado = envelope(alvos=(snapshot(), snapshot(subject_coid=SUJEITO_B, origin=procedencia(1))))
    servico, _, _, registro = montar(
        [descritor(), descritor(subject_coid=SUJEITO_B, origin=procedencia(1))],
        [observado(aprovado.approval_id), TimeoutError("provedor não respondeu")],
    )
    with pytest.raises(DestructiveExecutionUnknownMaterialStateError) as capturado:
        servico.execute(
            pedido(
                aprovado,
                (referencia(), referencia(subject_coid=SUJEITO_B, origin=procedencia(1))),
            )
        )

    evidencia = capturado.value.evidence
    assert capturado.value.error_code.code == "PIA-8047"
    assert evidencia.failed_position == 1
    assert evidencia.attempts_observed == 1
    assert evidencia.receipts_persisted == 1
    # A aprovação permanece consumida, e o recibo do alvo anterior ficou.
    assert registro.consumos == [aprovado.approval_id]
    assert len(registro.recibos) == 1


def test_s30_o_estado_desconhecido_nao_fabrica_recibo_do_alvo_ambiguo(montar):
    from app.memory.errors.exceptions import DestructiveExecutionUnknownMaterialStateError

    aprovado = envelope()
    servico, _, _, registro = montar([descritor()], [RuntimeError("adaptador caiu")])
    with pytest.raises(DestructiveExecutionUnknownMaterialStateError):
        servico.execute(pedido(aprovado))
    assert registro.recibos == []
    assert registro.consumos == [aprovado.approval_id]


@pytest.mark.parametrize(
    ("violacao", "monta"),
    [
        (AdapterContractViolation.APPROVAL_MISMATCH, "approval"),
        (AdapterContractViolation.SUBJECT_MISMATCH, "subject"),
        (AdapterContractViolation.TARGET_CLASS_MISMATCH, "classe"),
    ],
)
def test_s31_resultado_incoerente_do_adaptador_e_recusado(montar, violacao, monta):
    """`RETURNED_RESULT != FACT_UNTIL_BOUND_TO_THE_REQUEST`."""
    from app.memory.errors.exceptions import (
        DestructiveExecutionAdapterContractViolationError,
    )

    aprovado = envelope()
    if monta == "approval":
        resposta = observado(uuid.uuid4())
    elif monta == "subject":
        resposta = observado(aprovado.approval_id, sujeito=SUJEITO_B)
    else:
        resposta = observado(
            aprovado.approval_id,
            target_class=ErasureTargetClass.AUTHORIZED_CONNECTOR_REFERENT,
        )

    servico, _, _, registro = montar([descritor()], [resposta])
    with pytest.raises(DestructiveExecutionAdapterContractViolationError) as capturado:
        servico.execute(pedido(aprovado))

    assert capturado.value.error_code.code == "PIA-8048"
    assert capturado.value.violation is violacao
    assert registro.recibos == []
    assert registro.consumos == [aprovado.approval_id]


def test_s32_nao_tentativa_incoerente_tambem_e_recusada(montar):
    """Aprovação e sujeito são exigidos dos DOIS desfechos."""
    from app.memory.errors.exceptions import (
        DestructiveExecutionAdapterContractViolationError,
    )

    aprovado = envelope()
    servico, _, _, registro = montar(
        [descritor()], [nao_iniciada(aprovado.approval_id, sujeito=SUJEITO_B)]
    )
    with pytest.raises(DestructiveExecutionAdapterContractViolationError) as capturado:
        servico.execute(pedido(aprovado))
    assert capturado.value.violation is AdapterContractViolation.SUBJECT_MISMATCH
    assert registro.recibos == []


def test_s33_falha_no_commit_do_recibo_nao_alega_recibo(montar):
    """Nem alega recibo, nem desfaz o efeito observado no papel."""
    from app.memory.errors.exceptions import ErasureReceiptNotPersistedError
    from app.repositories.exceptions import TransactionError

    aprovado = envelope()
    servico, _, efeito, registro = montar(
        [descritor()],
        [observado(aprovado.approval_id)],
        recibo=TransactionError("commit do recibo falhou"),
    )
    with pytest.raises(ErasureReceiptNotPersistedError) as capturado:
        servico.execute(pedido(aprovado))

    assert capturado.value.error_code.code == "PIA-8049"
    assert capturado.value.outcome is ErasureOutcome.SUCCEEDED
    assert capturado.value.evidence.receipts_persisted == 0
    assert len(efeito.chamadas) == 1


def test_s34_erros_parciais_nao_expoem_material_sensivel(montar):
    """Redação medida também nos erros, `repr` e `str`."""
    from app.memory.errors.exceptions import DestructiveExecutionUnknownMaterialStateError

    aprovado = envelope()
    servico, _, _, _ = montar(
        [descritor(transient_locator=f"s3://pia-storage/w1/{MARCADOR}")],
        [RuntimeError(f"falha ao contatar {MARCADOR}")],
    )
    with pytest.raises(DestructiveExecutionUnknownMaterialStateError) as capturado:
        servico.execute(pedido(aprovado))

    erro = capturado.value
    for texto in (str(erro), repr(erro.evidence), str(erro.detail)):
        assert MARCADOR not in texto


# ----------------------------------------------------------------------
# Paridade de canal
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("canal", "revisao"),
    [
        ("TEXT", "NOT_APPLICABLE"),
        ("VOICE", "REVIEWED_AND_CONFIRMED"),
    ],
)
def test_s35_texto_e_voz_percorrem_as_mesmas_regras(montar, canal, revisao):
    """Nenhum atalho por canal — a governança é a mesma.

    ```text
    NATURAL_LANGUAGE_NEVER_REACHES_THE_EFFECT_PORT
    ```
    """
    from app.memory.models.approval_enums import InputChannel, VoiceReviewState

    aprovado = envelope(canal=InputChannel[canal], revisao=VoiceReviewState[revisao])
    servico, _, efeito, registro = montar([descritor()], [observado(aprovado.approval_id)])
    resultado = servico.execute(pedido(aprovado))
    assert resultado.attempts_observed == 1
    assert registro.commits == 2
    # O pedido que chega à porta carrega descritor e evidência — nunca texto.
    assert len(efeito.chamadas) == 1
