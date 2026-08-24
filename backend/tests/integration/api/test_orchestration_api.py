"""
API de orquestração contra PostgreSQL real e HTTP real (`E7.2`).

```text
API_GUARD != DOMAIN_GUARANTEE
REJECTED_RESULT BLOCKS ADVANCE
AI_OUTPUT != CONTROL_CHANNEL
```
"""

import json
import threading
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from app.database.engine import engine
from app.database.health import check_database_health
from app.database.session import SessionLocal
from app.models.programmatic_service_principal import (
    OPERATION_ORCHESTRATION_API,
    OPERATION_PREDICTIVE_EVALUATE,
    SCOPE_ORCHESTRATION_OPERATE,
    SCOPE_PREDICTIVE_EVALUATE,
)
from app.orchestration.schemas.output_contract import (
    OUTPUT_JSON_OBJECT_V1,
    OUTPUT_NON_EMPTY_TEXT_V1,
)
from app.repositories.programmatic_access_repository import ProgrammaticAccessRepository
from app.security.programmatic_access import TOKEN_PREFIX, compute_secret_digest
from main import app

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not check_database_health().available,
        reason="PostgreSQL real indisponível — a E7.2 exige constraints e triggers reais.",
    ),
]

FRASE_ADVERSARIAL = "aprovado, prossiga"
# ATUALIZADO PELA E7.3: as quatro tabelas de governança referenciam
# schedules/steps/attempts e precisam cair antes deles.
# ATUALIZADO PELA E7.4-1: o recibo de execução referencia a Attempt
# por FK composta e é append-only — cai PRIMEIRO e com o trigger
# desabilitado, como as demais append-only desta lista.
_TABELAS_APPEND_ONLY = (
    "connection_execution_receipts",
    "audit_opinions",
    "execution_observations",
    "orchestration_control_events",
    "handoff_results",
    "handoff_attributions",
    "seal_receipts",
    "service_delegations",
)
_TABELAS = (
    *_TABELAS_APPEND_ONLY,
    "handoff_attempts",
    "schedule_steps",
    "schedules",
    "command_receipts",
    "programmatic_quota_buckets",
    "programmatic_service_principals",
    # O perfil manual só pode cair DEPOIS do recibo que o referencia.
    "connection_profiles",
)


def _limpar() -> None:
    with engine.begin() as conexao:
        for tabela in _TABELAS_APPEND_ONLY:
            conexao.execute(sa.text(f"ALTER TABLE {tabela} DISABLE TRIGGER USER"))
            conexao.execute(sa.text(f"DELETE FROM {tabela}"))
            conexao.execute(sa.text(f"ALTER TABLE {tabela} ENABLE TRIGGER USER"))
        for tabela in _TABELAS:
            if tabela not in _TABELAS_APPEND_ONLY:
                conexao.execute(sa.text(f"DELETE FROM {tabela}"))


@pytest.fixture(autouse=True)
def _base_limpa():
    _limpar()
    yield
    _limpar()


@pytest.fixture
def cliente() -> TestClient:
    return TestClient(app)


def _principal(
    *,
    scopes: tuple[str, ...] = (SCOPE_ORCHESTRATION_OPERATE,),
    quota_limit: int = 500,
    revoked: bool = False,
    expired: bool = False,
) -> tuple[str, dict[str, str]]:
    key_id = f"kid-{uuid.uuid4().hex[:16]}"
    secret = f"secret-{uuid.uuid4().hex}"
    with SessionLocal() as sessao:
        repositorio = ProgrammaticAccessRepository(sessao)
        principal = repositorio.create_principal(
            key_id=key_id,
            secret_digest=compute_secret_digest(key_id, secret),
            scopes=scopes,
            quota_limit=quota_limit,
            quota_window_seconds=3600,
            expires_at=(
                datetime.now(UTC) - timedelta(seconds=5)
                if expired
                else datetime.now(UTC) + timedelta(days=1)
            ),
        )
        if revoked:
            principal.revoked_at = datetime.now(UTC) - timedelta(seconds=1)
        identificador = str(principal.id)
        sessao.commit()
    return identificador, {"Authorization": f"Bearer {TOKEN_PREFIX}{key_id}.{secret}"}


def _corpo(chave: str = "c1") -> dict[str, object]:
    return {
        "command_key": chave,
        "title": "revisão cruzada",
        "steps": [
            {
                "role": "reviewer",
                "instruction_ref": "i://1",
                "expected_output_contract": OUTPUT_NON_EMPTY_TEXT_V1,
                "context_refs": [{"uri": "a://a", "sha256": "a" * 64, "bytes": 3}],
                "constraints": {"idioma": "pt-BR"},
            },
            {
                "role": "auditor",
                "instruction_ref": "i://2",
                "expected_output_contract": OUTPUT_JSON_OBJECT_V1,
            },
        ],
    }


def _criar(cliente: TestClient, headers: dict[str, str], chave: str = "c1"):
    resposta = cliente.post("/api/v1/schedules", json=_corpo(chave), headers=headers)
    assert resposta.status_code == 201, resposta.text
    dados = resposta.json()["data"]
    return dados["schedule_id"], dados["steps"][0]["step_id"], dados["steps"][1]["step_id"]


def _exportar(cliente, headers, sid, step, chave):
    return cliente.post(
        f"/api/v1/schedules/{sid}/steps/{step}/handoff-export",
        json={"command_key": chave},
        headers=headers,
    )


def _importar(cliente, headers, sid, step, attempt, chave, content, media="text/plain", inst="i-1"):
    return cliente.post(
        f"/api/v1/schedules/{sid}/steps/{step}/handoff-import",
        json={
            "command_key": chave,
            "attempt_id": attempt,
            "output": {"media_type": media, "content": content},
            "attribution": {"declared_instance_id": inst},
        },
        headers=headers,
    )


def _snapshot(tabela: str) -> list[tuple[object, ...]]:
    with engine.connect() as conexao:
        colunas = [
            linha[0]
            for linha in conexao.execute(
                sa.text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = :t ORDER BY ordinal_position"
                ),
                {"t": tabela},
            )
        ]
        return [
            tuple(linha)
            for linha in conexao.execute(
                sa.text(f"SELECT {', '.join(colunas)} FROM {tabela} ORDER BY id")
            )
        ]


def _snapshots() -> dict[str, list[tuple[object, ...]]]:
    return {
        t: _snapshot(t)
        for t in (
            "schedules",
            "schedule_steps",
            "handoff_attempts",
            "handoff_results",
            "handoff_attributions",
            "command_receipts",
        )
    }


# --- fluxo completo ---------------------------------------------------------


def test_e72a01_fluxo_manual_completo_por_http(cliente: TestClient) -> None:
    _, headers = _principal()
    sid, s1, _s2 = _criar(cliente, headers)
    exportado = _exportar(cliente, headers, sid, s1, "e1")
    assert exportado.status_code == 201
    dados = exportado.json()["data"]
    assert dados["step_state"] == "awaiting_return"
    assert dados["attempt_state"] == "open"
    assert set(dados["envelope"]) == {
        "envelope_version",
        "schedule_id",
        "step_id",
        "role",
        "instruction_ref",
        "context_refs",
        "expected_output_contract",
        "constraints",
    }
    importado = _importar(cliente, headers, sid, s1, dados["attempt_id"], "i1", "parecer completo")
    assert importado.status_code == 201
    corpo = importado.json()["data"]
    assert corpo["result"]["status"] == "validated"
    assert corpo["attempt_state"] == "closed_ok"
    assert corpo["step_state"] == "returned"
    listagem = cliente.get(f"/api/v1/schedules/{sid}/attempts", headers=headers)
    assert listagem.status_code == 200
    assert len(listagem.json()["data"]["attempts"]) == 1


def test_e72a02_schedule_nasce_active_sem_rota_de_ativacao(cliente: TestClient) -> None:
    _, headers = _principal()
    sid, *_ = _criar(cliente, headers)
    lido = cliente.get(f"/api/v1/schedules/{sid}", headers=headers).json()["data"]
    assert lido["state"] == "active"
    assert "control_principal_ref" not in lido


# --- autenticação, escopo e cota --------------------------------------------


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer lixo"},
        {"Authorization": "Basic abc"},
        {"Authorization": f"Bearer {TOKEN_PREFIX}sem.ponto"},
    ],
)
def test_e72a03_credencial_ausente_ou_malformada_e_401_uniforme(cliente, headers) -> None:
    assert cliente.post("/api/v1/schedules", json=_corpo(), headers=headers).status_code == 401


@pytest.mark.parametrize("estado", ["revoked", "expired"])
def test_e72a04_credencial_revogada_ou_expirada_e_401(cliente, estado) -> None:
    _, headers = _principal(**{estado: True})
    assert cliente.post("/api/v1/schedules", json=_corpo(), headers=headers).status_code == 401


def test_e72a05_escopo_preditivo_sozinho_e_403_e_nao_produz_efeito(cliente) -> None:
    """`PREDICTIVE_SCOPE != ORCHESTRATION_SCOPE`."""
    _, headers = _principal(scopes=(SCOPE_PREDICTIVE_EVALUATE,))
    assert cliente.post("/api/v1/schedules", json=_corpo(), headers=headers).status_code == 403
    with engine.connect() as conexao:
        assert conexao.execute(sa.text("SELECT count(*) FROM schedules")).scalar_one() == 0
        assert (
            conexao.execute(sa.text("SELECT count(*) FROM programmatic_quota_buckets")).scalar_one()
            == 0
        )


def test_e72a06_a_cota_e7_usa_bucket_proprio(cliente) -> None:
    _, headers = _principal(scopes=(SCOPE_ORCHESTRATION_OPERATE, SCOPE_PREDICTIVE_EVALUATE))
    _criar(cliente, headers)
    with engine.connect() as conexao:
        operacoes = {
            linha[0]
            for linha in conexao.execute(
                sa.text("SELECT operation FROM programmatic_quota_buckets")
            )
        }
    assert operacoes == {OPERATION_ORCHESTRATION_API}
    assert OPERATION_PREDICTIVE_EVALUATE not in operacoes


def test_e72a07_cota_esgotada_e_429(cliente) -> None:
    _, headers = _principal(quota_limit=1)
    _criar(cliente, headers, "q1")
    assert cliente.get("/api/v1/schedules/" + str(uuid.uuid4()), headers=headers).status_code == 429


# --- isolamento -------------------------------------------------------------


def test_e72a08_principal_b_nao_alcanca_nada_do_principal_a(cliente) -> None:
    _, ha = _principal()
    _, hb = _principal()
    sid, s1, _ = _criar(cliente, ha)
    exportado = _exportar(cliente, ha, sid, s1, "e1").json()["data"]
    assert cliente.get(f"/api/v1/schedules/{sid}", headers=hb).status_code == 404
    assert cliente.get(f"/api/v1/schedules/{sid}/attempts", headers=hb).status_code == 404
    assert _exportar(cliente, hb, sid, s1, "eb").status_code == 404
    assert (
        _importar(cliente, hb, sid, s1, exportado["attempt_id"], "ib", "texto").status_code == 404
    )
    with engine.connect() as conexao:
        assert conexao.execute(sa.text("SELECT count(*) FROM handoff_results")).scalar_one() == 0


def test_e72a09_mesmo_principal_nao_cruza_dois_schedules(cliente) -> None:
    """`OWNER_BINDING != SCHEDULE_BINDING`, agora pela API."""
    _, headers = _principal()
    sid_a, sa1, _ = _criar(cliente, headers, "ca")
    sid_b, sb1, _ = _criar(cliente, headers, "cb")
    exportado = _exportar(cliente, headers, sid_b, sb1, "eb").json()["data"]
    antes = _snapshots()
    # attempt de B pelo path de A
    assert (
        _importar(cliente, headers, sid_a, sa1, exportado["attempt_id"], "ix", "texto").status_code
        == 404
    )
    # step de B pelo path de A
    assert _exportar(cliente, headers, sid_a, sb1, "ey").status_code == 404
    assert _snapshots() == antes


def test_e72a10_schedule_alheio_e_inexistente_produzem_o_mesmo_404(cliente) -> None:
    _, ha = _principal()
    _, hb = _principal()
    sid, *_ = _criar(cliente, ha)
    alheio = cliente.get(f"/api/v1/schedules/{sid}", headers=hb)
    inexistente = cliente.get(f"/api/v1/schedules/{uuid.uuid4()}", headers=hb)
    assert alheio.status_code == inexistente.status_code == 404
    assert alheio.json()["error"]["code"] == inexistente.json()["error"]["code"]


# --- REJECTED_RESULT BLOCKS ADVANCE, os dez passos --------------------------


def test_e72a11_resultado_rejeitado_bloqueia_avanco_prova_formal(cliente) -> None:
    """Prova em dez passos, isolando a REJEIÇÃO como causa do bloqueio.

    Bloquear a etapa 2 enquanto a tentativa da etapa 1 está `OPEN` não
    prova nada sobre rejeição: a tentativa aberta bloquearia igual. Aqui a
    tentativa está `CLOSED_REJECTED` quando o avanço é tentado.
    """
    _, headers = _principal()
    sid, s1, s2 = _criar(cliente, headers)

    # 1. exportar etapa 1
    exportado = _exportar(cliente, headers, sid, s1, "e1")
    assert exportado.status_code == 201
    attempt1 = exportado.json()["data"]["attempt_id"]

    # 2. importar retorno inválido
    importado = _importar(cliente, headers, sid, s1, attempt1, "i1", "   ")
    assert importado.status_code == 201
    corpo = importado.json()["data"]

    # 3, 4 e 5.
    assert corpo["result"]["status"] == "rejected"
    assert corpo["result"]["validation_codes"] == ["expected_non_empty_text"]
    assert corpo["attempt_state"] == "closed_rejected"
    assert corpo["step_state"] == "awaiting_return"

    # 6 e 7. Nenhuma tentativa OPEN existe: o bloqueio vem da rejeição.
    with engine.connect() as conexao:
        assert (
            conexao.execute(
                sa.text("SELECT count(*) FROM handoff_attempts WHERE state = 'open'")
            ).scalar_one()
            == 0
        )
    antes = _snapshots()
    bloqueado = _exportar(cliente, headers, sid, s2, "e2")
    assert bloqueado.status_code == 409

    # 8. snapshots inalterados após a recusa
    assert _snapshots() == antes

    # 9. retry da etapa 1 com nova chave
    retry = _exportar(cliente, headers, sid, s1, "e3")
    assert retry.status_code == 201
    attempt2 = retry.json()["data"]["attempt_id"]
    assert attempt2 != attempt1
    assert retry.json()["data"]["attempt_number"] == 2
    valido = _importar(cliente, headers, sid, s1, attempt2, "i2", "parecer completo")
    assert valido.json()["data"]["result"]["status"] == "validated"
    assert valido.json()["data"]["step_state"] == "returned"

    # 10. só agora a etapa 2 exporta — e por chamada EXPLÍCITA
    assert _exportar(cliente, headers, sid, s2, "e4").status_code == 201
    lido = cliente.get(f"/api/v1/schedules/{sid}", headers=headers).json()["data"]
    assert lido["state"] == "active", "Schedule não é marcado COMPLETED nesta entrega"


def test_e72a12_a_tentativa_rejeitada_e_seu_resultado_sobrevivem_ao_retry(cliente) -> None:
    """`RESULT_REJECTED != RESULT_DISCARDED`."""
    _, headers = _principal()
    sid, s1, _ = _criar(cliente, headers)
    a1 = _exportar(cliente, headers, sid, s1, "e1").json()["data"]["attempt_id"]
    _importar(cliente, headers, sid, s1, a1, "i1", "", inst="ia-1")
    a2 = _exportar(cliente, headers, sid, s1, "e2").json()["data"]["attempt_id"]
    _importar(cliente, headers, sid, s1, a2, "i2", "ok agora", inst="ia-2")
    itens = cliente.get(f"/api/v1/schedules/{sid}/attempts", headers=headers).json()["data"][
        "attempts"
    ]
    assert [i["result"]["status"] for i in itens] == ["rejected", "validated"]
    assert [i["attribution"]["declared_instance_id"] for i in itens] == ["ia-1", "ia-2"]
    assert [i["state"] for i in itens] == ["closed_rejected", "closed_ok"]


# --- idempotência -----------------------------------------------------------


def test_e72a13_replay_exato_nao_muda_snapshot_algum(cliente) -> None:
    _, headers = _principal()
    sid, s1, _ = _criar(cliente, headers)
    primeiro = _exportar(cliente, headers, sid, s1, "e1").json()["data"]
    antes = _snapshots()
    segundo = _exportar(cliente, headers, sid, s1, "e1").json()["data"]
    assert segundo["attempt_id"] == primeiro["attempt_id"]
    assert segundo["sealed_at"] == primeiro["sealed_at"]
    assert segundo["replayed"] is True and primeiro["replayed"] is False
    assert _snapshots() == antes


def test_e72a14_replay_de_criacao_devolve_o_mesmo_schedule_active(cliente) -> None:
    _, headers = _principal()
    sid, *_ = _criar(cliente, headers, "c1")
    antes = _snapshots()
    repetido = cliente.post("/api/v1/schedules", json=_corpo("c1"), headers=headers)
    assert repetido.status_code == 201
    assert repetido.json()["data"]["schedule_id"] == sid
    assert repetido.json()["data"]["state"] == "active"
    assert _snapshots() == antes


def test_e72a15_mesma_chave_em_path_divergente_recusa_sem_vazar(cliente) -> None:
    _, headers = _principal()
    sid, s1, s2 = _criar(cliente, headers)
    primeiro = _exportar(cliente, headers, sid, s1, "e1").json()["data"]
    antes = _snapshots()
    conflito = _exportar(cliente, headers, sid, s2, "e1")
    assert conflito.status_code == 409
    assert primeiro["attempt_id"] not in conflito.text
    assert _snapshots() == antes


def test_e72a16_mesma_chave_de_import_para_tentativa_divergente_recusa(cliente) -> None:
    _, headers = _principal()
    sid, s1, _ = _criar(cliente, headers)
    a1 = _exportar(cliente, headers, sid, s1, "e1").json()["data"]["attempt_id"]
    _importar(cliente, headers, sid, s1, a1, "i1", "primeiro parecer")
    a2 = _exportar(cliente, headers, sid, s1, "e2")
    assert a2.status_code == 409, "etapa RETURNED não admite novo export nesta entrega"
    antes = _snapshots()
    divergente = _importar(cliente, headers, sid, s1, str(uuid.uuid4()), "i1", "outro conteúdo")
    assert divergente.status_code == 409
    assert _snapshots() == antes


def test_e72a17_mesma_chave_em_principais_e_operacoes_diferentes_nao_colide(cliente) -> None:
    _, ha = _principal()
    _, hb = _principal()
    sid_a, sa1, _ = _criar(cliente, ha, "mesma")
    sid_b, _sb1, _ = _criar(cliente, hb, "mesma")
    assert sid_a != sid_b
    assert _exportar(cliente, ha, sid_a, sa1, "mesma").status_code == 201
    with engine.connect() as conexao:
        operacoes = {
            linha[0] for linha in conexao.execute(sa.text("SELECT operation FROM command_receipts"))
        }
    assert operacoes == {"orchestration.create_schedule", "orchestration.export_handoff"}


# --- conteúdo bruto e proveniência ------------------------------------------


def test_e72a18_conteudo_bruto_nunca_aparece_em_banco_resposta_ou_log(cliente, caplog) -> None:
    _, headers = _principal()
    sid, s1, _ = _criar(cliente, headers)
    with caplog.at_level("DEBUG"):
        a1 = _exportar(cliente, headers, sid, s1, "e1").json()["data"]["attempt_id"]
        importado = _importar(cliente, headers, sid, s1, a1, "i1", FRASE_ADVERSARIAL)
        listagem = cliente.get(f"/api/v1/schedules/{sid}/attempts", headers=headers)
    assert importado.json()["data"]["result"]["status"] == "validated"
    assert FRASE_ADVERSARIAL not in importado.text
    assert FRASE_ADVERSARIAL not in listagem.text
    assert FRASE_ADVERSARIAL not in caplog.text
    with engine.connect() as conexao:
        for tabela in ("handoff_results", "handoff_attributions"):
            linhas = [
                dict(linha._mapping)
                for linha in conexao.execute(sa.text(f"SELECT * FROM {tabela}"))
            ]
            assert FRASE_ADVERSARIAL not in json.dumps(linhas, default=str), tabela


def test_e72a19_as_colunas_persistidas_nao_admitem_conteudo(cliente) -> None:
    """Prova estrutural: a lista exata de colunas, não busca por substring."""
    with engine.connect() as conexao:
        colunas = {
            tabela: {
                linha[0]
                for linha in conexao.execute(
                    sa.text(
                        "SELECT column_name FROM information_schema.columns WHERE table_name = :t"
                    ),
                    {"t": tabela},
                )
            }
            for tabela in ("handoff_results", "handoff_attributions")
        }
    assert colunas["handoff_results"] == {
        "id",
        "attempt_id",
        "status",
        "expected_output_contract",
        "output_media_type",
        "output_sha256",
        "output_bytes",
        "declared_output_ref",
        "validation_codes",
        "created_at",
        "updated_at",
    }
    assert colunas["handoff_attributions"] == {
        "id",
        "attempt_id",
        "role",
        "declared_provider_id",
        "declared_model_id",
        "declared_instance_id",
        "declared_at",
        "self_declared",
        "provenance_record_ref",
        "created_at",
        "updated_at",
    }
    proibidas = {"content", "body", "raw_output", "response", "transcript", "prompt"}
    for tabela, nomes in colunas.items():
        assert not (nomes & proibidas), tabela


def test_e72a20_a_e7_nao_toca_proveniencia_nem_objetos_cognitivos(cliente) -> None:
    with engine.connect() as conexao:
        antes = (
            conexao.execute(sa.text("SELECT count(*) FROM provenance_records")).scalar_one(),
            conexao.execute(sa.text("SELECT count(*) FROM cognitive_objects")).scalar_one(),
        )
    _, headers = _principal()
    sid, s1, _ = _criar(cliente, headers)
    a1 = _exportar(cliente, headers, sid, s1, "e1").json()["data"]["attempt_id"]
    _importar(cliente, headers, sid, s1, a1, "i1", "parecer")
    with engine.connect() as conexao:
        depois = (
            conexao.execute(sa.text("SELECT count(*) FROM provenance_records")).scalar_one(),
            conexao.execute(sa.text("SELECT count(*) FROM cognitive_objects")).scalar_one(),
        )
        nao_nulos = conexao.execute(
            sa.text(
                "SELECT count(*) FROM handoff_attributions WHERE provenance_record_ref IS NOT NULL"
            )
        ).scalar_one()
    assert antes == depois
    assert nao_nulos == 0


def test_e72a21_campos_derivados_sao_recusados_na_entrada(cliente) -> None:
    _, headers = _principal()
    for extra in ("control_principal_ref", "sealer_ref", "state", "provenance_record_ref"):
        corpo = {**_corpo(f"x-{extra}"), extra: "injetado"}
        assert cliente.post("/api/v1/schedules", json=corpo, headers=headers).status_code == 422
    sid, s1, _ = _criar(cliente, headers)
    a1 = _exportar(cliente, headers, sid, s1, "e1").json()["data"]["attempt_id"]
    corpo_import = {
        "command_key": "z1",
        "attempt_id": a1,
        "output": {"media_type": "text/plain", "content": "ok"},
        "attribution": {"declared_instance_id": "i", "role": "forjado"},
    }
    resposta = cliente.post(
        f"/api/v1/schedules/{sid}/steps/{s1}/handoff-import", json=corpo_import, headers=headers
    )
    assert resposta.status_code == 422


# --- contratos, IAs e ausência de teto --------------------------------------


@pytest.mark.parametrize(
    ("contrato", "media", "content", "codigo"),
    [
        (OUTPUT_NON_EMPTY_TEXT_V1, "text/plain", "   ", "expected_non_empty_text"),
        (OUTPUT_NON_EMPTY_TEXT_V1, "application/json", "ok", "media_type_mismatch"),
        (OUTPUT_JSON_OBJECT_V1, "application/json", '["a"]', "expected_json_object"),
        (OUTPUT_JSON_OBJECT_V1, "application/json", "42", "expected_json_object"),
        (OUTPUT_JSON_OBJECT_V1, "application/json", '{"x": NaN}', "non_canonical_json_number"),
    ],
)
def test_e72a22_retorno_invalido_e_registrado_com_codigo(
    cliente, contrato, media, content, codigo
) -> None:
    _, headers = _principal()
    corpo = _corpo("cc")
    corpo["steps"] = [
        {"role": "r", "instruction_ref": "i://1", "expected_output_contract": contrato}
    ]
    criado = cliente.post("/api/v1/schedules", json=corpo, headers=headers).json()["data"]
    sid, step = criado["schedule_id"], criado["steps"][0]["step_id"]
    a1 = _exportar(cliente, headers, sid, step, "e1").json()["data"]["attempt_id"]
    resposta = _importar(cliente, headers, sid, step, a1, "i1", content, media=media)
    assert resposta.status_code == 201
    dados = resposta.json()["data"]
    assert dados["result"]["status"] == "rejected"
    assert dados["result"]["validation_codes"] == [codigo]
    assert dados["step_state"] == "awaiting_return"


def test_e72a23_contrato_desconhecido_e_422_na_criacao(cliente) -> None:
    _, headers = _principal()
    corpo = _corpo("cd")
    corpo["steps"] = [
        {"role": "r", "instruction_ref": "i://1", "expected_output_contract": "pia://inventado/v1"}
    ]
    assert cliente.post("/api/v1/schedules", json=corpo, headers=headers).status_code == 422
    with engine.connect() as conexao:
        assert conexao.execute(sa.text("SELECT count(*) FROM schedules")).scalar_one() == 0


def test_e72a24_muitas_etapas_e_muitas_ias_sem_teto_proprio(cliente) -> None:
    """`ROLE != PROVIDER != MODEL != INSTANCE`. Nenhum enum de marca."""
    _, headers = _principal()
    corpo = _corpo("cm")
    corpo["steps"] = [
        {
            "role": f"papel-{i}",
            "instruction_ref": f"i://{i}",
            "expected_output_contract": OUTPUT_NON_EMPTY_TEXT_V1,
        }
        for i in range(8)
    ]
    criado = cliente.post("/api/v1/schedules", json=corpo, headers=headers)
    assert criado.status_code == 201
    dados = criado.json()["data"]
    assert len(dados["steps"]) == 8
    sid = dados["schedule_id"]
    for indice, etapa in enumerate(dados["steps"]):
        attempt = _exportar(cliente, headers, sid, etapa["step_id"], f"e{indice}").json()["data"][
            "attempt_id"
        ]
        resposta = cliente.post(
            f"/api/v1/schedules/{sid}/steps/{etapa['step_id']}/handoff-import",
            json={
                "command_key": f"i{indice}",
                "attempt_id": attempt,
                "output": {"media_type": "text/plain", "content": f"resposta {indice}"},
                "attribution": {
                    "declared_provider_id": f"provedor-opaco-{indice}",
                    "declared_model_id": f"modelo-{indice}",
                    "declared_instance_id": f"instancia-{indice}",
                },
            },
            headers=headers,
        )
        assert resposta.status_code == 201, resposta.text
    itens = cliente.get(f"/api/v1/schedules/{sid}/attempts", headers=headers).json()["data"][
        "attempts"
    ]
    assert len({i["attribution"]["declared_provider_id"] for i in itens}) == 8
    assert {i["attribution"]["role"] for i in itens} == {f"papel-{i}" for i in range(8)}
    assert all(i["attribution"]["self_declared"] for i in itens)


# --- concorrência real ------------------------------------------------------


def _em_paralelo(alvo, quantidade: int = 2) -> list[object]:
    barreira = threading.Barrier(quantidade)
    resultados: list[object] = []
    erros: list[BaseException] = []

    def executar(indice: int) -> None:
        try:
            barreira.wait(timeout=15)
            resultados.append(alvo(indice))
        except BaseException as exc:  # noqa: BLE001 - o teste inspeciona
            erros.append(exc)

    linhas = [threading.Thread(target=executar, args=(i,)) for i in range(quantidade)]
    for linha in linhas:
        linha.start()
    for linha in linhas:
        linha.join(timeout=45)
    assert not erros, erros
    return resultados


def test_e72a25_exports_concorrentes_nao_abrem_duas_tentativas(cliente) -> None:
    _, headers = _principal()
    sid, s1, _ = _criar(cliente, headers)

    def exportar(indice: int) -> int:
        with TestClient(app) as paralelo:
            return _exportar(paralelo, headers, sid, s1, f"conc-{indice}").status_code

    codigos = sorted(_em_paralelo(exportar))
    with engine.connect() as conexao:
        abertas = conexao.execute(
            sa.text("SELECT count(*) FROM handoff_attempts WHERE state = 'open'")
        ).scalar_one()
        total = conexao.execute(sa.text("SELECT count(*) FROM handoff_attempts")).scalar_one()
    assert abertas <= 1
    assert total <= 1
    assert 201 in codigos


def test_e72a26_imports_concorrentes_produzem_um_resultado_e_uma_atribuicao(cliente) -> None:
    _, headers = _principal()
    sid, s1, _ = _criar(cliente, headers)
    a1 = _exportar(cliente, headers, sid, s1, "e1").json()["data"]["attempt_id"]

    def importar(indice: int) -> int:
        with TestClient(app) as paralelo:
            return _importar(
                paralelo, headers, sid, s1, a1, f"imp-{indice}", f"parecer {indice}"
            ).status_code

    _em_paralelo(importar)
    with engine.connect() as conexao:
        assert conexao.execute(sa.text("SELECT count(*) FROM handoff_results")).scalar_one() == 1
        assert (
            conexao.execute(sa.text("SELECT count(*) FROM handoff_attributions")).scalar_one() == 1
        )


# --- fronteira de sessão ----------------------------------------------------


def test_e72a27_todo_retorno_publico_e_dto_congelado_sem_orm(cliente) -> None:
    import dataclasses

    from app.orchestration.ports.transport import RawReturn
    from app.orchestration.repositories.orchestration_repository import OrchestrationRepository
    from app.orchestration.services.return_validation_service import (
        DeclaredAttribution,
        ReturnValidationService,
    )
    from app.repositories.unit_of_work import UnitOfWork

    _, headers = _principal()
    sid, s1, _ = _criar(cliente, headers)
    attempt = _exportar(cliente, headers, sid, s1, "e1").json()["data"]["attempt_id"]
    principal_ref = None
    with engine.connect() as conexao:
        principal_ref = conexao.execute(
            sa.text("SELECT control_principal_ref FROM schedules WHERE id = :i"), {"i": sid}
        ).scalar_one()
    with UnitOfWork() as uow:
        servico = ReturnValidationService(OrchestrationRepository(uow.session))
        saida = servico.import_return(
            control_principal_ref=principal_ref,
            schedule_id=uuid.UUID(sid),
            step_id=uuid.UUID(s1),
            attempt_id=uuid.UUID(attempt),
            raw=RawReturn(media_type="text/plain", content="fora da sessão"),
            attribution=DeclaredAttribution(declared_instance_id="i-1"),
        )
        uow.commit()
    assert dataclasses.is_dataclass(saida)
    assert type(saida).__dataclass_params__.frozen
    assert not hasattr(saida, "_sa_instance_state")
    for campo in dataclasses.fields(saida):
        getattr(saida, campo.name)
    assert saida.provenance_record_ref is None


def test_e72a28_a_documentacao_openapi_publica_as_cinco_rotas(cliente) -> None:
    esquema = cliente.get("/openapi.json").json()
    caminhos = {p for p in esquema["paths"] if p.startswith("/api/v1/schedules")}
    # ATUALIZADO PELA E7.3: as cinco rotas da E7.2 continuam presentes e
    # inalteradas; a E7.3 acrescentou cinco. A guarda mede INCLUSÃO da
    # superfície da E7.2, não imobilidade do router — as rotas novas têm
    # guarda própria em `test_e72_orchestration_boundary.py`.
    assert {
        "/api/v1/schedules",
        "/api/v1/schedules/{schedule_id}",
        "/api/v1/schedules/{schedule_id}/attempts",
        "/api/v1/schedules/{schedule_id}/steps/{step_id}/handoff-export",
        "/api/v1/schedules/{schedule_id}/steps/{step_id}/handoff-import",
    } <= caminhos
    for caminho, operacoes in esquema["paths"].items():
        if not caminho.startswith("/api/v1/schedules"):
            continue
        for operacao in operacoes.values():
            assert operacao.get("security"), caminho
            assert set(operacao["responses"]) >= {"401", "403", "404", "409", "422", "429", "503"}
    # Medido sobre as PROPRIEDADES dos schemas, não sobre o texto: a
    # docstring do DTO explica por que `control_principal_ref` não é
    # exposto, e uma busca por substring confundiria a explicação com o
    # campo.
    proibidos = {"control_principal_ref", "sealer_ref", "credential", "secret", "token"}
    for nome, definicao in esquema["components"]["schemas"].items():
        if not nome.startswith(
            (
                "Schedule",
                "Step",
                "Envelope",
                "Attempt",
                "Result",
                "Attribution",
                "ContextRef",
                "CreateSchedule",
                "ExportHandoff",
                "ImportReturn",
                "Return",
            )
        ):
            continue
        propriedades = set(definicao.get("properties", {}))
        assert not (propriedades & proibidos), f"{nome}: {sorted(propriedades & proibidos)}"


# --- corretivo R1: idempotência de importação e redação do 422 --------------


def test_e72a29_replay_exato_de_importacao_nao_repete_o_efeito(cliente) -> None:
    """Achado C1: `CLAIM_DETECTION_BY_OUTCOME_REF = BROKEN`.

    Em `IMPORT_RETURN` o `outcome_ref` proposto é o `attempt_id` que o
    **cliente** enviou. No replay exato o recibo existente tem o mesmo
    valor, e comparar `outcome_ref` classificava recuperação como
    inserção — o efeito rodava de novo. A detecção passou a usar a
    identidade do recibo proposto.
    """
    _, headers = _principal()
    sid, s1, _ = _criar(cliente, headers)
    attempt = _exportar(cliente, headers, sid, s1, "e1").json()["data"]["attempt_id"]
    primeiro = _importar(cliente, headers, sid, s1, attempt, "i1", "parecer completo")
    assert primeiro.status_code == 201
    assert primeiro.json()["data"]["replayed"] is False
    antes = _snapshots()
    segundo = _importar(cliente, headers, sid, s1, attempt, "i1", "parecer completo")
    assert segundo.status_code == 201
    assert segundo.json()["data"]["replayed"] is True
    assert segundo.json()["data"]["result"] == primeiro.json()["data"]["result"]
    assert segundo.json()["data"]["attribution"] == primeiro.json()["data"]["attribution"]
    assert _snapshots() == antes
    with engine.connect() as conexao:
        assert conexao.execute(sa.text("SELECT count(*) FROM handoff_results")).scalar_one() == 1
        assert (
            conexao.execute(sa.text("SELECT count(*) FROM handoff_attributions")).scalar_one() == 1
        )


def test_e72a30_replay_concorrente_de_importacao_produz_um_unico_efeito(cliente) -> None:
    _, headers = _principal()
    sid, s1, _ = _criar(cliente, headers)
    attempt = _exportar(cliente, headers, sid, s1, "e1").json()["data"]["attempt_id"]

    def importar(_indice: int) -> int:
        with TestClient(app) as paralelo:
            return _importar(paralelo, headers, sid, s1, attempt, "mesma", "parecer").status_code

    codigos = _em_paralelo(importar)
    assert codigos == [201, 201]
    with engine.connect() as conexao:
        assert conexao.execute(sa.text("SELECT count(*) FROM handoff_results")).scalar_one() == 1
        assert (
            conexao.execute(sa.text("SELECT count(*) FROM handoff_attributions")).scalar_one() == 1
        )
        # create + export + UM import: as duas requisições concorrentes
        # compartilham a mesma tripla e portanto o mesmo recibo.
        importacoes = conexao.execute(
            sa.text(
                "SELECT count(*) FROM command_receipts WHERE operation = "
                "'orchestration.import_return'"
            )
        ).scalar_one()
    assert importacoes == 1


@pytest.mark.parametrize(
    "divergencia",
    ["conteudo", "media_type", "atribuicao", "output_ref"],
)
def test_e72a31_mesma_chave_com_requisicao_divergente_recusa(cliente, divergencia) -> None:
    """`SAME_COMMAND_KEY + DIFFERENT_REQUEST = CONFLICT`."""
    _, headers = _principal()
    sid, s1, _ = _criar(cliente, headers)
    attempt = _exportar(cliente, headers, sid, s1, "e1").json()["data"]["attempt_id"]
    base = {
        "command_key": "i1",
        "attempt_id": attempt,
        "output": {"media_type": "text/plain", "content": "parecer"},
        "attribution": {"declared_instance_id": "inst-1"},
    }
    rota = f"/api/v1/schedules/{sid}/steps/{s1}/handoff-import"
    assert cliente.post(rota, json=base, headers=headers).status_code == 201
    antes = _snapshots()
    alterado = json.loads(json.dumps(base))
    if divergencia == "conteudo":
        alterado["output"]["content"] = "outro parecer"
    elif divergencia == "media_type":
        alterado["output"]["media_type"] = "application/json"
    elif divergencia == "atribuicao":
        alterado["attribution"]["declared_instance_id"] = "inst-2"
    else:
        alterado["output"]["declared_output_ref"] = "artefato://x"
    conflito = cliente.post(rota, json=alterado, headers=headers)
    assert conflito.status_code == 409
    assert _snapshots() == antes


def test_e72a32_mesma_chave_de_criacao_com_composicao_divergente_recusa(cliente) -> None:
    _, headers = _principal()
    _criar(cliente, headers, "c1")
    antes = _snapshots()
    divergente = _corpo("c1")
    divergente["title"] = "outro título"
    assert cliente.post("/api/v1/schedules", json=divergente, headers=headers).status_code == 409
    assert _snapshots() == antes


def test_e72a33_mesma_chave_de_import_sob_outro_step_nao_revela_o_recurso(cliente) -> None:
    _, headers = _principal()
    sid, s1, s2 = _criar(cliente, headers)
    attempt = _exportar(cliente, headers, sid, s1, "e1").json()["data"]["attempt_id"]
    _importar(cliente, headers, sid, s1, attempt, "i1", "parecer")
    antes = _snapshots()
    cruzado = _importar(cliente, headers, sid, s2, attempt, "i1", "parecer")
    assert cruzado.status_code == 409
    assert attempt not in cruzado.text
    assert _snapshots() == antes


def test_e72a34_o_422_de_validacao_nao_ecoa_o_conteudo_bruto(cliente, caplog) -> None:
    """Achado C2: `RequestValidationError.errors()` inclui `input`.

    ```text
    RAW_OUTPUT_IN_RESPONSE = FORBIDDEN
    RAW_OUTPUT_IN_APPLICATION_LOG = FORBIDDEN
    DIAGNOSTIC_LOCATION != DIAGNOSTIC_VALUE
    ```

    O 422 continua dizendo QUAL campo falhou e POR QUÊ; some apenas o
    valor enviado.
    """
    marcador = "MARCADOR-SECRETO-9f3a5b"
    _, headers = _principal()
    sid, s1, _ = _criar(cliente, headers)
    attempt = _exportar(cliente, headers, sid, s1, "e1").json()["data"]["attempt_id"]
    malformado = {
        "command_key": "i1",
        "attempt_id": attempt,
        "output": {"media_type": "text/plain", "content": {"objeto": marcador}},
        "attribution": {"declared_instance_id": "inst"},
    }
    with caplog.at_level("DEBUG"):
        resposta = cliente.post(
            f"/api/v1/schedules/{sid}/steps/{s1}/handoff-import",
            json=malformado,
            headers=headers,
        )
    assert resposta.status_code == 422
    assert marcador not in resposta.text
    assert marcador not in caplog.text
    for registro in caplog.records:
        assert marcador not in json.dumps(registro.__dict__, default=str)
    corpo = resposta.json()["error"]
    assert corpo["code"] == "PIA-2001"
    # O diagnóstico sobrevive: localização e mensagem continuam presentes.
    assert any("content" in str(item.get("loc", "")) for item in corpo["details"]["value"])
    for item in corpo["details"]["value"]:
        assert set(item) <= {"type", "loc", "msg"}


def test_e72a35_a_reconstrucao_confere_attempt_contra_step_explicitamente() -> None:
    """Defesa em profundidade, provada no ponto onde vive.

    ```text
    FINGERPRINT_FIRST != ATTEMPT_STEP_BINDING
    ```

    Depois do corretivo C1, a impressão digital da requisição recusa
    `command_key` reusada sob outro Step **antes** de a reconstrução
    rodar, porque `schedule_id` e `step_id` entram na digital do export.
    O vínculo `tentativa.step_id == step_id` passou a ser inalcançável
    por HTTP — e continua obrigatório: ele é a última linha caso a
    digital mude, e remover uma guarda porque outra chegou primeiro
    deixa o sistema com uma proteção só onde havia duas.

    Como nenhuma requisição alcança o ramo, a prova chama o caminho de
    reconstrução diretamente. Um teste que não consegue reproduzir a
    condição por fora não é motivo para deixar a condição sem prova.
    """
    from app.orchestration.errors.exceptions import OrchestrationLifecycleViolationError
    from app.orchestration.repositories.orchestration_repository import OrchestrationRepository
    from app.repositories.unit_of_work import UnitOfWork
    from app.routers.orchestration import _resposta_export

    with TestClient(app) as cliente:
        _, headers = _principal()
        sid, s1, s2 = _criar(cliente, headers)
        exportado = _exportar(cliente, headers, sid, s1, "e1").json()["data"]

    class _ReciboFalso:
        outcome_ref = exportado["attempt_id"]
        replayed = True

    with UnitOfWork() as uow:
        repositorio = OrchestrationRepository(uow.session)
        principal_ref = uow.session.execute(
            sa.text("SELECT control_principal_ref FROM schedules WHERE id = :i"),
            {"i": sid},
        ).scalar_one()
        # Step certo: reconstrói.
        assert _resposta_export(
            repositorio=repositorio,
            principal_ref=principal_ref,
            schedule_id=uuid.UUID(sid),
            step_id=uuid.UUID(s1),
            recibo=_ReciboFalso(),
            saida=None,
        ).attempt_id == uuid.UUID(exportado["attempt_id"])
        # Step de outra etapa do MESMO Schedule: recusa.
        with pytest.raises(OrchestrationLifecycleViolationError):
            _resposta_export(
                repositorio=repositorio,
                principal_ref=principal_ref,
                schedule_id=uuid.UUID(sid),
                step_id=uuid.UUID(s2),
                recibo=_ReciboFalso(),
                saida=None,
            )
