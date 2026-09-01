"""Integração do lote governado: conflito, três ramos e sidecar E5.l real."""

import pytest

from app.predictive_accessibility import coordinator as mod_coordinator
from app.predictive_accessibility import guidance as mod_guidance
from app.predictive_accessibility import routing as mod_routing
from app.predictive_accessibility.availability import (
    PredictiveAvailabilityOutcome,
    PredictiveCausalRejectionResult,
)
from app.predictive_accessibility.batch import (
    PredictiveUpstreamUnavailableInput,
    PredictiveUpstreamUnavailableOutcome,
)
from app.predictive_accessibility.channel import PredictiveChannel
from tests.unit.predictive_accessibility import _e5_case_helpers as h

pytestmark = pytest.mark.integration


def _rejeicao():
    return PredictiveCausalRejectionResult(
        claim=h.cer().claim,
        rejected_channels=(
            PredictiveAvailabilityOutcome(
                channel=PredictiveChannel(name="lag_1", lag=1),
                available=False,
                reason="sem defasagem suficiente",
            ),
        ),
        reason="nenhum canal com disponibilidade causal",
    )


def test_tres_ramos_um_desfecho_por_item_na_mesma_ordem() -> None:
    desfechos = (
        PredictiveUpstreamUnavailableOutcome(
            source=PredictiveUpstreamUnavailableInput(reference="u1", reason="fora")
        ),
        h.cer(),
        _rejeicao(),
    )
    resultado = mod_coordinator.predictive_route_batch(
        h.coordenado(desfechos), (None, h.governada(), None), at=h.AGORA
    )
    assert resultado.request_length == 3
    assert isinstance(resultado.outcomes[0], mod_routing.PredictiveUpstreamUnavailableRoutingResult)
    assert isinstance(resultado.outcomes[1], mod_routing.PredictiveFinalRoutingResult)
    assert isinstance(resultado.outcomes[2], mod_routing.PredictiveCausalRejectedRoutingResult)


def test_conflito_real_entre_itens_do_lote_abstem_ambos() -> None:
    resultado = mod_coordinator.predictive_route_batch(
        h.coordenado((h.cer(), h.cer())),
        (
            h.governada(conclusion_signature="pico acima"),
            h.governada(conclusion_signature="pico abaixo"),
        ),
        at=h.AGORA,
    )
    for desfecho in resultado.outcomes:
        assert desfecho.route is None
        assert any("conflito real" in limite for limite in desfecho.limits)


def test_ramos_nao_avaliados_nao_executam_qualidade(monkeypatch) -> None:
    chamadas: list[str] = []
    real = mod_guidance.predictive_recommendation_quality

    def espiao(*a, **k):
        chamadas.append("quality")
        return real(*a, **k)

    monkeypatch.setattr(mod_guidance, "predictive_recommendation_quality", espiao)
    desfechos = (
        PredictiveUpstreamUnavailableOutcome(
            source=PredictiveUpstreamUnavailableInput(reference="u", reason="fora")
        ),
        _rejeicao(),
    )
    mod_coordinator.predictive_route_batch(h.coordenado(desfechos), (None, None), at=h.AGORA)
    assert chamadas == []


def test_sidecar_desalinhado_reprova() -> None:
    with pytest.raises(ValueError):
        mod_coordinator.predictive_route_batch(h.coordenado((h.cer(),)), (), at=h.AGORA)


def test_promocao_vem_do_sidecar_e_nao_da_entrada_governada() -> None:
    sem_promocao = mod_coordinator.predictive_route_batch(
        h.coordenado((h.cer(),)), (h.governada(),), at=h.AGORA
    ).outcomes[0]
    com_promocao = mod_coordinator.predictive_route_batch(
        h.coordenado((h.cer(),), promovido=True), (h.governada(),), at=h.AGORA
    ).outcomes[0]
    assert sem_promocao.route is mod_routing.PredictiveRoute.PREDICT
    assert com_promocao.route is mod_routing.PredictiveRoute.RECONFIGURE
