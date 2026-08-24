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

from app.connections.models.enums import ModelAttestationLevel
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
