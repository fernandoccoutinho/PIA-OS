"""
Serviços da orquestração contra repositório dublê (`E7.1`).

O dublê existe para provar o que é decisão **de serviço**: escopo por
principal de controle, transições permitidas, ordem entre reivindicar e
produzir. O que é decisão do **banco** — atomicidade, unicidade composta,
trigger append-only — é provado na integração, contra PostgreSQL real, e
não aqui: um dublê que "prova" atomicidade prova apenas a si mesmo.

```text
FAKE_PROVES_SERVICE_LOGIC
FAKE_NEVER_PROVES_DATABASE_ATOMICITY
```
"""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime

import pytest

from app.orchestration.errors.exceptions import (
    OrchestrationContractViolationError,
    OrchestrationLifecycleViolationError,
    OrchestrationScopeViolationError,
    SealReceiptImmutableError,
)
from app.orchestration.models.enums import (
    AttemptState,
    CommandOperation,
    HandoffMode,
    ScheduleState,
    StepState,
)
from app.orchestration.schemas.envelope import ContextRef, ScheduleDraft, StepDraft
from app.orchestration.services.command_receipt_service import CommandReceiptService
from app.orchestration.services.handoff_service import HandoffService
from app.orchestration.services.schedule_service import ScheduleService

pytestmark = pytest.mark.unit

_HASH = "c" * 64


@dataclass
class _Agenda:
    id: uuid.UUID
    title: str
    state: ScheduleState
    execution_mode: HandoffMode
    control_principal_ref: str


@dataclass
class _Etapa:
    id: uuid.UUID
    schedule_id: uuid.UUID
    position: int
    role: str
    instruction_ref: str
    context_refs: tuple[ContextRef, ...]
    expected_output_contract: str
    constraints: tuple[tuple[str, str], ...]
    state: StepState


@dataclass
class _Tentativa:
    id: uuid.UUID
    schedule_id: uuid.UUID
    step_id: uuid.UUID
    attempt_number: int
    envelope_version: str
    content_sha256: str
    state: AttemptState


@dataclass
class _Recibo:
    id: uuid.UUID
    attempt_id: uuid.UUID
    content_sha256: str
    sealed_at: datetime
    sealer_ref: str


@dataclass
class _ReciboComando:
    id: uuid.UUID
    technical_principal_ref: str
    operation: str
    command_key: str
    outcome_ref: str
    request_sha256: str | None = None


@dataclass
class RepositorioDuble:
    """Repositório em memória com o MESMO contrato de escopo do real."""

    agendas: dict[uuid.UUID, _Agenda] = field(default_factory=dict)
    etapas: dict[uuid.UUID, _Etapa] = field(default_factory=dict)
    tentativas: list[_Tentativa] = field(default_factory=list)
    recibos: list[_Recibo] = field(default_factory=list)
    comandos: dict[tuple[str, str, str], _ReciboComando] = field(default_factory=dict)
    relogio: int = 0

    def database_now(self) -> datetime:
        self.relogio += 1
        return datetime(2026, 1, 1, tzinfo=UTC).replace(microsecond=self.relogio)

    def create_schedule(self, *, schedule_id, control_principal_ref, title, execution_mode, steps):
        agenda = _Agenda(
            id=schedule_id,
            title=title,
            state=ScheduleState.DRAFT,
            execution_mode=execution_mode,
            control_principal_ref=control_principal_ref,
        )
        self.agendas[schedule_id] = agenda
        for posicao, rascunho in enumerate(steps, start=1):
            etapa_id = uuid.uuid4()
            self.etapas[etapa_id] = _Etapa(
                id=etapa_id,
                schedule_id=schedule_id,
                position=posicao,
                role=rascunho.role,
                instruction_ref=rascunho.instruction_ref,
                context_refs=rascunho.context_refs,
                expected_output_contract=rascunho.expected_output_contract,
                constraints=rascunho.constraints,
                state=StepState.PENDING,
            )
        return agenda

    def get_schedule(self, *, control_principal_ref, schedule_id):
        agenda = self.agendas.get(schedule_id)
        if agenda is None or agenda.control_principal_ref != control_principal_ref:
            return None
        return agenda

    def lock_schedule(self, *, control_principal_ref, schedule_id):
        return self.get_schedule(
            control_principal_ref=control_principal_ref, schedule_id=schedule_id
        )

    def set_schedule_state(self, *, control_principal_ref, schedule_id, state):
        """Escopado como o real: o dublê não pode ser mais permissivo.

        ```text
        FAKE_LOOSER_THAN_REAL = TEST_THAT_PROVES_NOTHING
        ```
        """
        agenda = self.get_schedule(
            control_principal_ref=control_principal_ref, schedule_id=schedule_id
        )
        if agenda is None:
            raise OrchestrationScopeViolationError(message="fora do escopo")
        agenda.state = state
        return agenda

    def list_steps(self, *, control_principal_ref, schedule_id):
        if (
            self.get_schedule(control_principal_ref=control_principal_ref, schedule_id=schedule_id)
            is None
        ):
            return []
        return sorted(
            (e for e in self.etapas.values() if e.schedule_id == schedule_id),
            key=lambda e: e.position,
        )

    def get_step(self, *, control_principal_ref, schedule_id, step_id):
        etapa = self.etapas.get(step_id)
        if etapa is None or etapa.schedule_id != schedule_id:
            return None
        if (
            self.get_schedule(control_principal_ref=control_principal_ref, schedule_id=schedule_id)
            is None
        ):
            return None
        return etapa

    def next_attempt_number(self, *, control_principal_ref, schedule_id, step_id):
        if (
            self.get_step(
                control_principal_ref=control_principal_ref,
                schedule_id=schedule_id,
                step_id=step_id,
            )
            is None
        ):
            raise OrchestrationScopeViolationError(message="fora do escopo")
        return 1 + sum(1 for t in self.tentativas if t.step_id == step_id)

    def create_attempt(
        self,
        *,
        control_principal_ref,
        attempt_id,
        schedule_id,
        step_id,
        attempt_number,
        envelope_version,
        content_sha256,
    ):
        if (
            self.get_step(
                control_principal_ref=control_principal_ref,
                schedule_id=schedule_id,
                step_id=step_id,
            )
            is None
        ):
            raise OrchestrationScopeViolationError(message="fora do escopo")
        tentativa = _Tentativa(
            id=attempt_id,
            schedule_id=schedule_id,
            step_id=step_id,
            attempt_number=attempt_number,
            envelope_version=envelope_version,
            content_sha256=content_sha256,
            state=AttemptState.OPEN,
        )
        self.tentativas.append(tentativa)
        return tentativa

    def create_seal_receipt(
        self,
        *,
        control_principal_ref,
        schedule_id,
        attempt_id,
        content_sha256,
        sealed_at,
        sealer_ref,
    ):
        if self._tentativa_no_escopo(control_principal_ref, schedule_id, attempt_id) is None:
            raise OrchestrationScopeViolationError(message="fora do escopo")
        recibo = _Recibo(
            id=uuid.uuid4(),
            attempt_id=attempt_id,
            content_sha256=content_sha256,
            sealed_at=sealed_at,
            sealer_ref=sealer_ref,
        )
        self.recibos.append(recibo)
        return recibo

    def _tentativa_no_escopo(self, control_principal_ref, schedule_id, attempt_id):
        """As quatro condições do real, inclusive o Schedule DECLARADO.

        ```text
        OWNER_BINDING != SCHEDULE_BINDING
        FAKE_LOOSER_THAN_REAL = TEST_THAT_PROVES_NOTHING
        ```

        Derivar o Schedule de `tentativa.schedule_id`, como o dublê fazia,
        reproduziria no teste exatamente o defeito R2.
        """
        for tentativa in self.tentativas:
            if tentativa.id != attempt_id or tentativa.schedule_id != schedule_id:
                continue
            agenda = self.get_schedule(
                control_principal_ref=control_principal_ref, schedule_id=schedule_id
            )
            return tentativa if agenda is not None else None
        return None

    def get_attempt(self, *, control_principal_ref, schedule_id, attempt_id):
        return self._tentativa_no_escopo(control_principal_ref, schedule_id, attempt_id)

    def get_seal_receipt_by_attempt(self, *, control_principal_ref, schedule_id, attempt_id):
        if self._tentativa_no_escopo(control_principal_ref, schedule_id, attempt_id) is None:
            return None
        return next((r for r in self.recibos if r.attempt_id == attempt_id), None)

    def list_attempts(self, *, control_principal_ref, schedule_id, step_id=None):
        if (
            self.get_schedule(control_principal_ref=control_principal_ref, schedule_id=schedule_id)
            is None
        ):
            return []
        return [
            t
            for t in self.tentativas
            if t.schedule_id == schedule_id and (step_id is None or t.step_id == step_id)
        ]

    def claim_command(
        self,
        *,
        technical_principal_ref,
        operation,
        command_key,
        proposed_outcome_ref,
        request_sha256=None,
    ):
        """Escopado e com vínculo de requisição, como o real.

        ```text
        FAKE_LOOSER_THAN_REAL = TEST_THAT_PROVES_NOTHING
        ```
        """
        chave = (technical_principal_ref, operation, command_key)
        existente = self.comandos.get(chave)
        if existente is not None:
            return existente, False
        recibo = _ReciboComando(
            id=uuid.uuid4(),
            technical_principal_ref=technical_principal_ref,
            operation=operation,
            command_key=command_key,
            outcome_ref=proposed_outcome_ref,
            request_sha256=request_sha256,
        )
        self.comandos[chave] = recibo
        return recibo, True


@dataclass
class _Servicos:
    repositorio: RepositorioDuble
    agendas: ScheduleService
    handoff: HandoffService
    comandos: CommandReceiptService


@pytest.fixture
def servicos() -> _Servicos:
    repositorio = RepositorioDuble()
    agendas = ScheduleService(repositorio)  # type: ignore[arg-type]
    handoff = HandoffService(repositorio)  # type: ignore[arg-type]
    return _Servicos(
        repositorio=repositorio,
        agendas=agendas,
        handoff=handoff,
        comandos=CommandReceiptService(repositorio, agendas, handoff),  # type: ignore[arg-type]
    )


def _rascunho() -> ScheduleDraft:
    return ScheduleDraft(
        title="revisão cruzada",
        steps=(
            StepDraft(
                role="reviewer",
                instruction_ref="instr://1",
                expected_output_contract="contract://parecer",
                context_refs=(ContextRef(uri="art://a", sha256=_HASH, bytes=3),),
                constraints={"idioma": "pt-BR"},
            ),
        ),
    )


# --- composição e escopo ---------------------------------------------------


def test_e71s01_schedule_nasce_draft_com_o_principal_de_controle(servicos: _Servicos) -> None:
    vista = servicos.agendas.create_schedule(
        schedule_id=uuid.uuid4(),
        control_principal_ref="principal-a",
        draft=_rascunho(),
        execution_mode=HandoffMode.MANUAL_HANDOFF,
    )
    assert vista.state is ScheduleState.DRAFT
    assert vista.control_principal_ref == "principal-a"
    assert [etapa.position for etapa in vista.steps] == [1]
    assert vista.steps[0].state is StepState.PENDING


@pytest.mark.parametrize(
    "modo",
    [HandoffMode.SUPERVISED_AUTOMATIC_HANDOFF, HandoffMode.RESTRICTED_AUTOMATIC_CONTINUATION],
)
def test_e71s02_modo_declarado_mas_nao_executavel_e_recusado(
    servicos: _Servicos, modo: HandoffMode
) -> None:
    """`DECLARED_VOCABULARY != EXECUTABLE_MODE`."""
    with pytest.raises(OrchestrationContractViolationError):
        servicos.agendas.create_schedule(
            schedule_id=uuid.uuid4(),
            control_principal_ref="principal-a",
            draft=_rascunho(),
            execution_mode=modo,
        )


def test_e71s03_principal_b_nao_le_schedule_do_principal_a(servicos: _Servicos) -> None:
    """`CROSS_PRINCIPAL_SCHEDULE_READ = FORBIDDEN`."""
    schedule_id = uuid.uuid4()
    servicos.agendas.create_schedule(
        schedule_id=schedule_id,
        control_principal_ref="principal-a",
        draft=_rascunho(),
        execution_mode=HandoffMode.MANUAL_HANDOFF,
    )
    with pytest.raises(OrchestrationScopeViolationError):
        servicos.agendas.get_schedule(control_principal_ref="principal-b", schedule_id=schedule_id)
    with pytest.raises(OrchestrationScopeViolationError):
        servicos.agendas.activate(control_principal_ref="principal-b", schedule_id=schedule_id)


def test_e71s04_apenas_draft_para_active_e_executavel(servicos: _Servicos) -> None:
    schedule_id = uuid.uuid4()
    servicos.agendas.create_schedule(
        schedule_id=schedule_id,
        control_principal_ref="p",
        draft=_rascunho(),
        execution_mode=HandoffMode.MANUAL_HANDOFF,
    )
    assert (
        servicos.agendas.activate(control_principal_ref="p", schedule_id=schedule_id).state
        is ScheduleState.ACTIVE
    )
    with pytest.raises(OrchestrationLifecycleViolationError):
        servicos.agendas.activate(control_principal_ref="p", schedule_id=schedule_id)


# --- selamento -------------------------------------------------------------


def _agenda_ativa(servicos: _Servicos, principal: str = "p") -> tuple[uuid.UUID, uuid.UUID]:
    schedule_id = uuid.uuid4()
    servicos.agendas.create_schedule(
        schedule_id=schedule_id,
        control_principal_ref=principal,
        draft=_rascunho(),
        execution_mode=HandoffMode.MANUAL_HANDOFF,
    )
    vista = servicos.agendas.activate(control_principal_ref=principal, schedule_id=schedule_id)
    return schedule_id, vista.steps[0].step_id


def test_e71s05_dois_selamentos_do_mesmo_conteudo_dao_um_hash_e_dois_recibos(
    servicos: _Servicos,
) -> None:
    """`SAME_CONTENT + MULTIPLE_ATTEMPTS -> mesmo hash, recibos distintos`."""
    schedule_id, step_id = _agenda_ativa(servicos)
    primeiro = servicos.handoff.seal_step(
        attempt_id=uuid.uuid4(),
        control_principal_ref="p",
        schedule_id=schedule_id,
        step_id=step_id,
        sealer_ref="selador",
    )
    segundo = servicos.handoff.seal_step(
        attempt_id=uuid.uuid4(),
        control_principal_ref="p",
        schedule_id=schedule_id,
        step_id=step_id,
        sealer_ref="selador",
    )
    assert primeiro.content_sha256 == segundo.content_sha256
    assert primeiro.receipt_id != segundo.receipt_id
    assert primeiro.attempt_id != segundo.attempt_id
    assert (primeiro.attempt_number, segundo.attempt_number) == (1, 2)
    assert len(servicos.repositorio.recibos) == 2


def test_e71s06_selar_nao_despacha_a_etapa(servicos: _Servicos) -> None:
    """`SEALED != DISPATCHED` — transporte é E7.2."""
    schedule_id, step_id = _agenda_ativa(servicos)
    servicos.handoff.seal_step(
        attempt_id=uuid.uuid4(),
        control_principal_ref="p",
        schedule_id=schedule_id,
        step_id=step_id,
        sealer_ref="selador",
    )
    assert servicos.repositorio.etapas[step_id].state is StepState.PENDING
    assert servicos.repositorio.tentativas[0].state is AttemptState.OPEN


def test_e71s07_selar_exige_schedule_active(servicos: _Servicos) -> None:
    schedule_id = uuid.uuid4()
    vista = servicos.agendas.create_schedule(
        schedule_id=schedule_id,
        control_principal_ref="p",
        draft=_rascunho(),
        execution_mode=HandoffMode.MANUAL_HANDOFF,
    )
    with pytest.raises(OrchestrationLifecycleViolationError):
        servicos.handoff.seal_step(
            attempt_id=uuid.uuid4(),
            control_principal_ref="p",
            schedule_id=schedule_id,
            step_id=vista.steps[0].step_id,
            sealer_ref="selador",
        )
    assert servicos.repositorio.tentativas == []
    assert servicos.repositorio.recibos == []


def test_e71s08_selar_schedule_de_outro_principal_e_recusado(servicos: _Servicos) -> None:
    schedule_id, step_id = _agenda_ativa(servicos, principal="principal-a")
    with pytest.raises(OrchestrationScopeViolationError):
        servicos.handoff.seal_step(
            attempt_id=uuid.uuid4(),
            control_principal_ref="principal-b",
            schedule_id=schedule_id,
            step_id=step_id,
            sealer_ref="selador",
        )
    assert servicos.repositorio.tentativas == []


def test_e71s09_o_recibo_carrega_sealed_at_do_banco_e_o_hash_nao(servicos: _Servicos) -> None:
    schedule_id, step_id = _agenda_ativa(servicos)
    conteudo = servicos.handoff.build_envelope_content(
        control_principal_ref="p", schedule_id=schedule_id, step_id=step_id
    )
    resultado = servicos.handoff.seal_step(
        attempt_id=uuid.uuid4(),
        control_principal_ref="p",
        schedule_id=schedule_id,
        step_id=step_id,
        sealer_ref="selador",
    )
    assert resultado.content_sha256 == conteudo.content_sha256()
    assert resultado.sealed_at is not None
    assert "sealed_at" not in conteudo.canonical_json()


# --- idempotência de comando ------------------------------------------------


def test_e71s10_mesma_tripla_devolve_o_mesmo_recibo_sem_efeito_novo(
    servicos: _Servicos,
) -> None:
    """`SAME_COMMAND_KEY -> SAME_RECEIPT, NO_DUPLICATE_EFFECT`."""
    schedule_id, step_id = _agenda_ativa(servicos)
    primeiro = servicos.comandos.seal_handoff_once(
        technical_principal_ref="p",
        command_key="cmd-1",
        schedule_id=schedule_id,
        step_id=step_id,
        sealer_ref="selador",
    )
    segundo = servicos.comandos.seal_handoff_once(
        technical_principal_ref="p",
        command_key="cmd-1",
        schedule_id=schedule_id,
        step_id=step_id,
        sealer_ref="selador",
    )
    assert primeiro.receipt_id == segundo.receipt_id
    assert primeiro.outcome_ref == segundo.outcome_ref
    assert (primeiro.replayed, segundo.replayed) == (False, True)
    assert len(servicos.repositorio.tentativas) == 1
    assert len(servicos.repositorio.recibos) == 1


def test_e71s11_retry_com_chave_nova_abre_tentativa_nova_com_o_mesmo_hash(
    servicos: _Servicos,
) -> None:
    """`RETRY -> NEW_COMMAND_KEY -> NEW_ATTEMPT`."""
    schedule_id, step_id = _agenda_ativa(servicos)
    for chave in ("cmd-1", "cmd-2"):
        servicos.comandos.seal_handoff_once(
            technical_principal_ref="p",
            command_key=chave,
            schedule_id=schedule_id,
            step_id=step_id,
            sealer_ref="selador",
        )
    hashes = {t.content_sha256 for t in servicos.repositorio.tentativas}
    assert len(servicos.repositorio.tentativas) == 2
    assert len(hashes) == 1
    assert len(servicos.repositorio.recibos) == 2


def test_e71s12_mesma_chave_em_principais_diferentes_nao_colide(servicos: _Servicos) -> None:
    """`GLOBAL_COMMAND_KEY_ALONE = INSUFFICIENT`."""
    a = servicos.comandos.create_schedule_once(
        technical_principal_ref="principal-a", command_key="mesma-chave", draft=_rascunho()
    )
    b = servicos.comandos.create_schedule_once(
        technical_principal_ref="principal-b", command_key="mesma-chave", draft=_rascunho()
    )
    assert a.receipt_id != b.receipt_id
    assert a.outcome_ref != b.outcome_ref
    assert (a.replayed, b.replayed) == (False, False)
    assert len(servicos.repositorio.agendas) == 2


def test_e71s13_mesma_chave_em_operacoes_diferentes_nao_colide(servicos: _Servicos) -> None:
    schedule_id, step_id = _agenda_ativa(servicos)
    criacao = servicos.comandos.create_schedule_once(
        technical_principal_ref="p", command_key="k", draft=_rascunho()
    )
    selamento = servicos.comandos.seal_handoff_once(
        technical_principal_ref="p",
        command_key="k",
        schedule_id=schedule_id,
        step_id=step_id,
        sealer_ref="selador",
    )
    assert criacao.operation is CommandOperation.CREATE_SCHEDULE
    assert selamento.operation is CommandOperation.SEAL_HANDOFF
    assert criacao.receipt_id != selamento.receipt_id
    assert selamento.replayed is False
    assert len(servicos.repositorio.tentativas) == 1


def test_e71s14_o_content_hash_nunca_e_usado_como_chave_de_comando(
    servicos: _Servicos,
) -> None:
    """`COMMAND_IDEMPOTENCY_KEY` é do chamador, separada da identidade do conteúdo."""
    schedule_id, step_id = _agenda_ativa(servicos)
    resultado = servicos.comandos.seal_handoff_once(
        technical_principal_ref="p",
        command_key="cmd-1",
        schedule_id=schedule_id,
        step_id=step_id,
        sealer_ref="selador",
    )
    hashes = {t.content_sha256 for t in servicos.repositorio.tentativas}
    chaves = {chave for _, _, chave in servicos.repositorio.comandos}
    assert chaves == {"cmd-1"}
    assert not (chaves & hashes)
    assert resultado.outcome_ref not in hashes


def test_e71s15_comando_recusa_principal_ou_chave_vazios(servicos: _Servicos) -> None:
    with pytest.raises(OrchestrationContractViolationError, match="command_key"):
        servicos.comandos.create_schedule_once(
            technical_principal_ref="p", command_key="   ", draft=_rascunho()
        )
    with pytest.raises(OrchestrationContractViolationError, match="technical_principal_ref"):
        servicos.comandos.create_schedule_once(
            technical_principal_ref="", command_key="k", draft=_rascunho()
        )
    assert servicos.repositorio.comandos == {}


def test_e71s16_o_repositorio_real_recusa_alterar_recibo_de_selamento() -> None:
    """Segunda camada do append-only: recusa explícita, sem tocar no banco."""
    from app.orchestration.repositories.orchestration_repository import OrchestrationRepository

    repositorio = OrchestrationRepository(session=None)  # type: ignore[arg-type]
    recibo = _Recibo(
        id=uuid.uuid4(),
        attempt_id=uuid.uuid4(),
        content_sha256=_HASH,
        sealed_at=datetime(2026, 1, 1, tzinfo=UTC),
        sealer_ref="selador",
    )
    with pytest.raises(SealReceiptImmutableError):
        repositorio.update_seal_receipt(receipt=recibo)  # type: ignore[arg-type]
    with pytest.raises(SealReceiptImmutableError):
        repositorio.delete_seal_receipt(receipt=recibo)  # type: ignore[arg-type]
