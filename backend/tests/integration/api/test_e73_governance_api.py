"""
Governança da E7.3 por HTTP real (`Chain116`).

```text
BLOCKED_GATE_PERSISTS_PAUSE_WITH_ZERO_COMMAND_EFFECT
GUARD_DOMINATES transport.export()
CANCELLED | STOPPED | PAUSED -> ZERO TRANSPORT
AUDITOR_WRITE_ON_AUDITED_ARTIFACT = FORBIDDEN
```
"""

import json
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from app.database.engine import engine
from app.database.health import check_database_health
from app.database.session import SessionLocal
from app.models.programmatic_service_principal import SCOPE_ORCHESTRATION_OPERATE
from app.orchestration.schemas.output_contract import OUTPUT_NON_EMPTY_TEXT_V1
from app.repositories.programmatic_access_repository import ProgrammaticAccessRepository
from app.security.programmatic_access import TOKEN_PREFIX, compute_secret_digest
from main import app

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not check_database_health().available,
        reason="PostgreSQL real indisponível — gate, delegação e triggers são a prova.",
    ),
]

GATE_TECNICO = {"pia.gate.required": "service_delegation", "pia.gate.scope": "dispatch"}
GATE_HUMANO = {
    "pia.gate.required": "service_delegation_and_human",
    "pia.gate.scope": "dispatch",
}
_APPEND_ONLY = (
    "audit_opinions",
    "execution_observations",
    "orchestration_control_events",
    "handoff_results",
    "handoff_attributions",
    "seal_receipts",
    "service_delegations",
)


def _limpar() -> None:
    with engine.begin() as conexao:
        for tabela in _APPEND_ONLY:
            conexao.execute(sa.text(f"ALTER TABLE {tabela} DISABLE TRIGGER USER"))
            conexao.execute(sa.text(f"DELETE FROM {tabela}"))
            conexao.execute(sa.text(f"ALTER TABLE {tabela} ENABLE TRIGGER USER"))
        for tabela in (
            "handoff_attempts",
            "schedule_steps",
            "schedules",
            "command_receipts",
            "programmatic_quota_buckets",
            "programmatic_service_principals",
        ):
            conexao.execute(sa.text(f"DELETE FROM {tabela}"))


@pytest.fixture(autouse=True)
def _base_limpa():
    _limpar()
    yield
    _limpar()


@pytest.fixture
def cliente() -> TestClient:
    return TestClient(app)


def _principal() -> dict[str, str]:
    key_id = f"kid-{uuid.uuid4().hex[:16]}"
    secret = f"secret-{uuid.uuid4().hex}"
    with SessionLocal() as sessao:
        ProgrammaticAccessRepository(sessao).create_principal(
            key_id=key_id,
            secret_digest=compute_secret_digest(key_id, secret),
            scopes=(SCOPE_ORCHESTRATION_OPERATE,),
            quota_limit=900,
            quota_window_seconds=3600,
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
        sessao.commit()
    return {"Authorization": f"Bearer {TOKEN_PREFIX}{key_id}.{secret}"}


def _criar(cliente, headers, constraints, chave="c1"):
    corpo = {
        "command_key": chave,
        "title": "t",
        "steps": [
            {
                "role": "r",
                "instruction_ref": "i://1",
                "expected_output_contract": OUTPUT_NON_EMPTY_TEXT_V1,
                "constraints": constraints,
            }
        ],
    }
    resposta = cliente.post("/api/v1/schedules", json=corpo, headers=headers)
    assert resposta.status_code == 201, resposta.text
    dados = resposta.json()["data"]
    return dados["schedule_id"], dados["steps"][0]["step_id"]


def _contar(consulta: str) -> int:
    with engine.connect() as conexao:
        return int(conexao.execute(sa.text(consulta)).scalar_one())


def _exportar(cliente, headers, sid, step, chave):
    return cliente.post(
        f"/api/v1/schedules/{sid}/steps/{step}/handoff-export",
        json={"command_key": chave},
        headers=headers,
    )


def _grant(cliente, headers, sid, step, chave="g1", horas=1):
    return cliente.post(
        f"/api/v1/schedules/{sid}/steps/{step}/delegations",
        json={
            "command_key": chave,
            "valid_until": (datetime.now(UTC) + timedelta(hours=horas)).isoformat(),
        },
        headers=headers,
    )


def _controle(cliente, headers, sid, action, chave, categoria=None):
    corpo = {"command_key": chave, "action": action}
    if categoria is not None:
        corpo["stop_condition_category"] = categoria
    return cliente.post(f"/api/v1/schedules/{sid}/control-events", json=corpo, headers=headers)


# --- caminho bloqueado: o coração do addendum -------------------------------


def test_e73a01_gate_sem_delegacao_pausa_e_nao_produz_efeito_algum(cliente) -> None:
    """`BLOCKED_GATE_PERSISTS_PAUSE_WITH_ZERO_COMMAND_EFFECT`.

    A pausa é commitada **antes** do 409. Dentro do bloco genérico que faz
    `rollback`, ela seria apagada — e o teste provaria o contrário do que
    o sistema faz.
    """
    headers = _principal()
    sid, step = _criar(cliente, headers, GATE_TECNICO)
    recibos_antes = _contar(
        "SELECT count(*) FROM command_receipts WHERE operation = 'orchestration.export_handoff'"
    )

    resposta = _exportar(cliente, headers, sid, step, "e1")

    assert resposta.status_code == 409
    assert resposta.json()["error"]["code"] == "PIA-8062"
    assert _contar(f"SELECT count(*) FROM schedules WHERE id = '{sid}' AND state = 'paused'") == 1
    assert _contar("SELECT count(*) FROM orchestration_control_events") == 1
    assert (
        _contar(
            "SELECT count(*) FROM command_receipts "
            "WHERE operation = 'orchestration.export_handoff'"
        )
        == recibos_antes
    )
    assert _contar("SELECT count(*) FROM handoff_attempts") == 0
    assert _contar("SELECT count(*) FROM seal_receipts") == 0
    with engine.connect() as conexao:
        motivo = conexao.execute(
            sa.text("SELECT reason_code FROM orchestration_control_events")
        ).scalar_one()
    assert motivo == "delegation_missing"


def test_e73a02_repetir_enquanto_pausado_nao_duplica_evento(cliente) -> None:
    headers = _principal()
    sid, step = _criar(cliente, headers, GATE_TECNICO)
    assert _exportar(cliente, headers, sid, step, "e1").status_code == 409
    assert _exportar(cliente, headers, sid, step, "e2").status_code == 409
    assert _contar("SELECT count(*) FROM orchestration_control_events") == 1


def test_e73a03_a_mesma_command_key_bloqueada_executa_apos_grant_e_resume(cliente) -> None:
    """Nenhum recibo foi criado no bloqueio, então a chave continua livre."""
    headers = _principal()
    sid, step = _criar(cliente, headers, GATE_TECNICO)
    assert _exportar(cliente, headers, sid, step, "e1").status_code == 409
    assert _grant(cliente, headers, sid, step).status_code == 201
    assert _controle(cliente, headers, sid, "resume", "r1").status_code == 201
    liberado = _exportar(cliente, headers, sid, step, "e1")
    assert liberado.status_code == 201
    assert liberado.json()["data"]["step_state"] == "awaiting_return"
    assert _contar("SELECT count(*) FROM service_delegations WHERE state = 'consumed'") == 1
    assert _contar("SELECT count(*) FROM handoff_attempts") == 1


def test_e73a04_gate_humano_nega_em_producao(cliente) -> None:
    """`HUMAN_GATE_IN_PRODUCTION = DENY_ALL_UNTIL_E8`.

    Mesmo com delegação técnica válida concedida, o componente humano
    recusa — e nenhum principal técnico o satisfaz.
    """
    headers = _principal()
    sid, step = _criar(cliente, headers, GATE_HUMANO)
    assert _grant(cliente, headers, sid, step).status_code == 201
    assert _controle(cliente, headers, sid, "resume", "r0").status_code in (201, 409)
    resposta = _exportar(cliente, headers, sid, step, "e1")
    assert resposta.status_code == 409
    with engine.connect() as conexao:
        motivos = {
            linha[0]
            for linha in conexao.execute(
                sa.text("SELECT reason_code FROM orchestration_control_events")
            )
        }
    assert "human_gate_unavailable" in motivos
    assert _contar("SELECT count(*) FROM handoff_attempts") == 0


def test_e73a05_etapa_sem_gate_permanece_retrocompativel(cliente) -> None:
    """`ABSENT_GATE_MARKER` = despacha como antes, sem delegação."""
    headers = _principal()
    sid, step = _criar(cliente, headers, {})
    assert _exportar(cliente, headers, sid, step, "e1").status_code == 201
    assert _contar("SELECT count(*) FROM orchestration_control_events") == 0
    assert _contar("SELECT count(*) FROM service_delegations") == 0


# --- delegação --------------------------------------------------------------


def test_e73a06_hash_alterado_invalida_a_delegacao(cliente) -> None:
    """`CONTENT_HASH_CHANGED -> INVALID`, estrutural e não verificado."""
    headers = _principal()
    sid, step = _criar(cliente, headers, GATE_TECNICO)
    assert _grant(cliente, headers, sid, step).status_code == 201
    with engine.begin() as conexao:
        conexao.execute(
            sa.text("UPDATE schedule_steps SET instruction_ref = 'i://mudou' WHERE id = :p"),
            {"p": step},
        )
    resposta = _exportar(cliente, headers, sid, step, "e1")
    assert resposta.status_code == 409
    with engine.connect() as conexao:
        motivos = [
            linha[0]
            for linha in conexao.execute(
                sa.text("SELECT reason_code FROM orchestration_control_events")
            )
        ]
    assert "delegation_content_changed" in motivos
    assert _contar("SELECT count(*) FROM handoff_attempts") == 0


def test_e73a07_delegacao_expirada_bloqueia_e_e_materializada(cliente) -> None:
    headers = _principal()
    sid, step = _criar(cliente, headers, GATE_TECNICO)
    assert _grant(cliente, headers, sid, step).status_code == 201
    # `valid_until` é parte do binding IMUTÁVEL — o trigger recusa o UPDATE,
    # e é assim que deve ser. Para simular passagem de tempo sem relógio
    # injetável, a trigger é desabilitada só nesta preparação.
    with engine.begin() as conexao:
        conexao.execute(sa.text("ALTER TABLE service_delegations DISABLE TRIGGER USER"))
        conexao.execute(
            sa.text("UPDATE service_delegations SET valid_until = now() - interval '1 second'")
        )
        conexao.execute(sa.text("ALTER TABLE service_delegations ENABLE TRIGGER USER"))
    assert _exportar(cliente, headers, sid, step, "e1").status_code == 409
    assert _contar("SELECT count(*) FROM service_delegations WHERE state = 'expired'") == 1


def test_e73a08_delegacao_e_de_uso_unico(cliente) -> None:
    headers = _principal()
    sid, step = _criar(cliente, headers, GATE_TECNICO)
    _grant(cliente, headers, sid, step)
    _controle(cliente, headers, sid, "resume", "r1")
    primeiro = _exportar(cliente, headers, sid, step, "e1")
    assert primeiro.status_code == 201
    attempt = primeiro.json()["data"]["attempt_id"]
    corpo = {
        "command_key": "i1",
        "attempt_id": attempt,
        "output": {"media_type": "text/plain", "content": "   "},
        "attribution": {"declared_instance_id": "i1"},
    }
    assert (
        cliente.post(
            f"/api/v1/schedules/{sid}/steps/{step}/handoff-import", json=corpo, headers=headers
        ).json()["data"]["result"]["status"]
        == "rejected"
    )
    # Retry com chave nova: a delegação já foi consumida, então bloqueia.
    assert _exportar(cliente, headers, sid, step, "e2").status_code == 409
    assert _contar("SELECT count(*) FROM service_delegations WHERE state = 'consumed'") == 1


def test_e73a09_delegacao_revogada_bloqueia(cliente) -> None:
    headers = _principal()
    sid, step = _criar(cliente, headers, GATE_TECNICO)
    concedida = _grant(cliente, headers, sid, step).json()["data"]["delegation"]
    _controle(cliente, headers, sid, "resume", "r1")
    revogada = cliente.post(
        f"/api/v1/schedules/{sid}/steps/{step}/delegations/{concedida['delegation_id']}/revoke",
        json={"command_key": "rv1"},
        headers=headers,
    )
    assert revogada.status_code == 200
    assert revogada.json()["data"]["delegation"]["state"] == "revoked"
    assert _exportar(cliente, headers, sid, step, "e1").status_code == 409


def test_e73a10_etapa_sem_gate_nao_admite_delegacao(cliente) -> None:
    headers = _principal()
    sid, step = _criar(cliente, headers, {})
    assert _grant(cliente, headers, sid, step).status_code == 422


# --- controle cooperativo ---------------------------------------------------


@pytest.mark.parametrize("acao", ["stop", "cancel"])
def test_e73a11_terminal_nao_despacha_e_nao_grava_de_novo(cliente, acao) -> None:
    """`CANCELLED | STOPPED -> ZERO TRANSPORT`, sem nova escrita."""
    headers = _principal()
    sid, step = _criar(cliente, headers, {})
    categoria = "missing_authority" if acao == "stop" else None
    assert _controle(cliente, headers, sid, acao, "k1", categoria).status_code == 201
    eventos = _contar("SELECT count(*) FROM orchestration_control_events")
    assert _exportar(cliente, headers, sid, step, "e1").status_code == 409
    assert _contar("SELECT count(*) FROM orchestration_control_events") == eventos
    assert _contar("SELECT count(*) FROM handoff_attempts") == 0


def test_e73a12_cancelamento_fecha_tentativas_abertas_e_preserva_returned(cliente) -> None:
    headers = _principal()
    corpo = {
        "command_key": "c1",
        "title": "t",
        "steps": [
            {
                "role": f"r{i}",
                "instruction_ref": f"i://{i}",
                "expected_output_contract": OUTPUT_NON_EMPTY_TEXT_V1,
            }
            for i in range(2)
        ],
    }
    dados = cliente.post("/api/v1/schedules", json=corpo, headers=headers).json()["data"]
    sid = dados["schedule_id"]
    s1, s2 = dados["steps"][0]["step_id"], dados["steps"][1]["step_id"]
    attempt = _exportar(cliente, headers, sid, s1, "e1").json()["data"]["attempt_id"]
    cliente.post(
        f"/api/v1/schedules/{sid}/steps/{s1}/handoff-import",
        json={
            "command_key": "i1",
            "attempt_id": attempt,
            "output": {"media_type": "text/plain", "content": "ok"},
            "attribution": {"declared_instance_id": "i1"},
        },
        headers=headers,
    )
    aberta = _exportar(cliente, headers, sid, s2, "e2")
    assert aberta.status_code == 201
    resposta = _controle(cliente, headers, sid, "cancel", "k1")
    assert resposta.status_code == 201
    dados = resposta.json()["data"]
    assert dados["closed_attempts"] == 1
    assert _contar("SELECT count(*) FROM handoff_attempts WHERE state = 'open'") == 0
    assert _contar("SELECT count(*) FROM handoff_attempts WHERE state = 'closed_cancelled'") == 1
    assert _contar("SELECT count(*) FROM schedule_steps WHERE state = 'returned'") == 1
    assert _contar("SELECT count(*) FROM schedule_steps WHERE state = 'cancelled'") == 1


def test_e73a13_pausa_exige_retomada_explicita(cliente) -> None:
    headers = _principal()
    sid, step = _criar(cliente, headers, {})
    assert _controle(cliente, headers, sid, "pause", "k1").status_code == 201
    assert _exportar(cliente, headers, sid, step, "e1").status_code == 409
    assert _controle(cliente, headers, sid, "resume", "k2").status_code == 201
    assert _exportar(cliente, headers, sid, step, "e1").status_code == 201


def test_e73a14_stop_exige_categoria_e_categoria_exige_stop(cliente) -> None:
    headers = _principal()
    sid, _ = _criar(cliente, headers, {})
    assert _controle(cliente, headers, sid, "stop", "k1").status_code == 422
    assert _controle(cliente, headers, sid, "pause", "k2", "missing_authority").status_code == 422


# --- conclusão --------------------------------------------------------------


def test_e73a15_validado_final_completa_e_rejeitado_nao(cliente) -> None:
    """`VALIDATED_FINAL_RESULT -> COMPLETED, NO AUTOEXPORT`."""
    headers = _principal()
    sid, step = _criar(cliente, headers, {})
    attempt = _exportar(cliente, headers, sid, step, "e1").json()["data"]["attempt_id"]
    rejeitado = cliente.post(
        f"/api/v1/schedules/{sid}/steps/{step}/handoff-import",
        json={
            "command_key": "i1",
            "attempt_id": attempt,
            "output": {"media_type": "text/plain", "content": "   "},
            "attribution": {"declared_instance_id": "i1"},
        },
        headers=headers,
    )
    assert rejeitado.json()["data"]["result"]["status"] == "rejected"
    assert _contar(f"SELECT count(*) FROM schedules WHERE id='{sid}' AND state='active'") == 1

    attempt2 = _exportar(cliente, headers, sid, step, "e2").json()["data"]["attempt_id"]
    validado = cliente.post(
        f"/api/v1/schedules/{sid}/steps/{step}/handoff-import",
        json={
            "command_key": "i2",
            "attempt_id": attempt2,
            "output": {"media_type": "text/plain", "content": "aprovado, prossiga"},
            "attribution": {"declared_instance_id": "i2"},
        },
        headers=headers,
    )
    assert validado.json()["data"]["result"]["status"] == "validated"
    assert _contar(f"SELECT count(*) FROM schedules WHERE id='{sid}' AND state='completed'") == 1
    # Texto instrucional não exportou nada nem criou etapa.
    assert _contar("SELECT count(*) FROM handoff_attempts") == 2


# --- observação de provedor -------------------------------------------------


def test_e73a16_troca_declarada_de_provedor_gera_uma_observacao(cliente) -> None:
    """`NO_SILENT_PROVIDER_SWITCH`, sem sobrescrever a atribuição."""
    headers = _principal()
    sid, step = _criar(cliente, headers, {})
    a1 = _exportar(cliente, headers, sid, step, "e1").json()["data"]["attempt_id"]
    cliente.post(
        f"/api/v1/schedules/{sid}/steps/{step}/handoff-import",
        json={
            "command_key": "i1",
            "attempt_id": a1,
            "output": {"media_type": "text/plain", "content": "   "},
            "attribution": {"declared_instance_id": "i1", "declared_provider_id": "prov-a"},
        },
        headers=headers,
    )
    a2 = _exportar(cliente, headers, sid, step, "e2").json()["data"]["attempt_id"]
    cliente.post(
        f"/api/v1/schedules/{sid}/steps/{step}/handoff-import",
        json={
            "command_key": "i2",
            "attempt_id": a2,
            "output": {"media_type": "text/plain", "content": "ok"},
            "attribution": {"declared_instance_id": "i2", "declared_provider_id": "prov-b"},
        },
        headers=headers,
    )
    assert _contar("SELECT count(*) FROM execution_observations") == 1
    assert _contar("SELECT count(*) FROM handoff_attributions") == 2
    with engine.connect() as conexao:
        linha = conexao.execute(
            sa.text(
                "SELECT previous_declared_provider_id, current_declared_provider_id, "
                "self_declared FROM execution_observations"
            )
        ).one()
    assert linha == ("prov-a", "prov-b", True)


def test_e73a17_mesmo_provedor_nao_gera_observacao(cliente) -> None:
    headers = _principal()
    sid, step = _criar(cliente, headers, {})
    for indice, chave in enumerate(("e1", "e2")):
        attempt = _exportar(cliente, headers, sid, step, chave).json()["data"]["attempt_id"]
        cliente.post(
            f"/api/v1/schedules/{sid}/steps/{step}/handoff-import",
            json={
                "command_key": f"i{indice}",
                "attempt_id": attempt,
                "output": {"media_type": "text/plain", "content": "   " if indice == 0 else "ok"},
                "attribution": {"declared_instance_id": "i", "declared_provider_id": "prov-a"},
            },
            headers=headers,
        )
    assert _contar("SELECT count(*) FROM execution_observations") == 0


# --- auditoria --------------------------------------------------------------


def test_e73a18_parecer_negativo_preserva_o_resultado(cliente) -> None:
    headers = _principal()
    sid, step = _criar(cliente, headers, {})
    attempt = _exportar(cliente, headers, sid, step, "e1").json()["data"]["attempt_id"]
    cliente.post(
        f"/api/v1/schedules/{sid}/steps/{step}/handoff-import",
        json={
            "command_key": "i1",
            "attempt_id": attempt,
            "output": {"media_type": "text/plain", "content": "parecer"},
            "attribution": {"declared_instance_id": "i1"},
        },
        headers=headers,
    )
    with engine.connect() as conexao:
        antes = [
            tuple(linha)
            for linha in conexao.execute(
                sa.text("SELECT id, status, output_sha256, updated_at FROM handoff_results")
            )
        ]
    resposta = cliente.post(
        f"/api/v1/schedules/{sid}/attempts/{attempt}/audit-opinions",
        json={
            "command_key": "a1",
            "opinion": "dissent",
            "reason_codes": ["contract_nonconformity"],
            "auditor_execution_ref": "exec-1",
        },
        headers=headers,
    )
    assert resposta.status_code == 201
    with engine.connect() as conexao:
        depois = [
            tuple(linha)
            for linha in conexao.execute(
                sa.text("SELECT id, status, output_sha256, updated_at FROM handoff_results")
            )
        ]
    assert antes == depois


def test_e73a19_pareceres_independentes_coexistem(cliente) -> None:
    headers = _principal()
    sid, step = _criar(cliente, headers, {})
    attempt = _exportar(cliente, headers, sid, step, "e1").json()["data"]["attempt_id"]
    cliente.post(
        f"/api/v1/schedules/{sid}/steps/{step}/handoff-import",
        json={
            "command_key": "i1",
            "attempt_id": attempt,
            "output": {"media_type": "text/plain", "content": "parecer"},
            "attribution": {"declared_instance_id": "i1"},
        },
        headers=headers,
    )
    for chave, opiniao, motivo in (
        ("a1", "concur", "contract_conforms"),
        ("a2", "dissent", "contract_nonconformity"),
    ):
        assert (
            cliente.post(
                f"/api/v1/schedules/{sid}/attempts/{attempt}/audit-opinions",
                json={
                    "command_key": chave,
                    "opinion": opiniao,
                    "reason_codes": [motivo],
                    "auditor_execution_ref": f"exec-{chave}",
                },
                headers=headers,
            ).status_code
            == 201
        )
    assert _contar("SELECT count(*) FROM audit_opinions") == 2


@pytest.mark.parametrize(
    ("opiniao", "motivo"),
    [("concur", "contract_nonconformity"), ("dissent", "contract_conforms")],
)
def test_e73a20_matriz_de_parecer_e_imposta(cliente, opiniao, motivo) -> None:
    headers = _principal()
    sid, step = _criar(cliente, headers, {})
    attempt = _exportar(cliente, headers, sid, step, "e1").json()["data"]["attempt_id"]
    cliente.post(
        f"/api/v1/schedules/{sid}/steps/{step}/handoff-import",
        json={
            "command_key": "i1",
            "attempt_id": attempt,
            "output": {"media_type": "text/plain", "content": "parecer"},
            "attribution": {"declared_instance_id": "i1"},
        },
        headers=headers,
    )
    resposta = cliente.post(
        f"/api/v1/schedules/{sid}/attempts/{attempt}/audit-opinions",
        json={
            "command_key": "a1",
            "opinion": opiniao,
            "reason_codes": [motivo],
            "auditor_execution_ref": "exec-1",
        },
        headers=headers,
    )
    assert resposta.status_code == 422
    assert _contar("SELECT count(*) FROM audit_opinions") == 0


def test_e73a21_pass_final_nao_e_representavel(cliente) -> None:
    """`AI_SELF_PASS_FINAL = FORBIDDEN`, já no schema público."""
    headers = _principal()
    sid, step = _criar(cliente, headers, {})
    attempt = _exportar(cliente, headers, sid, step, "e1").json()["data"]["attempt_id"]
    resposta = cliente.post(
        f"/api/v1/schedules/{sid}/attempts/{attempt}/audit-opinions",
        json={
            "command_key": "a1",
            "opinion": "pass_final",
            "reason_codes": ["contract_conforms"],
            "auditor_execution_ref": "exec-1",
        },
        headers=headers,
    )
    assert resposta.status_code == 422
    esquema = cliente.get("/openapi.json").json()
    assert "pass_final" not in json.dumps(esquema)


# --- autoridade, escopo e isolamento ----------------------------------------


@pytest.mark.parametrize(
    "rota",
    [
        "/schedules/{sid}/steps/{step}/delegations",
        "/schedules/{sid}/control-events",
        "/schedules/{sid}/governance",
    ],
)
def test_e73a22_toda_rota_nova_exige_credencial(cliente, rota) -> None:
    headers = _principal()
    sid, step = _criar(cliente, headers, {})
    caminho = "/api/v1" + rota.format(sid=sid, step=step)
    if caminho.endswith("governance"):
        resposta = cliente.get(caminho)
    else:
        resposta = cliente.post(caminho, json={"command_key": "x", "action": "pause"})
    assert resposta.status_code == 401


def test_e73a23_principal_alheio_nao_alcanca_governanca(cliente) -> None:
    headers_a = _principal()
    headers_b = _principal()
    sid, step = _criar(cliente, headers_a, GATE_TECNICO)
    assert _grant(cliente, headers_b, sid, step).status_code == 404
    assert _controle(cliente, headers_b, sid, "pause", "k1").status_code == 404
    assert cliente.get(f"/api/v1/schedules/{sid}/governance", headers=headers_b).status_code == 404


def test_e73a24_governanca_nao_expoe_conteudo_nem_dono(cliente) -> None:
    headers = _principal()
    sid, step = _criar(cliente, headers, GATE_TECNICO)
    _grant(cliente, headers, sid, step)
    resposta = cliente.get(f"/api/v1/schedules/{sid}/governance", headers=headers)
    assert resposta.status_code == 200
    assert "control_principal_ref" not in resposta.text
    assert "granted_by_principal_ref" not in resposta.text


def test_e73a25_dto_recusa_campo_derivavel(cliente) -> None:
    headers = _principal()
    sid, step = _criar(cliente, headers, GATE_TECNICO)
    resposta = cliente.post(
        f"/api/v1/schedules/{sid}/steps/{step}/delegations",
        json={
            "command_key": "g1",
            "valid_until": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
            "content_sha256": "a" * 64,
        },
        headers=headers,
    )
    assert resposta.status_code == 422


def test_e73a26_mesma_chave_com_acao_divergente_recusa(cliente) -> None:
    headers = _principal()
    sid, _ = _criar(cliente, headers, {})
    assert _controle(cliente, headers, sid, "pause", "k1").status_code == 201
    assert _controle(cliente, headers, sid, "resume", "k1").status_code == 409


def test_e73a27_replay_exato_de_controle_nao_duplica(cliente) -> None:
    headers = _principal()
    sid, _ = _criar(cliente, headers, {})
    primeiro = _controle(cliente, headers, sid, "pause", "k1")
    assert primeiro.status_code == 201 and primeiro.json()["data"]["replayed"] is False
    segundo = _controle(cliente, headers, sid, "pause", "k1")
    assert segundo.status_code == 201 and segundo.json()["data"]["replayed"] is True
    assert _contar("SELECT count(*) FROM orchestration_control_events") == 1


# --- lacunas fechadas pelos mutantes M-h, M-c e M-s -------------------------


def test_e73a28_o_consumo_revalida_o_hash_no_ponto_material(cliente) -> None:
    """Mata `M-h`: `content_sha256` fora do UPDATE de consumo.

    O preflight já compara o hash, mas o consumo **revalida** — entre uma
    coisa e outra a etapa pode mudar, e a garantia tem de estar onde o
    efeito acontece, não só onde a decisão foi tomada.

    O cenário força exatamente essa janela: a delegação é concedida, o
    conteúdo muda no banco, e a autorização anterior é oferecida ao
    caminho de efeito.
    """
    from app.orchestration.adapters.deny_all_human_gate import DenyAllHumanGate
    from app.orchestration.adapters.manual_transport import ManualTransport
    from app.orchestration.errors.exceptions import DispatchBlockedError
    from app.orchestration.repositories.orchestration_repository import (
        OrchestrationRepository,
    )
    from app.orchestration.services.control_service import ControlService
    from app.orchestration.services.handoff_service import HandoffService
    from app.orchestration.services.manual_handoff_export_service import (
        DispatchAuthorized,
        ManualHandoffExportService,
    )
    from app.repositories.unit_of_work import UnitOfWork

    headers = _principal()
    sid, step = _criar(cliente, headers, GATE_TECNICO)
    _grant(cliente, headers, sid, step)
    _controle(cliente, headers, sid, "resume", "r1")
    with engine.connect() as conexao:
        principal_ref = conexao.execute(
            sa.text("SELECT control_principal_ref FROM schedules WHERE id = :i"), {"i": sid}
        ).scalar_one()
        hash_antigo = conexao.execute(
            sa.text("SELECT content_sha256 FROM service_delegations")
        ).scalar_one()
        delegation_id = conexao.execute(sa.text("SELECT id FROM service_delegations")).scalar_one()

    # O conteúdo muda DEPOIS da concessão.
    with engine.begin() as conexao:
        conexao.execute(
            sa.text("UPDATE schedule_steps SET instruction_ref = 'i://mudou' WHERE id = :p"),
            {"p": step},
        )

    with UnitOfWork() as uow:
        repositorio = OrchestrationRepository(uow.session)
        servico = ManualHandoffExportService(
            repositorio,
            HandoffService(repositorio),
            ManualTransport(),
            DenyAllHumanGate(),
            ControlService(repositorio),
        )
        # A autorização carrega o hash CORRENTE, como o preflight real
        # produziria; a delegação ficou presa ao antigo. É a revalidação no
        # UPDATE que precisa recusar — passar o hash antigo casaria com a
        # linha antiga e não provaria nada.
        conteudo_atual = HandoffService(repositorio).build_envelope_content(
            control_principal_ref=principal_ref,
            schedule_id=uuid.UUID(sid),
            step_id=uuid.UUID(step),
        )
        assert conteudo_atual.content_sha256() != hash_antigo
        autorizacao_obsoleta = DispatchAuthorized(
            content_sha256=conteudo_atual.content_sha256(),
            delegation_id=delegation_id,
            first_dispatch=True,
        )
        with pytest.raises(DispatchBlockedError):
            servico.export_step(
                attempt_id=uuid.uuid4(),
                control_principal_ref=principal_ref,
                schedule_id=uuid.UUID(sid),
                step_id=uuid.UUID(step),
                sealer_ref=principal_ref,
                authorization=autorizacao_obsoleta,
            )
    assert _contar("SELECT count(*) FROM service_delegations WHERE state = 'consumed'") == 0
    assert _contar("SELECT count(*) FROM handoff_attempts") == 0


@pytest.mark.parametrize(
    ("acao", "categoria", "estado"),
    [("cancel", None, "cancelled"), ("stop", "missing_authority", "stopped")],
)
def test_e73a29_terminal_nao_alcanca_o_transporte(cliente, acao, categoria, estado) -> None:
    """Mata `M-c` e `M-s`: conta invocações reais de `transport.export`.

    Contar o efeito, e não só o código HTTP, é o que distingue "recusou"
    de "recusou **antes** de atravessar a fronteira".
    """
    from app.orchestration.adapters.deny_all_human_gate import DenyAllHumanGate
    from app.orchestration.errors.exceptions import OrchestrationLifecycleViolationError
    from app.orchestration.repositories.orchestration_repository import (
        OrchestrationRepository,
    )
    from app.orchestration.services.control_service import ControlService
    from app.orchestration.services.handoff_service import HandoffService
    from app.orchestration.services.manual_handoff_export_service import (
        ManualHandoffExportService,
    )
    from app.repositories.unit_of_work import UnitOfWork

    class _TransporteContado:
        mode = "manual_handoff"

        def __init__(self) -> None:
            self.chamadas = 0

        def export(self, handoff):  # noqa: ANN001, ANN202
            self.chamadas += 1
            return handoff

        def receive(self, *, attempt_id):  # noqa: ANN001, ANN202
            raise AssertionError("não usado")

    headers = _principal()
    sid, step = _criar(cliente, headers, {})
    assert _controle(cliente, headers, sid, acao, "k1", categoria).status_code == 201
    with engine.connect() as conexao:
        principal_ref = conexao.execute(
            sa.text("SELECT control_principal_ref FROM schedules WHERE id = :i"), {"i": sid}
        ).scalar_one()
    transporte = _TransporteContado()
    with UnitOfWork() as uow:
        repositorio = OrchestrationRepository(uow.session)
        servico = ManualHandoffExportService(
            repositorio,
            HandoffService(repositorio),
            transporte,
            DenyAllHumanGate(),
            ControlService(repositorio),
        )
        with pytest.raises(OrchestrationLifecycleViolationError) as capturado:
            servico.export_step(
                attempt_id=uuid.uuid4(),
                control_principal_ref=principal_ref,
                schedule_id=uuid.UUID(sid),
                step_id=uuid.UUID(step),
                sealer_ref=principal_ref,
            )
    # A recusa vem da CAMADA DE CONTROLE, não do selamento. Há uma guarda
    # congelada da E7.1 que também recusaria — mas ela diria "selamento não
    # admite etapa em ...", e quem lê o erro precisa saber que o trabalho
    # está encerrado, não que a etapa está num estado estranho.
    #
    # ```text
    # DEFENSE_IN_DEPTH != INTERCHANGEABLE_GUARDS
    # ```
    assert capturado.value.detail["current_state"] == estado
    assert "não despacha" in capturado.value.message
    assert transporte.chamadas == 0
    assert _contar(f"SELECT count(*) FROM schedules WHERE id='{sid}' AND state='{estado}'") == 1
    assert _contar("SELECT count(*) FROM handoff_attempts") == 0


def test_e73a30_pausado_nao_alcanca_o_transporte(cliente) -> None:
    """Mata `M-s` pelo caminho de pausa explícita."""
    from app.orchestration.adapters.deny_all_human_gate import DenyAllHumanGate
    from app.orchestration.errors.exceptions import OrchestrationLifecycleViolationError
    from app.orchestration.repositories.orchestration_repository import (
        OrchestrationRepository,
    )
    from app.orchestration.services.control_service import ControlService
    from app.orchestration.services.handoff_service import HandoffService
    from app.orchestration.services.manual_handoff_export_service import (
        ManualHandoffExportService,
    )
    from app.repositories.unit_of_work import UnitOfWork

    class _TransporteContado:
        mode = "manual_handoff"

        def __init__(self) -> None:
            self.chamadas = 0

        def export(self, handoff):  # noqa: ANN001, ANN202
            self.chamadas += 1
            return handoff

        def receive(self, *, attempt_id):  # noqa: ANN001, ANN202
            raise AssertionError("não usado")

    headers = _principal()
    sid, step = _criar(cliente, headers, {})
    assert _controle(cliente, headers, sid, "pause", "k1").status_code == 201
    with engine.connect() as conexao:
        principal_ref = conexao.execute(
            sa.text("SELECT control_principal_ref FROM schedules WHERE id = :i"), {"i": sid}
        ).scalar_one()
    transporte = _TransporteContado()
    with UnitOfWork() as uow:
        repositorio = OrchestrationRepository(uow.session)
        servico = ManualHandoffExportService(
            repositorio,
            HandoffService(repositorio),
            transporte,
            DenyAllHumanGate(),
            ControlService(repositorio),
        )
        with pytest.raises(OrchestrationLifecycleViolationError) as capturado:
            servico.export_step(
                attempt_id=uuid.uuid4(),
                control_principal_ref=principal_ref,
                schedule_id=uuid.UUID(sid),
                step_id=uuid.UUID(step),
                sealer_ref=principal_ref,
            )
    # PAUSED tem de dizer que exige retomada — a guarda congelada da E7.1
    # recusaria com outra mensagem, e o operador não saberia o que fazer.
    assert capturado.value.detail["current_state"] == "paused"
    assert "retomada" in capturado.value.message
    assert transporte.chamadas == 0
    assert _contar("SELECT count(*) FROM handoff_attempts") == 0


# --- fase zero: replay resolvido antes de qualquer pré-condição -------------


def test_e73a31_replay_exato_com_attempt_aberta_devolve_o_mesmo_recurso(cliente) -> None:
    """`FASE ZERO = REPLAY`.

    Depois do primeiro export a etapa fica `AWAITING_RETURN` com tentativa
    `OPEN` — estado que o preflight recusa para um pedido **novo**. O
    replay não pode atravessar esse caminho: ele é resolvido antes, pela
    tripla de idempotência e pela impressão digital.
    """
    headers = _principal()
    sid, step = _criar(cliente, headers, GATE_TECNICO)
    _grant(cliente, headers, sid, step)
    _controle(cliente, headers, sid, "resume", "r1")

    primeiro = _exportar(cliente, headers, sid, step, "e1")
    assert primeiro.status_code == 201
    d1 = primeiro.json()["data"]
    assert d1["replayed"] is False
    eventos_antes = _contar("SELECT count(*) FROM orchestration_control_events")

    segundo = _exportar(cliente, headers, sid, step, "e1")
    assert segundo.status_code == 201
    d2 = segundo.json()["data"]
    assert d2["replayed"] is True
    assert (d2["attempt_id"], d2["receipt_id"], d2["content_sha256"], d2["sealed_at"]) == (
        d1["attempt_id"],
        d1["receipt_id"],
        d1["content_sha256"],
        d1["sealed_at"],
    )
    assert _contar("SELECT count(*) FROM handoff_attempts") == 1
    assert _contar("SELECT count(*) FROM seal_receipts") == 1
    assert _contar("SELECT count(*) FROM service_delegations WHERE state = 'consumed'") == 1
    assert _contar("SELECT count(*) FROM orchestration_control_events") == eventos_antes


def test_e73a32_replay_nao_consome_delegacao_de_novo(cliente) -> None:
    """Consumo é de uso único, e replay não é um segundo uso."""
    headers = _principal()
    sid, step = _criar(cliente, headers, GATE_TECNICO)
    _grant(cliente, headers, sid, step)
    _controle(cliente, headers, sid, "resume", "r1")
    _exportar(cliente, headers, sid, step, "e1")
    with engine.connect() as conexao:
        antes = conexao.execute(
            sa.text("SELECT state, consumed_at, consumed_by_attempt_id FROM service_delegations")
        ).one()
    _exportar(cliente, headers, sid, step, "e1")
    with engine.connect() as conexao:
        depois = conexao.execute(
            sa.text("SELECT state, consumed_at, consumed_by_attempt_id FROM service_delegations")
        ).one()
    assert antes == depois


def test_e73a33_replay_nao_chama_o_transporte_de_novo(cliente) -> None:
    """`transport.calls` permanece 1 — o efeito não roda duas vezes."""
    import app.routers.orchestration as router_modulo
    from app.orchestration.adapters.manual_transport import ManualTransport

    chamadas: list[int] = []
    original = ManualTransport.export

    def contado(self, handoff):  # noqa: ANN001, ANN202
        chamadas.append(1)
        return original(self, handoff)

    headers = _principal()
    sid, step = _criar(cliente, headers, GATE_TECNICO)
    _grant(cliente, headers, sid, step)
    _controle(cliente, headers, sid, "resume", "r1")
    ManualTransport.export = contado  # type: ignore[method-assign]
    try:
        assert _exportar(cliente, headers, sid, step, "e1").status_code == 201
        assert _exportar(cliente, headers, sid, step, "e1").status_code == 201
    finally:
        ManualTransport.export = original  # type: ignore[method-assign]
    assert len(chamadas) == 1
    del router_modulo


def test_e73a34_mesma_chave_com_requisicao_diferente_recusa_na_fase_zero(cliente) -> None:
    """Hash divergente é 409 **antes** de locks e preflight."""
    headers = _principal()
    sid, step = _criar(cliente, headers, GATE_TECNICO)
    corpo = {
        "command_key": "c2",
        "title": "t",
        "steps": [
            {
                "role": "r",
                "instruction_ref": "i://2",
                "expected_output_contract": OUTPUT_NON_EMPTY_TEXT_V1,
                "constraints": GATE_TECNICO,
            }
        ],
    }
    outro = cliente.post("/api/v1/schedules", json=corpo, headers=headers).json()["data"]
    outro_sid, outro_step = outro["schedule_id"], outro["steps"][0]["step_id"]
    _grant(cliente, headers, sid, step, "g1")
    _controle(cliente, headers, sid, "resume", "r1")
    assert _exportar(cliente, headers, sid, step, "e1").status_code == 201
    antes_eventos = _contar("SELECT count(*) FROM orchestration_control_events")
    # mesma chave, outro path -> outra impressão digital
    conflito = _exportar(cliente, headers, outro_sid, outro_step, "e1")
    assert conflito.status_code == 409
    assert _contar("SELECT count(*) FROM handoff_attempts") == 1
    assert _contar("SELECT count(*) FROM orchestration_control_events") == antes_eventos


def test_e73a35_duas_chamadas_identicas_concorrentes_produzem_um_efeito(cliente) -> None:
    """A segunda leitura, sob os locks, fecha a corrida.

    ```text
    ONE_EFFECT + ONE_REPLAY
    ```
    """
    import threading

    headers = _principal()
    sid, step = _criar(cliente, headers, GATE_TECNICO)
    _grant(cliente, headers, sid, step)
    _controle(cliente, headers, sid, "resume", "r1")

    barreira = threading.Barrier(2)
    respostas: list[tuple[int, bool]] = []
    erros: list[BaseException] = []

    def executar(_indice: int) -> None:
        try:
            with TestClient(app) as paralelo:
                barreira.wait(timeout=15)
                resposta = _exportar(paralelo, headers, sid, step, "e1")
                corpo = resposta.json()
                respostas.append(
                    (resposta.status_code, corpo.get("data", {}).get("replayed", False))
                )
        except BaseException as exc:  # noqa: BLE001 - o teste inspeciona
            erros.append(exc)

    linhas = [threading.Thread(target=executar, args=(i,)) for i in range(2)]
    for linha in linhas:
        linha.start()
    for linha in linhas:
        linha.join(timeout=45)
    assert not erros, erros
    assert len(respostas) == 2
    assert all(codigo == 201 for codigo, _ in respostas)
    assert _contar("SELECT count(*) FROM handoff_attempts") == 1
    assert _contar("SELECT count(*) FROM seal_receipts") == 1
    assert _contar("SELECT count(*) FROM service_delegations WHERE state = 'consumed'") == 1
    assert (
        _contar(
            "SELECT count(*) FROM command_receipts "
            "WHERE operation = 'orchestration.export_handoff'"
        )
        == 1
    )


def test_e73a36_a_impressao_da_fase_zero_coincide_com_a_do_claim(cliente) -> None:
    """Se divergirem, replay legítimo viraria pedido novo — em silêncio."""
    from app.orchestration.models.enums import CommandOperation
    from app.routers.orchestration import _impressao_de_export

    headers = _principal()
    sid, step = _criar(cliente, headers, GATE_TECNICO)
    _grant(cliente, headers, sid, step)
    _controle(cliente, headers, sid, "resume", "r1")
    assert _exportar(cliente, headers, sid, step, "e1").status_code == 201
    with engine.connect() as conexao:
        persistida = conexao.execute(
            sa.text("SELECT request_sha256 FROM command_receipts WHERE operation = :o"),
            {"o": CommandOperation.EXPORT_HANDOFF.value},
        ).scalar_one()
    with engine.connect() as conexao:
        principal_ref = conexao.execute(
            sa.text("SELECT control_principal_ref FROM schedules WHERE id = :i"), {"i": sid}
        ).scalar_one()
    assert _impressao_de_export(uuid.UUID(sid), uuid.UUID(step), principal_ref) == persistida
