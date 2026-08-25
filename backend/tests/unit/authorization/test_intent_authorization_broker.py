"""Provas da E8 IAB — produtor autorizado do descritor semântico."""

from datetime import UTC, datetime, timedelta

import pytest

from app.authorization.broker import (
    DEFAULT_DESCRIPTOR_TTL,
    REQUIRED_CAPABILITY_COVERAGE,
    IntentAuthorizationBroker,
    IntentAuthorizationUnavailableError,
)
from app.authorization.descriptor import AuthorizedCapabilityDescriptor, objective_digest
from app.authorization.ports import SemanticClassification
from app.memory.models.governance_enums import (
    CapabilityEngagement,
    CognitiveOperation,
    CriticalCapability,
    GovernanceOutcome,
)
from app.memory.services.platform_safety_boundary import assess_capability

MOMENTO = datetime(2026, 8, 25, 12, 0, 0, tzinfo=UTC)


class _Classificador:
    """Duplo determinístico. Nunca lê o objetivo para decidir."""

    def __init__(
        self,
        classificacao: SemanticClassification | None = None,
        *,
        version: str = "duplo-v1",
        cobertura: frozenset[CriticalCapability] | None = None,
        erro: Exception | None = None,
        retorno_cru: object = None,
    ) -> None:
        self._classificacao = classificacao or SemanticClassification()
        self._version = version
        self._cobertura = cobertura if cobertura is not None else REQUIRED_CAPABILITY_COVERAGE
        self._erro = erro
        self._retorno_cru = retorno_cru
        self.objetivos_vistos: list[str] = []

    @property
    def classifier_version(self) -> str:
        return self._version

    @property
    def covered_capabilities(self) -> frozenset[CriticalCapability]:
        return self._cobertura

    def classify(self, *, objective: str) -> SemanticClassification:
        self.objetivos_vistos.append(objective)
        if self._erro is not None:
            raise self._erro
        if self._retorno_cru is not None:
            return self._retorno_cru  # type: ignore[return-value]
        return self._classificacao


def _broker(classificador: _Classificador, **kwargs: object) -> IntentAuthorizationBroker:
    return IntentAuthorizationBroker(classificador, **kwargs)  # type: ignore[arg-type]


def test_e8u01_descritor_vincula_objetivo_versao_e_validade() -> None:
    classificador = _Classificador(version="semantico-v3")
    descritor = _broker(classificador).authorize(
        objective="analisar padrões de aliciamento para treinar moderadores",
        operation=CognitiveOperation.EXPOSE,
        moment=MOMENTO,
    )

    assert descritor.objective_sha256 == objective_digest(
        "analisar padrões de aliciamento para treinar moderadores"
    )
    assert descritor.classifier_version == "semantico-v3"
    assert descritor.evaluated_at == MOMENTO
    assert descritor.valid_until == MOMENTO + DEFAULT_DESCRIPTOR_TTL


def test_e8u02_descritor_nao_serve_a_outro_objetivo() -> None:
    descritor = _broker(_Classificador()).authorize(
        objective="objetivo A",
        operation=CognitiveOperation.EXPOSE,
        moment=MOMENTO,
    )
    assert descritor.matches_objective("objetivo A")
    assert not descritor.matches_objective("objetivo B")


def test_e8u03_janela_semiaberta_recusa_o_instante_exato_de_expiracao() -> None:
    descritor = _broker(_Classificador()).authorize(
        objective="qualquer objetivo",
        operation=CognitiveOperation.EXPOSE,
        moment=MOMENTO,
    )
    assert descritor.is_valid_at(MOMENTO)
    assert descritor.is_valid_at(descritor.valid_until - timedelta(microseconds=1))
    assert not descritor.is_valid_at(descritor.valid_until)


def test_e8u04_classificador_sem_cobertura_total_e_recusado() -> None:
    parcial = frozenset({CriticalCapability.CHILD_SEXUAL_EXPLOITATION})
    with pytest.raises(IntentAuthorizationUnavailableError) as capturado:
        _broker(_Classificador(cobertura=parcial)).authorize(
            objective="qualquer objetivo",
            operation=CognitiveOperation.EXPOSE,
            moment=MOMENTO,
        )
    assert "não cobre o vocabulário fechado" in str(capturado.value)


def test_e8u05_cobertura_exigida_e_o_vocabulario_inteiro() -> None:
    """Derivada do enum de propósito — capacidade nova invalida classificador antigo."""
    assert frozenset(CriticalCapability) == REQUIRED_CAPABILITY_COVERAGE


def test_e8u06_falha_do_classificador_vira_indisponibilidade_nao_permissao() -> None:
    with pytest.raises(IntentAuthorizationUnavailableError) as capturado:
        _broker(_Classificador(erro=RuntimeError("provider fora do ar"))).authorize(
            objective="qualquer objetivo",
            operation=CognitiveOperation.EXPOSE,
            moment=MOMENTO,
        )
    assert capturado.value.error_code == "PIA-8070"


def test_e8u07_ausencia_de_descritor_nao_e_not_applicable() -> None:
    """`MISSING DESCRIPTOR != NOT_APPLICABLE` — a diferença material da E8."""
    with pytest.raises(IntentAuthorizationUnavailableError):
        _broker(_Classificador(erro=TimeoutError("sem resposta"))).authorize(
            objective="qualquer objetivo",
            operation=CognitiveOperation.EXPOSE,
            moment=MOMENTO,
        )


def test_e8u08_retorno_fora_do_contrato_e_recusado() -> None:
    with pytest.raises(IntentAuthorizationUnavailableError) as capturado:
        _broker(_Classificador(retorno_cru={"capabilities": []})).authorize(
            objective="qualquer objetivo",
            operation=CognitiveOperation.EXPOSE,
            moment=MOMENTO,
        )
    assert "fora do contrato" in str(capturado.value)


def test_e8u09_habilitacao_operacional_e_proibida_pela_fronteira() -> None:
    classificacao = SemanticClassification(
        capabilities=frozenset({CriticalCapability.WEAPON_OF_MASS_DESTRUCTION_ENABLEMENT}),
        engagement=CapabilityEngagement.OPERATIONAL_ENABLEMENT,
    )
    descritor = _broker(_Classificador(classificacao)).authorize(
        objective="objetivo classificado como habilitação operacional",
        operation=CognitiveOperation.EXPOSE,
        moment=MOMENTO,
    )
    avaliacao = assess_capability(descritor.to_boundary_descriptor())
    assert avaliacao.outcome is GovernanceOutcome.PROHIBITED
    assert avaliacao.blocked_capabilities == (
        CriticalCapability.WEAPON_OF_MASS_DESTRUCTION_ENABLEMENT,
    )


@pytest.mark.parametrize(
    "engajamento",
    [CapabilityEngagement.ANALYTICAL, CapabilityEngagement.PREVENTIVE],
)
def test_e8u10_trabalho_analitico_e_preventivo_continua(
    engajamento: CapabilityEngagement,
) -> None:
    """`TOPIC != CAPABILITY` — o mesmo tema crítico não bloqueia por tema."""
    classificacao = SemanticClassification(
        capabilities=frozenset({CriticalCapability.CHILD_SEXUAL_EXPLOITATION}),
        engagement=engajamento,
        rationale="detecção e denúncia a canais competentes",
    )
    descritor = _broker(_Classificador(classificacao)).authorize(
        objective="treinar moderadores para detectar e denunciar",
        operation=CognitiveOperation.EXPOSE,
        moment=MOMENTO,
    )
    avaliacao = assess_capability(descritor.to_boundary_descriptor())
    assert avaliacao.outcome is GovernanceOutcome.NOT_APPLICABLE
    assert avaliacao.blocked_capabilities == ()


def test_e8u11_unspecified_sobre_capacidade_critica_proibe() -> None:
    classificacao = SemanticClassification(
        capabilities=frozenset({CriticalCapability.CATASTROPHIC_HARM_ENABLEMENT}),
        engagement=CapabilityEngagement.UNSPECIFIED,
        rationale="finalidade não estabelecida",
    )
    descritor = _broker(_Classificador(classificacao)).authorize(
        objective="objetivo sem finalidade estabelecida",
        operation=CognitiveOperation.EXPOSE,
        moment=MOMENTO,
    )
    assert descritor.stated_intent is None
    assert assess_capability(descritor.to_boundary_descriptor()).prohibits


def test_e8u12_relogio_lido_uma_unica_vez() -> None:
    leituras: list[int] = []

    def relogio() -> datetime:
        leituras.append(1)
        return MOMENTO

    descritor = _broker(_Classificador(), clock=relogio).authorize(
        objective="qualquer objetivo",
        operation=CognitiveOperation.EXPOSE,
    )
    assert len(leituras) == 1
    assert descritor.evaluated_at == MOMENTO


def test_e8u13_operacao_nao_tipada_e_recusada() -> None:
    with pytest.raises(IntentAuthorizationUnavailableError):
        _broker(_Classificador()).authorize(
            objective="qualquer objetivo",
            operation="expose",  # type: ignore[arg-type]
            moment=MOMENTO,
        )


def test_e8u14_objetivo_vazio_e_recusado() -> None:
    with pytest.raises(IntentAuthorizationUnavailableError):
        _broker(_Classificador()).authorize(
            objective="   ",
            operation=CognitiveOperation.EXPOSE,
            moment=MOMENTO,
        )


def test_e8u15_classificacao_com_valor_fora_do_vocabulario_nao_existe() -> None:
    with pytest.raises(TypeError):
        SemanticClassification(capabilities=frozenset({"child_sexual_exploitation"}))  # type: ignore[arg-type]


def test_e8u16_descritor_exige_janela_estritamente_positiva() -> None:
    with pytest.raises(ValueError):
        AuthorizedCapabilityDescriptor(
            operation=CognitiveOperation.EXPOSE,
            capabilities=frozenset(),
            engagement=CapabilityEngagement.ANALYTICAL,
            objective_sha256=objective_digest("x"),
            classifier_version="v1",
            evaluated_at=MOMENTO,
            valid_until=MOMENTO,
        )


def test_e8u17_broker_nao_inspeciona_o_objetivo_para_decidir() -> None:
    """O objetivo chega inteiro à porta; nada aqui o interpreta."""
    classificador = _Classificador()
    objetivo = "texto com palavras que um catálogo local acharia alarmantes"
    _broker(classificador).authorize(
        objective=objetivo,
        operation=CognitiveOperation.EXPOSE,
        moment=MOMENTO,
    )
    assert classificador.objetivos_vistos == [objetivo]
