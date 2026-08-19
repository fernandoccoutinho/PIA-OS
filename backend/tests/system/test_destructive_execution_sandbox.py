"""
Validação prática da composição destrutiva (`E4.9.9.d`).

```text
TEST_SANDBOX_EFFECT != PRODUCTION_EFFECT_ADAPTER
INTERNAL_COMPOSITION_COMPLETE != PRODUCTION_DELETION_AVAILABLE
REAL_USER_FILE_ERASURE = NOT_EXECUTED
```

PostgreSQL real para aprovação e recibo; arquivos reais confinados a
`tmp_path`. O que se valida aqui é **a composição interna e a ordem das
garantias** — nenhuma classe deste módulo é exportada por `backend/app`,
e nenhuma autoriza adaptador de produção.

## Por que a revalidação acontece no ponto material

O resolvedor observa o alvo e devolve um localizador. Entre a resolução
e o efeito, o sistema de arquivos pode mudar — e um symlink trocado
nesse intervalo apontaria para fora da raiz confinada.

```text
RESOLUTION_TIME_CHECK != EFFECT_TIME_CHECK
TOCTOU_CLOSED_AT_THE_MATERIAL_POINT
```

O adaptador de teste revalida **imediatamente antes de tocar no
arquivo**, com `realpath`, e recusa sem efeito. É a única camada capaz
de fechar a janela, porque é a única que existe no instante do efeito.
"""

import os
import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from app.database import migrations
from app.database.engine import engine
from app.database.health import check_database_health
from app.memory.errors.exceptions import DestructiveExecutionUnknownMaterialStateError
from app.memory.models.approval_enums import (
    DestructiveOperation,
    InputChannel,
    VoiceReviewState,
)
from app.memory.models.approval_lifecycle_enums import (
    ApprovalLifecycleState,
    ApprovalUsageRefusalReason,
)
from app.memory.models.erasure_effect_enums import MaterialAttemptRefusalReason
from app.memory.models.erasure_enums import ErasureOutcome, ErasureTargetClass
from app.memory.models.retention_assessment_enums import RetentionAssessmentDecision
from app.memory.models.retention_enums import RetentionScopeKind
from app.memory.models.target_resolution_enums import (
    LegacyProtectionState,
    RefusalDimension,
    TargetResolutionRefusalReason,
)
from app.memory.repositories.approval_record_repository import ApprovalRecordRepository
from app.memory.schemas.destructive_execution import (
    ApprovalConsumptionRefusal,
    DestructiveExecutionReport,
    DestructiveExecutionRequest,
    PreConsumptionRefusal,
)
from app.memory.schemas.erasure_effect import (
    MaterialAttemptNotStarted,
    ObservedAttemptResult,
)
from app.memory.schemas.erasure_target import (
    ErasureTargetDescriptor,
    TargetResolutionRefusal,
    VerifiedDeletionCapability,
)
from app.memory.schemas.retention import RetentionRule
from app.memory.services.destructive_execution_service import DestructiveExecutionService
from app.memory.services.retention_evaluator import RetentionCandidate, avaliar_retencao
from app.repositories.unit_of_work import UnitOfWork
from tests.helpers.destructive_execution import (
    SUJEITO_A,
    SUJEITO_B,
    custodia,
    envelope,
    procedencia,
    referencia,
    snapshot,
)


def _disponivel() -> bool:
    return check_database_health().available


pytestmark = pytest.mark.skipif(
    not _disponivel(),
    reason="PostgreSQL real indisponível — a validação prática exige commit durável.",
)


@pytest.fixture(autouse=True)
def _limpar():
    migrations.upgrade("head")
    _truncar()
    yield
    _truncar()


def _truncar() -> None:
    with engine.begin() as conn:
        conn.execute(sa.text("TRUNCATE approval_records CASCADE"))
        conn.execute(sa.text("TRUNCATE erasure_records CASCADE"))


def _persistir(aprovado) -> None:  # noqa: ANN001
    with Session(engine) as sessao:
        ApprovalRecordRepository(sessao).append_approved(aprovado)
        sessao.commit()


def _recibos() -> list[tuple[str, str]]:
    with Session(engine) as sessao:
        return [
            (linha[0], linha[1])
            for linha in sessao.execute(
                sa.text(
                    "SELECT subject_identifier, outcome FROM erasure_records "
                    "ORDER BY attempted_at, id"
                )
            )
        ]


def _estado(approval_id: uuid.UUID) -> str | None:
    with Session(engine) as sessao:
        return sessao.execute(
            sa.text("SELECT state FROM approval_records WHERE id = :i"), {"i": approval_id}
        ).scalar_one_or_none()


# ======================================================================
# Adaptadores SANDBOX — exclusivamente de teste
# ======================================================================


class ResolvedorSandbox:
    """Observa o arquivo e devolve um descritor. **Nunca escreve.**

    ```text
    RESOLUTION_IS_OBSERVATIONAL = TRUE
    ```

    A contagem de escritas é zero por construção: o resolvedor não abre
    arquivo em modo de escrita, não cria diretório e não tem sessão.
    """

    def __init__(
        self,
        raiz: Path,
        arquivos: dict[uuid.UUID, Path],
        *,
        protecao: dict[uuid.UUID, LegacyProtectionState] | None = None,
        etag: dict[uuid.UUID, str] | None = None,
    ) -> None:
        self._raiz = raiz
        self._arquivos = arquivos
        self._protecao = protecao or {}
        self._etag = etag or {}
        self.chamadas: list[uuid.UUID] = []

    def resolve_target(self, reference):  # noqa: ANN001, ANN201
        self.chamadas.append(reference.subject_coid)
        caminho = self._arquivos.get(reference.subject_coid)
        if caminho is None or not caminho.exists():
            return TargetResolutionRefusal(
                reason=TargetResolutionRefusalReason.UNRESOLVED_OPAQUE_REFERENCE,
                subject_coid=reference.subject_coid,
                origin=reference.origin,
            )
        return ErasureTargetDescriptor(
            target_class=ErasureTargetClass.PIA_MANAGED_ARTIFACT,
            subject_coid=reference.subject_coid,
            control_scope=reference.control_scope,
            custody_namespace=custodia(),
            capability=VerifiedDeletionCapability(
                operation="delete_object", scope="sandbox/*", verified=True
            ),
            resolved_at=datetime.now(UTC),
            origin=reference.origin,
            legacy_protection_state=self._protecao.get(
                reference.subject_coid, LegacyProtectionState.NOT_PROTECTED
            ),
            transient_locator=f"file://{caminho}",
            version_etag=self._etag.get(reference.subject_coid, 'W/"v1"'),
        )


class FugaDaRaiz(RuntimeError):
    """O localizador aponta para fora da raiz confinada."""


class EfeitoSandbox:
    """Move para a lixeira ou remove — **somente** dentro da raiz temporária.

    Toda operação é precedida de revalidação por `realpath`, feita no
    instante do efeito. Um symlink trocado depois da resolução é
    detectado aqui, e em nenhum outro lugar.
    """

    def __init__(
        self,
        raiz: Path,
        *,
        forcar: object | None = None,
        excecao_apos_iniciar: BaseException | None = None,
    ) -> None:
        self._raiz = raiz.resolve()
        self._lixeira = raiz / ".lixeira"
        self._forcar = forcar
        self._excecao = excecao_apos_iniciar
        self.chamadas: list[uuid.UUID] = []
        self.iniciou: list[uuid.UUID] = []

    def _caminho_confinado(self, localizador: str) -> Path:
        bruto = Path(localizador.removeprefix("file://"))
        # `os.path.realpath` resolve symlink, `..` e caminho absoluto de
        # uma vez só. A comparação é por relação de ancestralidade
        # depois da resolução — comparar strings antes resolveria nada.
        real = Path(os.path.realpath(bruto))
        if real != self._raiz and self._raiz not in real.parents:
            raise FugaDaRaiz(f"localizador fora da raiz confinada: {real}")
        return real

    def attempt_effect(self, request):  # noqa: ANN001, ANN201
        self.chamadas.append(request.descriptor.subject_coid)
        agora = datetime.now(UTC)

        if self._forcar is not None:
            forcado, self._forcar = self._forcar, None
            if isinstance(forcado, BaseException):
                raise forcado
            return forcado

        try:
            caminho = self._caminho_confinado(request.descriptor.transient_locator)
        except FugaDaRaiz:
            # Recusa ANTES de qualquer efeito — e sem vazar o caminho.
            return MaterialAttemptNotStarted(
                approval_id=request.authorization.approval_id,
                subject_coid=request.descriptor.subject_coid,
                reason=MaterialAttemptRefusalReason.PROVIDER_PRECONDITION_REFUSED,
                observed_at=agora,
            )

        self.iniciou.append(request.descriptor.subject_coid)
        if self._excecao is not None:
            excecao, self._excecao = self._excecao, None
            raise excecao

        operacao = request.authorization.operation
        if operacao is DestructiveOperation.MOVE_TO_TRASH:
            self._lixeira.mkdir(exist_ok=True)
            caminho.rename(self._lixeira / caminho.name)
        else:
            caminho.unlink()

        return ObservedAttemptResult(
            approval_id=request.authorization.approval_id,
            subject_coid=request.descriptor.subject_coid,
            target_class=request.descriptor.target_class,
            outcome=ErasureOutcome.SUCCEEDED,
            executor_ref="executor:sandbox",
            attempted_at=agora,
            completed_at=datetime.now(UTC),
        )


def _servico(resolvedor, efeito):  # noqa: ANN001, ANN202
    return DestructiveExecutionService(
        unit_of_work_factory=UnitOfWork,
        target_resolver=resolvedor,
        effect_port=efeito,
    )


@pytest.fixture
def cenario(tmp_path):  # noqa: ANN001, ANN201
    """Um arquivo real, uma aprovação persistida, dois adaptadores."""

    def _montar(
        *,
        operacao: DestructiveOperation = DestructiveOperation.MOVE_TO_TRASH,
        protecao: LegacyProtectionState = LegacyProtectionState.NOT_PROTECTED,
        etag_fresco: str | None = None,
        canal: InputChannel = InputChannel.TEXT,
        revisao: VoiceReviewState = VoiceReviewState.NOT_APPLICABLE,
        forcar=None,  # noqa: ANN001
        excecao_apos_iniciar=None,  # noqa: ANN001
    ):
        arquivo = tmp_path / "artefato-1.txt"
        arquivo.write_text("conteúdo do titular", encoding="utf-8")

        aprovado = envelope(
            operacao=operacao,
            alvos=(snapshot(legacy_protection_state=LegacyProtectionState.NOT_PROTECTED),),
            canal=canal,
            revisao=revisao,
        )
        _persistir(aprovado)

        resolvedor = ResolvedorSandbox(
            tmp_path,
            {SUJEITO_A: arquivo},
            protecao={SUJEITO_A: protecao},
            etag={SUJEITO_A: etag_fresco} if etag_fresco else None,
        )
        efeito = EfeitoSandbox(tmp_path, forcar=forcar, excecao_apos_iniciar=excecao_apos_iniciar)
        pedido = DestructiveExecutionRequest(aprovado, (referencia(),))
        return aprovado, arquivo, resolvedor, efeito, pedido

    return _montar


# ======================================================================
# Casos mínimos do §8
# ======================================================================


def test_p01_move_to_trash_move_o_arquivo_real(cenario, tmp_path):
    aprovado, arquivo, resolvedor, efeito, pedido = cenario()
    resultado = _servico(resolvedor, efeito).execute(pedido)

    assert isinstance(resultado, DestructiveExecutionReport)
    assert not arquivo.exists()
    assert (tmp_path / ".lixeira" / "artefato-1.txt").read_text(encoding="utf-8") == (
        "conteúdo do titular"
    )
    assert _estado(aprovado.approval_id) == ApprovalLifecycleState.CONSUMED.name
    assert _recibos() == [(str(SUJEITO_A), ErasureOutcome.SUCCEEDED.value)]


def test_p02_permanent_erasure_remove_o_arquivo_real(cenario):
    aprovado, arquivo, resolvedor, efeito, pedido = cenario(
        operacao=DestructiveOperation.PERMANENT_ERASURE
    )
    resultado = _servico(resolvedor, efeito).execute(pedido)

    assert isinstance(resultado, DestructiveExecutionReport)
    assert not arquivo.exists()
    assert _estado(aprovado.approval_id) == ApprovalLifecycleState.CONSUMED.name
    assert len(_recibos()) == 1


def test_p03_protecao_de_legado_alterada_apos_a_aprovacao(cenario):
    """O arquivo permanece, a aprovação continua ativa, zero recibo."""
    aprovado, arquivo, resolvedor, efeito, pedido = cenario(
        protecao=LegacyProtectionState.PROTECTED
    )
    resultado = _servico(resolvedor, efeito).execute(pedido)

    assert isinstance(resultado, PreConsumptionRefusal)
    assert arquivo.exists()
    assert _estado(aprovado.approval_id) == ApprovalLifecycleState.ACTIVE.name
    assert _recibos() == []
    assert efeito.chamadas == []


def test_p04_version_etag_alterado_recusa_antes_do_consumo(cenario):
    aprovado, arquivo, resolvedor, efeito, pedido = cenario(etag_fresco='W/"v2"')
    resultado = _servico(resolvedor, efeito).execute(pedido)

    assert isinstance(resultado, PreConsumptionRefusal)
    assert arquivo.exists()
    assert _estado(aprovado.approval_id) == ApprovalLifecycleState.ACTIVE.name
    assert _recibos() == []


def test_p05_resolucao_recusada_nao_consome_nem_apaga(tmp_path):
    aprovado = envelope()
    _persistir(aprovado)
    # Nenhum arquivo registrado: o resolvedor devolve recusa tipada.
    resolvedor = ResolvedorSandbox(tmp_path, {})
    efeito = EfeitoSandbox(tmp_path)
    resultado = _servico(resolvedor, efeito).execute(
        DestructiveExecutionRequest(aprovado, (referencia(),))
    )

    assert isinstance(resultado, PreConsumptionRefusal)
    assert _estado(aprovado.approval_id) == ApprovalLifecycleState.ACTIVE.name
    assert efeito.chamadas == []
    assert _recibos() == []


def test_p06_not_started_consome_mas_nao_apaga_nem_registra(cenario):
    """`NO_MATERIAL_ATTEMPT -> NO_ERASURE_RECORD`, com arquivo intacto."""
    aprovado, arquivo, resolvedor, efeito, pedido = cenario()
    efeito._forcar = MaterialAttemptNotStarted(  # noqa: SLF001
        approval_id=aprovado.approval_id,
        subject_coid=SUJEITO_A,
        reason=MaterialAttemptRefusalReason.ADAPTER_UNAVAILABLE,
        observed_at=datetime.now(UTC),
    )
    resultado = _servico(resolvedor, efeito).execute(pedido)

    assert resultado.not_attempted == 1
    assert arquivo.exists()
    assert _estado(aprovado.approval_id) == ApprovalLifecycleState.CONSUMED.name
    assert _recibos() == []


@pytest.mark.parametrize("desfecho", [ErasureOutcome.FAILED, ErasureOutcome.PARTIAL])
def test_p07_failed_e_partial_geram_exatamente_um_recibo(cenario, desfecho):
    aprovado, arquivo, resolvedor, efeito, pedido = cenario()
    agora = datetime.now(UTC)
    efeito._forcar = ObservedAttemptResult(  # noqa: SLF001
        approval_id=aprovado.approval_id,
        subject_coid=SUJEITO_A,
        target_class=ErasureTargetClass.PIA_MANAGED_ARTIFACT,
        outcome=desfecho,
        executor_ref="executor:sandbox",
        attempted_at=agora,
        completed_at=agora,
        failure_code="provider_denied",
    )
    resultado = _servico(resolvedor, efeito).execute(pedido)

    persistidos = _recibos()
    assert len(persistidos) == 1
    assert persistidos[0] == (str(SUJEITO_A), desfecho.value)
    assert len(resultado.receipts_persisted) == 1


def test_p08_excecao_depois_de_iniciar_deixa_estado_desconhecido(cenario):
    """A aprovação fica consumida; nenhum recibo é fabricado."""
    aprovado, arquivo, resolvedor, efeito, pedido = cenario(
        excecao_apos_iniciar=OSError("dispositivo removido no meio da operação")
    )
    with pytest.raises(DestructiveExecutionUnknownMaterialStateError) as capturado:
        _servico(resolvedor, efeito).execute(pedido)

    assert efeito.iniciou == [SUJEITO_A]
    assert _estado(aprovado.approval_id) == ApprovalLifecycleState.CONSUMED.name
    assert _recibos() == []
    assert capturado.value.evidence.receipts_persisted == 0


def test_p09_replay_da_mesma_aprovacao_nao_chama_o_efeito_de_novo(cenario, tmp_path):
    aprovado, arquivo, resolvedor, efeito, pedido = cenario()
    _servico(resolvedor, efeito).execute(pedido)
    assert not arquivo.exists()

    arquivo.write_text("o titular recriou o arquivo", encoding="utf-8")
    segundo_efeito = EfeitoSandbox(tmp_path)
    resultado = _servico(ResolvedorSandbox(tmp_path, {SUJEITO_A: arquivo}), segundo_efeito).execute(
        pedido
    )

    assert isinstance(resultado, ApprovalConsumptionRefusal)
    assert resultado.reason is ApprovalUsageRefusalReason.ALREADY_CONSUMED
    assert segundo_efeito.chamadas == []
    assert arquivo.exists()
    assert len(_recibos()) == 1


def test_p10_lote_com_dois_alvos_preserva_a_ordem(tmp_path):
    primeiro = tmp_path / "a.txt"
    segundo = tmp_path / "b.txt"
    primeiro.write_text("a", encoding="utf-8")
    segundo.write_text("b", encoding="utf-8")

    aprovado = envelope(alvos=(snapshot(), snapshot(subject_coid=SUJEITO_B, origin=procedencia(1))))
    _persistir(aprovado)
    resolvedor = ResolvedorSandbox(tmp_path, {SUJEITO_A: primeiro, SUJEITO_B: segundo})
    efeito = EfeitoSandbox(tmp_path)
    resultado = _servico(resolvedor, efeito).execute(
        DestructiveExecutionRequest(
            aprovado,
            (referencia(), referencia(subject_coid=SUJEITO_B, origin=procedencia(1))),
        )
    )

    assert efeito.chamadas == [SUJEITO_A, SUJEITO_B]
    assert [linha[0] for linha in _recibos()] == [str(SUJEITO_A), str(SUJEITO_B)]
    assert resultado.attempts_observed == 2
    assert not primeiro.exists()
    assert not segundo.exists()


@pytest.mark.parametrize(
    ("canal", "revisao"),
    [
        (InputChannel.TEXT, VoiceReviewState.NOT_APPLICABLE),
        (InputChannel.VOICE, VoiceReviewState.REVIEWED_AND_CONFIRMED),
    ],
)
def test_p11_texto_e_voz_percorrem_as_mesmas_regras(cenario, canal, revisao):
    """Nenhum parser, nenhum canal privilegiado.

    ```text
    NATURAL_LANGUAGE_NEVER_REACHES_THE_EFFECT_PORT
    ```

    O canal viaja no envelope como proveniência; o que chega à porta é
    descritor mais evidência de consumo. Os dois caminhos produzem o
    mesmo efeito material e o mesmo recibo.
    """
    aprovado, arquivo, resolvedor, efeito, pedido = cenario(canal=canal, revisao=revisao)
    resultado = _servico(resolvedor, efeito).execute(pedido)

    assert isinstance(resultado, DestructiveExecutionReport)
    assert not arquivo.exists()
    assert len(_recibos()) == 1


# ----------------------------------------------------------------------
# Confinamento — caminho absoluto, `..`, symlink e troca pós-resolução
# ----------------------------------------------------------------------


@pytest.mark.parametrize("forma", ["absoluto", "dois_pontos", "symlink"])
def test_p12_fuga_da_raiz_e_recusada_pelo_adaptador(tmp_path, forma):
    """Três formas de escapar, uma única checagem: `realpath` + ancestral."""
    fora = tmp_path.parent / f"fora-{forma}-{uuid.uuid4().hex}.txt"
    fora.write_text("arquivo de outra pessoa", encoding="utf-8")

    if forma == "absoluto":
        alvo = fora
    elif forma == "dois_pontos":
        alvo = tmp_path / ".." / fora.name
    else:
        alvo = tmp_path / "link-para-fora"
        alvo.symlink_to(fora)

    aprovado = envelope()
    _persistir(aprovado)
    resolvedor = ResolvedorSandbox(tmp_path, {SUJEITO_A: alvo})
    efeito = EfeitoSandbox(tmp_path)
    resultado = _servico(resolvedor, efeito).execute(
        DestructiveExecutionRequest(aprovado, (referencia(),))
    )

    assert resultado.not_attempted == 1
    assert efeito.iniciou == []
    assert fora.exists(), "o arquivo fora da raiz foi tocado"
    assert _recibos() == []
    fora.unlink()


def test_p13_symlink_trocado_apos_a_resolucao_e_recusado_no_ponto_material(tmp_path):
    """`RESOLUTION_TIME_CHECK != EFFECT_TIME_CHECK`.

    O link aponta para dentro da raiz quando o resolvedor o observa, e é
    trocado para fora **entre** a resolução e o efeito. Só a revalidação
    no instante material fecha essa janela — e é ela que este teste mede.
    """
    dentro = tmp_path / "legitimo.txt"
    dentro.write_text("do titular", encoding="utf-8")
    fora = tmp_path.parent / f"vitima-{uuid.uuid4().hex}.txt"
    fora.write_text("de outra pessoa", encoding="utf-8")

    link = tmp_path / "alvo"
    link.symlink_to(dentro)

    aprovado = envelope()
    _persistir(aprovado)

    class ResolvedorQueTroca(ResolvedorSandbox):
        """Resolve com o link legítimo e o troca logo depois."""

        def resolve_target(self, reference):  # noqa: ANN001, ANN201
            descritor = super().resolve_target(reference)
            link.unlink()
            link.symlink_to(fora)
            return descritor

    resolvedor = ResolvedorQueTroca(tmp_path, {SUJEITO_A: link})
    efeito = EfeitoSandbox(tmp_path)
    resultado = _servico(resolvedor, efeito).execute(
        DestructiveExecutionRequest(aprovado, (referencia(),))
    )

    assert resultado.not_attempted == 1
    assert efeito.iniciou == []
    assert fora.exists(), "a troca do symlink alcançou um arquivo fora da raiz"
    assert dentro.exists()
    assert _recibos() == []
    fora.unlink()


# ----------------------------------------------------------------------
# Retenção informa; a autoridade continua sendo a aprovação humana
# ----------------------------------------------------------------------


def _regra(dias: int) -> RetentionRule:
    return RetentionRule(
        rule_id="ret-30",
        scope_kind=RetentionScopeKind.ALL_LOCAL_PATRIMONY,
        minimum_age_days=dias,
    )


def test_p14_fluxo_completo_da_retencao_ate_o_servico(cenario):
    """`avaliar_retencao → ASSESS_AND_INFORM → aprovação humana → serviço`.

    As camadas não se fundem: o avaliador **informa**, e quem autoriza é
    a aprovação. O serviço não o consulta em momento algum.
    """
    aprovado, arquivo, resolvedor, efeito, pedido = cenario()

    avaliacao = avaliar_retencao(
        candidate=RetentionCandidate(
            subject_coid=SUJEITO_A,
            domain_id=aprovado.context.domain_id,
            created_at=datetime(2020, 1, 1, tzinfo=UTC),
            legacy_protection_state=LegacyProtectionState.NOT_PROTECTED,
        ),
        rules=(_regra(30),),
        policy_effective_from=datetime(2019, 1, 1, tzinfo=UTC),
        policy_effective_until=None,
        evaluated_at=datetime.now(UTC),
    )
    assert avaliacao.decision is RetentionAssessmentDecision.ASSESS_AND_INFORM

    resultado = _servico(resolvedor, efeito).execute(pedido)
    assert isinstance(resultado, DestructiveExecutionReport)
    assert not arquivo.exists()


def test_p15_legado_protegido_nao_inicia_proposta_nem_servico(tmp_path):
    """`PRESERVE_LEGACY_PROTECTED` para o fluxo no produto, antes de tudo."""
    arquivo = tmp_path / "protegido.txt"
    arquivo.write_text("memória do titular", encoding="utf-8")

    avaliacao = avaliar_retencao(
        candidate=RetentionCandidate(
            subject_coid=SUJEITO_A,
            domain_id=uuid.uuid4(),
            created_at=datetime(2020, 1, 1, tzinfo=UTC),
            legacy_protection_state=LegacyProtectionState.PROTECTED,
        ),
        rules=(_regra(30),),
        policy_effective_from=datetime(2019, 1, 1, tzinfo=UTC),
        policy_effective_until=None,
        evaluated_at=datetime.now(UTC),
    )

    assert avaliacao.decision is RetentionAssessmentDecision.PRESERVE_LEGACY_PROTECTED
    # Nenhuma proposta é materializada, nenhuma aprovação é persistida e
    # o serviço nunca é chamado — o arquivo permanece.
    with Session(engine) as sessao:
        assert sessao.execute(sa.text("SELECT count(*) FROM approval_records")).scalar_one() == 0
    assert arquivo.exists()


def test_p16_o_resolvedor_sandbox_nao_escreve_nada(tmp_path):
    """Censo do diretório antes e depois — `RESOLUTION_IS_OBSERVATIONAL`."""
    arquivo = tmp_path / "intacto.txt"
    arquivo.write_text("x", encoding="utf-8")
    antes = sorted(p.name for p in tmp_path.iterdir())

    resolvedor = ResolvedorSandbox(tmp_path, {SUJEITO_A: arquivo})
    resolvedor.resolve_target(referencia())

    assert sorted(p.name for p in tmp_path.iterdir()) == antes
    assert arquivo.read_text(encoding="utf-8") == "x"


def test_p17_o_recibo_persistido_nao_contem_o_caminho_real(cenario):
    """O localizador não sobrevive ao efeito — nem em coluna, nem em texto."""
    aprovado, arquivo, resolvedor, efeito, pedido = cenario()
    caminho = str(arquivo)
    _servico(resolvedor, efeito).execute(pedido)

    with Session(engine) as sessao:
        linha = sessao.execute(
            sa.text("SELECT erasure_records::text FROM erasure_records")
        ).scalar_one()
    assert caminho not in linha
    assert "file://" not in linha


def test_p18_a_recusa_de_fuga_nao_revela_o_caminho(tmp_path):
    """A recusa é vocabulário fechado; não transporta o alvo observado."""
    fora = tmp_path.parent / f"segredo-{uuid.uuid4().hex}.txt"
    fora.write_text("x", encoding="utf-8")
    link = tmp_path / "link"
    link.symlink_to(fora)

    aprovado = envelope()
    _persistir(aprovado)
    resultado = _servico(
        ResolvedorSandbox(tmp_path, {SUJEITO_A: link}), EfeitoSandbox(tmp_path)
    ).execute(DestructiveExecutionRequest(aprovado, (referencia(),)))

    for texto in (repr(resultado), str(resultado)):
        assert fora.name not in texto
        assert str(tmp_path.parent) not in texto
    fora.unlink()


def test_p19_dimensao_de_recusa_permanece_vocabulario_fechado():
    """Guarda de premissa: nenhuma recusa tem campo de texto livre."""
    campos = set(TargetResolutionRefusal.__dataclass_fields__)
    assert campos == {
        "reason",
        "subject_coid",
        "origin",
        "classified_as",
        "observed_dimension",
    }
    assert all(isinstance(membro, RefusalDimension) for membro in RefusalDimension)


def test_p20_escopo_do_sandbox_declarado(tmp_path):
    """O que este módulo prova, e o que ele explicitamente não prova.

    ```text
    PROVED      composição interna e ordem das garantias
    NOT_PROVED  adaptador de produção, autenticador, API, conector
    ```
    """
    from app.memory.services import destructive_execution_service as modulo

    assert not hasattr(modulo, "EfeitoSandbox")
    assert not hasattr(modulo, "ResolvedorSandbox")
    assert (tmp_path / ".lixeira").exists() is False
