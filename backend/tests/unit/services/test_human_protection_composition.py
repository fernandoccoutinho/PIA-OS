"""Provas do B1b — tradução por valor e composição do gate em G2/G3."""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.authorization.broker import IntentAuthorizationBroker
from app.authorization.ports import SemanticClassification
from app.memory.models.governance_enums import (
    CapabilityEngagement,
    CognitiveOperation,
    CriticalCapability,
)
from app.orchestration.errors.exceptions import HumanProtectionGateUnavailableError
from app.orchestration.ports.governance import GovernanceResolutionView
from app.orchestration.ports.governance_vocabulary import (
    BoundaryCapability,
    BoundaryEngagement,
    BoundaryOperation,
    BoundaryOutcome,
)
from app.orchestration.protection.fingerprint import calcular_binding_sha256
from app.orchestration.protection.vocabulary import GatePosition, ProtectionOutcome
from app.services.human_protection_composition import (
    GATES_DO_B1B,
    HumanProtectionComposition,
    traduzir_capacidades,
    traduzir_engajamento,
    traduzir_operacao,
)

MOMENTO = datetime(2026, 8, 25, 12, 0, 0, tzinfo=UTC)
BOUNDARY_VERSION = 1


class _Classificador:
    classifier_version = "semantico-v1"
    covered_capabilities = frozenset(CriticalCapability)

    def __init__(self, classificacao: SemanticClassification) -> None:
        self._classificacao = classificacao

    def classify(self, *, objective: str) -> SemanticClassification:
        return self._classificacao


class _PortaDeGovernanca:
    """Fronteira E4 real, simulada por valor a partir da regra pura."""

    def resolve(self, query) -> GovernanceResolutionView:  # type: ignore[no-untyped-def]
        proibido = bool(query.descriptor_capabilities) and query.descriptor_engagement in (
            BoundaryEngagement.OPERATIONAL_ENABLEMENT,
            BoundaryEngagement.UNSPECIFIED,
        )
        return GovernanceResolutionView(
            outcome=BoundaryOutcome.PROHIBITED if proibido else BoundaryOutcome.NOT_APPLICABLE,
            capability_engagement=query.descriptor_engagement,
            boundary_version=query.binding.boundary_version,
            classifier_version=query.binding.classifier_version,
            decision_fingerprint="d" * 64,
            binding_sha256=calcular_binding_sha256(query.binding),
            evaluated_at=MOMENTO,
            valid_until=query.binding.valid_until,
            blocked_capabilities=(
                tuple(sorted(query.descriptor_capabilities, key=lambda c: c.value))
                if proibido
                else ()
            ),
        )


class _Repositorio:
    def __init__(self) -> None:
        self.registrados: list[object] = []

    def registrar_aplicacao(self, aplicacao, **kwargs):  # type: ignore[no-untyped-def]
        self.registrados.append(aplicacao)
        return aplicacao


class _Ponte:
    """Ponte real seria o HumanProtectionBridge; aqui o caminho sem banco."""

    def __init__(self, porta: _PortaDeGovernanca, repositorio: _Repositorio) -> None:
        from app.orchestration.protection.bridge import HumanProtectionBridge

        self._real = HumanProtectionBridge(porta, repositorio)  # type: ignore[arg-type]
        self.repositorio = repositorio

    def avaliar(self, query, *, moment=None):  # type: ignore[no-untyped-def]
        return self._real.avaliar(query, moment=moment)

    def registrar_aplicacao(self, *, vista, binding, efeitos, moment=None):  # type: ignore[no-untyped-def]
        aplicacao = self._real.montar_aplicacao(vista=vista, binding=binding, efeitos=efeitos)
        self.repositorio.registrados.append(aplicacao)
        return aplicacao


class _Pausa:
    def __init__(self, erro: Exception | None = None) -> None:
        self.chamadas: list[uuid.UUID] = []
        self._erro = erro

    def pause(self, *, schedule_id: uuid.UUID, reason_fingerprint: str) -> None:
        if self._erro is not None:
            raise self._erro
        self.chamadas.append(schedule_id)


def _composicao(
    classificacao: SemanticClassification, pausa: "_Pausa | None" = None
) -> HumanProtectionComposition:
    broker = IntentAuthorizationBroker(
        _Classificador(classificacao),  # type: ignore[arg-type]
        ttl=timedelta(minutes=5),
    )
    return HumanProtectionComposition(
        broker=broker,
        bridge=_Ponte(_PortaDeGovernanca(), _Repositorio()),  # type: ignore[arg-type]
        boundary_version=BOUNDARY_VERSION,
        pause_port=pausa if pausa is not None else _Pausa(),  # type: ignore[arg-type]
    )


# --- tradução por valor -----------------------------------------------------


def test_b1bu01_operacao_atravessa_por_valor() -> None:
    assert traduzir_operacao(CognitiveOperation.EXPOSE) is BoundaryOperation.EXPOSE


def test_b1bu02_engajamento_atravessa_por_valor() -> None:
    for canonico in CapabilityEngagement:
        assert traduzir_engajamento(canonico).value == canonico.value


def test_b1bu03_capacidades_atravessam_membro_a_membro() -> None:
    traduzidas = traduzir_capacidades(frozenset(CriticalCapability))
    assert {c.value for c in traduzidas} == {c.value for c in CriticalCapability}
    assert all(isinstance(c, BoundaryCapability) for c in traduzidas)


def test_b1bu04_capacidade_sem_espelho_nao_vira_conjunto_vazio() -> None:
    class _Falsa:
        value = "capacidade_que_nao_existe"

    with pytest.raises(HumanProtectionGateUnavailableError) as capturado:
        traduzir_capacidades(frozenset({_Falsa()}))  # type: ignore[arg-type]
    assert "jamais vira conjunto vazio" in str(capturado.value)


def test_b1bu05_capacidade_nao_tipada_e_recusada() -> None:
    with pytest.raises(HumanProtectionGateUnavailableError):
        traduzir_capacidades(frozenset({"child_sexual_exploitation"}))  # type: ignore[arg-type]


# --- composição -------------------------------------------------------------


def test_b1bu06_habilitacao_operacional_bloqueia_em_g2() -> None:
    composicao = _composicao(
        SemanticClassification(
            capabilities=frozenset({CriticalCapability.WEAPON_OF_MASS_DESTRUCTION_ENABLEMENT}),
            engagement=CapabilityEngagement.OPERATIONAL_ENABLEMENT,
        )
    )
    aplicacao = composicao.aplicar(
        objective="objetivo classificado como habilitação operacional",
        gate_position=GatePosition.G2,
        principal_ref="principal-1",
        operation=CognitiveOperation.EXPOSE,
        schedule_id=uuid.uuid4(),
        step_id=uuid.uuid4(),
        moment=MOMENTO,
    )
    assert aplicacao.outcome is ProtectionOutcome.BLOCKED
    assert not composicao.permite(aplicacao)
    assert aplicacao.blocked_capabilities == (
        BoundaryCapability.WEAPON_OF_MASS_DESTRUCTION_ENABLEMENT,
    )


@pytest.mark.parametrize(
    "engajamento",
    [CapabilityEngagement.ANALYTICAL, CapabilityEngagement.PREVENTIVE],
)
def test_b1bu07_trabalho_preventivo_atravessa_o_gate(
    engajamento: CapabilityEngagement,
) -> None:
    composicao = _composicao(
        SemanticClassification(
            capabilities=frozenset({CriticalCapability.CHILD_SEXUAL_EXPLOITATION}),
            engagement=engajamento,
            rationale="detecção e denúncia",
        )
    )
    aplicacao = composicao.aplicar(
        objective="treinar moderadores para detectar e denunciar",
        gate_position=GatePosition.G2,
        principal_ref="principal-1",
        operation=CognitiveOperation.EXPOSE,
        schedule_id=uuid.uuid4(),
        step_id=uuid.uuid4(),
        moment=MOMENTO,
    )
    assert aplicacao.outcome is ProtectionOutcome.ALLOWED
    assert composicao.permite(aplicacao)
    assert aplicacao.blocked_capabilities == ()


def test_b1bu08_g3_amarra_a_tentativa_prealocada() -> None:
    tentativa = uuid.uuid4()
    composicao = _composicao(SemanticClassification())
    aplicacao = composicao.aplicar(
        objective="exportação sob o lock final",
        gate_position=GatePosition.G3,
        principal_ref="principal-1",
        operation=CognitiveOperation.EXPOSE,
        schedule_id=uuid.uuid4(),
        step_id=uuid.uuid4(),
        attempt_id=tentativa,
        moment=MOMENTO,
    )
    assert aplicacao.binding_attempt_id == tentativa
    assert aplicacao.gate_position is GatePosition.G3


def test_b1bu09_allowed_fica_registrado_e_prova_que_o_gate_rodou() -> None:
    composicao = _composicao(SemanticClassification())
    aplicacao = composicao.aplicar(
        objective="objetivo sem capacidade crítica",
        gate_position=GatePosition.G2,
        principal_ref="principal-1",
        operation=CognitiveOperation.EXPOSE,
        schedule_id=uuid.uuid4(),
        step_id=uuid.uuid4(),
        moment=MOMENTO,
    )
    assert aplicacao.outcome is ProtectionOutcome.ALLOWED
    assert aplicacao.producer_ref


def test_b1bu10_g4_bloqueado_sem_porta_de_revogacao_e_recusado() -> None:
    """B2 ativou G1/G4; sem a porta de revogação, um G4 bloqueado recusa."""
    composicao = _composicao(
        SemanticClassification(
            capabilities=frozenset({CriticalCapability.CATASTROPHIC_HARM_ENABLEMENT}),
            engagement=CapabilityEngagement.OPERATIONAL_ENABLEMENT,
        )
    )
    with pytest.raises(HumanProtectionGateUnavailableError) as capturado:
        composicao.aplicar(
            objective="delegação recusada sem porta composta",
            gate_position=GatePosition.G4,
            principal_ref="principal-1",
            operation=CognitiveOperation.EXPOSE,
            schedule_id=uuid.uuid4(),
            step_id=uuid.uuid4(),
            moment=MOMENTO,
        )
    assert "porta de revogação" in str(capturado.value)


def test_b1bu11_gates_do_b1b_sao_enumerados_nao_derivados() -> None:
    assert frozenset({GatePosition.G2, GatePosition.G3}) == GATES_DO_B1B
    assert frozenset(GatePosition) != GATES_DO_B1B


def test_b1bu12_falha_da_e8_e_indisponibilidade_nao_permissao() -> None:
    class _Quebrado:
        classifier_version = "v1"
        covered_capabilities = frozenset(CriticalCapability)

        def classify(self, *, objective: str) -> SemanticClassification:
            raise RuntimeError("provider fora do ar")

    composicao = HumanProtectionComposition(
        broker=IntentAuthorizationBroker(_Quebrado()),  # type: ignore[arg-type]
        bridge=_Ponte(_PortaDeGovernanca(), _Repositorio()),  # type: ignore[arg-type]
        boundary_version=BOUNDARY_VERSION,
        pause_port=_Pausa(),  # type: ignore[arg-type]
    )
    with pytest.raises(HumanProtectionGateUnavailableError) as capturado:
        composicao.aplicar(
            objective="qualquer objetivo",
            gate_position=GatePosition.G2,
            principal_ref="principal-1",
            operation=CognitiveOperation.EXPOSE,
            moment=MOMENTO,
        )
    assert "não produziu descritor autorizado" in str(capturado.value)


def test_b1bu13_binding_carrega_o_objetivo_e_a_versao_do_classificador() -> None:
    composicao = _composicao(SemanticClassification())
    aplicacao = composicao.aplicar(
        objective="objetivo vinculado",
        gate_position=GatePosition.G2,
        principal_ref="principal-1",
        operation=CognitiveOperation.EXPOSE,
        schedule_id=uuid.uuid4(),
        step_id=uuid.uuid4(),
        moment=MOMENTO,
    )
    assert len(aplicacao.objective_sha256) == 64
    assert aplicacao.classifier_version == "semantico-v1"


def test_b1bu14_incoerencia_de_posicao_vira_indisponibilidade_tipada() -> None:
    """G2 sem etapa é binding incoerente — recusa tipada, nunca ValueError cru."""
    composicao = _composicao(SemanticClassification())
    with pytest.raises(HumanProtectionGateUnavailableError) as capturado:
        composicao.aplicar(
            objective="g2 sem step_id",
            gate_position=GatePosition.G2,
            principal_ref="principal-1",
            operation=CognitiveOperation.EXPOSE,
            schedule_id=uuid.uuid4(),
            moment=MOMENTO,
        )
    assert "binding incoerente" in str(capturado.value)


def test_b1bu15_bloqueio_suspende_o_trabalho_antes_de_registrar() -> None:
    pausa = _Pausa()
    composicao = _composicao(
        SemanticClassification(
            capabilities=frozenset({CriticalCapability.CATASTROPHIC_HARM_ENABLEMENT}),
            engagement=CapabilityEngagement.OPERATIONAL_ENABLEMENT,
        ),
        pausa,
    )
    schedule = uuid.uuid4()
    aplicacao = composicao.aplicar(
        objective="objetivo bloqueado",
        gate_position=GatePosition.G3,
        principal_ref="principal-1",
        operation=CognitiveOperation.EXPOSE,
        schedule_id=schedule,
        step_id=uuid.uuid4(),
        attempt_id=uuid.uuid4(),
        moment=MOMENTO,
    )
    assert pausa.chamadas == [schedule]
    assert aplicacao.pause_applied is True
    assert aplicacao.outcome is ProtectionOutcome.BLOCKED


def test_b1bu16_pausa_que_falha_nao_vira_bloqueio_silencioso() -> None:
    composicao = _composicao(
        SemanticClassification(
            capabilities=frozenset({CriticalCapability.CATASTROPHIC_HARM_ENABLEMENT}),
            engagement=CapabilityEngagement.OPERATIONAL_ENABLEMENT,
        ),
        _Pausa(erro=RuntimeError("lock perdido")),
    )
    with pytest.raises(HumanProtectionGateUnavailableError) as capturado:
        composicao.aplicar(
            objective="objetivo bloqueado",
            gate_position=GatePosition.G2,
            principal_ref="principal-1",
            operation=CognitiveOperation.EXPOSE,
            schedule_id=uuid.uuid4(),
            step_id=uuid.uuid4(),
            moment=MOMENTO,
        )
    assert "não pôde ser suspenso" in str(capturado.value)


def test_b1bu17_allowed_nao_suspende_nada() -> None:
    pausa = _Pausa()
    composicao = _composicao(SemanticClassification(), pausa)
    composicao.aplicar(
        objective="objetivo sem capacidade crítica",
        gate_position=GatePosition.G2,
        principal_ref="principal-1",
        operation=CognitiveOperation.EXPOSE,
        schedule_id=uuid.uuid4(),
        step_id=uuid.uuid4(),
        moment=MOMENTO,
    )
    assert pausa.chamadas == []


# --- B2: G1/G4, pausa e retomada --------------------------------------------


class _Revogacao:
    def __init__(self, quantas: int = 2, erro: Exception | None = None) -> None:
        self.chamadas: list[uuid.UUID] = []
        self._quantas = quantas
        self._erro = erro

    def revoke(self, *, schedule_id: uuid.UUID, reason_fingerprint: str) -> int:
        if self._erro is not None:
            raise self._erro
        self.chamadas.append(schedule_id)
        return self._quantas


class _Retomada:
    def __init__(self, erro: Exception | None = None) -> None:
        self.chamadas: list[uuid.UUID] = []
        self._erro = erro

    def resume(self, *, schedule_id: uuid.UUID, decision_fingerprint: str) -> None:
        if self._erro is not None:
            raise self._erro
        self.chamadas.append(schedule_id)


def _composicao_b2(
    classificacao: SemanticClassification,
    *,
    pausa: "_Pausa | None" = None,
    revogacao: "_Revogacao | None" = None,
    retomada: "_Retomada | None" = None,
) -> HumanProtectionComposition:
    broker = IntentAuthorizationBroker(
        _Classificador(classificacao),  # type: ignore[arg-type]
        ttl=timedelta(minutes=5),
    )
    return HumanProtectionComposition(
        broker=broker,
        bridge=_Ponte(_PortaDeGovernanca(), _Repositorio()),  # type: ignore[arg-type]
        boundary_version=BOUNDARY_VERSION,
        pause_port=pausa if pausa is not None else _Pausa(),  # type: ignore[arg-type]
        revocation_port=revogacao if revogacao is not None else _Revogacao(),  # type: ignore[arg-type]
        resume_port=retomada if retomada is not None else _Retomada(),  # type: ignore[arg-type]
    )


_BLOQUEIA = SemanticClassification(
    capabilities=frozenset({CriticalCapability.CATASTROPHIC_HARM_ENABLEMENT}),
    engagement=CapabilityEngagement.OPERATIONAL_ENABLEMENT,
)


def test_b2u01_g1_bloqueia_sem_schedule_e_sem_pausa() -> None:
    pausa = _Pausa()
    aplicacao = _composicao_b2(_BLOQUEIA, pausa=pausa).aplicar(
        objective="criação recusada na origem",
        gate_position=GatePosition.G1,
        principal_ref="principal-1",
        operation=CognitiveOperation.EXPOSE,
        moment=MOMENTO,
    )
    assert aplicacao.outcome is ProtectionOutcome.BLOCKED
    assert aplicacao.pause_applied is False
    assert aplicacao.schedule_id is None and aplicacao.step_id is None
    assert pausa.chamadas == []


def test_b2u02_g1_permitido_deixa_criar() -> None:
    aplicacao = _composicao_b2(SemanticClassification()).aplicar(
        objective="criação legítima",
        gate_position=GatePosition.G1,
        principal_ref="principal-1",
        operation=CognitiveOperation.EXPOSE,
        moment=MOMENTO,
    )
    assert aplicacao.outcome is ProtectionOutcome.ALLOWED


def test_b2u03_g4_bloqueado_pausa_e_revoga_delegacao() -> None:
    pausa, revogacao = _Pausa(), _Revogacao(quantas=3)
    schedule = uuid.uuid4()
    aplicacao = _composicao_b2(_BLOQUEIA, pausa=pausa, revogacao=revogacao).aplicar(
        objective="delegação recusada",
        gate_position=GatePosition.G4,
        principal_ref="principal-1",
        operation=CognitiveOperation.EXPOSE,
        schedule_id=schedule,
        step_id=uuid.uuid4(),
        moment=MOMENTO,
    )
    assert aplicacao.pause_applied is True
    assert aplicacao.delegations_revoked == 3
    assert revogacao.chamadas == [schedule]


def test_b2u04_revogacao_que_falha_nao_vira_bloqueio_parcial() -> None:
    composicao = _composicao_b2(_BLOQUEIA, revogacao=_Revogacao(erro=RuntimeError("sem lock")))
    with pytest.raises(HumanProtectionGateUnavailableError) as capturado:
        composicao.aplicar(
            objective="delegação recusada",
            gate_position=GatePosition.G4,
            principal_ref="principal-1",
            operation=CognitiveOperation.EXPOSE,
            schedule_id=uuid.uuid4(),
            step_id=uuid.uuid4(),
            moment=MOMENTO,
        )
    assert "não pôde ser revogada" in str(capturado.value)


def test_b2u05_g4_permitido_nao_revoga_nada() -> None:
    revogacao = _Revogacao()
    aplicacao = _composicao_b2(SemanticClassification(), revogacao=revogacao).aplicar(
        objective="delegação legítima",
        gate_position=GatePosition.G4,
        principal_ref="principal-1",
        operation=CognitiveOperation.EXPOSE,
        schedule_id=uuid.uuid4(),
        step_id=uuid.uuid4(),
        moment=MOMENTO,
    )
    assert aplicacao.delegations_revoked == 0
    assert revogacao.chamadas == []


def test_b2u06_retomada_exige_decisao_nova_que_permita() -> None:
    retomada = _Retomada()
    schedule = uuid.uuid4()
    aplicacao = _composicao_b2(SemanticClassification(), retomada=retomada).retomar(
        objective="mesmo objetivo, decisão nova",
        gate_position=GatePosition.G2,
        principal_ref="principal-1",
        operation=CognitiveOperation.EXPOSE,
        schedule_id=schedule,
        step_id=uuid.uuid4(),
        moment=MOMENTO,
    )
    assert aplicacao.outcome is ProtectionOutcome.ALLOWED
    assert retomada.chamadas == [schedule]


def test_b2u07_bloqueio_novo_nao_retoma() -> None:
    """`RESUME_UNDER_THE_OLD_DECISION = STALE_AUTHORIZATION`."""
    retomada = _Retomada()
    aplicacao = _composicao_b2(_BLOQUEIA, retomada=retomada).retomar(
        objective="objetivo que segue bloqueado",
        gate_position=GatePosition.G2,
        principal_ref="principal-1",
        operation=CognitiveOperation.EXPOSE,
        schedule_id=uuid.uuid4(),
        step_id=uuid.uuid4(),
        moment=MOMENTO,
    )
    assert aplicacao.outcome is ProtectionOutcome.BLOCKED
    assert retomada.chamadas == []


def test_b2u08_g1_nao_retoma() -> None:
    with pytest.raises(HumanProtectionGateUnavailableError):
        _composicao_b2(SemanticClassification()).retomar(
            objective="qualquer",
            gate_position=GatePosition.G1,
            principal_ref="principal-1",
            operation=CognitiveOperation.EXPOSE,
            schedule_id=uuid.uuid4(),
            step_id=uuid.uuid4(),
            moment=MOMENTO,
        )


def test_b2u09_gates_ativos_sao_escritos_membro_a_membro() -> None:
    from app.services.human_protection_composition import GATES_ATIVOS, GATES_DO_B2

    assert frozenset({GatePosition.G1, GatePosition.G4}) == GATES_DO_B2
    assert (
        frozenset({GatePosition.G1, GatePosition.G2, GatePosition.G3, GatePosition.G4})
        == GATES_ATIVOS
    )
