"""
Invariantes dos contratos congelados do kernel — sem banco.

```text
INVARIANTE MATERIAL MORA NO VALUE OBJECT, NÃO SÓ NO SERVIÇO
```

Lição reincidente da auditoria (E4.2.1, E4.3.2, E4.4.1, E3.4.2.1,
E4.5.1, E4.6.1): um invariante que existe apenas no manager é contornado
pelo construtor público.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest

from app.connections.models.enums import ConnectionMethod, ModelAttestationLevel
from app.connections.schemas.projection import (
    CapabilityView,
    ConnectionExecutionReceiptView,
)
from app.connections.services.connection_execution_receipt_service import (
    ExecutionAttribution,
    manual_attribution,
)

pytestmark = pytest.mark.unit

_AGORA = datetime(2026, 8, 24, 12, 0, tzinfo=UTC)


def test_e741u01_capability_recusa_ttl_invertido_ou_nulo() -> None:
    """`valid_until` posterior a `observed_at` é o que dá sentido a "vencido".

    Sem esta recusa, um snapshot com validade no passado do próprio
    instante de observação seria construtível — e "stale" deixaria de
    significar coisa alguma.
    """
    with pytest.raises(ValueError, match="valid_until"):
        CapabilityView(
            connection_id=uuid.uuid4(),
            observed_at=_AGORA,
            valid_until=_AGORA - timedelta(hours=1),
            is_stale=True,
            capabilities=(),
        )
    with pytest.raises(ValueError, match="valid_until"):
        CapabilityView(
            connection_id=uuid.uuid4(),
            observed_at=_AGORA,
            valid_until=_AGORA,
            is_stale=True,
            capabilities=(),
        )
    valida = CapabilityView(
        connection_id=uuid.uuid4(),
        observed_at=_AGORA,
        valid_until=_AGORA + timedelta(hours=1),
        is_stale=False,
        capabilities=("texto",),
    )
    assert valida.is_stale is False


def test_e741u02_atestacao_e_bicondicional_no_value_object() -> None:
    identidade = {
        "receipt_id": uuid.uuid4(),
        "attempt_id": uuid.uuid4(),
        "step_id": uuid.uuid4(),
        "schedule_id": uuid.uuid4(),
        "connection_id": uuid.uuid4(),
        "connection_method": manual_attribution(connection_id=uuid.uuid4()).connection_method,
        "access_provider": None,
        "requested_model": None,
        "observed_at": _AGORA,
    }
    with pytest.raises(ValueError, match="attested"):
        ConnectionExecutionReceiptView(
            **identidade,
            observed_model=None,
            model_attestation_level=ModelAttestationLevel.ATTESTED,
        )
    with pytest.raises(ValueError, match="attested"):
        ConnectionExecutionReceiptView(
            **identidade,
            observed_model="modelo-x",
            model_attestation_level=ModelAttestationLevel.UNKNOWN,
        )
    honesto = ConnectionExecutionReceiptView(
        **identidade,
        observed_model=None,
        model_attestation_level=ModelAttestationLevel.UNKNOWN,
    )
    assert honesto.observed_model is None


def test_e741u03_atribuicao_manual_nao_tem_operador_nem_modelo() -> None:
    """`GATEWAY_OPACO -> NULL, jamais um palpite`."""
    atribuicao = manual_attribution(connection_id=uuid.uuid4())
    assert atribuicao.access_provider is None
    assert atribuicao.requested_model is None
    assert atribuicao.observed_model is None
    assert atribuicao.model_attestation_level is ModelAttestationLevel.UNKNOWN

    with pytest.raises(ValueError, match="operador"):
        ExecutionAttribution(
            connection_id=uuid.uuid4(),
            connection_method=atribuicao.connection_method,
            access_provider="op",
            requested_model=None,
            observed_model=None,
            model_attestation_level=ModelAttestationLevel.UNKNOWN,
        )


# --- corretivo R2: a verdade do manual no SEGUNDO construtor público -------


def _receipt_view_kwargs(**overrides: object) -> dict[str, object]:
    """Kwargs de um recibo manual honesto, com sobreposições pontuais."""
    base: dict[str, object] = {
        "receipt_id": uuid.uuid4(),
        "attempt_id": uuid.uuid4(),
        "step_id": uuid.uuid4(),
        "schedule_id": uuid.uuid4(),
        "connection_id": uuid.uuid4(),
        "connection_method": ConnectionMethod.MANUAL_HANDOFF,
        "access_provider": None,
        "requested_model": None,
        "observed_model": None,
        "model_attestation_level": ModelAttestationLevel.UNKNOWN,
        "observed_at": _AGORA,
    }
    base.update(overrides)
    return base


@pytest.mark.parametrize(
    ("violacao", "kwargs"),
    [
        ("operador", {"access_provider": "openai"}),
        ("modelo solicitado", {"requested_model": "gpt-4"}),
        (
            "modelo observado",
            {"observed_model": "gpt-4", "model_attestation_level": ModelAttestationLevel.ATTESTED},
        ),
        (
            "atestação",
            {"model_attestation_level": ModelAttestationLevel.SELF_DECLARED},
        ),
    ],
)
def test_e741u04_a_view_do_recibo_recusa_manual_falso(violacao, kwargs) -> None:  # noqa: ANN001
    """Achado R1 da auditoria da Chain119 — as QUATRO violações.

    ```text
    manual_handoff => access_provider IS NULL
                      requested_model IS NULL
                      observed_model  IS NULL
                      atestação       = unknown
    ```

    `ConnectionExecutionReceiptView` é um **segundo construtor público**
    para a mesma atribuição. O corretivo R1 declarou o invariante aqui e
    não o aplicou; `p15` exercitava só `ExecutionAttribution` e passou
    sem provar este caminho.

    ```text
    UM CONSTRUTOR PÚBLICO PROVADO != TODOS OS CONSTRUTORES PÚBLICOS
    ```

    O caso de `observed_model` carrega atestação coerente de propósito:
    sem isso a recusa viria da bicondicional, e a prova mediria a guarda
    errada — o defeito recorrente desta entrega.
    """
    with pytest.raises(ValueError, match="repasse manual"):
        ConnectionExecutionReceiptView(**_receipt_view_kwargs(**kwargs))  # type: ignore[arg-type]


def test_e741u05_a_view_aceita_o_manual_honesto_e_o_nao_manual_atestado() -> None:
    """Não-vacuidade nos dois sentidos.

    Sem isto, a prova acima não distinguiria "recusa o manual falso" de
    "recusa tudo que é manual".
    """
    honesto = ConnectionExecutionReceiptView(**_receipt_view_kwargs())  # type: ignore[arg-type]
    assert honesto.observed_model is None
    assert honesto.model_attestation_level is ModelAttestationLevel.UNKNOWN

    # O invariante do manual NÃO alcança outros métodos: um recibo de API
    # direta pode e deve carregar operador, modelo e atestação.
    api = ConnectionExecutionReceiptView(
        **_receipt_view_kwargs(
            connection_method=ConnectionMethod.DIRECT_PROVIDER_API,
            access_provider="operador-x",
            requested_model="modelo-x",
            observed_model="modelo-x",
            model_attestation_level=ModelAttestationLevel.ATTESTED,
        )  # type: ignore[arg-type]
    )
    assert api.observed_model == "modelo-x"
