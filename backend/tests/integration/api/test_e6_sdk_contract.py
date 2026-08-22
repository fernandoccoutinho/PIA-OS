"""
Contrato do SDK contra o servidor REAL (E6.3).

```text
SDK_TRANSPORT -> LIVE_APP -> POSTGRESQL
MOCKED_CONTRACT != VERIFIED_CONTRACT
```

Os testes do pacote usam transporte simulado e provam a forma da
requisição. Este arquivo prova a outra metade: que a forma acordada é a
que o servidor de fato aceita, com credencial real, cota real e banco
real. Um SDK verde só contra mock combina consigo mesmo.

O transporte injetado é o `ASGITransport` do `httpx` apontando para a
aplicação: sem porta, sem rede, mas com o pipeline HTTP inteiro —
middleware, dependências, handlers de exceção.
"""

import pathlib
import sys
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from app.database.engine import engine
from app.database.health import check_database_health
from app.database.session import SessionLocal
from app.models.programmatic_service_principal import SCOPE_PREDICTIVE_EVALUATE
from app.repositories.programmatic_access_repository import ProgrammaticAccessRepository
from app.security.programmatic_access import TOKEN_PREFIX, compute_secret_digest
from main import app
from tests.fixtures.programmatic_evaluation import (
    ready_item_payload,
    unavailable_item_payload,
)

_SDK = pathlib.Path(__file__).resolve().parents[4] / "sdk" / "python"
if str(_SDK) not in sys.path:
    # Somente o TESTE alcança o SDK. `app/**` continua sem conhecê-lo —
    # a guarda estática `test_e63s04` mede exatamente isso.
    sys.path.insert(0, str(_SDK))

pytestmark = pytest.mark.skipif(
    not check_database_health().available,
    reason="PostgreSQL real indisponível — o contrato do SDK exige cota e credencial reais.",
)


@pytest.fixture(autouse=True)
def _limpa():
    with engine.begin() as conexao:
        conexao.execute(sa.text("DELETE FROM programmatic_quota_buckets"))
        conexao.execute(sa.text("DELETE FROM programmatic_service_principals"))
    yield
    with engine.begin() as conexao:
        conexao.execute(sa.text("DELETE FROM programmatic_quota_buckets"))
        conexao.execute(sa.text("DELETE FROM programmatic_service_principals"))


def _credencial(*, quota_limit: int = 10, revogada: bool = False) -> str:
    key_id = f"kid-{uuid.uuid4().hex[:16]}"
    secret = f"secret-{uuid.uuid4().hex}"
    with SessionLocal() as sessao:
        principal = ProgrammaticAccessRepository(sessao).create_principal(
            key_id=key_id,
            secret_digest=compute_secret_digest(key_id, secret),
            scopes=(SCOPE_PREDICTIVE_EVALUATE,),
            quota_limit=quota_limit,
            quota_window_seconds=3600,
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
        if revogada:
            principal.revoked_at = datetime.now(UTC) - timedelta(seconds=1)
        sessao.commit()
    return f"{TOKEN_PREFIX}{key_id}.{secret}"


def _cliente(credencial: str):
    from pia_os_sdk import PiaClient

    return PiaClient(
        "http://pia.local", credencial, client=TestClient(app, base_url="http://pia.local")
    )


def _requisicao(itens: int = 1):
    from pia_os_sdk import models as m

    payloads = [unavailable_item_payload(f"src-{i}") for i in range(itens)]
    return m.PublicEvaluationRequest.model_validate({"items": payloads})


def test_e63i01_evaluate_real_devolve_envelope_tipado() -> None:
    with _cliente(_credencial()) as cliente:
        resposta = cliente.evaluate(_requisicao(itens=2))
    assert resposta.data.request_length == 2
    assert [item.position for item in resposta.data.items] == [0, 1]


def test_e63i02_lote_com_item_ready_atravessa_a_ciencia_real() -> None:
    """O caminho completo: DTO do SDK -> E6.1 -> E5 -> envelope público."""
    from pia_os_sdk import models as m

    pedido = m.PublicEvaluationRequest.model_validate(
        {"items": [ready_item_payload(), unavailable_item_payload("src-x")]}
    )
    with _cliente(_credencial()) as cliente:
        resposta = cliente.evaluate(pedido)
    assert resposta.data.request_length == 2
    assert len(resposta.data.items) == 2


def test_e63i03_observabilidade_real() -> None:
    with _cliente(_credencial()) as cliente:
        assert cliente.health().status == "ok"
        assert cliente.status().database_connected is True
        assert cliente.version().api_version == "v1"


def test_e63i04_credencial_invalida_preserva_401_e_codigo() -> None:
    from pia_os_sdk import PiaApiError

    with (
        _cliente(f"{TOKEN_PREFIX}kid-inexistente01.errado") as cliente,
        pytest.raises(PiaApiError) as erro,
    ):
        cliente.evaluate(_requisicao())
    assert erro.value.status_code == 401
    assert erro.value.code == "PIA-7001"


def test_e63i05_credencial_revogada_preserva_401() -> None:
    from pia_os_sdk import PiaApiError

    with _cliente(_credencial(revogada=True)) as cliente, pytest.raises(PiaApiError) as erro:
        cliente.evaluate(_requisicao())
    assert erro.value.status_code == 401
    assert erro.value.code == "PIA-7001"


def test_e63i06_cota_real_preserva_429_e_codigo() -> None:
    from pia_os_sdk import PiaApiError

    credencial = _credencial(quota_limit=1)
    with _cliente(credencial) as cliente:
        cliente.evaluate(_requisicao())
        with pytest.raises(PiaApiError) as erro:
            cliente.evaluate(_requisicao())
    assert erro.value.status_code == 429
    assert erro.value.code == "PIA-1008"


def test_e63i07_contrato_publico_invalido_preserva_422() -> None:
    """Tetos da E5 continuam do servidor — o SDK não os reproduz."""
    from pia_os_sdk import PiaApiError

    with _cliente(_credencial()) as cliente, pytest.raises(PiaApiError) as erro:
        cliente.evaluate(_requisicao(itens=9))
    assert erro.value.status_code == 422
    assert erro.value.code == "PIA-2001"


def test_e63i08_o_sdk_envia_o_bearer_que_o_servidor_exige() -> None:
    """Sem header, o mesmo servidor recusa — prova que o 200 veio do Bearer."""
    with TestClient(app, base_url="http://pia.local") as http:
        resposta = http.post(
            "/api/v1/predictive-evaluations",
            json=_requisicao().model_dump(mode="json"),
        )
    assert resposta.status_code == 401


def test_e63i09_a_credencial_nao_aparece_na_resposta_nem_no_erro() -> None:
    from pia_os_sdk import PiaApiError

    credencial = _credencial(quota_limit=1)
    segredo = credencial.rsplit(".", 1)[1]
    with _cliente(credencial) as cliente:
        ok = cliente.evaluate(_requisicao())
        with pytest.raises(PiaApiError) as erro:
            cliente.evaluate(_requisicao())
    assert segredo not in ok.model_dump_json()
    assert segredo not in f"{erro.value} {erro.value!r} {erro.value.detail}"
