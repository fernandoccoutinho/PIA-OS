"""
DTOs públicos da E7.3 — o que o cliente não pode enviar (`Chain117`).

```text
NAIVE_DATETIME = AMBIGUOUS_INSTANT
```
"""

from datetime import UTC, datetime, timedelta

import pytest
from pydantic import ValidationError

from app.schemas import orchestration_public as dto

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "instante",
    ["2030-01-01T00:00:00", "2030-06-15T12:30:00.000000", "2030-06-15 12:30:00"],
)
def test_e73u01_valid_until_sem_fuso_e_recusado_no_dto(instante: str) -> None:
    """Achado C5, na camada de entrada.

    Sem fuso não há instante: o servidor teria de escolher um, e a escolha
    decidiria em silêncio quando a delegação expira. A comparação com o
    relógio do banco também estouraria `TypeError`, virando 500 para um
    erro do cliente.
    """
    with pytest.raises(ValidationError, match="fuso"):
        dto.GrantDelegationRequest(command_key="k", valid_until=instante)


def test_e73u02_valid_until_com_fuso_e_aceito() -> None:
    """Não-vacuidade: o validador recusa o ambíguo, não tudo."""
    momento = datetime.now(UTC) + timedelta(hours=1)
    pedido = dto.GrantDelegationRequest(command_key="k", valid_until=momento.isoformat())
    assert pedido.valid_until.tzinfo is not None


def test_e73u03_dtos_de_governanca_recusam_campo_desconhecido() -> None:
    for classe in (
        dto.GrantDelegationRequest,
        dto.RevokeDelegationRequest,
        dto.ControlEventRequest,
        dto.AuditOpinionRequest,
    ):
        assert classe.model_config.get("extra") == "forbid", classe.__name__
        assert classe.model_config.get("frozen") is True, classe.__name__
