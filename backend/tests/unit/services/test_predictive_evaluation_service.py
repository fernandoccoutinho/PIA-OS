"""
Serviço de aplicação `E6.2` — compõe, não decide.

```text
ZERO_WRITE_TO_RECONFIGURATION_EVENTS
RECONFIGURATION_INSTRUCTION = ALWAYS_NONE
MIXED_AT -> 422 BEFORE SCIENCE
UNAVAILABLE_ONLY_IS_DETERMINISTIC
```
"""

import ast
import pathlib
import uuid
from datetime import UTC, datetime

import pytest

from app.exceptions.validation import ValidationException
from app.schemas import predictive_evaluation as dto
from app.services import predictive_evaluation_service as servico
from tests.fixtures.programmatic_evaluation import ready_item, unavailable_item

pytestmark = pytest.mark.unit

FONTE_SERVICO = pathlib.Path(servico.__file__)


def _ready(at: str = "2026-03-01T00:00:00Z") -> dto.PublicReadyItem:
    return ready_item(at)


def _unavailable(ref: str = "src-1") -> dto.PublicUpstreamUnavailableItem:
    return unavailable_item(ref)


# --- prova 13: somente unavailable funciona e é determinístico -------------


def test_e62s01_lote_somente_unavailable_e_valido() -> None:
    resposta = servico.evaluate_and_route(
        dto.PublicEvaluationRequest(items=(_unavailable("a"), _unavailable("b")))
    )
    assert resposta.request_length == 2
    assert len(resposta.items) == 2


def test_e62s02_instante_interno_nao_afeta_curto_circuito_de_unavailable() -> None:
    """Prova que `_NO_READY_ITEM_INSTANT` não influencia o resultado."""
    pedido = dto.PublicEvaluationRequest(items=(_unavailable("a"),))
    base = servico.evaluate_and_route(pedido).model_dump()

    original = servico._NO_READY_ITEM_INSTANT
    try:
        servico._NO_READY_ITEM_INSTANT = datetime(2099, 12, 31, tzinfo=UTC)
        alternativo = servico.evaluate_and_route(pedido).model_dump()
    finally:
        servico._NO_READY_ITEM_INSTANT = original
    assert base == alternativo


# --- prova 12: `at` divergente = 422 antes da ciência ----------------------


def test_e62s03_at_divergente_recusa_com_validation_exception() -> None:
    pedido = dto.PublicEvaluationRequest(
        items=(_ready("2026-03-01T00:00:00Z"), _ready("2026-03-02T00:00:00Z"))
    )
    with pytest.raises(ValidationException) as erro:
        servico.evaluate_and_route(pedido)
    assert erro.value.status_code == 422
    assert erro.value.code == "PIA-2001"


def test_e62s04_at_igual_em_todos_os_ready_passa() -> None:
    pedido = dto.PublicEvaluationRequest(items=(_ready(), _ready()))
    resposta = servico.evaluate_and_route(pedido)
    assert resposta.request_length == 2


# --- prova 9/11: ordem e cardinalidade preservadas -------------------------


def test_e62s05_ordem_e_cardinalidade_preservadas() -> None:
    pedido = dto.PublicEvaluationRequest(
        items=(_unavailable("primeiro"), _ready(), _unavailable("terceiro"))
    )
    resposta = servico.evaluate_and_route(pedido)
    assert [item.position for item in resposta.items] == [0, 1, 2]
    assert resposta.request_length == 3


# --- prova 14: zero escrita em predictive_reconfiguration_events -----------


def test_e62s06_repositorio_no_write_explode_se_tocado() -> None:
    repo = servico.NoWriteReconfigurationRepository()
    with pytest.raises(servico.NoWriteReconfigurationRepository.Violation):
        repo.get(uuid.uuid4())
    with pytest.raises(servico.NoWriteReconfigurationRepository.Violation):
        repo.current("grid.load|demand.peak")
    with pytest.raises(servico.NoWriteReconfigurationRepository.Violation):
        repo.append(object())  # type: ignore[arg-type]


def test_e62s07_cadeia_completa_nao_toca_o_repositorio() -> None:
    """Se a E6.2 chamasse a porta E5.l, o no-write teria explodido."""
    servico.evaluate_and_route(dto.PublicEvaluationRequest(items=(_ready(),)))


# --- prova 10: tetos 8/512 continuam ativos --------------------------------


def test_e62s08_teto_de_lote_continua_ativo_pela_requisicao_canonica() -> None:
    excedente = tuple(_unavailable(f"src-{i}") for i in range(9))
    with pytest.raises(ValidationException):
        servico.evaluate_and_route(dto.PublicEvaluationRequest.model_construct(items=excedente))


# --- prova 15: nada de execução externa ------------------------------------


def test_e62s09_servico_nao_importa_provider_conector_nem_http() -> None:
    arvore = ast.parse(FONTE_SERVICO.read_text(encoding="utf-8"))
    modulos: list[str] = []
    for no in ast.walk(arvore):
        if isinstance(no, ast.Import):
            modulos.extend(a.name for a in no.names)
        elif isinstance(no, ast.ImportFrom) and no.module:
            modulos.append(no.module)
    proibidos = ("httpx", "requests", "urllib", "socket", "subprocess", "openai", "anthropic")
    for modulo in modulos:
        assert not modulo.startswith(proibidos), modulo


# --- mutantes dirigidos -----------------------------------------------------


def test_e62m04_mutante_que_chama_e5_com_instrucao_de_reconfiguracao_morre() -> None:
    """As instruções são sempre `None`; qualquer outra coisa é promoção."""
    fonte = FONTE_SERVICO.read_text(encoding="utf-8")
    assert "instrucoes = tuple(None for _ in canonica.items)" in fonte
    for proibido in (
        "PredictiveReconfigurationInstruction(",
        "PredictiveReconfigurationCandidate(",
        "predictive_reconfiguration_gate(",
    ):
        assert proibido not in fonte, proibido


def test_e62m05_mutante_que_omite_o_roteamento_morre() -> None:
    fonte = FONTE_SERVICO.read_text(encoding="utf-8")
    assert "predictive_route_batch(" in fonte
    mutado = fonte.replace("roteamento = predictive_route_batch(", "roteamento = (")
    assert "predictive_route_batch(" not in mutado.split("def evaluate_and_route")[1]


def test_e62m06_mutante_que_aceita_at_divergente_morre() -> None:
    pedido = dto.PublicEvaluationRequest(
        items=(_ready("2026-03-01T00:00:00Z"), _ready("2026-03-05T00:00:00Z"))
    )
    with pytest.raises(ValidationException):
        servico.evaluate_and_route(pedido)


def test_e62m07_mutante_que_monta_desfecho_a_mao_morre() -> None:
    """O serviço não pode construir desfechos científicos por conta própria."""
    fonte = FONTE_SERVICO.read_text(encoding="utf-8")
    for proibido in (
        "PredictiveFinalRouting(",
        "PredictiveClaimEvaluationResult(",
        "PublicEvaluationResultItem(",
        "PublicScientificOutcome(",
    ):
        assert proibido not in fonte, proibido
