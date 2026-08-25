"""Composição produtiva MCP contra PostgreSQL real.

Estas provas percorrem o dispatcher transacional, os serviços e os
repositórios reais. Só a decisão da proteção é controlada para tornar G2 e
G3 determinísticos; nenhum serviço de orquestração é substituído.
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass
from typing import Any

import pytest
import sqlalchemy as sa

from app.database.engine import engine
from app.database.health import check_database_health
from app.database.session import SessionLocal
from app.mcp.auth import PrincipalAutenticado
from app.orchestration.errors.exceptions import OrchestrationLifecycleViolationError
from app.orchestration.models.enums import HandoffMode
from app.orchestration.protection.vocabulary import GatePosition, ProtectionOutcome
from app.orchestration.repositories.orchestration_repository import OrchestrationRepository
from app.orchestration.schemas.envelope import ContextRef, ScheduleDraft, StepDraft
from app.orchestration.schemas.output_contract import OUTPUT_NON_EMPTY_TEXT_V1
from app.orchestration.services.schedule_service import ScheduleService
from app.services.mcp_composition_root import RuntimeDependencies, TransactionalMcpTools

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        not check_database_health().available,
        reason="PostgreSQL real indisponível — atomicidade e concorrência exigem o banco.",
    ),
]

PRINCIPAL_REF = "principal-mcp-pg"
PRINCIPAL = PrincipalAutenticado(
    principal_ref=PRINCIPAL_REF,
    scopes=frozenset({"orchestration:operate"}),
    subject="sub-mcp-pg",
)
_HASH = "a" * 64


@dataclass(frozen=True)
class _Decisao:
    outcome: ProtectionOutcome
    decision_fingerprint: str = "f" * 64


class _ProtecaoControlada:
    def __init__(self, bloqueado_em: frozenset[GatePosition]) -> None:
        self._bloqueado_em = bloqueado_em

    def aplicar(self, *, gate_position: GatePosition, **_: Any) -> _Decisao:
        outcome = (
            ProtectionOutcome.BLOCKED
            if gate_position in self._bloqueado_em
            else ProtectionOutcome.ALLOWED
        )
        return _Decisao(outcome=outcome)


def _deps(bloqueado_em: frozenset[GatePosition] = frozenset()) -> RuntimeDependencies:
    return RuntimeDependencies(
        session_factory=SessionLocal,
        protecao_factory=lambda _s: _ProtecaoControlada(bloqueado_em),
        objetivo_por_step=lambda **_: "objetivo de integração MCP",
        operacao="expose",
        resource_config=None,
        jwks=None,
        principal_resolver=None,
        quota=None,
    )


def _limpar() -> None:
    append_only = (
        "human_protection_event_capabilities",
        "human_protection_events",
        "connection_execution_receipts",
        "audit_opinions",
        "execution_observations",
        "orchestration_control_events",
        "handoff_results",
        "handoff_attributions",
        "seal_receipts",
        "service_delegations",
    )
    comuns = (
        "handoff_attempts",
        "schedule_steps",
        "schedules",
        "command_receipts",
        "connection_profiles",
    )
    with engine.begin() as conexao:
        for tabela in append_only:
            conexao.execute(sa.text(f"ALTER TABLE {tabela} DISABLE TRIGGER USER"))
            conexao.execute(sa.text(f"DELETE FROM {tabela}"))
            conexao.execute(sa.text(f"ALTER TABLE {tabela} ENABLE TRIGGER USER"))
        for tabela in comuns:
            conexao.execute(sa.text(f"DELETE FROM {tabela}"))


@pytest.fixture(autouse=True)
def _banco_limpo():
    _limpar()
    yield
    _limpar()


def _criar_schedule() -> tuple[uuid.UUID, uuid.UUID]:
    schedule_id = uuid.uuid4()
    draft = ScheduleDraft(
        title="MCP PostgreSQL",
        steps=(
            StepDraft(
                role="worker",
                instruction_ref="instruction://mcp/1",
                expected_output_contract=OUTPUT_NON_EMPTY_TEXT_V1,
                context_refs=(ContextRef(uri="context://mcp/1", sha256=_HASH, bytes=1),),
            ),
        ),
    )
    with SessionLocal() as sessao:
        servico = ScheduleService(OrchestrationRepository(sessao))
        servico.create_schedule(
            schedule_id=schedule_id,
            control_principal_ref=PRINCIPAL_REF,
            draft=draft,
            execution_mode=HandoffMode.MANUAL_HANDOFF,
        )
        vista = servico.activate(
            control_principal_ref=PRINCIPAL_REF,
            schedule_id=schedule_id,
        )
        step_id = vista.steps[0].step_id
        sessao.commit()
    return schedule_id, step_id


def _exportar(
    tools: TransactionalMcpTools,
    schedule_id: uuid.UUID,
    step_id: uuid.UUID,
    command_key: str,
) -> dict[str, Any]:
    return tools.chamar(
        nome="handoff.export",
        argumentos={
            "schedule_id": str(schedule_id),
            "step_id": str(step_id),
            "command_key": command_key,
        },
        principal=PRINCIPAL,
    )


def _contar(tabela: str) -> int:
    with engine.connect() as conexao:
        return int(conexao.scalar(sa.text(f"SELECT count(*) FROM {tabela}")) or 0)


def test_e742pg01_export_permitido_materializa_e_commita() -> None:
    schedule_id, step_id = _criar_schedule()
    resposta = _exportar(TransactionalMcpTools(_deps()), schedule_id, step_id, "export-1")

    assert resposta["handoff_mode"] == HandoffMode.SUPERVISED_AUTOMATIC_HANDOFF.value
    assert resposta["replayed"] is False
    assert _contar("command_receipts") == 1
    assert _contar("handoff_attempts") == 1
    assert _contar("seal_receipts") == 1


def test_e742pg02_g2_bloqueado_nao_reivindica_nem_materializa() -> None:
    schedule_id, step_id = _criar_schedule()
    with pytest.raises(Exception, match="g2"):
        _exportar(
            TransactionalMcpTools(_deps(frozenset({GatePosition.G2}))),
            schedule_id,
            step_id,
            "blocked-g2",
        )
    assert _contar("command_receipts") == 0
    assert _contar("handoff_attempts") == 0
    assert _contar("seal_receipts") == 0


def test_e742pg03_g3_bloqueado_reverte_claim_e_deixa_chave_livre() -> None:
    schedule_id, step_id = _criar_schedule()
    bloqueado = TransactionalMcpTools(_deps(frozenset({GatePosition.G3})))
    with pytest.raises(Exception, match="g3"):
        _exportar(bloqueado, schedule_id, step_id, "blocked-g3")
    assert _contar("command_receipts") == 0
    assert _contar("handoff_attempts") == 0
    assert _contar("seal_receipts") == 0

    permitido = _exportar(TransactionalMcpTools(_deps()), schedule_id, step_id, "blocked-g3")
    assert permitido["replayed"] is False
    assert _contar("command_receipts") == 1
    assert _contar("handoff_attempts") == 1


def test_e742pg04_replay_devolve_a_mesma_attempt_sem_segundo_efeito() -> None:
    schedule_id, step_id = _criar_schedule()
    tools = TransactionalMcpTools(_deps())
    primeiro = _exportar(tools, schedule_id, step_id, "replay-1")
    segundo = _exportar(tools, schedule_id, step_id, "replay-1")

    assert segundo["attempt_id"] == primeiro["attempt_id"]
    assert segundo["replayed"] is True
    assert _contar("command_receipts") == 1
    assert _contar("handoff_attempts") == 1


def test_e742pg05_mesma_chave_pedido_diferente_e_conflito() -> None:
    primeiro_schedule, primeiro_step = _criar_schedule()
    segundo_schedule, segundo_step = _criar_schedule()
    tools = TransactionalMcpTools(_deps())
    _exportar(tools, primeiro_schedule, primeiro_step, "conflict-1")

    with pytest.raises(OrchestrationLifecycleViolationError):
        _exportar(tools, segundo_schedule, segundo_step, "conflict-1")
    assert _contar("command_receipts") == 1
    assert _contar("handoff_attempts") == 1


def test_e742pg06_concorrencia_real_tem_um_vencedor_e_uma_attempt() -> None:
    schedule_id, step_id = _criar_schedule()
    barreira = threading.Barrier(2)
    resultados: list[dict[str, Any]] = []
    falhas: list[BaseException] = []

    def executar() -> None:
        try:
            barreira.wait(timeout=5)
            resultados.append(
                _exportar(
                    TransactionalMcpTools(_deps()),
                    schedule_id,
                    step_id,
                    "concorrente-1",
                )
            )
        except BaseException as falha:  # pragma: no cover - diagnóstico do thread
            falhas.append(falha)

    threads = [threading.Thread(target=executar) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)

    assert falhas == []
    assert len(resultados) == 2
    assert len({r["attempt_id"] for r in resultados}) == 1
    assert sorted(r["replayed"] for r in resultados) == [False, True]
    assert _contar("command_receipts") == 1
    assert _contar("handoff_attempts") == 1


@pytest.mark.parametrize(
    ("content", "accepted"),
    [("resultado válido", True), ("", False)],
)
def test_e742pg07_importacao_real_persiste_apenas_o_veredito(content: str, accepted: bool) -> None:
    schedule_id, step_id = _criar_schedule()
    tools = TransactionalMcpTools(_deps())
    exportado = _exportar(tools, schedule_id, step_id, f"export-{accepted}")
    resposta = tools.chamar(
        nome="return.import",
        argumentos={
            "command_key": f"return-{accepted}",
            "schedule_id": str(schedule_id),
            "step_id": str(step_id),
            "attempt_id": exportado["attempt_id"],
            "media_type": "text/plain",
            "content": content,
            "declared_instance_id": "instance-mcp-pg",
            "declared_provider_id": "provider-mcp-pg",
            "declared_model_id": "model-mcp-pg",
        },
        principal=PRINCIPAL,
    )

    assert resposta["accepted"] is accepted
    assert _contar("handoff_results") == 1
    assert _contar("handoff_attributions") == 1
    with engine.connect() as conexao:
        colunas = {
            linha[0]
            for linha in conexao.execute(
                sa.text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name IN ('handoff_results', 'handoff_attributions')"
                )
            )
        }
    assert "content" not in colunas
    assert "payload" not in colunas
