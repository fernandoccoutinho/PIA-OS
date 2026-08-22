"""
`POST /api/v1/predictive-evaluations` contra PostgreSQL real.

```text
NO_HEADER -> 401
BAD_CREDENTIAL -> 401 INDISTINGUIVEL
NO_SCOPE -> 403 AND ZERO SCIENCE AND ZERO QUOTA
OVER_QUOTA -> 429
VALID -> 200 SuccessResponse
```

Skip por infraestrutura invalidaria o gate: quando o PostgreSQL não está
disponível, este arquivo não mede nada e diz isso explicitamente.
"""

import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from app.database.engine import engine
from app.database.health import check_database_health
from app.database.session import SessionLocal
from app.models.programmatic_service_principal import (
    OPERATION_PREDICTIVE_EVALUATE,
    SCOPE_PREDICTIVE_EVALUATE,
)
from app.repositories.programmatic_access_repository import ProgrammaticAccessRepository
from app.security.programmatic_access import TOKEN_PREFIX, compute_secret_digest
from main import app
from tests.fixtures.programmatic_evaluation import (
    ready_item_payload,
    request_payload,
    unavailable_item_payload,
)

pytestmark = pytest.mark.skipif(
    not check_database_health().available,
    reason="PostgreSQL real indisponível — a E6.2 exige cota atômica e constraints reais.",
)

ROTA = "/api/v1/predictive-evaluations"


@pytest.fixture(autouse=True)
def _limpa_acesso_programatico():
    with engine.begin() as conexao:
        conexao.execute(sa.text("DELETE FROM programmatic_quota_buckets"))
        conexao.execute(sa.text("DELETE FROM programmatic_service_principals"))
    yield
    with engine.begin() as conexao:
        conexao.execute(sa.text("DELETE FROM programmatic_quota_buckets"))
        conexao.execute(sa.text("DELETE FROM programmatic_service_principals"))


def _cria_principal(
    *,
    scopes: tuple[str, ...] = (SCOPE_PREDICTIVE_EVALUATE,),
    quota_limit: int = 10,
    quota_window_seconds: int = 3600,
    revoked: bool = False,
    expired: bool = False,
) -> tuple[str, str]:
    key_id = f"kid-{uuid.uuid4().hex[:16]}"
    secret = f"secret-{uuid.uuid4().hex}"
    with SessionLocal() as sessao:
        repositorio = ProgrammaticAccessRepository(sessao)
        principal = repositorio.create_principal(
            key_id=key_id,
            secret_digest=compute_secret_digest(key_id, secret),
            scopes=scopes,
            quota_limit=quota_limit,
            quota_window_seconds=quota_window_seconds,
            expires_at=(
                datetime.now(UTC) - timedelta(seconds=5)
                if expired
                else datetime.now(UTC) + timedelta(days=1)
            ),
        )
        if revoked:
            principal.revoked_at = datetime.now(UTC) - timedelta(seconds=1)
        sessao.commit()
    return key_id, f"Bearer {TOKEN_PREFIX}{key_id}.{secret}"


def _uso_atual(key_id: str) -> int:
    with SessionLocal() as sessao:
        repositorio = ProgrammaticAccessRepository(sessao)
        linha = repositorio.get_by_key_id(key_id)
        assert linha is not None
        return repositorio.current_usage(
            principal_id=linha.id,
            operation=OPERATION_PREDICTIVE_EVALUATE,
            quota_window_seconds=linha.quota_window_seconds,
        )


def _corpo_valido() -> dict[str, object]:
    return request_payload(ready_item_payload(), unavailable_item_payload("src-x"))


@pytest.fixture
def cliente() -> TestClient:
    return TestClient(app)


# --- provas 1, 2, 3 ---------------------------------------------------------


def test_e62i01_sem_header_devolve_401(cliente: TestClient) -> None:
    resposta = cliente.post(ROTA, json=_corpo_valido())
    assert resposta.status_code == 401
    assert resposta.json()["error"]["code"] == "PIA-7001"


def test_e62i02_condicoes_de_falha_sao_indistinguiveis(cliente: TestClient) -> None:
    """Malformado, desconhecido, segredo errado, revogado e expirado: um corpo."""
    _, valido = _cria_principal()
    key_ok = valido.split("_", 1)[1].split(".", 1)[0]
    _, revogado = _cria_principal(revoked=True)
    _, expirado = _cria_principal(expired=True)

    headers = [
        "Bearer pia_malformado",
        f"Bearer {TOKEN_PREFIX}kid-inexistente0001.qualquer",
        f"Bearer {TOKEN_PREFIX}{key_ok}.segredo-errado",
        revogado,
        expirado,
    ]
    corpos = set()
    for header in headers:
        resposta = cliente.post(ROTA, json=_corpo_valido(), headers={"Authorization": header})
        assert resposta.status_code == 401, header
        corpo = resposta.json()["error"]
        corpos.add((corpo["code"], corpo.get("message"), str(corpo.get("detail"))))
    assert len(corpos) == 1, corpos


def test_e62i03_credencial_nunca_aparece_na_resposta(cliente: TestClient) -> None:
    _, header = _cria_principal()
    segredo = header.rsplit(".", 1)[1]
    resposta = cliente.post(
        ROTA, json=_corpo_valido(), headers={"Authorization": f"{header}-corrompido"}
    )
    assert resposta.status_code == 401
    assert segredo not in resposta.text


# --- prova 5: escopo, sem ciência e sem cota -------------------------------


def test_e62i04_sem_escopo_devolve_403_e_nao_consome_cota(cliente: TestClient) -> None:
    """A rota não confia no escopo persistido — reavalia a cada chamada.

    O escritor central agora recusa escopo vazio (M1), então a linha é
    forjada por SQL direto. Isso é deliberado: o teste mede a rota, e
    medir a rota exige um estado que o escritor legítimo não produz.

    ```text
    WRITER_REJECTS != ROUTE_MAY_ASSUME
    ```
    """
    key_id = f"kid-{uuid.uuid4().hex[:16]}"
    secret = f"secret-{uuid.uuid4().hex}"
    with SessionLocal() as sessao:
        repositorio = ProgrammaticAccessRepository(sessao)
        repositorio.create_principal(
            key_id=key_id,
            secret_digest=compute_secret_digest(key_id, secret),
            scopes=(SCOPE_PREDICTIVE_EVALUATE,),
            quota_limit=5,
            quota_window_seconds=3600,
        )
        sessao.commit()
    with engine.begin() as conexao:
        conexao.execute(
            sa.text(
                "UPDATE programmatic_service_principals SET scopes = '[]'::jsonb "
                "WHERE key_id = :kid"
            ),
            {"kid": key_id},
        )

    resposta = cliente.post(
        ROTA,
        json=_corpo_valido(),
        headers={"Authorization": f"Bearer {TOKEN_PREFIX}{key_id}.{secret}"},
    )
    assert resposta.status_code == 403
    assert resposta.json()["error"]["code"] == "PIA-7002"
    assert _uso_atual(key_id) == 0


# --- prova 9: caminho feliz -------------------------------------------------


def test_e62i05_credencial_valida_devolve_200_com_envelope(cliente: TestClient) -> None:
    key_id, header = _cria_principal()
    resposta = cliente.post(ROTA, json=_corpo_valido(), headers={"Authorization": header})
    assert resposta.status_code == 200, resposta.text
    corpo = resposta.json()
    assert "data" in corpo
    dados = corpo["data"]
    assert dados["request_length"] == 2
    assert [item["position"] for item in dados["items"]] == [0, 1]
    assert "decomposed_conflict_dimensions" in dados
    assert _uso_atual(key_id) == 1


def test_e62i06_cada_chamada_consome_exatamente_uma_unidade(cliente: TestClient) -> None:
    """A dependency não pode ser executada duas vezes por requisição."""
    key_id, header = _cria_principal(quota_limit=10)
    for esperado in (1, 2, 3):
        cliente.post(ROTA, json=_corpo_valido(), headers={"Authorization": header})
        assert _uso_atual(key_id) == esperado


# --- prova 6: cota ----------------------------------------------------------


def test_e62i07_no_teto_aceita_e_a_proxima_devolve_429(cliente: TestClient) -> None:
    key_id, header = _cria_principal(quota_limit=2)
    assert (
        cliente.post(ROTA, json=_corpo_valido(), headers={"Authorization": header}).status_code
        == 200
    )
    assert (
        cliente.post(ROTA, json=_corpo_valido(), headers={"Authorization": header}).status_code
        == 200
    )
    excedente = cliente.post(ROTA, json=_corpo_valido(), headers={"Authorization": header})
    assert excedente.status_code == 429
    assert excedente.json()["error"]["code"] == "PIA-1008"
    assert _uso_atual(key_id) == 2


# --- prova 12: `at` divergente = 422 ---------------------------------------


def test_e62i08_at_divergente_devolve_422(cliente: TestClient) -> None:
    _, header = _cria_principal()
    corpo = request_payload(
        ready_item_payload("2026-03-01T00:00:00Z"), ready_item_payload("2026-03-09T00:00:00Z")
    )
    resposta = cliente.post(ROTA, json=corpo, headers={"Authorization": header})
    assert resposta.status_code == 422
    assert resposta.json()["error"]["code"] == "PIA-2001"


# --- prova 13: somente unavailable -----------------------------------------


def test_e62i09_lote_somente_unavailable_devolve_200(cliente: TestClient) -> None:
    _, header = _cria_principal()
    corpo = request_payload(unavailable_item_payload("a"), unavailable_item_payload("b"))
    resposta = cliente.post(ROTA, json=corpo, headers={"Authorization": header})
    assert resposta.status_code == 200
    assert resposta.json()["data"]["request_length"] == 2


# --- prova 10: tetos E5 continuam ativos -----------------------------------


def test_e62i10_teto_de_lote_da_e5_continua_ativo(cliente: TestClient) -> None:
    _, header = _cria_principal()
    corpo = request_payload(*[unavailable_item_payload(f"src-{i}") for i in range(9)])
    resposta = cliente.post(ROTA, json=corpo, headers={"Authorization": header})
    assert resposta.status_code == 422


# --- prova 14: zero escrita em predictive_reconfiguration_events -----------


def test_e62i11_nenhuma_escrita_em_eventos_de_reconfiguracao(cliente: TestClient) -> None:
    _, header = _cria_principal()
    with engine.connect() as conexao:
        antes = conexao.execute(
            sa.text("SELECT count(*) FROM predictive_reconfiguration_events")
        ).scalar_one()
    assert (
        cliente.post(ROTA, json=_corpo_valido(), headers={"Authorization": header}).status_code
        == 200
    )
    with engine.connect() as conexao:
        depois = conexao.execute(
            sa.text("SELECT count(*) FROM predictive_reconfiguration_events")
        ).scalar_one()
    assert antes == depois == 0


# --- prova 16: OpenAPI ------------------------------------------------------


def test_e62i12_openapi_publica_a_rota_e_seus_desfechos(cliente: TestClient) -> None:
    documento = cliente.get("/openapi.json").json()
    operacao = documento["paths"]["/api/v1/predictive-evaluations"]["post"]
    for status in ("200", "401", "403", "422", "429"):
        assert status in operacao["responses"], status
    esquema = operacao["responses"]["200"]["content"]["application/json"]["schema"]
    assert "SuccessResponse" in str(esquema)


# --- prova 20: credencial de serviço nunca satisfaz PIAP -------------------


def test_e62i13_credencial_de_servico_nao_cria_autoridade_piap(cliente: TestClient) -> None:
    """O principal técnico não vira `user_id` nem aprovação no resultado."""
    _, header = _cria_principal()
    resposta = cliente.post(ROTA, json=_corpo_valido(), headers={"Authorization": header})
    assert resposta.status_code == 200
    texto = resposta.text
    assert "predictive:evaluate" not in texto
    assert header.split(".", 1)[0] not in texto


# --- B2 corrigido: OpenAPI publica o esquema Bearer -----------------------


def test_e62i14_openapi_publica_o_esquema_bearer(cliente: TestClient) -> None:
    """Códigos de resposta não são contrato de autenticação.

    A versão rejeitada documentava 401/403 e usava `Header(...)` comum: o
    OpenAPI não tinha `securitySchemes` algum, então nenhum cliente gerado
    saberia que a rota exige credencial.
    """
    documento = cliente.get("/openapi.json").json()
    esquemas = documento["components"]["securitySchemes"]
    assert "PIAServiceBearer" in esquemas
    esquema = esquemas["PIAServiceBearer"]
    assert esquema["type"] == "http"
    assert esquema["scheme"] == "bearer"
    assert esquema["bearerFormat"] == "pia_<key_id>.<secret>"

    operacao = documento["paths"]["/api/v1/predictive-evaluations"]["post"]
    assert operacao["security"] == [{"PIAServiceBearer": []}]
    assert "503" in operacao["responses"]


def test_e62i15_esquema_diferente_de_bearer_continua_401(cliente: TestClient) -> None:
    """`auto_error=False`: o framework não pode inventar um 403 próprio."""
    for header in ("Basic YWJjOmRlZg==", "Digest xyz", "Token abc", "pia_kid.secret"):
        resposta = cliente.post(ROTA, json=_corpo_valido(), headers={"Authorization": header})
        assert resposta.status_code == 401, header
        assert resposta.json()["error"]["code"] == "PIA-7001"


# --- B1 corrigido: falha da autoridade de cota é 503, nunca 429 ----------


def test_e62i16_falha_do_banco_no_consumo_devolve_503_e_nunca_429(
    cliente: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`QUOTA_EXCEEDED != QUOTA_AUTHORITY_UNAVAILABLE`.

    Publicar 429 aqui afirmaria que o cliente estourou a cota e o
    orientaria a esperar a janela virar — quando a causa foi
    indisponibilidade da autoridade, que ele não resolve esperando.
    """
    _, header = _cria_principal(quota_limit=10)

    def _explode(*_args: object, **_kwargs: object) -> bool:
        raise RuntimeError("db down")

    monkeypatch.setattr(ProgrammaticAccessRepository, "consume_quota", _explode)
    resposta = cliente.post(ROTA, json=_corpo_valido(), headers={"Authorization": header})
    assert resposta.status_code == 503
    assert resposta.json()["error"]["code"] == "PIA-3002"
    assert resposta.status_code != 429


def test_e62i17_falha_do_banco_bloqueia_a_ciencia(
    cliente: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fail closed continua valendo: nada chega à E5."""
    _, header = _cria_principal()
    chamadas: list[object] = []

    import app.routers.predictive_evaluations as modulo

    def _registra(payload: object) -> object:  # pragma: no cover - não deve rodar
        chamadas.append(payload)
        raise AssertionError("a ciência foi alcançada com a cota indisponível")

    def _explode(*_args: object, **_kwargs: object) -> bool:
        raise RuntimeError("db down")

    monkeypatch.setattr(ProgrammaticAccessRepository, "consume_quota", _explode)
    monkeypatch.setattr(modulo, "evaluate_and_route", _registra)
    resposta = cliente.post(ROTA, json=_corpo_valido(), headers={"Authorization": header})
    assert resposta.status_code == 503
    assert chamadas == []


def test_e62i18_teto_real_continua_devolvendo_429(cliente: TestClient) -> None:
    """O 429 sobrevive: só `consume_quota() is False` o produz."""
    _, header = _cria_principal(quota_limit=1)
    assert (
        cliente.post(ROTA, json=_corpo_valido(), headers={"Authorization": header}).status_code
        == 200
    )
    excedente = cliente.post(ROTA, json=_corpo_valido(), headers={"Authorization": header})
    assert excedente.status_code == 429
    assert excedente.json()["error"]["code"] == "PIA-1008"


def test_e62i19_cota_e_isolada_por_principal(cliente: TestClient) -> None:
    """Chave da cota é o principal, não algo global.

    Sem esta prova, trocar `principal.id` por um valor fixo faria dois
    clientes dividirem o mesmo teto sem que nenhum teste notasse.
    """
    _, header_a = _cria_principal(quota_limit=1)
    _, header_b = _cria_principal(quota_limit=1)
    assert (
        cliente.post(ROTA, json=_corpo_valido(), headers={"Authorization": header_a}).status_code
        == 200
    )
    assert (
        cliente.post(ROTA, json=_corpo_valido(), headers={"Authorization": header_b}).status_code
        == 200
    )
    assert (
        cliente.post(ROTA, json=_corpo_valido(), headers={"Authorization": header_a}).status_code
        == 429
    )
